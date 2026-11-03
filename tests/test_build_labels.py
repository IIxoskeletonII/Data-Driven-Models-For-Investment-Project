"""In-Sample labels of 03_build_features.py (S23-1): truncated adjusted opens, label weeks, label_end, the guarded writer.

The script's module name starts with a digit, so it is loaded from its file. Inputs come from the shared synthetic market
(sessions 2011-01-03 to 2020-12-31, US holidays) or are tiny hand-made frames in a temporary folder (no real data).
Every expected value is recomputed here from the synthetic weekly opens.
"""

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import contracts, features
from src.config import data_settings, load_config
from src.data import write_csv
from src.vault import OOSAccessError

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
UNIVERSE = contracts.universe(CFG)
SECTORS = list(UNIVERSE.sectors)
TRADED = list(UNIVERSE.traded)
TRADABLES = list(UNIVERSE.tradables)
ASSET = list(CFG["features"]["asset"])
STATES = list(CFG["features"]["states"])
VARIANTS = [f"MOM{lookback}_1" for lookback in CFG["models"]["M0_star"]["lookback_weeks"]]
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
LAST_LABEL_WEEK = pd.Timestamp("2019-12-13")  # its O(t+2) is Mon 2019-12-23 (contract 7)
DAY = pd.Timedelta(days=1)


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("build_features_script_labels", ROOT / "03_build_features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


def upto(frame, end):
    return frame[frame.index <= end]


def full_labels(script, market) -> pd.DataFrame:
    """Labels from the FULL synthetic opens and closes (they extend to 2020-12-31)."""
    return script.build_labels(market.daily_open, market.daily_close, IS_END)


def label_weeks(labels: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(labels.index.get_level_values("date_close").unique())


def label_end_of(labels: pd.DataFrame, friday: str) -> pd.Timestamp:
    return pd.Timestamp(labels.xs(ts(friday), level="date_close")["label_end"].iloc[0])


# ---------------------------------------------------------------- features_settings


def test_features_settings_holds_data_features_execution_and_in_sample_end():
    assert features.features_settings(CFG) == {
        "data": data_settings(CFG),
        "features": CFG["features"],
        "execution": CFG["execution"],
        "in_sample_end": CFG["split"]["in_sample_end"],
    }


def test_features_settings_changes_with_the_execution_type():
    other = {**CFG, "execution": {"type": "close_to_close"}}
    assert features.features_settings(other) != features.features_settings(CFG)


# ---------------------------------------------------------------- load_opens


def write_fake_opens(root: Path) -> pd.DataFrame:
    """data/processed/daily_open.csv on sessions spanning the In-Sample end."""
    sessions = pd.bdate_range("2019-12-02", "2020-01-17").difference(pd.DatetimeIndex(["2019-12-25", "2020-01-01"]))
    rng = np.random.default_rng(5)
    opens = pd.DataFrame(50 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(sessions), len(TRADABLES))), axis=0)),
                         index=sessions.rename("Date"), columns=TRADABLES)
    write_csv(opens, root / "processed" / "daily_open.csv")
    return opens


def test_load_opens_truncates_at_end(script, tmp_path):
    original = write_fake_opens(tmp_path)
    opens = script.load_opens(tmp_path, IS_END)
    expected = upto(original, IS_END)
    assert pd.DatetimeIndex(opens.index).max() == IS_END
    assert list(pd.DatetimeIndex(opens.index)) == list(expected.index)
    np.testing.assert_allclose(opens[TRADABLES].to_numpy(dtype=np.float64), expected.to_numpy(), rtol=1e-15)


def test_load_opens_returns_float64_on_a_date_index(script, tmp_path):
    write_fake_opens(tmp_path)
    opens = script.load_opens(tmp_path, IS_END)
    assert isinstance(opens.index, pd.DatetimeIndex)
    assert opens.index.name == "date"
    assert all(dtype == np.float64 for dtype in opens.dtypes)


def test_load_opens_with_an_earlier_end(script, tmp_path):
    write_fake_opens(tmp_path)
    opens = script.load_opens(tmp_path, ts("2019-12-13"))
    assert pd.DatetimeIndex(opens.index).max() == ts("2019-12-13")


# ---------------------------------------------------------------- build_labels on the synthetic market


def test_build_labels_passes_the_label_contract(script, synthetic_market):
    labels = full_labels(script, synthetic_market)
    contracts.validate_labels(labels)
    assert list(labels.columns) == ["y", "label_end"]
    assert list(labels.index.names) == ["date_close", "ticker"]


def test_build_labels_has_no_label_realised_after_the_in_sample_end(script, synthetic_market):
    labels = full_labels(script, synthetic_market)
    weeks = label_weeks(labels)
    assert ts("2019-12-20") not in weeks  # its return would be realised at the open of Mon 2019-12-30
    assert ts("2019-12-27") not in weeks
    assert pd.Timestamp(labels["label_end"].max()) <= IS_END
    assert weeks.max() <= IS_END


def test_build_labels_last_week_is_2019_12_13_ending_2019_12_23(script, synthetic_market):
    labels = full_labels(script, synthetic_market)
    assert label_weeks(labels).max() == LAST_LABEL_WEEK
    assert label_end_of(labels, "2019-12-13") == ts("2019-12-23")


def test_build_labels_covers_every_week_up_to_the_last_label_week(script, synthetic_market):
    labels = full_labels(script, synthetic_market)
    closes = pd.DatetimeIndex(synthetic_market.weekly_open.index.get_level_values("date_close"))
    expected = closes[closes <= LAST_LABEL_WEEK]
    assert list(label_weeks(labels)) == list(expected)
    assert len(labels) == 9 * len(expected)


def test_build_labels_y_is_the_hand_computed_relative_forward_return(script, synthetic_market):
    labels = full_labels(script, synthetic_market)
    weekly_open = synthetic_market.weekly_open
    closes = pd.DatetimeIndex(weekly_open.index.get_level_values("date_close"))
    t = closes.get_loc(ts("2015-06-05"))
    fwd = weekly_open[SECTORS].iloc[t + 2] / weekly_open[SECTORS].iloc[t + 1] - 1
    expected = fwd - fwd.mean()
    got = labels.xs(ts("2015-06-05"), level="date_close")["y"].reindex(SECTORS)
    np.testing.assert_allclose(got.to_numpy(), expected.to_numpy(), rtol=1e-12, atol=1e-15)


def test_build_labels_label_end_is_the_monday_of_week_t_plus_2(script, synthetic_market):
    labels = full_labels(script, synthetic_market)
    assert label_end_of(labels, "2015-06-05") == ts("2015-06-15")


@pytest.mark.parametrize("friday, holiday, tuesday", [
    ("2015-01-09", "2015-01-19", "2015-01-20"),  # Martin Luther King Jr. Day
    ("2016-02-05", "2016-02-15", "2016-02-16"),  # Presidents Day
])
def test_build_labels_label_end_is_the_tuesday_after_a_monday_holiday(script, synthetic_market, friday, holiday, tuesday):
    assert ts(holiday) not in synthetic_market.sessions
    assert ts(tuesday) in synthetic_market.sessions
    labels = full_labels(script, synthetic_market)
    assert label_end_of(labels, friday) == ts(tuesday)


def test_build_labels_good_friday_week_keeps_its_friday_label(script, synthetic_market):
    """Good Friday 2015-04-03 is not a session: the week's label is dated Friday, its O(t+1) is Monday 2015-04-06 and
    label_end is Monday 2015-04-13; y is the hand-computed relative forward return."""
    friday = ts("2015-04-03")
    assert friday not in synthetic_market.sessions and ts("2015-04-02") in synthetic_market.sessions
    labels = full_labels(script, synthetic_market)
    assert label_end_of(labels, friday) == ts("2015-04-13")
    closes = pd.DatetimeIndex(synthetic_market.weekly_open.index.get_level_values("date_close"))
    row = int(np.flatnonzero(closes == friday)[0])
    opens = synthetic_market.weekly_open[SECTORS].to_numpy(dtype=np.float64)
    fwd = opens[row + 2] / opens[row + 1] - 1
    got = labels.xs(friday, level="date_close").loc[SECTORS, "y"].to_numpy()
    np.testing.assert_allclose(got, fwd - fwd.mean(), rtol=0, atol=1e-15)


def test_build_labels_is_the_same_with_pre_truncated_inputs(script, synthetic_market):
    full = full_labels(script, synthetic_market)
    truncated = script.build_labels(upto(synthetic_market.daily_open, IS_END), upto(synthetic_market.daily_close, IS_END),
                                    IS_END)
    pd.testing.assert_frame_equal(full, truncated)


def test_build_labels_ignores_every_price_after_the_in_sample_end(script, synthetic_market):
    full = full_labels(script, synthetic_market)
    opens, closes = synthetic_market.daily_open.copy(), synthetic_market.daily_close.copy()
    opens.loc[opens.index > IS_END] *= 3.0
    closes.loc[closes.index > IS_END] *= 0.5
    pd.testing.assert_frame_equal(full, script.build_labels(opens, closes, IS_END))


# ---------------------------------------------------------------- write_tables with labels


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


def make_labels_table(label_ends: dict[str, str]) -> pd.DataFrame:
    """A valid labels frame (contract 6): {date_close: label_end}, y summing to zero within each week."""
    fridays = pd.DatetimeIndex(sorted(label_ends))
    rows = pd.MultiIndex.from_product([fridays, sorted(SECTORS)], names=["date_close", "ticker"])
    rng = np.random.default_rng(9)
    raw = rng.normal(0, 0.02, (len(fridays), len(SECTORS)))
    y = (raw - raw.mean(axis=1, keepdims=True)).ravel()
    ends = np.repeat(pd.DatetimeIndex([label_ends[str(day.date())] for day in fridays]).as_unit("ns").to_numpy(),
                     len(SECTORS))
    labels = pd.DataFrame({"y": y, "label_end": ends}, index=rows)
    contracts.validate_labels(labels)
    return labels


IN_SAMPLE_LABELS = {"2019-12-06": "2019-12-16", "2019-12-13": "2019-12-23"}


def nothing_written(out_dir: Path) -> bool:
    return not out_dir.exists() or not any(out_dir.iterdir())


def test_write_tables_writes_labels_csv_with_a_checksum_entry(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    labels = make_labels_table(IN_SAMPLE_LABELS)
    info = script.write_tables({**make_tables("2019-12-27"), "labels": labels}, out_dir, IS_END, lock)
    path = out_dir / "labels.csv"
    content = path.read_bytes()
    entry = info["labels.csv"]
    assert b"\r\n" not in content
    assert entry["rows"] == len(labels)
    assert entry["bytes"] == len(content)
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert str(pd.Timestamp(entry["first_date_close"]).date()) == "2019-12-06"
    assert str(pd.Timestamp(entry["last_date_close"]).date()) == "2019-12-13"
    assert list(entry["columns"]) == ["y", "label_end"]


def test_labels_csv_round_trips(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    labels = make_labels_table(IN_SAMPLE_LABELS)
    script.write_tables({**make_tables("2019-12-27"), "labels": labels}, out_dir, IS_END, lock)
    back = pd.read_csv(out_dir / "labels.csv", index_col=[0, 1], parse_dates=[0])
    assert list(back.index.get_level_values(0)) == list(labels.index.get_level_values("date_close"))
    assert list(back.index.get_level_values(1)) == list(labels.index.get_level_values("ticker"))
    np.testing.assert_array_equal(back["y"].to_numpy(), labels["y"].to_numpy())
    assert list(pd.DatetimeIndex(pd.to_datetime(back["label_end"]))) == list(pd.DatetimeIndex(labels["label_end"]))


def test_write_tables_round_trips_the_synthetic_labels(script, synthetic_market, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    labels = full_labels(script, synthetic_market)
    info = script.write_tables({**make_tables("2019-12-27"), "labels": labels}, out_dir, IS_END, lock)
    assert info["labels.csv"]["rows"] == len(labels)
    assert str(pd.Timestamp(info["labels.csv"]["last_date_close"]).date()) == "2019-12-13"
    back = pd.read_csv(out_dir / "labels.csv", index_col=[0, 1], parse_dates=[0])
    np.testing.assert_array_equal(back["y"].to_numpy(), labels["y"].to_numpy())
    assert pd.DatetimeIndex(pd.to_datetime(back["label_end"])).max() == ts("2019-12-23")


OOS_LABELS = [
    {**IN_SAMPLE_LABELS, "2019-12-20": "2019-12-30"},  # label_end after the In-Sample end
    {**IN_SAMPLE_LABELS, "2020-01-03": "2020-01-13"},  # date_close after the In-Sample end
]


@pytest.mark.parametrize("label_ends", OOS_LABELS)
def test_write_tables_refuses_oos_labels_without_the_lock(script, tmp_path, label_ends):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    tables = {**make_tables("2019-12-27"), "labels": make_labels_table(label_ends)}
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock)
    assert nothing_written(out_dir)
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock, allow_oos=True)
    assert nothing_written(out_dir)


@pytest.mark.parametrize("label_ends", OOS_LABELS)
def test_write_tables_refuses_oos_labels_with_the_lock_but_without_allow_oos(script, tmp_path, label_ends):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    tables = {**make_tables("2019-12-27"), "labels": make_labels_table(label_ends)}
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock)
    assert nothing_written(out_dir)


def test_write_tables_writes_oos_labels_with_the_lock_and_allow_oos(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    labels = make_labels_table(OOS_LABELS[0])
    info = script.write_tables({**make_tables("2019-12-27"), "labels": labels}, out_dir, IS_END, lock, allow_oos=True)
    assert info["labels.csv"]["rows"] == len(labels)
    assert (out_dir / "labels.csv").exists()
