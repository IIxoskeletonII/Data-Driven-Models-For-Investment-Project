"""The round-2 lab graph: one Coder repair per invalid specification (S43-4), the round-2 prompts in the graph (S43-2,
S43-5) and the round-2 flags of 04_agent_lab.py (S43-6).

Written from the decisions and the session's interface only. The LLM is a fake object with .call(role, messages)
returning the dicts Round2LLM returns: no network, no key, no spend. The vault server is the real VaultServer on M7 over
the in-memory synthetic vault of tests/test_agents_round2_vault.py (sessions 2011-2020, cut at the In-Sample end); every
proposal of these tests stops before the walk-forward (invalid spec or redundancy), so no M7 walk-forward is run. Each
test has its own trial log and run folder under a temporary directory.
"""

import csv
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents import dsl
from src.agents.graph import Lab
from src.agents.vault_server import VaultServer

ROOT = Path(__file__).resolve().parents[1]
VENDOR = re.compile(r"anthropic|claude", re.IGNORECASE)
ORIGIN = re.compile(r"planted|injected|noise", re.IGNORECASE)
CACHE_1H = {"type": "ephemeral", "ttl": "1h"}
CALL_COST = 0.001

LOG_CLOSE = {"op": "log", "x": {"input": "close"}}
# MOM26_1 on the weekly grid: a valid spec that fails the redundancy check (|corr| about 1), before any walk-forward
MOMENTUM = {"name": "half-year change skipping a week", "expr": {"op": "cs_z", "x": {
    "op": "diff", "n": 25, "x": {"op": "lag", "n": 1, "x": LOG_CLOSE}}}}
# the one-week log return: the same quantity as REV1 (redundant)
WEEKLY_CHANGE = {"name": "weekly change", "expr": {"op": "cs_z", "x": {"op": "diff", "n": 1, "x": LOG_CLOSE}}}
BAD_OP = {"name": "first try", "expr": {"op": "cs_z", "x": {"op": "rank_all", "x": {"input": "close"}}}}
BAD_ROOT = {"name": "second try", "expr": {"op": "lag", "n": 1, "x": {"input": "close"}}}
BAD_KEY = {"name": "third try", "expr": {"op": "cs_z", "x": {"input": "close"}}, "rationale": "an extra key"}


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VAULT_TESTS = load_module("agents_round2_vault_helpers", "tests/test_agents_round2_vault.py")
SYN_CFG = VAULT_TESTS.SYN_CFG


def dsl_error(spec) -> str:
    with pytest.raises(dsl.DSLError) as raised:
        dsl.parse(spec)
    return str(raised.value)


class FakeModel:
    """Round2LLM stand-in: per-role answers (the Coder's from a queue); every call is recorded."""

    def __init__(self, coder_answers, hypothesis=None):
        self.coder_answers = list(coder_answers)
        self.hypothesis = hypothesis or {"mechanism": "momentum persists", "rationale": "not one of the six",
                                         "feature_idea": "a distinctive idea phrase"}
        self.calls = []

    def call(self, role, messages):
        self.calls.append((role, json.loads(json.dumps(list(messages)))))
        if str(role).startswith("coder"):  # the first Coder call and its repair (the role name of a repair is free)
            answer = self.coder_answers.pop(0)
            text = answer if isinstance(answer, str) else json.dumps(answer)
        elif role == "hypothesis":
            text = json.dumps(self.hypothesis)
        elif role == "skeptic":
            text = json.dumps({"veto": True, "reasons": "test veto"})
        else:
            text = json.dumps({"veto": True, "concern": "mechanism", "notes": "test veto"})
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        return {"content": text, "parsed": parsed if isinstance(parsed, dict) else None, "cached": False,
                "cost_usd": CALL_COST, "recorded_cost_usd": CALL_COST, "key": f"k{len(self.calls)}",
                "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 10}}

    def roles(self) -> list[str]:
        """The roles called, a repair counted as a Coder call."""
        return ["coder" if str(role).startswith("coder") else role for role, _ in self.calls]

    def messages_of(self, role) -> list[list[dict]]:
        return [messages for r, (_, messages) in zip(self.roles(), self.calls, strict=True) if r == role]


def text_of(messages) -> str:
    parts = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.extend(str(block.get("text", "")) for block in content)
    return "\n".join(parts)


@pytest.fixture
def server(synthetic_market, tmp_path):
    """A fresh M7 VaultServer with its own trial log and server log (the vault frames are built once per module)."""
    vault = VAULT_TESTS.make_vault(synthetic_market, tmp_path)
    w05 = load_module("train_walkforward_round2_lab_graph", "05_train_walkforward.py")
    trial_path, server_log = tmp_path / "trial_log.csv", tmp_path / "vault_server_log.jsonl"
    core = VaultServer(SYN_CFG, vault, "M7", w05.model_spec("M7", SYN_CFG), trial_path=trial_path,
                       server_log=server_log)
    return SimpleNamespace(core=core, trial_path=trial_path, server_log=server_log, run_dir=tmp_path / "run")


def trial_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def log_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidates(run_dir: Path) -> list[dict]:
    path = run_dir / "candidates.jsonl"
    assert path.exists(), "candidates.jsonl was not written"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_lab(server, model, *, coder_repairs=1, prompt_round=2, n_llm=1):
    lab = Lab(server.core, model, server.run_dir, n_llm=n_llm, injected=None, max_candidates=5, cfg=SYN_CFG,
              coder_repairs=coder_repairs, prompt_round=prompt_round)
    lab.run()
    return candidates(server.run_dir)


def assert_no_vendor(rows):
    for row in rows:
        assert not VENDOR.search(row.get("params_json", "") + row.get("notes", ""))


# ---------------------------------------------------------------- S43-4: the repair


def test_an_invalid_spec_is_repaired_once_and_the_repaired_spec_is_one_trial(server):
    error = dsl_error(BAD_OP)
    model = FakeModel([{"spec": BAD_OP}, {"spec": MOMENTUM}])
    records = run_lab(server, model)
    assert model.roles().count("coder") == 2
    second = text_of(model.messages_of("coder")[1])
    assert f"The Validator refused this spec: {error}" in second
    assert "rank_all" in second  # the previous answer is shown
    assert len(records) == 1
    record = records[0]
    assert record["stage"] == "redundancy"
    assert record["repaired"] is True and len(record["attempts"]) == 2
    first_attempt = json.dumps(record["attempts"][0])
    assert "invalid_spec" in first_attempt and "rank_all" in first_attempt
    assert "redundancy" in json.dumps(record["attempts"][1])
    rows = trial_rows(server.trial_path)
    assert len(rows) == 1
    row = rows[0]
    assert (row["kind"], row["author"], row["rung"]) == ("agent", "agent lab", "M7")
    assert json.loads(row["params_json"])["agent_features"][0]["expr"] == MOMENTUM["expr"]
    notes = json.loads(row["notes"])
    assert notes["stage"] == "redundancy" and notes["attempts"] == 2
    assert notes["cost_usd"] == pytest.approx(3 * CALL_COST, abs=1e-9)  # Hypothesis and both Coder calls
    refused = [line for line in log_lines(server.server_log) if line.get("result") == "refused"]
    assert any(error in line.get("reason", "") for line in refused)
    assert_no_vendor(rows)


def test_a_second_invalid_spec_is_final_and_one_trial(server):
    model = FakeModel([{"spec": BAD_OP}, {"spec": BAD_ROOT}, {"spec": MOMENTUM}])
    records = run_lab(server, model)
    assert model.roles().count("coder") == 2  # no third Coder call
    assert len(records) == 1 and records[0]["stage"] == "invalid_spec"
    assert len(records[0]["attempts"]) == 2
    rows = trial_rows(server.trial_path)
    assert len(rows) == 1
    assert json.loads(rows[0]["params_json"]) == {"invalid_dsl": BAD_ROOT, "rung": "M7"}
    notes = json.loads(rows[0]["notes"])
    assert notes["stage"] == "invalid_spec" and notes["attempts"] == 2
    assert_no_vendor(rows)


def test_a_coder_answer_that_is_not_json_is_repaired(server):
    model = FakeModel(["this is not a JSON object", {"spec": WEEKLY_CHANGE}])
    records = run_lab(server, model)
    assert model.roles().count("coder") == 2
    assert "The Validator refused this spec:" in text_of(model.messages_of("coder")[1])
    assert "this is not a JSON object" in text_of(model.messages_of("coder")[1])
    assert records[0]["repaired"] is True and records[0]["stage"] == "redundancy"
    assert len(trial_rows(server.trial_path)) == 1


def test_a_valid_first_spec_is_evaluated_at_once(server):
    model = FakeModel([{"spec": MOMENTUM}, {"spec": WEEKLY_CHANGE}])
    records = run_lab(server, model)
    assert model.roles().count("coder") == 1
    assert len(records) == 1 and records[0]["stage"] == "redundancy"
    assert not records[0].get("repaired")
    rows = trial_rows(server.trial_path)
    assert len(rows) == 1 and json.loads(rows[0]["notes"]).get("attempts", 1) == 1


def test_no_repair_when_coder_repairs_is_zero(server):
    model = FakeModel([{"spec": BAD_KEY}, {"spec": MOMENTUM}])
    records = run_lab(server, model, coder_repairs=0)
    assert model.roles().count("coder") == 1
    assert len(records) == 1 and records[0]["stage"] == "invalid_spec"
    assert not records[0].get("repaired")
    rows = trial_rows(server.trial_path)
    assert len(rows) == 1
    assert json.loads(rows[0]["params_json"]) == {"invalid_dsl": BAD_KEY, "rung": "M7"}


def test_the_lab_takes_its_repair_count_from_the_config_default():
    assert int(SYN_CFG["round2"]["agent_lab"]["coder_repairs"]) == 1
    assert SYN_CFG["round2"]["agent_lab"]["base_rung"] == "M7"
    assert int(SYN_CFG["round2"]["agent_lab"]["max_candidates"]) == 40


# ---------------------------------------------------------------- S43-2, S43-5: the round-2 prompts in the graph


def test_round2_hypothesis_prompt_is_cached_and_names_no_vendor_or_origin(server):
    model = FakeModel([{"spec": MOMENTUM}, {"spec": WEEKLY_CHANGE}, {"spec": MOMENTUM}])
    run_lab(server, model, n_llm=3, coder_repairs=0)
    hypotheses = model.messages_of("hypothesis")
    assert len(hypotheses) == 3
    for messages in hypotheses:
        system = [m for m in messages if m["role"] == "system"]
        users = [m for m in messages if m["role"] == "user"]
        assert len(system) == 1 and len(users) == 1
        content = users[0]["content"]
        assert isinstance(content, list) and content[0].get("cache_control") == CACHE_1H
        assert "cache_control" not in content[-1]
        assert sum("cache_control" in block for block in content) <= 2
    zero, first, second = (m[-1]["content"] for m in hypotheses)
    assert zero[0]["text"] == first[0]["text"] == second[0]["text"]  # the stable block does not change within the run
    assert (len(zero), len(first), len(second)) == (2, 3, 4)  # one more candidate block per earlier candidate
    assert first[1]["text"] == second[1]["text"]  # the cached prefix grows, it is never rewritten
    assert first[1]["text"].startswith("Candidate 1 of this run: ")
    assert second[2]["text"].startswith("Candidate 2 of this run: ")
    for _, messages in model.calls:
        text = text_of(messages)
        assert not VENDOR.search(text)
        assert not ORIGIN.search(text)


def test_round1_prompts_stay_in_round1(server):
    model = FakeModel([{"spec": MOMENTUM}])
    run_lab(server, model, coder_repairs=0, prompt_round=1)
    hypothesis = model.messages_of("hypothesis")[0]
    assert all(isinstance(m["content"], str) for m in hypothesis)
    assert "Trial history" in text_of(hypothesis)


# ---------------------------------------------------------------- S43-6: 04_agent_lab.py --round 2


@pytest.fixture
def lab_script(monkeypatch, tmp_path):
    """04_agent_lab.py with every guard against touching real data or the committed folders: real_server, Vault and
    shutil raise, the round-2 run folder constants point into tmp_path, and no key is set."""
    lab = load_module("agent_lab_script_round2", "04_agent_lab.py")

    def touched(*args, **kwargs):
        raise AssertionError("the In-Sample run touched real data or files before the planted PASS check")

    for name in ("real_server", "Vault"):
        if hasattr(lab, name):
            monkeypatch.setattr(lab, name, touched)
    monkeypatch.setattr(lab, "shutil", SimpleNamespace(copy=touched, copy2=touched, copyfile=touched, rmtree=touched))
    for name, value in list(vars(lab).items()):
        if isinstance(value, Path) and "run2" in value.parts:
            monkeypatch.setattr(lab, name, tmp_path / "guarded" / name)
    monkeypatch.delenv("DDMI_ANTHROPIC_API_KEY", raising=False)
    return lab


@pytest.mark.parametrize("summary", [None, {"pass": False}, {"pass": "true"}, {"planted_survived": True}])
def test_round2_insample_refuses_without_a_planted_pass(lab_script, monkeypatch, tmp_path, summary):
    planted_dir = tmp_path / "planted_round2"
    planted_dir.mkdir()
    if summary is not None:
        (planted_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    monkeypatch.setattr(lab_script, "PLANTED2_DIR", planted_dir)
    with pytest.raises((SystemExit, RuntimeError, ValueError)):
        lab_script.main(["--round", "2", "--insample"])
    assert not (tmp_path / "guarded").exists()


@pytest.mark.parametrize("argv", [["--probe"], ["--probe", "--replay", "--out", "OUT"]])
def test_round2_probe_refuses_without_a_planted_pass_live_or_replay(lab_script, monkeypatch, tmp_path, argv):
    """The probe reads the real In-Sample features, so even its replay needs the planted PASS (Amendment 9 C2; audit
    finding M2 of session 4.3)."""
    planted_dir = tmp_path / "planted_round2"
    planted_dir.mkdir()
    (planted_dir / "summary.json").write_text(json.dumps({"pass": False}), encoding="utf-8")
    monkeypatch.setattr(lab_script, "PLANTED2_DIR", planted_dir)
    argv = [str(tmp_path / "replay_out") if a == "OUT" else a for a in argv]
    with pytest.raises((SystemExit, RuntimeError, ValueError)):
        lab_script.main(["--round", "2", *argv])
    assert not (tmp_path / "guarded").exists() and not (tmp_path / "replay_out" / "probe.json").exists()


def test_round2_replay_needs_out(lab_script):
    with pytest.raises(SystemExit):
        lab_script.main(["--round", "2", "--planted", "--replay"])


def test_the_script_and_the_lab_modules_name_no_provider():
    """S43-6: every provider detail stays in src/agents/llm.py (and config.yaml)."""
    files = [ROOT / "04_agent_lab.py"] + [p for p in sorted((ROOT / "src" / "agents").glob("*.py")) if p.name != "llm.py"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not VENDOR.search(text), path.name
        assert "api.anthropic.com" not in text.lower(), path.name


def test_the_committed_trial_log_names_no_vendor():
    assert not VENDOR.search((ROOT / "docs" / "trial_log.csv").read_text(encoding="utf-8"))
