"""Metrics of weekly returns and signals, with the definitions of the course skeleton's docs/metrics.md (protocol section 11).

Not implemented yet: Phase 2.1 (Mattia). Interfaces: docs/interfaces.md, contract 16.
"""

import pandas as pd


def performance(r: pd.Series, rf: pd.Series | float) -> dict[str, float]:
    """Performance metrics of a weekly return series (§11; skeleton docs/metrics.md), P = 52 periods per year.

    r: simple weekly returns (decimals) on the weekly index; rf: weekly risk-free returns on the same index, or an annual
    constant. Cumulative and annualised return, volatility, Sharpe (both conventions), Sortino, max drawdown, Calmar.
    Ratios with a zero denominator are NaN.
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def return_stats(r: pd.Series) -> dict[str, float]:
    """Distribution statistics of weekly returns (§11): hit rate, average gain and loss, profit factor, best and worst
    week, skew, kurtosis. Ratios with a zero denominator are NaN.
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def behaviour(signals: pd.DataFrame, weights: pd.DataFrame) -> dict[str, float]:
    """Exposure and trading behaviour (§11): long, short, gross and net exposure, turnover and holding period, from the
    weekly signals (contract 9) and weights (contract 11).
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def market(r: pd.Series, m: pd.Series, rf: pd.Series | float) -> dict[str, float]:
    """Market relation of weekly returns r to the benchmark's weekly returns m (§11): beta, correlation, alpha,
    tracking error, information ratio, down-market statistics. Ratios with a zero denominator are NaN.
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def tbill_weekly_returns(dgs3mo: pd.Series, weeks: pd.MultiIndex) -> pd.Series:
    """Weekly risk-free returns from the daily FRED 3-month T-bill yield (percent per year), on the weekly index.

    Lagged one session (Amendment 1): the rate used for week t is known after Friday close t. Returns a float64 Series
    of simple weekly returns (decimals).
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def period_average_rf(rf_weekly: pd.Series, period: pd.Series) -> dict[str, float]:
    """Annual average risk-free rate (decimal) of each period, {"IS": ..., "OOS": ...}, from weekly risk-free returns
    and the period labels of contract 7.
    """
    raise NotImplementedError("Phase 2.1, Mattia")
