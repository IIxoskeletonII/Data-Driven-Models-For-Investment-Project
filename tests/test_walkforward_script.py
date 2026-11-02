"""05_train_walkforward.py (S23-2, S23-3): the M0 In-Sample walk-forward, its outputs, determinism and the trial log.

The script's module name starts with a digit, so it is loaded from its file, like 03_build_features.py. The data folder
is built here from the shared synthetic market (sessions 2011-01-03 to 2020-12-31) truncated at the In-Sample end, with
a copy of config.yaml whose warm-up ends in 2012 and whose test years are 2014-2019. Every path (data, outputs, lock,
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
SUMMARY_KEYS = {"rung", "spec_hash", "refits", "rows", "weeks", "values", "nan_count", "first_week", "last_week",
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
    return cfg


SYN_CFG = synthetic_cfg()
_BUILT: dict = {}


def build_data_dir(script03, market, data_dir: Path, lock: Path) -> None:
    """features.csv, market_states.csv, sizing_betas.csv, momentum_variants.csv, labels.csv and features_config.yaml."""
    daily_close, daily_open = market.daily_close, market.daily_open
    daily_close = daily_close[daily_close.index <= IS_END]
    daily_open = daily_open[daily_open.index <= IS_END]
    vix = market.vix[market.vix.index <= IS_END]
    fred = market.fred[market.fred.index <= IS_END]
    tables = script03.build_tables(daily_close, vix, fred, SYN_CFG)
    labels = script03.build_labels(daily_open, daily_close, IS_END)
    script03.write_tables({**tables, "labels": labels}, data_dir, IS_END, lock)
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


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- constants, spec and settings


def test_spots_are_the_five_values_fixed_before_the_run(script):
    assert tuple(script.SPOTS) == (("2008-01-04", "XLB"), ("2008-10-10", "XLF"), ("2012-06-01", "XLK"),
                                   ("2016-02-12", "XLE"), ("2019-12-13", "XLY"))


def test_model_spec_of_m0(script):
    assert script.model_spec("M0", CFG) == {"rung": "M0", "feature": CFG["models"]["M0"]["feature"],
                                            "author": "Eliya Allam", "kind": "human",
                                            "notes": "M0 In-Sample walk-forward (Phase 2.3a)"}


@pytest.mark.parametrize("rung", ["M1", "M2", "M3", "M5", "ENS"])
def test_model_spec_of_other_rungs_is_not_implemented(script, rung):
    with pytest.raises(NotImplementedError):
        script.model_spec(rung, CFG)


def test_walkforward_settings_are_exactly_the_agreed_config_sections():
    """S23-5: used.yaml holds exactly {seed, data, split, features, models}, each the whole config section."""
    settings = models.walkforward_settings(CFG)
    assert set(settings) == {"seed", "data", "split", "features", "models"}
    assert settings == {key: CFG[key] for key in ("seed", "data", "split", "features", "models")}


def test_walkforward_settings_changes_with_the_split():
    assert models.walkforward_settings(SYN_CFG) != models.walkforward_settings(CFG)


def test_main_accepts_only_m0(script):
    with pytest.raises(SystemExit):
        script.main(["--model", "M1"])


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
    assert built["summary"]["spec_hash"] == spec_hash(script.model_spec("M0", SYN_CFG))


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
        assert set(yaml.safe_load(f)) == {"seed", "data", "split", "features", "models"}


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
