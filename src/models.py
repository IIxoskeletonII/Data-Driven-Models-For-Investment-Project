"""The AI ladder of protocol section 07: M0 rank rule, ridge (M1, M2), LightGBM (M3), ENS and the M0* fallback.

Phase 2.2 (Eliya): M0 and the in-fold scaling pipeline (decisions S22-6, S22-11; Amendment 2 C1, C7; Amendment 4 C1).
Phase 3.1 (Eliya): ridge (M1, M2), LightGBM (M3), ENS, M0* and the choice within the fixed grids of Amendment 5 C1
(decisions S31-2 to S31-6), with the walk-forward loop the vault runs. Phase 3.3 (Eliya): agent feature columns and
their in-fold state products in the design (Amendment 7 C2, S33-4). Session 4.1 (Eliya): the round-2 rungs M6, M7
and M8 of Amendment 9 C1 and their Out-of-Sample hook, added after the round-1 code, which is unchanged (decisions S41-1
to S41-6). Interfaces: docs/interfaces.md, contracts 5, 8, 13, 14 and 15.
"""

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from lightgbm import LGBMRanker, LGBMRegressor
from sklearn.linear_model import Ridge

from src.backtest import run as run_backtest
from src.config import load_config
from src.contracts import ContractError, WalkForwardFold, interaction_columns, universe, validate_labels, validate_scores
from src.labels import assert_purged, label_end_by_week
from src.metrics import annualized_return, annualized_volatility, ratio
from src.sizing import size_book

INDICATOR_STATE = "BEAR24"  # Amendment 2 C1: used as 0/1 everywhere, never winsorised or standardised
VIX_STATE, VIX_SCALED = "VIX", "VIX_Z"  # Amendment 2 C7: VIX_Z is the in-fold standardisation of VIX
INTERACTION_SEPARATOR = "_x_"  # src.contracts.interaction_name joins the terms with it
SCALING_KEYS = ("lower", "upper", "mean", "std")


def _cfg(cfg: dict | None) -> dict:
    return load_config() if cfg is None else cfg


WALKFORWARD_SECTIONS = ("seed", "data", "split", "execution", "features", "models")  # 06 check_used (S23-5, S23-6)


def walkforward_settings(cfg: dict) -> dict:
    """The config sections that determine the walk-forward scores: saved as outputs/walkforward/<rung>/used.yaml by
    05_train_walkforward.py, compared by 06_backtest.py with check_used, and part of every trial's spec_hash (S23-5,
    S23-6). Exactly {seed, data, split, execution, features, models}, each the whole section.
    """
    return {key: cfg[key] for key in WALKFORWARD_SECTIONS}


def _winsor_quantiles(cfg: dict) -> tuple[float, float]:
    """The winsorising quantiles features.winsor_quantiles of config.yaml (Amendment 4 C1, S22-11)."""
    try:
        lower, upper = cfg["features"]["winsor_quantiles"]
    except KeyError:
        raise KeyError("config.yaml lacks features.winsor_quantiles (Amendment 4 C1: [0.01, 0.99]); the in-fold "
                       "winsorising of the market states cannot run without it") from None
    lower, upper = float(lower), float(upper)
    if not 0.0 <= lower < upper <= 1.0:
        raise ValueError(f"features.winsor_quantiles must satisfy 0 <= lower < upper <= 1, got [{lower}, {upper}]")
    return lower, upper


def _continuous_states(cfg: dict) -> list[str]:
    """The continuous market states of features.states (all but BEAR24, Amendment 2 C1), in config order."""
    return [state for state in cfg["features"]["states"] if state != INDICATOR_STATE]


def _scaled_name(state: str) -> str:
    """Name of a state after in-fold scaling: VIX becomes VIX_Z (C7); the others keep their names."""
    return VIX_SCALED if state == VIX_STATE else state


def fit_state_scaling(states: pd.DataFrame, cfg: dict | None = None) -> dict:
    """In-fold winsorising and standardisation parameters of the continuous market states (§06, S22-6, Amendment 4 C1).

    states: unscaled weekly market states (contract 4) of the TRAINING weeks only, one row per week, known after Friday
    close t. For each of MKT_VAR, VIX, TERM, CREDIT: lower/upper = numpy.nanquantile at features.winsor_quantiles
    (linear interpolation), then mean and sample std (ddof=1) of the clipped values, NaN ignored. Units are those of
    the state (variance of daily returns, index points, percentage points). BEAR24 gets no parameters (C1). Returns
    {"lower": {state: float}, "upper": {...}, "mean": {...}, "std": {...}}.
    """
    cfg = _cfg(cfg)
    lower_q, upper_q = _winsor_quantiles(cfg)
    if states.index.has_duplicates:
        raise ValueError("fit_state_scaling: states must hold one row per training week (duplicate index entries)")
    params: dict = {key: {} for key in SCALING_KEYS}
    for state in _continuous_states(cfg):
        values = states[state].to_numpy(dtype=np.float64)
        if np.count_nonzero(~np.isnan(values)) < 2:
            raise ValueError(f"fit_state_scaling: {state} needs at least 2 non-missing training weeks")
        lower, upper = np.nanquantile(values, [lower_q, upper_q])
        clipped = np.clip(values, lower, upper)
        params["lower"][state], params["upper"][state] = float(lower), float(upper)
        params["mean"][state] = float(np.nanmean(clipped))
        params["std"][state] = float(np.nanstd(clipped, ddof=1))
    return params


def scale_states(states: pd.DataFrame, params: Mapping) -> pd.DataFrame:
    """Market states with the stored in-fold scaling applied (no refitting; S22-6).

    states: unscaled weekly market states (contract 4), known after Friday close t; params: from fit_state_scaling.
    Returns the same index with columns BEAR24 (raw 0/1, untouched), then each fitted state scaled as
    (clip(x, lower, upper) − mean) / std, VIX renamed VIX_Z (C7); a state with std == 0 scales to 0.0; NaN stays NaN.
    float64, unitless (training standard deviations).
    """
    scaled = {INDICATOR_STATE: states[INDICATOR_STATE].to_numpy(dtype=np.float64)}
    for state in params["mean"]:
        values = np.clip(states[state].to_numpy(dtype=np.float64), params["lower"][state], params["upper"][state])
        std = params["std"][state]
        if std == 0:
            scaled[_scaled_name(state)] = np.where(np.isnan(values), np.nan, 0.0)
        else:
            scaled[_scaled_name(state)] = (values - params["mean"][state]) / std
    return pd.DataFrame(scaled, index=states.index, dtype=np.float64)


def _by_close(frame: pd.DataFrame) -> pd.DataFrame:
    """A weekly frame re-indexed by its date_close level alone."""
    keys = frame.index.get_level_values("date_close") if isinstance(frame.index, pd.MultiIndex) else frame.index
    return frame.set_axis(pd.DatetimeIndex(keys), axis=0)


def _row_states(features: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    """The weekly states of each feature row (matched on date_close); raises if a feature week has no state row."""
    weekly = _by_close(states)
    if weekly.index.has_duplicates:
        raise ValueError("states: duplicate date_close entries")
    dates = pd.DatetimeIndex(features.index.get_level_values("date_close"))
    absent = ~dates.isin(weekly.index)
    if absent.any():
        raise ValueError(f"states: no market-state row for the feature week {dates[absent][0].date()}")
    return weekly.reindex(dates).set_axis(features.index, axis=0)


def _design(features: pd.DataFrame, states: pd.DataFrame, params: Mapping) -> pd.DataFrame:
    """Design matrix of contract 5 from the stored parameters: asset columns, then the interaction products."""
    columns = list(params["columns"])
    assets = [column for column in columns if INTERACTION_SEPARATOR not in column]
    design = features[assets].astype(np.float64)
    if any(INTERACTION_SEPARATOR in column for column in columns):
        terms = pd.concat([design, _row_states(features, scale_states(states, params))], axis=1)
        for column in columns:
            if INTERACTION_SEPARATOR in column:
                product = np.ones(len(design))
                for term in column.split(INTERACTION_SEPARATOR):
                    product = product * terms[term].to_numpy(dtype=np.float64)
                design[column] = product
    return design[columns].astype(np.float64)


def agent_design_columns(agent_columns: Sequence[tuple[str, Sequence[str]]]) -> list[str]:
    """Design columns of agent features (Amendment 7 C2, S33-4): each column AG<k>, then, for one with states, the
    product AG<k>_x_<state>[_x_<state>] with the scaled state names (VIX as VIX_Z, BEAR24 raw)."""
    columns = [str(name) for name, _ in agent_columns]
    for name, terms in agent_columns:
        if terms:
            columns.append(INTERACTION_SEPARATOR.join([str(name)] + [_scaled_name(str(t)) for t in terms]))
    return columns


def fit_transform_train(features: pd.DataFrame, states: pd.DataFrame, interactions: bool = True,
                        cfg: dict | None = None, *,
                        agent_columns: Sequence[tuple[str, Sequence[str]]] = ()) -> tuple[pd.DataFrame, dict]:
    """Design matrix of the training rows and the fitted scaling parameters (§06, contract 5, S22-6).

    features: z-scored asset features (contract 3) of the purged training rows, index (date_close, ticker), known after
    Friday close t; states: unscaled weekly market states (contract 4) covering those weeks. The scaling of MKT_VAR,
    VIX, TERM and CREDIT is fitted on the distinct training weeks only (the date_close values of `features`). X holds
    the six asset columns (features.asset) and, with interactions=True, the five columns of
    src.contracts.interaction_columns(cfg) in that order: z-scored asset feature × raw BEAR24 × scaled MKT_VAR or VIX_Z.
    agent_columns (S33-4): (column, states) pairs of agent features held in `features`; X gains each column and, for
    one with states, its product with the in-fold scaled states (agent_design_columns), after the interactions.
    Returns (X float64 on features' index, params = fit_state_scaling output plus "interactions" (bool) and "columns"
    (list of X's columns)) for transform_test.
    """
    cfg = _cfg(cfg)
    weeks = pd.DatetimeIndex(features.index.get_level_values("date_close")).unique()
    weekly = _by_close(states)
    absent = ~weeks.isin(weekly.index)
    if absent.any():
        raise ValueError(f"states: no market-state row for the training week {weeks[absent][0].date()}")
    params = fit_state_scaling(weekly.loc[weekly.index.isin(weeks)], cfg)
    agent = agent_design_columns(agent_columns)
    plain = [column for column in agent if INTERACTION_SEPARATOR not in column]
    products = [column for column in agent if INTERACTION_SEPARATOR in column]
    columns = list(cfg["features"]["asset"]) + plain + (interaction_columns(cfg) if interactions else []) + products
    params["interactions"], params["columns"] = bool(interactions), columns
    return _design(features, states, params), params


def transform_test(features: pd.DataFrame, states: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Design matrix of test rows with the scaling fitted by fit_transform_train (no refitting on test data).

    features: z-scored asset features of the rows to score, known after Friday close t; states: unscaled weekly market
    states covering those weeks; params: from fit_transform_train. Returns X (float64) on features' index with
    params["columns"].
    """
    return _design(features, states, params)


class M0:
    """Rule momentum, the hurdle (§07): the score is the z-scored MOM26_1 feature itself; fit is a no-op."""

    def __init__(self, feature: str = "MOM26_1", name: str = "M0") -> None:
        self.feature = feature
        self.name = name

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "M0":
        """No-op fit (the rule has no parameters); returns self without changing any state."""
        return self

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index: the momentum column X[feature], known after Friday close t
        (higher = more attractive).
        """
        return pd.Series(X[self.feature].to_numpy(dtype=np.float64), index=X.index, name="score")


def _check_training(X: pd.DataFrame, y: pd.Series, name: str) -> None:
    """Raise ValueError unless X and y share their index and hold only finite values (S31-4)."""
    if not X.index.equals(y.index):
        raise ValueError(f"{name}.fit: X and y must have the same index")
    if len(X) == 0:
        raise ValueError(f"{name}.fit: no training row")
    if not np.isfinite(X.to_numpy(dtype=np.float64)).all() or not np.isfinite(y.to_numpy(dtype=np.float64)).all():
        raise ValueError(f"{name}.fit: training inputs and labels must be finite (S31-4)")


def _predict(model, X: pd.DataFrame, columns: list[str], name: str) -> pd.Series:
    """Predictions of a fitted estimator on X[columns]; a row with any missing input gets NaN (S31-4)."""
    if model is None:
        raise ValueError(f"{name}.score: the model is not fitted")
    values = X[columns].to_numpy(dtype=np.float64)
    complete = np.isfinite(values).all(axis=1)
    out = np.full(len(values), np.nan)
    if complete.any():
        out[complete] = np.asarray(model.predict(values[complete]), dtype=np.float64)
    return pd.Series(out, index=X.index, name="score", dtype=np.float64)


class RidgeModel:
    """Ridge regression ranker (§07): M1 on the six z-scored asset features, M2 with the five interactions;
    λ ∈ models.M1.alpha / models.M2.alpha. sklearn Ridge(alpha=λ) with library defaults (fit_intercept=True; S31-4).
    """

    def __init__(self, alpha: float, name: str = "M1") -> None:
        self.alpha = alpha
        self.name = name
        self._model = None
        self.columns: list[str] = []

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RidgeModel":
        """Fit on purged training rows (label_end ≤ purge_end, asserted by the caller): X the design of contract 5, y the
        relative weekly label of contract 6 (decimal return). Returns self.
        """
        _check_training(X, y, self.name)
        self.columns = list(X.columns)
        self._model = Ridge(alpha=float(self.alpha)).fit(X.to_numpy(dtype=np.float64), y.to_numpy(dtype=np.float64))
        return self

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index: the predicted relative return of the week (higher = more
        attractive), known after Friday close t; NaN for a row with a missing input. Does not change the model.
        """
        return _predict(self._model, X, self.columns, self.name)


class LightGBMModel:
    """Gradient-boosted trees on the M2 inputs (M3, §07): depth ∈ {2, 3}, 200 trees, learning rate 0.03,
    deterministic=True, num_threads=1, seed from config.seed; also force_row_wise=True and verbose=-1, library defaults
    otherwise (S31-4).
    """

    def __init__(self, max_depth: int, n_estimators: int = 200, learning_rate: float = 0.03, seed: int = 42,
                 name: str = "M3", num_threads: int = 1) -> None:
        self.max_depth = max_depth
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.seed = seed
        self.name = name
        self.num_threads = num_threads
        self._model = None
        self.columns: list[str] = []

    def params(self) -> dict:
        """Every parameter passed to lightgbm.LGBMRegressor (S31-4)."""
        return {"max_depth": int(self.max_depth), "n_estimators": int(self.n_estimators),
                "learning_rate": float(self.learning_rate), "num_threads": int(self.num_threads), "deterministic": True,
                "force_row_wise": True, "random_state": int(self.seed), "verbose": -1}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMModel":
        """Fit on purged training rows (label_end ≤ purge_end, asserted by the caller); returns self."""
        _check_training(X, y, self.name)
        self.columns = list(X.columns)
        self._model = LGBMRegressor(**self.params()).fit(X.to_numpy(dtype=np.float64), y.to_numpy(dtype=np.float64))
        return self

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index (higher = more attractive), known after Friday close t; NaN for a row
        with a missing input. Does not change the model.
        """
        return _predict(self._model, X, self.columns, self.name)


def to_weekly(scores: pd.Series, weeks: pd.MultiIndex, cfg: dict | None = None) -> pd.DataFrame:
    """Row scores on (date_close, ticker) as a weekly score frame (contract 8): index `weeks` (date_open, date_close),
    columns the 9 sectors in universe order, float64, NaN where a week or sector has no score.
    """
    cfg = _cfg(cfg)
    wide = scores.unstack("ticker").reindex(columns=list(universe(cfg).sectors))
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    wide = wide.reindex(closes).astype(np.float64)
    wide.index = pd.MultiIndex.from_arrays([closes - pd.Timedelta(days=4), closes], names=["date_open", "date_close"])
    wide.columns.name = None
    return wide


def ensemble_scores(scores: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """ENS (§07, S31-5): equal-weight average of the cross-sectional rank scores of the members (M1–M3, + M5 later).

    scores: weekly score frames (contract 8) with identical index and columns, known after Friday close t. Each week
    each member's sector scores are ranked (1 = lowest, ties get their average rank) and the ranks are averaged; a week
    where any member lacks any score is NaN for every sector (the sizing carries the previous book, Amendment 2 C3).
    Returns a weekly score frame (contract 8).
    """
    frames = list(scores)
    if not frames:
        raise ValueError("ensemble_scores: no member scores")
    index, columns = frames[0].index, list(frames[0].columns)
    for frame in frames[1:]:
        if not frame.index.equals(index) or list(frame.columns) != columns:
            raise ValueError("ensemble_scores: member score frames must share the same weekly index and columns")
    incomplete = np.zeros(len(index), dtype=bool)
    total = np.zeros((len(index), len(columns)))
    for frame in frames:
        incomplete |= frame.isna().any(axis=1).to_numpy()
        total += frame.rank(axis=1, method="average").to_numpy(dtype=np.float64)
    mean = total / len(frames)
    mean[incomplete] = np.nan
    result = pd.DataFrame(mean, index=index, columns=columns, dtype=np.float64)
    validate_scores(result)
    return result


# -- Amendment 5 C1: the choice within the fixed grids -------------------------------------------------------------------

GRID_KEYS = {"M1": "alpha", "M2": "alpha", "M3": "max_depth", "M0_star": "lookback_weeks"}  # models.<rung>.<key>
PARAM_KEYS = {"M1": "alpha", "M2": "alpha", "M3": "max_depth"}  # the spec "params" key of a fixed grid value (S31-2)
ENS_MEMBERS = ("M1", "M2", "M3")  # M5 joins in Phase 3.3 (S31-5)
RUNGS = ("M0", "M1", "M2", "M3", "M0_star", "ENS")
TIE_TOLERANCE = 1e-12  # inner Sharpes within this distance of the best are ties (S31-3)
TUNING_RULE = "Amendment 5 C1"


@dataclass(frozen=True)
class LadderData:
    """The In-Sample inputs of the ladder, as served by the vault (every row known by split.in_sample_end).

    features: asset features (contract 3); states: market states (contract 4; its weekly index is the calendar);
    labels: labels (contract 6); betas: sizing betas (contract 10); fwd, realised_on, period: forward returns of contract
    7 (rows realised by the In-Sample end); momentum: the M0* variants MOM13_1, MOM26_1, MOM52_1 (contract 3); agent_columns: (column, states) pairs of
    agent features held as extra columns of `features` (Amendment 7 C2, S33-4), empty for the human rungs.
    """

    features: pd.DataFrame
    states: pd.DataFrame
    labels: pd.DataFrame
    betas: pd.DataFrame | None = None
    fwd: pd.DataFrame | None = None
    realised_on: pd.Series | None = None
    period: pd.Series | None = None
    momentum: pd.DataFrame | None = None
    agent_columns: tuple = ()


def grid(rung: str, cfg: dict | None = None) -> list:
    """The pre-registered grid of a rung (§07): models.M1.alpha, models.M2.alpha, models.M3.max_depth,
    models.M0_star.lookback_weeks, in config order.
    """
    cfg = _cfg(cfg)
    if rung not in GRID_KEYS:
        raise ValueError(f"grid: rung {rung!r} has no grid (rungs with a grid: {sorted(GRID_KEYS)})")
    return list(cfg["models"][rung][GRID_KEYS[rung]])


def tie_order(rung: str, cfg: dict | None = None) -> list:
    """tuning.tie_order of a rung (S31-3): its grid values, the simpler value first; ValueError unless it is a
    permutation of the grid.
    """
    cfg = _cfg(cfg)
    try:
        order = list(cfg["tuning"]["tie_order"][rung])
    except KeyError:
        raise KeyError(f"config.yaml lacks tuning.tie_order.{rung} (Amendment 5 C1, S31-3)") from None
    values = grid(rung, cfg)
    if len(order) != len(values) or set(order) != set(values) or len(set(order)) != len(order):
        raise ValueError(f"tuning.tie_order.{rung} {order} must list each grid value {values} exactly once")
    return order


def inner_validation_weeks(cfg: dict | None = None) -> int:
    """tuning.inner_validation_weeks (104, Amendment 5 C1)."""
    cfg = _cfg(cfg)
    try:
        weeks = int(cfg["tuning"]["inner_validation_weeks"])
    except KeyError:
        raise KeyError("config.yaml lacks tuning.inner_validation_weeks (Amendment 5 C1: 104)") from None
    if weeks < 2:
        raise ValueError(f"tuning.inner_validation_weeks must be at least 2, got {weeks}")
    return weeks


def tuning_spec(cfg: dict | None = None) -> dict:
    """The "tuning" entry of the spec of a tuned run (S31-2): every setting that drives the Amendment 5 C1 choice beyond
    walkforward_settings(cfg), so that it is part of the trial's spec_hash.
    """
    cfg = _cfg(cfg)
    return {"rule": TUNING_RULE, "tuning": cfg["tuning"], "cost_bps": cfg["costs"]["bps_baseline"],
            "borrow_annual": cfg["costs"]["borrow_baseline"], "sharpe": "zero_cost", "signal": cfg["signal"],
            "periods_per_year": cfg["metrics"]["periods_per_year"]}


def inner_fold(fold: WalkForwardFold, label_end: pd.Series, inner_weeks: int, embargo_weeks: int) -> WalkForwardFold:
    """The inner split of a refit record (Amendment 5 C1, S31-3).

    fold: an outer refit (contract 13); label_end: per-week label_end on the weekly index (label_end_by_week). The
    training weeks are those with date_close in [fold.train_start, fold.train_end] and label_end ≤ fold.purge_end; the
    last `inner_weeks` of them are the validation weeks (test_start … test_end = fold.train_end); the inner training
    weeks are the training weeks with label_end ≤ purge_end = test_start − 7 × embargo_weeks days. Returns a
    WalkForwardFold with fold's test_year and refit (messages only; not for validate_folds). ValueError if there are not
    more training weeks than inner_weeks or no inner training week.
    """
    if isinstance(label_end.index, pd.MultiIndex):
        closes = pd.DatetimeIndex(label_end.index.get_level_values("date_close"))
    else:
        closes = pd.DatetimeIndex(label_end.index)
    ends = pd.to_datetime(label_end).to_numpy(dtype="datetime64[ns]")
    known = ~np.isnat(ends)
    training = np.asarray((closes >= fold.train_start) & (closes <= fold.train_end)) & known
    training &= ends <= fold.purge_end.to_datetime64()
    weeks = closes[training].sort_values()
    if len(weeks) <= inner_weeks:
        raise ValueError(f"inner_fold: refit {fold.test_year} Q{fold.refit} has {len(weeks)} training weeks, not more "
                         f"than the {inner_weeks} inner validation weeks")
    start = pd.Timestamp(weeks[-inner_weeks])
    purge_end = start - pd.Timedelta(days=7 * int(embargo_weeks))
    inner = training & (ends <= purge_end.to_datetime64())
    if not inner.any():
        raise ValueError(f"inner_fold: refit {fold.test_year} Q{fold.refit} has no inner training week")
    train_end = pd.Timestamp(closes[inner].max())
    if train_end + pd.Timedelta(days=10) > purge_end:
        raise ContractError(f"inner_fold: inner training ends {train_end.date()}, too close to purge_end {purge_end.date()}")
    return WalkForwardFold(test_year=fold.test_year, refit=fold.refit, train_start=fold.train_start, train_end=train_end,
                           purge_end=purge_end, test_start=start, test_end=pd.Timestamp(weeks[-1]))


def choose_grid_value(sharpes: Mapping, tie_order: Sequence):
    """The grid value with the highest inner Sharpe (Amendment 5 C1, S31-3): values within 1e-12 of the best are ties
    and go to the earliest in tie_order (the simpler value); a NaN Sharpe never wins unless all are NaN, when
    tie_order[0] is returned. ValueError unless sharpes' keys and tie_order are the same set.
    """
    order = list(tie_order)
    if set(sharpes) != set(order) or len(set(order)) != len(order) or len(sharpes) != len(order):
        raise ValueError(f"choose_grid_value: values {sorted(sharpes)} differ from the tie order {order}")
    valid = {value: float(sharpe) for value, sharpe in sharpes.items() if not np.isnan(sharpe)}
    if not valid:
        return order[0]
    best = max(valid.values())
    for value in order:
        if value in valid and valid[value] >= best - TIE_TOLERANCE:
            return value
    raise AssertionError("unreachable")  # the best value is in the tie order


def inner_sharpe(scores: pd.DataFrame, betas: pd.DataFrame, fwd: pd.DataFrame, period: pd.Series,
                 cfg: dict | None = None) -> float:
    """Net Sharpe of the hedged book of week-t scores (Amendment 5 C1): §09 sizing (src.sizing.size_book), the engine
    (src.backtest.run) at costs.bps_baseline and costs.borrow_baseline, entered from cash in the first week, zero-cost
    convention annualised return / annualised volatility (src.metrics). Mattia's functions, imported unchanged.
    """
    cfg = _cfg(cfg)
    weeks = scores.index
    sizing = size_book(scores, betas.loc[betas.index.isin(weeks)], cfg)
    result = run_backtest(sizing, fwd.loc[fwd.index.isin(weeks)], period.loc[period.index.isin(weeks)],
                          cfg["costs"]["bps_baseline"], cfg["costs"]["borrow_baseline"])
    return ratio(annualized_return(result.net), annualized_volatility(result.net))


def _closes_of(frame: pd.DataFrame | pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


def _weeks_between(weeks: pd.MultiIndex, start: pd.Timestamp, end: pd.Timestamp) -> pd.MultiIndex:
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    return weeks[np.asarray((closes >= start) & (closes <= end))]


def _momentum_column(data: LadderData, feature: str) -> pd.DataFrame:
    """The single momentum column of M0 or M0* (contract 5): a feature column or a MOM{L}_1 variant."""
    if feature in data.features.columns:
        return data.features[[feature]]
    if data.momentum is not None and feature in data.momentum.columns:
        return data.momentum[[feature]]
    raise ValueError(f"unknown momentum column {feature!r}")


def _fit_score(rung: str, value, data: LadderData, fold: WalkForwardFold, cfg: dict) -> pd.Series:
    """Fit `rung` at grid value `value` on the purged training rows of `fold` and score its test weeks.

    Training rows: date_close in [train_start, train_end] with a label; assert_purged against fold.purge_end before the
    fit. The market-state scaling (M2, M3) is fitted on the training weeks only (S22-6). Returns row scores on
    (date_close, ticker) for the weeks test_start … test_end.
    """
    labels = data.labels
    if rung in ("M0", "M0_star"):
        if data.agent_columns:
            raise ValueError(f"{rung} takes no agent features (Amendment 7, S33-4)")
        source = _momentum_column(data, value if rung == "M0" else f"MOM{int(value)}_1")
    else:
        agent_names = [str(name) for name, _ in data.agent_columns]
        source = data.features[list(cfg["features"]["asset"]) + agent_names]
    dates = _closes_of(source)
    train_index = source.index[np.asarray((dates >= fold.train_start) & (dates <= fold.train_end))]
    train_index = train_index[train_index.isin(labels.index)]
    assert_purged(labels.loc[train_index, "label_end"], fold)
    test_index = source.index[np.asarray((dates >= fold.test_start) & (dates <= fold.test_end))]
    y = labels.loc[train_index, "y"].astype(np.float64)
    if rung in ("M0", "M0_star"):
        model = M0(feature=source.columns[0], name=rung)
        return model.fit(source.loc[train_index], y).score(source.loc[test_index])
    X_train, params = fit_transform_train(data.features.loc[train_index], data.states, rung != "M1", cfg,
                                          agent_columns=data.agent_columns)
    X_test = transform_test(data.features.loc[test_index], data.states, params)
    if rung == "M3":
        m3 = cfg["models"]["M3"]
        model = LightGBMModel(int(value), n_estimators=int(m3["n_estimators"]), learning_rate=float(m3["learning_rate"]),
                              seed=int(cfg["seed"]), name="M3", num_threads=int(m3["num_threads"]))
    else:
        model = RidgeModel(float(value), name=rung)
    return model.fit(X_train, y.loc[X_train.index]).score(X_test)


def _check_realised(data: LadderData, weeks: pd.MultiIndex, fold: WalkForwardFold) -> None:
    """Every validation week's return must be realised by the outer cutoff purge_end (S31-3)."""
    if data.realised_on is None or data.fwd is None or data.period is None or data.betas is None:
        raise ValueError("Amendment 5 C1 needs the sizing betas and the forward returns (LadderData betas, fwd, "
                         "realised_on, period)")
    realised = pd.Series(pd.to_datetime(data.realised_on).to_numpy(dtype="datetime64[ns]"), index=_closes_of(data.realised_on))
    values = realised.reindex(pd.DatetimeIndex(weeks.get_level_values("date_close"))).to_numpy(dtype="datetime64[ns]")
    if np.isnat(values).any() or (values > fold.purge_end.to_datetime64()).any():
        raise ContractError(f"inner validation of refit {fold.test_year} Q{fold.refit}: a return is not realised by "
                            f"purge_end {fold.purge_end.date()} (Amendment 5 C1 uses only data available at the refit)")


def _value_label(value) -> str:
    return format(value, "g")


def _choose(rung: str, data: LadderData, fold: WalkForwardFold, label_end: pd.Series, cfg: dict) -> tuple[object, dict]:
    """The Amendment 5 C1 choice at one refit: (chosen value, selection row)."""
    split = inner_fold(fold, label_end, inner_validation_weeks(cfg), int(cfg["split"]["embargo_weeks"]))
    validation = _weeks_between(data.states.index, split.test_start, split.test_end)
    _check_realised(data, validation, fold)
    sharpes = {}
    for value in grid(rung, cfg):
        weekly = to_weekly(_fit_score(rung, value, data, split, cfg), validation, cfg)
        sharpes[value] = inner_sharpe(weekly, data.betas, data.fwd, data.period, cfg)
    chosen = choose_grid_value(sharpes, tie_order(rung, cfg))
    row = {"test_year": fold.test_year, "refit": fold.refit, "test_start": fold.test_start, "train_start": fold.train_start,
           "train_end": fold.train_end, "purge_end": fold.purge_end, "inner_train_end": split.train_end,
           "inner_purge_end": split.purge_end, "inner_val_start": split.test_start, "inner_val_end": split.test_end,
           "inner_val_weeks": len(validation)}
    row.update({f"sharpe_{_value_label(value)}": sharpe for value, sharpe in sharpes.items()})
    row["chosen"] = chosen
    return chosen, row


def walkforward_rung(rung: str, data: LadderData, folds: Sequence[WalkForwardFold], cfg: dict | None = None, *,
                     value=None, members: Sequence[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Weekly scores of a rung over the In-Sample walk-forward refits (§07, §10, contract 13; Amendment 5).

    rung: M0, M1, M2, M3, M0_star or ENS. value: a fixed grid value (M0: the momentum column, default models.M0.feature;
    M1/M2: λ; M3: max depth); None for M1, M2, M3 and M0_star applies the Amendment 5 C1 choice at every refit (S31-3);
    ENS averages the ranks of its members (default M1, M2, M3, each with C1; S31-5). Every inner and outer fit asserts
    the purge. Returns (scores: contract 8 on the test weeks of `folds`, known after Friday close t; selection: one row
    per refit with the inner Sharpe of each grid value and the chosen value, None for fixed runs and ENS).
    """
    cfg = _cfg(cfg)
    if rung not in RUNGS:
        raise ValueError(f"walkforward_rung: unknown rung {rung!r}; known {list(RUNGS)}")
    folds = list(folds)
    weeks = data.states.index
    test_weeks = _weeks_between(weeks, folds[0].test_start, folds[-1].test_end)
    if rung == "ENS":
        if value is not None:
            raise ValueError("walkforward_rung: ENS has no grid value")
        names = list(ENS_MEMBERS if members is None else members)
        frames = [walkforward_rung(member, data, folds, cfg)[0] for member in names]
        return ensemble_scores(frames), None
    if rung == "M0" and value is None:
        value = cfg["models"]["M0"]["feature"]
    if rung == "M0_star" and value is not None:
        raise ValueError("walkforward_rung: a fixed M0* lookback L is the rung M0 with value 'MOM{L}_1' (S31-6)")
    if value is not None and rung in GRID_KEYS and value not in grid(rung, cfg):
        raise ValueError(f"walkforward_rung: {value!r} is not in the pre-registered grid {grid(rung, cfg)} of {rung}")
    label_end = label_end_by_week(data.labels, weeks)
    rows, selection = [], []
    for fold in folds:
        chosen = value
        if value is None:
            chosen, record = _choose(rung, data, fold, label_end, cfg)
            selection.append(record)
        rows.append(_fit_score(rung, chosen, data, fold, cfg))
    scores = to_weekly(pd.concat(rows), test_weeks, cfg)
    validate_scores(scores)
    return scores, (pd.DataFrame(selection) if value is None else None)


# -- Amendment 9 C1: the round-2 rungs M6, M7 and M8 (session 4.1, decisions S41-1 to S41-6) ---------------------------

ROUND2_RUNGS = ("M6", "M7", "M8")
HALF_LIFE = "half_life_weeks"
ROUND2_PARAMS = {"M6": ("alpha",), "M7": ("alpha", HALF_LIFE), "M8": ("max_depth", HALF_LIFE)}  # S41-5 spec params
ROUND2_TAG_PREFIX = {"alpha": "a", "max_depth": "d", HALF_LIFE: "h"}  # tags a0.1, a10_h4, d2_h2 (S41-4)
# The round2 keys that determine M6-M8 scores, carried in every round-2 spec (S41-5): a trial's identity is the set of
# settings that determine its scores, so round2.selection, round2.candidate_order and round2.agent_lab are left out.
ROUND2_SCORE_KEYS = ("test_weeks", "label", "smoothing", "models", "tie_order", "tie_precedence")


def _round2_section(cfg: dict) -> dict:
    try:
        return cfg["round2"]
    except KeyError:
        raise KeyError("config.yaml lacks the round2 section (Amendment 9, S40-1)") from None


def round2_spec_settings(cfg: dict | None = None) -> dict:
    """The "round2" entry of every M6-M8 spec (S41-5): the keys ROUND2_SCORE_KEYS of config.yaml's round2 section
    (test weeks, 4-week label, smoothing, models, tie order and precedence), each the whole subsection. Gate and
    agent-lab settings are not part of it, so changing them leaves every round-2 spec_hash unchanged."""
    section = _round2_section(_cfg(cfg))
    missing = [key for key in ROUND2_SCORE_KEYS if key not in section]
    if missing:
        raise KeyError(f"config.yaml round2 lacks {missing} (Amendment 9 C1, S40-1)")
    return {key: section[key] for key in ROUND2_SCORE_KEYS}


def round2_agent_base(cfg: dict | None = None) -> str:
    """The base rung of the round-2 agent lab (round2.agent_lab.base_rung, M7; Amendment 9 C2): the only round-2 rung
    whose specs and walk-forward take agent features (S43-3)."""
    return str(_round2_section(_cfg(cfg))["agent_lab"]["base_rung"])


def _check_round2_rung(rung: str) -> None:
    if rung not in ROUND2_RUNGS:
        raise ValueError(f"unknown round-2 rung {rung!r}; round-2 rungs {list(ROUND2_RUNGS)}")


def round2_grid(rung: str, cfg: dict | None = None) -> list[dict]:
    """The grid points of a round-2 rung (Amendment 9 C1, S41-4) as parameter dicts, in config order, first parameter
    outer and H inner: M6 {"alpha": λ}; M7 {"alpha": λ, "half_life_weeks": H}; M8 {"max_depth": d, "half_life_weeks": H}.
    Values keep their YAML type (0.1 float, 1 and 10 int). The half-lives of M7 and M8 must be round2.smoothing's.
    """
    cfg = _cfg(cfg)
    _check_round2_rung(rung)
    section = _round2_section(cfg)
    model = section["models"][rung]
    keys = ROUND2_PARAMS[rung]
    if HALF_LIFE in keys and list(model[HALF_LIFE]) != list(section["smoothing"][HALF_LIFE]):
        raise ValueError(f"round2.models.{rung}.{HALF_LIFE} {model[HALF_LIFE]} differs from round2.smoothing.{HALF_LIFE} "
                         f"{section['smoothing'][HALF_LIFE]}")
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*(list(model[key]) for key in keys))]


def round2_tie_order(rung: str, cfg: dict | None = None) -> list[dict]:
    """The grid points of round2_grid in the tie order of S41-4: sorted by the position of each parameter's value in
    round2.tie_order, parameters taken in round2.tie_precedence order (λ or depth first, then H). The first point of
    this list wins a tie of inner Sharpes. ValueError unless each tie order lists each grid value exactly once.
    """
    cfg = _cfg(cfg)
    points = round2_grid(rung, cfg)
    section = _round2_section(cfg)
    keys = ROUND2_PARAMS[rung]
    precedence = list(section["tie_precedence"])
    missing = [key for key in keys if key not in precedence]
    if missing:
        raise ValueError(f"round2.tie_precedence {precedence} lacks {missing}")
    orders = {}
    for key in keys:
        order = list(section["tie_order"][key])
        values = list(dict.fromkeys(point[key] for point in points))
        if len(order) != len(values) or set(order) != set(values) or len(set(order)) != len(order):
            raise ValueError(f"round2.tie_order.{key} {order} must list each grid value {values} exactly once")
        orders[key] = order
    ranked = sorted(keys, key=precedence.index)
    return sorted(points, key=lambda point: tuple(orders[key].index(point[key]) for key in ranked))


def round2_tag(rung: str, point: Mapping) -> str:
    """The tag of a grid point (S41-4): a<λ> (M6), a<λ>_h<H> (M7), d<depth>_h<H> (M8), values formatted with 'g'."""
    _check_round2_rung(rung)
    return "_".join(f"{ROUND2_TAG_PREFIX[key]}{format(point[key], 'g')}" for key in ROUND2_PARAMS[rung])


def smoothing_weights(half_life: int, lags_per_half_life: int = 3) -> np.ndarray:
    """Weights of the round-2 smoothing (Amendment 9 C1, S41-3): w_k = 2^(−k/H) for k = 0 … lags_per_half_life × H,
    normalised to sum 1 (H = 2: 7 weights; H = 4: 13 weights). w_0 applies to week t itself."""
    half_life, lags = int(half_life), int(lags_per_half_life)
    if half_life < 1 or lags < 0:
        raise ValueError(f"smoothing_weights: half-life {half_life} must be >= 1 and lags per half-life {lags} >= 0")
    k = np.arange(lags * half_life + 1, dtype=np.float64)
    weights = np.power(2.0, -k / half_life)
    return weights / weights.sum()


def smooth_weekly(raw: pd.DataFrame, weights: Sequence[float], weeks: pd.MultiIndex) -> pd.DataFrame:
    """Smoothed weekly scores (S41-3): row t of the result = Σ_k weights[k] × the row k places earlier in raw's weekly
    index (k = 0 is week t itself).

    raw: weekly score frame (contract 8) on a contiguous run of the weekly calendar, each row known after its Friday
    close; weeks: the weeks to return (rows of raw). A value is NaN when the week or any of its lags is absent from raw
    or NaN. Returns a float64 frame on `weeks` with raw's columns; row t uses only rows of raw dated on or before t.
    """
    w = np.asarray(weights, dtype=np.float64)
    values = raw.to_numpy(dtype=np.float64)
    positions = raw.index.get_indexer(weeks)
    out = np.zeros((len(weeks), values.shape[1]), dtype=np.float64)
    for k, weight in enumerate(w):
        lagged = positions - k
        valid = (positions >= 0) & (lagged >= 0)
        rows = np.full((len(weeks), values.shape[1]), np.nan)
        rows[valid] = values[lagged[valid]]
        out += weight * rows
    return pd.DataFrame(out, index=weeks, columns=raw.columns, dtype=np.float64)


def within_week_relevance(y: pd.Series) -> pd.Series:
    """LambdaRank relevance of M8 (Amendment 9 C1, S41-3): within each date_close, the rank of y, 0 for the lowest …
    n − 1 for the highest (8 with 9 sectors); exact ties give the higher relevance to the alphabetically earlier ticker
    (§09 step 2). y: finite values on (date_close, ticker). Returns an int64 Series named "relevance" on y's index.
    """
    values = y.to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("within_week_relevance: y must be finite")
    frame = pd.DataFrame({"date": np.asarray(y.index.get_level_values("date_close")),
                          "ticker": np.asarray(y.index.get_level_values("ticker"), dtype=object),
                          "y": values, "position": np.arange(len(values))})
    frame = frame.sort_values(["date", "y", "ticker"], ascending=[True, False, True], kind="mergesort")
    order = frame.groupby("date", sort=False).cumcount().to_numpy()
    size = frame.groupby("date", sort=False)["y"].transform("size").to_numpy()
    relevance = np.empty(len(values), dtype=np.int64)
    relevance[frame["position"].to_numpy()] = size - 1 - order
    return pd.Series(relevance, index=y.index, name="relevance", dtype=np.int64)


class RankerModel:
    """LightGBM LambdaRank ranker of M8 (Amendment 9 C1, S41-3) on the M2 design: one query group per week (the 9
    sectors), relevance = within_week_relevance of the 4-week label, linear label gain over the levels, every position
    evaluated; max_depth ∈ {2, 3}, 200 trees, learning rate 0.03, deterministic=True, num_threads=1, seed from
    config.seed; also force_row_wise=True and verbose=-1, library defaults otherwise.
    """

    def __init__(self, max_depth: int, n_estimators: int = 200, learning_rate: float = 0.03, seed: int = 42,
                 name: str = "M8", num_threads: int = 1, levels: int = 9) -> None:
        self.max_depth = max_depth
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.seed = seed
        self.name = name
        self.num_threads = num_threads
        self.levels = levels
        self._model = None
        self.columns: list[str] = []

    def params(self) -> dict:
        """Every parameter passed to lightgbm.LGBMRanker (S41-3)."""
        levels = int(self.levels)
        return {"objective": "lambdarank", "max_depth": int(self.max_depth), "n_estimators": int(self.n_estimators),
                "learning_rate": float(self.learning_rate), "num_threads": int(self.num_threads), "deterministic": True,
                "force_row_wise": True, "random_state": int(self.seed), "verbose": -1,
                "label_gain": [float(level) for level in range(levels)], "lambdarank_truncation_level": levels}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RankerModel":
        """Fit on purged training rows (label_end ≤ purge_end, asserted by the caller): X the M2 design on
        (date_close, ticker), y the 4-week relative label (decimal). Each week must hold exactly `levels` rows (the 9
        sectors). Returns self."""
        _check_training(X, y, self.name)
        X, y = X.sort_index(), y.sort_index()
        dates = pd.DatetimeIndex(X.index.get_level_values("date_close"))
        groups = pd.Series(np.ones(len(dates), dtype=np.int64), index=dates).groupby(level=0, sort=False).sum()
        if (groups.to_numpy() != int(self.levels)).any():
            week = groups.index[np.flatnonzero(groups.to_numpy() != int(self.levels))[0]]
            raise ValueError(f"{self.name}.fit: the training week {week.date()} has {groups[week]} rows, not one per "
                             f"sector ({self.levels})")
        self.columns = list(X.columns)
        relevance = within_week_relevance(y)
        self._model = LGBMRanker(**self.params()).fit(X.to_numpy(dtype=np.float64), relevance.to_numpy(),
                                                      group=groups.to_numpy())
        return self

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index (higher = more attractive), known after Friday close t; NaN for a row
        with a missing input. Does not change the model."""
        return _predict(self._model, X, self.columns, self.name)


def _round2_point(rung: str, value: Mapping, cfg: dict) -> dict:
    """A grid point given as a parameter dict, checked against round2_grid (same keys, values equal with the same
    type, S31-12); returns the grid's own dict."""
    if not isinstance(value, Mapping) or set(value) != set(ROUND2_PARAMS[rung]):
        raise ValueError(f"{rung}: a grid point is {{{', '.join(repr(k) for k in ROUND2_PARAMS[rung])}}}, got {value!r}")
    for point in round2_grid(rung, cfg):
        if all(not isinstance(value[key], bool) and value[key] == point[key] and type(value[key]) is type(point[key])
               for key in point):
            return dict(point)
    raise ValueError(f"{rung}: {dict(value)!r} is not, with the same types, a point of the pre-registered grid "
                     f"{round2_grid(rung, cfg)} (round2.models.{rung})")


def round2_fold(fold: WalkForwardFold, label_end_h4: pd.Series) -> WalkForwardFold:
    """The fold record of a round-2 fit (S41-2): `fold` with train_end = the last week from train_start whose 4-week
    label_end ≤ purge_end. label_end_h4: per-week 4-week label_end (label_end_by_week of the 4-week labels)."""
    closes = (pd.DatetimeIndex(label_end_h4.index.get_level_values("date_close"))
              if isinstance(label_end_h4.index, pd.MultiIndex) else pd.DatetimeIndex(label_end_h4.index))
    ends = pd.to_datetime(label_end_h4).to_numpy(dtype="datetime64[ns]")
    train = np.asarray(closes >= fold.train_start) & ~np.isnat(ends) & (ends <= fold.purge_end.to_datetime64())
    if not train.any():
        raise ValueError(f"round2_fold: refit {fold.test_year} Q{fold.refit} has no week with a 4-week label realised by "
                         f"purge_end {fold.purge_end.date()}")
    return replace(fold, train_end=pd.Timestamp(closes[train].max()))


def _round2_fit(rung: str, point: Mapping, data: LadderData, labels_h4: pd.DataFrame, fold: WalkForwardFold,
                cfg: dict) -> tuple[object, dict]:
    """Fit a round-2 model at a grid point on the purged training rows of `fold` (S41-2, S41-3): rows with date_close in
    [train_start, train_end] and a 4-week label, assert_purged on their 4-week label_end before the fit; M2 design with
    the in-fold state scaling. Agent columns of the round-2 lab's base rung (S43-3) join the source and the design as in
    round 1 (Amendment 7 C2, S33-4). Returns (fitted model, design parameters)."""
    agent_names = [str(name) for name, _ in data.agent_columns]
    source = data.features[list(cfg["features"]["asset"]) + agent_names]
    dates = _closes_of(source)
    train_index = source.index[np.asarray((dates >= fold.train_start) & (dates <= fold.train_end))]
    train_index = train_index[train_index.isin(labels_h4.index)]
    assert_purged(labels_h4.loc[train_index, "label_end"], fold)
    y = labels_h4.loc[train_index, "y"].astype(np.float64)
    X_train, params = fit_transform_train(data.features.loc[train_index], data.states, True, cfg,
                                          agent_columns=data.agent_columns)
    if rung == "M8":
        m8 = _round2_section(cfg)["models"]["M8"]
        model = RankerModel(int(point["max_depth"]), n_estimators=int(m8["n_estimators"]),
                            learning_rate=float(m8["learning_rate"]), seed=int(cfg["seed"]), name="M8",
                            num_threads=int(m8["num_threads"]), levels=int(m8["relevance_levels"]))
    else:
        model = RidgeModel(float(point["alpha"]), name=rung)
    return model.fit(X_train, y.loc[X_train.index]), params


def _round2_raw(model, params: dict, data: LadderData, weeks: pd.MultiIndex, cfg: dict) -> pd.DataFrame:
    """Unsmoothed weekly scores of a fitted round-2 model on `weeks` (rows of the weekly calendar)."""
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    rows = data.features.index[np.asarray(_closes_of(data.features).isin(closes))]
    X = transform_test(data.features.loc[rows], data.states, params)
    return to_weekly(model.score(X), weeks, cfg)


def _round2_scores(model, params: dict, data: LadderData, weeks: pd.MultiIndex, half_life, cfg: dict) -> pd.DataFrame:
    """Weekly scores of a fitted round-2 model on `weeks`: unsmoothed for M6 (half_life None), else the smoothing of
    S41-3 over the 3H weeks before each week on the weekly calendar (data.states' index)."""
    if half_life is None:
        return _round2_raw(model, params, data, weeks, cfg)
    weights = smoothing_weights(int(half_life), int(_round2_section(cfg)["smoothing"]["lags_per_half_life"]))
    calendar = data.states.index
    positions = calendar.get_indexer(weeks)
    if (positions < 0).any():
        raise ValueError("round-2 smoothing: a week to score is not on the weekly calendar")
    first = max(int(positions.min()) - (len(weights) - 1), 0)
    span = calendar[first:int(positions.max()) + 1]
    return smooth_weekly(_round2_raw(model, params, data, span, cfg), weights, weeks)


def _round2_choose(rung: str, data: LadderData, labels_h4: pd.DataFrame, fold: WalkForwardFold, label_end_h4: pd.Series,
                   cfg: dict) -> tuple[dict, dict]:
    """The Amendment 5 C1 choice at one round-2 refit (S41-2, S41-4): (chosen grid point, selection row)."""
    split = inner_fold(fold, label_end_h4, inner_validation_weeks(cfg), int(cfg["split"]["embargo_weeks"]))
    validation = _weeks_between(data.states.index, split.test_start, split.test_end)
    _check_realised(data, validation, fold)
    points = round2_grid(rung, cfg)
    fits: dict = {}
    sharpes = {}
    for point in points:
        key = point[ROUND2_PARAMS[rung][0]]  # the fit depends on λ or depth only; H changes the scoring (S41-3)
        if key not in fits:
            fits[key] = _round2_fit(rung, point, data, labels_h4, split, cfg)
        weekly = _round2_scores(*fits[key], data, validation, point.get(HALF_LIFE), cfg)
        sharpes[round2_tag(rung, point)] = inner_sharpe(weekly, data.betas, data.fwd, data.period, cfg)
    chosen_tag = choose_grid_value(sharpes, [round2_tag(rung, point) for point in round2_tie_order(rung, cfg)])
    chosen = next(point for point in points if round2_tag(rung, point) == chosen_tag)
    row = {"test_year": fold.test_year, "refit": fold.refit, "test_start": fold.test_start, "train_start": fold.train_start,
           "train_end": fold.train_end, "purge_end": fold.purge_end, "inner_train_end": split.train_end,
           "inner_purge_end": split.purge_end, "inner_val_start": split.test_start, "inner_val_end": split.test_end,
           "inner_val_weeks": len(validation)}
    row.update({f"sharpe_{tag}": sharpe for tag, sharpe in sharpes.items()})
    row["chosen"] = chosen_tag
    row.update({f"chosen_{key}": chosen[key] for key in ROUND2_PARAMS[rung]})
    return chosen, row


def walkforward_round2(rung: str, data: LadderData, labels_h4: pd.DataFrame, folds: Sequence[WalkForwardFold],
                       cfg: dict | None = None, *, value: Mapping | None = None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Weekly scores of a round-2 rung (M6, M7, M8) over walk-forward refits (Amendment 9 C1; S41-2 to S41-4, S41-6).

    data: the ladder tables (contract 3, 4, 6; betas and forward returns for tuning); labels_h4: the 4-week labels
    (contract 6 shape, S41-1); folds: refit records (round 1's In-Sample folds, or 08's Out-of-Sample folds). Each fit
    uses the rows whose 4-week label_end ≤ purge_end, asserted on every fit, inner and full. value: a fixed grid point
    (round2_grid dict; at Out-of-Sample refits the frozen point of round2_frozen_value, Amendment 6 C2); None applies
    the Amendment 5 C1 choice at every refit, refused for a fold ending after split.in_sample_end. Returns (scores:
    contract 8 on the test weeks of `folds`, known after Friday close t; selection: one row per refit, None for a
    fixed point). data.agent_columns (S43-3): allowed only for round2_agent_base(cfg) (M7, the round-2 lab's base rung);
    each agent column and its in-fold state product join the design as in round 1, and the smoothing applies to the
    scores of that design.
    """
    cfg = _cfg(cfg)
    _check_round2_rung(rung)
    if data.agent_columns and rung != round2_agent_base(cfg):
        raise ValueError(f"walkforward_round2: {rung} takes no agent features; only the round-2 lab's base rung "
                         f"{round2_agent_base(cfg)} does (Amendment 9 C2, S43-3)")
    validate_labels(labels_h4)
    folds = list(folds)
    if not folds:
        raise ValueError("walkforward_round2: no refit")
    point = None if value is None else _round2_point(rung, value, cfg)
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    if point is None and any(fold.test_end > is_end for fold in folds):
        raise ValueError(f"walkforward_round2: tuning on a fold ending after the In-Sample end {is_end.date()} is refused; "
                         "Out-of-Sample refits keep the frozen grid point (Amendment 6 C2)")
    weeks = data.states.index
    label_end_h4 = label_end_by_week(labels_h4, weeks)
    frames, selection = [], []
    for fold in folds:
        fold4 = round2_fold(fold, label_end_h4)
        chosen = point
        if point is None:
            chosen, record = _round2_choose(rung, data, labels_h4, fold4, label_end_h4, cfg)
            selection.append(record)
        model, params = _round2_fit(rung, chosen, data, labels_h4, fold4, cfg)
        fold_weeks = _weeks_between(weeks, fold.test_start, fold.test_end)
        frames.append(_round2_scores(model, params, data, fold_weeks, chosen.get(HALF_LIFE), cfg))
    test_weeks = _weeks_between(weeks, folds[0].test_start, folds[-1].test_end)
    scores = pd.concat(frames)
    if not scores.index.equals(test_weeks):
        raise ValueError("walkforward_round2: the refits' test windows do not partition the test weeks")
    scores = scores[list(universe(cfg).sectors)].astype(np.float64)
    validate_scores(scores)
    return scores, (pd.DataFrame(selection) if point is None else None)


def round2_frozen_value(rung: str, selection: pd.DataFrame, cfg: dict | None = None) -> dict:
    """The grid point chosen at the last In-Sample refit of a tuned round-2 rung (Amendment 6 C2, S41-6), from its
    selection.csv (S41-4): the last row by (test_year, refit), whose test_year must be the last of split.test_years.
    Returns the round2_grid dict with the grid's types; ValueError if the row's chosen_<parameter> values or its tag are
    not a grid point."""
    cfg = _cfg(cfg)
    _check_round2_rung(rung)
    keys = ROUND2_PARAMS[rung]
    needed = ["test_year", "refit", "chosen"] + [f"chosen_{key}" for key in keys]
    missing = [column for column in needed if column not in selection.columns]
    if missing or selection.empty:
        raise ValueError(f"round2_frozen_value: the {rung} selection table is empty or lacks {missing}")
    last = selection.sort_values(["test_year", "refit"]).iloc[-1]
    last_year = int(cfg["split"]["test_years"][1])
    if int(last["test_year"]) != last_year:
        raise ValueError(f"round2_frozen_value: the last {rung} refit is in {int(last['test_year'])}, not the last In-Sample "
                         f"test year {last_year}")
    matches = [point for point in round2_grid(rung, cfg)
               if all(float(point[key]) == float(last[f"chosen_{key}"]) for key in keys)]
    if len(matches) != 1 or round2_tag(rung, matches[0]) != str(last["chosen"]):
        raise ValueError(f"round2_frozen_value: the last {rung} refit chose {last['chosen']!r}, not a point of the grid "
                         f"{round2_grid(rung, cfg)}")
    return dict(matches[0])
