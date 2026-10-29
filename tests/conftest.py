"""Synthetic, deterministic daily prices for the tests: no network and no licensed data.

The generator mimics a Yahoo response with auto_adjust=False: Close adjusted for splits only, Adj Close also
for dividends with the multiplicative rule f(t-1) = f(t) * (1 - D(t) / Close(t-1)).
"""

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
