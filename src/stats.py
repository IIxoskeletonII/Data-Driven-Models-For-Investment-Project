"""Inference of protocol section 11: paired stationary block bootstrap, HAC rank IC, Ledoit-Wolf Sharpe test,
Deflated Sharpe Ratio and PBO by CSCV.

Not implemented yet: Phase 3.3 (Eliya). Interfaces: docs/interfaces.md, contract 16.
"""

from collections.abc import Mapping

import pandas as pd


def paired_block_bootstrap(candidate: pd.Series, baseline: pd.Series, n_resamples: int = 5000, block: int = 4,
                           seed: int = 42) -> dict[str, float]:
    """Paired stationary block bootstrap of the weekly net return difference candidate − baseline (§07, §11).

    Both series are weekly net returns on the same weekly index; mean block length `block` weeks (4, sensitivity 8),
    `n_resamples` resamples (5,000), fixed seed. Returns the Sharpe uplift, its interval and P(uplift > 0).
    """
    raise NotImplementedError("Phase 3.3, Eliya")


def rank_ic(scores: pd.DataFrame, fwd: pd.DataFrame) -> dict[str, float]:
    """Weekly Spearman rank IC between scores of week t (known after Friday close t) and the forward returns of contract
    7 over the sectors, with its HAC-adjusted mean and t-statistic (§11).
    """
    raise NotImplementedError("Phase 3.3, Eliya")


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int, trial_sharpes: pd.Series | None = None) -> float:
    """Deflated Sharpe Ratio of a weekly return series (§10, §11), with N = every human and agent trial in
    docs/trial_log.csv.
    """
    raise NotImplementedError("Phase 3.3, Eliya")


def pbo_cscv(returns: pd.DataFrame, n_blocks: int = 16) -> float:
    """Probability of backtest overfitting by CSCV (§10, §11) on the In-Sample weekly return matrix (one column per
    candidate configuration), split into n_blocks blocks. A diagnostic; it never chooses the model.
    """
    raise NotImplementedError("Phase 3.3, Eliya")


def sharpe_difference_test(a: pd.Series, b: pd.Series) -> dict[str, float]:
    """Ledoit-Wolf (2008) HAC test of the Sharpe difference of two weekly return series on the same index (§11)."""
    raise NotImplementedError("Phase 3.3, Eliya")


def selection_gate(results: Mapping[str, pd.Series], m0: pd.Series, cfg: dict | None = None) -> str:
    """The §07 selection rule on In-Sample walk-forward weekly net returns.

    results: candidate name → weekly net returns; m0: the hurdle's weekly net returns. A candidate passes with net
    Sharpe ≥ M0 + selection.sharpe_uplift, max drawdown at most selection.mdd_tolerance worse than M0, and paired block
    bootstrap P(uplift > 0) ≥ selection.bootstrap_prob. Returns the first passing name in models.candidate_order, else
    "M0_star".
    """
    raise NotImplementedError("Phase 3.3, Eliya")
