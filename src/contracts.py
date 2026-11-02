"""Interface contract between modules (docs/interfaces.md): universe, result dataclasses, model protocol and validators.

Every producer calls the matching validate_* function on what it returns; every consumer may call it on what it
receives. Validators return None, never modify their arguments, and raise ContractError naming the object, the rule
broken and the first offending week or column. Universe and thresholds come from config.yaml, never from this file.
Section numbers (§05, §06, ...) are those of docs/preregistration.md.
"""

from __future__ import annotations

import functools
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_datetime64_dtype, is_string_dtype

from src.config import load_config

TOLERANCE = 1e-12  # docs/interfaces.md, contracts 6, 11 and 12
WEEK_LEVELS = ["date_open", "date_close"]
FEATURE_LEVELS = ["date_close", "ticker"]
LABEL_COLUMNS = ["y", "label_end"]
PERIODS = ("IS", "OOS")
MARKET_STATE_REQUIRED = ("BEAR24", "VIX")  # Amendment 2 C1 (indicator, never scaled) and C7 (lagged VIX level)
LABEL_END_MIN_DAYS = 10  # label_end of week t is a session of week t+2: at least its Monday, date_close(t) + 10 days


class ContractError(ValueError):
    """An object broke the interface contract of docs/interfaces.md."""


# ---------------------------------------------------------------------------------------------------------------------
# Universe and names
# ---------------------------------------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _default_config() -> dict:
    """config.yaml, read once per process (the validators read thresholds from it)."""
    return load_config()


def _cfg(cfg: dict | None) -> dict:
    return _default_config() if cfg is None else cfg


@dataclass(frozen=True)
class Universe:
    """Tickers of config.yaml (§04): sectors, hedge (IVV) and benchmark (SPY, never traded), in universe order."""

    sectors: tuple[str, ...]
    hedge: str
    benchmark: str
    traded: tuple[str, ...]
    tradables: tuple[str, ...]


def universe(cfg: dict | None = None) -> Universe:
    """The universe of config.yaml: `traded` = sectors + hedge (10), `tradables` = traded + benchmark (11)."""
    data = _cfg(cfg)["data"]
    sectors = tuple(data["tickers"])
    traded = sectors + (data["hedge"],)
    return Universe(sectors=sectors, hedge=data["hedge"], benchmark=data["benchmark"], traded=traded,
                    tradables=traded + (data["benchmark"],))


def interaction_name(terms: Sequence[str]) -> str:
    """Column name of an interaction (§06, contract 5): the terms joined by `_x_`, e.g. BETA52_x_BEAR24."""
    terms = list(terms)
    if not terms or not all(isinstance(term, str) and term for term in terms):
        raise ContractError(f"interaction_name: terms must be a non-empty sequence of non-empty strings, got {terms!r}")
    return "_x_".join(terms)


def interaction_columns(cfg: dict | None = None) -> list[str]:
    """The five pre-registered interaction columns of M2/M3 (§06), in `features.interactions` order."""
    return [interaction_name(terms) for terms in _cfg(cfg)["features"]["interactions"]]


# ---------------------------------------------------------------------------------------------------------------------
# Result dataclasses and the model protocol
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class SizingResult:
    """Output of src.sizing.target_weights (§09, contract 11), every field on the same weekly index.

    weights: target weights w (TRADED, float64), held from O(t+1) to O(t+2); signals: sector signals and the IVV signal
    sign(h) (TRADED, int8); hedge: h before scaling; residual_beta: (β_c + h·β̂_IVV) / (1 + |h|); net_exposure:
    h / (1 + |h|); cap_binds: |β_c / β̂_IVV| > cap (bool). All known after Friday close t.
    """

    weights: pd.DataFrame
    signals: pd.DataFrame
    hedge: pd.Series
    residual_beta: pd.Series
    net_exposure: pd.Series
    cap_binds: pd.Series


@dataclass(frozen=True, eq=False)
class BacktestResult:
    """Output of src.backtest.run (§09, contract 12), every field on the same weekly index.

    Row t: weights held from O(t+1) to O(t+2); gross = Σ w·R_fwd; turnover = Σ|w − w_pre| (drifted weights);
    costs = cost_bps/10 000 · turnover; borrow = borrow_annual · 7/365 · Σ_{w<0}|w|; net = gross − costs − borrow
    (no cash interest); residual_beta, net_exposure and hedge from SizingResult; period "IS"/"OOS" by realisation
    date (contract 7). Returns are simple weekly returns (decimals). Each Series is named after its field.
    """

    weights: pd.DataFrame
    gross: pd.Series
    net: pd.Series
    turnover: pd.Series
    costs: pd.Series
    borrow: pd.Series
    residual_beta: pd.Series
    net_exposure: pd.Series
    hedge: pd.Series
    period: pd.Series


@dataclass(frozen=True)
class WalkForwardFold:
    """One quarterly refit of the In-Sample walk-forward (§07, §10, contract 13).

    The model is fitted after the close of `test_start` on weeks `train_start … train_end` (all with
    label_end ≤ purge_end = test_start − embargo_weeks × 7 days) and scores the weeks `test_start … test_end`.
    Dates are `date_close` Fridays, except purge_end, a limit on label_end.
    """

    test_year: int
    refit: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    purge_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@runtime_checkable
class ScoreModel(Protocol):
    """A ranking model of the AI ladder (§07, contract 14).

    fit(X, y) learns from a purged design matrix (index date_close × ticker) and returns self; score(X) returns a float64
    Series named `score` on exactly X's index (higher = more attractive) without changing the fitted model.
    Deterministic, no file or network access, no data other than the arguments.
    """

    name: str

    def fit(self, X: pd.DataFrame, y: pd.Series) -> ScoreModel: ...

    def score(self, X: pd.DataFrame) -> pd.Series: ...


# ---------------------------------------------------------------------------------------------------------------------
# Private checks
# ---------------------------------------------------------------------------------------------------------------------


def _fail(obj: str, message: str) -> None:
    raise ContractError(f"{obj}: {message}")


def _day(value) -> str:
    return "NaT" if pd.isna(value) else str(pd.Timestamp(value).date())


def _row_label(index: pd.Index, position: int) -> str:
    """Readable label of one row: a week (date_open, date_close), a (date_close, ticker) pair or a date."""
    if isinstance(index, pd.MultiIndex):
        values = index[position]
        if list(index.names) == WEEK_LEVELS:
            return f"week {_day(values[0])}/{_day(values[1])}"
        return "(" + ", ".join(_day(v) if isinstance(v, pd.Timestamp) else str(v) for v in values) + ")"
    value = index[position]
    return _day(value) if isinstance(value, pd.Timestamp) else str(value)


def _first(mask: np.ndarray) -> int:
    return int(np.flatnonzero(mask)[0])


def _first_cell(mask: np.ndarray) -> tuple[int, int]:
    """(row, column) of the first True cell of a 2-D mask, scanning row by row."""
    row, column = np.argwhere(mask)[0]
    return int(row), int(column)


def _require_frame(obj: str, frame) -> None:
    if not isinstance(frame, pd.DataFrame):
        _fail(obj, f"must be a pandas DataFrame, got {type(frame).__name__}")


def _require_series(obj: str, series, name: str | None = None) -> None:
    if not isinstance(series, pd.Series):
        _fail(obj, f"must be a pandas Series, got {type(series).__name__}")
    if name is not None and series.name != name:
        _fail(obj, f"must be named {name!r}, got {series.name!r}")


def _check_dates(obj: str, values, allow_nat: bool = False) -> np.ndarray:
    """tz-naive datetime64 (any resolution) at midnight; returns the values as datetime64[ns]."""
    dtype = values.dtype
    if is_datetime64_any_dtype(dtype) and not is_datetime64_dtype(dtype):
        _fail(obj, f"must be tz-naive, got {dtype}")
    if not is_datetime64_dtype(dtype):
        _fail(obj, f"must have a datetime64 dtype, got {dtype}")
    dates = pd.DatetimeIndex(values)
    missing = np.asarray(dates.isna())
    if missing.any() and not allow_nat:
        _fail(obj, f"has a missing date (NaT) at position {_first(missing)}")
    present = dates[~missing]
    not_midnight = np.asarray(present != present.normalize())
    if not_midnight.any():
        _fail(obj, f"date {present[_first(not_midnight)]} is not at midnight")
    return np.asarray(dates.as_unit("ns").values)


def _check_columns(obj: str, frame: pd.DataFrame, expected: Sequence[str]) -> None:
    actual, expected = list(frame.columns), list(expected)
    if actual != expected:
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        detail = f"missing {missing}" if missing else f"unexpected {extra}" if extra else "wrong order"
        _fail(obj, f"columns must be exactly {expected} in this order, got {actual} ({detail})")


def _check_dtype(obj: str, frame: pd.DataFrame, dtype: np.dtype) -> None:
    for column in frame.columns:
        if frame[column].dtype != dtype:
            _fail(obj, f"column {column!r} must have dtype {dtype}, got {frame[column].dtype}")


def _values(frame: pd.DataFrame) -> np.ndarray:
    return frame.to_numpy(dtype=np.float64, copy=True)


def _check_finite_or_nan(obj: str, frame: pd.DataFrame, allow_nan: bool = True) -> np.ndarray:
    """No ±inf (and no NaN unless allowed); returns the values as a float64 array."""
    values = _values(frame)
    infinite = np.isinf(values)
    if infinite.any():
        row, column = _first_cell(infinite)
        _fail(obj, f"infinite value in {_row_label(frame.index, row)}, column {frame.columns[column]!r}")
    if not allow_nan:
        missing = np.isnan(values)
        if missing.any():
            row, column = _first_cell(missing)
            _fail(obj, f"missing value (NaN) in {_row_label(frame.index, row)}, column {frame.columns[column]!r}")
    return values


def _check_leading_nan(obj: str, frame: pd.DataFrame, values: np.ndarray, groups: np.ndarray | None = None) -> None:
    """NaN only in a leading warm-up block: once a column is complete on a row (or date group), it stays complete."""
    if values.size == 0:
        return
    missing = np.isnan(values)
    if groups is not None:  # collapse the rows of each date into one: missing if any row of the date is missing
        _, start = np.unique(groups, return_index=True)
        missing_by_group = np.logical_or.reduceat(missing, np.sort(start), axis=0)
        first_row = np.sort(start)
    else:
        missing_by_group, first_row = missing, np.arange(len(values))
    complete_before = np.maximum.accumulate(~missing_by_group, axis=0)
    late = missing_by_group & np.vstack([np.zeros((1, values.shape[1]), dtype=bool), complete_before[:-1]])
    if late.any():
        row, column = _first_cell(late)
        _fail(obj, f"missing value (NaN) after the warm-up in {_row_label(frame.index, first_row[row])}, "
                   f"column {frame.columns[column]!r}")


def _check_same_index(obj: str, index: pd.Index, reference: pd.Index, reference_name: str) -> None:
    if not index.equals(reference):
        _fail(obj, f"index must equal the index of {reference_name} (same weeks, same order)")


def _check_feature_index(obj: str, index: pd.Index, cfg: dict | None = None) -> np.ndarray:
    """Index (date_close, ticker): Friday dates, sector tickers, all 9 sectors per date, sorted, unique."""
    if not isinstance(index, pd.MultiIndex) or list(index.names) != FEATURE_LEVELS:
        names = list(index.names) if isinstance(index, pd.MultiIndex) else [index.name]
        _fail(obj, f"index must be a MultiIndex with levels {FEATURE_LEVELS}, got {names}")
    dates = _check_dates(f"{obj} level 'date_close'", index.get_level_values("date_close"))
    not_friday = np.asarray(pd.DatetimeIndex(dates).day_of_week != 4)
    if not_friday.any():
        _fail(obj, f"date_close {_day(dates[_first(not_friday)])} is not a Friday")
    sectors = universe(cfg).sectors
    tickers = index.get_level_values("ticker")
    unknown = ~np.isin(np.asarray(tickers, dtype=object), np.asarray(sectors, dtype=object))
    if unknown.any():
        _fail(obj, f"ticker {tickers[_first(unknown)]!r} on {_day(dates[_first(unknown)])} is not one of the sectors {list(sectors)}")
    if not index.is_unique:
        duplicated = np.asarray(index.duplicated())
        _fail(obj, f"duplicate row {_row_label(index, _first(duplicated))}")
    if not index.is_monotonic_increasing:
        _fail(obj, "rows must be sorted by (date_close, ticker)")
    counts = pd.Series(1, index=pd.DatetimeIndex(dates)).groupby(level=0).size()
    incomplete = counts[counts != len(sectors)]
    if len(incomplete):
        _fail(obj, f"date_close {_day(incomplete.index[0])} has {incomplete.iloc[0]} sectors, expected all {len(sectors)}")
    return dates


# ---------------------------------------------------------------------------------------------------------------------
# Validators (docs/interfaces.md, "Validators and helpers of src/contracts.py")
# ---------------------------------------------------------------------------------------------------------------------


def validate_weekly_index(index: pd.Index) -> None:
    """Weekly index (contract 2): MultiIndex (date_open, date_close) = (Monday, Friday of the same week).

    Levels tz-naive datetime64 at midnight, no NaT, date_close = date_open + 4 days, rows strictly increasing (unique).
    Row t holds what is known after the close of the last session of week t (§05).
    """
    obj = "weekly index"
    if not isinstance(index, pd.MultiIndex) or list(index.names) != WEEK_LEVELS:
        names = list(index.names) if isinstance(index, pd.MultiIndex) else [index.name]
        _fail(obj, f"must be a MultiIndex with levels {WEEK_LEVELS}, got {names}")
    opens = pd.DatetimeIndex(_check_dates(f"{obj} level 'date_open'", index.get_level_values("date_open")))
    closes = pd.DatetimeIndex(_check_dates(f"{obj} level 'date_close'", index.get_level_values("date_close")))
    not_monday = np.asarray(opens.day_of_week != 0)
    if not_monday.any():
        _fail(obj, f"date_open {_day(opens[_first(not_monday)])} ({_row_label(index, _first(not_monday))}) is not a Monday")
    not_friday = np.asarray(closes != opens + pd.Timedelta(days=4))
    if not_friday.any():
        _fail(obj, f"{_row_label(index, _first(not_friday))}: date_close must be date_open + 4 days (the Friday)")
    not_increasing = np.asarray(closes[1:] <= closes[:-1])
    if not_increasing.any():
        _fail(obj, f"rows must be strictly increasing and unique: {_row_label(index, _first(not_increasing) + 1)} "
                   f"does not follow {_row_label(index, _first(not_increasing))}")


def validate_daily_frame(frame: pd.DataFrame, columns: Sequence[str] | None = None) -> None:
    """Daily frame (contract 1): index `date` of sessions, columns a subset of `columns` (default: tradables) in order.

    Index: tz-naive datetime64 at midnight, strictly increasing, no weekends. Values float64, no ±inf. Price columns
    (tradables: adjusted opens or closes, the close being the total-return index) are > 0 and NaN only before the
    ticker's first date. Other columns (market series such as VIX or FRED rates, percent) are only checked for float64
    and no ±inf: rates may be zero or negative and FRED has gaps.
    """
    obj = "daily frame"
    _require_frame(obj, frame)
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.name != "date":
        _fail(obj, f"index must be a DatetimeIndex named 'date', got {type(frame.index).__name__} named {frame.index.name!r}")
    dates = pd.DatetimeIndex(_check_dates(f"{obj} index", frame.index))
    weekend = np.asarray(dates.day_of_week >= 5)
    if weekend.any():
        _fail(obj, f"date {_day(dates[_first(weekend)])} is a weekend day, not a session")
    not_increasing = np.asarray(dates[1:] <= dates[:-1])
    if not_increasing.any():
        _fail(obj, f"dates must be strictly increasing and unique: {_day(dates[_first(not_increasing) + 1])}")
    allowed = list(universe().tradables if columns is None else columns)
    actual = list(frame.columns)
    unknown = [c for c in actual if c not in allowed]
    if unknown or len(set(actual)) != len(actual) or actual != [c for c in allowed if c in actual]:
        _fail(obj, f"columns must be a subset of {allowed} in this order without duplicates, got {actual}")
    _check_dtype(obj, frame, np.dtype(np.float64))
    values = _check_finite_or_nan(obj, frame)
    prices = [i for i, c in enumerate(actual) if c in universe().tradables]
    if not prices:
        return
    price_values = values[:, prices]
    not_positive = ~np.isnan(price_values) & (price_values <= 0)
    if not_positive.any():
        row, column = _first_cell(not_positive)
        _fail(obj, f"price {float(price_values[row, column]):.17g} on {_day(dates[row])}, column {actual[prices[column]]!r} must be > 0")
    _check_leading_nan(obj, frame.iloc[:, prices], price_values)


def validate_features(features: pd.DataFrame, columns: Sequence[str] | None = None) -> None:
    """Asset features (§06, contract 3): index (date_close, ticker), exactly `columns` (default features.asset), float64.

    Every date_close is a Friday with all 9 sectors; sorted by (date_close, ticker), unique; no ±inf; NaN only in the
    leading warm-up (until a window is full). Values are known after Friday close t (cross-sectional z-scoring is the
    producer's construction and is not re-checked here).
    """
    obj = "features"
    _require_frame(obj, features)
    dates = _check_feature_index(obj, features.index)
    _check_columns(obj, features, _default_config()["features"]["asset"] if columns is None else columns)
    _check_dtype(obj, features, np.dtype(np.float64))
    values = _check_finite_or_nan(obj, features)
    _check_leading_nan(obj, features, values, groups=dates)


def validate_market_states(states: pd.DataFrame) -> None:
    """Market states (§06, Amendments 1 and 2, contract 4): weekly index, columns exactly features.states, float64, unscaled.

    The columns include the indicator BEAR24, in {0, 1} and never scaled (Amendment 2 C1), and VIX, the VIX level lagged
    one session (C7); no column is a standardised `*_Z` name, which exists only inside the model pipeline. No ±inf; NaN
    only in the leading warm-up; MKT_VAR (a variance of daily SPY returns) ≥ 0. Row t is known after Friday close t.
    """
    obj = "market states"
    expected = list(_default_config()["features"]["states"])
    for required in MARKET_STATE_REQUIRED:
        if required not in expected:
            _fail(obj, f"config.yaml features.states must contain {required!r} (Amendment 2 C1, C7), got {expected}")
    scaled = [c for c in expected if c.endswith("_Z")]
    if scaled:
        _fail(obj, f"config.yaml features.states lists standardised names {scaled}: the frame holds unscaled states and "
                   "the `*_Z` columns exist only inside the model pipeline (Amendment 2 C7)")
    _require_frame(obj, states)
    validate_weekly_index(states.index)
    _check_columns(obj, states, expected)
    _check_dtype(obj, states, np.dtype(np.float64))
    values = _check_finite_or_nan(obj, states)
    _check_leading_nan(obj, states, values)
    bear = values[:, expected.index("BEAR24")]
    bad = ~np.isnan(bear) & (bear != 0.0) & (bear != 1.0)
    if bad.any():
        _fail(obj, f"BEAR24 must be 0.0 or 1.0 (an unscaled indicator, Amendment 2 C1), got {float(bear[_first(bad)]):g} "
                   f"in {_row_label(states.index, _first(bad))}")
    if "MKT_VAR" in states.columns:
        variance = values[:, list(states.columns).index("MKT_VAR")]
        bad = ~np.isnan(variance) & (variance < 0)
        if bad.any():
            _fail(obj, f"MKT_VAR must be >= 0, got {float(variance[_first(bad)]):.17g} in {_row_label(states.index, _first(bad))}")


def validate_labels(labels: pd.DataFrame) -> None:
    """Training labels (§05, contract 6): index (date_close, ticker) with 9 sectors per week, columns exactly [y, label_end].

    y: float64 relative forward return R_fwd − mean over the 9 sectors, no NaN or ±inf, Σ_i y = 0 within 1e-12 per week.
    label_end: tz-naive datetime64, no NaT, the session date of O(t+2), identical within a week and > date_close.
    """
    obj = "labels"
    _require_frame(obj, labels)
    dates = _check_feature_index(obj, labels.index)
    _check_columns(obj, labels, LABEL_COLUMNS)
    if labels["y"].dtype != np.float64:
        _fail(obj, f"column 'y' must have dtype float64, got {labels['y'].dtype}")
    _check_finite_or_nan(obj, labels[["y"]], allow_nan=False)
    label_end = _check_dates(f"{obj} column 'label_end'", labels["label_end"])
    frame = pd.DataFrame({"y": labels["y"].to_numpy(dtype=np.float64), "label_end": label_end}, index=pd.DatetimeIndex(dates))
    grouped = frame.groupby(level=0, sort=False)
    sums = grouped["y"].sum()
    off = np.abs(sums.to_numpy()) > TOLERANCE
    if off.any():
        _fail(obj, f"y must sum to 0 within {TOLERANCE} per week: date_close {_day(sums.index[_first(off)])} sums to "
                   f"{sums.iloc[_first(off)]:.3e}")
    varying = (grouped["label_end"].nunique() != 1).to_numpy()
    if varying.any():
        _fail(obj, f"label_end must be identical for the sectors of a week: date_close {_day(sums.index[_first(varying)])}")
    early = label_end <= dates
    if early.any():
        _fail(obj, f"label_end {_day(label_end[_first(early)])} must be after date_close {_day(dates[_first(early)])}")


def validate_scores(scores: pd.DataFrame) -> None:
    """Model scores (§07, §09, contract 8): weekly index, columns exactly the sectors, float64, no ±inf.

    Higher is more attractive; NaN marks a missing score (sizing keeps the previous signals, §09 step 5). Row t is known
    after Friday close t.
    """
    obj = "scores"
    _require_frame(obj, scores)
    validate_weekly_index(scores.index)
    _check_columns(obj, scores, universe().sectors)
    _check_dtype(obj, scores, np.dtype(np.float64))
    _check_finite_or_nan(obj, scores)


def validate_signals(signals: pd.DataFrame, top_k: int | None = None, bottom_k: int | None = None) -> None:
    """Discrete signals (§09, contract 9): weekly index, columns exactly TRADED, dtype int8, values in {−1, 0, 1}.

    Every row has exactly top_k (signal.top_k = 2) values of +1 and bottom_k (signal.bottom_k = 2) values of −1 among
    the sectors; IVV is in {−1, 0, 1}. Signals of week t are known after Friday close t and executed at O(t+1).
    """
    obj = "signals"
    signal = _default_config()["signal"]
    top_k = signal["top_k"] if top_k is None else top_k
    bottom_k = signal["bottom_k"] if bottom_k is None else bottom_k
    _require_frame(obj, signals)
    validate_weekly_index(signals.index)
    u = universe()
    _check_columns(obj, signals, u.traded)
    _check_dtype(obj, signals, np.dtype(np.int8))
    values = signals.to_numpy(dtype=np.int64, copy=True)
    bad = ~np.isin(values, [-1, 0, 1])
    if bad.any():
        row, column = _first_cell(bad)
        _fail(obj, f"value {values[row, column]} in {_row_label(signals.index, row)}, column {signals.columns[column]!r} "
                   "is not in {-1, 0, 1}")
    sectors = values[:, : len(u.sectors)]
    for sign, expected, word in ((1, top_k, "+1"), (-1, bottom_k, "-1")):
        counts = (sectors == sign).sum(axis=1)
        wrong = counts != expected
        if wrong.any():
            row = _first(wrong)
            _fail(obj, f"{_row_label(signals.index, row)} has {counts[row]} sector signals of {word}, expected {expected}")


def validate_betas(betas: pd.DataFrame) -> None:
    """Sizing betas (§06, §09, contract 10): weekly index, columns exactly TRADED, float64, raw BETA52 against SPY.

    Known after Friday close t; no ±inf; NaN only in the leading warm-up of each column.
    """
    obj = "betas"
    _require_frame(obj, betas)
    validate_weekly_index(betas.index)
    _check_columns(obj, betas, universe().traded)
    _check_dtype(obj, betas, np.dtype(np.float64))
    values = _check_finite_or_nan(obj, betas)
    _check_leading_nan(obj, betas, values)


def core_weight_for(k: int | None = None, cfg: dict | None = None) -> float:
    """Core weight per selected name (§09; Amendment 2 C4): core gross per side / k, i.e. 0.5 / k.

    The side gross is signal.core_weight × signal.top_k (0.25 × 2 = 0.5), so k = 2 (or None) gives the pre-registered 0.25
    and the sensitivity runs k = 1 and k = 3 give 0.5 and 1/6: the core stays dollar-neutral with gross 1 before hedge scaling.
    """
    signal = _cfg(cfg)["signal"]
    if k is None:
        return float(signal["core_weight"])
    if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 1:
        raise ContractError(f"core_weight_for: k must be a positive int, got {k!r}")
    return float(signal["core_weight"]) * signal["top_k"] / int(k)


def validate_weights(weights: pd.DataFrame, signals: pd.DataFrame | None = None, *, core_weight: float | None = None,
                     cap: float | None = None, k: int | None = None, dead_band: float | None = None) -> None:
    """Target weights (§09, Amendment 2 C2 and C4, contract 11): weekly index, columns exactly TRADED, float64, no NaN or ±inf.

    On every row with positions (tolerance 1e-12): Σ|w| = 1; the sector legs are dollar-neutral (Σ_sectors w = 0) and
    every non-zero sector weight has size core_weight · (1 − |w_IVV|); |w_IVV| ≤ cap / (1 + cap); and w_IVV is either 0
    or at least dead_band (2% of capital, C2). An all-zero row is flat. With `signals` (same index and columns),
    sign(w) = signal element-wise. core_weight defaults to core_weight_for(k) (0.25 for the pre-registered k = 2, 0.5 / k
    in the sensitivity runs, C4); cap and dead_band default to signal.hedge_cap and signal.hedge_deadband. Weights of
    week t are held from O(t+1) to O(t+2).
    """
    obj = "weights"
    signal = _default_config()["signal"]
    core_weight = core_weight_for(k) if core_weight is None else core_weight
    cap = signal["hedge_cap"] if cap is None else cap
    dead_band = signal["hedge_deadband"] if dead_band is None else dead_band
    _require_frame(obj, weights)
    validate_weekly_index(weights.index)
    u = universe()
    _check_columns(obj, weights, u.traded)
    _check_dtype(obj, weights, np.dtype(np.float64))
    values = _check_finite_or_nan(obj, weights, allow_nan=False)
    gross = np.abs(values).sum(axis=1)
    flat = gross <= TOLERANCE
    off = ~flat & (np.abs(gross - 1.0) > TOLERANCE)
    if off.any():
        row = _first(off)
        _fail(obj, f"{_row_label(weights.index, row)}: sum of |w| is {float(gross[row]):.17g}, must be 1 within {TOLERANCE} (or 0 when flat)")
    n_sectors = len(u.sectors)
    sector, hedge = values[:, :n_sectors], values[:, n_sectors]
    net = sector.sum(axis=1)
    unbalanced = ~flat & (np.abs(net) > TOLERANCE)
    if unbalanced.any():
        row = _first(unbalanced)
        _fail(obj, f"{_row_label(weights.index, row)}: sector weights sum to {float(net[row]):.3e}, must be 0 (dollar-neutral core)")
    leg = core_weight * (1 - np.abs(hedge))
    size = np.abs(sector)
    unequal = ~flat[:, None] & (size > TOLERANCE) & (np.abs(size - leg[:, None]) > TOLERANCE)
    if unequal.any():
        row, column = _first_cell(unequal)
        _fail(obj, f"{_row_label(weights.index, row)}, column {weights.columns[column]!r}: |w| = {float(size[row, column]):.17g}, "
                   f"must be core_weight * (1 - |w_IVV|) = {float(leg[row]):.17g}")
    too_big = np.abs(hedge) > cap / (1 + cap) + TOLERANCE
    if too_big.any():
        row = _first(too_big)
        _fail(obj, f"{_row_label(weights.index, row)}: |w_{u.hedge}| = {float(abs(hedge[row])):.17g} exceeds cap / (1 + cap) = {cap / (1 + cap):.17g}")
    in_band = (np.abs(hedge) > TOLERANCE) & (np.abs(hedge) < dead_band - TOLERANCE)
    if in_band.any():
        row = _first(in_band)
        _fail(obj, f"{_row_label(weights.index, row)}: |w_{u.hedge}| = {float(abs(hedge[row])):.17g} is inside the dead-band: "
                   f"below {dead_band} of capital the hedge must be 0 (§09 step 4, Amendment 2 C2)")
    if signals is None:
        return
    _require_frame("signals", signals)
    _check_same_index("signals", signals.index, weights.index, "weights")
    _check_columns("signals", signals, u.traded)
    signs = np.where(np.abs(values) > TOLERANCE, np.sign(values), 0.0)
    expected = signals.to_numpy(dtype=np.float64, copy=True)
    mismatch = signs != expected
    if mismatch.any():
        row, column = _first_cell(mismatch)
        _fail(obj, f"{_row_label(weights.index, row)}, column {weights.columns[column]!r}: sign of w is "
                   f"{int(signs[row, column])}, signal is {expected[row, column]:g}")


def _check_period_values(obj: str, period: pd.Series) -> np.ndarray:
    """period dtype object or string, values "IS"/"OOS" or missing; returns a boolean mask of missing values."""
    if not (period.dtype == object or is_string_dtype(period.dtype)):
        _fail(obj, f"must have an object or string dtype, got {period.dtype}")
    missing = np.asarray(period.isna())
    values = period.to_numpy(dtype=object)
    bad = ~missing & ~np.isin(values, np.asarray(PERIODS, dtype=object))
    if bad.any():
        _fail(obj, f"value {values[_first(bad)]!r} in {_row_label(period.index, _first(bad))} is not 'IS' or 'OOS'")
    return missing


def validate_forward_returns(fwd: pd.DataFrame, realised_on: pd.Series, period: pd.Series,
                             is_end: pd.Timestamp | None = None) -> None:
    """Forward returns, realisation dates and periods (§05, §10, contract 7), all on the same weekly index.

    fwd: columns exactly TRADABLES, float64, R_fwd[t] = O(t+2)/O(t+1) − 1 (simple, > −1), no ±inf, last two rows NaN.
    realised_on: Series named `realised_on`, datetime64, = date_open of row t+2, NaT on the last two rows.
    period: Series named `period`, "IS" if realised_on ≤ is_end (default split.in_sample_end) else "OOS", missing
    where realised_on is NaT.
    """
    is_end = pd.Timestamp(_default_config()["split"]["in_sample_end"] if is_end is None else is_end)
    _require_frame("fwd", fwd)
    validate_weekly_index(fwd.index)
    _check_columns("fwd", fwd, universe().tradables)
    _check_dtype("fwd", fwd, np.dtype(np.float64))
    values = _check_finite_or_nan("fwd", fwd)
    below = ~np.isnan(values) & (values <= -1.0)
    if below.any():
        row, column = _first_cell(below)
        _fail("fwd", f"return {float(values[row, column]):.17g} in {_row_label(fwd.index, row)}, column {fwd.columns[column]!r} must be > -1")
    tail = values[-2:]
    if (~np.isnan(tail)).any():
        row, column = _first_cell(~np.isnan(tail))
        row += len(values) - len(tail)
        _fail("fwd", f"the last two rows must be NaN (no O(t+2) yet): {_row_label(fwd.index, row)}, column {fwd.columns[column]!r}")

    _require_series("realised_on", realised_on, "realised_on")
    _check_same_index("realised_on", realised_on.index, fwd.index, "fwd")
    realised = _check_dates("realised_on", realised_on, allow_nat=True)
    opens = np.asarray(pd.DatetimeIndex(fwd.index.get_level_values("date_open")).as_unit("ns").values)
    expected = np.full(len(opens), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    expected[:-2] = opens[2:]
    wrong = ~((realised == expected) | (np.isnat(realised) & np.isnat(expected)))
    if wrong.any():
        row = _first(wrong)
        want = "NaT (last two rows)" if np.isnat(expected[row]) else f"{_day(expected[row])} (date_open of row t+2)"
        _fail("realised_on", f"{_row_label(fwd.index, row)} has {_day(realised[row])}, expected {want}")

    _require_series("period", period, "period")
    _check_same_index("period", period.index, fwd.index, "fwd")
    missing = _check_period_values("period", period)
    nat = np.isnat(realised)
    expected_period = np.where(realised <= is_end.to_datetime64(), "IS", "OOS").astype(object)
    values_period = period.to_numpy(dtype=object)
    wrong = (missing != nat) | (~nat & ~missing & (values_period != expected_period))
    if wrong.any():
        row = _first(wrong)
        want = "missing (realised_on is NaT)" if nat[row] else repr(expected_period[row])
        _fail("period", f"{_row_label(fwd.index, row)} has {values_period[row]!r}, expected {want} "
                        f"(IS iff realised_on <= {_day(is_end)})")


def validate_backtest_result(result: BacktestResult, cost_bps: float | None = None, borrow_annual: float | None = None,
                             *, k: int | None = None) -> None:
    """Backtest output (§09, contract 12). Tolerance 1e-12.

    weights pass validate_weights (with k for the sensitivity runs, Amendment 2 C4); every Series is named after its field and shares the weights' index; numeric fields
    are float64 and finite; period is "IS"/"OOS" with no missing value and never "IS" after "OOS"; turnover, costs and
    borrow ≥ 0; turnover of the first week = Σ|w| (entered from cash); net = gross − costs − borrow;
    net_exposure = Σ_i w; w_IVV = hedge / (1 + |hedge|). With cost_bps (basis points per dollar traded) the check
    costs = cost_bps/10 000 · turnover is added; with borrow_annual (decimal per year) borrow = borrow_annual · 7/365 ·
    Σ_{w<0}|w|.
    """
    obj = "backtest result"
    if not isinstance(result, BacktestResult):
        _fail(obj, f"must be a BacktestResult, got {type(result).__name__}")
    validate_weights(result.weights, k=k)
    index = result.weights.index
    numeric = {}
    for field in fields(BacktestResult):
        if field.name == "weights":
            continue
        series = getattr(result, field.name)
        _require_series(f"{obj} field {field.name!r}", series, field.name)
        _check_same_index(f"{obj} field {field.name!r}", series.index, index, "weights")
        if field.name == "period":
            continue
        if series.dtype != np.float64:
            _fail(obj, f"field {field.name!r} must have dtype float64, got {series.dtype}")
        values = series.to_numpy(dtype=np.float64, copy=True)
        bad = ~np.isfinite(values)
        if bad.any():
            _fail(obj, f"field {field.name!r} has a non-finite value in {_row_label(index, _first(bad))}")
        numeric[field.name] = values

    missing = _check_period_values(f"{obj} field 'period'", result.period)
    if missing.any():
        _fail(obj, f"field 'period' is missing in {_row_label(index, _first(missing))}")
    is_oos = result.period.to_numpy(dtype=object) == "OOS"
    back_to_is = ~is_oos & np.r_[False, np.maximum.accumulate(is_oos)[:-1]]
    if back_to_is.any():
        _fail(obj, f"field 'period' returns to 'IS' after 'OOS' in {_row_label(index, _first(back_to_is))}")

    def check(rule: str, residual: np.ndarray) -> None:
        bad = np.abs(residual) > TOLERANCE
        if bad.any():
            row = _first(bad)
            _fail(obj, f"{rule} fails in {_row_label(index, row)} by {residual[row]:.3e}")

    for name in ("turnover", "costs", "borrow"):
        negative = numeric[name] < 0
        if negative.any():
            _fail(obj, f"field {name!r} must be >= 0, got {float(numeric[name][_first(negative)]):.17g} in "
                       f"{_row_label(index, _first(negative))}")
    weights = _values(result.weights)
    if len(weights):
        check("turnover of the first week = sum of |w| (entered from cash)",
              numeric["turnover"][:1] - np.abs(weights[:1]).sum(axis=1))
    check("net = gross - costs - borrow", numeric["net"] - (numeric["gross"] - numeric["costs"] - numeric["borrow"]))
    check("net_exposure = sum of w", numeric["net_exposure"] - weights.sum(axis=1))
    hedge = numeric["hedge"]
    hedge_column = list(result.weights.columns).index(universe().hedge)
    check("w_IVV = hedge / (1 + |hedge|)", weights[:, hedge_column] - hedge / (1 + np.abs(hedge)))
    if cost_bps is not None:
        check(f"costs = {cost_bps} bps * turnover", numeric["costs"] - cost_bps / 10_000 * numeric["turnover"])
    if borrow_annual is not None:
        short = np.where(weights < 0, -weights, 0.0).sum(axis=1)
        check(f"borrow = {borrow_annual} * 7/365 * short gross", numeric["borrow"] - borrow_annual * 7 / 365 * short)


def validate_folds(folds: Sequence[WalkForwardFold], embargo_weeks: int | None = None,
                   label_end: pd.Series | None = None) -> None:
    """Walk-forward folds (§07, §10, contract 13), in chronological order.

    Each record: int test_year and refit (1 … 4, the calendar quarter of test_start); tz-naive midnight Timestamps;
    train_start, train_end, test_start, test_end are Fridays with train_start ≤ train_end < test_start ≤ test_end;
    test_start and test_end in test_year; purge_end = test_start − 7 days × embargo_weeks (default split.embargo_weeks).
    Purging (§05): the label of the last training week ends no later than purge_end. Its label_end is at least
    train_end + 10 days (the Monday of week t+2), so train_end + 10 days ≤ purge_end is always required; with
    `label_end` (per-week label_end on the weekly index) the exact label_end of the train_end week is checked.
    Across records: one training start (expanding window), train_end non-decreasing, (test_year, refit) unique, and the
    next test_start is the week after test_end (7 days, no gap or overlap).
    """
    obj = "folds"
    embargo_weeks = _default_config()["split"]["embargo_weeks"] if embargo_weeks is None else embargo_weeks
    folds = list(folds)
    if not folds:
        _fail(obj, "must contain at least one WalkForwardFold")
    date_fields = ["train_start", "train_end", "purge_end", "test_start", "test_end"]
    for i, fold in enumerate(folds):
        where = f"record {i}"
        if not isinstance(fold, WalkForwardFold):
            _fail(obj, f"{where} must be a WalkForwardFold, got {type(fold).__name__}")
        where = f"record {i} ({fold.test_year} Q{fold.refit})"
        for name in ("test_year", "refit"):
            value = getattr(fold, name)
            if not isinstance(value, (int, np.integer)) or isinstance(value, bool):
                _fail(obj, f"{where}: {name} must be an int, got {type(value).__name__}")
        if not 1 <= fold.refit <= 4:
            _fail(obj, f"{where}: refit must be a quarter in 1..4, got {fold.refit}")
        for name in date_fields:
            value = getattr(fold, name)
            if not isinstance(value, pd.Timestamp) or pd.isna(value):
                _fail(obj, f"{where}: {name} must be a pandas Timestamp, got {value!r}")
            if value.tz is not None:
                _fail(obj, f"{where}: {name} must be tz-naive, got {value}")
            if value != value.normalize():
                _fail(obj, f"{where}: {name} {value} is not at midnight")
            if name != "purge_end" and value.day_of_week != 4:
                _fail(obj, f"{where}: {name} {_day(value)} is not a Friday (a date_close)")
        if not fold.train_start <= fold.train_end < fold.test_start <= fold.test_end:
            _fail(obj, f"{where}: must satisfy train_start <= train_end < test_start <= test_end, got "
                       f"{_day(fold.train_start)}, {_day(fold.train_end)}, {_day(fold.test_start)}, {_day(fold.test_end)}")
        if fold.purge_end != fold.test_start - pd.Timedelta(days=7 * embargo_weeks):
            _fail(obj, f"{where}: purge_end {_day(fold.purge_end)} must be test_start - {7 * embargo_weeks} days "
                       f"= {_day(fold.test_start - pd.Timedelta(days=7 * embargo_weeks))}")
        earliest_label_end = fold.train_end + pd.Timedelta(days=LABEL_END_MIN_DAYS)
        if earliest_label_end > fold.purge_end:
            _fail(obj, f"{where}: the label of train_end {_day(fold.train_end)} ends on {_day(earliest_label_end)} or later, "
                       f"after purge_end {_day(fold.purge_end)} (purge and embargo, §05)")
        if label_end is not None:
            ends = label_end[pd.DatetimeIndex(label_end.index.get_level_values("date_close")) == fold.train_end]
            if len(ends) != 1:
                _fail(obj, f"{where}: label_end has {len(ends)} rows for train_end {_day(fold.train_end)}, expected 1")
            if pd.isna(ends.iloc[0]) or ends.iloc[0] > fold.purge_end:
                _fail(obj, f"{where}: label_end {_day(ends.iloc[0])} of train_end {_day(fold.train_end)} is after "
                           f"purge_end {_day(fold.purge_end)} (purge and embargo, §05)")
        if fold.test_start.year != fold.test_year or fold.test_end.year != fold.test_year:
            _fail(obj, f"{where}: test_start and test_end must lie in test_year {fold.test_year}")
        if fold.test_start.quarter != fold.refit:
            _fail(obj, f"{where}: refit {fold.refit} must be the calendar quarter of test_start {_day(fold.test_start)}")
    keys = [(fold.test_year, fold.refit) for fold in folds]
    if len(set(keys)) != len(keys):
        _fail(obj, f"duplicate (test_year, refit) {next(k for k in keys if keys.count(k) > 1)}")
    for i, (previous, fold) in enumerate(itertools.pairwise(folds), start=1):
        where = f"record {i} ({fold.test_year} Q{fold.refit})"
        if fold.train_start != folds[0].train_start:
            _fail(obj, f"{where}: train_start {_day(fold.train_start)} differs from the first record's "
                       f"{_day(folds[0].train_start)} (expanding window)")
        if fold.train_end < previous.train_end:
            _fail(obj, f"{where}: train_end {_day(fold.train_end)} is before the previous record's {_day(previous.train_end)}")
        if fold.test_start != previous.test_end + pd.Timedelta(days=7):
            _fail(obj, f"{where}: test_start {_day(fold.test_start)} must be the week after the previous test_end "
                       f"{_day(previous.test_end)} (chronological, no gap or overlap)")
