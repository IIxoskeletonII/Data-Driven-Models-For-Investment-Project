"""Features of src/features.py (§06; Amendments 1 and 2; decisions S22-1 to S22-4), checked against hand computations.

Expected values are computed independently here with numpy on small constructed price series. Conventions (S22-3):
with F the Friday date_close of week t, "13 weeks ending t" are the sessions s with F − 91 days < s ≤ F and "52 weeks"
those with F − 364 days < s ≤ F; a daily simple return belongs to a window when its end session does; TR(t − k w) is
the close of the last session of the calendar week ending F − 7k days (Thursday when that Friday is a holiday).
Full-window rule (S22-4): NaN unless the session calendar starts before the window and every close it needs exists.
Market series enter lagged one session (Amendment 1, S22-2).
"""

import numpy as np
import pandas as pd
import pytest

from src import contracts, features
from src.config import load_config
from src.data import weekly_panel

CFG = load_config()
UNIVERSE = contracts.universe(CFG)
SECTORS = list(UNIVERSE.sectors)
HEDGE = UNIVERSE.hedge
BENCHMARK = UNIVERSE.benchmark
TRADED = list(UNIVERSE.traded)
TRADABLES = list(UNIVERSE.tradables)
ASSET = list(CFG["features"]["asset"])
STATES = list(CFG["features"]["states"])
LOOKBACKS = list(CFG["models"]["M0_star"]["lookback_weeks"])  # 13, 26, 52
MKT_VAR_DAYS = CFG["features"]["mkt_var_days"]  # 126
DAY = pd.Timedelta(days=1)

# US equity holidays 2015 - mid 2018: Monday holidays, Good Fridays (2015-04-03, 2016-03-25, 2017-04-14, 2018-03-30),
# Friday holidays (2015-07-03, 2015-12-25, 2016-01-01), Thursday Thanksgivings and a Tuesday Independence Day
HOLIDAYS = ["2015-01-19", "2015-02-16", "2015-04-03", "2015-05-25", "2015-07-03", "2015-09-07", "2015-11-26", "2015-12-25",
            "2016-01-01", "2016-01-18", "2016-02-15", "2016-03-25", "2016-05-30", "2016-07-04", "2016-09-05", "2016-11-24",
            "2016-12-26", "2017-01-02", "2017-01-16", "2017-02-20", "2017-04-14", "2017-05-29", "2017-07-04", "2017-09-04",
            "2017-11-23", "2017-12-25", "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28"]
# FRED publishes on Good Friday but not on Columbus Day or Veterans Day
FRED_CLOSED = ["2015-10-12", "2015-11-11", "2016-10-10", "2016-11-11", "2017-10-09", "2017-11-10"]


def ts(day) -> pd.Timestamp:
    return pd.Timestamp(day)


def make_sessions(start: str = "2015-01-05", end: str = "2018-06-29") -> pd.DatetimeIndex:
    """Business days minus the holidays above, named `date` (the first session is Monday 2015-01-05)."""
    return pd.bdate_range(start, end).difference(pd.DatetimeIndex(HOLIDAYS)).rename("date")


def make_close(sessions: pd.DatetimeIndex | None = None, seed: int = 0) -> pd.DataFrame:
    """Adjusted daily closes (contract 1) of the 11 tradables: independent lognormal random walks."""
    sessions = make_sessions() if sessions is None else sessions
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0003, 0.012, (len(sessions), len(TRADABLES)))
    starts = np.linspace(30.0, 80.0, len(TRADABLES))
    return pd.DataFrame(starts * np.exp(np.cumsum(steps, axis=0)), index=sessions, columns=TRADABLES)


def make_market_series(sessions: pd.DatetimeIndex) -> tuple[pd.Series, pd.DataFrame]:
    """Raw, unlagged VIX (sessions plus two VIX-only prints) and FRED series (FRED business days, one gap)."""
    vix = pd.Series(10.0 + 0.001 * np.arange(len(sessions)), index=sessions, name="VIX")
    vix_only = pd.Series([77.0, 99.0], index=pd.DatetimeIndex([ts("2016-11-24"), ts("2017-04-14")]), name="VIX")
    vix = pd.concat([vix, vix_only]).sort_index()  # prints on Thanksgiving and Good Friday (not sessions)
    fred_days = pd.bdate_range(sessions[0], sessions[-1]).difference(pd.DatetimeIndex(FRED_CLOSED))
    m = len(fred_days)
    fred = pd.DataFrame({"DGS3MO": 0.5 + 0.0001 * np.arange(m), "DGS10": 2.0 + 0.0003 * np.arange(m),
                         "BAA10Y": 3.0 + 0.0002 * np.arange(m)}, index=fred_days)
    fred.loc[ts("2017-06-29"), "DGS10"] = np.nan  # DGS10 missing on a Thursday when DGS3MO and BAA10Y publish
    return vix, fred


# ---------------------------------------------------------------- independent reference computations


def last_session_of_week(sessions: pd.DatetimeIndex, friday) -> pd.Timestamp | None:
    """Last session of the calendar week ending on `friday` (Friday, or Thursday when Friday is a holiday)."""
    friday = ts(friday)
    in_week = sessions[(sessions > friday - 7 * DAY) & (sessions <= friday)]
    return in_week[-1] if len(in_week) else None


def tr_lag(close: pd.Series, friday, k: int) -> float:
    """TR(t − k w): close of the last session of the week ending F − 7k days; NaN if that week has no session."""
    session = last_session_of_week(close.index, ts(friday) - 7 * k * DAY)
    return np.nan if session is None else float(close[session])


def window_positions(sessions: pd.DatetimeIndex, friday, days: int) -> np.ndarray:
    friday = ts(friday)
    return np.flatnonzero((sessions > friday - days * DAY) & (sessions <= friday))


def window_returns(close: pd.Series, friday, days: int) -> np.ndarray:
    """Daily simple returns whose end session lies in the window; the first uses the close before the window."""
    positions = window_positions(close.index, friday, days)
    assert positions[0] >= 1, "test setup: the window must not start at the first session"
    values = close.to_numpy(dtype=np.float64)
    return values[positions] / values[positions - 1] - 1


def expected_raw(close: pd.DataFrame, friday, ticker: str) -> dict[str, float]:
    """The six raw asset features of contract 3 / S22-1 for one sector and week, computed with numpy."""
    c, spy = close[ticker], close[BENCHMARK]
    r_i, r_m = window_returns(c, friday, 364), window_returns(spy, friday, 364)
    return {
        "MOM26_1": np.log(tr_lag(c, friday, 1)) - np.log(tr_lag(c, friday, 26)),
        "MOM52_4": np.log(tr_lag(c, friday, 4)) - np.log(tr_lag(c, friday, 52)),
        "REV1": np.log(tr_lag(c, friday, 0)) - np.log(tr_lag(c, friday, 1)),
        "VOL13": np.std(window_returns(c, friday, 91), ddof=1) * np.sqrt(252),
        "DD13": tr_lag(c, friday, 0) / c.to_numpy()[window_positions(c.index, friday, 91)].max() - 1,
        "BETA52": np.cov(r_i, r_m, ddof=1)[0, 1] / np.var(r_m, ddof=1),
    }


def zscore(values: np.ndarray) -> np.ndarray:
    return (values - values.mean()) / values.std(ddof=1)


def week_rows(frame: pd.DataFrame, friday) -> pd.DataFrame:
    """The 9 sector rows of one date_close, in sector order."""
    rows = frame.xs(ts(friday), level="date_close")
    return rows.loc[SECTORS]


def week_tuples(index: pd.MultiIndex) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    return [(ts(a), ts(b)) for a, b in index]


def state_at(states: pd.DataFrame, friday, column: str) -> float:
    return float(states.xs(ts(friday), level="date_close")[column].iloc[0])


@pytest.fixture(scope="module")
def close() -> pd.DataFrame:
    return make_close()


@pytest.fixture(scope="module")
def raw(close) -> pd.DataFrame:
    return features.raw_asset_features(close.copy())


# ---------------------------------------------------------------- calendar helpers


def test_weekly_index_equals_weekly_panel_index_on_synthetic_market(synthetic_market):
    index = features.weekly_index(synthetic_market.sessions)
    contracts.validate_weekly_index(index)
    assert week_tuples(index) == week_tuples(synthetic_market.weekly_close.index)


def test_weekly_index_equals_weekly_panel_index_with_holidays(close):
    index = features.weekly_index(close.index)
    contracts.validate_weekly_index(index)
    _, weekly_close = weekly_panel(close, close)
    assert week_tuples(index) == week_tuples(weekly_close.index)
    assert (ts("2017-01-16"), ts("2017-01-20")) in week_tuples(index)  # Monday holiday: nominal Monday kept
    assert (ts("2017-04-10"), ts("2017-04-14")) in week_tuples(index)  # Good Friday: nominal Friday kept


def test_last_sessions_is_thursday_when_friday_is_a_holiday(close):
    last = features.last_sessions(close.index)
    assert list(pd.DatetimeIndex(last.index)) == list(pd.DatetimeIndex(features.weekly_index(close.index).get_level_values(1)))
    assert ts(last.loc[ts("2017-04-14")]) == ts("2017-04-13")  # Good Friday
    assert ts(last.loc[ts("2015-07-03")]) == ts("2015-07-02")  # Independence Day observed on a Friday
    assert ts(last.loc[ts("2017-06-30")]) == ts("2017-06-30")
    assert ts(last.loc[ts("2017-01-20")]) == ts("2017-01-20")  # Monday-holiday week still ends on Friday


# ---------------------------------------------------------------- raw asset features: hand computations


def test_raw_features_index_columns_and_contract(close, raw):
    fridays = pd.DatetimeIndex(features.weekly_index(close.index).get_level_values("date_close"))
    expected = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    assert list(raw.index) == list(expected)
    assert list(raw.columns) == ASSET
    assert all(raw[c].dtype == np.float64 for c in ASSET)
    contracts.validate_features(raw)


@pytest.mark.parametrize("friday", ["2017-06-30", "2017-04-14", "2017-04-21", "2017-05-12", "2016-01-08", "2018-01-05"])
@pytest.mark.parametrize("feature", ["MOM26_1", "MOM52_4", "REV1", "VOL13", "DD13", "BETA52"])
def test_raw_feature_matches_hand_computation(close, raw, feature, friday):
    expected = np.array([expected_raw(close, friday, ticker)[feature] for ticker in SECTORS])
    actual = week_rows(raw, friday)[feature].to_numpy()
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-13)


def test_tr_lag_uses_thursday_when_that_friday_is_a_holiday(close, raw):
    xlb = close[SECTORS[0]]
    # week t = 2017-04-21 follows Good Friday 2017-04-14: TR(t − 1w) is Thursday 2017-04-13's close
    rev1 = np.log(xlb[ts("2017-04-21")]) - np.log(xlb[ts("2017-04-13")])
    mom26 = np.log(xlb[ts("2017-04-13")]) - np.log(xlb[ts("2016-10-21")])
    # week t = 2017-04-14 itself: TR(t) is Thursday's close
    rev1_holiday_week = np.log(xlb[ts("2017-04-13")]) - np.log(xlb[ts("2017-04-07")])
    # week t = 2017-05-12: TR(t − 4w) is in the Good Friday week
    mom52_4 = np.log(xlb[ts("2017-04-13")]) - np.log(xlb[ts("2016-05-13")])
    row = raw.loc[(ts("2017-04-21"), SECTORS[0])]
    assert row["REV1"] == pytest.approx(rev1, rel=1e-12)
    assert row["MOM26_1"] == pytest.approx(mom26, rel=1e-12)
    assert raw.loc[(ts("2017-04-14"), SECTORS[0]), "REV1"] == pytest.approx(rev1_holiday_week, rel=1e-12)
    assert raw.loc[(ts("2017-05-12"), SECTORS[0]), "MOM52_4"] == pytest.approx(mom52_4, rel=1e-12)


def test_vol13_uses_simple_returns_over_13_calendar_weeks_with_holiday_weeks(close, raw):
    friday = ts("2017-06-30")
    xlb = close[SECTORS[0]]
    window = close.index[(close.index > friday - 91 * DAY) & (close.index <= friday)]
    assert window[0] == ts("2017-04-03") and len(window) == 63  # 65 weekdays minus Good Friday and Memorial Day
    values = xlb.to_numpy()
    positions = close.index.get_indexer(window)
    simple = values[positions] / values[positions - 1] - 1  # the first return uses Friday 2017-03-31's close
    expected = np.std(simple, ddof=1) * np.sqrt(252)
    log_based = np.std(np.log1p(simple), ddof=1) * np.sqrt(252)
    assert abs(expected - log_based) > 1e-8  # the data separate simple from log returns
    assert raw.loc[(friday, SECTORS[0]), "VOL13"] == pytest.approx(expected, rel=1e-10)


def single_return_bumped(close: pd.DataFrame, ticker: str, session, factor: float = 1.05) -> pd.DataFrame:
    """Change only the daily return ending at `session`: scale that close and every later close of `ticker`."""
    bumped = close.copy()
    bumped.loc[bumped.index >= ts(session), ticker] *= factor
    return bumped


def test_vol13_window_excludes_the_return_ending_on_friday_minus_91_days(close, raw):
    friday, ticker = ts("2017-06-30"), SECTORS[0]
    base = raw.loc[(friday, ticker), "VOL13"]
    outside = features.raw_asset_features(single_return_bumped(close, ticker, "2017-03-31"))
    inside = features.raw_asset_features(single_return_bumped(close, ticker, "2017-04-03"))
    assert outside.loc[(friday, ticker), "VOL13"] == pytest.approx(base, rel=1e-9)
    assert abs(inside.loc[(friday, ticker), "VOL13"] - base) > 1e-4


def test_dd13_uses_the_maximum_over_the_13_week_window_only(close):
    friday, ticker = ts("2017-06-30"), SECTORS[0]
    planted = close.copy()
    planted.loc[ts("2017-03-31"), ticker] = 5000.0  # F − 91 days: outside the window
    planted.loc[ts("2017-05-10"), ticker] = 1000.0  # the window maximum
    raw_planted = features.raw_asset_features(planted)
    expected = planted.loc[friday, ticker] / 1000.0 - 1
    assert raw_planted.loc[(friday, ticker), "DD13"] == pytest.approx(expected, rel=1e-12)
    # in the Good Friday week TR(t) is Thursday's close
    expected_holiday = planted.loc[ts("2017-04-13"), ticker] / planted.loc[window_positions_index(planted, "2017-04-14"), ticker].max() - 1
    assert raw_planted.loc[(ts("2017-04-14"), ticker), "DD13"] == pytest.approx(expected_holiday, rel=1e-12)


def window_positions_index(close: pd.DataFrame, friday) -> pd.DatetimeIndex:
    return close.index[window_positions(close.index, friday, 91)]


def planted_beta_close(friday="2017-06-30") -> tuple[pd.DataFrame, dict[str, float]]:
    """Sector j: r_j = m_j · r_SPY inside the 52 weeks ending `friday`, −m_j · r_SPY + noise before; IVV: 0.5 · r_SPY."""
    sessions = make_sessions()
    rng = np.random.default_rng(7)
    r_spy = rng.normal(0.0003, 0.01, len(sessions))
    inside = (sessions > ts(friday) - 364 * DAY) & (sessions <= ts(friday))
    multipliers = {ticker: 0.5 + 0.25 * j for j, ticker in enumerate(SECTORS)}
    returns = {}
    for ticker, m in multipliers.items():
        returns[ticker] = np.where(inside, m * r_spy, -m * r_spy + rng.normal(0, 0.005, len(sessions)))
    returns[HEDGE] = 0.5 * r_spy
    returns[BENCHMARK] = r_spy
    frame = {}
    for ticker in TRADABLES:
        r = returns[ticker].copy()
        r[0] = 0.0
        frame[ticker] = 50.0 * np.cumprod(1 + r)
    return pd.DataFrame(frame, index=sessions)[TRADABLES], multipliers


def test_beta52_recovers_a_planted_beta_over_exactly_52_weeks():
    friday = ts("2017-06-30")
    planted, multipliers = planted_beta_close(friday)
    raw_planted = features.raw_asset_features(planted)
    actual = week_rows(raw_planted, friday)["BETA52"].to_numpy()
    np.testing.assert_allclose(actual, [multipliers[t] for t in SECTORS], rtol=0, atol=1e-9)
    assert multipliers[SECTORS[0]] == 0.5 and multipliers[SECTORS[6]] == 2.0  # XLU: returns are 2 × SPY's


def test_sizing_betas_planted_and_contract():
    friday = ts("2017-06-30")
    planted, multipliers = planted_beta_close(friday)
    betas = features.sizing_betas(planted)
    contracts.validate_betas(betas)
    assert list(betas.columns) == TRADED
    assert week_tuples(betas.index) == week_tuples(features.weekly_index(planted.index))
    row = betas.xs(friday, level="date_close").iloc[0]
    np.testing.assert_allclose(row[SECTORS].to_numpy(), [multipliers[t] for t in SECTORS], rtol=0, atol=1e-9)
    assert row[HEDGE] == pytest.approx(0.5, abs=1e-9)
    later = betas.xs(ts("2018-03-02"), level="date_close").iloc[0]
    assert later[HEDGE] == pytest.approx(0.5, abs=1e-9)


def test_sizing_betas_sector_columns_equal_raw_beta52(close, raw):
    betas = features.sizing_betas(close)
    unstacked = raw["BETA52"].unstack("ticker")[SECTORS]
    np.testing.assert_allclose(betas[SECTORS].to_numpy(), unstacked.to_numpy(), rtol=1e-12, atol=1e-14, equal_nan=True)


# ---------------------------------------------------------------- full-window rule (S22-4)


@pytest.mark.parametrize("feature, nan_friday, first_friday", [
    ("REV1", "2015-01-09", "2015-01-16"),  # TR(t − 1w) of the first week has no session
    ("VOL13", "2015-04-03", "2015-04-10"),  # calendar must hold a session dated <= F − 91 days
    ("DD13", "2015-04-03", "2015-04-10"),  # same rule although the partial window could be computed
    ("MOM26_1", "2015-07-03", "2015-07-10"),  # week ending F − 182 days has a session from 2015-07-10
    ("MOM52_4", "2016-01-01", "2016-01-08"),
    ("BETA52", "2016-01-01", "2016-01-08"),  # calendar must hold a session dated <= F − 364 days
])
def test_feature_is_nan_until_its_window_is_full(raw, feature, nan_friday, first_friday):
    assert week_rows(raw, nan_friday)[feature].isna().all()
    assert week_rows(raw, first_friday)[feature].notna().all()


def test_beta_is_nan_until_the_window_has_every_close_of_a_late_starting_ticker(close):
    late = close.copy()
    late.loc[late.index < ts("2015-06-01"), HEDGE] = np.nan  # IVV starts on Monday 2015-06-01
    betas = features.sizing_betas(late)
    hedge = betas[HEDGE].droplevel("date_open")
    # 2016-05-27: the first window return (ending 2015-06-01) needs the missing close of 2015-05-29
    assert np.isnan(hedge.loc[ts("2016-05-27")])
    assert np.isfinite(hedge.loc[ts("2016-06-03")])
    assert hedge.loc[: ts("2016-05-27")].isna().all()


# ---------------------------------------------------------------- cross-sectional z-scores


def zscore_input() -> pd.DataFrame:
    fridays = pd.DatetimeIndex(["2017-06-02", "2017-06-09", "2017-06-16"])
    index = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(rng.normal(size=(len(index), 2)), index=index, columns=["A", "B"])
    frame.loc[fridays[1], "A"] = 0.7  # every sector equal
    frame.loc[(fridays[2], SECTORS[4]), "A"] = np.nan  # one sector missing
    return frame


def test_cross_sectional_zscore_hand_values():
    frame = zscore_input()
    z = features.cross_sectional_zscore(frame.copy())
    assert list(z.index) == list(frame.index) and list(z.columns) == ["A", "B"]
    first = frame.xs(ts("2017-06-02"), level="date_close")
    np.testing.assert_allclose(z.xs(ts("2017-06-02"), level="date_close")["A"].to_numpy(), zscore(first["A"].to_numpy()),
                               rtol=1e-12, atol=1e-14)
    for friday in ["2017-06-02", "2017-06-09", "2017-06-16"]:
        b = z.xs(ts(friday), level="date_close")["B"].to_numpy()
        assert b.mean() == pytest.approx(0.0, abs=1e-12)
        assert b.std(ddof=1) == pytest.approx(1.0, rel=1e-12)


def test_cross_sectional_zscore_all_equal_week_is_zero():
    z = features.cross_sectional_zscore(zscore_input())
    equal = z.xs(ts("2017-06-09"), level="date_close")["A"].to_numpy()
    assert np.array_equal(equal, np.zeros(len(SECTORS)))


def test_cross_sectional_zscore_one_missing_sector_blanks_the_week():
    z = features.cross_sectional_zscore(zscore_input())
    week = z.xs(ts("2017-06-16"), level="date_close")
    assert week["A"].isna().all()
    assert week["B"].notna().all()


def test_asset_features_are_zscores_of_the_hand_raw_values(close):
    friday = ts("2017-06-30")
    z = features.asset_features(close)
    contracts.validate_features(z)
    actual = week_rows(z, friday)
    for feature in ASSET:
        raw_values = np.array([expected_raw(close, friday, ticker)[feature] for ticker in SECTORS])
        np.testing.assert_allclose(actual[feature].to_numpy(), zscore(raw_values), rtol=1e-9, atol=1e-11)


def test_asset_features_moments_on_complete_weeks(synthetic_market):
    z = features.asset_features(synthetic_market.daily_close)
    contracts.validate_features(z)
    grouped = z.groupby(level="date_close")
    complete = grouped.count().eq(len(SECTORS)).all(axis=1)
    assert complete.sum() > 300
    means = grouped.mean()[complete]
    stds = grouped.std(ddof=1)[complete].to_numpy()
    # zero raw dispersion (e.g. every sector at its 13-week high, DD13 = 0) gives z = 0 for the whole week
    flat = (grouped.apply(lambda week: (week == 0.0).all())[complete]).to_numpy()
    np.testing.assert_allclose(means.to_numpy(), 0.0, atol=1e-12)
    np.testing.assert_allclose(stds[~flat], 1.0, rtol=1e-12)
    assert (stds[flat] == 0.0).all()


# ---------------------------------------------------------------- momentum variants (M0* fallback)


def test_momentum_variants_columns_contract_and_hand_value(close):
    variants = features.momentum_variants(close)
    columns = [f"MOM{lookback}_1" for lookback in LOOKBACKS]
    assert columns == ["MOM13_1", "MOM26_1", "MOM52_1"]
    contracts.validate_features(variants, columns=columns)
    friday = ts("2017-06-30")
    for lookback in LOOKBACKS:
        raw_values = np.array([np.log(tr_lag(close[t], friday, 1)) - np.log(tr_lag(close[t], friday, lookback))
                               for t in SECTORS])
        np.testing.assert_allclose(week_rows(variants, friday)[f"MOM{lookback}_1"].to_numpy(), zscore(raw_values),
                                   rtol=1e-9, atol=1e-11)
    z = features.asset_features(close)
    np.testing.assert_allclose(variants["MOM26_1"].to_numpy(), z["MOM26_1"].to_numpy(), rtol=1e-12, atol=1e-14,
                               equal_nan=True)


# ---------------------------------------------------------------- market states


def bear_close() -> pd.DataFrame:
    """SPY flat at 100 until Tuesday 2017-06-13, then 50 from Wednesday 2017-06-14."""
    planted = make_close()
    planted[BENCHMARK] = np.where(planted.index < ts("2017-06-14"), 100.0, 50.0)
    return planted


def test_bear24_flips_from_zero_to_one_at_a_known_week():
    planted = bear_close()
    vix, fred = make_market_series(planted.index)
    states = features.market_states(planted, vix, fred)
    contracts.validate_market_states(states)
    bear = states["BEAR24"].droplevel("date_open")
    # TR_SPY(t − 104 w) is in the week ending F − 728 days: no session there before 2017-01-06
    assert np.isnan(bear.loc[ts("2016-12-30")])
    assert bear.loc[: ts("2016-12-30")].isna().all()
    # ratio exactly 1 → not negative → 0
    assert (bear.loc[ts("2017-01-06"): ts("2017-06-09")] == 0.0).all()
    # the week containing the drop and every later week of the sample: 50 / 100 − 1 < 0
    assert (bear.loc[ts("2017-06-16"):] == 1.0).all()


def test_mkt_var_is_the_sample_variance_of_the_last_126_daily_returns(close):
    vix, fred = make_market_series(close.index)
    states = features.market_states(close, vix, fred)
    spy = close[BENCHMARK].to_numpy()
    for friday in ["2017-06-30", "2017-04-14"]:
        last = last_session_of_week(close.index, friday)
        p = close.index.get_loc(last)
        returns = spy[p - MKT_VAR_DAYS + 1: p + 1] / spy[p - MKT_VAR_DAYS: p] - 1
        assert len(returns) == 126
        assert state_at(states, friday, "MKT_VAR") == pytest.approx(np.var(returns, ddof=1), rel=1e-10)


def test_mkt_var_uses_exactly_126_returns(close):
    friday = ts("2017-06-30")
    vix, fred = make_market_series(close.index)
    p = close.index.get_loc(friday)
    base = state_at(features.market_states(close, vix, fred), friday, "MKT_VAR")
    session_127 = close.index[p - MKT_VAR_DAYS]  # end session of the 127th return back: outside
    session_126 = close.index[p - MKT_VAR_DAYS + 1]  # end session of the 126th return back: inside
    outside = features.market_states(single_return_bumped(close, BENCHMARK, session_127, 1.2), vix, fred)
    inside = features.market_states(single_return_bumped(close, BENCHMARK, session_126, 1.2), vix, fred)
    assert state_at(outside, friday, "MKT_VAR") == pytest.approx(base, rel=1e-9)
    assert abs(state_at(inside, friday, "MKT_VAR") - base) > 1e-6


def test_mkt_var_needs_127_closes(close):
    vix, fred = make_market_series(close.index)
    states = features.market_states(close, vix, fred)
    mkt_var = states["MKT_VAR"].droplevel("date_open")
    last = features.last_sessions(close.index)
    positions = close.index.get_indexer(pd.DatetimeIndex(last.to_numpy()))
    full = positions >= MKT_VAR_DAYS  # 127 closes at positions p − 126 … p
    assert mkt_var[~full].isna().all()
    assert mkt_var[full].notna().all()


def test_vix_term_credit_are_lagged_one_session(close):
    vix, fred = make_market_series(close.index)
    states = features.market_states(close, vix, fred)
    assert list(states.columns) == STATES
    contracts.validate_market_states(states)
    # Good Friday week: last session Thursday 04-13, so VIX is Wednesday 04-12's print (never the VIX-only Friday print)
    assert state_at(states, "2017-04-14", "VIX") == vix[ts("2017-04-12")]
    assert state_at(states, "2017-04-21", "VIX") == vix[ts("2017-04-20")]
    assert state_at(states, "2017-06-30", "VIX") == vix[ts("2017-06-29")]
    # Friday after Thanksgiving: previous session Wednesday 11-23; the Thursday VIX-only print is not used
    assert state_at(states, "2016-11-25", "VIX") == vix[ts("2016-11-23")]
    # each FRED series lagged on its own: DGS10 is missing on Thursday 06-29, so it carries Wednesday 06-28
    term = fred.loc[ts("2017-06-28"), "DGS10"] - fred.loc[ts("2017-06-29"), "DGS3MO"]
    assert state_at(states, "2017-06-30", "TERM") == pytest.approx(term, rel=1e-12)
    assert state_at(states, "2017-06-30", "CREDIT") == fred.loc[ts("2017-06-29"), "BAA10Y"]
    # Friday 2016-11-11 (Veterans Day, a session): previous session Thursday 11-10 has FRED values
    assert state_at(states, "2016-11-11", "CREDIT") == fred.loc[ts("2016-11-10"), "BAA10Y"]
    # Friday 2016-11-18: previous session Thursday 11-17
    assert state_at(states, "2016-11-18", "CREDIT") == fred.loc[ts("2016-11-17"), "BAA10Y"]


def test_market_states_good_friday_vix_uses_wednesday(synthetic_market):
    """Synthetic market: Good Friday 2015-04-03 has a VIX-only print; the week's VIX is Wednesday 2015-04-01's."""
    m = synthetic_market
    states = features.market_states(m.daily_close, m.vix, m.fred)
    contracts.validate_market_states(states)
    assert state_at(states, "2015-04-03", "VIX") == m.vix[ts("2015-04-01")]
    assert state_at(states, "2015-04-10", "VIX") == m.vix[ts("2015-04-09")]


# ---------------------------------------------------------------- lag_one_session (S22-2)

LAG_HOLIDAYS = ["2021-04-02", "2021-05-31", "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24"]


def lag_sessions() -> pd.DatetimeIndex:
    """2021 equity sessions from March: Good Friday and Memorial Day closed; Columbus Day and Veterans Day open."""
    return pd.bdate_range("2021-03-01", "2021-12-31").difference(pd.DatetimeIndex(LAG_HOLIDAYS)).rename("date")


def series(values: dict, name: str = "X") -> pd.Series:
    return pd.Series(list(values.values()), index=pd.DatetimeIndex([ts(d) for d in values]), name=name, dtype=np.float64)


def test_lag_monday_after_a_friday_holiday_uses_thursday():
    sessions = lag_sessions()
    observed = series({"2021-03-31": 1.0, "2021-04-01": 2.0, "2021-04-02": 3.0, "2021-04-05": np.nan, "2021-04-06": 5.0})
    lagged = features.lag_one_session(observed, sessions)
    assert lagged[ts("2021-04-01")] == 1.0
    assert lagged[ts("2021-04-05")] == 2.0  # Monday: previous session Thursday 04-01; the Good Friday print is later
    assert lagged[ts("2021-04-06")] == 3.0  # previous session 04-05 has no value: the Good Friday print is the last one
    assert lagged[ts("2021-04-07")] == 5.0


@pytest.mark.parametrize("with_nan_row", [False, True])
def test_lag_thursday_veterans_day_carries_wednesday(with_nan_row):
    sessions = lag_sessions()
    values = {"2021-11-08": 1.0, "2021-11-09": 2.0, "2021-11-10": 3.0, "2021-11-12": 5.0, "2021-11-15": 6.0}
    if with_nan_row:
        values["2021-11-11"] = np.nan
    observed = series(values).sort_index()
    lagged = features.lag_one_session(observed, sessions)
    assert ts("2021-11-11") in sessions
    assert lagged[ts("2021-11-11")] == 3.0
    assert lagged[ts("2021-11-12")] == 3.0  # Wednesday's value, never Friday's own
    assert lagged[ts("2021-11-15")] == 5.0


def test_lag_columbus_day_monday():
    sessions = lag_sessions()
    observed = series({"2021-10-07": 1.0, "2021-10-08": 2.0, "2021-10-12": 4.0, "2021-10-13": 5.0})
    lagged = features.lag_one_session(observed, sessions)
    assert lagged[ts("2021-10-11")] == 2.0
    assert lagged[ts("2021-10-12")] == 2.0  # Tuesday: previous session Columbus Monday has no value → Friday 10-08
    assert lagged[ts("2021-10-13")] == 4.0


def test_lag_non_session_observation_is_not_used_early():
    sessions = lag_sessions()
    observed = series({"2021-05-27": 0.5, "2021-05-28": 1.0, "2021-05-31": 2.0, "2021-06-01": 3.0}, name="VIX")
    lagged = features.lag_one_session(observed, sessions)
    assert lagged[ts("2021-06-01")] == 1.0  # previous session Friday 05-28; the Memorial Day print is not yet usable
    assert lagged[ts("2021-06-02")] == 3.0
    only_holiday = series({"2021-05-27": 0.5, "2021-05-28": 1.0, "2021-05-31": 2.0}, name="VIX")
    lagged = features.lag_one_session(only_holiday, sessions)
    assert lagged[ts("2021-06-01")] == 1.0
    assert lagged[ts("2021-06-02")] == 2.0  # used once the previous session (06-01) is on or after its date


def test_lag_first_session_and_before_first_observation_are_nan():
    sessions = lag_sessions()
    early = series({"2021-01-04": 1.0, "2021-02-26": 2.0, "2021-03-01": 3.0, "2021-03-02": 4.0})
    lagged = features.lag_one_session(early, sessions)
    assert np.isnan(lagged[sessions[0]])
    assert lagged[ts("2021-03-02")] == 3.0
    late = series({"2021-03-10": 7.0, "2021-03-12": 8.0})
    lagged = features.lag_one_session(late, sessions)
    assert lagged.loc[: ts("2021-03-10")].isna().all()
    assert lagged[ts("2021-03-11")] == 7.0
    assert lagged[ts("2021-03-12")] == 7.0
    assert lagged[ts("2021-03-15")] == 8.0


def test_lag_returns_float64_on_sessions_with_the_same_name():
    sessions = lag_sessions()
    observed = pd.Series(np.arange(10, dtype=np.int64), index=pd.bdate_range("2021-03-01", periods=10), name="DGS10")
    lagged = features.lag_one_session(observed, sessions)
    assert lagged.dtype == np.float64
    assert lagged.name == "DGS10"
    assert list(pd.DatetimeIndex(lagged.index)) == list(sessions)


def reference_lag(observed: pd.Series, sessions: pd.DatetimeIndex) -> np.ndarray:
    """Brute force: last non-missing observation dated on or before the previous session."""
    present = observed.dropna().sort_index()
    out = np.full(len(sessions), np.nan)
    for i in range(1, len(sessions)):
        eligible = present[present.index <= sessions[i - 1]]
        if len(eligible):
            out[i] = eligible.iloc[-1]
    return out


def test_lag_matches_brute_force_on_random_dates():
    sessions = lag_sessions()
    rng = np.random.default_rng(11)
    days = pd.date_range("2021-02-15", "2022-01-10")  # includes weekends and holidays
    chosen = np.sort(rng.choice(len(days), size=200, replace=False))
    values = rng.normal(size=200)
    values[rng.random(200) < 0.1] = np.nan
    observed = pd.Series(values, index=days[chosen], name="X")
    lagged = features.lag_one_session(observed, sessions)
    np.testing.assert_array_equal(lagged.to_numpy(), reference_lag(observed, sessions))


# ---------------------------------------------------------------- look-ahead perturbation and contracts


def rows_through(frame: pd.DataFrame, t: pd.Timestamp) -> pd.DataFrame:
    return frame[pd.DatetimeIndex(frame.index.get_level_values("date_close")) <= t]


def rows_after(frame: pd.DataFrame, t: pd.Timestamp) -> pd.DataFrame:
    return frame[pd.DatetimeIndex(frame.index.get_level_values("date_close")) > t]


def all_outputs(close: pd.DataFrame, vix: pd.Series, fred: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "raw": features.raw_asset_features(close),
        "features": features.asset_features(close),
        "momentum_variants": features.momentum_variants(close),
        "market_states": features.market_states(close, vix, fred),
        "sizing_betas": features.sizing_betas(close),
    }


def test_outputs_up_to_t_ignore_any_change_after_t(synthetic_market):
    """Closes after Friday t and market series dated on or after t (lagged one session) are randomly rescaled."""
    m = synthetic_market
    t = ts("2016-06-17")
    rng = np.random.default_rng(5)
    close = m.daily_close.copy()
    after = close.index > t
    close.loc[after] = close.loc[after].to_numpy() * rng.uniform(0.5, 1.5, (int(after.sum()), close.shape[1]))
    vix = m.vix.copy()
    vix[vix.index >= t] = vix[vix.index >= t].to_numpy() * rng.uniform(0.5, 1.5, int((vix.index >= t).sum()))
    fred = m.fred.copy()
    later = fred.index >= t
    fred.loc[later] = fred.loc[later].to_numpy() * rng.uniform(0.5, 1.5, (int(later.sum()), fred.shape[1]))

    base = all_outputs(m.daily_close, m.vix, m.fred)
    perturbed = all_outputs(close, vix, fred)
    for name in base:
        a, b = rows_through(base[name], t), rows_through(perturbed[name], t)
        assert a.index.equals(b.index), name
        assert np.array_equal(a.to_numpy(dtype=np.float64), b.to_numpy(dtype=np.float64), equal_nan=True), name
        assert np.isfinite(a.to_numpy(dtype=np.float64)).any(), name
        later_a, later_b = rows_after(base[name], t), rows_after(perturbed[name], t)
        assert not np.array_equal(later_a.to_numpy(dtype=np.float64), later_b.to_numpy(dtype=np.float64),
                                  equal_nan=True), name


def test_every_output_passes_its_validator_on_the_synthetic_market(synthetic_market):
    m = synthetic_market
    weeks = features.weekly_index(m.daily_close.index)
    outputs = all_outputs(m.daily_close, m.vix, m.fred)
    contracts.validate_features(outputs["raw"])
    contracts.validate_features(outputs["features"])
    contracts.validate_features(outputs["momentum_variants"], columns=[f"MOM{lookback}_1" for lookback in LOOKBACKS])
    contracts.validate_market_states(outputs["market_states"])
    contracts.validate_betas(outputs["sizing_betas"])
    assert week_tuples(outputs["market_states"].index) == week_tuples(weeks)
    assert week_tuples(outputs["sizing_betas"].index) == week_tuples(weeks)
    fridays = list(pd.DatetimeIndex(weeks.get_level_values("date_close")))
    for name in ("raw", "features", "momentum_variants"):
        index = outputs[name].index
        assert list(pd.DatetimeIndex(index.get_level_values("date_close").unique())) == fridays, name
    # BEAR24 and all the states are defined after the 104-week warm-up of the synthetic market
    assert outputs["market_states"].loc[(slice(None), slice(ts("2013-06-01"), None)), :].notna().all().all()
