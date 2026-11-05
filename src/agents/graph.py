"""Orchestrator graph of the research lab (protocol section 08; decision S33-7): LangGraph StateGraph of the roles
Orchestrator (deterministic), Hypothesis (LLM), Coder (LLM), Validator (deterministic tool), Skeptic (LLM, veto), Risk
(LLM plus tool, veto). Agents propose features through the MCP server ddmi-vault only and never trade; at most
`max_candidates` proposals and the USD hard stop of src.agents.llm; every LLM call is cached for offline replay.

Per proposal: Hypothesis -> Coder -> Validator (run_walkforward through MCP) -> [Skeptic -> Risk if the Validator passed]
-> record. Injected specs (the planted-signal test, S33-8) enter at the Validator. A candidate survives if it passes the
Validator and neither the Skeptic nor Risk vetoes; an unparseable Skeptic or Risk answer counts as a veto, an
unparseable Coder answer as an invalid spec. Risk (S33-14): the tool's three checks (turnover, residual beta, cost
sensitivity, each against the base rung) veto deterministically; only if all pass is the Risk LLM asked, and its veto
counts only for a named concern (concentration, mechanism, instability) that does not rest on Sharpe ratios or costs. Each run writes <run_dir>/candidates.jsonl (one line per proposal).
"""

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents import prompts
from src.agents.llm import LLM, BudgetExceeded
from src.agents.vault_server import VaultServer, build_mcp, call_tool
from src.config import load_config


class LabState(TypedDict, total=False):
    records: list[dict]
    current: dict
    llm_done: int
    injected: list[dict]
    stopped: str


class Lab:
    """One lab run: the vault server core (behind its MCP server), the LLM, the limits and the run folder."""

    def __init__(self, core: VaultServer, model: LLM, run_dir: Path, *, n_llm: int, injected: list[dict] | None = None,
                 max_candidates: int | None = None, as_of: str | None = None, cfg: dict | None = None) -> None:
        self.cfg = load_config() if cfg is None else cfg
        self.core, self.llm, self.run_dir = core, model, Path(run_dir)
        self.mcp = build_mcp(core)
        self.n_llm = int(n_llm)
        self.injected = list(injected or [])
        cap = int(self.cfg["agent_lab"]["max_candidates"]) if max_candidates is None else int(max_candidates)
        if self.n_llm + len(self.injected) > cap:
            raise ValueError(f"{self.n_llm} LLM and {len(self.injected)} injected candidates exceed the cap of {cap}")
        self.as_of = str(self.cfg["split"]["in_sample_end"]) if as_of is None else as_of
        self._features: dict | None = None

    # -- tools -------------------------------------------------------------------------------------------------------------

    def tool(self, name: str, arguments: dict) -> dict:
        return call_tool(self.mcp, name, arguments)

    def features_summary(self) -> dict:
        if self._features is None:
            self._features = self.tool("get_features", {"as_of": self.as_of})
        return self._features

    # -- nodes -------------------------------------------------------------------------------------------------------------

    def orchestrator(self, state: LabState) -> LabState:
        return {}

    def route(self, state: LabState) -> str:
        if state.get("stopped"):
            return "end"
        if state.get("llm_done", 0) < self.n_llm:
            return "hypothesis"
        if state.get("injected"):
            return "inject"
        return "end"

    def _number(self, state: LabState) -> int:
        return len(state.get("records", [])) + 1

    def hypothesis(self, state: LabState) -> LabState:
        number = self._number(state)
        current = {"candidate": number, "source": "llm", "cost_usd": 0.0, "review_cost_usd": 0.0}
        try:
            history = prompts.history_lines(state.get("records", []))
            trials = prompts.trial_summaries(self.tool("get_trial_history", {})["trials"])  # S33-7, S33-15 (4)
            answer = self.llm.call("hypothesis", prompts.hypothesis_messages(self.features_summary(), history, trials))
        except BudgetExceeded as error:
            return {"stopped": str(error)}
        current["cost_usd"] += answer["recorded_cost_usd"]
        current["hypothesis"] = answer["parsed"] if answer["parsed"] is not None else {"unparsed": answer["content"]}
        return {"current": current, "llm_done": state.get("llm_done", 0) + 1}

    def coder(self, state: LabState) -> LabState:
        current = dict(state["current"])
        try:
            answer = self.llm.call("coder", prompts.coder_messages(current["hypothesis"]))
        except BudgetExceeded as error:
            return {"stopped": str(error), "current": current}
        current["cost_usd"] += answer["recorded_cost_usd"]
        parsed = answer["parsed"] or {}
        spec = parsed.get("spec", parsed if parsed else None)
        # S33-15 (1): anything but a JSON object is an invalid spec, recorded as such by the Validator
        current["spec"] = spec if isinstance(spec, dict) else {"unparsed": answer["content"]}
        return {"current": current}

    def inject(self, state: LabState) -> LabState:
        queue = list(state["injected"])
        item = queue.pop(0)
        spec = item["spec"]
        name = spec.get("name") if isinstance(spec, dict) else None
        # S33-15: the LLMs see an injected spec like any proposal; its origin stays in `source`, which no prompt shows
        current = {"candidate": self._number(state), "source": item["source"], "hypothesis": {"feature_idea": name},
                   "spec": spec, "cost_usd": 0.0, "review_cost_usd": 0.0}
        return {"current": current, "injected": queue}

    def validator(self, state: LabState) -> LabState:
        current = dict(state["current"])
        try:
            result = self.tool("run_walkforward", {"spec": current["spec"], "candidate": current["candidate"],
                                                   "cost_usd": round(current["cost_usd"], 8)})
        except Exception as error:  # noqa: BLE001 - S33-15 (1): a failed tool call rejects the proposal, never the run
            result = {"stage": "tool_error", "passed": False, "reason": f"{type(error).__name__}: {error}"}
        current.update(stage=result["stage"], checks=result.get("checks", {}), metrics=result.get("metrics"),
                       risk_checks=result.get("risk_checks"), passed_validator=bool(result["passed"]),
                       validator_reason=result.get("reason"), spec_hash=result.get("spec_hash"))
        return {"current": current}

    def after_validator(self, state: LabState) -> str:
        return "skeptic" if state["current"].get("passed_validator") else "record"

    def skeptic(self, state: LabState) -> LabState:
        current = dict(state["current"])
        messages = prompts.skeptic_messages(current["hypothesis"], current["spec"], current["checks"], current["metrics"],
                                            current["candidate"])
        try:
            answer = self.llm.call("skeptic", messages)
        except BudgetExceeded as error:
            current["skeptic"] = {"veto": True, "reasons": "not reviewed: budget stop"}
            return {"current": current, "stopped": str(error)}
        current["review_cost_usd"] += answer["recorded_cost_usd"]
        current["skeptic"] = _verdict(answer["parsed"], "reasons", answer["content"])
        return {"current": current}

    def risk(self, state: LabState) -> LabState:
        """Risk = tool + LLM (S33-14): a failed tool check is a veto and the LLM is not called; otherwise the LLM may
        veto for a named concern, and an invalid veto is recorded but does not count."""
        current = dict(state["current"])
        checks = current.get("risk_checks") or {}
        if not checks.get("passed"):
            failed = checks.get("failed", ["risk_checks missing"])
            current["risk"] = {"veto": True, "by": "tool", "notes": f"tool checks failed: {', '.join(failed)}"}
            return {"current": current}
        try:
            answer = self.llm.call("risk", prompts.risk_messages(current["spec"], checks, current["metrics"]))
        except BudgetExceeded as error:
            current["risk"] = {"veto": True, "by": "budget", "notes": "not reviewed: budget stop"}
            return {"current": current, "stopped": str(error)}
        current["review_cost_usd"] += answer["recorded_cost_usd"]
        current["risk"] = risk_verdict(answer["parsed"], answer["content"])
        return {"current": current}

    def after_skeptic(self, state: LabState) -> str:
        return "record" if state.get("stopped") else "risk"

    def record(self, state: LabState) -> LabState:
        current = dict(state.get("current") or {})
        if not current or "stage" not in current:
            return {}
        current["survived"] = bool(current.get("passed_validator") and not current.get("skeptic", {}).get("veto", True)
                                   and not current.get("risk", {}).get("veto", True))
        if current["survived"]:
            self.core.mark_survivor(current["spec"])
        records = list(state.get("records", [])) + [current]
        return {"records": records, "current": {}}

    # -- graph -------------------------------------------------------------------------------------------------------------

    def build(self):
        graph = StateGraph(LabState)
        for name in ("orchestrator", "hypothesis", "coder", "inject", "validator", "skeptic", "risk", "record"):
            graph.add_node(name, getattr(self, name))
        graph.set_entry_point("orchestrator")
        graph.add_conditional_edges("orchestrator", self.route,
                                    {"hypothesis": "hypothesis", "inject": "inject", "end": END})
        graph.add_conditional_edges("hypothesis", lambda s: "end" if s.get("stopped") else "coder",
                                    {"coder": "coder", "end": END})
        graph.add_conditional_edges("coder", lambda s: "end" if s.get("stopped") else "validator",
                                    {"validator": "validator", "end": END})
        graph.add_edge("inject", "validator")
        graph.add_conditional_edges("validator", self.after_validator, {"skeptic": "skeptic", "record": "record"})
        graph.add_conditional_edges("skeptic", self.after_skeptic, {"risk": "risk", "record": "record"})
        graph.add_edge("risk", "record")
        graph.add_edge("record", "orchestrator")
        return graph.compile()

    def run(self) -> dict:
        """Run the graph; writes candidates.jsonl and returns {"records", "stopped"}."""
        state = self.build().invoke({"records": [], "llm_done": 0, "injected": list(self.injected)},
                                    {"recursion_limit": 20 * (self.n_llm + len(self.injected)) + 50})
        records = state.get("records", [])
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.run_dir / "candidates.jsonl", "w", encoding="utf-8", newline="\n") as handle:
            handle.writelines(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) + "\n" for record in records)
        return {"records": records, "stopped": state.get("stopped")}


def _verdict(parsed: dict | None, field: str, content: str) -> dict:
    """{"veto": bool, field: str}; an unparseable answer or a non-boolean veto counts as a veto (S33-7)."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("veto"), bool):
        return {"veto": True, field: f"unparseable answer counted as a veto: {content[:200]}"}
    return {"veto": parsed["veto"], field: str(parsed.get(field, ""))}


# S33-14, S33-15 (2): letters, not word characters, bound the words, so snake_case names such as net_sharpe match
INVALID_VETO_WORDS = re.compile(r"(?<![a-z])(sharpe|costs?|borrow)(?![a-z])", re.IGNORECASE)


def risk_verdict(parsed: dict | None, content: str) -> dict:
    """The Risk LLM's verdict after the tool checks passed (S33-14). An unparseable answer or a non-boolean veto counts
    as a veto (S33-7). A veto counts only if `concern` is one of prompts.RISK_CONCERNS and the notes do not cite a Sharpe
    ratio or costs (the words sharpe, cost, costs, borrow); otherwise it is kept as `invalid_veto` and does not count.
    Returns {"veto", "by", "concern", "notes", "llm_veto"[, "invalid_veto"]}."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("veto"), bool):
        return {"veto": True, "by": "llm", "concern": None, "llm_veto": None,
                "notes": f"unparseable answer counted as a veto: {content[:200]}"}
    concern, notes = parsed.get("concern"), str(parsed.get("notes", ""))
    verdict = {"veto": parsed["veto"], "by": "llm", "concern": concern, "notes": notes, "llm_veto": parsed["veto"]}
    if parsed["veto"]:
        if concern not in prompts.RISK_CONCERNS:
            verdict.update(veto=False, invalid_veto=f"no allowed concern named (concern = {concern!r})")
        elif INVALID_VETO_WORDS.search(notes):
            word = INVALID_VETO_WORDS.search(notes).group(0)
            verdict.update(veto=False, invalid_veto=f"the notes cite Sharpe or costs ({word!r})")
    return verdict


def build_graph(cfg: dict | None = None, *, lab: Lab | None = None) -> Any:
    """The compiled LangGraph of a configured Lab (the lab holds the server, the LLM and the limits)."""
    if lab is None:
        raise ValueError("build_graph needs a configured Lab (src.agents.graph.Lab)")
    return lab.build()


def run_lab(cfg: dict | None = None, replay: bool = False, *, lab: Lab | None = None) -> list[dict]:
    """Run a configured Lab (its LLM's mode decides live or replay) and return the candidate records."""
    if lab is None:
        raise ValueError("run_lab needs a configured Lab (src.agents.graph.Lab); see 04_agent_lab.py")
    if replay and lab.llm.mode != "replay":
        raise ValueError("run_lab(replay=True) needs an LLM in replay mode")
    return lab.run()["records"]
