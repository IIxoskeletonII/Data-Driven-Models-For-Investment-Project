"""run_all.py (decisions S39-1 to S39-6): the step list read from 05, the order, the steps never run, the freeze flag, the
clean-tree rule, the stop at the first failing step, the summary table, and two runs of a stubbed step list on the
synthetic market giving identical outputs."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load("run_all_script", ROOT / "run_all.py")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "gc.auto", "0")
    git(root, "config", "maintenance.auto", "false")
    (root / ".gitignore").write_text("outputs/\n", encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit",
        "-q", "--no-verify", "-m", "chore: test repository")
    return root


def step_script(folder: Path, name: str, body: str) -> str:
    """A small Python script for a stubbed step; returns its absolute path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("import os, sys\nfrom pathlib import Path\n" + body, encoding="utf-8", newline="\n")
    return str(path)


# ---------------------------------------------------------------- the step list


def test_the_pipeline_runs_every_05_configuration_in_order_and_never_04_or_08(script):
    cfg = load_config()
    s05 = load("run_all_test_05", ROOT / "05_train_walkforward.py")
    rungs, fixed = list(s05.RUNGS), list(s05.fixed_names(cfg))
    names = [step.name for step in script.pipeline(cfg)]
    expected = (["01_download_data.py", "03_build_features.py"]
                + [f"05_train_walkforward.py --model {r}" for r in rungs]
                + [f"05_train_walkforward.py --fixed {f}" for f in fixed]
                + ["06_backtest.py --all", "06_backtest.py --shift-check " + " ".join(rungs), "06_backtest.py --placebo",
                   "05_train_walkforward.py --agent-returns", "05_train_walkforward.py --select", "07_evaluate.py",
                   "06_backtest.py --ledger-years"])
    assert names == expected
    round2 = tuple(f"{r}_" for r in cfg["round2"]["candidate_order"])
    assert len(set(fixed)) == len(fixed) and not set(fixed) & set(rungs) and "M0_star" in rungs
    assert len([f for f in fixed if not f.startswith(round2)]) == 11  # round 1's fixed values (S31-10); round 2 is extra
    assert not any(name.startswith(("04_", "08_")) for name in names)
    assert [s.name for s in script.pipeline(cfg) if s.frozen] == ["05_train_walkforward.py --agent-returns",
                                                                    "05_train_walkforward.py --select"]


def test_a_rung_added_to_05_is_run_and_shift_checked(script, monkeypatch):
    cfg = load_config()
    s05 = script._script("05_train_walkforward.py")
    monkeypatch.setattr(s05, "RUNGS", (*s05.RUNGS, "M6"))
    names = [step.name for step in script.pipeline(cfg)]
    assert "05_train_walkforward.py --model M6" in names
    assert next(n for n in names if "--shift-check" in n).endswith(" M6")


def test_run_steps_refuses_a_step_that_is_never_run(script, tmp_path):
    for banned in ("04_agent_lab.py", "08_run_oos.py"):
        with pytest.raises(SystemExit, match="never runs"):
            script.run_steps([script.Step((banned,))], tmp_path, seed=42, out=lambda _: None)


# ---------------------------------------------------------------- preflight: freeze flag and raw snapshot


def test_preflight_needs_the_flag_after_the_freeze_and_the_lock_with_the_flag(script, tmp_path):
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "manifest.json").write_text("{}", encoding="utf-8")
    script.preflight(tmp_path, after_freeze=False)
    with pytest.raises(SystemExit, match="--after-freeze given, but FROZEN.lock does not exist"):
        script.preflight(tmp_path, after_freeze=True)
    (tmp_path / "FROZEN.lock").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="FROZEN.lock exists.*pass --after-freeze"):
        script.preflight(tmp_path, after_freeze=False)
    script.preflight(tmp_path, after_freeze=True)


def test_preflight_refuses_without_the_raw_snapshot(script, tmp_path):
    with pytest.raises(SystemExit, match="manifest.json not found.*never downloads"):
        script.preflight(tmp_path, after_freeze=False)


# ---------------------------------------------------------------- running steps


def test_it_stops_at_the_first_failure_naming_the_step_and_prints_the_summary(script, tmp_path):
    root, bin_dir = git_repo(tmp_path / "project"), tmp_path / "bin"
    ok = step_script(bin_dir, "ok.py", "Path('outputs').mkdir(exist_ok=True)\n"
                                       "Path('outputs', sys.argv[1]).write_text('done')\n")
    fail = step_script(bin_dir, "fail.py", "sys.exit(3)\n")
    steps = [script.Step((ok, "first")), script.Step((fail,)), script.Step((ok, "third"))]
    lines = []
    with pytest.raises(SystemExit, match=r"stopped: step '.*fail.py' failed with exit code 3"):
        script.run_steps(steps, root, seed=42, out=lines.append)
    assert (root / "outputs" / "first").exists() and not (root / "outputs" / "third").exists()
    table = lines[-1].lstrip(chr(10)).splitlines()  # header, rule, one row per step, total
    assert table[0].split() == ["step", "status", "seconds", "note"] and table[-1].startswith("total")
    first, failed, third = table[2:5]
    assert first.startswith(steps[0].name) and " ok " in first
    assert failed.startswith(steps[1].name) and " FAILED " in failed and failed.endswith("exit code 3")
    assert third.startswith(steps[2].name) and " not run " in third


def test_the_last_step_failing_leaves_the_earlier_outputs(script, tmp_path):
    root, bin_dir = git_repo(tmp_path / "project"), tmp_path / "bin"
    ok = step_script(bin_dir, "ok.py", "Path('outputs').mkdir(exist_ok=True)\nPath('outputs', 'result').write_text('x')\n")
    ledger = step_script(bin_dir, "ledger.py", "sys.exit(1)\n")
    lines = []
    with pytest.raises(SystemExit, match="ledger.py' failed.*the steps before it completed"):
        script.run_steps([script.Step((ok,)), script.Step((ledger,))], root, seed=42, out=lines.append)
    assert (root / "outputs" / "result").read_text() == "x"
    assert "FAILED" in lines[-1] and "exit code 1" in lines[-1]


def test_frozen_steps_are_skipped_after_the_freeze_and_every_step_gets_the_hash_seed(script, tmp_path):
    root, bin_dir = git_repo(tmp_path / "project"), tmp_path / "bin"
    record = step_script(bin_dir, "record.py", "Path('outputs').mkdir(exist_ok=True)\n"
                                               "Path('outputs', sys.argv[1]).write_text(os.environ['PYTHONHASHSEED'])\n")
    steps = [script.Step((record, "a")), script.Step((record, "frozen"), frozen=True), script.Step((record, "b"))]
    results = script.run_steps(steps, root, seed=42, after_freeze=True, out=lambda _: None)
    assert [r.status for r in results] == ["ok", "skipped", "ok"]
    assert (root / "outputs" / "a").read_text() == "42" and not (root / "outputs" / "frozen").exists()
    results = script.run_steps(steps, root, seed=7, out=lambda _: None)
    assert [r.status for r in results] == ["ok", "ok", "ok"] and (root / "outputs" / "frozen").read_text() == "7"


def test_a_dirty_tree_is_refused_and_a_run_that_changes_the_tree_fails(script, tmp_path):
    root, bin_dir = git_repo(tmp_path / "project"), tmp_path / "bin"
    touch = step_script(bin_dir, "touch.py", "Path('tracked.txt').write_text('changed')\n")
    (root / "notes.txt").write_text("untracked", encoding="utf-8")
    with pytest.raises(SystemExit, match="not clean.*notes.txt"):
        script.run_steps([script.Step((touch,))], root, seed=42, out=lambda _: None)
    assert not (root / "tracked.txt").exists()  # refused before the first step
    (root / "notes.txt").unlink()
    with pytest.raises(SystemExit, match="the run changed 1 file.*tracked.txt"):
        script.run_steps([script.Step((touch,))], root, seed=42, out=lambda _: None)


def test_outside_a_git_checkout_the_tree_check_is_skipped_and_said(script, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    ok = step_script(bin_dir, "ok.py", "Path('done').write_text('x')\n")
    project = tmp_path / "zip" / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(script, "git_dirty", lambda root: None)  # what git says outside a work tree (also tested below)
    lines = []
    script.run_steps([script.Step((ok,))], project, seed=42, out=lines.append)
    assert lines[0] == "not a git checkout: the clean-tree check is skipped" and (project / "done").exists()


def test_git_dirty_is_none_outside_a_work_tree(script, tmp_path):
    outside = tmp_path / "plain"
    outside.mkdir()
    inside = subprocess.run(["git", "-C", str(outside), "rev-parse", "--is-inside-work-tree"], capture_output=True,
                            check=False)
    if inside.returncode == 0:
        pytest.skip("the temporary folder is inside a git work tree on this machine")
    assert script.git_dirty(outside) is None
    assert script.git_dirty(git_repo(tmp_path / "repo")) == []


# ---------------------------------------------------------------- two runs give identical outputs


STAGES = '''
REPO, STAGE, ROOT = Path(sys.argv[1]), sys.argv[2], Path.cwd()
sys.path[:0] = [str(REPO), str(REPO / "tests")]
import importlib.util
import pandas as pd
from conftest import make_synthetic_market
from src import features, plots
from src.config import load_config, save_used


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IS_END = pd.Timestamp("2019-12-27")
SPOTS = (("2017-01-06", "XLB"), ("2018-02-09", "XLE"), ("2019-12-13", "XLY"))
cfg = load_config(ROOT / "config.yaml")
processed = ROOT / "data" / "processed"
if STAGE == "features":  # 03_build_features.py, In-Sample
    market = make_synthetic_market()
    s03 = load("stub_03", "03_build_features.py")
    close = market.daily_close[market.daily_close.index <= IS_END]
    opens = market.daily_open[market.daily_open.index <= IS_END]
    tables = s03.build_tables(close, market.vix[market.vix.index <= IS_END], market.fred[market.fred.index <= IS_END],
                              cfg)
    tables["labels"] = s03.build_labels(opens, close, IS_END)
    tables["forward_returns"] = s03.build_forward_returns(opens, close, IS_END)
    s03.write_tables(tables, processed, IS_END, ROOT / "FROZEN.lock")
    save_used(features.features_settings(cfg), processed / "features_config.yaml")
elif STAGE == "models":  # 05_train_walkforward.py --model M0, then 06_backtest.py --model M0
    s05 = load("stub_05", "05_train_walkforward.py")
    s05.run("M0", cfg, data_dir=processed, out_dir=ROOT / "outputs" / "walkforward" / "M0",
            trial_path=ROOT / "docs" / "trial_log.csv", log_path=ROOT / "outputs" / "vault_access_log.jsonl",
            lock_path=ROOT / "FROZEN.lock", spots=SPOTS)
    s06 = load("stub_06", "06_backtest.py")
    s06.ROOT = ROOT
    s06.backtest_model(cfg, "M0", s06.in_sample_inputs(cfg))
elif STAGE == "plots":  # a chart of 07_evaluate.py
    weekly = pd.read_csv(ROOT / "outputs" / "backtests" / "M0" / "weekly.csv", index_col=[0, 1], parse_dates=[0, 1, 2])
    plots.equity_curves(weekly[["net"]].rename(columns={"net": "M0"}), weekly["period"], weekly["realised_on"],
                        ROOT / "outputs" / "plots" / "M0_equity")
else:
    raise SystemExit(f"unknown stage {STAGE}")
'''
LOGS = ("outputs/vault_access_log.jsonl",)  # append-only access logs: each run adds its own timestamped lines (S39-5)


def produced(root: Path) -> dict[str, str]:
    """SHA-256 of every file the stubbed pipeline writes (data/processed tables and outputs/), the access logs aside."""
    import hashlib
    files = sorted(p for p in [*(root / "data" / "processed").glob("*"), *(root / "outputs").rglob("*")] if p.is_file())
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            if p.relative_to(root).as_posix() not in LOGS}


def wipe(root: Path) -> None:
    """Remove what the stubbed steps write, so the second run rebuilds it rather than leaving the first run's files."""
    import shutil
    shutil.rmtree(root / "outputs")
    for name in ("features", "market_states", "labels", "momentum_variants", "sizing_betas", "forward_returns"):
        (root / "data" / "processed" / f"{name}.csv").unlink()
    (root / "data" / "processed" / "features_config.yaml").unlink()


def test_two_runs_of_a_stubbed_pipeline_give_identical_outputs(script, synthetic_market, tmp_path):
    helpers = load("run_all_project_helpers", ROOT / "tests" / "test_run_oos_script.py")
    root = tmp_path / "project"
    root.mkdir()
    cfg = helpers.build_project(root, synthetic_market, walkforwards=("M0",))
    trial_log = (root / "docs" / "trial_log.csv").read_bytes()
    stages = step_script(tmp_path / "bin", "stages.py", STAGES)
    steps = [script.Step((stages, str(ROOT), stage)) for stage in ("features", "models", "plots")]
    hashes = []
    for _ in range(2):
        wipe(root)
        results = script.run_steps(steps, root, seed=int(cfg["seed"]), out=lambda _: None)
        assert [r.status for r in results] == ["ok", "ok", "ok"]  # and the git tree is still clean (checked inside)
        hashes.append(produced(root))
    assert hashes[0] == hashes[1]
    assert {"data/processed/features.csv", "outputs/walkforward/M0/scores.csv", "outputs/backtests/M0/weekly.csv",
            "outputs/plots/M0_equity.html", "outputs/plots/M0_equity.png"} <= set(hashes[0])
    assert (root / "docs" / "trial_log.csv").read_bytes() == trial_log  # a logged spec adds no trial row
    assert json.loads((root / "outputs" / "walkforward" / "M0" / "summary.json").read_text(encoding="utf-8"))["weeks"] > 0


def test_the_headers_and_the_summary_keep_their_place_when_stdout_is_a_file(script, tmp_path):
    """The default output is flushed, so a log file shows each step's header before that step's own lines."""
    bin_dir = tmp_path / "bin"
    shout = step_script(bin_dir, "shout.py", "print('child line')\n")
    driver = bin_dir / "driver.py"
    driver.write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nimport importlib.util\n"
                      f"spec = importlib.util.spec_from_file_location('r', {str(ROOT / 'run_all.py')!r})\n"
                      "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                      "m.git_dirty = lambda root: []\n"
                      f"m.run_steps([m.Step(({shout!r},))], {str(tmp_path)!r}, seed=42)\n", encoding="utf-8")
    log = tmp_path / "log.txt"
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run([sys.executable, str(driver)], stdout=f, stderr=subprocess.STDOUT, check=True)
    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[0].startswith("=== ") and lines[1] == "child line" and lines[2].startswith("step")
