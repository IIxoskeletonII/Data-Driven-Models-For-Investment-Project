"""Metrics of weekly returns and signals, with the definitions of the course skeleton's docs/metrics.md (protocol section 11).

Interfaces: docs/interfaces.md, contract 16. P = metrics.periods_per_year (52). Returns are simple weekly returns
(decimals) on the weekly index; row t is the return earned by the weights of week t, realised at O(t+2).

Sharpe ratio, three conventions (§09, §11):
- sharpe_rf (headline, skeleton): (annualised return − rf) / annualised volatility;
- sharpe_zero_cost (zero-cost long/short): annualised return / annualised volatility;
- sharpe_textbook (information only): √P · mean / std of the weekly returns.
With a weekly risk-free series, rf is its compound annual average over the same weeks (period_average_rf).

Amendment 2 C5: one continuous book; every metric, the equity curve (rebased to 100) and the behaviour statistics are
computed separately on each period (period_metrics).
"""

import functools

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.config import load_config


@functools.lru_cache(maxsize=1)
def _periods_per_year() -> int:
    return int(load_config()["metrics"]["periods_per_year"])


def ratio(numerator: float, denominator: float) -> float:
    """numerator / denominator, NaN if the denominator is zero (e.g. a strategy always flat), as in the skeleton."""
    return float(numerator / denominator) if denominator != 0 else np.nan


def annualized_return(r: pd.Series) -> float:
    """Compound annual return: (Π(1 + r))^(P/T) − 1."""
    return float((1 + r).prod() ** (_periods_per_year() / len(r)) - 1)


def annualized_volatility(r: pd.Series) -> float:
    """Sample standard deviation of the weekly returns × √P."""
    return float(r.std() * np.sqrt(_periods_per_year()))


def max_drawdown(r: pd.Series) -> float:
    """min_t E_t / max_{τ≤t} E_τ − 1, with the starting capital as the first peak."""
    equity = (1 + r).cumprod()
    peak = equity.cummax().clip(lower=1)
    return float((equity / peak - 1).min())


def equity_curve(r: pd.Series, base: float = 100.0) -> pd.Series:
    """E_t = base · Π_{τ≤t}(1 + r_τ): the equity after the return of week t, starting from `base` (100)."""
    return (base * (1 + r).cumprod()).rename("equity")


def _annual_rf(rf: pd.Series | float, index: pd.Index) -> float:
    """Annual risk-free rate of the weeks in index: the constant itself, or the compound average of weekly returns."""
    if np.isscalar(rf):
        return float(rf)
    weekly = rf.reindex(index)
    if weekly.isna().any():
        raise ValueError("the weekly risk-free series has no value for some weeks of the return series")
    return annualized_return(weekly)


def _weekly_rf(rf: pd.Series | float, index: pd.Index) -> pd.Series:
    """Weekly risk-free returns on index: rf / P for an annual constant (skeleton), else the series itself."""
    if np.isscalar(rf):
        return pd.Series(float(rf) / _periods_per_year(), index=index)
    weekly = rf.reindex(index)
    if weekly.isna().any():
        raise ValueError("the weekly risk-free series has no value for some weeks of the return series")
    return weekly


def sharpe_ratio(r: pd.Series, rf: pd.Series | float) -> float:
    """Skeleton Sharpe: (annualised return − rf) / annualised volatility (the headline sharpe_rf)."""
    return ratio(annualized_return(r) - _annual_rf(rf, r.index), annualized_volatility(r))


def performance(r: pd.Series, rf: pd.Series | float) -> dict[str, float]:
    """Performance metrics of a weekly return series (§11; skeleton docs/metrics.md), P = 52 periods per year.

    r: simple weekly returns (decimals) on the weekly index; rf: weekly risk-free returns on the same index, or an annual
    constant. Cumulative and annualised return, volatility, Sharpe (three conventions, see the module docstring), Sortino
    ((annualised return − rf) / (downside RMS over all weeks × √P)), max drawdown, Calmar, and the annual rf used.
    Ratios with a zero denominator are NaN.
    """
    P = _periods_per_year()
    rf_annual = _annual_rf(rf, r.index)
    ann = annualized_return(r)
    vol = annualized_volatility(r)
    downside = float(np.sqrt((r.clip(upper=0) ** 2).mean()) * np.sqrt(P))
    mdd = max_drawdown(r)
    return {
        "cumulative_return": float((1 + r).prod() - 1),
        "annualized_return": ann,
        "annualized_volatility": vol,
        "sharpe_rf": ratio(ann - rf_annual, vol),
        "sharpe_zero_cost": ratio(ann, vol),
        "sharpe_textbook": ratio(np.sqrt(P) * r.mean(), r.std()),
        "sortino_ratio": ratio(ann - rf_annual, downside),
        "max_drawdown": mdd,
        "calmar_ratio": ratio(ann, abs(mdd)),
        "rf_annual": rf_annual,
    }


def return_stats(r: pd.Series) -> dict[str, float]:
    """Distribution statistics of weekly returns (§11): hit rate, average gain and loss, profit factor, best and worst
    week, skew (sample), excess kurtosis (sample). Ratios with a zero denominator are NaN.
    """
    flat = not r.std() > 0
    return {
        "hit_rate": float((r > 0).mean()),
        "avg_gain": float(r[r > 0].mean()),
        "avg_loss": float(r[r < 0].mean()),
        "profit_factor": ratio(r[r > 0].sum(), abs(r[r < 0].sum())),
        "best": float(r.max()),
        "worst": float(r.min()),
        "skew": np.nan if flat else float(r.skew()),
        "kurtosis": np.nan if flat else float(r.kurt()),
    }


def holding_periods(s: pd.Series) -> pd.Series:
    """Lengths, in weeks, of the runs of the same non-zero signal (skeleton)."""
    run = (s != s.shift()).cumsum()
    runs = s.groupby(run).agg(["first", "size"])
    return runs.loc[runs["first"] != 0, "size"]


def behaviour(signals: pd.DataFrame, weights: pd.DataFrame) -> dict[str, float]:
    """Exposure and trading behaviour (§11) from the weekly signals (contract 9) and weights (contract 11) of one period.

    Skeleton definitions on the signals, N = number of traded columns (9 sectors + IVV): net and gross exposure,
    long/flat/short shares, turnover per year (every column flat before the first week of the period), average holding
    period. The same on the weights: net and gross exposure (Σw, Σ|w|) and turnover per year of the targets
    (Σ|w_t − w_{t−1}|, flat before the first week; the engine's drifted-weight turnover is in BacktestResult.turnover).
    """
    P = _periods_per_year()
    T = len(signals)
    s = signals.astype(np.float64)
    trades = s.diff().fillna(s)
    holdings = pd.concat([holding_periods(signals[ticker]) for ticker in signals.columns])
    w = weights.astype(np.float64)
    weight_trades = w.diff().fillna(w)
    return {
        "net_exposure": float(s.mean(axis=1).mean()),
        "gross_exposure": float(s.abs().mean(axis=1).mean()),
        "long": float((signals == 1).to_numpy().mean()),
        "flat": float((signals == 0).to_numpy().mean()),
        "short": float((signals == -1).to_numpy().mean()),
        "turnover_per_year": float(trades.abs().mean(axis=1).sum() * P / T),
        "avg_holding": float(holdings.mean()) if len(holdings) else np.nan,
        "net_exposure_weights": float(w.sum(axis=1).mean()),
        "gross_exposure_weights": float(w.abs().sum(axis=1).mean()),
        "turnover_per_year_weights": float(weight_trades.abs().sum(axis=1).sum() * P / T),
    }


def market(r: pd.Series, m: pd.Series, rf: pd.Series | float) -> dict[str, float]:
    """Market relation of weekly returns r to the benchmark's weekly returns m (§11, skeleton): beta, correlation, Jensen
    alpha (annualised, (r̄ − rf_w − β(m̄ − rf_w))·P with rf_w the mean weekly risk-free return), tracking error,
    information ratio, down- and up-market means, ΔSharpe (headline convention). Ratios with a zero denominator are NaN.
    """
    P = _periods_per_year()
    m = m.reindex(r.index)
    rf_w = float(_weekly_rf(rf, r.index).mean())
    beta = ratio(r.cov(m), m.var())
    tracking_error = float((r - m).std() * np.sqrt(P))
    return {
        "beta": beta,
        "correlation": ratio(r.cov(m), r.std() * m.std()),
        "alpha": float((r.mean() - rf_w - beta * (m.mean() - rf_w)) * P),
        "tracking_error": tracking_error,
        "information_ratio": ratio((r.mean() - m.mean()) * P, tracking_error),
        "down_market": float(r[m < 0].mean()),
        "up_market": float(r[m > 0].mean()),
        "sharpe_vs_market": sharpe_ratio(r, rf) - sharpe_ratio(m, rf),
    }


def tbill_weekly_returns(dgs3mo: pd.Series, weeks: pd.MultiIndex, sessions: pd.DatetimeIndex) -> pd.Series:
    """Weekly risk-free returns from the daily FRED 3-month T-bill yield (percent per year), on the weekly index.

    Lagged one session (Amendment 1): the rate of week t is the last observation dated on or before the session before
    the last session of week t, so it is known after Friday close t; it accrues over the holding week O(t+1) → O(t+2)
    as rate/100 · 7/365, the day count of the pre-registered borrow charge (§09). sessions: the equity calendar.
    Returns a float64 Series named `rf` of simple weekly returns (decimals); NaN where no rate is known yet.
    """
    observed = dgs3mo.dropna().sort_index()
    fridays = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    last_session = np.searchsorted(sessions.values, fridays.values, side="right") - 1
    in_week = (last_session >= 0) & (sessions.values[np.clip(last_session, 0, None)] >= (fridays - pd.Timedelta(days=4)).values)
    if not in_week.all():
        raise ValueError("a week of the weekly index has no session in the given calendar")
    previous_session = last_session - 1
    known = np.full(len(weeks), np.nan)
    ok = previous_session >= 0
    position = np.searchsorted(observed.index.values, sessions.values[previous_session[ok]], side="right") - 1
    values = np.where(position >= 0, observed.to_numpy(dtype=np.float64)[np.clip(position, 0, None)], np.nan)
    known[ok] = values
    return pd.Series(known / 100 * 7 / 365, index=weeks, name="rf", dtype=np.float64)


def period_average_rf(rf_weekly: pd.Series, period: pd.Series) -> dict[str, float]:
    """Annual average risk-free rate (decimal) of each period, {"IS": ..., "OOS": ...}, from weekly risk-free returns
    and the period labels of contract 7: the compound annual return (Π(1 + rf))^(P/T) − 1 over the weeks of the period.
    """
    labels = period.reindex(rf_weekly.index)
    out = {}
    for name in ("IS", "OOS"):
        weekly = rf_weekly[(labels == name).to_numpy()]
        if len(weekly):
            if weekly.isna().any():
                raise ValueError(f"the weekly risk-free series is missing in the {name} period")
            out[name] = annualized_return(weekly)
    return out


def period_metrics(net: pd.Series, period: pd.Series, signals: pd.DataFrame, weights: pd.DataFrame, m: pd.Series,
                   rf: pd.Series | float) -> dict[str, dict[str, float]]:
    """Every metric of one continuous book, computed separately on each period (Amendment 2 C5; skeleton: the equity
    restarts from 100 and turnover and holding periods restart at the first week of each period).

    net: the book's weekly returns (BacktestResult.net); period: "IS"/"OOS" on the same index; signals and weights: the
    traded signals and target weights of those weeks; m: the benchmark's weekly returns; rf: weekly series or annual
    constant. Returns {period: {metric: value}}, with `weeks` and `final_equity` (rebased to 100) added.
    """
    out = {}
    labels = period.reindex(net.index)
    for name in ("IS", "OOS"):
        mask = (labels == name).to_numpy()
        if not mask.any():
            continue
        r = net[mask]
        weeks = r.index
        metrics = {"weeks": float(len(r)), "final_equity": float(equity_curve(r).iloc[-1])}
        metrics |= performance(r, rf)
        metrics |= return_stats(r)
        metrics |= behaviour(signals.loc[weeks], weights.loc[weeks])
        metrics |= market(r, m, rf)
        out[name] = metrics
    return out


# -- market-neutral bonus tests of §11 (decision S34-9) -----------------------------------------------------------------


def hac_beta(r: pd.Series, m: pd.Series, lags: int, confidence: float = 0.95) -> dict[str, float]:
    """OLS beta of weekly returns r on the benchmark's weekly returns m (with intercept) and its Newey–West HAC interval
    (§11 bonus test 1, decision S34-9).

    beta = cov(r, m) / var(m) (as `market`). HAC variance of the slope: S / (T · s_x²), with x̃ = m − m̄, u the OLS
    residuals, z_t = x̃_t u_t, S = Γ_0 + 2 Σ_{j=1..lags} (1 − j/(lags + 1)) Γ_j, Γ_j = Σ_t z_t z_{t−j} / T and
    s_x² = Σ x̃² / T; lags = 0 gives White's heteroskedasticity-robust error. The interval is beta ± z_q · se with the
    normal quantile at `confidence`. Returns beta, se, lower, upper, lags, n_weeks.
    """
    m = m.reindex(r.index)
    x, y = m.to_numpy(dtype=np.float64), r.to_numpy(dtype=np.float64)
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError("hac_beta: missing values in the returns or the benchmark")
    t = len(y)
    if t < 3:
        raise ValueError("hac_beta: at least three weeks are needed")
    if not 0 < confidence < 1:
        raise ValueError(f"hac_beta: confidence must be in (0, 1), got {confidence}")
    lags = int(lags)
    if lags < 0:
        raise ValueError("hac_beta: lags must be >= 0")
    xc = x - x.mean()
    sxx = float(xc @ xc)
    if sxx == 0:
        raise ValueError("hac_beta: the benchmark has zero variance")
    beta = float(xc @ (y - y.mean()) / sxx)
    u = (y - y.mean()) - beta * xc
    z = xc * u
    s = float(z @ z) / t
    for j in range(1, min(lags, t - 1) + 1):
        s += 2.0 * (1.0 - j / (lags + 1.0)) * float(z[j:] @ z[:-j]) / t
    se = float(np.sqrt(max(s, 0.0) * t) / sxx)
    q = float(norm.ppf(0.5 + confidence / 2.0))
    return {"beta": beta, "se": se, "lower": beta - q * se, "upper": beta + q * se, "lags": float(lags),
            "n_weeks": float(t)}


def monthly_returns(r: pd.Series, realised_on: pd.Series) -> pd.Series:
    """Compounded monthly returns of weekly returns, each week in the calendar month of its realisation date (decision
    S34-9): Π(1 + r) − 1 over the weeks realised in the month. Index: month-end timestamps, named `month`."""
    dates = pd.DatetimeIndex(pd.to_datetime(realised_on.reindex(r.index)))
    if dates.isna().any():
        raise ValueError("monthly_returns: a week has no realisation date")
    months = dates.to_period("M")
    grouped = (1.0 + pd.Series(r.to_numpy(dtype=np.float64), index=months)).groupby(level=0).prod() - 1.0
    grouped.index = grouped.index.to_timestamp(how="end").normalize()
    return grouped.rename_axis("month").astype(np.float64)


def rolling_positive_share(r: pd.Series, window: int = 52) -> float:
    """Share of the T − window + 1 rolling windows of `window` consecutive weeks whose compounded return is > 0 (§11
    bonus test 4, decision S34-9); NaN when the series is shorter than the window."""
    if len(r) < window:
        return np.nan
    log_growth = np.log1p(r.to_numpy(dtype=np.float64))
    sums = np.convolve(log_growth, np.ones(window), mode="valid")
    return float(np.mean(sums > 0))


def calendar_year_returns(r: pd.Series, realised_on: pd.Series) -> pd.Series:
    """Compounded return of each calendar year of the realisation dates (§11 bonus test 4, decision S34-9). Index: the
    year (int), named `year`."""
    dates = pd.DatetimeIndex(pd.to_datetime(realised_on.reindex(r.index)))
    if dates.isna().any():
        raise ValueError("calendar_year_returns: a week has no realisation date")
    out = (1.0 + pd.Series(r.to_numpy(dtype=np.float64), index=dates.year)).groupby(level=0).prod() - 1.0
    return out.rename_axis("year").astype(np.float64)
