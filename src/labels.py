"""Forward returns O(t+2)/O(t+1) - 1, relative training labels and label_end dates for purging (protocol section 05).

Not implemented yet: Phase 2.2 (Eliya). Interfaces: docs/interfaces.md, contracts 6 and 13.
"""

import pandas as pd

from src.contracts import WalkForwardFold


def make_labels(fwd: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Relative training labels with their label_end dates (§05, contract 6).

    fwd: forward returns of contract 7 (O(t+2)/O(t+1) − 1 on the weekly index); sessions: the equity sessions.
    y[t, i] = R_fwd[t, i] − mean over the 9 sectors; label_end = the actual session date of O(t+2), the first session of
    week t+2. Only weeks with a defined forward return get rows. Returns index (date_close, ticker), columns
    [y, label_end]; passes validate_labels.
    """
    raise NotImplementedError("Phase 2.2, Eliya")


def walk_forward_folds(weeks: pd.MultiIndex, label_end: pd.Series, cfg: dict) -> list[WalkForwardFold]:
    """Quarterly expanding-window refits of the In-Sample walk-forward (§07, §10, contract 13).

    weeks: the weekly index; label_end: the per-week label_end on it. In-Sample weeks only; training starts at the first
    week after split.warmup_end; test folds are the calendar years split.test_years, refit at the first week of each
    quarter; training rows have label_end ≤ purge_end = test_start − split.embargo_weeks × 7 days. Returns the records in
    chronological order; passes validate_folds.
    """
    raise NotImplementedError("Phase 2.2, Eliya")
