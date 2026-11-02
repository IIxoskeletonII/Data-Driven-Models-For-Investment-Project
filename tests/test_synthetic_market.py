"""The shared synthetic market of tests/conftest.py follows contract 18 of docs/interfaces.md.

Only the fixtures `synthetic_market` and `synthetic_market_factory` are used; conftest is never imported.
"""

import numpy as np
import pandas as pd
import pytest

from src import contracts, data
from src.config import load_config

CFG = load_config()
SECTORS = list(CFG["data"]["tickers"])
HEDGE = CFG["data"]["hedge"]
BENCHMARK = CFG["data"]["benchmark"]
TRADABLES = SECTORS + [HEDGE, BENCHMARK]
FRED = list(CFG["data"]["fred"])
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])

FIELDS = ["sessions", "raw", "unadjusted_open", "unadjusted_close", "daily_open", "daily_close", "weekly_open",
          "weekly_close", "vix", "fred", "split", "true_beta", "drift", "is_end"]

GOOD_FRIDAYS = ["2011-04-22", "2012-04-06", "2013-03-29", "2014-04-18", "2015-04-03", "2016-03-25", "2017-04-14",
                "2018-03-30", "2019-04-19", "2020-04-10"]
HOLIDAYS = [
    "2011-12-26",  # Christmas on a Sunday, observed Monday
    "2015-07-03",  # Independence Day on a Saturday, observed Friday
    "2017-01-02",  # New Year on a Sunday, observed Monday
    "2019-01-21",  # Martin Luther King Day
    "2019-02-18",  # Presidents Day
    "2019-05-27",  # Memorial Day
    "2019-07-04",  # Independence Day
    "2019-09-02",  # Labor Day
    "2019-11-28",  # Thanksgiving
    "2019-12-25",  # Christmas
    "2012-10-29", "2012-10-30",  # closure (hurricane Sandy)
]


def columbus_days() -> list[pd.Timestamp]:
    """Second Monday of October, 2011-2020."""
    days = []
    for year in range(2011, 2021):
        mondays = pd.date_range(f"{year}-10-01", f"{year}-10-14", freq="W-MON")
        days.append(mondays[1])
    return days


def veterans_days() -> list[pd.Timestamp]:
    """11 November on a weekday, 2011-2020."""
    days = [pd.Timestamp(f"{year}-11-11") for year in range(2011, 2021)]
    return [day for day in days if day.day_of_week < 5]


def split_factor(splits: pd.Series) -> pd.Series:
    """Product of the split ratios dated strictly after each day (Yahoo's split adjustment of earlier prices)."""
    ratios = splits.fillna(0.0).replace(0.0, 1.0)
    after = ratios[::-1].cumprod()[::-1].shift(-1, fill_value=1.0)
    return after


def momentum_ic(market) -> pd.Series:
    """Weekly cross-sectional Spearman IC over the 9 sectors between ln C(t-1)/C(t-26) and fwd[t] = O(t+2)/O(t+1) - 1."""
    close, opens = market.weekly_close[SECTORS], market.weekly_open[SECTORS]
    momentum = np.log(close.shift(1) / close.shift(26))
    fwd = opens.shift(-2) / opens.shift(-1) - 1
    rows = momentum.notna().all(axis=1) & fwd.notna().all(axis=1)
    return momentum[rows].rank(axis=1).corrwith(fwd[rows].rank(axis=1), axis=1)


# ---------------------------------------------------------------- fields and calendar


def test_fields_present(synthetic_market):
    for field in FIELDS:
        assert hasattr(synthetic_market, field), field
    assert synthetic_market.is_end == IS_END == pd.Timestamp("2019-12-27")


def test_sessions_calendar(synthetic_market):
    sessions = synthetic_market.sessions
    assert isinstance(sessions, pd.DatetimeIndex) and sessions.name == "date"
    assert sessions.is_monotonic_increasing and sessions.is_unique
    assert pd.Timestamp("2011-01-03") <= sessions[0] <= pd.Timestamp("2011-01-07")
    assert pd.Timestamp("2020-12-24") <= sessions[-1] <= pd.Timestamp("2020-12-31")
    assert (sessions.day_of_week < 5).all()
    assert 2490 < len(sessions) < 2530  # about 252 sessions a year for ten years
    for day in GOOD_FRIDAYS + HOLIDAYS:
        assert pd.Timestamp(day) not in sessions, day
    for day in ["2012-10-26", "2012-10-31", "2019-12-24", "2019-12-26", "2019-12-27", "2019-12-30"]:
        assert pd.Timestamp(day) in sessions, day
    assert sessions[0] < IS_END < sessions[-1]


# ---------------------------------------------------------------- daily and weekly frames


def test_daily_frames_follow_the_contract(synthetic_market):
    m = synthetic_market
    for frame in [m.daily_open, m.daily_close]:
        contracts.validate_daily_frame(frame)
        assert list(frame.columns) == TRADABLES
        pd.testing.assert_index_equal(frame.index, m.sessions, check_names=True, exact=False)
    for frame in [m.unadjusted_open, m.unadjusted_close]:
        assert list(frame.columns) == TRADABLES
        pd.testing.assert_index_equal(frame.index, m.sessions, exact=False)


def test_daily_frames_are_adjust_ohlc_of_raw(synthetic_market):
    m = synthetic_market
    for ticker in TRADABLES:
        adjusted = data.adjust_ohlc(m.raw[ticker]).reindex(m.sessions)
        np.testing.assert_allclose(m.daily_close[ticker], adjusted["Close"], rtol=1e-12)
        np.testing.assert_allclose(m.daily_open[ticker], adjusted["Open"], rtol=1e-12)


def test_weekly_frames_follow_the_contract(synthetic_market):
    m = synthetic_market
    contracts.validate_weekly_index(m.weekly_open.index)
    contracts.validate_weekly_index(m.weekly_close.index)
    pd.testing.assert_index_equal(m.weekly_open.index, m.weekly_close.index)
    opens, close = data.weekly_panel(m.daily_open, m.daily_close)
    pd.testing.assert_frame_equal(m.weekly_open, opens)
    pd.testing.assert_frame_equal(m.weekly_close, close)
    assert IS_END in m.weekly_close.index.get_level_values("date_close")


def test_drift_is_a_weekly_sector_frame(synthetic_market):
    drift = synthetic_market.drift
    contracts.validate_weekly_index(drift.index)
    assert list(drift.columns) == SECTORS


def test_ivv_starts_two_months_late(synthetic_market):
    m = synthetic_market
    for frame in [m.daily_open, m.daily_close]:
        first = frame[HEDGE].first_valid_index()
        assert pd.Timestamp("2011-02-14") <= first <= pd.Timestamp("2011-03-15")
        assert frame[HEDGE].loc[first:].notna().all()
        assert frame.drop(columns=HEDGE).notna().all().all()


def test_true_beta(synthetic_market):
    beta = synthetic_market.true_beta
    assert set(beta) == set(TRADABLES)
    assert beta[BENCHMARK] == pytest.approx(1.0, abs=0.1)
    assert beta[HEDGE] == pytest.approx(beta[BENCHMARK], abs=0.05)


# ---------------------------------------------------------------- raw Yahoo-format data, the split and dividends


def test_raw_format(synthetic_market):
    raw = synthetic_market.raw
    assert set(raw) == set(TRADABLES)
    for ticker, frame in raw.items():
        assert list(frame.columns) == data.RAW_FIELDS, ticker


def test_exactly_one_split_xlk_two_for_one(synthetic_market):
    m = synthetic_market
    ticker, day, ratio = m.split
    assert ticker == "XLK" and ratio == 2.0
    day = pd.Timestamp(day)
    assert day in m.sessions and m.sessions[0] < day < m.sessions[-1]
    nonzero = []
    for name, frame in m.raw.items():
        splits = frame["Stock Splits"].fillna(0.0)
        nonzero += [(name, date, value) for date, value in splits[splits != 0].items()]
    assert nonzero == [("XLK", day, 2.0)]


def test_split_halves_the_traded_price_not_the_adjusted_one(synthetic_market):
    m = synthetic_market
    ticker, day, _ = m.split
    day = pd.Timestamp(day)
    before = m.sessions[m.sessions.get_loc(day) - 1]
    raw_move = m.unadjusted_close.loc[day, ticker] / m.unadjusted_close.loc[before, ticker]
    adjusted_move = m.daily_close.loc[day, ticker] / m.daily_close.loc[before, ticker]
    assert 0.4 < raw_move < 0.6
    assert 0.8 < adjusted_move < 1.25


def test_undoing_the_split_factor_gives_the_traded_prices(synthetic_market):
    m = synthetic_market
    for ticker in TRADABLES:
        raw = m.raw[ticker].dropna(subset=["Close"])
        factor = split_factor(raw["Stock Splits"])
        np.testing.assert_allclose(raw["Close"] * factor, m.unadjusted_close[ticker].loc[raw.index], rtol=1e-6)
        np.testing.assert_allclose(raw["Open"] * factor, m.unadjusted_open[ticker].loc[raw.index], rtol=1e-6)


def test_adjusted_close_follows_the_multiplicative_dividend_rule(synthetic_market):
    m = synthetic_market
    paid = 0
    for ticker in TRADABLES:
        raw = m.raw[ticker].dropna(subset=["Close"])
        factor = raw["Adj Close"] / raw["Close"]
        dividends = raw["Dividends"].fillna(0.0)
        paid += int((dividends > 0).sum())
        # factor(d-1) / factor(d) = 1 - D(d) / Close(d-1) on an ex-date d, 1 otherwise
        expected = 1 - dividends.iloc[1:].to_numpy() / raw["Close"].iloc[:-1].to_numpy()
        observed = factor.iloc[:-1].to_numpy() / factor.iloc[1:].to_numpy()
        np.testing.assert_allclose(observed, expected, rtol=1e-6, err_msg=ticker)
    assert paid > 0


# ---------------------------------------------------------------- market states


def test_vix_has_two_vix_only_dates(synthetic_market):
    m = synthetic_market
    vix = m.vix
    assert isinstance(vix, pd.Series) and vix.name == "VIX"
    assert m.sessions.isin(vix.index).all()
    extra = vix.index.difference(m.sessions)
    assert len(extra) == 2
    assert (extra.day_of_week < 5).all()


def test_fred_calendar(synthetic_market):
    fred = synthetic_market.fred
    assert list(fred.columns) == FRED
    assert (fred.index.day_of_week < 5).all()
    good_fridays = [pd.Timestamp(day) for day in GOOD_FRIDAYS if pd.Timestamp(day) in fred.index]
    assert good_fridays and fred.loc[good_fridays].notna().any(axis=1).any()
    for day in columbus_days() + veterans_days():
        assert day not in fred.index or fred.loc[day].isna().all(), day
    assert fred.isna().any().any()  # a few missing values


# ---------------------------------------------------------------- determinism and copies


def test_factory_is_deterministic(synthetic_market_factory, synthetic_market):
    a, b = synthetic_market_factory(seed=42), synthetic_market_factory(seed=42)
    pd.testing.assert_frame_equal(a.daily_close, b.daily_close)
    pd.testing.assert_frame_equal(a.raw["XLK"], b.raw["XLK"])
    pd.testing.assert_series_equal(a.vix, b.vix)
    pd.testing.assert_frame_equal(a.fred, b.fred)
    pd.testing.assert_frame_equal(synthetic_market.daily_close, synthetic_market_factory().daily_close)
    other = synthetic_market_factory(seed=7)
    assert not other.daily_close.equals(a.daily_close)


def test_fixture_is_an_independent_copy(synthetic_market, synthetic_market_factory):
    first_close = synthetic_market_factory().daily_close.iloc[0, 0]
    synthetic_market.daily_close.iloc[0, 0] = -1.0
    synthetic_market.raw["XLK"].iloc[0, 0] = -1.0
    synthetic_market.raw.pop(BENCHMARK)
    fresh = synthetic_market_factory()
    assert fresh.daily_close.iloc[0, 0] == first_close > 0
    assert fresh.raw["XLK"].iloc[0, 0] > 0
    assert BENCHMARK in fresh.raw


# ---------------------------------------------------------------- planted momentum


def test_planted_momentum(synthetic_market):
    ic = momentum_ic(synthetic_market)
    t_stat = ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic)))
    assert len(ic) > 400
    assert ic.mean() >= 0.05
    assert t_stat >= 3


def test_no_momentum_without_drift_dispersion(synthetic_market_factory):
    ic = momentum_ic(synthetic_market_factory(momentum=False))
    assert abs(ic.mean()) < 0.03


def test_no_drift_dispersion_when_momentum_is_off(synthetic_market_factory):
    drift = synthetic_market_factory(momentum=False).drift  # contract 18: "momentum=False (no drift dispersion)"
    assert (drift.std(axis=1, ddof=1).fillna(0.0) < 1e-12).all()
