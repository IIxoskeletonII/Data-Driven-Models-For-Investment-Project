"""05_train_walkforward.py (S23-2, S23-3, S31-10): the In-Sample walk-forward of M0 and of the ladder (tuned rungs and
fixed grid values), its outputs, determinism and the trial log.

The script's module name starts with a digit, so it is loaded from its file, like 03_build_features.py. The data folder
is built here from the shared synthetic market (sessions 2011-01-03 to 2020-12-31) truncated at the In-Sample end, with
a copy of config.yaml whose warm-up ends in 2012, whose test years are 2014-2019 and whose inner validation window
(Amendment 5 C1) is 26 weeks, since the first training window holds only 2013. Every path (data, outputs, lock,
access log, trial log) is under a temporary folder; main() is never run on the real data.
"""

import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src import contracts, features, models
from src.config import check_used, load_config, save_used
from src.vault import Vault

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
SECTORS = list(contracts.universe(CFG).sectors)
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
LAST_WEEK = "2019-12-13"  # last In-Sample signal week (contract 7)
FIRST_WEEK = "2014-01-03"  # first Friday of 2014, the first synthetic test year
SUMMARY_KEYS = {"name", "rung", "spec_hash", "refits", "rows", "weeks", "values", "nan_count", "first_week", "last_week",
                "column_sums", "min", "max", "spots", "scores_sha256"}
OUTPUT_FILES = ["scores.csv", "used.yaml", "summary.json"]
SYNTHETIC_SPOTS = (("2014-01-03", "XLB"), ("2015-06-12", "XLK"), ("2016-02-12", "XLE"), ("2018-10-12", "XLF"),
                   ("2019-12-13", "XLY"))


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script("train_walkforward_script", "05_train_walkforward.py")


@pytest.fixture(scope="module")
def script03():
    return load_script("build_features_script_walkforward", "03_build_features.py")


def synthetic_cfg() -> dict:
    """config.yaml with a warm-up and test years that fit the synthetic market (2011-2020); same In-Sample end."""
    cfg = copy.deepcopy(CFG)
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2013]
    cfg["split"]["test_years"] = [2014, 2019]
    cfg["tuning"]["inner_validation_weeks"] = 26
    return cfg


SYN_CFG = synthetic_cfg()
_BUILT: dict = {}


def build_data_dir(script03, market, data_dir: Path, lock: Path) -> None:
    """features.csv, market_states.csv, sizing_betas.csv, momentum_variants.csv, labels.csv, forward_returns.csv and
    features_config.yaml.
    """
    daily_close, daily_open = market.daily_close, market.daily_open
    daily_close = daily_close[daily_close.index <= IS_END]
    daily_open = daily_open[daily_open.index <= IS_END]
    vix = market.vix[market.vix.index <= IS_END]
    fred = market.fred[market.fred.index <= IS_END]
    tables = script03.build_tables(daily_close, vix, fred, SYN_CFG)
    labels = script03.build_labels(daily_open, daily_close, IS_END)
    forward = script03.build_forward_returns(daily_open, daily_close, IS_END)
    script03.write_tables({**tables, "labels": labels, "forward_returns": forward}, data_dir, IS_END, lock)
    save_used(features.features_settings(SYN_CFG), data_dir / "features_config.yaml")


def paths(root: Path, data_dir: Path) -> dict:
    return {"data_dir": data_dir, "out_dir": root / "out", "trial_path": root / "trial_log.csv",
            "log_path": root / "logs" / "vault_access_log.jsonl", "lock_path": root / "FROZEN.lock"}


def run_into(script, root: Path, data_dir: Path, **overrides) -> tuple[dict, dict]:
    where = {**paths(root, data_dir), **overrides}
    return script.run("M0", SYN_CFG, spots=SYNTHETIC_SPOTS, **where), where


@pytest.fixture
def built(script, script03, synthetic_market, tmp_path_factory) -> dict:
    """One synthetic data folder and one reference run, shared by the tests of this module (read-only)."""
    if not _BUILT:
        root = tmp_path_factory.mktemp("walkforward")
        data_dir = root / "processed"
        build_data_dir(script03, synthetic_market, data_dir, root / "FROZEN.lock")
        summary, where = run_into(script, root / "reference", data_dir)
        _BUILT.update(data_dir=data_dir, summary=summary, where=where)
    return _BUILT


def read_scores(out_dir: Path) -> pd.DataFrame:
    return pd.read_csv(out_dir / "scores.csv", index_col=[0, 1], parse_dates=[0, 1])


def read_trials(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def spec_hash(spec: dict, cfg: dict) -> str:
    """Trial hash of S23-6: canonical JSON of the spec and the walk-forward config sections."""
    keyed = {"config": {key: cfg[key] for key in ("seed", "data", "split", "execution", "features", "models")},
             "spec": spec}
    return hashlib.sha256(json.dumps(keyed, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- constants, spec and settings


def test_spots_are_the_five_values_fixed_before_the_run(script):
    assert tuple(script.SPOTS) == (("2008-01-04", "XLB"), ("2008-10-10", "XLF"), ("2012-06-01", "XLK"),
                                   ("2016-02-12", "XLE"), ("2019-12-13", "XLY"))


def test_model_spec_of_m0(script):
    assert script.model_spec("M0", CFG) == {"rung": "M0", "feature": CFG["models"]["M0"]["feature"],
                                            "author": "Eliya Allam", "kind": "human",
                                            "notes": "M0 In-Sample walk-forward (Phase 2.3a)"}


@pytest.mark.parametrize("rung", ["M1", "M2", "M3", "M0_star"])
def test_model_spec_of_a_tuned_rung_carries_the_tuning_spec(script, rung):
    """S31-2: a tuned rung's spec holds rung and tuning = src.models.tuning_spec(cfg), and neither params nor feature."""
    spec = script.model_spec(rung, CFG)
    assert spec["rung"] == rung and spec["tuning"] == models.tuning_spec(CFG)
    assert "params" not in spec and "feature" not in spec and spec["author"] == "Eliya Allam"


def test_model_spec_of_ens_names_its_members(script):
    spec = script.model_spec("ENS", CFG)
    assert spec["members"] == ["M1", "M2", "M3"] and spec["tuning"] == models.tuning_spec(CFG)


def test_model_spec_of_an_unknown_rung_is_refused(script):
    with pytest.raises(ValueError):
        script.model_spec("M5", CFG)


def test_fixed_names_follow_the_grids(script):
    """S31-10: one --fixed name per grid value, built from config.yaml."""
    assert script.fixed_names(CFG) == ["M1_a0.1", "M1_a1", "M1_a10", "M2_a0.1", "M2_a1", "M2_a10", "M3_d2", "M3_d3",
                                       "M0_L13", "M0_L26", "M0_L52"]


@pytest.mark.parametrize("name, params", [("M1_a0.1", {"alpha": 0.1}), ("M2_a10", {"alpha": 10}),
                                          ("M3_d2", {"max_depth": 2}), ("M3_d3", {"max_depth": 3})])
def test_fixed_spec_of_a_grid_value(script, name, params):
    spec = script.fixed_spec(name, CFG)
    assert spec["rung"] == name.split("_")[0] and spec["params"] == params and "tuning" not in spec


def test_fixed_m0_l26_is_the_m0_trial_itself(script):
    """S31-6: M0_L26 is exactly the M0 spec, so it has the M0 spec_hash and adds no trial row."""
    assert script.fixed_spec("M0_L26", CFG) == script.model_spec("M0", CFG)


@pytest.mark.parametrize("lookback", [13, 52])
def test_fixed_m0_lookbacks_use_the_momentum_variants(script, lookback):
    spec = script.fixed_spec(f"M0_L{lookback}", CFG)
    assert spec["rung"] == "M0" and spec["feature"] == f"MOM{lookback}_1"


def test_walkforward_settings_are_exactly_the_agreed_config_sections():
    """S23-5, S23-6: used.yaml holds exactly {seed, data, split, execution, features, models}, whole sections."""
    sections = ("seed", "data", "split", "execution", "features", "models")
    settings = models.walkforward_settings(CFG)
    assert set(settings) == set(sections)
    assert settings == {key: CFG[key] for key in sections}


def test_walkforward_settings_changes_with_the_split():
    assert models.walkforward_settings(SYN_CFG) != models.walkforward_settings(CFG)


@pytest.mark.parametrize("argv", [["--model", "M5"], ["--fixed", "M1_a5"], ["--model", "M1", "--fixed", "M1_a1"], []])
def test_main_refuses_unknown_names_and_needs_exactly_one_option(script, argv):
    """argparse refuses an unknown rung or fixed name, both options together, and neither (before any data access)."""
    with pytest.raises(SystemExit):
        script.main(argv)


# ---------------------------------------------------------------- the reference run on the synthetic market


def test_run_refits_quarterly_over_six_test_years(built):
    assert built["summary"]["refits"] == 24
    assert isinstance(built["summary"]["refits"], int)


def test_run_scores_the_test_weeks_from_2014_to_the_last_in_sample_week(built):
    summary = built["summary"]
    fridays = pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D")
    assert summary["first_week"] == FIRST_WEEK
    assert summary["last_week"] == LAST_WEEK
    assert summary["weeks"] == len(fridays)
    assert summary["rows"] == len(fridays)
    closes = pd.DatetimeIndex(read_scores(built["where"]["out_dir"]).index.get_level_values("date_close"))
    assert list(closes) == list(fridays)


def test_run_writes_no_score_after_the_last_in_sample_week(built):
    scores = read_scores(built["where"]["out_dir"])
    assert pd.DatetimeIndex(scores.index.get_level_values("date_close")).max() == pd.Timestamp(LAST_WEEK)
    assert pd.DatetimeIndex(scores.index.get_level_values("date_open")).max() < IS_END


def test_run_scores_pass_the_score_contract(built):
    scores = read_scores(built["where"]["out_dir"])
    assert list(scores.index.names) == ["date_open", "date_close"]
    assert list(scores.columns) == SECTORS
    contracts.validate_scores(scores)


def test_run_m0_scores_equal_the_mom26_1_feature(built):
    scores = read_scores(built["where"]["out_dir"])
    feats = pd.read_csv(built["data_dir"] / "features.csv", index_col=[0, 1], parse_dates=[0])
    expected = feats["MOM26_1"].unstack("ticker")[SECTORS]
    closes = pd.DatetimeIndex(scores.index.get_level_values("date_close"))
    np.testing.assert_allclose(scores.to_numpy(), expected.loc[closes].to_numpy(), rtol=1e-12, atol=1e-15)


def test_run_summary_counts(built):
    summary = built["summary"]
    scores = read_scores(built["where"]["out_dir"])
    assert summary["rung"] == "M0"
    assert summary["nan_count"] == 0
    assert summary["values"] == int(scores.notna().to_numpy().sum()) == 9 * summary["weeks"]


def test_run_summary_aggregates_match_scores_csv(built):
    summary = built["summary"]
    out_dir = built["where"]["out_dir"]
    scores = read_scores(out_dir)
    assert set(summary["column_sums"]) == set(SECTORS)
    for sector in SECTORS:
        np.testing.assert_allclose(summary["column_sums"][sector], scores[sector].sum(), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(summary["min"], np.nanmin(scores.to_numpy()), rtol=1e-15)
    np.testing.assert_allclose(summary["max"], np.nanmax(scores.to_numpy()), rtol=1e-15)
    assert summary["scores_sha256"] == hashlib.sha256((out_dir / "scores.csv").read_bytes()).hexdigest()


def test_run_summary_spots_match_the_scores(built):
    spots = built["summary"]["spots"]
    scores = read_scores(built["where"]["out_dir"]).droplevel("date_open")
    assert [(spot["date_close"], spot["ticker"]) for spot in spots] == [tuple(spot) for spot in SYNTHETIC_SPOTS]
    for spot in spots:
        expected = scores.loc[pd.Timestamp(spot["date_close"]), spot["ticker"]]
        np.testing.assert_allclose(spot["score"], expected, rtol=1e-15)


def test_run_summary_spec_hash_is_the_canonical_json_hash(script, built):
    assert built["summary"]["spec_hash"] == spec_hash(script.model_spec("M0", SYN_CFG), SYN_CFG)


def test_run_summary_has_exactly_the_listed_keys_and_no_timestamp(built):
    out_dir = built["where"]["out_dir"]
    on_disk = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert set(on_disk) == SUMMARY_KEYS
    assert on_disk == json.loads(json.dumps(built["summary"]))


def test_run_summary_json_has_sorted_keys_and_lf(built):
    content = (built["where"]["out_dir"] / "summary.json").read_bytes()
    assert b"\r\n" not in content
    keys = json.loads(content, object_pairs_hook=lambda pairs: [key for key, _ in pairs])
    assert keys == sorted(keys)


def test_run_used_yaml_is_the_walkforward_settings(built):
    used = built["where"]["out_dir"] / "used.yaml"
    check_used(models.walkforward_settings(SYN_CFG), used, "05_train_walkforward.py")
    with open(used, encoding="utf-8") as f:
        assert set(yaml.safe_load(f)) == {"seed", "data", "split", "execution", "features", "models"}


def test_run_logs_one_trial_row(built):
    rows = read_trials(built["where"]["trial_path"])
    assert len(rows) == 1
    assert rows[0]["rung"] == "M0"
    assert rows[0]["author"] == "Eliya Allam"
    assert rows[0]["kind"] == "human"


# ---------------------------------------------------------------- determinism and the trial log (S23-2)


def test_run_twice_gives_byte_identical_files(script, built, tmp_path):
    _, first = run_into(script, tmp_path / "a", built["data_dir"])
    before = {name: (first["out_dir"] / name).read_bytes() for name in OUTPUT_FILES}
    run_into(script, tmp_path / "a", built["data_dir"])
    _, other = run_into(script, tmp_path / "b", built["data_dir"])
    for name in OUTPUT_FILES:
        assert (first["out_dir"] / name).read_bytes() == before[name]
        assert (other["out_dir"] / name).read_bytes() == before[name]
        assert (built["where"]["out_dir"] / name).read_bytes() == before[name]


def test_run_twice_logs_one_trial_row(script, built, tmp_path):
    first, where = run_into(script, tmp_path, built["data_dir"])
    second, _ = run_into(script, tmp_path, built["data_dir"])
    assert first == second
    rows = read_trials(where["trial_path"])
    assert len(rows) == 1


def test_a_different_spec_adds_a_second_trial_row(script, built, tmp_path):
    _, where = run_into(script, tmp_path, built["data_dir"])
    vault = Vault(IS_END, lock_path=where["lock_path"], log_path=where["log_path"], data_dir=built["data_dir"],
                  cfg=SYN_CFG)
    other = {**script.model_spec("M0", SYN_CFG), "notes": "M0 rerun with other notes"}
    vault.run_walkforward(other, trial_path=where["trial_path"])
    assert len(read_trials(where["trial_path"])) == 2
    vault.run_walkforward(other, trial_path=where["trial_path"])
    assert len(read_trials(where["trial_path"])) == 2


# ---------------------------------------------------------------- check_used refusals


def test_run_refuses_a_data_folder_built_with_other_settings(script, built, tmp_path):
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    for name in ["features.csv", "market_states.csv", "labels.csv", "momentum_variants.csv"]:
        (data_dir / name).write_bytes((built["data_dir"] / name).read_bytes())
    other = copy.deepcopy(SYN_CFG)
    other["execution"]["type"] = "close_to_close"
    save_used(features.features_settings(other), data_dir / "features_config.yaml")
    with pytest.raises(ValueError):
        run_into(script, tmp_path, data_dir)
    assert not (tmp_path / "out" / "scores.csv").exists()
    assert not (tmp_path / "trial_log.csv").exists()


def test_run_refuses_a_data_folder_without_features_config(script, built, tmp_path):
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    for name in ["features.csv", "market_states.csv", "labels.csv", "momentum_variants.csv"]:
        (data_dir / name).write_bytes((built["data_dir"] / name).read_bytes())
    with pytest.raises(FileNotFoundError):
        run_into(script, tmp_path, data_dir)
    assert not (tmp_path / "out" / "scores.csv").exists()


# ---------------------------------------------------------------- the ladder on the synthetic market (S31-10)


def run_name(script, name: str, root: Path, data_dir: Path) -> tuple[dict, dict]:
    where = paths(root, data_dir)
    return script.run(name, SYN_CFG, spots=SYNTHETIC_SPOTS, **where), where


@pytest.fixture
def tuned_m1(script, built, tmp_path_factory) -> dict:
    """One tuned M1 run on the synthetic data folder (shared, read-only)."""
    if "tuned_m1" not in _BUILT:
        root = tmp_path_factory.mktemp("tuned_m1")
        summary, where = run_name(script, "M1", root, built["data_dir"])
        _BUILT["tuned_m1"] = {"summary": summary, "where": where}
    return _BUILT["tuned_m1"]


def test_tuned_run_writes_selection_csv_with_one_row_per_refit(tuned_m1):
    """selection.csv: 24 refits, the S31-10 columns, the chosen value in the grid with the best inner Sharpe."""
    selection = pd.read_csv(tuned_m1["where"]["out_dir"] / "selection.csv")
    assert len(selection) == 24
    sharpes = ["sharpe_0.1", "sharpe_1", "sharpe_10"]
    assert list(selection.columns) == ["test_year", "refit", "test_start", "train_start", "train_end", "purge_end",
                                       "inner_train_end", "inner_purge_end", "inner_val_start", "inner_val_end",
                                       "inner_val_weeks"] + sharpes + ["chosen"]
    assert (selection["inner_val_weeks"] == 26).all()
    assert set(selection["chosen"]) <= {0.1, 1.0, 10.0}
    best = selection[sharpes].max(axis=1)
    picked = [row[f"sharpe_{format(row['chosen'], 'g')}"] for _, row in selection.iterrows()]
    np.testing.assert_allclose(picked, best, rtol=0, atol=1e-12)
    assert (pd.to_datetime(selection["inner_val_end"]) == pd.to_datetime(selection["train_end"])).all()
    assert (pd.to_datetime(selection["inner_purge_end"]) == pd.to_datetime(selection["inner_val_start"])
            - pd.Timedelta(days=7)).all()


def test_tuned_run_logs_one_m1_trial_and_writes_the_standard_outputs(tuned_m1):
    where = tuned_m1["where"]
    for name in OUTPUT_FILES:
        assert (where["out_dir"] / name).exists()
    rows = read_trials(where["trial_path"])
    assert [row["rung"] for row in rows] == ["M1"]
    assert tuned_m1["summary"]["name"] == "M1" and tuned_m1["summary"]["refits"] == 24
    contracts.validate_scores(read_scores(where["out_dir"]).astype(np.float64))


def test_tuned_scores_equal_the_fixed_scores_at_the_chosen_value(script, built, tuned_m1, tmp_path):
    """Each refit of the tuned run scores its test weeks exactly like the fixed run at the value it chose."""
    selection = pd.read_csv(tuned_m1["where"]["out_dir"] / "selection.csv", parse_dates=["test_start"])
    tuned = read_scores(tuned_m1["where"]["out_dir"])
    closes = pd.DatetimeIndex(tuned.index.get_level_values("date_close"))
    starts = list(selection["test_start"]) + [closes.max() + pd.Timedelta(days=7)]
    fixed = {}
    for value in sorted(set(selection["chosen"])):
        _, where = run_name(script, f"M1_a{format(value, 'g')}", tmp_path / format(value, "g"), built["data_dir"])
        fixed[value] = read_scores(where["out_dir"])
    for k, row in selection.iterrows():
        weeks = np.asarray((closes >= starts[k]) & (closes < starts[k + 1]))
        pd.testing.assert_frame_equal(tuned.loc[weeks], fixed[row["chosen"]].loc[weeks])


def test_fixed_m0_l26_adds_no_trial_row_and_equals_m0(script, built, tmp_path):
    """S31-6: after the M0 run, M0_L26 writes the same scores with the same spec_hash and no new trial row."""
    m0, where = run_name(script, "M0", tmp_path / "m0", built["data_dir"])
    l26 = script.run("M0_L26", SYN_CFG, spots=SYNTHETIC_SPOTS, **{**where, "out_dir": tmp_path / "l26"})
    assert l26["spec_hash"] == m0["spec_hash"] and l26["scores_sha256"] == m0["scores_sha256"]
    assert l26["name"] == "M0_L26" and l26["rung"] == "M0"
    assert len(read_trials(where["trial_path"])) == 1
    assert not (tmp_path / "l26" / "selection.csv").exists()


def test_ens_run_writes_no_selection_and_ranks_in_one_to_nine(script, built, tmp_path):
    """ENS scores are mean ranks (between 1 and 9, summing to 45 per week); no selection.csv; one ENS trial row."""
    summary, where = run_name(script, "ENS", tmp_path, built["data_dir"])
    scores = read_scores(where["out_dir"])
    assert not (where["out_dir"] / "selection.csv").exists()
    values = scores.to_numpy()
    assert np.nanmin(values) >= 1 and np.nanmax(values) <= 9
    np.testing.assert_allclose(np.nansum(values, axis=1), 45.0, rtol=0, atol=1e-12)
    assert [row["rung"] for row in read_trials(where["trial_path"])] == ["ENS"]
    assert summary["name"] == "ENS"
