"""03_build_features.py (S22-3, S22-5, S22-9): input truncation at the In-Sample end, calendar check and the OOS-guarded writer.

The script's module name starts with a digit, so it is loaded from its file. Inputs are tiny synthetic CSV files in a
temporary data folder; tables are small hand-made frames or come from the shared synthetic market (no real data).
"""

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import contracts, features
from src.config import load_config
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
FRED = list(CFG["data"]["fred"])
VARIANTS = [f"MOM{lookback}_1" for lookback in CFG["models"]["M0_star"]["lookback_weeks"]]
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
DAY = pd.Timedelta(days=1)
TABLE_KEYS = ["features", "market_states", "sizing_betas", "momentum_variants"]


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("build_features_script", ROOT / "03_build_features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


# ---------------------------------------------------------------- write_tables


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


def nothing_written(out_dir: Path) -> bool:
    return not out_dir.exists() or not any(out_dir.iterdir())


def test_write_tables_refuses_oos_rows_without_the_lock(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    with pytest.raises(OOSAccessError):
        script.write_tables(make_tables("2020-01-03"), out_dir, IS_END, lock)
    assert nothing_written(out_dir)
    with pytest.raises(OOSAccessError):
        script.write_tables(make_tables("2020-01-03"), out_dir, IS_END, lock, allow_oos=True)
    assert nothing_written(out_dir)


def test_write_tables_refuses_oos_rows_with_the_lock_but_without_allow_oos(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    with pytest.raises(OOSAccessError):
        script.write_tables(make_tables("2020-01-03"), out_dir, IS_END, lock)
    assert nothing_written(out_dir)


def test_write_tables_refuses_when_a_single_table_reaches_past_the_end(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    tables = make_tables("2019-12-27")
    tables["sizing_betas"] = make_tables("2020-01-03")["sizing_betas"]
    with pytest.raises(OOSAccessError):
        script.write_tables(tables, out_dir, IS_END, lock)
    assert nothing_written(out_dir)


def check_written(info: dict, tables: dict, out_dir: Path) -> None:
    assert set(info) == {f"{key}.csv" for key in TABLE_KEYS}
    for key, table in tables.items():
        path = out_dir / f"{key}.csv"
        entry = info[f"{key}.csv"]
        content = path.read_bytes()
        assert b"\r\n" not in content
        assert entry["rows"] == len(table)
        assert entry["bytes"] == len(content)
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        closes = pd.DatetimeIndex(table.index.get_level_values("date_close"))
        assert str(pd.Timestamp(entry["first_date_close"]).date()) == str(closes.min().date())
        assert str(pd.Timestamp(entry["last_date_close"]).date()) == str(closes.max().date())
        assert list(entry["columns"]) == list(table.columns)


def test_write_tables_writes_in_sample_tables(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    tables = make_tables("2019-12-27")
    info = script.write_tables(tables, out_dir, IS_END, lock)
    check_written(info, tables, out_dir)
    back = pd.read_csv(out_dir / "market_states.csv", index_col=[0, 1], parse_dates=[0, 1])
    np.testing.assert_allclose(back[STATES].to_numpy(), tables["market_states"].to_numpy())


def test_write_tables_writes_oos_rows_with_the_lock_and_allow_oos(script, tmp_path):
    out_dir, lock = tmp_path / "processed", tmp_path / "FROZEN.lock"
    lock.write_text("signed\n", encoding="utf-8")
    tables = make_tables("2020-01-10")
    info = script.write_tables(tables, out_dir, IS_END, lock, allow_oos=True)
    check_written(info, tables, out_dir)
    assert str(pd.Timestamp(info["features.csv"]["last_date_close"]).date()) == "2020-01-10"


# ---------------------------------------------------------------- load_inputs


def fake_data_dir(root: Path) -> dict:
    """data/processed/daily_close.csv, data/raw/yahoo/VIX.csv and data/raw/fred/<SERIES>.csv spanning the In-Sample end."""
    sessions = pd.bdate_range("2019-12-02", "2020-01-17").difference(pd.DatetimeIndex(["2019-12-25", "2020-01-01"]))
    rng = np.random.default_rng(3)
    close = pd.DataFrame(50 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(sessions), len(TRADABLES))), axis=0)),
                         index=sessions.rename("Date"), columns=TRADABLES)
    write_csv(close, root / "processed" / "daily_close.csv")
    vix_dates = sessions.union(pd.DatetimeIndex(["2019-12-25"])).rename("Date")  # a VIX-only holiday print
    vix_close = np.round(15 + rng.normal(0, 1, len(vix_dates)), 2)
    vix = pd.DataFrame({"Open": vix_close + 0.5, "High": vix_close + 1, "Low": vix_close - 1, "Close": vix_close,
                        "Adj Close": vix_close, "Volume": 0, "Dividends": 0.0, "Stock Splits": 0.0}, index=vix_dates)
    write_csv(vix, root / "raw" / "yahoo" / "VIX.csv")
    fred_days = pd.bdate_range("2019-12-02", "2020-01-17").difference(pd.DatetimeIndex(["2019-12-25", "2020-01-01"]))
    fred = {}
    for i, series in enumerate(FRED):
        values = pd.Series(np.round(1.0 + i + rng.normal(0, 0.05, len(fred_days)), 2), index=fred_days.rename("Date"),
                           name=series)
        values.iloc[5 + i] = np.nan  # a missing FRED value
        fred[series] = values
        write_csv(values.to_frame(), root / "raw" / "fred" / f"{series}.csv")
    return {"close": close, "vix": vix["Close"], "fred": fred}


def test_load_inputs_truncates_every_input_at_end(script, tmp_path):
    original = fake_data_dir(tmp_path)
    daily_close, vix, fred = script.load_inputs(tmp_path, IS_END)
    for frame in (daily_close, vix, fred):
        assert pd.DatetimeIndex(frame.index).max() <= IS_END
    assert pd.DatetimeIndex(daily_close.index).max() == IS_END
    assert list(daily_close.columns) == TRADABLES
    expected_close = original["close"][original["close"].index <= IS_END]
    assert list(pd.DatetimeIndex(daily_close.index)) == list(expected_close.index)
    np.testing.assert_allclose(daily_close.to_numpy(dtype=np.float64), expected_close.to_numpy(), rtol=1e-15)
    assert vix.name == "VIX"
    expected_vix = original["vix"][original["vix"].index <= IS_END]
    assert list(pd.DatetimeIndex(vix.index)) == list(expected_vix.index)
    np.testing.assert_allclose(vix.to_numpy(dtype=np.float64), expected_vix.to_numpy(), rtol=1e-15)
    assert set(FRED) <= set(fred.columns)
    for series, values in original["fred"].items():
        kept = values[values.index <= IS_END]
        got = fred[series].reindex(kept.index)
        np.testing.assert_allclose(got.to_numpy(dtype=np.float64), kept.to_numpy(), rtol=1e-15, equal_nan=True)


def test_load_inputs_with_an_earlier_end(script, tmp_path):
    fake_data_dir(tmp_path)
    end = ts("2019-12-13")
    daily_close, vix, fred = script.load_inputs(tmp_path, end)
    assert pd.DatetimeIndex(daily_close.index).max() == end
    assert pd.DatetimeIndex(vix.index).max() == end
    assert pd.DatetimeIndex(fred.index).max() == end


# ---------------------------------------------------------------- build_tables


def short_market(synthetic_market) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    end = ts("2014-12-31")
    m = synthetic_market
    return m.daily_close[m.daily_close.index <= end], m.vix[m.vix.index <= end], m.fred[m.fred.index <= end]


def test_build_tables_returns_validated_tables(script, synthetic_market):
    daily_close, vix, fred = short_market(synthetic_market)
    tables = script.build_tables(daily_close, vix, fred, CFG)
    assert set(tables) == set(TABLE_KEYS)
    contracts.validate_features(tables["features"])
    contracts.validate_market_states(tables["market_states"])
    contracts.validate_betas(tables["sizing_betas"])
    contracts.validate_features(tables["momentum_variants"], columns=VARIANTS)
    np.testing.assert_allclose(tables["features"].to_numpy(), features.asset_features(daily_close).to_numpy(),
                               rtol=1e-12, atol=1e-14, equal_nan=True)


def test_build_tables_rejects_a_calendar_week_without_a_session(script, synthetic_market):
    daily_close, vix, fred = short_market(synthetic_market)
    gap = (daily_close.index >= ts("2013-05-06")) & (daily_close.index <= ts("2013-05-10"))
    with pytest.raises(ValueError):
        script.build_tables(daily_close[~gap], vix, fred, CFG)
