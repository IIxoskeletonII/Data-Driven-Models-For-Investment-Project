"""Relative training labels, label_end dates for purging, and the In-Sample walk-forward folds (protocol sections 05, 07
and 10).

Forward returns O(t+2)/O(t+1) - 1 are computed by src/backtest.py: forward_returns (contract 7); this module turns them
into labels (contract 6) and builds the quarterly refits of contract 13. Decisions S22-7 (label_end on weekly-index rows).
"""

import numpy as np
import pandas as pd

from src.config import load_config
from src.contracts import ContractError, WalkForwardFold, universe, validate_folds, validate_labels

LABEL_LEVELS = ["date_close", "ticker"]


def _sessions_ns(sessions: pd.DatetimeIndex) -> np.ndarray:
    """Sorted unique session dates as datetime64[ns]."""
    return np.unique(pd.DatetimeIndex(sessions).as_unit("ns").to_numpy())


def _label_end_of_rows(weeks: pd.MultiIndex, sessions: pd.DatetimeIndex) -> np.ndarray:
    """Per row t of the weekly index: the first session on or after date_open of the row two places later (S22-7).

    NaT for the last two rows and where no such session exists. Returns datetime64[ns] values.
    """
    days = _sessions_ns(sessions)
    opens = pd.DatetimeIndex(weeks.get_level_values("date_open")).as_unit("ns").to_numpy()
    result = np.full(len(opens), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    if len(opens) <= 2 or len(days) == 0:
        return result
    target = opens[2:]
    position = np.searchsorted(days, target, side="left")
    found = position < len(days)
    result[:-2][found] = days[position[found]]
    return result


def make_labels(fwd: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Relative training labels with their label_end dates (§05, contract 6).

    fwd: forward returns of contract 7 (O(t+2)/O(t+1) − 1 as decimals, on the weekly index; columns include the 9
    sectors, IVV and SPY are ignored); sessions: the equity sessions. y[t, i] = fwd[t, i] − mean of fwd[t] over the 9
    sectors; label_end[t] = the first session on or after date_open of the week two rows later in fwd's index, i.e. the
    session of O(t+2) (Tuesday after a holiday Monday; S22-7). A label of row t is realised only at label_end[t], after
    Friday close t. Rows exist only for weeks where all 9 sector forward returns are defined. Returns index
    (date_close, ticker) sorted, columns [y (float64), label_end (datetime64)]; passes validate_labels.
    """
    sectors = list(universe().sectors)
    missing = [ticker for ticker in sectors if ticker not in fwd.columns]
    if missing:
        raise ValueError(f"make_labels: fwd lacks the sector columns {missing}")
    values = fwd[sectors].to_numpy(dtype=np.float64)
    label_end = _label_end_of_rows(fwd.index, sessions)
    complete = ~np.isnan(values).any(axis=1)
    undated = complete & np.isnat(label_end)
    if undated.any():
        week = pd.Timestamp(fwd.index.get_level_values("date_close")[np.flatnonzero(undated)[0]]).date()
        raise ValueError(f"make_labels: week {week} has forward returns but no session at the open of week t+2")
    values, label_end = values[complete], label_end[complete]
    dates = pd.DatetimeIndex(fwd.index.get_level_values("date_close"))[complete]
    order = np.argsort(np.asarray(sectors, dtype=object))
    tickers = [sectors[i] for i in order]
    relative = values - values.mean(axis=1, keepdims=True)
    index = pd.MultiIndex.from_arrays([np.repeat(dates, len(tickers)), np.tile(np.asarray(tickers, dtype=object), len(dates))],
                                      names=LABEL_LEVELS)
    labels = pd.DataFrame({"y": relative[:, order].reshape(-1),
                           "label_end": np.repeat(label_end, len(tickers))}, index=index)
    labels = labels.sort_index()
    validate_labels(labels)
    return labels


def _label_end_ahead(weeks: pd.MultiIndex, sessions: pd.DatetimeIndex, rows_ahead: int) -> np.ndarray:
    """Per row t of the weekly index: the first session on or after date_open of the row `rows_ahead` places later.

    NaT for the last `rows_ahead` rows and where no such session exists. With rows_ahead = 2 this is
    _label_end_of_rows (S22-7). Returns datetime64[ns] values.
    """
    days = _sessions_ns(sessions)
    opens = pd.DatetimeIndex(weeks.get_level_values("date_open")).as_unit("ns").to_numpy()
    result = np.full(len(opens), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    if len(opens) <= rows_ahead or len(days) == 0:
        return result
    target = opens[rows_ahead:]
    position = np.searchsorted(days, target, side="left")
    found = position < len(days)
    result[:-rows_ahead][found] = days[position[found]]
    return result


def make_horizon_labels(weekly_open: pd.DataFrame, sessions: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    """Relative training labels over `horizon` weeks with their label_end dates (Amendment 9 C1, decision S41-1).

    weekly_open: adjusted first open of each week (src.data.weekly_panel), columns include the 9 sectors; sessions: the
    equity sessions. R_h[t, i] = O(t+h+1, i) / O(t+1, i) − 1 (decimal; for h = 1 the arithmetic of
    src.backtest.forward_returns); y[t, i] = R_h[t, i] − mean of R_h[t] over the 9 sectors; label_end[t] = the first
    session on or after date_open of the week h+1 rows later (the session of O(t+h+1): for h = 4, O(t+5)). The label of
    row t is realised only at label_end[t], after Friday close t. Rows exist only where the 9 sector values are defined.
    Returns index (date_close, ticker) sorted, columns [y (float64), label_end (datetime64)]; passes validate_labels.
    With horizon = 1 the result equals make_labels(fwd, sessions).
    """
    horizon = int(horizon)
    if horizon < 1:
        raise ValueError(f"make_horizon_labels: horizon must be at least 1 week, got {horizon}")
    sectors = list(universe().sectors)
    missing = [ticker for ticker in sectors if ticker not in weekly_open.columns]
    if missing:
        raise ValueError(f"make_horizon_labels: weekly_open lacks the sector columns {missing}")
    opens = weekly_open[sectors].astype(np.float64)
    values = (opens.shift(-(horizon + 1)) / opens.shift(-1) - 1).to_numpy(dtype=np.float64)
    label_end = _label_end_ahead(weekly_open.index, sessions, horizon + 1)
    complete = ~np.isnan(values).any(axis=1)
    undated = complete & np.isnat(label_end)
    if undated.any():
        week = pd.Timestamp(weekly_open.index.get_level_values("date_close")[np.flatnonzero(undated)[0]]).date()
        raise ValueError(f"make_horizon_labels: week {week} has a {horizon}-week return but no session at the open of "
                         f"week t+{horizon + 1}")
    values, label_end = values[complete], label_end[complete]
    dates = pd.DatetimeIndex(weekly_open.index.get_level_values("date_close"))[complete]
    order = np.argsort(np.asarray(sectors, dtype=object))
    tickers = [sectors[i] for i in order]
    relative = values - values.mean(axis=1, keepdims=True)
    index = pd.MultiIndex.from_arrays([np.repeat(dates, len(tickers)), np.tile(np.asarray(tickers, dtype=object), len(dates))],
                                      names=LABEL_LEVELS)
    labels = pd.DataFrame({"y": relative[:, order].reshape(-1),
                           "label_end": np.repeat(label_end, len(tickers))}, index=index)
    labels = labels.sort_index()
    validate_labels(labels)
    return labels


def label_end_by_week(labels: pd.DataFrame, weeks: pd.MultiIndex) -> pd.Series:
    """label_end of each week of the weekly index `weeks` (contract 6): the session of O(t+2), identical for the 9
    sectors; NaT where the week has no label. Returns a datetime64[ns] Series named "label_end" on `weeks`.
    """
    per_week = labels["label_end"].groupby(level="date_close").first()
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    values = pd.to_datetime(per_week.reindex(closes)).to_numpy(dtype="datetime64[ns]")
    return pd.Series(values, index=weeks, name="label_end")


def _label_end_on(weeks: pd.MultiIndex, label_end: pd.Series) -> pd.Series:
    """The per-week label_end aligned to `weeks` by date_close (NaT where absent), as datetime64[ns]."""
    if isinstance(label_end.index, pd.MultiIndex):
        keys = pd.DatetimeIndex(label_end.index.get_level_values("date_close"))
    else:
        keys = pd.DatetimeIndex(label_end.index)
    by_close = pd.Series(pd.to_datetime(label_end).to_numpy(dtype="datetime64[ns]"), index=keys)
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    return pd.Series(by_close.reindex(closes).to_numpy(dtype="datetime64[ns]"), index=weeks, name="label_end")


def _quarter_starts(test_weeks: pd.DatetimeIndex) -> np.ndarray:
    """Positions of the first test week of each calendar quarter (by date_close)."""
    key = np.asarray(test_weeks.year * 10 + test_weeks.quarter)
    return np.flatnonzero(np.concatenate([[True], key[1:] != key[:-1]]))


def _fold(closes: pd.DatetimeIndex, ends: np.ndarray, first_scored: pd.Timestamp, test_start: pd.Timestamp,
          test_end: pd.Timestamp, embargo_weeks: int) -> WalkForwardFold:
    """One refit: training weeks from first_scored with label_end ≤ purge_end = test_start − 7 × embargo_weeks days."""
    purge_end = test_start - pd.Timedelta(days=7 * embargo_weeks)
    train = np.asarray(closes >= first_scored) & ~np.isnat(ends) & (ends <= purge_end.to_datetime64())
    if not train.any():
        raise ValueError(f"walk_forward_folds: no training week for the refit at {test_start.date()}")
    if ends[train].max() > purge_end.to_datetime64():
        raise ContractError(f"walk_forward_folds: a training label ends after purge_end {purge_end.date()}")
    return WalkForwardFold(test_year=int(test_start.year), refit=int(test_start.quarter), train_start=first_scored,
                           train_end=pd.Timestamp(closes[train].max()), purge_end=purge_end, test_start=test_start,
                           test_end=test_end)


def walk_forward_folds(weeks: pd.MultiIndex, label_end: pd.Series, cfg: dict) -> list[WalkForwardFold]:
    """Quarterly expanding-window refits of the In-Sample walk-forward (§07, §10, contract 13).

    weeks: the weekly index; label_end: the per-week label_end on it (label_end_by_week). In-Sample weeks are those
    with label_end ≤ split.in_sample_end. Test weeks are the In-Sample weeks whose date_close lies in the calendar years
    split.test_years; a refit happens at the first test week of each calendar quarter (the cutoff test_start, after its
    Friday close) and scores the weeks up to the one before the next refit (the last In-Sample week for the final
    record). Training starts at the first week with date_close after split.warmup_end and holds the weeks with
    label_end ≤ purge_end = test_start − split.embargo_weeks × 7 days. Returns the records in chronological order
    (48 on the real calendar); passes validate_folds.
    """
    cfg = load_config() if cfg is None else cfg
    split = cfg["split"]
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    ends = _label_end_on(weeks, label_end).to_numpy(dtype="datetime64[ns]")
    is_end = pd.Timestamp(split["in_sample_end"]).to_datetime64()
    in_sample = ~np.isnat(ends) & (ends <= is_end)
    scored = closes[closes > pd.Timestamp(split["warmup_end"])]
    if len(scored) == 0:
        raise ValueError(f"walk_forward_folds: no week after split.warmup_end {split['warmup_end']}")
    first_year, last_year = (int(year) for year in split["test_years"])
    test_weeks = closes[in_sample & np.asarray((closes.year >= first_year) & (closes.year <= last_year))]
    if len(test_weeks) == 0:
        raise ValueError(f"walk_forward_folds: no In-Sample week in the test years {first_year}-{last_year}")
    starts = _quarter_starts(test_weeks)
    stops = np.append(starts[1:] - 1, len(test_weeks) - 1)
    embargo_weeks = int(split["embargo_weeks"])
    folds = [_fold(closes, ends, pd.Timestamp(scored[0]), pd.Timestamp(test_weeks[start]), pd.Timestamp(test_weeks[stop]),
                   embargo_weeks) for start, stop in zip(starts, stops, strict=True)]
    validate_folds(folds, embargo_weeks=embargo_weeks, label_end=pd.Series(ends, index=weeks, name="label_end"))
    return folds


def assert_purged(train_label_end: pd.Series, fold: WalkForwardFold) -> None:
    """Purging check of every fit (§05, contract 13): every training label must be realised by fold.purge_end.

    train_label_end: label_end of the training rows (datetime64). Raises ContractError if any value is NaT or later
    than fold.purge_end; returns None otherwise.
    """
    ends = pd.to_datetime(pd.Series(train_label_end)).to_numpy(dtype="datetime64[ns]")
    if np.isnat(ends).any():
        raise ContractError(f"assert_purged: a training row has no label_end (refit {fold.test_year} Q{fold.refit})")
    late = ends > fold.purge_end.to_datetime64()
    if late.any():
        raise ContractError(f"assert_purged: training label_end {pd.Timestamp(ends[late].max()).date()} is after purge_end "
                            f"{fold.purge_end.date()} (refit {fold.test_year} Q{fold.refit}, §05 purge and embargo)")
