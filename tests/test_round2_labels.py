"""The 4-week label of round 2 (Amendment 9 C1, decision S41-1): src.labels.make_horizon_labels,
03_build_features.py: build_horizon_labels, the writer's seal on labels_h4, the committed checksum file and
Vault.labels(as_of, horizon).

Inputs come from the shared synthetic market of contract 18 (sessions 2011-01-03 to 2020-12-31, US holidays) or are
small hand-made frames. Every expected value is recomputed here from the synthetic weekly opens. Lock files, access logs
and output folders are temporary; nothing touches FROZEN.lock, outputs/ or data/processed/.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import contracts
from src import labels as labels_mod
from src.backtest import forward_returns
from src.config import load_config
from src.data import weekly_panel
from src.vault import OOSAccessError, Vault

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
SECTORS = list(contracts.universe(CFG).sectors)
TRADED = list(contracts.universe(CFG).traded)
ASSET = list(CFG["features"]["asset"])
STATES = list(CFG["features"]["states"])
VARIANTS = [f"MOM{lookback}_1" for lookback in CFG["models"]["M0_star"]["lookback_weeks"]]
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
HORIZON = int(CFG["round2"]["label"]["horizon_weeks"])  # 4
LAST_H4_WEEK = pd.Timestamp("2019-11-22")  # its O(t+5) is the open of Mon 2019-12-23 (S41-1)
LAST_H4_END = pd.Timestamp("2019-12-23")
REFERENCE_COMMIT = "b8fc01a"  # main with Amendment 9 merged, before session 4.1 (S41-1)
ROUND1_CHECKSUM_ENTRIES = ["features.csv", "forward_returns.csv", "labels.csv", "market_states.csv",
                           "momentum_variants.csv", "sizing_betas.csv"]
DAY = pd.Timedelta(days=1)


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("build_features_script_round2", ROOT / "03_build_features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


def upto(frame, end):
    return frame[frame.index <= end]


def closes_of(index: pd.MultiIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def label_weeks(labels: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(labels.index.get_level_values("date_close").unique())


def label_end_of(labels: pd.DataFrame, friday) -> pd.Timestamp:
    ends = pd.DatetimeIndex(labels.xs(ts(friday), level="date_close")["label_end"])
    assert ends.nunique() == 1
    return pd.Timestamp(ends[0])


def h4(market) -> pd.DataFrame:
    """make_horizon_labels(h = 4) on the full synthetic weekly opens (to 2020-12-31)."""
    return labels_mod.make_horizon_labels(market.weekly_open, market.sessions, HORIZON)


def hand_y(weekly_open: pd.DataFrame, friday, horizon: int) -> np.ndarray:
    """y_h of the week ending `friday`: O(t+h+1)/O(t+1) - 1 on the weekly opens, minus its mean over the 9 sectors,
    in SECTORS order."""
    row = int(np.flatnonzero(closes_of(weekly_open.index) == ts(friday))[0])
    opens = weekly_open[SECTORS].to_numpy(dtype=np.float64)
    ret = opens[row + horizon + 1] / opens[row + 1] - 1
    return ret - ret.mean()


def hand_label_end(weekly_open: pd.DataFrame, sessions: pd.DatetimeIndex, friday, horizon: int) -> pd.Timestamp:
    """The first session on or after date_open of the row horizon + 1 places after the week ending `friday`."""
    row = int(np.flatnonzero(closes_of(weekly_open.index) == ts(friday))[0])
    date_open = pd.Timestamp(weekly_open.index.get_level_values("date_open")[row + horizon + 1])
    return pd.Timestamp(sessions[sessions.searchsorted(date_open)])


# ---------------------------------------------------------------- make_horizon_labels


def test_horizon_one_is_exactly_make_labels(synthetic_market):
    """S41-1: with h = 1 the builder returns exactly make_labels(fwd, sessions), no tolerance."""
    market = synthetic_market
    fwd, _, _ = forward_returns(market.weekly_open, market.is_end)
    expected = labels_mod.make_labels(fwd, market.sessions)
    got = labels_mod.make_horizon_labels(market.weekly_open, market.sessions, 1)
    pd.testing.assert_frame_equal(got, expected, check_exact=True)


def test_horizon_one_is_exactly_make_labels_on_in_sample_opens(synthetic_market):
    market = synthetic_market
    daily_open, daily_close = upto(market.daily_open, IS_END), upto(market.daily_close, IS_END)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    sessions = pd.DatetimeIndex(daily_open.index)
    fwd, _, _ = forward_returns(weekly_open, IS_END)
    pd.testing.assert_frame_equal(labels_mod.make_horizon_labels(weekly_open, sessions, 1),
                                  labels_mod.make_labels(fwd, sessions), check_exact=True)


def test_horizon_four_passes_the_label_contract(synthetic_market):
    labels = h4(synthetic_market)
    contracts.validate_labels(labels)
    assert list(labels.columns) == ["y", "label_end"]
    assert list(labels.index.names) == ["date_close", "ticker"]
    assert labels["y"].dtype == np.float64
    assert labels.index.is_monotonic_increasing


def test_horizon_four_sums_to_zero_in_every_week(synthetic_market):
    labels = h4(synthetic_market)
    sums = labels["y"].groupby(level="date_close").sum()
    assert np.abs(sums.to_numpy()).max() <= 1e-12
    assert (labels.groupby(level="date_close").size() == len(SECTORS)).all()


def test_horizon_four_has_rows_for_every_week_but_the_last_five(synthetic_market):
    """R4 needs O(t+5): the last five weeks of the weekly index have no label; every earlier week has 9 rows."""
    market = synthetic_market
    labels = h4(market)
    closes = closes_of(market.weekly_open.index)
    assert list(label_weeks(labels)) == list(closes[:-5])


@pytest.mark.parametrize("friday", ["2013-03-08", "2015-06-05", "2018-10-12", "2019-11-22"])
def test_horizon_four_y_is_the_hand_computed_relative_four_week_return(synthetic_market, friday):
    """y4[t, i] = O(t+5, i)/O(t+1, i) - 1 minus its mean over the 9 sectors, on the adjusted weekly opens."""
    market = synthetic_market
    labels = h4(market)
    got = labels.xs(ts(friday), level="date_close")["y"].reindex(SECTORS).to_numpy()
    np.testing.assert_allclose(got, hand_y(market.weekly_open, friday, 4), rtol=1e-12, atol=1e-15)


def test_horizon_four_y_differs_from_compounding_one_week_labels_only_by_rounding(synthetic_market):
    """The opens' ratio equals the product of the four 1-week gross returns up to rounding (option (b) of S41-1)."""
    market = synthetic_market
    fwd, _, _ = forward_returns(market.weekly_open, market.is_end)
    gross = (1 + fwd[SECTORS]).to_numpy()
    row = int(np.flatnonzero(closes_of(fwd.index) == ts("2016-05-06"))[0])
    compounded = gross[row:row + 4].prod(axis=0) - 1
    expected = compounded - compounded.mean()
    got = h4(market).xs(ts("2016-05-06"), level="date_close")["y"].reindex(SECTORS).to_numpy()
    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-13)


def test_horizon_four_label_end_is_the_session_of_o_t_plus_5(synthetic_market):
    market = synthetic_market
    labels = h4(market)
    # 2015-06-05: O(t+5) is the open of the week ending 2015-07-10, Monday 2015-07-06
    assert label_end_of(labels, "2015-06-05") == ts("2015-07-06")
    for friday in ["2013-03-08", "2016-05-06", "2019-11-22"]:
        assert label_end_of(labels, friday) == hand_label_end(market.weekly_open, market.sessions, friday, 4)


@pytest.mark.parametrize("friday, holiday, tuesday", [
    ("2014-12-19", "2015-01-19", "2015-01-20"),  # Martin Luther King Jr. Day
    ("2016-01-15", "2016-02-15", "2016-02-16"),  # Presidents Day
    ("2015-08-07", "2015-09-07", "2015-09-08"),  # Labor Day
])
def test_horizon_four_label_end_is_the_tuesday_after_a_monday_holiday(synthetic_market, friday, holiday, tuesday):
    market = synthetic_market
    assert ts(holiday) not in market.sessions
    assert ts(tuesday) in market.sessions
    assert label_end_of(h4(market), friday) == ts(tuesday)


def test_horizon_four_label_end_is_after_date_close_and_identical_within_a_week(synthetic_market):
    labels = h4(synthetic_market)
    ends = pd.DatetimeIndex(labels["label_end"])
    assert (ends > closes_of(labels.index)).all()
    assert (labels["label_end"].groupby(level="date_close").nunique() == 1).all()


def test_horizon_four_last_in_sample_week_from_truncated_opens(synthetic_market):
    """On opens truncated at the In-Sample end, the last label week is 2019-11-22 with label_end 2019-12-23."""
    market = synthetic_market
    daily_open, daily_close = upto(market.daily_open, IS_END), upto(market.daily_close, IS_END)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    labels = labels_mod.make_horizon_labels(weekly_open, pd.DatetimeIndex(daily_open.index), 4)
    assert label_weeks(labels).max() == LAST_H4_WEEK
    assert label_end_of(labels, LAST_H4_WEEK) == LAST_H4_END
    assert pd.DatetimeIndex(labels["label_end"]).max() <= IS_END


# ---------------------------------------------------------------- build_horizon_labels (03_build_features.py)

_CACHE: dict = {}


def in_sample_h4(script, market) -> pd.DataFrame:
    if "is_h4" not in _CACHE:
        _CACHE["is_h4"] = script.build_horizon_labels(market.daily_open, market.daily_close, IS_END, HORIZON)
    return _CACHE["is_h4"]


def test_build_horizon_labels_passes_the_label_contract(script, synthetic_market):
    labels = in_sample_h4(script, synthetic_market)
    contracts.validate_labels(labels)
    assert list(labels.columns) == ["y", "label_end"]
    assert list(labels.index.names) == ["date_close", "ticker"]


def test_build_horizon_labels_last_week_is_2019_11_22_ending_2019_12_23(script, synthetic_market):
    labels = in_sample_h4(script, synthetic_market)
    assert label_weeks(labels).max() == LAST_H4_WEEK
    assert label_end_of(labels, LAST_H4_WEEK) == LAST_H4_END


def test_build_horizon_labels_has_no_label_end_after_the_in_sample_end(script, synthetic_market):
    labels = in_sample_h4(script, synthetic_market)
    assert pd.DatetimeIndex(labels["label_end"]).max() <= IS_END
    assert ts("2019-11-29") not in label_weeks(labels)  # its O(t+5) is the open of Mon 2019-12-30


def test_build_horizon_labels_equals_make_horizon_labels_on_truncated_opens(script, synthetic_market):
    market = synthetic_market
    daily_open, daily_close = upto(market.daily_open, IS_END), upto(market.daily_close, IS_END)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    expected = labels_mod.make_horizon_labels(weekly_open, pd.DatetimeIndex(daily_open.index), HORIZON)
    expected = expected[pd.DatetimeIndex(expected["label_end"]) <= IS_END]
    got = in_sample_h4(script, market)
    assert got.index.equals(expected.index)
    np.testing.assert_allclose(got["y"].to_numpy(), expected["y"].to_numpy(), rtol=1e-12, atol=1e-15)
    assert list(pd.DatetimeIndex(got["label_end"])) == list(pd.DatetimeIndex(expected["label_end"]))


def test_build_horizon_labels_covers_every_week_up_to_the_last_label_week(script, synthetic_market):
    market = synthetic_market
    labels = in_sample_h4(script, market)
    closes = closes_of(market.weekly_open.index)
    assert list(label_weeks(labels)) == list(closes[closes <= LAST_H4_WEEK])


def test_build_horizon_labels_horizon_one_equals_build_labels(script, synthetic_market):
    """One formula for both horizons: h = 1 reproduces the round-1 labels.csv builder."""
    market = synthetic_market
    expected = script.build_labels(market.daily_open, market.daily_close, IS_END)
    got = script.build_horizon_labels(market.daily_open, market.daily_close, IS_END, 1)
    pd.testing.assert_frame_equal(got, expected, check_exact=True)


def test_build_horizon_labels_ignores_every_price_after_the_in_sample_end(script, synthetic_market):
    market = synthetic_market
    reference = in_sample_h4(script, market)
    opens, closes = market.daily_open.copy(), market.daily_close.copy()
    opens.loc[opens.index > IS_END] *= 3.0
    closes.loc[closes.index > IS_END] *= 0.5
    pd.testing.assert_frame_equal(reference, script.build_horizon_labels(opens, closes, IS_END, HORIZON))


def test_build_horizon_labels_is_the_same_with_pre_truncated_inputs(script, synthetic_market):
    market = synthetic_market
    got = script.build_horizon_labels(upto(market.daily_open, IS_END), upto(market.daily_close, IS_END), IS_END, HORIZON)
    pd.testing.assert_frame_equal(in_sample_h4(script, market), got)


@pytest.mark.parametrize("with_path", [False, True])
def test_build_horizon_labels_truncate_after_the_in_sample_end_needs_the_lock(script, synthetic_market, tmp_path,
                                                                               with_path):
    """A truncate_at after is_end raises OOSAccessError while FROZEN.lock does not exist."""
    market = synthetic_market
    lock = tmp_path / "FROZEN.lock"
    kwargs = {"lock_path": lock} if with_path else {}
    with pytest.raises(OOSAccessError):
        script.build_horizon_labels(market.daily_open, market.daily_close, IS_END, HORIZON,
                                    truncate_at=ts("2020-06-30"), **kwargs)
    assert not lock.exists()


def test_build_horizon_labels_with_the_lock_reaches_past_the_in_sample_end(script, synthetic_market, tmp_path):
    """With an existing (temporary) FROZEN.lock the labels run to truncate_at; their In-Sample part is unchanged."""
    market = synthetic_market
    lock = tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    data_end = pd.Timestamp(market.sessions.max())
    labels = script.build_horizon_labels(market.daily_open, market.daily_close, IS_END, HORIZON, truncate_at=data_end,
                                         lock_path=lock)
    contracts.validate_labels(labels)
    ends = pd.DatetimeIndex(labels["label_end"])
    assert ends.max() > IS_END
    assert ends.max() <= data_end
    reference = in_sample_h4(script, market)
    early = labels[np.asarray(ends <= IS_END)]
    assert early.index.equals(reference.index)
    np.testing.assert_allclose(early["y"].to_numpy(), reference["y"].to_numpy(), rtol=1e-12, atol=1e-15)
    friday = "2020-06-05"
    got = labels.xs(ts(friday), level="date_close")["y"].reindex(SECTORS).to_numpy()
    np.testing.assert_allclose(got, hand_y(market.weekly_open, friday, 4), rtol=1e-12, atol=1e-15)


def test_build_horizon_labels_truncate_before_the_in_sample_end_is_refused(script, synthetic_market, tmp_path):
    market = synthetic_market
    with pytest.raises(ValueError):
        script.build_horizon_labels(market.daily_open, market.daily_close, IS_END, HORIZON,
                                    truncate_at=ts("2019-06-28"))
    lock = tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        script.build_horizon_labels(market.daily_open, market.daily_close, IS_END, HORIZON,
                                    truncate_at=ts("2019-06-28"), lock_path=lock)


# ---------------------------------------------------------------- write_tables and labels_h4


def make_tables(last_friday: str) -> dict[str, pd.DataFrame]:
    """Four small valid tables on the Fridays from 2019-12-06 to `last_friday`."""
    fridays = pd.date_range("2019-12-06", last_friday, freq="7D")
    weeks = pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])
    rows = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(0)
    return {
        "features": pd.DataFrame(rng.normal(size=(len(rows), len(ASSET))), index=rows, columns=ASSET),
        "market_states": pd.DataFrame({"BEAR24": 0.0, "MKT_VAR": 1e-4, "VIX": 15.0, "TERM": 1.2, "CREDIT": 2.1},
                                      index=weeks)[STATES],
        "sizing_betas": pd.DataFrame(rng.uniform(0.5, 1.5, (len(weeks), len(TRADED))), index=weeks, columns=TRADED),
        "momentum_variants": pd.DataFrame(rng.normal(size=(len(rows), len(VARIANTS))), index=rows, columns=VARIANTS),
    }


def make_labels_table(label_ends: dict[str, str], seed: int = 9) -> pd.DataFrame:
    """A valid labels frame (contract 6): {date_close: label_end}, y summing to zero within each week."""
    fridays = pd.DatetimeIndex(sorted(label_ends))
    rows = pd.MultiIndex.from_product([fridays, sorted(SECTORS)], names=["date_close", "ticker"])
    raw = np.random.default_rng(seed).normal(0, 0.04, (len(fridays), len(SECTORS)))
    y = (raw - raw.mean(axis=1, keepdims=True)).ravel()
    ends = np.repeat(pd.DatetimeIndex([label_ends[str(day.date())] for day in fridays]).as_unit("ns").to_numpy(),
                     len(SECTORS))
    labels = pd.DataFrame({"y": y, "label_end": ends}, index=rows)
    contracts.validate_labels(labels)
    return labels


ONE_WEEK_LABELS = {"2019-12-06": "2019-12-16", "2019-12-13": "2019-12-23"}
IN_SAMPLE_H4 = {"2019-11-15": "2019-12-16", "2019-11-22": "2019-12-23"}
OOS_H4 = [
    {**IN_SAMPLE_H4, "2019-11-29": "2019-12-30"},  # label_end after the In-Sample end
    {**IN_SAMPLE_H4, "2019-12-06": "2020-01-06"},
]


def nothing_written(out_dir: Path) -> bool:
    return not out_dir.exists() or not any(out_dir.iterdir())


def h4_tables(label_ends: dict[str, str]) -> dict[str, pd.DataFrame]:
    return {**make_tables("2019-12-27"), "labels": make_labels_table(ONE_WEEK_LABELS),
            "labels_h4": make_labels_table(label_ends, seed=4)}


def test_write_tables_writes_labels_h4_csv_with_a_checksum_entry(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    tables = h4_tables(IN_SAMPLE_H4)
    info = script.write_tables(tables, out_dir, IS_END, lock)
    path = out_dir / "labels_h4.csv"
    assert path.exists()
    entry = info["labels_h4.csv"]
    assert entry["rows"] == len(tables["labels_h4"])
    assert entry["bytes"] == len(path.read_bytes())
    assert b"\r\n" not in path.read_bytes()
    assert list(entry["columns"]) == ["y", "label_end"]
    assert str(pd.Timestamp(entry["last_date_close"]).date()) == "2019-11-22"


@pytest.mark.parametrize("label_ends", OOS_H4)
def test_write_tables_refuses_a_labels_h4_end_after_the_in_sample_end_while_sealed(script, tmp_path, label_ends):
    """S41-1: the seal covers every label table; nothing is written when it refuses."""
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    tables = h4_tables(label_ends)
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock)
    assert nothing_written(out_dir)
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock, allow_oos=True)
    assert nothing_written(out_dir)
    lock.write_text("signed\n", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock)
    assert nothing_written(out_dir)


def test_write_tables_writes_oos_labels_h4_with_the_lock_and_allow_oos(script, tmp_path):
    """S41-6: 08_run_oos.py writes the 4-week labels to the data end with allow_oos=True after the freeze."""
    out_dir, lock = tmp_path / "oos", tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    tables = h4_tables(OOS_H4[0])
    info = script.write_tables(tables, out_dir, IS_END, lock, allow_oos=True)
    assert info["labels_h4.csv"]["rows"] == len(tables["labels_h4"])
    assert (out_dir / "labels_h4.csv").exists()


def synthetic_round1_tables(script, market) -> dict[str, pd.DataFrame]:
    """The round-1 tables of 03_build_features.py on the synthetic market truncated at the In-Sample end."""
    if "round1" not in _CACHE:
        daily_close, daily_open = upto(market.daily_close, IS_END), upto(market.daily_open, IS_END)
        vix, fred = upto(market.vix, IS_END), upto(market.fred, IS_END)
        tables = script.build_tables(daily_close, vix, fred, CFG)
        _CACHE["round1"] = {**tables, "labels": script.build_labels(daily_open, daily_close, IS_END),
                            "forward_returns": script.build_forward_returns(daily_open, daily_close, IS_END)}
    return _CACHE["round1"]


def test_round1_tables_are_byte_identical_with_and_without_labels_h4(script, synthetic_market, tmp_path):
    """S41-1: adding labels_h4 changes no byte of any other table and no entry of their description."""
    market = synthetic_market
    round1 = synthetic_round1_tables(script, market)
    lock = tmp_path / "FROZEN.lock"
    without, with_h4 = tmp_path / "without", tmp_path / "with"
    info_without = script.write_tables(dict(round1), without, IS_END, lock)
    info_with = script.write_tables({**round1, "labels_h4": in_sample_h4(script, market)}, with_h4, IS_END, lock)
    names = sorted(path.name for path in without.iterdir())
    assert {f"{key}.csv" for key in round1} <= set(names)
    assert "labels_h4.csv" not in names
    for name in names:
        assert (with_h4 / name).read_bytes() == (without / name).read_bytes(), name
    assert sorted(path.name for path in with_h4.iterdir()) == sorted(names + ["labels_h4.csv"])
    for name, entry in info_without.items():
        assert info_with[name] == entry, name
    assert set(info_with) == set(info_without) | {"labels_h4.csv"}


def test_synthetic_labels_h4_csv_round_trips(script, synthetic_market, tmp_path):
    labels = in_sample_h4(script, synthetic_market)
    out_dir = tmp_path / "processed"
    info = script.write_tables({"labels_h4": labels}, out_dir, IS_END, tmp_path / "FROZEN.lock")
    assert info["labels_h4.csv"]["rows"] == len(labels)
    back = pd.read_csv(out_dir / "labels_h4.csv", index_col=[0, 1], parse_dates=[0])
    np.testing.assert_allclose(back["y"].to_numpy(), labels["y"].to_numpy(), rtol=1e-12, atol=1e-15)
    assert pd.DatetimeIndex(pd.to_datetime(back["label_end"])).max() == LAST_H4_END


# ---------------------------------------------------------------- the committed checksum file


def committed_checksums() -> dict:
    with open(ROOT / "data" / "checksums_features.json", encoding="utf-8") as f:
        return json.load(f)


def test_round1_checksum_entries_are_unchanged_from_main():
    """The six entries other than labels_h4.csv equal those of data/checksums_features.json at b8fc01a."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    shown = subprocess.run(["git", "show", f"{REFERENCE_COMMIT}:data/checksums_features.json"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", check=False)
    if shown.returncode != 0:
        pytest.skip(f"commit {REFERENCE_COMMIT} is not available: {shown.stderr.strip()}")
    reference = json.loads(shown.stdout)
    assert sorted(reference) == ROUND1_CHECKSUM_ENTRIES
    current = committed_checksums()
    for name in ROUND1_CHECKSUM_ENTRIES:
        assert current[name] == reference[name], name
    assert set(current) - set(reference) <= {"labels_h4.csv"}


def test_checksum_file_has_the_labels_h4_entry():
    """S41-1: data/checksums_features.json gains the labels_h4.csv entry (In-Sample: last week 2019-11-22)."""
    entry = committed_checksums().get("labels_h4.csv")
    assert entry is not None, "data/checksums_features.json has no labels_h4.csv entry"
    assert list(entry["columns"]) == ["y", "label_end"]
    assert str(pd.Timestamp(entry["last_date_close"]).date()) == "2019-11-22"


# ---------------------------------------------------------------- Vault.labels(as_of, horizon)


def log_lines(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def vault_frames(market) -> dict[str, pd.DataFrame]:
    """1-week and 4-week labels on the full synthetic market (to 2020-12-31), held in memory."""
    if "frames" not in _CACHE:
        fwd, _, _ = forward_returns(market.weekly_open, market.is_end)
        _CACHE["frames"] = {"labels": labels_mod.make_labels(fwd, market.sessions), "labels_h4": h4(market)}
    return {name: frame.copy() for name, frame in _CACHE["frames"].items()}


@pytest.fixture
def env(synthetic_market, tmp_path):
    paths = {"lock": tmp_path / "FROZEN.lock", "log": tmp_path / "logs" / "vault_access_log.jsonl"}
    frames = vault_frames(synthetic_market)
    vault = Vault(IS_END, lock_path=paths["lock"], log_path=paths["log"], frames=frames, cfg=CFG)
    return vault, paths, frames


@pytest.mark.parametrize("as_of", ["2015-06-10", "2019-12-23", "2019-12-27"])
def test_vault_h4_labels_are_the_rows_realised_by_as_of(env, as_of):
    vault, paths, frames = env
    got = vault.labels(ts(as_of), horizon=4)
    full = frames["labels_h4"]
    expected = full[pd.DatetimeIndex(full["label_end"]) <= ts(as_of)]
    assert got.index.equals(expected.index)
    np.testing.assert_array_equal(got["y"].to_numpy(), expected["y"].to_numpy())
    assert (pd.DatetimeIndex(got["label_end"]) <= ts(as_of)).all()
    contracts.validate_labels(got)
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == ("labels_h4", as_of, "ok")


def test_vault_h4_labels_at_the_in_sample_end_stop_at_2019_11_22(env):
    vault, _, _ = env
    got = vault.labels(IS_END, horizon=4)
    assert label_weeks(got).max() == LAST_H4_WEEK


@pytest.mark.parametrize("as_of", ["2019-12-30", "2020-03-06"])
def test_vault_h4_labels_after_the_in_sample_end_are_refused_and_logged(env, as_of):
    vault, paths, _ = env
    with pytest.raises(OOSAccessError):
        vault.labels(ts(as_of), horizon=4)
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["as_of"], last["result"]) == ("labels_h4", as_of, "refused")


def test_vault_h4_labels_refused_with_the_lock_but_without_unlock(env):
    vault, paths, _ = env
    paths["lock"].write_text("signed\n", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        vault.labels(ts("2020-03-06"), horizon=4)


def test_vault_h4_labels_open_after_lock_and_unlock(env):
    vault, paths, _ = env
    paths["lock"].write_text("signed\n", encoding="utf-8")
    vault.unlock()
    got = vault.labels(ts("2020-06-30"), horizon=4)
    ends = pd.DatetimeIndex(got["label_end"])
    assert IS_END < ends.max() <= ts("2020-06-30")


@pytest.mark.parametrize("as_of", ["2015-06-10", "2019-12-27"])
def test_vault_horizon_one_is_the_round1_call(env, as_of):
    """horizon=1 is the existing call: same rows as labels(as_of), logged with method labels."""
    vault, paths, frames = env
    default = vault.labels(ts(as_of))
    explicit = vault.labels(ts(as_of), horizon=1)
    pd.testing.assert_frame_equal(default, explicit, check_exact=True)
    full = frames["labels"]
    assert explicit.index.equals(full[pd.DatetimeIndex(full["label_end"]) <= ts(as_of)].index)
    lines = log_lines(paths["log"])[-2:]
    assert [(line["method"], line["result"]) for line in lines] == [("labels", "ok"), ("labels", "ok")]


def test_vault_horizon_one_after_the_in_sample_end_is_refused_as_before(env):
    vault, paths, _ = env
    with pytest.raises(OOSAccessError):
        vault.labels(ts("2019-12-30"), horizon=1)
    last = log_lines(paths["log"])[-1]
    assert (last["method"], last["result"]) == ("labels", "refused")


@pytest.mark.parametrize("horizon", [2, 3, 5, 0])
def test_vault_other_horizons_are_refused_and_logged(env, horizon):
    vault, paths, _ = env
    with pytest.raises(ValueError):
        vault.labels(ts("2015-06-10"), horizon=horizon)
    assert log_lines(paths["log"])[-1]["result"] == "refused"


def test_vault_reads_labels_h4_csv_from_data_dir(script, synthetic_market, tmp_path):
    """Without frames, horizon 4 reads data_dir/labels_h4.csv."""
    labels = in_sample_h4(script, synthetic_market)
    data_dir = tmp_path / "processed"
    script.write_tables({"labels_h4": labels}, data_dir, IS_END, tmp_path / "FROZEN.lock")
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", data_dir=data_dir, cfg=CFG)
    got = vault.labels(IS_END, horizon=4)
    assert got.index.equals(labels.index)
    np.testing.assert_allclose(got["y"].to_numpy(), labels["y"].to_numpy(), rtol=1e-12, atol=1e-15)
    assert list(pd.DatetimeIndex(got["label_end"])) == list(pd.DatetimeIndex(labels["label_end"]))


def test_vault_h1_labels_do_not_need_the_round2_section(synthetic_market, tmp_path):
    """S41-1: the 1-week call is unchanged and never reads round2 (a configuration without that section still works)."""
    cfg = {key: value for key, value in CFG.items() if key != "round2"}
    log = tmp_path / "log.jsonl"
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=log, frames=vault_frames(synthetic_market), cfg=cfg)
    got = vault.labels(IS_END)
    assert (pd.DatetimeIndex(got["label_end"]) <= IS_END).all() and len(got)
    assert [(line["method"], line["result"]) for line in log_lines(log)] == [("labels", "ok")]
