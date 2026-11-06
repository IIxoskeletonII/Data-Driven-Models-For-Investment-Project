"""05_train_walkforward.py for the round-2 rungs M6, M7 and M8 (Amendment 9 C1, C4; decisions S41-4 and S41-5): rung
and fixed names, spec shapes, unchanged round-1 identities, the outputs of a run, the trial log and the vault's checks
of round-2 specs.

The script's module name starts with a digit, so it is loaded from its file. The data folder is built from the shared
synthetic market (sessions 2011-01-03 to 2020-12-31) truncated at the In-Sample end, with the 4-week labels_h4.csv
added, and a copy of config.yaml whose warm-up ends in 2012, whose test years are 2014-2019, whose inner validation
window is 26 weeks and whose round2.test_weeks is the synthetic test-week count. Every path (data, outputs, lock, access
log, trial log) is under a temporary folder; main() is never run on the real data. The committed docs/trial_log.csv is
only read.
"""

import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src import contracts, features, models
from src.config import check_used, load_config, save_used
from src.vault import Vault, logged_spec_hashes, spec_hash

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
SECTORS = list(contracts.universe(CFG).sectors)
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
FIRST_WEEK = "2014-01-03"
LAST_WEEK = "2019-12-13"
N_TEST_WEEKS = len(pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D"))
SUMMARY_KEYS = {"name", "rung", "spec_hash", "refits", "rows", "weeks", "values", "nan_count", "first_week", "last_week",
                "column_sums", "min", "max", "spots", "scores_sha256"}
OUTPUT_FILES = ["scores.csv", "used.yaml", "summary.json"]
SYNTHETIC_SPOTS = (("2014-01-03", "XLB"), ("2015-06-12", "XLK"), ("2016-02-12", "XLE"), ("2018-10-12", "XLF"),
                   ("2019-12-13", "XLY"))
ROUND1_RUNGS = ("M0", "M1", "M2", "M3", "ENS", "M0_star")
ROUND1_FIXED = ["M1_a0.1", "M1_a1", "M1_a10", "M2_a0.1", "M2_a1", "M2_a10", "M3_d2", "M3_d3", "M0_L13", "M0_L26",
                "M0_L52"]
ROUND2_FIXED = ["M6_a0.1", "M6_a1", "M6_a10", "M7_a0.1_h2", "M7_a0.1_h4", "M7_a1_h2", "M7_a1_h4", "M7_a10_h2",
                "M7_a10_h4", "M8_d2_h2", "M8_d2_h4", "M8_d3_h2", "M8_d3_h4"]
ROUND2_PARAMS = {
    "M6_a0.1": {"alpha": 0.1}, "M6_a1": {"alpha": 1}, "M6_a10": {"alpha": 10},
    "M7_a0.1_h2": {"alpha": 0.1, "half_life_weeks": 2}, "M7_a0.1_h4": {"alpha": 0.1, "half_life_weeks": 4},
    "M7_a1_h2": {"alpha": 1, "half_life_weeks": 2}, "M7_a1_h4": {"alpha": 1, "half_life_weeks": 4},
    "M7_a10_h2": {"alpha": 10, "half_life_weeks": 2}, "M7_a10_h4": {"alpha": 10, "half_life_weeks": 4},
    "M8_d2_h2": {"max_depth": 2, "half_life_weeks": 2}, "M8_d2_h4": {"max_depth": 2, "half_life_weeks": 4},
    "M8_d3_h2": {"max_depth": 3, "half_life_weeks": 2}, "M8_d3_h4": {"max_depth": 3, "half_life_weeks": 4},
}
SELECTION_BASE = ["test_year", "refit", "test_start", "train_start", "train_end", "purge_end", "inner_train_end",
                  "inner_purge_end", "inner_val_start", "inner_val_end", "inner_val_weeks"]
TRIAL_LOG = ROOT / "docs" / "trial_log.csv"
VOL_RATIO = {"name": "vol ratio", "expr": {"op": "cs_z", "x": {
    "op": "ratio",
    "a": {"op": "rolling", "stat": "std", "n": 4, "x": {"op": "diff", "n": 1, "x": {"op": "log", "x": {"input": "close"}}}},
    "b": {"op": "rolling", "stat": "std", "n": 26, "x": {"op": "diff", "n": 1, "x": {"op": "log", "x": {"input": "close"}}}},
}}}


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script("train_walkforward_script_round2", "05_train_walkforward.py")


@pytest.fixture(scope="module")
def script03():
    return load_script("build_features_script_walkforward_round2", "03_build_features.py")


def synthetic_cfg() -> dict:
    """config.yaml fitted to the synthetic market (2011-2020); same In-Sample end; round2.test_weeks = synthetic count."""
    cfg = copy.deepcopy(CFG)
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2013]
    cfg["split"]["test_years"] = [2014, 2019]
    cfg["tuning"]["inner_validation_weeks"] = 26
    cfg["round2"]["test_weeks"] = N_TEST_WEEKS
    return cfg


SYN_CFG = synthetic_cfg()
_BUILT: dict = {}


def build_data_dir(script03, market, data_dir: Path, lock: Path) -> None:
    """The round-1 tables, labels_h4.csv and features_config.yaml from the synthetic market cut at the In-Sample end."""
    daily_close = market.daily_close[market.daily_close.index <= IS_END]
    daily_open = market.daily_open[market.daily_open.index <= IS_END]
    vix = market.vix[market.vix.index <= IS_END]
    fred = market.fred[market.fred.index <= IS_END]
    tables = script03.build_tables(daily_close, vix, fred, SYN_CFG)
    labels = script03.build_labels(daily_open, daily_close, IS_END)
    forward = script03.build_forward_returns(daily_open, daily_close, IS_END)
    labels_h4 = script03.build_horizon_labels(daily_open, daily_close, IS_END, 4)
    script03.write_tables({**tables, "labels": labels, "forward_returns": forward, "labels_h4": labels_h4}, data_dir,
                          IS_END, lock)
    save_used(features.features_settings(SYN_CFG), data_dir / "features_config.yaml")


def paths(root: Path, data_dir: Path) -> dict:
    return {"data_dir": data_dir, "out_dir": root / "out", "trial_path": root / "trial_log.csv",
            "log_path": root / "logs" / "vault_access_log.jsonl", "lock_path": root / "FROZEN.lock"}


def run_name(script, name: str, root: Path, data_dir: Path) -> tuple[dict, dict]:
    where = paths(root, data_dir)
    return script.run(name, SYN_CFG, spots=SYNTHETIC_SPOTS, **where), where


@pytest.fixture
def data_dir(script03, synthetic_market, tmp_path_factory) -> Path:
    """One synthetic data folder shared by the tests of this module (read-only)."""
    if "data_dir" not in _BUILT:
        root = tmp_path_factory.mktemp("round2_walkforward")
        build_data_dir(script03, synthetic_market, root / "processed", root / "FROZEN.lock")
        _BUILT["data_dir"] = root / "processed"
    return _BUILT["data_dir"]


def shared_run(script, name: str, data_dir: Path, tmp_path_factory) -> dict:
    """One run per name into its own temporary root, shared by the tests of this module (read-only)."""
    if name not in _BUILT:
        root = tmp_path_factory.mktemp(f"run_{name}")
        summary, where = run_name(script, name, root, data_dir)
        _BUILT[name] = {"summary": summary, "where": where, "root": root}
    return _BUILT[name]


@pytest.fixture
def m6(script, data_dir, tmp_path_factory) -> dict:
    return shared_run(script, "M6", data_dir, tmp_path_factory)


@pytest.fixture
def m7_a1_h2(script, data_dir, tmp_path_factory) -> dict:
    return shared_run(script, "M7_a1_h2", data_dir, tmp_path_factory)


@pytest.fixture
def m8_d2_h2(script, data_dir, tmp_path_factory) -> dict:
    return shared_run(script, "M8_d2_h2", data_dir, tmp_path_factory)


def read_scores(out_dir: Path) -> pd.DataFrame:
    return pd.read_csv(out_dir / "scores.csv", index_col=[0, 1], parse_dates=[0, 1])


def read_trials(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def log_lines(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canonical(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------- names and specs (S41-5)


def test_rungs_append_m6_m7_m8_to_round1(script):
    assert tuple(script.RUNGS) == ROUND1_RUNGS + ("M6", "M7", "M8")


def test_fixed_names_are_round1_then_the_13_round2_names(script):
    assert script.fixed_names(CFG) == ROUND1_FIXED + ROUND2_FIXED


@pytest.mark.parametrize("rung", ["M6", "M7", "M8"])
def test_spec_of_a_tuned_round2_rung(script, rung):
    spec = script.spec_for(rung, CFG)
    assert set(spec) == {"rung", "round2", "tuning", "author", "kind", "notes"}
    assert spec["rung"] == rung
    assert spec["round2"] == models.round2_spec_settings(CFG)
    assert spec["tuning"] == models.tuning_spec(CFG)
    assert (spec["author"], spec["kind"]) == ("Eliya Allam", "human")
    assert isinstance(spec["notes"], str) and spec["notes"]


@pytest.mark.parametrize("name", ROUND2_FIXED)
def test_spec_of_a_fixed_round2_value(script, name):
    spec = script.spec_for(name, CFG)
    assert set(spec) == {"rung", "round2", "params", "author", "kind", "notes"}
    assert spec["rung"] == name.split("_")[0]
    assert spec["round2"] == models.round2_spec_settings(CFG)
    assert spec["params"] == ROUND2_PARAMS[name]
    assert list(spec["params"]) == list(ROUND2_PARAMS[name])
    for key, value in ROUND2_PARAMS[name].items():
        assert type(spec["params"][key]) is type(value), (name, key)
    assert (spec["author"], spec["kind"]) == ("Eliya Allam", "human")


def test_round2_spec_carries_the_score_keys_of_the_cfg_given(script):
    """S41-5: the spec carries exactly the score-determining keys of the round2 section of the cfg passed (so the
    synthetic cfg, with its own test_weeks, differs)."""
    spec = script.spec_for("M6", SYN_CFG)
    assert list(spec["round2"]) == ["test_weeks", "label", "smoothing", "models", "tie_order", "tie_precedence"]
    assert spec["round2"] == {key: SYN_CFG["round2"][key] for key in spec["round2"]}
    assert spec["round2"] != models.round2_spec_settings(CFG)
    assert spec_hash(script.spec_for("M7_a1_h2", SYN_CFG), SYN_CFG) != spec_hash(script.spec_for("M7_a1_h2", CFG), SYN_CFG)


@pytest.mark.parametrize("name", list(ROUND1_RUNGS) + ROUND1_FIXED)
def test_round1_spec_hashes_are_unchanged(script, name):
    """C4: every round-1 name of 05 still reproduces a spec_hash logged in docs/trial_log.csv."""
    spec = script.spec_for(name, CFG)
    assert "round2" not in spec
    assert spec_hash(spec, CFG) in logged_spec_hashes(TRIAL_LOG)


def test_round2_specs_have_distinct_hashes(script):
    names = ["M6", "M7", "M8"] + ROUND2_FIXED
    hashes = {spec_hash(script.spec_for(name, CFG), CFG) for name in names}
    assert len(hashes) == len(names)
    round1 = {spec_hash(script.spec_for(name, CFG), CFG) for name in list(ROUND1_RUNGS) + ROUND1_FIXED}
    assert not hashes & round1


@pytest.mark.parametrize("argv", [["--model", "M9"], ["--fixed", "M6_a5"], ["--fixed", "M7_a1"], ["--fixed", "M8_d4_h2"]])
def test_main_refuses_unknown_round2_names(script, argv):
    with pytest.raises(SystemExit):
        script.main(argv)


# ---------------------------------------------------------------- runs on the synthetic market


def fridays() -> list[pd.Timestamp]:
    return list(pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D"))


@pytest.mark.parametrize("run", ["m6", "m7_a1_h2", "m8_d2_h2"])
def test_run_writes_the_round1_outputs(run, request):
    built = request.getfixturevalue(run)
    out_dir = built["where"]["out_dir"]
    for name in OUTPUT_FILES:
        assert (out_dir / name).exists(), name
    scores = read_scores(out_dir)
    assert list(scores.index.names) == ["date_open", "date_close"]
    assert list(scores.columns) == SECTORS
    contracts.validate_scores(scores.astype("float64"))
    assert list(pd.DatetimeIndex(scores.index.get_level_values("date_close"))) == fridays()


@pytest.mark.parametrize("run", ["m6", "m7_a1_h2", "m8_d2_h2"])
def test_run_used_yaml_is_the_walkforward_settings(run, request):
    """S41-5 (d): used.yaml is walkforward_settings(cfg), without the round2 section."""
    used = request.getfixturevalue(run)["where"]["out_dir"] / "used.yaml"
    check_used(models.walkforward_settings(SYN_CFG), used, "05_train_walkforward.py")
    with open(used, encoding="utf-8") as f:
        assert set(yaml.safe_load(f)) == {"seed", "data", "split", "execution", "features", "models"}


@pytest.mark.parametrize("run, name, rung", [("m6", "M6", "M6"), ("m7_a1_h2", "M7_a1_h2", "M7"),
                                             ("m8_d2_h2", "M8_d2_h2", "M8")])
def test_run_summary_has_round1_keys(script, run, name, rung, request):
    built = request.getfixturevalue(run)
    out_dir = built["where"]["out_dir"]
    on_disk = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert set(on_disk) == SUMMARY_KEYS
    assert on_disk == json.loads(json.dumps(built["summary"]))
    assert (on_disk["name"], on_disk["rung"]) == (name, rung)
    assert on_disk["refits"] == 24
    assert on_disk["weeks"] == on_disk["rows"] == N_TEST_WEEKS
    assert (on_disk["first_week"], on_disk["last_week"]) == (FIRST_WEEK, LAST_WEEK)
    assert on_disk["nan_count"] == 0
    assert on_disk["spec_hash"] == spec_hash(script.spec_for(name, SYN_CFG), SYN_CFG)
    assert on_disk["scores_sha256"] == hashlib.sha256((out_dir / "scores.csv").read_bytes()).hexdigest()
    content = (out_dir / "summary.json").read_bytes()
    assert b"\r\n" not in content


def test_tuned_run_writes_the_s41_4_selection_csv(m6):
    selection = pd.read_csv(m6["where"]["out_dir"] / "selection.csv")
    sharpes = ["sharpe_a0.1", "sharpe_a1", "sharpe_a10"]
    assert list(selection.columns) == SELECTION_BASE + sharpes + ["chosen", "chosen_alpha"]
    assert len(selection) == 24
    assert (selection["inner_val_weeks"] == 26).all()
    tie_order = ["a10", "a1", "a0.1"]
    values = {"a0.1": 0.1, "a1": 1, "a10": 10}
    for _, row in selection.iterrows():
        chosen = models.choose_grid_value({tag.removeprefix("sharpe_"): row[tag] for tag in sharpes}, tie_order)
        assert row["chosen"] == chosen
        assert float(row["chosen_alpha"]) == values[chosen]
    assert int(selection.iloc[-1]["test_year"]) == 2019


@pytest.mark.parametrize("run", ["m7_a1_h2", "m8_d2_h2"])
def test_fixed_run_writes_no_selection_csv(run, request):
    assert not (request.getfixturevalue(run)["where"]["out_dir"] / "selection.csv").exists()


@pytest.mark.parametrize("run, name", [("m6", "M6"), ("m7_a1_h2", "M7_a1_h2"), ("m8_d2_h2", "M8_d2_h2")])
def test_run_logs_one_trial_row_with_the_spec(script, run, name, request):
    built = request.getfixturevalue(run)
    rows = read_trials(built["where"]["trial_path"])
    assert len(rows) == 1
    spec = script.spec_for(name, SYN_CFG)
    assert rows[0]["rung"] == name.split("_")[0]
    assert (rows[0]["author"], rows[0]["kind"]) == ("Eliya Allam", "human")
    assert rows[0]["spec_hash"] == spec_hash(spec, SYN_CFG)
    assert json.loads(rows[0]["params_json"]) == spec
    assert rows[0]["params_json"] == canonical(spec)
    assert rows[0]["is_sharpe"] == "" and rows[0]["is_mdd"] == ""


def test_rerun_adds_no_trial_row(script, data_dir, tmp_path):
    first, where = run_name(script, "M7_a1_h2", tmp_path, data_dir)
    second, _ = run_name(script, "M7_a1_h2", tmp_path, data_dir)
    assert first == second
    assert len(read_trials(where["trial_path"])) == 1


def test_two_configurations_give_two_trial_rows(script, data_dir, tmp_path):
    run_name(script, "M6_a1", tmp_path, data_dir)
    _, where = run_name(script, "M6_a10", tmp_path, data_dir)
    rows = read_trials(where["trial_path"])
    assert [row["rung"] for row in rows] == ["M6", "M6"]
    assert rows[0]["spec_hash"] != rows[1]["spec_hash"]


def test_tuned_run_twice_gives_byte_identical_files(script, m6, data_dir, tmp_path):
    _, other = run_name(script, "M6", tmp_path / "again", data_dir)
    for name in OUTPUT_FILES + ["selection.csv"]:
        assert (other["out_dir"] / name).read_bytes() == (m6["where"]["out_dir"] / name).read_bytes(), name


def test_round2_scored_weeks_equal_round1(script, m6, data_dir, tmp_path):
    """S41-2: the round-2 test weeks are exactly round 1's (the M2 run on the same data and cfg)."""
    _, where = run_name(script, "M2_a1", tmp_path, data_dir)
    round1 = read_scores(where["out_dir"])
    round2 = read_scores(m6["where"]["out_dir"])
    assert round2.index.equals(round1.index)


def test_fixed_m6_at_the_chosen_value_reproduces_the_tuned_run(script, m6, data_dir, tmp_path):
    """The tuned M6 scores each refit like the fixed run at the alpha it chose (selection.csv)."""
    selection = pd.read_csv(m6["where"]["out_dir"] / "selection.csv", parse_dates=["test_start"])
    tuned = read_scores(m6["where"]["out_dir"])
    closes = pd.DatetimeIndex(tuned.index.get_level_values("date_close"))
    starts = list(selection["test_start"]) + [closes.max() + pd.Timedelta(days=7)]
    fixed = {}
    for tag in sorted(set(selection["chosen"])):
        _, where = run_name(script, f"M6_{tag}", tmp_path / tag, data_dir)
        fixed[tag] = read_scores(where["out_dir"])
    for k, row in selection.iterrows():
        weeks = (closes >= starts[k]) & (closes < starts[k + 1])
        pd.testing.assert_frame_equal(tuned.loc[weeks], fixed[row["chosen"]].loc[weeks], check_exact=False, rtol=1e-12,
                                      atol=1e-12)


# ---------------------------------------------------------------- the vault's checks of round-2 specs (S41-5)


def refused_specs() -> list[dict]:
    round2 = models.round2_spec_settings(SYN_CFG)
    other_round2 = copy.deepcopy(round2)
    other_round2["test_weeks"] = round2["test_weeks"] + 1
    tuning = models.tuning_spec(SYN_CFG)
    return [
        {"rung": "M6", "params": {"alpha": 1}},  # no round2
        {"rung": "M6", "round2": other_round2, "params": {"alpha": 1}},  # round2 differs from cfg["round2"]
        {"rung": "M6", "round2": models.round2_spec_settings(CFG), "params": {"alpha": 1}},  # real round2, synthetic cfg
        {"rung": "M6", "round2": SYN_CFG["round2"], "params": {"alpha": 1}},  # the whole section, gate and lab included
        {"rung": "M7", "round2": round2, "params": {"alpha": 1, "half_life_weeks": 2}, "tuning": tuning},  # both
        {"rung": "M7", "round2": round2},  # neither
        {"rung": "M6", "round2": round2, "params": {"alpha": 5}},  # not a grid value
        {"rung": "M6", "round2": round2, "params": {"alpha": 1.0}},  # grid value with another type
        {"rung": "M6", "round2": round2, "params": {"alpha": True}},
        {"rung": "M6", "round2": round2, "params": {"alpha": 1, "half_life_weeks": 2}},  # a key M6 does not have
        {"rung": "M7", "round2": round2, "params": {"alpha": 1}},  # H missing
        {"rung": "M7", "round2": round2, "params": {"alpha": 1, "half_life_weeks": 3}},
        {"rung": "M7", "round2": round2, "params": {"alpha": 1, "half_life_weeks": 2.0}},
        {"rung": "M8", "round2": round2, "params": {"max_depth": 2.0, "half_life_weeks": 2}},
        {"rung": "M8", "round2": round2, "params": {"max_depth": 4, "half_life_weeks": 2}},
        {"rung": "M8", "round2": round2, "params": {"alpha": 1, "half_life_weeks": 2}},
        {"rung": "M6", "round2": round2, "tuning": {"rule": "something else"}},  # differs from tuning_spec
        {"rung": "M7", "round2": round2, "params": {"alpha": 1, "half_life_weeks": 2}, "agent_features": [VOL_RATIO]},
        {"rung": "M7", "round2": round2, "tuning": tuning, "agent_features": [VOL_RATIO]},
        {"rung": "M6", "round2": round2, "params": {"alpha": 1}, "feature": "MOM26_1"},
        {"rung": "M8", "round2": round2, "tuning": tuning, "members": ["M6", "M7"]},
        {"rung": "M1", "round2": round2, "params": {"alpha": 1}},  # a round-1 spec carrying round2
        {"rung": "M0", "round2": round2, "feature": "MOM26_1"},
        {"rung": "M0_star", "round2": round2, "tuning": tuning},
        {"rung": "M9", "round2": round2, "tuning": tuning},  # M9 is not implemented in this session
    ]


@pytest.mark.parametrize("spec", refused_specs())
def test_vault_refuses_round2_specs_that_do_not_fit(data_dir, tmp_path, spec):
    log, trials = tmp_path / "logs" / "vault_access_log.jsonl", tmp_path / "trial_log.csv"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, data_dir=data_dir, cfg=SYN_CFG)
    with pytest.raises(ValueError):
        vault.run_walkforward({**spec, "author": "Eliya Allam", "kind": "human"}, trial_path=trials)
    assert log_lines(log)[-1]["result"] == "refused"
    assert not trials.exists()


def test_vault_accepts_a_round2_spec_and_logs_it(data_dir, tmp_path):
    """A fixed M6 spec with round2 = round2_spec_settings(cfg) runs on round 1's test weeks and adds one trial row."""
    log, trials = tmp_path / "log.jsonl", tmp_path / "trial_log.csv"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, data_dir=data_dir, cfg=SYN_CFG)
    spec = {"rung": "M6", "round2": models.round2_spec_settings(SYN_CFG), "params": {"alpha": 10}, "author": "Eliya Allam",
            "kind": "human", "notes": "fixed"}
    scores = vault.run_walkforward(spec, trial_path=trials)
    contracts.validate_scores(scores)
    assert list(pd.DatetimeIndex(scores.index.get_level_values("date_close"))) == fridays()
    assert vault.last_selection is None
    rows = read_trials(trials)
    assert len(rows) == 1 and rows[0]["rung"] == "M6" and rows[0]["spec_hash"] == spec_hash(spec, SYN_CFG)
    assert log_lines(log)[-1]["result"] == "ok"


def test_vault_refuses_a_round2_run_that_does_not_score_round2_test_weeks(data_dir, tmp_path):
    """S41-2: the vault stops a round-2 run whose scored weeks do not number round2.test_weeks (logged refused, no row)."""
    cfg = copy.deepcopy(SYN_CFG)
    cfg["round2"]["test_weeks"] = N_TEST_WEEKS + 1
    log, trials = tmp_path / "log.jsonl", tmp_path / "trial_log.csv"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, data_dir=data_dir, cfg=cfg)
    spec = {"rung": "M6", "round2": models.round2_spec_settings(cfg), "params": {"alpha": 10}, "author": "Eliya Allam",
            "kind": "human",
            "notes": "fixed"}
    with pytest.raises(ValueError, match="round2.test_weeks"):
        vault.run_walkforward(spec, trial_path=trials)
    assert log_lines(log)[-1]["result"] == "refused"
    assert not trials.exists()


# ---------------------------------------------------------------- the identity of a round-2 trial (S41-5)

ROUND2_NAMES = ["M6", "M7", "M8"] + ROUND2_FIXED


def round2_hashes(script, cfg: dict) -> dict[str, str]:
    return {name: spec_hash(script.spec_for(name, cfg), cfg) for name in ROUND2_NAMES}


@pytest.mark.parametrize("path, value", [
    (("selection", "bootstrap_prob"), 0.95),
    (("candidate_order",), ["M6", "M7", "M8"]),
    (("agent_lab", "max_candidates"), 39),
    (("agent_lab", "api_key_env"), "DDMI_OTHER_API_KEY"),
])
def test_gate_and_agent_lab_settings_leave_every_round2_spec_hash_unchanged(script, path, value):
    """S41-5: a trial's identity is the set of settings that determine its scores; round2.selection,
    round2.candidate_order and round2.agent_lab do not, so editing them stales no M6-M8 output."""
    edited = copy.deepcopy(CFG)
    target = edited["round2"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert round2_hashes(script, edited) == round2_hashes(script, CFG)


@pytest.mark.parametrize("path, value", [
    (("test_weeks",), 625),
    (("label", "horizon_weeks"), 5),
    (("smoothing", "lags_per_half_life"), 4),
    (("models", "M8", "n_estimators"), 300),
    (("tie_order", "alpha"), [1, 10, 0.1]),
    (("tie_precedence",), ["half_life_weeks", "alpha", "max_depth"]),
])
def test_every_score_key_of_round2_changes_every_round2_spec_hash(script, path, value):
    """S41-5: each score-determining key of round2 is part of every M6-M8 identity."""
    edited = copy.deepcopy(CFG)
    target = edited["round2"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    before, after = round2_hashes(script, CFG), round2_hashes(script, edited)
    assert all(before[name] != after[name] for name in ROUND2_NAMES)
