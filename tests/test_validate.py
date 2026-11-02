"""QA gate functions on synthetic data with planted defects."""

import numpy as np
import pandas as pd
import pytest

from src import validate

SPLIT_TOLERANCE = 0.03
BIG_MOVE = 0.10


def test_planted_split_flagged_in_raw_not_in_adjusted(raw):
    adjusted = raw["Close"]  # continuous series
    split_day = adjusted.index[100]
    unadjusted = adjusted.where(adjusted.index >= split_day, adjusted * 2)  # 2:1 split: the price halves on split_day

    flagged = validate.split_like_moves(unadjusted, SPLIT_TOLERANCE)
    assert list(flagged["date"]) == [split_day]
    assert flagged["looks_like"].iloc[0] == "2:1"
    assert validate.split_like_moves(adjusted, SPLIT_TOLERANCE).empty

    moves = validate.big_moves(pd.DataFrame({"X": unadjusted}), BIG_MOVE)
    assert list(moves["date"]) == [split_day]
    assert validate.big_moves(pd.DataFrame({"X": adjusted}), BIG_MOVE).empty


def test_reverse_split_flagged(raw):
    close = raw["Close"]
    day = close.index[50]
    merged = close.where(close.index < day, close * 4)  # 1:4 reverse split
    assert list(validate.split_like_moves(merged, SPLIT_TOLERANCE)["looks_like"]) == ["1:4"]


def test_duplicate_dates_detected(raw):
    frame = pd.concat([raw.iloc[:10], raw.iloc[[9]], raw.iloc[10:]])
    assert list(validate.duplicate_dates(frame.index)) == [raw.index[9]]
    assert validate.duplicate_dates(raw.index).empty


def test_non_monotonic_dates_detected(raw):
    order = list(range(len(raw)))
    order[20], order[21] = order[21], order[20]
    frame = raw.iloc[order]
    assert list(validate.non_monotonic_dates(frame.index)) == [raw.index[20]]
    assert validate.non_monotonic_dates(raw.index).empty


def test_non_positive_prices_detected(raw):
    frame = raw.copy()
    frame.loc[frame.index[5], "Close"] = 0.0
    frame.loc[frame.index[7], "Low"] = -1.0
    bad = validate.non_positive_prices(frame, ["Open", "High", "Low", "Close"])
    assert list(bad.index) == [frame.index[5], frame.index[7]]
    assert validate.non_positive_prices(raw, ["Open", "High", "Low", "Close"]).empty


def test_planted_12_percent_day_flagged(raw):
    close = raw["Close"].copy()
    jump_day = close.index[60]
    close[close.index >= jump_day] *= 1.12
    moves = validate.big_moves(pd.DataFrame({"X": close}), BIG_MOVE)
    assert list(moves["date"]) == [jump_day]
    assert moves["ticker"].iloc[0] == "X"
    assert moves["return"].iloc[0] == pytest.approx(1.12 * raw["Close"].iloc[60] / raw["Close"].iloc[59] - 1)


def test_nine_percent_day_not_flagged(raw):
    close = raw["Close"].copy()
    close[close.index >= close.index[60]] *= 1.09
    assert validate.big_moves(pd.DataFrame({"X": close}), BIG_MOVE).empty


def test_stale_session_detected(raw):
    frame = raw.copy()
    frame.iloc[30, frame.columns.get_indexer(["Open", "High", "Low", "Close"])] = frame.iloc[29][["Open", "High", "Low", "Close"]]
    frame.iloc[40, frame.columns.get_loc("Volume")] = 0
    stale = validate.stale_sessions(frame)
    assert list(stale.index) == [frame.index[30], frame.index[40]]
    assert stale["repeated_ohlc"].tolist() == [True, False]
    assert stale["zero_volume"].tolist() == [False, True]
    assert validate.stale_sessions(raw).empty


def test_session_gaps(sessions):
    dates = sessions.delete(10).append(pd.DatetimeIndex(["2021-06-05"]))  # one session missing, one Saturday added
    missing, extra = validate.session_gaps(dates.sort_values(), sessions)
    assert list(missing) == [sessions[10]]
    assert list(extra) == [pd.Timestamp("2021-06-05")]
    assert list(validate.weekend_dates(dates)) == [pd.Timestamp("2021-06-05")]


def test_adjustment_reconciles_with_dividends(raw):
    result = validate.adjustment_reconciliation(raw)
    assert result["events"] == 4
    assert result["total_gap"] == pytest.approx(0, abs=1e-12)
    assert result["max_event_error"] < 1e-12
    assert result["max_unexplained_step"] < 1e-12


def test_unexplained_adjustment_step_detected(raw):
    frame = raw.copy()
    frame.loc[frame.index[:150], "Adj Close"] *= 0.99  # a 1% adjustment with no dividend behind it
    result = validate.adjustment_reconciliation(frame)
    assert result["max_unexplained_step"] == pytest.approx(0.01, rel=1e-6)
    assert result["unexplained_steps_above_1e-4"] == 1
    assert abs(result["total_gap"]) == pytest.approx(-np.log(0.99), rel=1e-6)


def test_missing_dividend_breaks_reconciliation(raw):
    frame = raw.copy()
    frame["Dividends"] = 0.0  # adjusted prices still include the dividends
    result = validate.adjustment_reconciliation(frame)
    assert result["events"] == 0
    assert result["max_unexplained_step"] > 1e-3


def test_annual_gap_and_yield_positive_with_dividends(raw):
    gap = validate.annual_gap(raw["Adj Close"], raw["Close"])
    paid = validate.distribution_yield(raw)
    assert 0.01 < paid < 0.03  # 0.88 per year on a price near 50
    assert 0.01 < gap < 0.03


def test_compare_returns_uses_returns_not_levels(raw):
    first = raw["Close"]
    second = raw["Close"] * 0.8  # a different adjustment convention: same returns
    dates = raw.index[[10, 20, 30]]
    table = validate.compare_returns(first, second, dates)
    assert list(table.index) == list(dates)
    assert table["difference"].abs().max() < 1e-12


def test_sample_dates_fixed_seed(sessions):
    a = validate.sample_dates(sessions, 20, seed=42)
    b = validate.sample_dates(sessions, 20, seed=42)
    assert a.equals(b)
    assert len(a.unique()) == 20 and a.is_monotonic_increasing
    assert a.isin(sessions).all()


# Second source: import formats and the 20-date comparison on synthetic files


def _write(path, text: str):
    path.write_bytes(text.encode("utf-8"))
    return path


def test_read_second_source_standard_format(tmp_path):
    path = _write(tmp_path / "XLB.csv", "date,open,high,low,close,adj_close,volume\n"
                  "2021-01-05,10,11,9,10.5,,1000\n2021-01-04,9,10,8,9.5,9.4,2000\n")
    frame = validate.read_second_source(path)
    assert frame.index.name == "date" and list(frame.index) == [pd.Timestamp("2021-01-04"), pd.Timestamp("2021-01-05")]
    assert list(frame.columns) == validate.SECOND_SOURCE_COLUMNS[1:]
    assert (frame.dtypes == "float64").all()
    assert frame.loc["2021-01-04", "adj_close"] == 9.4 and np.isnan(frame.loc["2021-01-05", "adj_close"])


def test_read_second_source_investing_com_mapping(tmp_path):
    path = _write(tmp_path / "SPY.csv", '﻿"Date","Price","Open","High","Low","Vol.","Change %"\n'
                  '"01/05/2021","1,371.25","1,368.00","1,372.50","1,365.10","1.25M","0.24%"\n'
                  '"01/04/2021","1,368.00","1,370.00","1,375.00","1,360.00","850.30K","-1.10%"\n')
    frame = validate.read_second_source(path)
    assert list(frame.index) == [pd.Timestamp("2021-01-04"), pd.Timestamp("2021-01-05")]  # sorted ascending
    assert frame.loc["2021-01-05", "close"] == 1371.25 and frame.loc["2021-01-05", "open"] == 1368.0
    assert frame.loc["2021-01-05", "volume"] == 1.25e6 and frame.loc["2021-01-04", "volume"] == pytest.approx(850300.0)
    assert frame["adj_close"].isna().all()


def test_read_second_source_rejects_unknown_header(tmp_path):
    path = _write(tmp_path / "XLB.csv", "Date,Open,Close\n2021-01-04,1,2\n")
    with pytest.raises(ValueError, match="unrecognised columns"):
        validate.read_second_source(path)


def test_compare_second_source_finds_the_matching_convention(raw, tmp_path):
    rows = "".join(f"{d.date()},{r.Open},{r.High},{r.Low},{r.Close},,{int(r.Volume)}\n" for d, r in raw.iterrows())
    second = validate.read_second_source(_write(tmp_path / "XLB.csv", "date,open,high,low,close,adj_close,volume\n" + rows))
    ex_dates = raw.index[raw["Dividends"] > 0]  # adjusted and split-only returns differ only on ex-dividend dates
    dates = validate.sample_dates(raw.index[1:], 20, seed=42).union(ex_dates)
    table = validate.compare_second_source(raw["Adj Close"], raw["Close"], second, dates)
    error = table.groupby(["yahoo", "second_series"])["difference"].apply(lambda d: d.abs().max())
    assert error.idxmin() == ("split_only", "close")  # the file holds Yahoo's split-only close
    assert error.min() < 1e-12
    assert error[("adjusted", "close")] > 1e-4  # the dividend shows on the ex-dates
    assert len(table[table["yahoo"] == "split_only"]) == len(dates)
