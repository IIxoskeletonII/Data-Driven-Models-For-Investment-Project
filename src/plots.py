"""Equity curves from 100 per period (log scale), drawdowns and exposures, as interactive HTML and static PNG.

Not implemented yet: Phase 3.3 (Mattia).
"""

from pathlib import Path

import pandas as pd

from src.contracts import BacktestResult


def equity_curves(returns: pd.DataFrame, period: pd.Series, path: Path) -> None:
    """Equity curves of weekly net returns (one column per series), each starting at 100 in each period, on a shared
    dated axis, log scale (§11). Writes `path` with .html and .png suffixes.
    """
    raise NotImplementedError("Phase 3.3, Mattia")


def drawdowns(returns: pd.DataFrame, period: pd.Series, path: Path) -> None:
    """Drawdown curves of weekly net returns per period (§11). Writes `path` with .html and .png suffixes."""
    raise NotImplementedError("Phase 3.3, Mattia")


def exposures(result: BacktestResult, path: Path) -> None:
    """Weekly gross, net and hedge exposure and residual beta of a backtest (§09, §11). Writes `path` with .html and
    .png suffixes.
    """
    raise NotImplementedError("Phase 3.3, Mattia")
