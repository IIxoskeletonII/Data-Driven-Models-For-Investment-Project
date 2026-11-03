"""The AI ladder of protocol section 07: M0 rank rule, ridge (M1, M2), LightGBM (M3), ENS and the M0* fallback.

Phase 2.2 (Eliya): M0 and the in-fold scaling pipeline (decisions S22-6, S22-11; Amendment 2 C1, C7; Amendment 4 C1).
Not implemented yet: ridge, LightGBM, ENS and M0* in Phase 3.1 (Eliya). Interfaces: docs/interfaces.md, contracts 5, 8
and 14.
"""

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from src.config import load_config
from src.contracts import interaction_columns

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
    if params["interactions"]:
        terms = pd.concat([design, _row_states(features, scale_states(states, params))], axis=1)
        for column in columns:
            if INTERACTION_SEPARATOR in column:
                product = np.ones(len(design))
                for term in column.split(INTERACTION_SEPARATOR):
                    product = product * terms[term].to_numpy(dtype=np.float64)
                design[column] = product
    return design[columns].astype(np.float64)


def fit_transform_train(features: pd.DataFrame, states: pd.DataFrame, interactions: bool = True,
                        cfg: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Design matrix of the training rows and the fitted scaling parameters (§06, contract 5, S22-6).

    features: z-scored asset features (contract 3) of the purged training rows, index (date_close, ticker), known after
    Friday close t; states: unscaled weekly market states (contract 4) covering those weeks. The scaling of MKT_VAR,
    VIX, TERM and CREDIT is fitted on the distinct training weeks only (the date_close values of `features`). X holds
    the six asset columns (features.asset) and, with interactions=True, the five columns of
    src.contracts.interaction_columns(cfg) in that order: z-scored asset feature × raw BEAR24 × scaled MKT_VAR or VIX_Z.
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
    columns = list(cfg["features"]["asset"]) + (interaction_columns(cfg) if interactions else [])
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


class RidgeModel:
    """Ridge regression ranker (M1 on the six asset features, M2 with the five interactions; §07, λ ∈ {0.1, 1, 10})."""

    def __init__(self, alpha: float, name: str = "M1") -> None:
        self.alpha = alpha
        self.name = name

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RidgeModel":
        """Fit on purged training rows (label_end ≤ purge_end); returns self."""
        raise NotImplementedError("Phase 3.1, Eliya")

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index (higher = more attractive)."""
        raise NotImplementedError("Phase 3.1, Eliya")


class LightGBMModel:
    """Gradient-boosted trees on the M2 inputs (M3, §07): depth ∈ {2, 3}, 200 trees, learning rate 0.03,
    deterministic=True, num_threads=1, seed from config.seed.
    """

    def __init__(self, max_depth: int, n_estimators: int = 200, learning_rate: float = 0.03, seed: int = 42,
                 name: str = "M3") -> None:
        self.max_depth = max_depth
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.seed = seed
        self.name = name

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMModel":
        """Fit on purged training rows (label_end ≤ purge_end); returns self."""
        raise NotImplementedError("Phase 3.1, Eliya")

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index (higher = more attractive)."""
        raise NotImplementedError("Phase 3.1, Eliya")


def ensemble_scores(scores: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """ENS (§07): equal-weight average of the cross-sectional rank scores of M1–M3 (+ M5 if it exists).

    scores: weekly score frames (contract 8) on the same weekly index. Returns a weekly score frame (contract 8).
    """
    raise NotImplementedError("Phase 3.1, Eliya")


def select_m0_star_lookback(net_returns: Mapping[int, pd.Series], cutoff: pd.Timestamp) -> int:
    """M0* fallback (§07): the lookback in models.M0_star.lookback_weeks with the highest walk-forward In-Sample net
    Sharpe, using only weekly net returns realised on or before the refit cutoff.
    """
    raise NotImplementedError("Phase 3.1, Eliya")
