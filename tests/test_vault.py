"""The vault of src/vault.py (§10, contract 15, S22-8): sealed OOS, access log, unlock path, walk-forward and trial log.

Every test uses a temporary lock file, access log and trial log, and in-memory frames built here by hand on a
business-day calendar 2001-2020 (no real data). Nothing touches FROZEN.lock, outputs/ or docs/trial_log.csv.
"""

import copy
import csv
import hashlib
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src import contracts, models
from src.backtest import forward_returns
from src.config import load_config
from src.data import write_csv
from src.models import walkforward_settings
from src.vault import OOSAccessError, Vault, append_trial, logged_spec_hashes
from src.vault import spec_hash as vault_spec_hash

CFG = load_config()
UNIVERSE = contracts.universe(CFG)
SECTORS = list(UNIVERSE.sectors)
TRADED = list(UNIVERSE.traded)
ASSET = list(CFG["features"]["asset"])
STATES = list(CFG["features"]["states"])
VARIANTS = [f"MOM{lookback}_1" for lookback in CFG["models"]["M0_star"]["lookback_weeks"]]
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
OOS_START = pd.Timestamp(CFG["split"]["oos_start"])  # Mon 2019-12-30
TRIAL_COLUMNS = ["trial_id", "timestamp", "author", "kind", "rung", "spec_hash", "params_json", "is_sharpe", "is_mdd", "notes"]
DAY = pd.Timedelta(days=1)
# a few Monday holidays and Good Fridays, so first sessions and last sessions differ from the nominal dates
HOLIDAYS = ["2007-12-24", "2008-01-21", "2008-03-21", "2012-04-06", "2015-09-07", "2019-01-21", "2019-12-23", "2019-12-25"]


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


def build_frames() -> dict[str, pd.DataFrame]:
    """Features, market states, labels, momentum variants and sizing betas (contracts 3, 4, 6, 10) on weeks 2001-2020."""
    sessions = pd.bdate_range("2001-01-01", "2020-12-31").difference(pd.DatetimeIndex(HOLIDAYS))
    fridays = pd.DatetimeIndex(np.unique((sessions + pd.to_timedelta(4 - sessions.day_of_week, unit="D")).values))
    weeks = pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])
    rows = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(21)
    features = pd.DataFrame(rng.normal(size=(len(rows), len(ASSET))), index=rows, columns=ASSET)
    variants = pd.DataFrame(rng.normal(size=(len(rows), len(VARIANTS))), index=rows, columns=VARIANTS)
    variants["MOM26_1"] = features["MOM26_1"]  # identical whichever frame MOM26_1 is read from
    states = pd.DataFrame({
        "BEAR24": (rng.random(len(weeks)) < 0.2).astype(np.float64),
        "MKT_VAR": rng.uniform(1e-5, 4e-4, len(weeks)),
        "VIX": rng.uniform(10, 40, len(weeks)),
        "TERM": rng.normal(1.5, 1.0, len(weeks)),
        "CREDIT": rng.uniform(1.5, 4.0, len(weeks)),
    }, index=weeks)[STATES]
    opens = pd.DatetimeIndex(weeks.get_level_values("date_open"))
    label_end = [sessions[sessions.searchsorted(opens[r + 2])] for r in range(len(weeks) - 2)]
    labelled = rows[: 9 * (len(weeks) - 2)]
    raw_y = rng.normal(size=(len(weeks) - 2, len(SECTORS)))
    y = (raw_y - raw_y.mean(axis=1, keepdims=True)).ravel()
    labels = pd.DataFrame({"y": y, "label_end": pd.DatetimeIndex(np.repeat(np.array(label_end, dtype="datetime64[ns]"), 9))},
                          index=labelled)
    contracts.validate_features(features)
    contracts.validate_features(variants, columns=VARIANTS)
    contracts.validate_market_states(states)
    betas = pd.DataFrame(rng.uniform(0.5, 1.5, (len(weeks), len(TRADED))), index=weeks, columns=TRADED)
    betas.iloc[:52] = np.nan  # BETA52 warm-up
    contracts.validate_labels(labels)
    contracts.validate_betas(betas)
    in_sample = weeks[np.asarray(fridays <= IS_END)]
    opens_weekly = pd.DataFrame(np.exp(np.cumsum(rng.normal(0, 0.02, (len(in_sample), len(UNIVERSE.tradables))), axis=0)),
                                index=in_sample, columns=list(UNIVERSE.tradables))
    fwd, realised_on, period = forward_returns(opens_weekly, is_end=IS_END)
    fwd_table = fwd.copy()
    fwd_table["realised_on"], fwd_table["period"] = realised_on, period
    return {"features": features, "market_states": states, "labels": labels, "momentum_variants": variants,
            "sizing_betas": betas, "forward_returns": fwd_table}


FRAMES = build_frames()


@pytest.fixture
def env(tmp_path):
    paths = {"lock": tmp_path / "FROZEN.lock", "log": tmp_path / "logs" / "vault_access_log.jsonl",
             "trials": tmp_path / "trial_log.csv"}
    frames = {name: frame.copy() for name, frame in FRAMES.items()}
    vault = Vault(IS_END, lock_path=paths["lock"], log_path=paths["log"], frames=frames, cfg=CFG)
    return vault, paths


def log_lines(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def trial_rows(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def spec_hash(spec: dict, cfg: dict = CFG) -> tuple[str, str]:
    """(trial hash over the spec and the config sections (S23-6), params_json = the spec's canonical JSON)."""
    text = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    keyed = json.dumps({"config": walkforward_settings(cfg), "spec": spec}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(keyed.encode("utf-8")).hexdigest(), text


def closes_of(frame: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


# ---------------------------------------------------------------- sealed OOS


@pytest.mark.parametrize("method", ["features", "market_states", "labels"])
@pytest.mark.parametrize("as_of", ["2019-12-30", "2020-01-03", "2020-06-30"])
def test_oos_dates_are_refused_and_logged(env, method, as_of):
    vault, paths = env
    with pytest.raises(OOSAccessError):
        getattr(vault, method)(ts(as_of))
    last = log_lines(paths["log"])[-1]
    assert last["result"] == "refused"
    assert last["method"] == method
    assert last["as_of"] == as_of
    assert issubclass(OOSAccessError, PermissionError)


@pytest.mark.parametrize("method", ["features", "market_states", "labels"])
def test_in_sample_end_is_allowed_and_logged_ok(env, method):
    vault, paths = env
    getattr(vault, method)(IS_END)
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == (method, "2019-12-27", "ok")
    datetime.fromisoformat(last["utc"])  # an ISO-8601 time stamp


def test_features_and_states_rows_up_to_as_of(env):
    vault, _ = env
    as_of = ts("2015-06-10")
    got = vault.features(as_of)
    expected = FRAMES["features"][closes_of(FRAMES["features"]) <= as_of]
    assert got.index.equals(expected.index)
    np.testing.assert_allclose(got[ASSET].to_numpy(), expected.to_numpy(), rtol=0, atol=0)
    states = vault.market_states(as_of)
    expected_states = FRAMES["market_states"][closes_of(FRAMES["market_states"]) <= as_of]
    assert states.index.equals(expected_states.index)
    np.testing.assert_allclose(states[STATES].to_numpy(), expected_states.to_numpy(), rtol=0, atol=0)


@pytest.mark.parametrize("as_of", ["2015-06-10", "2019-12-27", "2008-01-02"])
def test_labels_never_return_a_label_end_after_as_of(env, as_of):
    vault, _ = env
    got = vault.labels(ts(as_of))
    assert (pd.DatetimeIndex(got["label_end"]) <= ts(as_of)).all()
    expected = FRAMES["labels"][pd.DatetimeIndex(FRAMES["labels"]["label_end"]) <= ts(as_of)]
    assert len(got) == len(expected)
    assert got.index.equals(expected.index)


def test_every_call_is_logged_in_order(env):
    vault, paths = env
    before = len(log_lines(paths["log"])) if paths["log"].exists() else 0
    vault.features(ts("2010-01-08"))
    with pytest.raises(OOSAccessError):
        vault.labels(OOS_START)
    vault.market_states(ts("2011-01-07"))
    lines = log_lines(paths["log"])[before:]
    assert [(line["method"], line["result"]) for line in lines] == [("features", "ok"), ("labels", "refused"),
                                                                     ("market_states", "ok")]
    assert all(set(line) >= {"utc", "method", "result"} for line in lines)


# ---------------------------------------------------------------- unlock path


def test_unlock_without_the_lock_file_raises_and_is_logged(env):
    vault, paths = env
    with pytest.raises(OOSAccessError):
        vault.unlock()
    last = log_lines(paths["log"])[-1]
    assert last["method"] == "unlock" and last["result"] == "refused"
    with pytest.raises(OOSAccessError):
        vault.features(ts("2020-01-03"))


def test_lock_file_alone_does_not_open_the_vault(env):
    vault, paths = env
    paths["lock"].write_text("signed\n", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        vault.features(ts("2020-01-03"))


def test_lock_file_and_unlock_allow_later_dates(env):
    vault, paths = env
    paths["lock"].write_text("signed\n", encoding="utf-8")
    vault.unlock()
    assert log_lines(paths["log"])[-1]["method"] == "unlock"
    assert log_lines(paths["log"])[-1]["result"] == "ok"
    got = vault.features(ts("2020-06-26"))
    assert closes_of(got).max() == ts("2020-06-26")
    labels = vault.labels(ts("2020-06-30"))
    assert pd.DatetimeIndex(labels["label_end"]).max() <= ts("2020-06-30")
    assert pd.DatetimeIndex(labels["label_end"]).max() > IS_END
    assert vault.market_states(ts("2020-03-06")).index.get_level_values("date_close").max() == ts("2020-03-06")


def test_vault_reads_csv_files_from_data_dir(tmp_path):
    data_dir = tmp_path / "processed"
    write_csv(FRAMES["features"], data_dir / "features.csv")
    write_csv(FRAMES["market_states"], data_dir / "market_states.csv")
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", data_dir=data_dir, cfg=CFG)
    as_of = ts("2012-03-09")
    got = vault.features(as_of)
    expected = FRAMES["features"][closes_of(FRAMES["features"]) <= as_of]
    assert list(closes_of(got)) == list(closes_of(expected))
    assert list(got.index.get_level_values("ticker")) == list(expected.index.get_level_values("ticker"))
    np.testing.assert_allclose(got[ASSET].to_numpy(dtype=np.float64), expected.to_numpy(), rtol=1e-15, atol=0)
    states = vault.market_states(as_of)
    np.testing.assert_allclose(states[STATES].to_numpy(dtype=np.float64),
                               FRAMES["market_states"][closes_of(FRAMES["market_states"]) <= as_of].to_numpy(), rtol=1e-15)


# ---------------------------------------------------------------- sizing betas (S23-4)


def test_sizing_betas_returns_rows_up_to_as_of_and_logs_ok(env):
    vault, paths = env
    as_of = ts("2015-06-05")
    got = vault.sizing_betas(as_of)
    contracts.validate_betas(got)
    expected = FRAMES["sizing_betas"][closes_of(FRAMES["sizing_betas"]) <= as_of]
    pd.testing.assert_frame_equal(got, expected, check_exact=True)
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == ("sizing_betas", "2015-06-05", "ok")


def test_sizing_betas_at_the_in_sample_end_stops_there(env):
    vault, _ = env
    assert closes_of(vault.sizing_betas(IS_END)).max() == IS_END


@pytest.mark.parametrize("day", ["2019-12-28", "2019-12-30", "2020-01-03", "2026-10-16"])
def test_sizing_betas_after_the_in_sample_end_is_refused_and_logged(env, day):
    vault, paths = env
    with pytest.raises(OOSAccessError):
        vault.sizing_betas(ts(day))
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == ("sizing_betas", day, "refused")


def test_sizing_betas_after_the_in_sample_end_is_refused_with_the_lock_but_without_unlock(env):
    vault, paths = env
    paths["lock"].write_text("signed\n", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        vault.sizing_betas(ts("2020-01-03"))


def test_sizing_betas_open_after_lock_and_unlock(env):
    vault, paths = env
    paths["lock"].write_text("signed\n", encoding="utf-8")
    vault.unlock()
    assert closes_of(vault.sizing_betas(ts("2020-06-26"))).max() == ts("2020-06-26")


def test_sizing_betas_failing_validation_is_refused_and_logged(tmp_path):
    frames = {name: frame.copy() for name, frame in FRAMES.items()}
    frames["sizing_betas"] = frames["sizing_betas"].drop(columns=["IVV"])
    log = tmp_path / "log.jsonl"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, frames=frames, cfg=CFG)
    with pytest.raises(contracts.ContractError):
        vault.sizing_betas(ts("2015-06-05"))
    assert log_lines(log)[-1]["result"] == "refused"


def test_sizing_betas_read_from_csv_in_data_dir(tmp_path):
    data_dir = tmp_path / "processed"
    write_csv(FRAMES["sizing_betas"], data_dir / "sizing_betas.csv")
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", data_dir=data_dir, cfg=CFG)
    got = vault.sizing_betas(ts("2012-03-09"))
    expected = FRAMES["sizing_betas"][closes_of(FRAMES["sizing_betas"]) <= ts("2012-03-09")]
    assert list(got.index) == list(expected.index)
    assert all(got[column].dtype == np.float64 for column in TRADED)
    np.testing.assert_array_equal(got.to_numpy(), expected.to_numpy())


# ---------------------------------------------------------------- run_walkforward and the trial log


def expected_m0_scores(column: str, frame: str = "features") -> pd.DataFrame:
    values = FRAMES[frame][column].unstack("ticker")[SECTORS]
    return values[(values.index >= ts("2008-01-04")) & (values.index <= ts("2019-12-13"))]


def test_run_walkforward_m0_scores_and_one_trial_row(env):
    vault, paths = env
    spec = {"rung": "M0"}
    scores = vault.run_walkforward(spec, trial_path=paths["trials"])
    contracts.validate_scores(scores)
    expected = expected_m0_scores("MOM26_1")
    assert list(closes_of(scores)) == list(expected.index)
    assert (pd.DatetimeIndex(scores.index.get_level_values("date_open")) == closes_of(scores) - 4 * DAY).all()
    np.testing.assert_allclose(scores.to_numpy(), expected.to_numpy(), rtol=0, atol=0)
    rows = trial_rows(paths["trials"])
    assert len(rows) == 1
    digest, text = spec_hash(spec)
    assert list(rows[0]) == TRIAL_COLUMNS
    assert rows[0]["rung"] == "M0"
    assert rows[0]["spec_hash"] == digest
    assert rows[0]["params_json"] == text
    assert rows[0]["is_sharpe"] == "" and rows[0]["is_mdd"] == ""
    assert rows[0]["trial_id"] == "1"
    last = log_lines(paths["log"])[-1]
    assert last["result"] == "ok" and last["spec_hash"] == digest


def test_run_walkforward_momentum_variant_and_evaluator(env):
    vault, paths = env
    spec = {"rung": "M0", "feature": "MOM13_1", "author": "Eliya", "kind": "human", "notes": "variant check"}
    seen = []

    def evaluate(scores):
        seen.append(scores)
        return 0.75, -0.125

    scores = vault.run_walkforward(spec, evaluate=evaluate, trial_path=paths["trials"])
    np.testing.assert_allclose(scores.to_numpy(), expected_m0_scores("MOM13_1", "momentum_variants").to_numpy(), rtol=0, atol=0)
    assert len(seen) == 1
    vault.run_walkforward({"rung": "M0"}, trial_path=paths["trials"])
    rows = trial_rows(paths["trials"])
    assert [row["trial_id"] for row in rows] == ["1", "2"]
    assert float(rows[0]["is_sharpe"]) == 0.75 and float(rows[0]["is_mdd"]) == -0.125
    assert rows[0]["author"] == "Eliya" and rows[0]["kind"] == "human" and rows[0]["notes"] == "variant check"
    assert rows[0]["spec_hash"] == spec_hash(spec)[0]


def test_rerun_of_the_same_spec_adds_no_trial_row(env):
    """S23-2: one trial row per distinct spec_hash; the rerun still returns identical scores and is logged ok."""
    vault, paths = env
    spec = {"rung": "M0", "author": "Eliya", "kind": "human", "notes": "first"}
    first = vault.run_walkforward(spec, trial_path=paths["trials"])
    second = vault.run_walkforward(dict(reversed(list(spec.items()))), trial_path=paths["trials"])
    pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert len(trial_rows(paths["trials"])) == 1
    last = log_lines(paths["log"])[-1]
    assert last["method"] == "run_walkforward" and last["result"] == "ok" and last["spec_hash"] == spec_hash(spec)[0]
    vault.run_walkforward(spec | {"notes": "second"}, trial_path=paths["trials"])
    rows = trial_rows(paths["trials"])
    assert [row["trial_id"] for row in rows] == ["1", "2"]
    assert [row["notes"] for row in rows] == ["first", "second"]


def test_logged_spec_hashes_reads_the_trial_log(tmp_path):
    path = tmp_path / "trials.csv"
    assert logged_spec_hashes(path) == set()
    append_trial({"rung": "M0", "spec_hash": "abc"}, path=path)
    append_trial({"rung": "M0", "spec_hash": "def"}, path=path)
    assert logged_spec_hashes(path) == {"abc", "def"}


def test_public_spec_hash_matches_the_trial_log_hash():
    spec = {"rung": "M0", "feature": "MOM26_1", "notes": "x"}
    assert vault_spec_hash(spec, CFG) == spec_hash(spec)[0]
    assert vault_spec_hash(dict(reversed(list(spec.items()))), CFG) == spec_hash(spec)[0]


def test_spec_hash_covers_every_walkforward_config_section():
    """S23-6: changing any section of walkforward_settings changes the trial identity; other sections do not."""
    spec = {"rung": "M0"}
    base = vault_spec_hash(spec, CFG)
    for section in ("seed", "data", "split", "execution", "features", "models"):
        changed = copy.deepcopy(CFG)
        changed[section] = {"changed": True} if isinstance(CFG[section], dict) else CFG[section] + 1
        assert vault_spec_hash(spec, changed) != base, section
    other = copy.deepcopy(CFG)
    other["costs"] = {"bps_baseline": 99}
    assert vault_spec_hash(spec, other) == base


def test_same_spec_under_a_changed_config_is_a_new_trial(tmp_path):
    """S23-6: a rerun with an identical spec but a changed walk-forward config section appends a second row."""
    frames = {name: frame.copy() for name, frame in FRAMES.items()}
    trials, log = tmp_path / "trials.csv", tmp_path / "log.jsonl"
    spec = {"rung": "M0"}
    Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, frames=frames, cfg=CFG).run_walkforward(
        spec, trial_path=trials)
    changed = copy.deepcopy(CFG)
    changed["seed"] = CFG["seed"] + 1
    Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, frames=frames, cfg=changed).run_walkforward(
        spec, trial_path=trials)
    rows = trial_rows(trials)
    assert [row["trial_id"] for row in rows] == ["1", "2"]
    assert rows[0]["spec_hash"] == spec_hash(spec)[0] and rows[1]["spec_hash"] == spec_hash(spec, changed)[0]
    assert rows[0]["params_json"] == rows[1]["params_json"] == spec_hash(spec)[1]


@pytest.mark.parametrize("key", ["as_of", "end"])
def test_run_walkforward_refuses_a_spec_reaching_past_the_in_sample_end(env, key):
    vault, paths = env
    with pytest.raises(OOSAccessError):
        vault.run_walkforward({"rung": "M0", key: "2020-03-06"}, trial_path=paths["trials"])
    assert log_lines(paths["log"])[-1]["result"] == "refused"
    assert not paths["trials"].exists() or trial_rows(paths["trials"]) == []


@pytest.mark.parametrize("rung", ["M5", "M4", "M9"])
def test_run_walkforward_unknown_rung_is_refused_and_logged(env, rung):
    """A rung outside the implemented ladder (M5 arrives in Phase 3.3) is refused, logged and adds no trial."""
    vault, paths = env
    with pytest.raises(ValueError, match="unknown rung"):
        vault.run_walkforward({"rung": rung}, trial_path=paths["trials"])
    assert log_lines(paths["log"])[-1]["result"] == "refused"
    assert not paths["trials"].exists()


@pytest.mark.parametrize("spec", [
    {"rung": "M1"},  # neither params nor tuning
    {"rung": "M1", "params": {"alpha": 1}, "tuning": "x"},  # both
    {"rung": "M1", "params": {"alpha": 5}},  # outside the grid
    {"rung": "M1", "params": {"alpha": 1.0}},  # the grid value 1 with another type: another spec_hash (S31-12)
    {"rung": "M1", "params": {"alpha": True}},
    {"rung": "M3", "params": {"max_depth": 2.0}},
    {"rung": "M1", "params": {"max_depth": 2}},  # the wrong key
    {"rung": "M3", "params": {"max_depth": 4}},
    {"rung": "M2", "tuning": {"rule": "something else"}},  # differs from tuning_spec
    {"rung": "M0", "params": {"alpha": 1}},
    {"rung": "M1", "params": {"alpha": 1}, "feature": "MOM26_1"},
    {"rung": "M0_star"},
    {"rung": "ENS", "members": ["M1", "M2"]},
    {"rung": "M1", "params": {"alpha": 1}, "members": ["M1"]},
])
def test_run_walkforward_refuses_ladder_specs_that_do_not_fit_their_rung(env, spec):
    """S31-2: params, tuning, feature and members must fit the rung and the pre-registered grids."""
    vault, paths = env
    if spec.get("rung") == "ENS":
        spec = dict(spec, tuning=models.tuning_spec(CFG))
    with pytest.raises(ValueError):
        vault.run_walkforward(spec, trial_path=paths["trials"])
    assert log_lines(paths["log"])[-1]["result"] == "refused"
    assert not paths["trials"].exists()


def test_run_walkforward_fixed_ridge_value_logs_one_trial_and_no_selection(env):
    """A fixed M1 grid value scores the 2008-2019 test weeks, adds one trial row with rung M1 and leaves no selection."""
    vault, paths = env
    spec = {"rung": "M1", "params": {"alpha": 10}, "author": "Eliya Allam", "kind": "human", "notes": "fixed"}
    scores = vault.run_walkforward(spec, trial_path=paths["trials"])
    contracts.validate_scores(scores)
    closes = closes_of(scores)
    assert closes.min().year == 2008 and closes.max() <= IS_END
    assert np.isfinite(scores.to_numpy()).all()
    assert vault.last_selection is None
    rows = trial_rows(paths["trials"])
    assert [row["rung"] for row in rows] == ["M1"]
    assert rows[0]["spec_hash"] == spec_hash(spec)[0]


def test_run_walkforward_tuned_m0_star_sets_last_selection(env):
    """A tuned M0* run leaves one selection row per refit and scores each fold with the chosen lookback's variant."""
    vault, paths = env
    spec = {"rung": "M0_star", "tuning": models.tuning_spec(CFG), "author": "Eliya Allam", "kind": "human"}
    scores = vault.run_walkforward(spec, trial_path=paths["trials"])
    contracts.validate_scores(scores)
    selection = vault.last_selection
    assert len(selection) == 48
    assert set(selection["chosen"]) <= {13, 26, 52}
    assert {"sharpe_13", "sharpe_26", "sharpe_52", "inner_val_weeks"} <= set(selection.columns)
    assert (selection["inner_val_weeks"] == CFG["tuning"]["inner_validation_weeks"]).all()
    assert (pd.DatetimeIndex(selection["inner_val_end"]) == pd.DatetimeIndex(selection["train_end"])).all()
    by_close = scores.set_axis(closes_of(scores))
    for _, row in selection.iterrows():
        variant = FRAMES["momentum_variants"][f"MOM{row['chosen']}_1"]
        expected = variant.xs(row["test_start"], level="date_close").reindex(SECTORS).to_numpy()
        np.testing.assert_array_equal(by_close.loc[row["test_start"]].to_numpy(), expected)
    assert trial_rows(paths["trials"])[0]["rung"] == "M0_star"
    vault.run_walkforward({"rung": "M0"}, trial_path=paths["trials"])
    assert vault.last_selection is None  # the table of the last call only


# ---------------------------------------------------------------- forward returns (S31-1)


@pytest.mark.parametrize("as_of", ["2008-06-30", "2019-12-23", "2019-12-27"])
def test_forward_returns_only_rows_realised_by_as_of(env, as_of):
    """forward_returns(as_of) returns (fwd, realised_on, period) for returns realised on or before as_of only."""
    vault, paths = env
    fwd, realised_on, period = vault.forward_returns(ts(as_of))
    assert (realised_on <= ts(as_of)).all() and not realised_on.isna().any()
    table = FRAMES["forward_returns"]
    keep = table["realised_on"].notna().to_numpy() & (table["realised_on"] <= ts(as_of)).to_numpy()
    pd.testing.assert_frame_equal(fwd, table.loc[keep, list(UNIVERSE.tradables)])
    assert fwd.index.equals(realised_on.index) and fwd.index.equals(period.index)
    assert set(period) == {"IS"}
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == ("forward_returns", as_of, "ok")


@pytest.mark.parametrize("day", ["2019-12-28", "2019-12-30", "2026-10-16"])
def test_forward_returns_after_the_in_sample_end_is_refused_and_logged(env, day):
    """The forward returns are sealed at the In-Sample end like every table (OOSAccessError, logged refused)."""
    vault, paths = env
    with pytest.raises(OOSAccessError):
        vault.forward_returns(ts(day))
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == ("forward_returns", day, "refused")


def test_forward_returns_refused_with_the_lock_but_without_unlock(env):
    """FROZEN.lock alone does not open the forward returns; only unlock() does."""
    vault, paths = env
    paths["lock"].write_text("frozen", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        vault.forward_returns(ts("2020-01-03"))


def test_forward_returns_table_with_an_oos_realisation_is_refused(tmp_path):
    """A forward-returns table holding a return realised after the In-Sample end is refused on first read."""
    frames = {name: frame.copy() for name, frame in FRAMES.items()}
    weeks = FRAMES["market_states"].index[: closes_of(FRAMES["market_states"]).get_indexer([IS_END])[0] + 4]
    opens = pd.DataFrame(np.ones((len(weeks), len(UNIVERSE.tradables))), index=weeks, columns=list(UNIVERSE.tradables))
    fwd, realised_on, period = forward_returns(opens, is_end=IS_END)
    frames["forward_returns"] = fwd.assign(realised_on=realised_on, period=period)
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", frames=frames, cfg=CFG)
    with pytest.raises(OOSAccessError):
        vault.forward_returns(ts("2010-01-08"))
    assert log_lines(tmp_path / "log.jsonl")[-1]["result"] == "refused"


def test_forward_returns_read_from_csv_in_data_dir(tmp_path):
    """forward_returns.csv written with write_csv reads back with float64 returns, dates and IS/missing periods."""
    data_dir = tmp_path / "processed"
    for name, frame in FRAMES.items():
        write_csv(frame, data_dir / f"{name}.csv")
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", data_dir=data_dir, cfg=CFG)
    fwd, realised_on, _ = vault.forward_returns(IS_END)
    table = FRAMES["forward_returns"]
    expected = table.loc[table["realised_on"].notna().to_numpy()]
    np.testing.assert_allclose(fwd.to_numpy(), expected[list(UNIVERSE.tradables)].to_numpy(), rtol=1e-15, atol=0)
    assert (realised_on.to_numpy() == expected["realised_on"].to_numpy()).all()
    assert list(fwd.dtypes.unique()) == [np.dtype(np.float64)]


def test_append_trial_numbers_rows_and_fills_defaults(tmp_path):
    path = tmp_path / "trial_log.csv"
    append_trial({"rung": "M0", "spec_hash": "abc", "params_json": "{}"}, path=path)
    append_trial({"rung": "M1", "author": "Mattia", "kind": "human"}, path=path)
    append_trial({"trial_id": 7, "rung": "M2"}, path=path)
    rows = trial_rows(path)
    assert [row["trial_id"] for row in rows] == ["1", "2", "7"]
    assert list(rows[0]) == TRIAL_COLUMNS
    assert rows[0]["notes"] == "" and rows[0]["author"] == "" and rows[0]["is_sharpe"] == ""
    stamp = datetime.fromisoformat(rows[0]["timestamp"])
    assert stamp.utcoffset() is None or stamp.utcoffset().total_seconds() == 0
    content = path.read_bytes()
    assert b"\r\n" not in content
    assert content.decode("utf-8").count("trial_id,") == 1


def test_append_trial_writes_the_header_into_an_empty_file(tmp_path):
    path = tmp_path / "trial_log.csv"
    path.write_text("", encoding="utf-8")
    append_trial({"rung": "M0"}, path=path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(TRIAL_COLUMNS)
    assert len(lines) == 2


def test_append_trial_continues_a_file_with_a_header_only(tmp_path):
    path = tmp_path / "trial_log.csv"
    path.write_text(",".join(TRIAL_COLUMNS) + "\n", encoding="utf-8")
    append_trial({"rung": "M0"}, path=path)
    rows = trial_rows(path)
    assert len(rows) == 1 and rows[0]["trial_id"] == "1"


def test_append_trial_rejects_unknown_keys(tmp_path):
    path = tmp_path / "trial_log.csv"
    with pytest.raises(ValueError):
        append_trial({"rung": "M0", "sharpe": 1.0}, path=path)
    assert not path.exists() or trial_rows(path) == []


# ---------------------------------------------------------------- hardening (S22-12)


def test_is_end_after_the_configured_in_sample_end_is_refused(tmp_path):
    log = tmp_path / "log.jsonl"
    with pytest.raises(OOSAccessError):
        Vault(ts("2026-10-16"), lock_path=tmp_path / "FROZEN.lock", log_path=log, frames=FRAMES, cfg=CFG)
    assert log_lines(log)[-1]["result"] == "refused"


def test_a_failed_read_is_logged_as_refused(tmp_path):
    log = tmp_path / "log.jsonl"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, data_dir=tmp_path / "empty", cfg=CFG)
    with pytest.raises(FileNotFoundError):
        vault.features(IS_END)
    assert [(line["method"], line["result"]) for line in log_lines(log)] == [("features", "refused")]


def test_seal_refusal_is_logged_once(env):
    vault, paths = env
    with pytest.raises(OOSAccessError):
        vault.labels(OOS_START)
    assert len(log_lines(paths["log"])) == 1


@pytest.mark.parametrize("spec", [{"rung": "M0", "start": "2021-01-01"}, {"rung": "M0", "lookahead": 1}])
def test_run_walkforward_refuses_unknown_spec_keys(env, spec):
    vault, paths = env
    with pytest.raises(ValueError):
        vault.run_walkforward(spec, trial_path=paths["trials"])
    lines = log_lines(paths["log"])
    assert len(lines) == 1 and lines[0]["result"] == "refused" and lines[0]["spec_hash"] == spec_hash(spec)[0]
    assert not paths["trials"].exists()


def test_run_walkforward_unknown_feature_is_logged_as_refused(env):
    vault, paths = env
    with pytest.raises(ValueError):
        vault.run_walkforward({"rung": "M0", "feature": "MOM7_3"}, trial_path=paths["trials"])
    assert [line["result"] for line in log_lines(paths["log"])] == ["refused"]
