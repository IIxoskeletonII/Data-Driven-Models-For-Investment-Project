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

Round 2 (Amendment 9 C2; S43-4, S43-5): prompt_round=2 uses the round-2 Hypothesis prompt, append-only (the snapshot's
trials in a cached stable block, then one block per earlier candidate of the run with the trial rows it logged, each
rendered once); coder_repairs=1 lets the Coder repair an invalid specification once,
shown the Validator's exact error (Validator -> repair -> Validator), and the record keeps every attempt ("attempts",
"repaired"). With the defaults (prompt_round=1, coder_repairs=0) the graph and its records are round 1's.
"""

import json
import re
from collections.abc import Callable
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
                 max_candidates: int | None = None, as_of: str | None = None, cfg: dict | None = None,
                 coder_repairs: int = 0, prompt_round: int = 1,
                 reserve: Callable[[list[dict]], str | None] | None = None) -> None:
        self.cfg = load_config() if cfg is None else cfg
        self.core, self.llm, self.run_dir = core, model, Path(run_dir)
        self.mcp = build_mcp(core)
        self.n_llm = int(n_llm)
        self.injected = list(injected or [])
        cap = int(self.cfg["agent_lab"]["max_candidates"]) if max_candidates is None else int(max_candidates)
        if self.n_llm + len(self.injected) > cap:
            raise ValueError(f"{self.n_llm} LLM and {len(self.injected)} injected candidates exceed the cap of {cap}")
        if prompt_round not in (1, 2) or int(coder_repairs) < 0:
            raise ValueError(f"prompt_round must be 1 or 2 and coder_repairs >= 0, got {prompt_round}, {coder_repairs}")
        self.as_of = str(self.cfg["split"]["in_sample_end"]) if as_of is None else as_of
        self.coder_repairs, self.prompt_round = int(coder_repairs), int(prompt_round)
        # S43-1, round-2 In-Sample run: reserve(messages of the next Hypothesis call) -> a stop reason or None, checked
        # only at a candidate's start, so an open candidate is never interrupted
        self.reserve = reserve
        # round-2 records carry the Coder attempts (S43-4); a round-1 lab writes exactly the records it wrote before
        self.round2 = self.prompt_round == 2 or self.coder_repairs > 0
        self._n_stable: int | None = None  # trial rows shown at the first Hypothesis call: the snapshot (S43-5)
        self._n_seen = 0  # trial rows already placed in the prompt (snapshot plus candidate blocks)
        self._blocks: list[str] = []  # rendered candidate blocks of the round-2 Hypothesis prompt, append-only
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

    def _round2_context(self, history: list[dict], trials: list[dict]) -> tuple[list[dict], list[str]]:
        """The snapshot's trials and the candidate blocks of the round-2 Hypothesis prompt (S43-5). The rows shown at the
        run's first call are the snapshot; each later row goes to exactly one candidate block, the block of the latest
        candidate recorded when the row is first seen. A block is rendered once and kept, so the prompt only grows by
        appending."""
        if self._n_stable is None:
            self._n_stable = self._n_seen = len(trials)
        new = history[len(self._blocks):]
        for position, line in enumerate(new, start=len(self._blocks) + 1):
            rows = trials[self._n_seen:] if position == len(history) else []
            self._n_seen += len(rows)
            self._blocks.append(prompts.candidate_block(position, line, rows))
        return trials[:self._n_stable], list(self._blocks)

    def _number(self, state: LabState) -> int:
        return len(state.get("records", [])) + 1

    def hypothesis(self, state: LabState) -> LabState:
        number = self._number(state)
        current = {"candidate": number, "source": "llm", "cost_usd": 0.0, "review_cost_usd": 0.0}
        try:
            history = prompts.history_lines(state.get("records", []))
            trials = prompts.trial_summaries(self.tool("get_trial_history", {})["trials"])  # S33-7, S33-15 (4)
            if self.prompt_round == 2:
                messages = prompts.hypothesis_messages_round2(self.features_summary(), *self._round2_context(
                    history, trials))
            else:
                messages = prompts.hypothesis_messages(self.features_summary(), history, trials)
            if self.reserve is not None:
                reason = self.reserve(messages)
                if reason:
                    return {"stopped": str(reason)}
            answer = self.llm.call("hypothesis", messages)
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
        current["spec"] = _coder_spec(answer)
        if self.round2:
            current.update(coder_content=answer["content"], repairs_left=self.coder_repairs, attempts=[], repaired=False)
        return {"current": current}

    def repair(self, state: LabState) -> LabState:
        """The Coder's one repair of an invalid specification (S43-4): shown its previous answer and the Validator's exact
        error. On a budget stop the first spec goes through the Validator as final, so the proposal keeps its trial row."""
        current = dict(state["current"])
        current["repairs_left"] = int(current.get("repairs_left", 0)) - 1
        messages = prompts.coder_repair_messages(current["hypothesis"], current.get("coder_content") or "",
                                                 str(current.get("validator_reason")))
        try:
            answer = self.llm.call("coder_repair", messages)
        except BudgetExceeded as error:
            # no repair was made: the first spec, now final, is the proposal's one attempt (its non-final entry dropped)
            current["repairs_left"], current["attempts"] = 0, list(current.get("attempts", []))[:-1]
            current = self._validate(current)
            return {"current": current, "stopped": str(error)}
        current["cost_usd"] += answer["recorded_cost_usd"]
        current.update(spec=_coder_spec(answer), coder_content=answer["content"], repaired=True)
        return {"current": current}

    def after_repair(self, state: LabState) -> str:
        return "record" if state.get("stopped") else "validator"

    def inject(self, state: LabState) -> LabState:
        queue = list(state["injected"])
        item = queue.pop(0)
        spec = item["spec"]
        name = spec.get("name") if isinstance(spec, dict) else None
        # S33-15: the LLMs see an injected spec like any proposal; its origin stays in `source`, which no prompt shows
        current = {"candidate": self._number(state), "source": item["source"], "hypothesis": {"feature_idea": name},
                   "spec": spec, "cost_usd": 0.0, "review_cost_usd": 0.0}
        if self.round2:  # an injected spec has no Coder, so no repair (S43-4)
            current.update(coder_content=None, repairs_left=0, attempts=[], repaired=False)
        return {"current": current, "injected": queue}

    def _validate(self, current: dict) -> dict:
        """One Validator call through MCP. Round 2 (S43-4): the call is final unless a Coder repair is still allowed."""
        current = dict(current)
        arguments = {"spec": current["spec"], "candidate": current["candidate"], "cost_usd": round(current["cost_usd"], 8)}
        if self.round2:
            attempts = list(current.get("attempts", []))
            arguments.update(final=int(current.get("repairs_left", 0)) <= 0, attempts=len(attempts) + 1)
        try:
            result = self.tool("run_walkforward", arguments)
        except Exception as error:  # noqa: BLE001 - S33-15 (1): a failed tool call rejects the proposal, never the run
            result = {"stage": "tool_error", "passed": False, "reason": f"{type(error).__name__}: {error}"}
        current.update(stage=result["stage"], checks=result.get("checks", {}), metrics=result.get("metrics"),
                       risk_checks=result.get("risk_checks"), passed_validator=bool(result["passed"]),
                       validator_reason=result.get("reason"), spec_hash=result.get("spec_hash"))
        if self.round2:
            current["attempts"] = list(current.get("attempts", [])) + [
                {"spec": current["spec"], "coder_content": current.get("coder_content"), "stage": result["stage"],
                 "reason": result.get("reason")}]
            current["repair_pending"] = result.get("final") is False
        return current

    def validator(self, state: LabState) -> LabState:
        return {"current": self._validate(state["current"])}

    def after_validator(self, state: LabState) -> str:
        current = state["current"]
        if current.get("repair_pending"):
            return "repair"
        return "skeptic" if current.get("passed_validator") else "record"

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
        for key in ("repairs_left", "repair_pending"):  # graph bookkeeping, not part of the record
            current.pop(key, None)
        current["survived"] = bool(current.get("passed_validator") and not current.get("skeptic", {}).get("veto", True)
                                   and not current.get("risk", {}).get("veto", True))
        if current["survived"]:
            self.core.mark_survivor(current["spec"])
        records = list(state.get("records", [])) + [current]
        return {"records": records, "current": {}}

    # -- graph -------------------------------------------------------------------------------------------------------------

    def build(self):
        graph = StateGraph(LabState)
        for name in ("orchestrator", "hypothesis", "coder", "inject", "validator", "repair", "skeptic", "risk", "record"):
            graph.add_node(name, getattr(self, name))
        graph.set_entry_point("orchestrator")
        graph.add_conditional_edges("orchestrator", self.route,
                                    {"hypothesis": "hypothesis", "inject": "inject", "end": END})
        graph.add_conditional_edges("hypothesis", lambda s: "end" if s.get("stopped") else "coder",
                                    {"coder": "coder", "end": END})
        graph.add_conditional_edges("coder", lambda s: "end" if s.get("stopped") else "validator",
                                    {"validator": "validator", "end": END})
        graph.add_edge("inject", "validator")
        graph.add_conditional_edges("validator", self.after_validator,
                                    {"skeptic": "skeptic", "record": "record", "repair": "repair"})
        graph.add_conditional_edges("repair", self.after_repair, {"validator": "validator", "record": "record"})
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


def _coder_spec(answer: dict) -> dict:
    """The spec of a Coder answer: its "spec" object (or the whole object); anything but a JSON object is kept as
    {"unparsed": <answer>}, an invalid spec recorded as such by the Validator (S33-15 (1))."""
    parsed = answer["parsed"] or {}
    spec = parsed.get("spec", parsed if parsed else None)
    return spec if isinstance(spec, dict) else {"unparsed": answer["content"]}


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
