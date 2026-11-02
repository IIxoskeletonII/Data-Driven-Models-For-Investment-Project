"""Synthetic, deterministic daily prices for the tests: no network and no licensed data.

The generator mimics a Yahoo response with auto_adjust=False: Close adjusted for splits only, Adj Close also
for dividends with the multiplicative rule f(t-1) = f(t) * (1 - D(t) / Close(t-1)).
"""

import copy
import functools
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

# 2021 US market holidays: includes Monday holidays (18 Jan, 15 Feb, 31 May, 6 Sep) and Good Friday (2 Apr)
HOLIDAYS = ["2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31", "2021-07-05", "2021-09-06", "2021-11-25",
            "2021-12-24"]


def make_sessions(start: str = "2021-01-01", end: str = "2021-12-31") -> pd.DatetimeIndex:
    days = pd.bdate_range(start, end)
    return days.difference(pd.DatetimeIndex(HOLIDAYS))


def make_raw(sessions: pd.DatetimeIndex, seed: int = 0, start_price: float = 50.0, dividends: dict | None = None) -> pd.DataFrame:
    """One ticker's daily OHLCV, dividends and splits, with an Adj Close consistent with the dividends."""
    rng = np.random.default_rng(seed)
    n = len(sessions)
    close = start_price * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    opens = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(opens, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(opens, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    raw = pd.DataFrame({"Open": opens, "High": high, "Low": low, "Close": close}, index=sessions)
    raw["Volume"] = rng.integers(100_000, 1_000_000, n)
    raw["Dividends"] = 0.0
    for day, amount in (dividends or {}).items():
        raw.loc[pd.Timestamp(day), "Dividends"] = amount
    raw["Stock Splits"] = 0.0

    factor = np.ones(n)
    for t in range(n - 1, 0, -1):
        factor[t - 1] = factor[t] * (1 - raw["Dividends"].iloc[t] / raw["Close"].iloc[t - 1])
    raw["Adj Close"] = raw["Close"] * factor
    return raw[["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"]].rename_axis("Date")


QUARTERLY_DIVIDENDS = {"2021-03-22": 0.20, "2021-06-21": 0.22, "2021-09-20": 0.21, "2021-12-20": 0.25}


@pytest.fixture
def sessions() -> pd.DatetimeIndex:
    return make_sessions()


@pytest.fixture
def raw(sessions) -> pd.DataFrame:
    return make_raw(sessions, seed=1, dividends=QUARTERLY_DIVIDENDS)


@pytest.fixture
def raw_factory():
    return make_raw


# ---------------------------------------------------------------------------------------------------------------------
# Shared synthetic market (docs/interfaces.md, contract 18)
# ---------------------------------------------------------------------------------------------------------------------

SYNTHETIC_START = "2011-01-03"
SYNTHETIC_END = "2020-12-31"
SYNTHETIC_CLOSURE = ["2012-10-29", "2012-10-30"]  # equity market closed by a storm; FRED still publishes
SYNTHETIC_HEDGE_START = "2011-03-07"  # first date of the hedge ticker: a Monday about two months after the others
SYNTHETIC_SPLIT = ("XLK", "2015-06-09", 2.0)  # (ticker, first session at the new price, ratio)
SYNTHETIC_VIX_ONLY = ["2012-10-29", "2015-04-03"]  # VIX prints on an equity closure and on a Good Friday

# Planted betas to the market factor, annual dividend yields (paid quarterly as a fraction of the previous close), start prices
SYNTHETIC_BETAS = {"XLB": 1.10, "XLE": 1.25, "XLF": 1.30, "XLI": 1.05, "XLK": 1.15, "XLP": 0.65, "XLU": 0.60, "XLV": 0.80,
                   "XLY": 1.40, "IVV": 1.0, "SPY": 1.0}
SYNTHETIC_YIELDS = {"XLE": 0.030, "XLF": 0.018, "XLP": 0.025, "XLU": 0.035, "IVV": 0.019, "SPY": 0.019}
SYNTHETIC_START_PRICES = {"XLB": 35.0, "XLE": 70.0, "XLF": 16.0, "XLI": 35.0, "XLK": 50.0, "XLP": 29.0, "XLU": 31.0,
                          "XLV": 32.0, "XLY": 38.0, "IVV": 130.0, "SPY": 127.0}

MARKET_MU = 0.0002  # daily log drift of the market factor
MARKET_SIGMA = 0.010  # daily volatility of the market factor
IDIO_SIGMA = 0.007  # daily idiosyncratic volatility of a sector
TRACKING_SIGMA = 0.0002  # daily tracking noise: SPY around the market, IVV around SPY
OVERNIGHT_SIGMA = 0.002  # log gap between the previous close and the open
DRIFT_PHI = 0.98  # weekly AR(1) persistence of a sector's latent expected weekly log return
DRIFT_SD = 0.005  # stationary standard deviation of that latent expected weekly log return


def _observed(day: pd.Timestamp, new_year: bool = False) -> pd.Timestamp | None:
    """Weekend observance: Saturday -> Friday, Sunday -> Monday; a Saturday New Year is not observed."""
    if day.day_of_week == 5:
        return None if new_year else day - pd.Timedelta(days=1)
    if day.day_of_week == 6:
        return day + pd.Timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> pd.Timestamp:
    """The n-th given weekday (0 = Monday) of a month; n = -1 is the last one."""
    if n > 0:
        first = pd.Timestamp(year, month, 1)
        return first + pd.Timedelta(days=(weekday - first.day_of_week) % 7 + 7 * (n - 1))
    last = pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)
    return last - pd.Timedelta(days=(last.day_of_week - weekday) % 7)


def easter_sunday(year: int) -> pd.Timestamp:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 19 * m) // 433
    month = (h + m - 7 * n + 90) // 25
    day = (h + m - 7 * n + 33 * month + 19) % 32
    return pd.Timestamp(year, month, day)


def us_equity_holidays(year: int) -> list[pd.Timestamp]:
    """US equity market holidays of a year, as observed."""
    days = [
        _observed(pd.Timestamp(year, 1, 1), new_year=True),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Presidents Day
        easter_sunday(year) - pd.Timedelta(days=2),  # Good Friday
        _nth_weekday(year, 5, 0, -1),  # Memorial Day
        _observed(pd.Timestamp(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(pd.Timestamp(year, 12, 25)),  # Christmas
    ]
    return [day for day in days if day is not None]


def us_federal_holidays(year: int) -> list[pd.Timestamp]:
    """US federal holidays of a year (no FRED value): no Good Friday, plus Columbus and Veterans Day."""
    days = [
        _observed(pd.Timestamp(year, 1, 1), new_year=True),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _nth_weekday(year, 5, 0, -1),
        _observed(pd.Timestamp(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        _observed(pd.Timestamp(year, 11, 11)),  # Veterans Day
        _nth_weekday(year, 11, 3, 4),
        _observed(pd.Timestamp(year, 12, 25)),
    ]
    return [day for day in days if day is not None]


def _weekdays_except(holidays: list[pd.Timestamp]) -> pd.DatetimeIndex:
    days = pd.bdate_range(SYNTHETIC_START, SYNTHETIC_END)
    return days.difference(pd.DatetimeIndex(holidays)).rename("date")


def _years() -> range:
    return range(pd.Timestamp(SYNTHETIC_START).year, pd.Timestamp(SYNTHETIC_END).year + 1)


def synthetic_sessions() -> pd.DatetimeIndex:
    """Equity sessions of the synthetic market: weekdays minus US market holidays and the October 2012 closure."""
    holidays = [day for year in _years() for day in us_equity_holidays(year)]
    return _weekdays_except(holidays + [pd.Timestamp(day) for day in SYNTHETIC_CLOSURE])


def fred_business_days() -> pd.DatetimeIndex:
    """FRED publication days of the synthetic market: weekdays minus US federal holidays."""
    return _weekdays_except([day for year in _years() for day in us_federal_holidays(year)])


@dataclass
class SyntheticMarket:
    """A deterministic synthetic market in the formats of docs/interfaces.md (contract 18)."""

    sessions: pd.DatetimeIndex
    raw: dict[str, pd.DataFrame]
    unadjusted_open: pd.DataFrame
    unadjusted_close: pd.DataFrame
    daily_open: pd.DataFrame
    daily_close: pd.DataFrame
    weekly_open: pd.DataFrame
    weekly_close: pd.DataFrame
    vix: pd.Series
    fred: pd.DataFrame
    split: tuple[str, pd.Timestamp, float]
    true_beta: dict[str, float]
    drift: pd.DataFrame
    is_end: pd.Timestamp


def _quarterly_ex_dates(sessions: pd.DatetimeIndex) -> np.ndarray:
    """Boolean mask of ex-dividend sessions: the first session on or after the 20th of March, June, September, December."""
    mask = np.zeros(len(sessions), dtype=bool)
    for year in range(sessions[0].year, sessions[-1].year + 1):
        for month in (3, 6, 9, 12):
            position = sessions.searchsorted(pd.Timestamp(year, month, 20))
            if position < len(sessions):
                mask[position] = True
    return mask


def _yahoo_frame(actual_open: np.ndarray, actual_close: np.ndarray, dividends: np.ndarray, ratio: np.ndarray,
                 volume: np.ndarray, rng: np.random.Generator, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Yahoo auto_adjust=False rows from actual traded prices.

    Open, High, Low, Close and Dividends are divided by the split ratios still to come (Volume multiplied), and
    Adj Close = Close * f with f(t-1) = f(t) * (1 - D(t) / Close(t-1)), the rule of make_raw.
    """
    n = len(index)
    high = np.maximum(actual_open, actual_close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(actual_open, actual_close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    later = np.r_[np.cumprod(ratio[::-1])[::-1][1:], 1.0]  # product of the split ratios after each date
    raw = pd.DataFrame({"Open": actual_open / later, "High": high / later, "Low": low / later,
                        "Close": actual_close / later}, index=index)
    raw["Volume"] = np.round(volume * later).astype(np.int64)
    raw["Dividends"] = dividends / later
    raw["Stock Splits"] = np.where(ratio != 1.0, ratio, 0.0)
    close = raw["Close"].to_numpy()
    step = np.ones(n)
    step[1:] = 1 - raw["Dividends"].to_numpy()[1:] / close[:-1]
    factor = np.r_[np.cumprod(step[::-1])[::-1][1:], 1.0]
    raw["Adj Close"] = close * factor
    return raw[["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"]].rename_axis("Date")


@functools.lru_cache(maxsize=8)
def _build_synthetic_market(seed: int, momentum: bool) -> SyntheticMarket:
    from src.config import load_config
    from src.data import adjust_ohlc, weekly_panel

    cfg = load_config()
    data = cfg["data"]
    sectors, hedge, benchmark = list(data["tickers"]), data["hedge"], data["benchmark"]
    tradables = sectors + [hedge, benchmark]
    rng = np.random.default_rng(seed)
    sessions = synthetic_sessions()
    n = len(sessions)

    # Week of each session (Friday label) and the latent, persistent expected weekly log return of each sector
    fridays = sessions + pd.to_timedelta((4 - sessions.day_of_week) % 7, unit="D")
    _, week_of_session = np.unique(fridays.values, return_inverse=True)
    sessions_in_week = np.bincount(week_of_session)
    latent = np.zeros((len(sessions_in_week), len(sectors)))
    latent[0] = rng.normal(0.0, DRIFT_SD, len(sectors))
    shocks = rng.normal(0.0, DRIFT_SD * np.sqrt(1 - DRIFT_PHI**2), latent.shape)
    for w in range(1, len(latent)):
        latent[w] = DRIFT_PHI * latent[w - 1] + shocks[w]
    if not momentum:
        latent[:] = 0.0

    # Daily close-to-close log total returns: every sector expects MARKET_MU per session plus its latent drift
    market = rng.normal(MARKET_MU, MARKET_SIGMA, n)
    log_return = {}
    for j, ticker in enumerate(sectors):
        idio = rng.normal(0.0, IDIO_SIGMA, n)
        log_return[ticker] = SYNTHETIC_BETAS[ticker] * (market - MARKET_MU) + MARKET_MU + latent[week_of_session, j] / 5 + idio
    log_return[benchmark] = market + rng.normal(0.0, TRACKING_SIGMA, n)
    log_return[hedge] = log_return[benchmark] + rng.normal(0.0, TRACKING_SIGMA, n)

    # Actual traded prices: C(t) = (C(t-1) - D(t)) / ratio(t) * exp(r(t)), O(t) = (C(t-1) - D(t)) / ratio(t) * exp(gap(t))
    split_ticker, split_day, split_ratio = SYNTHETIC_SPLIT
    split_day = pd.Timestamp(split_day)
    ex_dates = _quarterly_ex_dates(sessions)
    raw, unadjusted_open, unadjusted_close = {}, {}, {}
    for ticker in tradables:
        gap = rng.normal(0.0, OVERNIGHT_SIGMA, n)
        volume = rng.integers(1_000_000, 20_000_000, n).astype(np.float64)
        dividend_rate = np.where(ex_dates, SYNTHETIC_YIELDS.get(ticker, 0.0) / 4, 0.0)
        dividend_rate[0] = 0.0
        ratio = np.ones(n)
        if ticker == split_ticker:
            ratio[sessions.get_loc(split_day)] = split_ratio
        growth = (1 - dividend_rate) / ratio * np.exp(log_return[ticker])
        growth[0] = 1.0
        close = SYNTHETIC_START_PRICES[ticker] * np.cumprod(growth)
        previous = np.r_[close[0], close[:-1]]
        dividends = dividend_rate * previous
        opens = (previous - dividends) / ratio * np.exp(gap)
        frame = _yahoo_frame(opens, close, dividends, ratio, volume, rng, sessions)
        listed = sessions >= (pd.Timestamp(SYNTHETIC_HEDGE_START) if ticker == hedge else sessions[0])
        raw[ticker] = frame.loc[listed]
        unadjusted_open[ticker] = np.where(listed, opens, np.nan)
        unadjusted_close[ticker] = np.where(listed, close, np.nan)

    def daily(columns: dict) -> pd.DataFrame:
        return pd.DataFrame(columns, index=sessions)[tradables].astype(np.float64)

    adjusted = {ticker: adjust_ohlc(raw[ticker]).reindex(sessions) for ticker in tradables}
    daily_open = daily({ticker: adjusted[ticker]["Open"].to_numpy() for ticker in tradables})
    daily_close = daily({ticker: adjusted[ticker]["Close"].to_numpy() for ticker in tradables})
    weekly_open, weekly_close = weekly_panel(daily_open, daily_close)

    # Planted expected log return of each sector over the sessions of each week (identical across sectors without momentum)
    drift_values = sessions_in_week[:, None] * (MARKET_MU + latent / 5)
    drift = pd.DataFrame(drift_values, index=weekly_open.index, columns=sectors)

    # VIX: mean-reverting log level that rises when the market falls; on the sessions plus two VIX-only dates
    vix_dates = sessions.union(pd.DatetimeIndex(SYNTHETIC_VIX_ONLY)).rename("date")
    market_on_vix = pd.Series(market, index=sessions).reindex(vix_dates, fill_value=0.0).to_numpy()
    vix_noise = rng.normal(0.0, 0.03, len(vix_dates))
    log_vix = np.empty(len(vix_dates))
    log_vix[0] = np.log(18.0)
    for t in range(1, len(vix_dates)):
        log_vix[t] = log_vix[t - 1] + 0.03 * (np.log(18.0) - log_vix[t - 1]) - 4.0 * market_on_vix[t] + vix_noise[t]
    vix = pd.Series(np.round(np.exp(log_vix), 2), index=vix_dates, name="VIX")

    # FRED: percent rates on federal business days (values on Good Friday, none on Columbus or Veterans Day), ~1% missing
    fred_dates = fred_business_days()
    m = len(fred_dates)
    fred = pd.DataFrame({
        "DGS3MO": np.clip(0.10 + np.cumsum(rng.normal(0.0, 0.01, m)), 0.0, None),
        "DGS10": np.clip(3.30 + np.cumsum(rng.normal(0.0, 0.04, m)), 0.3, None),
        "BAA10Y": np.clip(2.50 + np.cumsum(rng.normal(0.0, 0.02, m)), 1.0, None),
    }, index=fred_dates).round(2)
    fred = fred.mask(rng.random(fred.shape) < 0.01)

    return SyntheticMarket(
        sessions=sessions, raw=raw, unadjusted_open=daily(unadjusted_open), unadjusted_close=daily(unadjusted_close),
        daily_open=daily_open, daily_close=daily_close, weekly_open=weekly_open, weekly_close=weekly_close,
        vix=vix, fred=fred, split=(split_ticker, split_day, split_ratio),
        true_beta={ticker: SYNTHETIC_BETAS[ticker] for ticker in tradables}, drift=drift,
        is_end=pd.Timestamp(cfg["split"]["in_sample_end"]),
    )


def make_synthetic_market(seed: int = 42, momentum: bool = True) -> SyntheticMarket:
    """The shared synthetic market: deterministic, built once per (seed, momentum), returned as an independent copy."""
    return copy.deepcopy(_build_synthetic_market(seed, momentum))


@pytest.fixture
def synthetic_market() -> SyntheticMarket:
    return make_synthetic_market()


@pytest.fixture
def synthetic_market_factory():
    return make_synthetic_market
