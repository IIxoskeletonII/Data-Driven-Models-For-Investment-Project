"""The ddmi-vault server and the lab graph (decisions S33-5, S33-6, S33-9, S33-14 and S33-15).

Written from the decisions and the public interface only. The market is the synthetic planted market of
src/agents/planted.py (1999 to the In-Sample end), built once per module in a temporary folder; the base rung is M1, the
cheapest. Every LLM is a fake client or a replay: no network, no key, no spend.
"""

import csv
import json
import math
import re
from types import SimpleNamespace

import numpy as np
import pytest

from src.agents import planted, prompts
from src.agents.graph import Lab, risk_verdict
from src.agents.llm import LLM, LLMCache
from src.agents.vault_server import IN_SAMPLE_END, SERVER_NAME, VaultServer, anonymise, build_mcp, call_tool, load_script
from src.config import load_config
from src.contracts import universe
from src.vault import OOSAccessError, append_trial

SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
CODES = {f"A{i}" for i in range(1, 10)}
OOS_DATES = ("2019-12-30", "2020-01-03", "2021-06-30")
FORBIDDEN = re.compile(r"planted|injected|noise", re.IGNORECASE)

LOG_CLOSE = {"op": "log", "x": {"input": "close"}}
LOG_RETURN = {"op": "diff", "n": 1, "x": LOG_CLOSE}
# the one-week log return: the same quantity as REV1, so it fails the redundancy check when it reaches it
WEEKLY_CHANGE = {"name": "weekly change", "expr": {"op": "cs_z", "x": LOG_RETURN}}
# ln close(t - 1w) - ln close(t - 26w): MOM26_1 on the weekly grid, |corr| about 1 with it (S33-6 (4))
MOMENTUM = {"name": "half-year change skipping a week", "expr": {"op": "cs_z", "x": {
    "op": "diff", "n": 25, "x": {"op": "lag", "n": 1, "x": LOG_CLOSE}}}}
# needs 104 + 104 + 103 weeks of history: missing in 2003-2004 on a market starting in 1999 (S33-6 (3))
LONG_LOOKBACK = {"name": "lagged two-year change of the two-year mean", "expr": {"op": "cs_z", "x": {
    "op": "lag", "n": 104, "x": {"op": "diff", "n": 104, "x": {"op": "rolling", "stat": "mean", "n": 104,
                                                                "x": {"input": "close"}}}}}}
# a short-to-long volatility ratio: passes leakage, warm-up and redundancy, so it reaches the walk-forward
VOL_RATIO = {"name": "vol ratio 4 over 26", "expr": {"op": "cs_z", "x": {
    "op": "ratio", "a": {"op": "rolling", "stat": "std", "n": 4, "x": LOG_RETURN},
    "b": {"op": "rolling", "stat": "std", "n": 26, "x": LOG_RETURN}}}}
CHANGE_13 = {"name": "quarter change rank", "expr": {"op": "cs_rank", "x": {"op": "diff", "n": 13, "x": LOG_CLOSE}}}
CLOSE_VS_MEAN = {"name": "close over its two-year mean", "expr": {"op": "cs_z", "x": {
    "op": "ratio", "a": {"input": "close"}, "b": {"op": "rolling", "stat": "mean", "n": 104, "x": {"input": "close"}}}}}

WF_COST = 0.00123
WF_CANDIDATE = 3
HUMAN_PARAMS = json.dumps({"rung": "M0", "feature": "MOM26_1"}, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------- fixtures and helpers


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """The planted market, its sealed vault and a VaultServer on M1 with its own trial log and server log."""
    base = tmp_path_factory.mktemp("vault_server")
    lab = load_script("04_agent_lab.py")
    cfg = planted.planted_cfg()
    vault, paths = lab.planted_vault(cfg, base / "data")
    w05 = load_script("05_train_walkforward.py")
    run = base / "run"
    run.mkdir()
    trial_path, server_log = run / "trial_log.csv", run / "vault_server_log.jsonl"
    # one human row with params_json, so get_trial_history has a human row to strip (S33-5)
    append_trial({"author": "Test Human", "kind": "human", "rung": "M0", "spec_hash": "0" * 64, "params_json": HUMAN_PARAMS,
                  "is_sharpe": 0.1, "is_mdd": -0.2, "notes": "seeded human row"}, trial_path)
    core = VaultServer(cfg, vault, "M1", w05.model_spec("M1", cfg), trial_path=trial_path, server_log=server_log)
    return SimpleNamespace(cfg=cfg, core=core, server=build_mcp(core), base=base, trial_path=trial_path,
                           server_log=server_log, paths=paths)


def trial_rows(env) -> list[dict]:
    if not env.trial_path.exists():
        return []
    with open(env.trial_path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def log_lines(env) -> list[dict]:
    if not env.server_log.exists():
        return []
    return [json.loads(line) for line in env.server_log.read_text(encoding="utf-8").splitlines() if line.strip()]


def notes_of(row: dict) -> dict:
    return json.loads(row["notes"])


def propose(env, spec, **extra) -> tuple[dict, list[dict]]:
    """run_walkforward through the MCP server; returns the result and the trial rows it added."""
    before = trial_rows(env)
    result = call_tool(env.server, "run_walkforward", {"spec": spec, **extra})
    return result, trial_rows(env)[len(before):]


@pytest.fixture(scope="module")
def walkforward(env):
    """One valid spec run through the whole Validator (one walk-forward of the candidate, plus the base rung's)."""
    base = env.core.base()
    result, added = propose(env, VOL_RATIO, candidate=WF_CANDIDATE, cost_usd=WF_COST)
    return SimpleNamespace(base=base, result=result, added=added)


def _numbers_only(values) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def _no_series(value, path="root") -> None:
    if isinstance(value, list):
        assert not (len(value) > 20 and _numbers_only(value)), f"{path}: a list of {len(value)} numbers (a series)"
        for i, item in enumerate(value):
            _no_series(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        assert not (len(value) > 20 and _numbers_only(value.values())), f"{path}: {len(value)} numeric entries (a series)"
        for key, item in value.items():
            _no_series(item, f"{path}.{key}")


# ---------------------------------------------------------------- S33-5: constants and anonymisation


def test_constants():
    assert IN_SAMPLE_END == "2019-12-27"
    assert SERVER_NAME == "ddmi-vault"


def test_anonymise_is_a_deterministic_bijection_onto_a1_to_a9():
    cfg = load_config()
    mapping = anonymise(cfg)
    assert set(mapping) == set(universe(cfg).sectors) == set(SECTORS)
    assert set(mapping.values()) == CODES and len(set(mapping.values())) == 9
    assert anonymise(load_config()) == mapping


def test_anonymise_follows_the_seeded_permutation():
    cfg = load_config()
    sectors = list(universe(cfg).sectors)
    permutation = list(np.random.default_rng(cfg["seed"]).permutation(9))
    expected = {sector: f"A{permutation.index(i) + 1}" for i, sector in enumerate(sectors)}
    assert anonymise(cfg) == expected


# ---------------------------------------------------------------- S33-5: get_features


@pytest.mark.parametrize("as_of", OOS_DATES)
def test_get_features_after_the_in_sample_end_raises(env, as_of):
    with pytest.raises(OOSAccessError):
        env.core.get_features(as_of)
    assert log_lines(env)[-1]["result"] == "refused"


@pytest.mark.parametrize("as_of", OOS_DATES)
def test_get_features_tool_after_the_in_sample_end_raises(env, as_of):
    # the error may surface wrapped by the MCP layer, whatever its message; it must surface as an exception
    with pytest.raises(Exception, match=r"(?s).*"):
        call_tool(env.server, "get_features", {"as_of": as_of})
    assert log_lines(env)[-1]["result"] == "refused"


def test_get_features_is_anonymised_and_holds_no_series(env):
    out = env.core.get_features(IN_SAMPLE_END)
    assert isinstance(out, dict) and out
    text = json.dumps(out)
    for ticker in SECTORS + ("IVV",):
        assert ticker not in text, f"real ticker {ticker} leaked"
    for code in CODES:
        assert re.search(rf"\b{code}\b", text), f"code {code} missing"
    _no_series(out)


def test_every_tool_call_writes_one_server_log_line(env):
    calls = [
        lambda: env.core.get_features(IN_SAMPLE_END),
        lambda: call_tool(env.server, "get_features", {"as_of": IN_SAMPLE_END}),
        lambda: call_tool(env.server, "get_trial_history", {}),
        lambda: env.core.get_trial_history(),
        lambda: call_tool(env.server, "run_walkforward", {"spec": {"name": "log line probe"}}),
    ]
    for call in calls:
        before = len(log_lines(env))
        call()
        lines = log_lines(env)
        assert len(lines) == before + 1
        assert {"tool", "argument_hash", "result"} <= set(lines[-1]) and lines[-1]["result"] in ("ok", "refused")
    before = len(log_lines(env))
    with pytest.raises(OOSAccessError):
        env.core.get_features("2020-03-31")
    assert len(log_lines(env)) == before + 1


# ---------------------------------------------------------------- S33-9, S33-15 (1): malformed proposals


MALFORMED = {
    "none": None,
    "string": "cs_z(close)",
    "list": [1, 2],
    "unparsed": {"unparsed": "the spec is cs_z of the close"},
    "extra_key": {"name": "extra", "expr": {"op": "cs_z", "x": LOG_RETURN}, "rationale": "an extra key"},
}


@pytest.mark.parametrize("label", list(MALFORMED))
def test_malformed_proposal_is_one_invalid_spec_row_and_never_raises(env, label):
    proposal = MALFORMED[label]
    result, added = propose(env, proposal)
    assert result["stage"] == "invalid_spec"
    assert result["passed"] is False
    assert len(added) == 1
    row = added[0]
    assert row["kind"] == "agent" and row["author"] == "agent lab" and row["rung"] == "M1"
    assert row["spec_hash"] and notes_of(row)["stage"] == "invalid_spec"
    again, added_again = propose(env, proposal)
    assert again["stage"] == "invalid_spec" and again["passed"] is False
    assert added_again == []


# ---------------------------------------------------------------- S33-6: Validator stages before the walk-forward


@pytest.mark.parametrize(("spec", "stage"), [(LONG_LOOKBACK, "warm_up"), (MOMENTUM, "redundancy")])
def test_validator_stops_at_the_first_failed_check(env, spec, stage):
    result, added = propose(env, spec, candidate=1, cost_usd=0.0)
    assert result["stage"] == stage
    assert result["passed"] is False
    assert "risk_checks" not in result or not result["risk_checks"]
    assert len(added) == 1
    assert added[0]["kind"] == "agent" and notes_of(added[0])["stage"] == stage
    assert added[0]["is_sharpe"] == ""
    _, added_again = propose(env, spec, candidate=1, cost_usd=0.0)
    assert added_again == []


def test_redundancy_failure_reports_the_correlation(env):
    result, _ = propose(env, MOMENTUM)
    text = json.dumps(result["checks"])
    assert "MOM26_1" in text


# ---------------------------------------------------------------- S33-6, S33-9: a walk-forward


def test_valid_spec_reaches_the_walk_forward(walkforward):
    result = walkforward.result
    assert result["stage"] == "walk_forward"
    assert {"stage", "checks", "metrics", "passed", "reason", "spec_hash", "risk_checks"} <= set(result)
    metrics = result["metrics"]
    assert {"uplift", "p_uplift_positive", "net_sharpe", "base_net_sharpe", "adverse_uplift", "passed_gate"} <= set(metrics)
    for key in ("uplift", "p_uplift_positive", "net_sharpe", "base_net_sharpe", "adverse_uplift"):
        assert isinstance(metrics[key], (int, float)) and math.isfinite(metrics[key]), key
    assert 0.0 <= metrics["p_uplift_positive"] <= 1.0
    assert metrics["uplift"] == pytest.approx(metrics["net_sharpe"] - metrics["base_net_sharpe"], abs=1e-3)
    assert metrics["base_net_sharpe"] == pytest.approx(walkforward.base["net_sharpe"], abs=1e-3)
    assert isinstance(metrics["passed_gate"], bool) and result["passed"] is metrics["passed_gate"]
    assert {"turnover", "residual_beta", "cost_sensitivity", "passed"} <= set(result["risk_checks"])
    assert isinstance(result["risk_checks"]["passed"], bool)


def test_walk_forward_trial_row(walkforward):
    assert len(walkforward.added) == 1
    row = walkforward.added[0]
    assert row["kind"] == "agent" and row["author"] == "agent lab" and row["rung"] == "M1"
    assert row["spec_hash"] == walkforward.result["spec_hash"]
    sharpe = float(row["is_sharpe"])
    assert math.isfinite(sharpe) and sharpe == pytest.approx(walkforward.result["metrics"]["net_sharpe"], abs=1e-3)
    assert math.isfinite(float(row["is_mdd"]))
    notes = notes_of(row)
    assert notes["stage"] == "walk_forward"
    assert notes["candidate"] == WF_CANDIDATE
    assert notes["cost_usd"] == pytest.approx(WF_COST)
    params = json.loads(row["params_json"])
    assert VOL_RATIO["name"] in json.dumps(params)


# ---------------------------------------------------------------- S33-15 (1): an error after parsing is a refusal


def _boom(*args, **kwargs):
    raise RuntimeError("boom from the test")


@pytest.mark.parametrize(("target", "spec"), [("leakage_check", CHANGE_13), ("vault.run_walkforward", CLOSE_VS_MEAN)])
def test_error_after_parsing_is_a_refused_row_not_a_raise(env, walkforward, monkeypatch, target, spec):
    owner = env.core.vault if target.startswith("vault.") else env.core
    monkeypatch.setattr(owner, target.split(".")[-1], _boom)
    result, added = propose(env, spec, candidate=9, cost_usd=0.0)
    assert result["stage"] == "refused"
    assert result["passed"] is False
    assert len(added) == 1
    row = added[0]
    assert row["kind"] == "agent" and notes_of(row)["stage"] == "refused"
    assert "boom from the test" in row["notes"]
    assert log_lines(env)[-1]["result"] == "refused"


# ---------------------------------------------------------------- S33-5: trial history


def test_trial_history(env, walkforward):
    history = env.core.get_trial_history()
    via_tool = call_tool(env.server, "get_trial_history", {})
    assert set(via_tool) == {"trials"} and len(via_tool["trials"]) == len(history)
    assert len(history) == len(trial_rows(env))
    humans = [row for row in history if row.get("kind") == "human"]
    agents = [row for row in history if row.get("kind") == "agent"]
    assert humans and agents
    for row in humans:
        assert not row.get("params_json"), "a human row kept its params_json"
    assert all(row.get("notes") for row in agents)
    walked = [row for row in agents if VOL_RATIO["name"] in json.dumps(row)]
    assert walked, "the agent row lost its DSL feature"
    assert "rolling" in json.dumps(walked[0])
    assert "walk_forward" in json.dumps(walked[0]["notes"])


# ---------------------------------------------------------------- graph: fake LLM client


class FakeClient:
    """OpenAI-compatible stand-in: every answer is the same JSON object, valid for every role."""

    def __init__(self, answer: dict, prompt_tokens: int = 1000, completion_tokens: int = 200):
        self.answer, self.messages = json.dumps(answer), []
        self.prompt_tokens, self.completion_tokens = prompt_tokens, completion_tokens
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.messages.append(kwargs["messages"])
        usage = SimpleNamespace(model_dump=lambda: {"prompt_tokens": self.prompt_tokens,
                                                    "completion_tokens": self.completion_tokens})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))], usage=usage)


def answer(spec) -> dict:
    return {"mechanism": "volatility clustering", "rationale": "a short window reacts first",
            "feature_idea": "compare recent and longer volatility", "spec": spec,
            "veto": False, "reasons": "ok", "concern": None, "notes": "ok"}


def recording_llm(cache_dir, client) -> tuple[LLM, list]:
    """A live-mode LLM on a fake client; every (role, messages) it is asked is recorded, cached or not."""
    model = LLM(LLMCache(cache_dir, "t"), mode="live", client_factory=lambda: client)
    calls, original = [], model.call

    def call(*args, **kwargs):
        role = args[0] if args else kwargs.get("role")
        messages = args[1] if len(args) > 1 else kwargs.get("messages")
        calls.append((role, [dict(m) for m in messages]))
        return original(*args, **kwargs)

    model.call = call
    return model, calls


def read_candidates(run_dir) -> list[dict]:
    path = run_dir / "candidates.jsonl"
    assert path.exists(), "candidates.jsonl was not written"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def contents(messages) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


@pytest.mark.parametrize("spec", [None, "cs_z(close)"])
def test_coder_answer_that_is_not_an_object_is_an_invalid_spec(env, walkforward, tmp_path, spec):
    client = FakeClient(answer(spec))
    model, _ = recording_llm(tmp_path / "cache", client)
    run_dir = tmp_path / "run"
    before = len(trial_rows(env))
    Lab(env.core, model, run_dir, n_llm=1, injected=None, max_candidates=5, cfg=env.cfg).run()
    records = read_candidates(run_dir)
    assert len(records) == 1 and records[0]["stage"] == "invalid_spec"
    added = trial_rows(env)[before:]
    assert len(added) == 1 and notes_of(added[0])["stage"] == "invalid_spec"


def test_no_prompt_names_an_origin_and_hypothesis_sees_the_trial_history(env, walkforward, tmp_path):
    source = "injected:planted"
    client = FakeClient(answer(WEEKLY_CHANGE))
    model, calls = recording_llm(tmp_path / "cache", client)
    run_dir = tmp_path / "run"
    Lab(env.core, model, run_dir, n_llm=1, injected=[{"source": source, "spec": VOL_RATIO}], max_candidates=5,
        cfg=env.cfg).run()
    records = read_candidates(run_dir)
    assert len(records) == 2
    assert calls and client.messages
    for _, messages in calls:
        text = contents(messages)
        assert not FORBIDDEN.search(text) and source not in text
    for messages in client.messages:
        text = contents(messages)
        assert not FORBIDDEN.search(text) and source not in text
    hypothesis = [messages for role, messages in calls if "hypo" in str(role).lower()]
    assert hypothesis and all("Trial history" in contents(messages) for messages in hypothesis)

    injected = [r for r in records if r.get("source") == source]
    assert len(injected) == 1
    record = injected[0]
    assert record["hypothesis"] == {"feature_idea": VOL_RATIO["name"]}
    assert not FORBIDDEN.search(json.dumps(record["hypothesis"]))
    if record.get("passed_validator"):
        assert any("skep" in str(role).lower() for role, _ in calls), "the validated spec did not reach the Skeptic"
    skeptic = prompts.skeptic_messages(record["hypothesis"], record["spec"], record["checks"], record["metrics"], 2)
    risk = prompts.risk_messages(record["spec"], record["risk_checks"], record["metrics"])
    for messages in (skeptic, risk):
        text = contents(messages)
        assert not FORBIDDEN.search(text) and source not in text


# ---------------------------------------------------------------- S33-15 (3): cached answers keep their recorded cost


def test_cached_answer_records_the_cost_of_its_live_call(tmp_path):
    messages = [{"role": "system", "content": "Answer in json."}, {"role": "user", "content": "Write the spec."}]
    first_client = FakeClient({"ok": True}, prompt_tokens=1000, completion_tokens=200)
    first = LLM(LLMCache(tmp_path, "t"), mode="live", client_factory=lambda: first_client)
    out1 = first.call("coder", messages)
    expected = 1000 * 0.30e-6 + 200 * 1.20e-6
    assert out1["cached"] is False and out1["cost_usd"] == pytest.approx(expected)

    second_client = FakeClient({"ok": False})
    second = LLM(LLMCache(tmp_path, "t2"), mode="live", client_factory=lambda: second_client)
    out2 = second.call("coder", messages)
    assert out2["cached"] is True
    assert out2["cost_usd"] == 0.0
    assert out2["recorded_cost_usd"] == pytest.approx(out1["cost_usd"])
    assert second_client.messages == []

    replay = LLM(LLMCache(tmp_path, "t3"), mode="replay")
    out3 = replay.call("coder", messages)
    assert out3["cached"] is True and out3["cost_usd"] == 0.0
    assert out3["recorded_cost_usd"] == pytest.approx(expected)


# ---------------------------------------------------------------- S33-14, S33-15 (2): invalid Risk vetoes


@pytest.mark.parametrize("notes", [
    "net_sharpe drops in the later folds",
    "sharpe_uplift_over_base_rung_adverse_costs is fragile across folds",
    "cost_sensitivity suggests the effect is unstable",
    "the NET_SHARPE path is erratic",
])
def test_instability_veto_citing_snake_case_figures_is_invalid(notes):
    out = risk_verdict({"veto": True, "concern": "instability", "notes": notes}, "{}")
    assert out["veto"] is False
    assert out.get("invalid_veto")


@pytest.mark.parametrize("notes", [
    "the weights are costly to rebalance and flip sign from fold to fold",
    "the signal borrowed its strength from two folds only",
])
def test_costly_and_borrowed_do_not_invalidate_a_veto(notes):
    out = risk_verdict({"veto": True, "concern": "instability", "notes": notes}, "{}")
    assert out["veto"] is True
    assert "invalid_veto" not in out
