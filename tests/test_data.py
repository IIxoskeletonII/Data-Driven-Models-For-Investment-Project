"""Weekly panel, price adjustment, market-series lag and byte-stable CSV files."""

import numpy as np
import pandas as pd
import pytest

from src import data


def test_weekly_panel_first_open_last_close(raw):
    opens, close = data.weekly_panel(raw[["Open"]], raw[["Close"]])
    assert list(opens.index.names) == data.WEEK_COLUMNS == list(close.index.names)
    date_open = opens.index.get_level_values("date_open")
    date_close = opens.index.get_level_values("date_close")
    assert (date_open.day_name() == "Monday").all()
    assert (date_close.day_name() == "Friday").all()
    assert ((date_close - date_open) == pd.Timedelta(days=4)).all()

    # a regular week: Monday open, Friday close
    week = (pd.Timestamp("2021-03-08"), pd.Timestamp("2021-03-12"))
    assert opens.loc[week, "Open"] == raw.loc["2021-03-08", "Open"]
    assert close.loc[week, "Close"] == raw.loc["2021-03-12", "Close"]


def test_weekly_panel_holiday_weeks(raw):
    opens, close = data.weekly_panel(raw[["Open"]], raw[["Close"]])
    # Monday holiday (Martin Luther King Day): the week keeps its Monday label, the open is Tuesday's
    week = (pd.Timestamp("2021-01-18"), pd.Timestamp("2021-01-22"))
    assert opens.loc[week, "Open"] == raw.loc["2021-01-19", "Open"]
    # Good Friday: the week keeps its Friday label, the close is Thursday's
    week = (pd.Timestamp("2021-03-29"), pd.Timestamp("2021-04-02"))
    assert close.loc[week, "Close"] == raw.loc["2021-04-01", "Close"]
    # New Year's Day on a Friday: the week of 28 Dec 2020 is outside the data, the first week ends 8 Jan
    assert opens.index[0] == (pd.Timestamp("2021-01-04"), pd.Timestamp("2021-01-08"))


def test_weekly_panel_drops_weeks_without_sessions(raw):
    closed = raw.drop(raw.loc["2021-06-07":"2021-06-11"].index)
    opens, close = data.weekly_panel(closed[["Open"]], closed[["Close"]])
    fridays = close.index.get_level_values("date_close")
    assert pd.Timestamp("2021-06-11") not in fridays
    assert len(close) == len(data.weekly_panel(raw[["Open"]], raw[["Close"]])[1]) - 1
    assert not close.isna().any().any() and not opens.isna().any().any()


def test_weekly_panel_counts_each_ticker_separately(raw_factory, sessions):
    a = raw_factory(sessions, seed=2)
    b = raw_factory(sessions, seed=3).drop(pd.Timestamp("2021-03-12"))  # b has no Friday session that week
    _, close = data.weekly_panel(pd.DataFrame({"A": a["Open"], "B": b["Open"]}),
                                 pd.DataFrame({"A": a["Close"], "B": b["Close"]}))
    week = (pd.Timestamp("2021-03-08"), pd.Timestamp("2021-03-12"))
    assert close.loc[week, "A"] == a.loc["2021-03-12", "Close"]
    assert close.loc[week, "B"] == b.loc["2021-03-11", "Close"]


def test_adjust_ohlc_applies_dividend_factor(raw):
    adjusted = data.adjust_ohlc(raw)
    factor = raw["Adj Close"] / raw["Close"]
    for field in ["Open", "High", "Low"]:
        np.testing.assert_allclose(adjusted[field], raw[field] * factor)
    assert adjusted["Close"].equals(raw["Adj Close"])

    # the open-to-open return across an ex-date includes the dividend
    ex = raw.index.get_loc(pd.Timestamp("2021-06-21"))
    raw_return = raw["Open"].iloc[ex] / raw["Open"].iloc[ex - 1]
    adjusted_return = adjusted["Open"].iloc[ex] / adjusted["Open"].iloc[ex - 1]
    dividend_factor = 1 - raw["Dividends"].iloc[ex] / raw["Close"].iloc[ex - 1]
    assert adjusted_return == pytest.approx(raw_return / dividend_factor, rel=1e-12)


def test_lag_to_sessions_uses_only_earlier_observations():
    observed = pd.Series([1.0, np.nan, 3.0, 4.0], index=pd.to_datetime(["2021-03-04", "2021-03-05", "2021-03-08", "2021-03-09"]))
    sessions = pd.to_datetime(["2021-03-04", "2021-03-05", "2021-03-08", "2021-03-09", "2021-03-10"])
    lagged = data.lag_to_sessions(observed, pd.DatetimeIndex(sessions), lag_days=1)
    # Thursday's value is first used on Friday; Friday is missing, so Monday still uses Thursday's;
    # Monday's value is first used on Tuesday, never on Monday itself
    assert np.isnan(lagged.iloc[0])
    assert lagged.tolist()[1:] == [1.0, 1.0, 3.0, 4.0]


def test_write_csv_is_byte_stable(raw, tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    data.write_csv(raw, first)
    data.write_csv(data.read_daily(first), second)
    content = first.read_bytes()
    assert content == second.read_bytes()
    assert b"\r" not in content
    assert content.startswith(b"Date,Open,High,Low,Close,Adj Close,Volume,Dividends,Stock Splits\n2021-01-04,")
    pd.testing.assert_frame_equal(data.read_daily(first), raw, check_freq=False, check_dtype=False)  # "0" reads back as int
    assert data.sha256(first) == data.sha256(second)


def test_file_stem():
    assert data.file_stem("^VIX") == "VIX"
    assert data.file_stem("XLB") == "XLB"
