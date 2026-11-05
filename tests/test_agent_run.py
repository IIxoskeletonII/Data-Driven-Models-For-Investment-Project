"""The real In-Sample run of the agent lab and the recognition probe (decisions S33-16 and S33-17; S33-5, S33-9).

Written from the decisions and the public interface only. The vault server runs on the synthetic planted market of
src/agents/planted.py, built once per module in a temporary folder. Every path of 04_agent_lab.py (run folder, trial
log, cache folder, repository root) is redirected into tmp_path: nothing is written to agent_lab/ or docs/trial_log.csv,
no LLM is called and no licensed data is read.
"""

import csv
import json
import re
import shutil
from types import SimpleNamespace

import pytest

from src.agents import planted
from src.agents.prompts import probe_messages
from src.agents.vault_server import IN_SAMPLE_END, VaultServer, load_script
from src.config import load_config
from src.vault import TRIAL_COLUMNS, append_trial

SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
SECTOR_NAMES = ("Materials", "Energy", "Financials", "Industrials", "Technology", "Consumer Staples", "Utilities",
                "Health Care", "Consumer Discretionary")
CODES = tuple(f"A{i}" for i in range(1, 10))


# ---------------------------------------------------------------- helpers


def human_row(note: str, spec_hash: str, author: str = "Test Human") -> dict:
    params = json.dumps({"rung": "M0", "feature": "MOM26_1", "note": note}, sort_keys=True, separators=(",", ":"))
    return {"author": author, "kind": "human", "rung": "M0", "spec_hash": spec_hash, "params_json": params,
            "is_sharpe": 0.1, "is_mdd": -0.2, "notes": note}


def read_rows(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def jsonl_lines(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- the planted market and its vault (module scope)


@pytest.fixture(scope="module")
def market(tmp_path_factory):
    """The planted market, its sealed vault and M1's trial spec (the cheapest rung)."""
    base = tmp_path_factory.mktemp("agent_run")
    lab = load_script("04_agent_lab.py")
    cfg = planted.planted_cfg()
    vault, _ = lab.planted_vault(cfg, base / "data")
    spec = load_script("05_train_walkforward.py").model_spec("M1", cfg)
    return SimpleNamespace(cfg=cfg, vault=vault, spec=spec)


def server(market, run_dir, trial_path, snapshot=None) -> VaultServer:
    run_dir.mkdir(parents=True, exist_ok=True)
    return VaultServer(market.cfg, market.vault, "M1", market.spec, trial_path=trial_path,
                       server_log=run_dir / "vault_server_log.jsonl", history_snapshot=snapshot)


SNAPSHOT_NOTES = ("snapshot row 1", "snapshot row 2", "snapshot row 3")


@pytest.fixture
def logs(tmp_path):
    """A trial log that starts with three rows, a snapshot of exactly those rows, then a teammate's row after it."""
    trial_path, snapshot = tmp_path / "trial_log.csv", tmp_path / "trial_log_snapshot.csv"
    for i, note in enumerate(SNAPSHOT_NOTES, start=1):
        append_trial(human_row(note, str(i) * 64), trial_path)
    shutil.copyfile(trial_path, snapshot)
    append_trial(human_row("foreign row 1", "a" * 64, author="Teammate"), trial_path)
    return SimpleNamespace(trial_path=trial_path, snapshot=snapshot)


# ---------------------------------------------------------------- S33-16: get_trial_history with a snapshot


def ids(rows) -> list[str]:
    return [str(row["trial_id"]) for row in rows]


def test_history_with_a_snapshot_is_the_snapshot_rows_only(market, tmp_path, logs):
    core = server(market, tmp_path / "run", logs.trial_path, logs.snapshot)
    history = core.get_trial_history()
    assert ids(history) == ids(read_rows(logs.snapshot)) == ["1", "2", "3"]
    assert all(row.get("kind") == "human" and not row.get("params_json") for row in history)


def test_history_adds_this_servers_own_proposal_never_a_foreign_row(market, tmp_path, logs):
    core = server(market, tmp_path / "run", logs.trial_path, logs.snapshot)
    before = len(read_rows(logs.trial_path))
    result = core.run_walkforward(None)
    assert result["stage"] == "invalid_spec"
    rows = read_rows(logs.trial_path)
    assert len(rows) == before + 1 and rows[-1]["kind"] == "agent"
    proposal_id = rows[-1]["trial_id"]
    append_trial(human_row("foreign row 2", "b" * 64, author="Teammate"), logs.trial_path)
    foreign = [row["trial_id"] for row in read_rows(logs.trial_path) if row["author"] == "Teammate"]
    assert len(foreign) == 2

    history = core.get_trial_history()
    assert ids(history) == ["1", "2", "3", proposal_id]
    assert history[3]["kind"] == "agent"
    assert json.loads(history[3]["notes"])["stage"] == "invalid_spec"
    assert not set(ids(history)) & set(foreign)
    assert not any(str(row.get("spec_hash", "")).startswith(("a", "b")) for row in history[:3])


def test_history_without_a_snapshot_is_every_trial_row(market, tmp_path, logs):
    core = server(market, tmp_path / "run", logs.trial_path)
    core.run_walkforward(None)
    append_trial(human_row("foreign row 2", "b" * 64, author="Teammate"), logs.trial_path)
    history = core.get_trial_history()
    rows = read_rows(logs.trial_path)
    assert len(rows) == 6
    assert ids(history) == ids(rows)
    assert [row["kind"] for row in history] == [row["kind"] for row in rows]


# ---------------------------------------------------------------- S33-16: the run's paths (04_agent_lab.py)


@pytest.fixture(scope="module")
def lab_module():
    return load_script("04_agent_lab.py")


@pytest.fixture
def lab(lab_module, tmp_path, monkeypatch):
    """04_agent_lab.py with its repository root, run folder, trial log and cache folder all inside tmp_path."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "agent_lab" / "cache").mkdir(parents=True)
    monkeypatch.setattr(lab_module, "ROOT", root)
    monkeypatch.setattr(lab_module, "RUN_DIR", root / "agent_lab" / "run")
    monkeypatch.setattr(lab_module, "TRIAL_LOG", root / "docs" / "trial_log.csv")
    monkeypatch.setattr(lab_module, "CACHE_DIR", root / "agent_lab" / "cache")
    for i, note in enumerate(SNAPSHOT_NOTES, start=1):
        append_trial(human_row(note, str(i) * 64), lab_module.TRIAL_LOG)
    return lab_module


def test_live_first_call_snapshots_the_trial_log(lab):
    paths = lab.insample_paths("live", lab.RUN_DIR)
    snapshot = lab.RUN_DIR / "trial_log_snapshot.csv"
    assert paths["resumed"] is False
    assert snapshot.read_bytes() == lab.TRIAL_LOG.read_bytes()
    assert paths["trial_path"] == lab.TRIAL_LOG
    assert paths["cache_dir"] == lab.RUN_DIR / "cache"


def test_live_resumption_keeps_the_snapshot(lab):
    lab.insample_paths("live", lab.RUN_DIR)
    snapshot = lab.RUN_DIR / "trial_log_snapshot.csv"
    first = snapshot.read_bytes()
    append_trial(human_row("written during the run", "c" * 64), lab.TRIAL_LOG)
    paths = lab.insample_paths("live", lab.RUN_DIR)
    assert paths["resumed"] is True
    assert snapshot.read_bytes() == first
    assert snapshot.read_bytes() != lab.TRIAL_LOG.read_bytes()


@pytest.mark.parametrize("change", ["edit", "remove"])
def test_live_resumption_refuses_a_trial_log_that_no_longer_starts_with_the_snapshot(lab, change):
    lab.insample_paths("live", lab.RUN_DIR)
    rows = read_rows(lab.TRIAL_LOG)
    if change == "edit":
        rows[0]["spec_hash"] = "e" * 64
    else:
        rows = rows[1:]
    write_rows(lab.TRIAL_LOG, rows)
    with pytest.raises(RuntimeError):
        lab.insample_paths("live", lab.RUN_DIR)


def test_live_refuses_a_finished_run(lab):
    lab.insample_paths("live", lab.RUN_DIR)
    (lab.RUN_DIR / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        lab.insample_paths("live", lab.RUN_DIR)


def test_live_run_dir_must_be_the_run_folder(lab, tmp_path):
    with pytest.raises(ValueError):
        lab.insample_paths("live", tmp_path / "elsewhere")


def test_every_invocation_appends_one_run_log_line(lab):
    run_log = lab.RUN_DIR / "run_log.jsonl"
    lab.insample_paths("live", lab.RUN_DIR)
    assert len(jsonl_lines(run_log)) == 1
    lab.insample_paths("live", lab.RUN_DIR)
    assert len(jsonl_lines(run_log)) == 2


def test_replay_refuses_a_folder_inside_agent_lab(lab):
    with pytest.raises(ValueError):
        lab.insample_paths("replay", lab.ROOT / "agent_lab" / "replay")


def test_replay_needs_the_committed_snapshot(lab, tmp_path):
    out = tmp_path / "replay"
    out.mkdir()
    with pytest.raises(FileNotFoundError):
        lab.insample_paths("replay", out)


def test_replay_copies_the_committed_snapshot_and_never_uses_the_real_trial_log(lab, tmp_path):
    lab.insample_paths("live", lab.RUN_DIR)
    committed = lab.RUN_DIR / "trial_log_snapshot.csv"
    append_trial(human_row("a later row of the real trial log", "d" * 64), lab.TRIAL_LOG)
    real_before = lab.TRIAL_LOG.read_bytes()
    out = tmp_path / "replay"
    out.mkdir()
    paths = lab.insample_paths("replay", out)
    assert paths["trial_path"] == out / "trial_log.csv"
    assert paths["trial_path"] != lab.TRIAL_LOG
    assert (out / "trial_log_snapshot.csv").read_bytes() == committed.read_bytes()
    assert (out / "trial_log.csv").read_bytes() == committed.read_bytes()
    assert paths["cache_dir"] == lab.RUN_DIR / "cache"
    assert lab.TRIAL_LOG.read_bytes() == real_before


# ---------------------------------------------------------------- S33-16: counts and budget


def record(candidate, stage, passed_validator=False, survived=False) -> dict:
    return {"candidate": candidate, "stage": stage, "passed_validator": passed_validator, "survived": survived}


def test_insample_counts():
    records = [
        record(1, "invalid_spec"),
        record(2, "refused"),
        record(3, "tool_error"),
        record(4, "walk_forward"),
        record(5, "redundancy"),
        record(6, "walk_forward", passed_validator=True, survived=True),
        record(7, "walk_forward", passed_validator=True, survived=False),
    ]
    counts = load_script("04_agent_lab.py").insample_counts(records)
    expected = {"proposed": 7, "invalid": 1, "refused": 2, "validated": 2, "vetoed": 1, "surviving": 1}
    assert {key: counts[key] for key in expected} == expected


def cache_entry(key: str, cost: float) -> dict:
    return {"key": key, "request": {"model": "m", "messages": [{"role": "user", "content": key}]},
            "response": "{}", "usage": {"prompt_tokens": 10, "completion_tokens": 2}, "cost_usd": cost}


def test_lab_budget_subtracts_the_cached_spend(lab):
    lines = {"run_a.jsonl": [cache_entry("k1", 0.01), cache_entry("k2", 0.02)], "run_b.jsonl": [cache_entry("k3", 0.005)]}
    for name, entries in lines.items():
        text = "".join(json.dumps(entry) + "\n" for entry in entries)
        (lab.CACHE_DIR / name).write_text(text, encoding="utf-8")
    cfg = load_config()
    cfg["agent_lab"] = {**cfg["agent_lab"], "budget_usd": 5.0}
    assert lab.lab_budget(cfg) == pytest.approx(5.0 - 0.035)


def test_lab_budget_with_an_empty_cache_is_the_budget(lab):
    cfg = load_config()
    assert lab.lab_budget(cfg) == pytest.approx(float(cfg["agent_lab"]["budget_usd"]))


# ---------------------------------------------------------------- review.md


SURVIVOR_SPEC = {"name": "vol ratio four over twentysix", "expr": {"op": "cs_z", "x": {
    "op": "ratio", "a": {"op": "rolling", "stat": "std", "n": 4, "x": {"op": "diff", "n": 1, "x": {"op": "log", "x": {
        "input": "close"}}}},
    "b": {"op": "rolling", "stat": "std", "n": 26, "x": {"op": "diff", "n": 1, "x": {"op": "log", "x": {
        "input": "close"}}}}}}}
SURVIVOR_METRICS = {"uplift": 0.43, "p_uplift_positive": 0.91, "rank_ic_mean": 0.06, "rank_ic_t": 2.71,
                    "mean_turnover": 0.37, "base_mean_turnover": 0.33, "mean_abs_residual_beta": 0.02,
                    "adverse_uplift": 0.29, "net_sharpe": -0.55, "base_net_sharpe": -0.98, "max_drawdown_change": 0.01}
REJECTED_SPEC = {"name": "quarter change rank", "expr": {"op": "cs_rank", "x": {"op": "diff", "n": 13, "x": {
    "op": "log", "x": {"input": "close"}}}}}
REJECTED_METRICS = {"uplift": -0.17, "p_uplift_positive": 0.23, "rank_ic_mean": -0.04, "rank_ic_t": -1.13,
                    "mean_turnover": 1.12, "base_mean_turnover": 0.33, "mean_abs_residual_beta": 0.05,
                    "adverse_uplift": -0.19, "net_sharpe": -1.15, "base_net_sharpe": -0.98, "max_drawdown_change": -0.07}
MECHANISM = "Volatility clustering makes a short window react before the long one"
SKEPTIC_NOTE = "Distinct from the six features and plausible"
RISK_NOTE = "No concentration or instability concern found"


def full_record(candidate, stage, spec, *, passed, survived, metrics=None, skeptic=None, risk=None) -> dict:
    out = {"candidate": candidate, "source": "llm", "stage": stage, "spec": spec, "spec_hash": f"{candidate}" * 64,
           "hypothesis": {"mechanism": f"mechanism of candidate {candidate}", "rationale": "a rationale",
                          "feature_idea": "an idea"},
           "checks": {}, "metrics": metrics or {}, "risk_checks": {}, "passed_validator": passed, "survived": survived,
           "validator_reason": "", "cost_usd": 0.001, "review_cost_usd": 0.0}
    if skeptic is not None:
        out["skeptic"] = skeptic
    if risk is not None:
        out["risk"] = risk
    return out


def survivor() -> dict:
    out = full_record(1, "walk_forward", SURVIVOR_SPEC, passed=True, survived=True, metrics=SURVIVOR_METRICS,
                      skeptic={"veto": False, "reasons": SKEPTIC_NOTE},
                      risk={"veto": False, "by": "llm", "notes": RISK_NOTE})
    out["hypothesis"] = {"mechanism": MECHANISM, "rationale": "short windows lead long ones", "feature_idea": "vol ratio"}
    out["risk_checks"] = {"passed": True, "failed": [],
                          "turnover": {"candidate": 0.37, "base": 0.33, "limit": 1.5, "passed": True},
                          "residual_beta": {"mean_abs": 0.02, "limit": 0.1, "passed": True},
                          "cost_sensitivity": {"adverse_uplift": 0.29, "limit": 0.0, "passed": True}}
    return out


def rejected() -> dict:
    return full_record(2, "walk_forward", REJECTED_SPEC, passed=False, survived=False, metrics=REJECTED_METRICS)


def invalid() -> dict:
    return full_record(3, "invalid_spec", {"unparsed": "cs_z of the close, not JSON"}, passed=False, survived=False)


def write_run(run_dir, records, *, surviving) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    counts = {"proposed": len(records), "invalid": sum(r["stage"] == "invalid_spec" for r in records), "refused": 0,
              "validated": sum(bool(r["passed_validator"]) for r in records), "vetoed": 0, "surviving": surviving}
    summary = {"base_rung": "M2", "base_net_sharpe": -0.9865, "counts": counts, "total_cache_spend_usd": 0.0123,
               "llm_calls_cached": 7, "stopped": None}
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def section(text: str, pattern: str) -> str:
    """The text under the first markdown heading matching `pattern`, up to the next heading of its level or higher."""
    lines = text.splitlines()

    def level(line: str) -> int:
        stripped = line.lstrip()
        return len(stripped) - len(stripped.lstrip("#"))

    for i, line in enumerate(lines):
        if level(line) and re.search(pattern, line, re.IGNORECASE):
            body = []
            for following in lines[i + 1:]:
                if level(following) and level(following) <= level(line):
                    break
                body.append(following)
            return "\n".join(body)
    raise AssertionError(f"no heading matching {pattern!r} in review.md:\n{text}")


def table_rows(body: str) -> list[str]:
    """Data rows of the first markdown table in `body` (header and separator dropped)."""
    rows = [line for line in body.splitlines() if line.strip().startswith("|")]
    return [row for row in rows[2:] if row.strip()]


def shows(text: str, *alternatives: str) -> bool:
    return any(alt in text for alt in alternatives)


def review_text(lab, run_dir) -> str:
    path = lab.write_review(run_dir)
    assert path == run_dir / "review.md"
    return path.read_text(encoding="utf-8")


def test_review_lists_the_survivor_for_the_human_gate(lab, tmp_path):
    run_dir = tmp_path / "out"
    write_run(run_dir, [survivor(), rejected(), invalid()], surviving=1)
    text = review_text(lab, run_dir)
    survivors = section(text, r"surviv")
    assert SURVIVOR_SPEC["name"] in survivors
    assert "rolling" in survivors and "ratio" in survivors, "the DSL spec is not shown"
    assert MECHANISM in survivors
    assert shows(survivors, "0.43"), "uplift"
    assert shows(survivors, "0.91", "91%", "91 %"), "P(uplift > 0)"
    assert shows(survivors, "0.06"), "rank IC"
    assert shows(survivors, "0.37"), "turnover"
    assert shows(survivors, "0.02"), "|residual beta|"
    assert SKEPTIC_NOTE in survivors
    assert RISK_NOTE in survivors
    assert REJECTED_SPEC["name"] not in survivors


def test_review_has_one_table_row_per_candidate(lab, tmp_path):
    run_dir = tmp_path / "out"
    records = [survivor(), rejected(), invalid()]
    write_run(run_dir, records, surviving=1)
    rows = table_rows(section(review_text(lab, run_dir), r"every candidate"))
    assert len(rows) == len(records)


def test_review_without_survivors_says_none(lab, tmp_path):
    run_dir = tmp_path / "out"
    write_run(run_dir, [rejected(), invalid()], surviving=0)
    text = review_text(lab, run_dir)
    assert "None." in section(text, r"surviv")
    assert len(table_rows(section(text, r"every candidate"))) == 2


def test_review_probe_section_before_and_after_the_probe(lab, tmp_path):
    run_dir = tmp_path / "out"
    write_run(run_dir, [survivor(), rejected(), invalid()], surviving=1)
    before = section(review_text(lab, run_dir), r"probe")
    assert re.search(r"not (yet )?(been )?run|n't (yet )?(been )?run|not yet", before, re.IGNORECASE), before

    results = [{"code": code, "answer": SECTORS[(i + 1) % 9], "hit": i < 2, "reason": f"reason {code}"}
               for i, code in enumerate(CODES)]
    probe = {"n": 9, "hits": 2, "hit_rate": 2 / 9, "chance": 1 / 9, "results": results}
    (run_dir / "probe.json").write_text(json.dumps(probe), encoding="utf-8")
    after = section(review_text(lab, run_dir), r"probe")
    assert shows(after, "2/9", "2 / 9", "2 of 9", "0.22", "22%", "22.2"), after
    assert not re.search(r"not (yet )?(been )?run|n't (yet )?(been )?run", after, re.IGNORECASE)


# ---------------------------------------------------------------- S33-17: probe_messages


def codes_level(value):
    """The dict of get_features whose keys are the nine codes."""
    if isinstance(value, dict):
        if set(CODES) <= set(value):
            return value
        for item in value.values():
            found = codes_level(item)
            if found is not None:
                return found
    return None


def numbers(value) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [n for item in value.values() for n in numbers(item)]
    if isinstance(value, list):
        return [n for item in value for n in numbers(item)]
    return []


@pytest.fixture(scope="module")
def code_summary(market, tmp_path_factory):
    run = tmp_path_factory.mktemp("probe_server")
    core = server(market, run, run / "trial_log.csv")
    per_code = codes_level(core.get_features(IN_SAMPLE_END))
    assert per_code is not None, "get_features has no level keyed by A1 ... A9"
    return per_code["A4"]


def contents(messages) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def test_probe_names_the_code_and_the_nine_sector_etfs(code_summary):
    text = contents(probe_messages("A4", code_summary))
    assert re.search(r"\bA4\b", text)
    for ticker in SECTORS:
        assert re.search(rf"\b{ticker}\b", text), ticker
    for name in SECTOR_NAMES:
        assert name in text, name


def test_probe_asks_for_json_with_a_ticker(code_summary):
    text = contents(probe_messages("A4", code_summary))
    assert re.search(r"json", text, re.IGNORECASE)
    assert '"ticker"' in text or "ticker" in text


def test_probe_is_deterministic(code_summary):
    assert probe_messages("A4", code_summary) == probe_messages("A4", json.loads(json.dumps(code_summary)))


def test_probe_includes_the_summary_numbers(code_summary):
    text = contents(probe_messages("A4", code_summary))
    values = numbers(code_summary)
    assert values, "the code's summary holds no number"
    missing = [v for v in values if json.dumps(v) not in text]
    assert not missing, f"numbers of the summary not in the prompt: {missing[:5]}"


# ---------------------------------------------------------------- S33-15 (3), S33-16: a replay needs --out


@pytest.mark.parametrize("argv", [["--insample", "--replay"], ["--probe", "--replay"]])
def test_replay_without_out_exits(lab, monkeypatch, argv):
    def must_not_run(*args, **kwargs):
        pytest.fail("a replay without --out reached the run")

    for name in ("run_insample", "run_probe", "run_planted", "real_server"):
        monkeypatch.setattr(lab, name, must_not_run)
    with pytest.raises(SystemExit):
        lab.main(argv)
