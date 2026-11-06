"""08_run_oos.py (decisions S34-1 to S34-7): --freeze, the lock checks, the single-entry OOS access log, the full-range
rebuild through 03's unlock path, the quarterly Out-of-Sample refits at the frozen grid values and the continuous book.

Everything runs on the shared synthetic market (sessions 2011-01-03 to 2020-12-31) laid out as a small project in a
temporary git repository: config.yaml (a copy of the real one with a warm-up ending in 2012, test years 2017-2019, a
26-week inner validation window and data.end 2020-12-18), the raw files, the daily prices, the In-Sample tables of 03,
the walk-forwards of 05 and the In-Sample backtests of 06. No path of the repository itself is written and no
FROZEN.lock is created in it.
"""

import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src import features
from src.config import data_settings, load_config, save_used
from src.data import write_csv
from src.models import ensemble_scores, walkforward_rung
from src.vault import OOSAccessError

ROOT = Path(__file__).resolve().parents[1]
IS_END = pd.Timestamp("2019-12-27")
DATA_END = "2020-12-18"
SPOTS = (("2017-01-06", "XLB"), ("2017-06-09", "XLK"), ("2018-02-09", "XLE"), ("2018-10-12", "XLF"),
         ("2019-12-13", "XLY"))
WALKFORWARDS = ("M0", "M0_star", "M1", "M2", "M3", "ENS")
HURDLE = {"sharpe_m0": -0.5, "mdd_m0": -0.30}  # M0's figures, shared by every evaluated row


def gate_row(name: str, passes: bool, p: float | None = None) -> dict:
    """An evaluated row of src.stats.selection_gate whose verdicts follow from its numbers (S42-1): passing every test
    (Sharpe −0.30 ≥ −0.5 + 0.15, the same drawdown, P = 0.95) or failing every test; `p` overrides P(uplift > 0) and
    the bootstrap verdict is then that of the round-1 threshold 0.80."""
    sharpe, mdd, prob = (-0.30, -0.30, 0.95) if passes else (-0.60, -0.40, 0.30)
    prob = prob if p is None else p
    flags = {"passes_sharpe": passes, "passes_mdd": passes, "passes_bootstrap": prob >= 0.80 if p is not None else passes}
    return {"name": name, "status": "evaluated", "sharpe": sharpe, "mdd": mdd, "p_uplift_positive": prob, **HURDLE,
            **flags, "passes": all(flags.values())}


ROUND2_ABSENT = [{"name": name, "status": "absent"} for name in ("M6", "M7", "M8", "M9")]  # round2.candidate_order
GATE = {"selected": "M2", "candidates": [gate_row("M1", False), gate_row("M2", True), gate_row("M3", False),
                                          {"name": "M5", "status": "absent"}, gate_row("ENS", False)] + ROUND2_ABSENT}


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load("run_oos_script", "08_run_oos.py")


def synthetic_cfg() -> dict:
    cfg = copy.deepcopy(load_config())
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2013]
    cfg["split"]["test_years"] = [2017, 2019]
    cfg["tuning"]["inner_validation_weeks"] = 26
    cfg["data"]["end"] = DATA_END
    return cfg


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def init_repo(root: Path) -> None:
    """git init with automatic housekeeping off (S38-3): a commit may otherwise start git's background auto-maintenance,
    which creates and deletes lock files under .git/ while copy_repo copies the folder. The settings live in .git/config,
    so every copy inherits them."""
    git(root, "init", "-q")
    git(root, "config", "gc.auto", "0")
    git(root, "config", "maintenance.auto", "false")


def _git_locks(folder: str, names: list[str]) -> set[str]:
    """copytree ignore: transient *.lock files inside .git/ (S38-3); FROZEN.lock in the working tree is copied."""
    inside_git = ".git" in Path(folder).parts
    return {name for name in names if inside_git and name.endswith(".lock")}


def copy_repo(source: Path, target: Path) -> Path:
    """Copy a test project (working tree, git-ignored data/ and outputs/, and .git/) without git's lock files."""
    shutil.copytree(source, target, ignore=_git_locks)
    return target


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "-q", "--no-verify", "-m", message)


def build_project(root: Path, market, walkforwards=WALKFORWARDS, gate_content=None) -> dict:
    """The synthetic project: raw files (full range, like the archived snapshot), daily prices, the In-Sample tables of
    03, the walk-forwards of 05, the In-Sample backtests of 06, the gate file; everything but data/ and outputs/
    committed."""
    cfg = synthetic_cfg()
    (root / "docs").mkdir(parents=True)
    with open(root / "config.yaml", "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    cfg = load_config(root / "config.yaml")
    (root / "docs" / "decisions.md").write_text("# Decision log\n", encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text("data/\noutputs/\n", encoding="utf-8", newline="\n")

    raw, fred_dir = root / "data" / "raw" / "yahoo", root / "data" / "raw" / "fred"
    raw.mkdir(parents=True)
    fred_dir.mkdir(parents=True)
    for ticker, frame in market.raw.items():
        frame.rename_axis("Date").to_csv(raw / f"{ticker}.csv")
    market.vix.rename("Close").to_frame().rename_axis("Date").to_csv(raw / "VIX.csv")
    for name in cfg["data"]["fred"]:
        market.fred[[name]].rename_axis("Date").to_csv(fred_dir / f"{name}.csv")
    processed = root / "data" / "processed"
    write_csv(market.daily_close.rename_axis("date"), processed / "daily_close.csv")
    write_csv(market.daily_open.rename_axis("date"), processed / "daily_open.csv")
    save_used(data_settings(cfg), processed / "config.yaml")

    s03 = load("oos_test_03", "03_build_features.py")
    close, opens = market.daily_close, market.daily_open
    close, opens = close[close.index <= IS_END], opens[opens.index <= IS_END]
    vix, fred = market.vix[market.vix.index <= IS_END], market.fred[market.fred.index <= IS_END]
    tables = s03.build_tables(close, vix, fred, cfg)
    tables["labels"] = s03.build_labels(opens, close, IS_END)
    tables["forward_returns"] = s03.build_forward_returns(opens, close, IS_END)
    s03.write_tables(tables, processed, IS_END, root / "FROZEN.lock")
    save_used(features.features_settings(cfg), processed / "features_config.yaml")

    s05 = load("oos_test_05", "05_train_walkforward.py")
    for name in walkforwards:
        s05.run(name, cfg, data_dir=processed, out_dir=root / "outputs" / "walkforward" / name,
                trial_path=root / "docs" / "trial_log.csv", log_path=root / "outputs" / "vault_access_log.jsonl",
                lock_path=root / "FROZEN.lock", spots=SPOTS)
    s06 = load("oos_test_06", "06_backtest.py")
    s06.ROOT = root  # this module instance only
    inputs = s06.in_sample_inputs(cfg)
    for name in walkforwards:
        s06.backtest_model(cfg, name, inputs)
    gate = root / "outputs" / "metrics" / "selection_gate.json"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(json.dumps(GATE if gate_content is None else gate_content), encoding="utf-8")

    init_repo(root)
    commit(root, "chore: synthetic project")
    return cfg


_PROJECT: dict = {}
_RAN: dict = {}


@pytest.fixture
def project(synthetic_market, tmp_path_factory) -> dict:
    """The synthetic project, built once per module, not frozen (read-only: tests copy it before changing anything)."""
    if not _PROJECT:
        root = tmp_path_factory.mktemp("oos_project") / "project"
        root.mkdir()
        _PROJECT.update(root=root, cfg=build_project(root, synthetic_market))
    return _PROJECT


def copy_project(project: dict, tmp_path: Path) -> Path:
    return copy_repo(project["root"], tmp_path / "project")


@pytest.fixture
def ran(script, project, tmp_path_factory) -> dict:
    """A copy of the project frozen, signed (lock and decisions committed) and run once (read-only, built once)."""
    if not _RAN:
        root = tmp_path_factory.mktemp("oos_ran") / "project"
        copy_repo(project["root"], root)
        lock = script.freeze(root)
        with open(root / "docs" / "decisions.md", "a", encoding="utf-8", newline="\n") as f:
            f.write("\nGate 3 signatures (synthetic test)\n")
        commit(root, "docs: sign the freeze")
        report = script.run_oos(root)
        _RAN.update(root=root, cfg=project["cfg"], lock=lock, report=report)
    return _RAN


def read_weekly(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col=[0, 1], parse_dates=[0, 1, "realised_on"] if "weekly" in path.name else [0, 1])


def closes(frame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


# ---------------------------------------------------------------- unit helpers


def test_oos_log_check_accepts_zero_or_one_entry_and_refuses_two(script):
    assert script.check_oos_log_text("[]") == 0
    assert script.check_oos_log_text('[{"utc": "2026-11-07T10:00:00+00:00"}]') == 1
    with pytest.raises(ValueError, match="2 entries"):
        script.check_oos_log_text('[{"utc": "a"}, {"utc": "b"}]')


@pytest.mark.parametrize("text", ["{}", "not json", '[{"time": "x"}]', '["x"]'])
def test_oos_log_check_refuses_a_malformed_log(script, text):
    with pytest.raises(ValueError):
        script.check_oos_log_text(text)


def test_copy_repo_skips_git_lock_files_and_keeps_frozen_lock(tmp_path):
    """S38-3: a *.lock inside .git/ (git's transient maintenance and index locks) is not copied; FROZEN.lock is."""
    source = tmp_path / "source"
    (source / ".git" / "objects").mkdir(parents=True)
    (source / ".git" / "objects" / "maintenance.lock").write_text("", encoding="utf-8")
    (source / ".git" / "index.lock").write_text("", encoding="utf-8")
    (source / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (source / "FROZEN.lock").write_text("{}", encoding="utf-8")
    (source / "outputs").mkdir()
    (source / "outputs" / "x.lock").write_text("kept", encoding="utf-8")
    target = copy_repo(source, tmp_path / "target")
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        ".git/config", "FROZEN.lock", "outputs/x.lock"]


def test_project_copies_keep_automatic_git_housekeeping_off(project, tmp_path):
    root = copy_project(project, tmp_path)
    assert git(root, "config", "--get", "gc.auto").strip() == "0"
    assert git(root, "config", "--get", "maintenance.auto").strip() == "false"


def test_text_sha256_reads_crlf_as_lf(script, tmp_path):
    (tmp_path / "a").write_bytes(b"x: 1\r\ny: 2\r\n")
    (tmp_path / "b").write_bytes(b"x: 1\ny: 2\n")
    assert script.text_sha256(tmp_path / "a") == script.text_sha256(tmp_path / "b")


def test_run_models_are_the_evaluated_candidates_then_m0_and_m0_star(script):
    cfg = load_config()
    assert script.run_models(GATE, cfg) == ["M1", "M2", "M3", "ENS", "M0", "M0_star"]
    only_m1 = {"selected": "M0_star", "candidates": [{"name": n, "status": "evaluated" if n == "M1" else "absent"}
                                                      for n in cfg["models"]["candidate_order"]]}
    assert script.run_models(only_m1, cfg) == ["M1", "M0", "M0_star"]
    ens = {"selected": "ENS", "candidates": [{"name": n, "status": "evaluated" if n == "ENS" else "absent"}
                                             for n in cfg["models"]["candidate_order"]]}
    assert script.run_models(ens, cfg) == ["M1", "M2", "M3", "ENS", "M0", "M0_star"]  # ENS needs its members


def test_read_gate_refuses_a_selected_model_that_was_not_evaluated(script, tmp_path):
    gate = tmp_path / "outputs" / "metrics" / "selection_gate.json"
    gate.parent.mkdir(parents=True)
    gate.write_text(json.dumps({**GATE, "selected": "M5"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="neither an evaluated candidate"):
        script.read_gate(tmp_path, load_config())
    gate.write_text(json.dumps({"selected": "M1", "candidates": GATE["candidates"][:2]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="differ from models.candidate_order"):
        script.read_gate(tmp_path, load_config())


def test_read_gate_needs_the_gate_file(script, tmp_path):
    with pytest.raises(SystemExit, match="selection_gate.json not found"):
        script.read_gate(tmp_path, load_config())


# ---------------------------------------------------------------- the gate of both rounds (Amendment 9 C3, S42-1)


def write_gate(root: Path, gate: dict) -> None:
    path = root / "outputs" / "metrics" / "selection_gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gate), encoding="utf-8")


def with_round2(rows: dict, selected: str) -> dict:
    """GATE with the given round-2 rows (name -> row) in place of the absent ones, and `selected`."""
    candidates = [rows.get(c["name"], c) for c in GATE["candidates"]]
    return {"selected": selected, "candidates": candidates}


def test_the_candidate_order_and_the_thresholds_come_from_both_config_sections(script):
    cfg = load_config()
    assert script.candidate_rounds(cfg) == (["M1", "M2", "M3", "M5", "ENS"], ["M6", "M7", "M8", "M9"])
    assert [c["name"] for c in GATE["candidates"]] == script.candidate_rounds(cfg)[0] + script.candidate_rounds(cfg)[1]
    assert [script.bootstrap_threshold(n, cfg) for n in ("M1", "ENS", "M6", "M9")] == [0.80, 0.80, 0.90, 0.90]
    with pytest.raises(ValueError, match="not a candidate"):
        script.bootstrap_threshold("M0_star", cfg)


def test_read_gate_accepts_both_rounds_with_round_2_absent(script, tmp_path):
    write_gate(tmp_path, GATE)
    assert script.read_gate(tmp_path, load_config()) == GATE
    assert script.check_gate(GATE, load_config()) == {"names": [c["name"] for c in GATE["candidates"]],
                                                      "complete": True, "selected": "M2", "round1_selected": "M2"}


def test_read_gate_refuses_a_gate_file_of_round_1_only(script, tmp_path):
    """The round-1 file of S37-9 is valid on its own (07 reads it), but the freeze needs the order of Amendment 9 C3."""
    round1 = {"selected": "M0_star", "candidates": [gate_row(n, False) if n != "M5" else {"name": n, "status": "absent"}
                                                    for n in ("M1", "M2", "M3", "M5", "ENS")]}
    assert script.check_gate(round1, load_config())["complete"] is False
    assert script.check_gate(round1, load_config())["round1_selected"] == "M0_star"
    write_gate(tmp_path, round1)
    with pytest.raises(SystemExit, match="lists only the round-1 candidates"):
        script.read_gate(tmp_path, load_config())


def test_a_round_2_candidate_needs_the_round_2_bootstrap_threshold(script, tmp_path):
    """P = 0.85 passes the round-1 threshold 0.80 but not the round-2 threshold 0.90 (Amendment 9 C3)."""
    cfg = load_config()
    honest = gate_row("M7", True) | {"p_uplift_positive": 0.85, "passes_bootstrap": False, "passes": False}
    assert script.check_gate(with_round2({"M7": honest}, "M2"), cfg)["selected"] == "M2"
    lenient = honest | {"passes_bootstrap": True, "passes": True}  # judged with 0.80
    with pytest.raises(SystemExit, match=r"M7: \['passes_bootstrap', 'passes'\].*P\(uplift > 0\) >= 0.9"):
        script.check_gate(with_round2({"M7": lenient}, "M2"), cfg)
    round1 = gate_row("M1", False, p=0.85)  # in round 1, the same P passes the bootstrap test
    assert round1["passes_bootstrap"] is True and round1["passes"] is False
    script.check_gate({"selected": "M2", "candidates": [round1] + GATE["candidates"][1:]}, cfg)


def test_selected_is_the_first_passing_candidate_of_both_rounds(script):
    cfg = load_config()
    no_round1 = [gate_row(c["name"], False) if c["status"] == "evaluated" else c for c in GATE["candidates"][:5]]
    gate = {"selected": "M7", "candidates": no_round1 + [ROUND2_ABSENT[0], gate_row("M7", True), gate_row("M8", True),
                                                         ROUND2_ABSENT[3]]}
    checked = script.check_gate(gate, cfg)
    assert (checked["selected"], checked["round1_selected"]) == ("M7", "M0_star")  # round 1's verdict is kept apart
    for wrong in ("M8", "M0_star"):
        with pytest.raises(SystemExit, match="first passing candidate"):
            script.check_gate(gate | {"selected": wrong}, cfg)
    with pytest.raises(SystemExit, match="first passing candidate .* is 'M2'"):
        script.check_gate(GATE | {"selected": "M0_star"}, cfg)


@pytest.mark.parametrize("edit, expected", [
    (lambda row: row.pop("p_uplift_positive"), "lacks \\['p_uplift_positive'\\]"),
    (lambda row: row.update(passes="yes"), "lacks \\['passes'\\]"),
    (lambda row: row.update(sharpe=True), "lacks \\['sharpe'\\]"),
    (lambda row: row.update(passes_mdd=False, passes=False), "do not follow from its numbers"),
    (lambda row: row.update(sharpe_m0=-0.6), "one hurdle"),
])
def test_check_gate_refuses_a_row_that_is_not_a_gate_row(script, edit, expected):
    gate = copy.deepcopy(GATE)
    edit(gate["candidates"][1])
    with pytest.raises(SystemExit, match=expected):
        script.check_gate(gate, load_config())


def test_run_models_refuse_an_evaluated_round_2_candidate_until_its_refit_exists(script):
    cfg = load_config()
    assert script.run_models(GATE, cfg) == ["M1", "M2", "M3", "ENS", "M0", "M0_star"]  # round 2 absent: unchanged
    with pytest.raises(SystemExit, match="round-2 candidates \\['M6'\\] were evaluated.*session 4.2b"):
        script.run_models(with_round2({"M6": gate_row("M6", False)}, "M2"), cfg)


def test_freeze_refuses_a_gate_file_of_round_1_only(script, project, tmp_path):
    root = copy_project(project, tmp_path)
    write_gate(root, {"selected": "M2", "candidates": GATE["candidates"][:5]})  # outputs/ is git-ignored: tree clean
    with pytest.raises(SystemExit, match="lists only the round-1 candidates"):
        script.freeze(root)
    assert not (root / "FROZEN.lock").exists()


# ---------------------------------------------------------------- --freeze


def test_freeze_records_hashes_selection_and_frozen_values(script, project, tmp_path):
    root = copy_project(project, tmp_path)
    lock = script.freeze(root)
    assert json.loads((root / "FROZEN.lock").read_text(encoding="utf-8")) == lock
    assert lock["code_commit"] == git(root, "rev-parse", "HEAD").strip()
    assert lock["config_sha256"] == script.text_sha256(root / "config.yaml")
    assert lock["trial_log_sha256"] == script.text_sha256(root / "docs" / "trial_log.csv")
    assert lock["trial_count"] == len(pd.read_csv(root / "docs" / "trial_log.csv"))
    assert lock["selected"] == "M2"
    assert lock["models"] == ["M1", "M2", "M3", "ENS", "M0", "M0_star"]
    assert lock["allowed_after_freeze"] == ["FROZEN.lock", "docs/decisions.md"]
    for rung in ("M1", "M2", "M3", "M0_star"):  # Amendment 6 C2: the value chosen at the last In-Sample refit
        selection = pd.read_csv(root / "outputs" / "walkforward" / rung / "selection.csv")
        last = selection.sort_values(["test_year", "refit"]).iloc[-1]
        frozen = lock["frozen_values"][rung]
        assert float(frozen["value"]) == float(last["chosen"]) and (frozen["test_year"], frozen["refit"]) == (2019, 4)
    assert isinstance(lock["frozen_values"]["M1"]["value"], (int, float)) and not isinstance(
        lock["frozen_values"]["M3"]["value"], float)  # M3 depth stays an int
    expected = {f"data/processed/{t}.csv" for t in script.TABLES} | {"data/processed/features_config.yaml",
                                                                      "outputs/metrics/selection_gate.json"}
    for name in lock["models"]:
        expected |= {f"outputs/walkforward/{name}/{f}" for f in ("scores.csv", "used.yaml", "summary.json")}
    for rung in ("M1", "M2", "M3", "M0_star"):
        expected.add(f"outputs/walkforward/{rung}/selection.csv")
    assert set(lock["artefacts"]) == expected
    assert lock["artefacts"]["outputs/walkforward/M3/scores.csv"] == script.file_sha256(
        root / "outputs" / "walkforward" / "M3" / "scores.csv")


def test_freeze_refuses_a_dirty_tree(script, project, tmp_path):
    root = copy_project(project, tmp_path)
    (root / "notes.txt").write_text("untracked", encoding="utf-8")
    with pytest.raises(SystemExit, match="not clean"):
        script.freeze(root)
    assert not (root / "FROZEN.lock").exists()


def test_freeze_refuses_an_existing_lock_and_stale_scores(script, project, tmp_path):
    root = copy_project(project, tmp_path)
    script.freeze(root)
    commit(root, "docs: lock")
    with pytest.raises(SystemExit, match="already exists"):
        script.freeze(root)
    other = copy_project(project, tmp_path / "other")
    summary = other / "outputs" / "walkforward" / "M1" / "summary.json"
    content = json.loads(summary.read_text(encoding="utf-8"))
    summary.write_text(json.dumps({**content, "spec_hash": "0" * 64}), encoding="utf-8")
    with pytest.raises(SystemExit, match="stale"):
        script.freeze(other)
    assert not (other / "FROZEN.lock").exists()


# ---------------------------------------------------------------- the checks of the run


def frozen_copy(script, project, tmp_path) -> Path:
    root = copy_project(project, tmp_path)
    script.freeze(root)
    commit(root, "docs: lock")
    return root


def nothing_accessed(root: Path) -> bool:
    return not (root / "outputs" / "oos_access_log.json").exists() and not (root / "outputs" / "oos").exists() \
        and not (root / "data" / "processed" / "oos").exists()


def test_run_refuses_without_the_lock(script, project, tmp_path):
    root = copy_project(project, tmp_path)
    with pytest.raises(SystemExit, match="does not exist"):
        script.run_oos(root)
    assert nothing_accessed(root)


def test_run_refuses_a_changed_artefact(script, project, tmp_path):
    root = frozen_copy(script, project, tmp_path)
    path = root / "outputs" / "walkforward" / "M2" / "scores.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="hashes differ.*M2/scores.csv"):
        script.run_oos(root)
    assert nothing_accessed(root)


def test_run_refuses_a_code_change_after_the_freeze(script, project, tmp_path):
    root = frozen_copy(script, project, tmp_path)
    (root / "extra.py").write_text("x = 1\n", encoding="utf-8")
    commit(root, "feat: a change after the freeze")
    with pytest.raises(SystemExit, match="files changed since the freeze.*extra.py"):
        script.run_oos(root)
    assert nothing_accessed(root)


def test_run_refuses_a_dirty_tree(script, project, tmp_path):
    root = frozen_copy(script, project, tmp_path)
    with open(root / "docs" / "trial_log.csv", "a", encoding="utf-8", newline="\n") as f:
        f.write("99,x,x,human,M1,abc,{},,,extra\n")
    with pytest.raises(SystemExit, match="not clean"):
        script.run_oos(root)
    assert nothing_accessed(root)


def test_run_refuses_when_the_access_log_has_an_entry(script, project, tmp_path):
    root = frozen_copy(script, project, tmp_path)
    log = root / "outputs" / "oos_access_log.json"
    log.write_text('[{"utc": "2026-11-07T10:00:00+00:00"}]', encoding="utf-8")
    with pytest.raises(SystemExit, match="already has an entry"):
        script.run_oos(root)
    assert not (root / "outputs" / "oos").exists()


# ---------------------------------------------------------------- the run


def test_the_run_writes_exactly_one_access_entry_and_refuses_a_second_run(script, ran):
    root = ran["root"]
    entries = json.loads((root / "outputs" / "oos_access_log.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    entry = entries[0]
    assert entry["lock_sha256"] == script.file_sha256(root / "FROZEN.lock")
    assert entry["code_commit"] == ran["lock"]["code_commit"] and entry["selected"] == "M2"
    with pytest.raises(SystemExit, match="exactly once"):
        script.run_oos(root)
    assert len(json.loads((root / "outputs" / "oos_access_log.json").read_text(encoding="utf-8"))) == 1


def test_the_vault_is_unlocked_once_and_the_frozen_tables_are_untouched(script, ran):
    root = ran["root"]
    lines = [json.loads(line) for line in (root / "outputs" / "vault_access_log.jsonl").read_text().splitlines()]
    unlocks = [line for line in lines if line["method"] == "unlock"]
    assert [u["result"] for u in unlocks] == ["ok"]
    late = [line for line in lines if line.get("as_of", "") > "2019-12-27"]
    assert late and all(line["result"] == "ok" for line in late)
    for path, digest in ran["lock"]["artefacts"].items():  # the run wrote its tables to data/processed/oos/
        assert script.file_sha256(root / path) == digest


def test_the_full_range_tables_reach_the_data_end_with_periods_by_realisation(script, ran):
    oos_dir = ran["root"] / "data" / "processed" / "oos"
    table = pd.read_csv(oos_dir / "forward_returns.csv", index_col=[0, 1], parse_dates=[0, 1, "realised_on"])
    realised = table["realised_on"].dropna()
    assert realised.max() <= pd.Timestamp(DATA_END) and realised.max() > IS_END
    period = table.loc[realised.index, "period"]
    assert (period == np.where(realised <= IS_END, "IS", "OOS")).all()
    assert realised[period == "OOS"].min() == pd.Timestamp("2019-12-30")
    labels = pd.read_csv(oos_dir / "labels.csv", parse_dates=["date_close", "label_end"])
    assert labels["label_end"].max() <= pd.Timestamp(DATA_END) and labels["label_end"].max() > IS_END
    frozen = pd.read_csv(ran["root"] / "data" / "processed" / "features.csv", index_col=[0, 1], parse_dates=[0])
    full = pd.read_csv(oos_dir / "features.csv", index_col=[0, 1], parse_dates=[0])
    assert np.allclose(full.loc[frozen.index].to_numpy(), frozen.to_numpy(), atol=1e-12, rtol=0, equal_nan=True)


class _Stop(Exception):
    pass


def test_rebuild_tables_passes_the_truncation_and_the_lock_to_the_builder(script, project, tmp_path, monkeypatch):
    """S38-1: is_end stays the period boundary, truncate_at = data.end, lock_path = the project's FROZEN.lock."""
    root = frozen_copy(script, project, tmp_path)
    calls = []

    def spy(daily_open, daily_close, is_end, truncate_at=None, lock_path=None):
        calls.append((pd.Timestamp(is_end), truncate_at, lock_path))
        raise _Stop

    monkeypatch.setattr(script.features_script(), "build_forward_returns", spy)
    with pytest.raises(_Stop):
        script.rebuild_tables(root, project["cfg"], tmp_path / "tables")
    assert calls == [(IS_END, pd.Timestamp(DATA_END), root / "FROZEN.lock")]
    assert not (tmp_path / "tables").exists()


def test_rebuild_tables_is_refused_by_the_builder_without_the_lock(script, project, tmp_path):
    """S38-1: without FROZEN.lock, build_forward_returns itself raises before any table is built or written."""
    root = copy_project(project, tmp_path)
    with pytest.raises(OOSAccessError, match="needs an existing FROZEN.lock"):
        script.rebuild_tables(root, project["cfg"], tmp_path / "tables")
    assert not (tmp_path / "tables").exists()


def test_the_refits_start_with_2019_q4_and_continue_quarterly_purged(script, ran):
    folds = ran["report"]["folds"]
    assert folds[0]["test_start"] == "2019-10-04" and folds[0]["test_end"] == "2019-12-27"
    assert [(f["test_year"], f["refit"]) for f in folds] == [(2019, 4), (2020, 1), (2020, 2), (2020, 3), (2020, 4)]
    for f in folds:
        test_start, purge_end = pd.Timestamp(f["test_start"]), pd.Timestamp(f["purge_end"])
        assert purge_end == test_start - pd.Timedelta(days=7)
        assert pd.Timestamp(f["train_end"]) + pd.Timedelta(days=10) <= purge_end
    assert folds[-1]["test_end"] == "2020-12-04"  # the last week whose label is realised by data.end
    assert ran["report"]["last_in_sample_scored_week"] == "2019-12-13"


def test_the_2019_q4_refit_reproduces_the_frozen_scores(script, ran):
    for name, check in ran["report"]["reproduction_2019q4"].items():
        assert check["weeks"] == 11, name  # 2019-10-04 .. 2019-12-13
        assert check["within_tolerance"] and check["signals_identical"], name


def test_oos_scores_use_the_frozen_values(script, ran):
    root, cfg, lock = ran["root"], ran["cfg"], ran["lock"]
    oos = {name: pd.read_csv(root / "outputs" / "oos" / name / "scores.csv", index_col=[0, 1], parse_dates=[0, 1])
           for name in lock["models"]}
    for name, scores in oos.items():
        assert closes(scores).min() == pd.Timestamp("2019-12-20"), name
        assert closes(scores).max() == pd.Timestamp("2020-12-04"), name
    assert np.allclose(oos["ENS"].to_numpy(), ensemble_scores([oos[m] for m in ("M1", "M2", "M3")]).to_numpy())
    # M0* runs as M0 on MOM{L}_1 with its frozen lookback: the z-scored momentum column of the rebuilt tables
    lookback = int(lock["frozen_values"]["M0_star"]["value"])
    momentum = pd.read_csv(root / "data" / "processed" / "oos" / "momentum_variants.csv", index_col=[0, 1], parse_dates=[0])
    column = momentum[f"MOM{lookback}_1"].unstack("ticker")
    expected = column.loc[closes(oos["M0_star"]), list(oos["M0_star"].columns)]
    assert np.allclose(oos["M0_star"].to_numpy(), expected.to_numpy())
    # an M1 refit at another grid value gives other scores: the frozen value is the one used
    vault_data = script.ladder_data(_open_vault(script, root, cfg), pd.Timestamp(DATA_END))
    folds = script.oos_folds(vault_data, cfg, pd.Timestamp("2019-12-13"))
    value = lock["frozen_values"]["M1"]["value"]
    refit = walkforward_rung("M1", vault_data, folds, cfg, value=value)[0]
    assert np.allclose(refit.loc[oos["M1"].index].to_numpy(), oos["M1"].to_numpy(), atol=1e-12, rtol=0)


def _open_vault(script, root, cfg):
    vault = script.Vault(IS_END, lock_path=root / "FROZEN.lock", log_path=root / "outputs" / "test_vault_log.jsonl",
                         data_dir=root / "data" / "processed" / "oos", cfg=cfg)
    vault.unlock()
    return vault


def test_one_continuous_book_across_the_boundary(script, ran):
    root = ran["root"]
    for name in ran["lock"]["models"]:
        weekly = read_weekly(root / "outputs" / "oos" / name / "weekly.csv")
        assert set(weekly["period"]) == {"IS", "OOS"}
        assert (weekly["period"] == np.where(weekly["realised_on"] <= IS_END, "IS", "OOS")).all()
        assert closes(weekly)[0] == pd.Timestamp("2017-01-06") and weekly["turnover"].iloc[0] == pytest.approx(1.0)
        first_oos = weekly.loc[weekly["period"] == "OOS"].iloc[0]
        assert first_oos["realised_on"] == pd.Timestamp("2019-12-30")
        assert first_oos["turnover"] < 1.0  # costed from the drifted In-Sample book (Amendment 2 C5), not from cash
        check = ran["report"]["in_sample_backtest_check"][name]
        assert check["weeks"] == int((weekly["period"] == "IS").sum()) and check["max_abs_diff_net"] <= 1e-12
        summary = json.loads((root / "outputs" / "oos" / name / "summary.json").read_text(encoding="utf-8"))
        assert set(summary["scenarios"]["10bps_2pct"]) == {"IS", "OOS"}
        metrics = pd.read_csv(root / "outputs" / "oos" / name / "metrics.csv")
        assert set(metrics["period"]) == {"IS", "OOS"} and len(metrics) == 3 * 2 * 2


def test_the_run_does_not_touch_the_repository(script, ran):
    assert not (ROOT / "FROZEN.lock").exists()
    assert not (ROOT / "outputs" / "oos_access_log.json").exists()


def test_run_refuses_a_lock_that_is_not_json(script, project, tmp_path):
    root = copy_project(project, tmp_path)
    (root / "FROZEN.lock").write_text("signed by hand", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        script.run_oos(root)
    assert nothing_accessed(root)


# ---------------------------------------------------------------- the rerun of Amendment 8 C1 (decision S36-1)


def rerun_decision(decision_id: str, fix: str, files, bug: str = "a synthetic bug found after the run of record") -> str:
    """A rerun decision entry of docs/decisions.md with the fields of S36-1."""
    named = ", ".join(f"`{path}`" for path in files)
    return (f"\n### {decision_id} · Rerun after a synthetic fix\n\n| Field | Content |\n| --- | --- |\n"
            f"| Date | 2026-11-08 |\n| Bug | {bug} |\n| Fix commit | `{fix}` |\n| Fix files | {named} |\n"
            "| Approved by | Test |\n")


def record_decision(root: Path, text: str) -> None:
    with open(root / "docs" / "decisions.md", "a", encoding="utf-8", newline="\n") as f:
        f.write(text)
    commit(root, "docs: record a rerun decision")


def make_fix(root: Path, files: dict | None = None) -> str:
    """Commit a synthetic fix and return its full hash."""
    for name, content in (files or {"fix.py": "x = 2\n"}).items():
        (root / name).write_text(content, encoding="utf-8", newline="\n")
    commit(root, "fix: a synthetic bug")
    return git(root, "rev-parse", "HEAD").strip()


def commit_log(root: Path) -> None:
    """Commit the access log as S34-4 prescribes after the run (outputs/ is git-ignored)."""
    git(root, "add", "-f", "outputs/oos_access_log.json")
    commit(root, "data: the Out-of-Sample access log")


def ran_copy(ran: dict, tmp_path: Path) -> Path:
    return copy_repo(ran["root"], tmp_path / "project")


def log_entries(root: Path) -> list[dict]:
    return json.loads((root / "outputs" / "oos_access_log.json").read_text(encoding="utf-8"))


def nothing_rerun(root: Path, entries: int = 1) -> bool:
    return len(log_entries(root)) == entries and not (root / "outputs" / "oos_reruns").exists() \
        and not (root / "data" / "processed" / "oos_reruns").exists()


def tree_hashes(folder: Path, script) -> dict:
    return {p.relative_to(folder).as_posix(): script.file_sha256(p) for p in sorted(folder.rglob("*")) if p.is_file()}


def test_parse_rerun_decision_reads_the_three_fields(script):
    text = "# Decision log\n" + rerun_decision("S99-1", "ABCDEF1", ["b.py", "a.py", "b.py"], bug="x \\| y")
    tables = script.decision_tables(text)
    decision = script.parse_rerun_decision("S99-1", tables["S99-1"])
    assert decision == script.RerunDecision("S99-1", "x \\| y", "abcdef1", ("a.py", "b.py"))
    assert script.rerun_decisions(text) == {"S99-1": decision}
    with pytest.raises(ValueError, match="not found"):
        script.parse_rerun_decision("S99-2", tables.get("S99-2", []))
    with pytest.raises(ValueError, match="exactly one commit hash"):
        script.parse_rerun_decision("S99-1", [{**tables["S99-1"][0], "Fix commit": "`abcdef1` then `abcdef2`"}])
    with pytest.raises(ValueError, match="heads 2 entries"):
        script.parse_rerun_decision("S99-1", script.decision_tables(text + text)["S99-1"])


def test_no_decision_up_to_s36_1_reads_as_a_rerun_decision(script):
    text = (ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    ids = list(script.decision_tables(text))  # in the order of the file
    up_to_s36_1 = ids[: ids.index("S36-1") + 1]
    assert len(up_to_s36_1) > 90 and not set(up_to_s36_1) & set(script.rerun_decisions(text))


def test_a_second_plain_run_points_to_rerun(script, ran):
    with pytest.raises(SystemExit, match="--rerun DECISION_ID"):
        script.run_oos(ran["root"])


@pytest.mark.parametrize("case", ["missing", "no_fields", "bad_id"])
def test_a_rerun_naming_no_valid_decision_is_refused(script, ran, tmp_path, case):
    root = ran_copy(ran, tmp_path)
    fix = make_fix(root)
    if case == "no_fields":  # an ordinary decision: no Bug, Fix commit or Fix files
        record_decision(root, "\n### S99-1 · An ordinary decision\n\n| Field | Content |\n| --- | --- |\n"
                              f"| Decision | fixed in `{fix[:10]}` |\n| Files affected | `fix.py` |\n")
    expected = {"missing": "decision S99-1 not found", "no_fields": "is not a rerun decision",
                "bad_id": "is not a decision ID"}[case]
    with pytest.raises(SystemExit, match=expected):
        script.run_oos(root, rerun="S99 1" if case == "bad_id" else "S99-1")
    assert nothing_rerun(root)


def test_a_rerun_needs_the_run_of_record(script, project, tmp_path):
    root = frozen_copy(script, project, tmp_path)
    fix = make_fix(root)
    record_decision(root, rerun_decision("S99-1", fix, ["fix.py"]))
    with pytest.raises(SystemExit, match="no run of record"):
        script.run_oos(root, rerun="S99-1")
    assert nothing_accessed(root)


def test_a_rerun_refuses_fix_files_that_differ_from_the_fix_commit(script, ran, tmp_path):
    root = ran_copy(ran, tmp_path)
    fix = make_fix(root)
    record_decision(root, rerun_decision("S99-1", fix[:10], ["fix.py", "other.py"]))
    with pytest.raises(SystemExit, match=r"changes \['fix.py'\], but 'Fix files' names"):
        script.run_oos(root, rerun="S99-1")
    assert nothing_rerun(root)


def test_a_rerun_refuses_files_changed_since_the_freeze_that_the_decision_does_not_name(script, ran, tmp_path):
    root = ran_copy(ran, tmp_path)
    fix = make_fix(root)
    record_decision(root, rerun_decision("S99-1", fix, ["fix.py"]))
    (root / "extra.py").write_text("y = 1\n", encoding="utf-8")
    commit(root, "feat: an unrecorded change")
    with pytest.raises(SystemExit, match=r"files changed since the freeze: \['extra.py'\]"):
        script.run_oos(root, rerun="S99-1")
    assert nothing_rerun(root)


def test_a_rerun_refuses_a_fix_of_a_setting_or_a_fix_before_the_freeze(script, ran, tmp_path):
    root = ran_copy(ran, tmp_path)
    fix = make_fix(root)
    record_decision(root, rerun_decision("S99-1", fix, ["config.yaml"]))
    with pytest.raises(SystemExit, match="changes no setting"):
        script.run_oos(root, rerun="S99-1")
    record_decision(root, rerun_decision("S99-2", ran["lock"]["code_commit"], ["fix.py"]))
    with pytest.raises(SystemExit, match="does not come after the frozen commit"):
        script.run_oos(root, rerun="S99-2")
    record_decision(root, rerun_decision("S99-3", "0" * 40, ["fix.py"]))
    with pytest.raises(SystemExit, match="not a commit of this repository"):
        script.run_oos(root, rerun="S99-3")
    assert nothing_rerun(root)


_RERAN: dict = {}


@pytest.fixture
def reran(script, ran, tmp_path_factory) -> dict:
    """A copy of the run project with the log committed (S34-4), a fix, its rerun decision S99-1 and one rerun (read-only,
    built once)."""
    if not _RERAN:
        root = tmp_path_factory.mktemp("oos_reran") / "project"
        copy_repo(ran["root"], root)
        before = tree_hashes(root / "outputs" / "oos", script)
        commit_log(root)
        fix = make_fix(root)
        record_decision(root, rerun_decision("S99-1", fix[:10], ["fix.py"]))
        report = script.run_oos(root, rerun="S99-1")
        _RERAN.update(root=root, fix=fix, report=report, before=before)
    return _RERAN


def test_a_rerun_appends_one_entry_naming_its_decision(script, ran, reran):
    root = reran["root"]
    entries = log_entries(root)
    assert len(entries) == 2 and entries[0] == log_entries(ran["root"])[0]
    assert entries[1]["rerun_decision"] == "S99-1" and entries[1]["fix_commit"] == reran["fix"]
    assert entries[1]["lock_sha256"] == entries[0]["lock_sha256"]
    decisions = (root / "docs" / "decisions.md").read_text(encoding="utf-8")
    text = (root / "outputs" / "oos_access_log.json").read_text(encoding="utf-8")
    assert script.check_oos_log_text(text, decisions_text=decisions) == 2
    before = (ran["root"] / "docs" / "decisions.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="2 entries"):  # against the decisions before S99-1 was recorded
        script.check_oos_log_text(text, decisions_text=before)


def test_a_rerun_writes_its_own_folders_and_leaves_the_run_of_record_untouched(script, ran, reran):
    root = reran["root"]
    assert tree_hashes(root / "outputs" / "oos", script) == reran["before"]
    for path, digest in ran["lock"]["artefacts"].items():
        assert script.file_sha256(root / path) == digest
    report = json.loads((root / "outputs" / "oos_reruns" / "S99-1" / "run.json").read_text(encoding="utf-8"))
    assert report["rerun"] == {"decision": "S99-1", "bug": "a synthetic bug found after the run of record",
                               "fix_commit": reran["fix"], "fix_files": ["fix.py"]}
    assert json.loads((root / "outputs" / "oos" / "run.json").read_text(encoding="utf-8"))["rerun"] is None
    assert (root / "data" / "processed" / "oos_reruns" / "S99-1" / "forward_returns.csv").exists()
    for name in ran["lock"]["models"]:  # the synthetic fix touches no code the run uses: the same books
        first = read_weekly(root / "outputs" / "oos" / name / "weekly.csv")
        second = read_weekly(root / "outputs" / "oos_reruns" / "S99-1" / name / "weekly.csv")
        assert first.index.equals(second.index) and np.allclose(first["net"], second["net"], atol=1e-12, rtol=0)


def test_a_decision_allows_one_rerun_and_a_later_rerun_may_follow_an_earlier_fix(script, reran, tmp_path):
    root = copy_repo(reran["root"], tmp_path / "project")
    commit_log(root)
    with pytest.raises(SystemExit, match="already holds the rerun of decision S99-1"):
        script.run_oos(root, rerun="S99-1")
    fix = make_fix(root, {"fix2.py": "z = 3\n"})
    record_decision(root, rerun_decision("S99-2", fix, ["fix2.py"]))
    _, _, decision = script.verify_lock(root, "S99-2")  # fix.py of S99-1 also changed since the freeze: recorded
    assert decision.files == ("fix2.py",) and decision.fix_commit == fix
    assert len(log_entries(root)) == 2  # the checks write nothing
