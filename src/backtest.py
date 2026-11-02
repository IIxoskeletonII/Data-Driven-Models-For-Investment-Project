"""Vectorised weekly returns net of costs on drifted-weight turnover and short borrow, no cash interest (protocol section 09).

Not implemented yet: Phase 2.1 (Mattia). Interfaces: docs/interfaces.md, contracts 7 and 12.
"""

import pandas as pd

from src.contracts import BacktestResult, SizingResult

__all__ = ["BacktestResult", "forward_returns", "run"]


def forward_returns(weekly_open: pd.DataFrame, is_end: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Forward returns, realisation dates and periods on the full weekly index (§05, §10, contract 7).

    weekly_open: adjusted first open of each week (src.data.weekly_panel), columns = tradables. Returns
    (fwd, realised_on, period): fwd[t] = O(t+2) / O(t+1) − 1 (simple return, decimals; the last two rows NaN);
    realised_on[t] = date_open of week t+2 (NaT on the last two rows); period[t] = "IS" if realised_on ≤ is_end
    (default split.in_sample_end, 2019-12-27) else "OOS", missing where realised_on is NaT.
    The signal of week t, known after Friday close t, is executed at O(t+1) and realised at O(t+2).
    """
    raise NotImplementedError("Phase 2.1, Mattia")


def run(sizing: SizingResult, fwd: pd.DataFrame, period: pd.Series, cost_bps: float, borrow_annual: float) -> BacktestResult:
    """Weekly book returns (§09, contract 12). The engine never computes signals and never reads files.

    sizing: target weights of week t (held O(t+1) → O(t+2)); fwd and period from forward_returns. cost_bps is in basis
    points per dollar traded (10 → 0.0010); borrow_annual is a decimal annual rate (0.02).
    gross_t = Σ w·R_fwd; turnover_t = Σ|w_t − w_pre_t| with w_pre the previous weights drifted by their realised returns
    (0 before the first week); costs_t = cost_bps/10 000 · turnover_t; borrow_t = borrow_annual · 7/365 · Σ_{w<0}|w|;
    net_t = gross_t − costs_t − borrow_t, no cash interest. Returns a BacktestResult on the consecutive weeks that have
    weights and a realised forward return for every traded ticker.
    """
    raise NotImplementedError("Phase 2.1, Mattia")
