"""Vectorised weekly returns net of costs on drifted-weight turnover and short borrow, no cash interest (protocol section 09).

Interfaces: docs/interfaces.md, contracts 7 and 12. The engine never computes signals and never reads files.
Amendment 2 C5: one continuous book over In-Sample and Out-of-Sample (the OOS does not restart from cash); metrics are
split by period afterwards (src/metrics.py).
"""

import numpy as np
import pandas as pd

from src.config import load_config
from src.contracts import (
    TOLERANCE,
    BacktestResult,
    ContractError,
    SizingResult,
    universe,
    validate_backtest_result,
    validate_forward_returns,
    validate_weekly_index,
    validate_weights,
)

__all__ = ["BacktestResult", "forward_returns", "run"]


def forward_returns(weekly_open: pd.DataFrame, is_end: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Forward returns, realisation dates and periods on the full weekly index (§05, §10, contract 7).

    weekly_open: adjusted first open of each week (src.data.weekly_panel), columns = tradables. Returns
    (fwd, realised_on, period): fwd[t] = O(t+2) / O(t+1) − 1 (simple return, decimals; the last two rows NaN);
    realised_on[t] = date_open of week t+2 (NaT on the last two rows); period[t] = "IS" if realised_on ≤ is_end
    (default split.in_sample_end, 2019-12-27) else "OOS", missing where realised_on is NaT.
    The signal of week t, known after Friday close t, is executed at O(t+1) and realised at O(t+2).
    """
    validate_weekly_index(weekly_open.index)
    is_end = pd.Timestamp(load_config()["split"]["in_sample_end"] if is_end is None else is_end)
    tradables = list(universe().tradables)
    absent = [ticker for ticker in tradables if ticker not in weekly_open.columns]
    if absent:
        raise ContractError(f"weekly_open: missing columns {absent}")
    opens = weekly_open[tradables].astype(np.float64)
    fwd = opens.shift(-2) / opens.shift(-1) - 1

    date_open = pd.Series(weekly_open.index.get_level_values("date_open"), index=weekly_open.index)
    realised_on = date_open.shift(-2).rename("realised_on")
    labels = np.where(realised_on <= is_end, "IS", "OOS").astype(object)
    labels[realised_on.isna().to_numpy()] = None
    period = pd.Series(labels, index=weekly_open.index, name="period", dtype=object)

    validate_forward_returns(fwd, realised_on, period, is_end=is_end)
    return fwd, realised_on, period


def _evaluated_weeks(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.Index:
    """Weeks with weights and a realised forward return for every traded ticker; they must be consecutive in the weekly
    index of `returns` (no week in between without a position or a return)."""
    known = returns.reindex(weights.index)
    rows = weights.index[known.notna().all(axis=1).to_numpy()]
    positions = returns.index.get_indexer(rows)
    if len(rows) == 0:
        raise ValueError("no week has both weights and a realised forward return for every traded ticker")
    gaps = np.flatnonzero(np.diff(positions) != 1)
    if gaps.size:
        week = rows[gaps[0] + 1]
        raise ValueError(f"the evaluated weeks are not consecutive: a gap before the week {week} (missing weights or "
                         "forward returns in between)")
    return rows


def run(sizing: SizingResult, fwd: pd.DataFrame, period: pd.Series, cost_bps: float, borrow_annual: float,
        *, core_weight: float | None = None) -> BacktestResult:
    """Weekly book returns (§09, contract 12). The engine never computes signals and never reads files.

    sizing: target weights of week t (held O(t+1) → O(t+2)); fwd and period from forward_returns. cost_bps is in basis
    points per dollar traded (10 → 0.0010); borrow_annual is a decimal annual rate (0.02).
    gross_t = Σ w·R_fwd; turnover_t = Σ|w_t − w_pre_t| with
    w_pre_t = w_{t−1}·(1 + R_fwd_{t−1}) / (1 + net_{t−1}) (0 before the first week, entered from cash): the drifted
    weights divide by the book's value after costs and borrow (Amendment 3 C2; the pre-registered denominator
    1 + Σ w·R_fwd omitted them);
    costs_t = cost_bps/10 000 · turnover_t; borrow_t = borrow_annual · 7/365 · Σ_{w<0}|w|;
    net_t = gross_t − costs_t − borrow_t, no cash interest. Returns a BacktestResult on the consecutive weeks that have
    weights and a realised forward return for every traded ticker: one continuous book across IS and OOS
    (Amendment 2 C5).

    core_weight: the per-name core weight of the sizing (signal.core_weight by default; 0.5 / k for the sensitivity
    runs, Amendment 2 C4), used only to validate the weights.
    """
    traded = list(universe().traded)
    weeks = _evaluated_weeks(sizing.weights, fwd[traded])
    w = sizing.weights.loc[weeks, traded].to_numpy(dtype=np.float64)
    r = fwd.loc[weeks, traded].to_numpy(dtype=np.float64)

    gross = (w * r).sum(axis=1)
    borrow = borrow_annual * 7 / 365 * np.where(w < 0, -w, 0.0).sum(axis=1)
    cost_rate = cost_bps / 10_000
    # Loop over weeks: w_pre_t needs net_{t−1}, which needs turnover_{t−1} (Amendment 3 C2)
    turnover, net = np.zeros(len(w)), np.zeros(len(w))
    w_pre = np.zeros(w.shape[1])
    for t in range(len(w)):
        if t:
            value = 1 + net[t - 1]
            if value <= 0:
                raise ValueError("the book lost all its capital in a week: drifted weights are undefined")
            w_pre = w[t - 1] * (1 + r[t - 1]) / value
        turnover[t] = np.abs(w[t] - w_pre).sum()
        net[t] = gross[t] - cost_rate * turnover[t] - borrow[t]
    costs = cost_rate * turnover

    weeks_period = period.reindex(weeks)
    if weeks_period.isna().any():
        raise ValueError(f"period is missing for the week {weeks_period.index[weeks_period.isna().to_numpy()][0]}")

    def series(values, name: str) -> pd.Series:
        return pd.Series(np.asarray(values, dtype=np.float64), index=weeks, name=name)

    result = BacktestResult(
        weights=sizing.weights.loc[weeks, traded].astype(np.float64),
        gross=series(gross, "gross"),
        net=series(net, "net"),
        turnover=series(turnover, "turnover"),
        costs=series(costs, "costs"),
        borrow=series(borrow, "borrow"),
        residual_beta=series(sizing.residual_beta.loc[weeks], "residual_beta"),
        net_exposure=series(sizing.net_exposure.loc[weeks], "net_exposure"),
        hedge=series(sizing.hedge.loc[weeks], "hedge"),
        period=weeks_period.astype(object).rename("period"),
    )
    _validate(result, cost_bps, borrow_annual, core_weight)
    return result


def _validate(result: BacktestResult, cost_bps: float, borrow_annual: float, core_weight: float | None) -> None:
    """validate_backtest_result for the pre-registered core weight; for a sensitivity core weight (Amendment 2 C4),
    whose sizes validate_backtest_result cannot check yet, the weights are validated with that core weight and the
    accounting identities of contract 12 are checked here."""
    default = load_config()["signal"]["core_weight"]
    if core_weight is None or abs(core_weight - default) <= TOLERANCE:
        validate_backtest_result(result, cost_bps=cost_bps, borrow_annual=borrow_annual)
        return
    validate_weights(result.weights, core_weight=core_weight)
    w = result.weights.to_numpy()
    hedge = result.hedge.to_numpy()
    checks = {
        "net = gross - costs - borrow": result.net - (result.gross - result.costs - result.borrow),
        "costs = cost_bps / 10 000 * turnover": result.costs - cost_bps / 10_000 * result.turnover,
        "borrow = borrow_annual * 7/365 * short gross": result.borrow - borrow_annual * 7 / 365 * np.where(w < 0, -w, 0).sum(1),
        "net_exposure = sum of w": result.net_exposure - w.sum(axis=1),
        "w_IVV = hedge / (1 + |hedge|)": result.weights[universe().hedge] - hedge / (1 + np.abs(hedge)),
        "first turnover = sum of |w|": result.turnover.iloc[:1] - np.abs(w[:1]).sum(axis=1),
    }
    for rule, residual in checks.items():
        if (np.abs(np.asarray(residual)) > TOLERANCE).any():
            raise ContractError(f"backtest result: {rule} fails")
