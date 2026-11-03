"""Asset-level features (MOM26_1, MOM52_4, REV1, VOL13, DD13, BETA52) and market states (BEAR24, MKT_VAR,
VIX, TERM, CREDIT) of protocol section 06, using only data known at the Friday close. VIX is the lagged level;
VIX_Z is its in-fold standardisation inside the model pipeline (Amendment 2 C7).

Conventions (docs/decisions.md S22-1 to S22-4; docs/interfaces.md contracts 0 to 4 and 10). F is the Friday
`date_close` of week t, L(t) the last session of week t (Friday, or Thursday when Friday is a holiday), TR the adjusted
close (total-return index).
- "The w weeks ending t" are the sessions s with F - 7w days < s <= F (calendar weeks, not session counts).
- A daily simple return r(s) = TR(s) / TR(previous session) - 1 belongs to a window when its end session s does.
- TR(t - k w) is the close of the last session of the calendar week ending F - 7k days; NaN if that week has no session.
- Full-window rule: a value is NaN unless every close it needs is present and the session calendar starts before the
  window; return windows also need the close of the session just before the window. MKT_VAR counts sessions (126 daily
  returns, so 127 closes, ending at L(t)).
- Market series (VIX, FRED) enter lagged one session: the last observation dated on or before the previous session.
Every value on row t is known after Friday close t.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import data_settings, load_config
from src.contracts import universe, validate_betas, validate_features, validate_market_states

WEEK_LEVELS = ["date_open", "date_close"]
FEATURE_LEVELS = ["date_close", "ticker"]
DAYS_PER_WEEK = 7
TRADING_DAYS_PER_YEAR = 252  # annualisation of VOL13 (§06: "x sqrt(252)")
SHORT_WINDOW_WEEKS = 13  # VOL13 and DD13 (§06)
TERM_LONG, TERM_SHORT, CREDIT_SERIES = "DGS10", "DGS3MO", "BAA10Y"  # TERM = DGS10 - DGS3MO, CREDIT = BAA10Y (§06)
MOMENTUM_NAME = re.compile(r"^MOM(\d+)_(\d+)$")  # MOM{L}_{S} = ln TR(t - S w) - ln TR(t - L w)


def _config(cfg: dict | None) -> dict:
    return load_config() if cfg is None else cfg


def features_settings(cfg: dict) -> dict:
    """The config settings that determine the files written by 03_build_features.py (features, market states, sizing
    betas, momentum variants and labels), saved as data/processed/features_config.yaml for check_used (S23-1).

    Returns {"data": data_settings(cfg), "features": cfg["features"], "execution": cfg["execution"], "in_sample_end":
    cfg["split"]["in_sample_end"]}; execution.type determines the labels.
    """
    return {"data": data_settings(cfg), "features": cfg["features"], "execution": cfg["execution"],
            "in_sample_end": cfg["split"]["in_sample_end"]}


def _as_ns(dates) -> np.ndarray:
    """Dates as a datetime64[ns] numpy array (any input resolution)."""
    return np.asarray(pd.DatetimeIndex(dates).as_unit("ns").values)


# ---------------------------------------------------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------------------------------------------------


def weekly_index(sessions: pd.DatetimeIndex) -> pd.MultiIndex:
    """Weekly index (contract 2) of a session calendar: one row per calendar week with at least one session.

    date_close is the Friday of each session's week (s + (4 - weekday) days), unique and ascending; date_open is
    date_close - 4 days (the Monday). Same weeks as src.data.weekly_panel on the same sessions.
    """
    sessions = pd.DatetimeIndex(sessions)
    fridays = sessions + pd.to_timedelta(4 - sessions.day_of_week, unit="D")
    closes = pd.DatetimeIndex(fridays.unique()).sort_values()
    return pd.MultiIndex.from_arrays([closes - pd.Timedelta(days=4), closes], names=WEEK_LEVELS)


def last_sessions(sessions: pd.DatetimeIndex) -> pd.Series:
    """Last session L(t) of each week: indexed by date_close (Friday), value Friday or Thursday when Friday is a holiday."""
    sessions = pd.DatetimeIndex(sessions)
    fridays = sessions + pd.to_timedelta(4 - sessions.day_of_week, unit="D")
    frame = pd.Series(sessions, index=pd.DatetimeIndex(fridays, name="date_close"), name="last_session")
    return frame.groupby(level=0).max()


@dataclass(frozen=True)
class _Calendar:
    """Session calendar and weeks: sessions and Fridays as datetime64[ns], and the position of L(t) in the sessions."""

    weeks: pd.MultiIndex
    sessions: np.ndarray
    fridays: np.ndarray
    last: np.ndarray


def _calendar(sessions: pd.DatetimeIndex) -> _Calendar:
    sessions = pd.DatetimeIndex(sessions)
    if not sessions.is_monotonic_increasing or not sessions.is_unique:
        raise ValueError("sessions must be strictly increasing and unique")
    weeks = weekly_index(sessions)
    session_ns = _as_ns(sessions)
    friday_ns = _as_ns(weeks.get_level_values("date_close"))
    last = np.searchsorted(session_ns, friday_ns, side="right") - 1
    return _Calendar(weeks=weeks, sessions=session_ns, fridays=friday_ns, last=last)


def _days(n: int) -> np.timedelta64:
    return np.timedelta64(int(n), "D").astype("timedelta64[ns]")


def _close_weeks_ago(cal: _Calendar, close: np.ndarray, k: int) -> np.ndarray:
    """TR(t - k w) for every week (rows) and column: close of the last session of the week ending F - 7k days.

    NaN when that calendar week has no session or the close there is missing. k = 0 gives TR(t), the close at L(t).
    """
    target = cal.fridays - _days(DAYS_PER_WEEK * k)
    position = np.searchsorted(cal.sessions, target, side="right") - 1
    clipped = np.clip(position, 0, None)
    in_week = (position >= 0) & (cal.sessions[clipped] > target - _days(DAYS_PER_WEEK))
    values = close[clipped].astype(np.float64, copy=True)
    values[~in_week] = np.nan
    return values


def _window_starts(cal: _Calendar, weeks: int) -> tuple[np.ndarray, np.ndarray]:
    """First session position of the window F - 7w days < s <= F, and whether the calendar starts before the window."""
    starts = np.searchsorted(cal.sessions, cal.fridays - _days(DAYS_PER_WEEK * weeks), side="right")
    return starts, starts >= 1


def _simple_returns(close: np.ndarray) -> np.ndarray:
    """Daily simple returns on their end session: r[s] = close[s] / close[s - 1] - 1; NaN on the first session."""
    returns = np.full(close.shape, np.nan)
    returns[1:] = close[1:] / close[:-1] - 1.0
    return returns


def _as_2d(values) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    return array[:, None] if array.ndim == 1 else array


# ---------------------------------------------------------------------------------------------------------------------
# Window statistics (one row per week, one column per ticker)
# ---------------------------------------------------------------------------------------------------------------------


def _window_volatility(cal: _Calendar, close: np.ndarray, weeks: int) -> np.ndarray:
    """Sample std (ddof=1) of the daily simple returns ending in the `weeks` weeks ending t, x sqrt(252)."""
    returns = _simple_returns(close)
    starts, full = _window_starts(cal, weeks)
    out = np.full((len(cal.fridays), close.shape[1]), np.nan)
    for w in np.flatnonzero(full):
        window = returns[starts[w]: cal.last[w] + 1]
        if len(window) >= 2:
            out[w] = np.std(window, axis=0, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
    return out


def _window_drawdown(cal: _Calendar, close: np.ndarray, weeks: int) -> np.ndarray:
    """TR(t) / max(TR over the sessions of the `weeks` weeks ending t) - 1."""
    starts, full = _window_starts(cal, weeks)
    out = np.full((len(cal.fridays), close.shape[1]), np.nan)
    for w in np.flatnonzero(full):
        window = close[starts[w]: cal.last[w] + 1]
        out[w] = close[cal.last[w]] / np.max(window, axis=0) - 1.0
    return out


def _window_beta(cal: _Calendar, close: np.ndarray, market: np.ndarray, weeks: int) -> np.ndarray:
    """cov(r_i, r_m) / var(r_m), both ddof=1, of the daily simple returns ending in the `weeks` weeks ending t."""
    returns, market_returns = _simple_returns(close), _simple_returns(market)
    starts, full = _window_starts(cal, weeks)
    out = np.full((len(cal.fridays), close.shape[1]), np.nan)
    for w in np.flatnonzero(full):
        r = returns[starts[w]: cal.last[w] + 1]
        m = market_returns[starts[w]: cal.last[w] + 1]
        if len(m) < 2:
            continue
        m_dev = m - m.mean()
        covariance = ((r - r.mean(axis=0)) * m_dev[:, None]).sum(axis=0) / (len(m) - 1)
        variance = (m_dev**2).sum() / (len(m) - 1)
        out[w] = covariance / variance
    return out


def _trailing_variance(cal: _Calendar, market: np.ndarray, n_returns: int) -> np.ndarray:
    """Sample variance (ddof=1) of the last n_returns daily simple returns ending at L(t) (n_returns + 1 closes)."""
    returns = _simple_returns(market)
    out = np.full(len(cal.fridays), np.nan)
    for w in np.flatnonzero(cal.last >= n_returns):
        out[w] = np.var(returns[cal.last[w] - n_returns + 1: cal.last[w] + 1], ddof=1)
    return out


def _log_momentum(cal: _Calendar, close: np.ndarray, long_weeks: int, skip_weeks: int) -> np.ndarray:
    """ln TR(t - skip_weeks w) - ln TR(t - long_weeks w)."""
    return np.log(_close_weeks_ago(cal, close, skip_weeks)) - np.log(_close_weeks_ago(cal, close, long_weeks))


# ---------------------------------------------------------------------------------------------------------------------
# Market series
# ---------------------------------------------------------------------------------------------------------------------


def lag_one_session(series: pd.Series, sessions: pd.DatetimeIndex) -> pd.Series:
    """Market series known at each session (Amendment 1, contract 1, S22-2).

    The value at session s is the last non-missing observation dated on or before the session before s (in
    `sessions`); a Monday after a holiday uses the value of the session before the holiday, and on a bond holiday
    that is an equity session the last published value is carried forward. Observations dated on non-sessions are used
    only once the previous session is on or after their date; a later observation is never used. Returns a float64
    Series on `sessions` with the input's name, NaN at the first session and before the first observation.
    """
    sessions = pd.DatetimeIndex(sessions)
    observed = series.dropna()
    observed = observed[~pd.DatetimeIndex(observed.index).isna()].sort_index(kind="stable")
    observed_dates = _as_ns(observed.index)
    observed_values = observed.to_numpy(dtype=np.float64)
    values = np.full(len(sessions), np.nan)
    if len(sessions) > 1 and len(observed_values):
        position = np.searchsorted(observed_dates, _as_ns(sessions)[:-1], side="right") - 1
        values[1:] = np.where(position >= 0, observed_values[np.clip(position, 0, None)], np.nan)
    return pd.Series(values, index=sessions, name=series.name, dtype=np.float64)


def _lagged_at_last_session(series: pd.Series, cal: _Calendar, sessions: pd.DatetimeIndex) -> np.ndarray:
    """The one-session-lagged value of a market series at L(t) of every week."""
    return lag_one_session(series, sessions).to_numpy()[cal.last]


# ---------------------------------------------------------------------------------------------------------------------
# Asset features
# ---------------------------------------------------------------------------------------------------------------------


def _feature_frame(cal: _Calendar, tickers: Sequence[str], columns: dict[str, np.ndarray]) -> pd.DataFrame:
    """Index (date_close, ticker) = weeks x tickers; each column a (weeks, tickers) array, flattened row by row."""
    closes = pd.DatetimeIndex(cal.weeks.get_level_values("date_close"), name="date_close")
    index = pd.MultiIndex.from_product([closes, list(tickers)], names=FEATURE_LEVELS)
    data = {name: np.asarray(values, dtype=np.float64).reshape(-1) for name, values in columns.items()}
    return pd.DataFrame(data, index=index, columns=list(columns)).astype(np.float64)


def _raw_feature(name: str, cal: _Calendar, close: np.ndarray, market: np.ndarray, cfg: dict) -> np.ndarray:
    """One raw asset feature (§06, S22-1 to S22-4) for every week (rows) and sector (columns)."""
    match = MOMENTUM_NAME.match(name)
    if match:
        return _log_momentum(cal, close, long_weeks=int(match.group(1)), skip_weeks=int(match.group(2)))
    if name == "REV1":
        return _log_momentum(cal, close, long_weeks=1, skip_weeks=0)
    if name == "VOL13":
        return _window_volatility(cal, close, SHORT_WINDOW_WEEKS)
    if name == "DD13":
        return _window_drawdown(cal, close, SHORT_WINDOW_WEEKS)
    if name == "BETA52":
        return _window_beta(cal, close, market, cfg["features"]["beta_weeks"])
    raise KeyError(f"unknown asset feature {name!r} in features.asset")


def raw_asset_features(daily_close: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """The six asset features of §06 before z-scoring, for every week of weekly_index(daily_close.index).

    daily_close: adjusted daily closes (total-return index) with the 9 sectors and SPY, on the session calendar.
    MOM26_1, MOM52_4, REV1 are log returns; VOL13 is annualised (decimal per year, simple daily returns); DD13 a
    decimal drawdown (<= 0); BETA52 a ratio against SPY. Row (date_close, ticker) is known after Friday close t.
    Returns index (date_close, ticker) with the sectors sorted, columns features.asset, float64.
    """
    cfg = _config(cfg)
    u = universe(cfg)
    sectors = sorted(u.sectors)
    cal = _calendar(daily_close.index)
    close = daily_close[sectors].to_numpy(dtype=np.float64)
    market = daily_close[u.benchmark].to_numpy(dtype=np.float64)
    columns = {name: _raw_feature(name, cal, close, market, cfg) for name in cfg["features"]["asset"]}
    return _feature_frame(cal, sectors, columns)


def cross_sectional_zscore(raw: pd.DataFrame) -> pd.DataFrame:
    """z = (x - mean) / std (ddof=1) of each column across the tickers of each date_close (contract 3).

    A week where any ticker's raw value is NaN gets NaN for all tickers of that feature; a week where all raw values
    are equal gets 0.0. Uses same-date values only. Same index and columns as `raw`, float64.
    """
    grouped = raw.groupby(level="date_close", sort=False)
    complete = raw.notna().groupby(level="date_close", sort=False).transform("all")
    mean, std = grouped.transform("mean"), grouped.transform("std")
    equal = grouped.transform("max") == grouped.transform("min")
    z = ((raw - mean) / std).mask(equal, 0.0).where(complete)
    return z.astype(np.float64)


def asset_features(daily_close: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """The six asset features of §06 (contract 3), cross-sectionally z-scored across the 9 sectors each Friday.

    daily_close: adjusted daily closes (total-return index, contract 1) of the sectors and SPY. Windows end at the last
    session of week t, so row (date_close, ticker) is known after Friday close t. Returns index (date_close, ticker),
    columns features.asset, float64, NaN only while a window is not full; passes validate_features.
    """
    cfg = _config(cfg)
    features = cross_sectional_zscore(raw_asset_features(daily_close, cfg))
    validate_features(features, columns=cfg["features"]["asset"])
    return features


def momentum_variants(daily_close: pd.DataFrame, lookbacks: Sequence[int] | None = None, *,
                      cfg: dict | None = None) -> pd.DataFrame:
    """M0* momentum variants (§07 fallback, contract 3): MOM{L}_1 = ln TR(t − 1w) − ln TR(t − L w), z-scored.

    lookbacks default to models.M0_star.lookback_weeks (13, 26, 52). Known after Friday close t. Returns index
    (date_close, ticker), one column per lookback; passes validate_features(columns=...).
    """
    cfg = _config(cfg)
    lookbacks = cfg["models"]["M0_star"]["lookback_weeks"] if lookbacks is None else lookbacks
    u = universe(cfg)
    sectors = sorted(u.sectors)
    cal = _calendar(daily_close.index)
    close = daily_close[sectors].to_numpy(dtype=np.float64)
    columns = {f"MOM{int(weeks)}_1": _log_momentum(cal, close, long_weeks=int(weeks), skip_weeks=1) for weeks in lookbacks}
    variants = cross_sectional_zscore(_feature_frame(cal, sectors, columns))
    validate_features(variants, columns=list(columns))
    return variants


# ---------------------------------------------------------------------------------------------------------------------
# Market states and sizing betas
# ---------------------------------------------------------------------------------------------------------------------


def _bear_indicator(cal: _Calendar, spy: np.ndarray, weeks: int) -> np.ndarray:
    """1.0 if TR_SPY(t) / TR_SPY(t - weeks w) - 1 < 0, else 0.0; NaN if either close is missing."""
    now = _close_weeks_ago(cal, _as_2d(spy), 0)[:, 0]
    then = _close_weeks_ago(cal, _as_2d(spy), weeks)[:, 0]
    with np.errstate(invalid="ignore"):
        bear = np.where(now / then - 1.0 < 0.0, 1.0, 0.0)
    bear[np.isnan(now) | np.isnan(then)] = np.nan
    return bear


def market_states(daily_close: pd.DataFrame, vix: pd.Series, fred: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """The five unscaled market states of §06 (contract 4) on the weekly index.

    BEAR24 (0/1) from SPY's 104-week total return, MKT_VAR from 126 daily SPY returns, VIX = VIX level, TERM = DGS10 −
    DGS3MO, CREDIT = BAA10Y; VIX and FRED values lagged one session (Amendment 1; Amendment 2 C6), so row t is known
    after Friday close t. In-fold scaling of the continuous states happens in the model pipeline on training rows only;
    BEAR24 is never scaled (Amendment 2 C1). Passes validate_market_states.

    vix: raw, unlagged VIX closes (index points), may include non-session dates. fred: raw, unlagged DGS3MO, DGS10 and
    BAA10Y (percent per year), may have NaN and non-session dates. MKT_VAR is a daily variance (decimal squared); TERM
    and CREDIT are in percentage points.
    """
    cfg = _config(cfg)
    u = universe(cfg)
    sessions = pd.DatetimeIndex(daily_close.index)
    cal = _calendar(sessions)
    spy = daily_close[u.benchmark].to_numpy(dtype=np.float64)
    states = {
        "BEAR24": _bear_indicator(cal, spy, cfg["features"]["bear_weeks"]),
        "MKT_VAR": _trailing_variance(cal, spy, cfg["features"]["mkt_var_days"]),
        "VIX": _lagged_at_last_session(vix, cal, sessions),
        "TERM": (_lagged_at_last_session(fred[TERM_LONG], cal, sessions)
                 - _lagged_at_last_session(fred[TERM_SHORT], cal, sessions)),
        "CREDIT": _lagged_at_last_session(fred[CREDIT_SERIES], cal, sessions),
    }
    unknown = [name for name in cfg["features"]["states"] if name not in states]
    if unknown:
        raise KeyError(f"unknown market states {unknown} in features.states")
    frame = pd.DataFrame({name: states[name] for name in cfg["features"]["states"]}, index=cal.weeks).astype(np.float64)
    validate_market_states(frame)
    return frame


def sizing_betas(daily_close: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Raw (not z-scored) BETA52 of each traded ticker against SPY (§06, §09, contract 10) on the weekly index.

    Daily simple returns whose end session lies in weeks t−51 … t; known after Friday close t and used to size the
    positions taken at O(t+1). NaN in the warm-up only. Passes validate_betas.
    """
    cfg = _config(cfg)
    u = universe(cfg)
    cal = _calendar(daily_close.index)
    close = daily_close[list(u.traded)].to_numpy(dtype=np.float64)
    market = daily_close[u.benchmark].to_numpy(dtype=np.float64)
    betas = _window_beta(cal, close, market, cfg["features"]["beta_weeks"])
    frame = pd.DataFrame(betas, index=cal.weeks, columns=list(u.traded)).astype(np.float64)
    validate_betas(frame)
    return frame
