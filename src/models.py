"""The AI ladder of protocol section 07: M0 rank rule, ridge (M1, M2), LightGBM (M3), ENS and the M0* fallback.

Not implemented yet: M0 and the scaling pipeline in Phase 2.2 (Eliya); ridge, LightGBM, ENS and M0* in Phase 3.1
(Eliya). Interfaces: docs/interfaces.md, contracts 5, 8 and 14.
"""

from collections.abc import Mapping, Sequence

import pandas as pd


def fit_transform_train(features: pd.DataFrame, states: pd.DataFrame, interactions: bool = True,
                        cfg: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Design matrix of the training rows and the fitted scaling parameters (§06, contract 5).

    features: z-scored asset features (contract 3); states: unscaled market states (contract 4), both known after Friday
    close t and restricted to purged training rows. Winsorising and standardising of the states are fitted on these
    rows only; with interactions=True the five pre-registered interaction columns (src.contracts.interaction_columns)
    are added after scaling. Returns (X_train indexed by (date_close, ticker), parameters for transform_test).
    """
    raise NotImplementedError("Phase 2.2, Eliya")


def transform_test(features: pd.DataFrame, states: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Design matrix of test rows with the scaling fitted by fit_transform_train (no refitting on test data)."""
    raise NotImplementedError("Phase 2.2, Eliya")


class M0:
    """Rule momentum, the hurdle (§07): the score is the z-scored MOM26_1 feature itself; fit is a no-op."""

    def __init__(self, feature: str = "MOM26_1", name: str = "M0") -> None:
        self.feature = feature
        self.name = name

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "M0":
        """No-op fit; returns self."""
        raise NotImplementedError("Phase 2.2, Eliya")

    def score(self, X: pd.DataFrame) -> pd.Series:
        """Float64 Series named `score` on X's index: the momentum column (higher = more attractive)."""
        raise NotImplementedError("Phase 2.2, Eliya")


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
