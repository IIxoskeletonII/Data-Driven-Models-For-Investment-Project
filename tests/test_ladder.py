"""The model ladder of src/models.py: RidgeModel, LightGBMModel, ENS, the Amendment 5 C1 helpers and walkforward_rung
(§07, §09; Amendment 5 C1; S31-2 to S31-6, S31-10).

Small estimator checks use hand-built arrays (closed-form ridge, planted tree structure). The walk-forward checks use the
shared synthetic market (sessions 2011-01-03 to 2020-12-31) truncated at the In-Sample end, with a copy of config.yaml
whose warm-up ends in 2012, whose test years are 2015-2019 and whose inner validation window is 52 weeks; only the first
few refits are run to keep the runtime modest. No data file is read.
"""

import copy
import dataclasses

import numpy as np
import pandas as pd
import pytest

from src import backtest, contracts, data, features, metrics, models, sizing
from src import labels as labels_mod
from src.config import load_config

CFG = load_config()
SECTORS = list(contracts.universe(CFG).sectors)
ASSET = list(CFG["features"]["asset"])
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
DAY = pd.Timedelta(days=1)
ContractError = contracts.ContractError
INNER_WEEKS = 52
SELECTION_BASE = ["test_year", "refit", "test_start", "train_start", "train_end", "purge_end", "inner_train_end",
                  "inner_purge_end", "inner_val_start", "inner_val_end", "inner_val_weeks"]
GRID_KEY = {"M1": "alpha", "M2": "alpha", "M3": "max_depth", "M0_star": "lookback_weeks"}


def ladder_cfg() -> dict:
    """config.yaml with a split that fits the synthetic market and a 52-week inner validation window."""
    cfg = copy.deepcopy(CFG)
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2014]
    cfg["split"]["test_years"] = [2015, 2019]
    cfg["tuning"]["inner_validation_weeks"] = INNER_WEEKS
    return cfg


LCFG = ladder_cfg()


def weekly(fridays) -> pd.MultiIndex:
    fridays = pd.DatetimeIndex(fridays)
    return pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])


def grid(rung: str) -> list:
    return list(LCFG["models"][rung][GRID_KEY[rung]])


# ---------------------------------------------------------------- shared synthetic ladder data

_LADDER: dict = {}
_RUNS: dict = {}


def build_ladder(market) -> dict:
    """Features, states, labels, betas, forward returns and momentum variants from the synthetic market up to the IS end."""
    keep = market.daily_close.index <= IS_END
    daily_close, daily_open = market.daily_close.loc[keep], market.daily_open.loc[keep]
    sessions = pd.DatetimeIndex(daily_close.index)
    vix = market.vix[market.vix.index <= IS_END]
    fred = market.fred[market.fred.index <= IS_END]
    weekly_open, _ = data.weekly_panel(daily_open, daily_close)
    fwd, realised_on, period = backtest.forward_returns(weekly_open, IS_END)
    labs = labels_mod.make_labels(fwd, sessions)
    states = features.market_states(daily_close, vix, fred, LCFG)
    ladder_data = models.LadderData(
        features=features.asset_features(daily_close, LCFG), states=states, labels=labs,
        betas=features.sizing_betas(daily_close, LCFG), fwd=fwd, realised_on=realised_on, period=period,
        momentum=features.momentum_variants(daily_close, cfg=LCFG))
    weeks = fwd.index
    label_end = labels_mod.label_end_by_week(labs, weeks)
    folds = labels_mod.walk_forward_folds(weeks, label_end, LCFG)
    return {"data": ladder_data, "weeks": weeks, "label_end": label_end, "folds": folds, "sessions": sessions}


@pytest.fixture
def ladder(synthetic_market) -> dict:
    """One synthetic ladder data set shared by the tests of this module (read-only)."""
    if not _LADDER:
        _LADDER.update(build_ladder(synthetic_market))
    return _LADDER


def run_rung(ladder: dict, rung: str, n_folds: int, value=None, members=None):
    """walkforward_rung on the first n_folds refits, cached by its arguments (inputs are never modified)."""
    key = (rung, n_folds, value, None if members is None else tuple(members))
    if key not in _RUNS:
        _RUNS[key] = models.walkforward_rung(rung, ladder["data"], ladder["folds"][:n_folds], LCFG, value=value,
                                             members=members)
    return _RUNS[key]


def closes_of(index: pd.MultiIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def fold_weeks(weeks: pd.MultiIndex, fold) -> pd.MultiIndex:
    closes = closes_of(weeks)
    return weeks[(closes >= fold.test_start) & (closes <= fold.test_end)]


def expected_test_weeks(weeks: pd.MultiIndex, folds) -> pd.MultiIndex:
    closes = closes_of(weeks)
    mask = np.zeros(len(weeks), dtype=bool)
    for fold in folds:
        mask |= np.asarray((closes >= fold.test_start) & (closes <= fold.test_end))
    return weeks[mask]


def fold_rows(scores: pd.DataFrame, fold) -> pd.DataFrame:
    closes = closes_of(scores.index)
    return scores[(closes >= fold.test_start) & (closes <= fold.test_end)]


def matching_grid_value(rung: str, chosen):
    return next(v for v in grid(rung) if v == chosen)


# ---------------------------------------------------------------- RidgeModel


def panel_index(n_weeks: int) -> pd.MultiIndex:
    fridays = pd.date_range("2010-01-08", periods=n_weeks, freq="7D")
    return pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])


def ridge_data(seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    index = panel_index(8)
    rng = np.random.default_rng(seed)
    x = pd.DataFrame(rng.normal(size=(len(index), 4)) + [0.5, -1.0, 2.0, 0.0], index=index, columns=list("abcd"))
    y = pd.Series(x.to_numpy() @ [0.3, -0.2, 0.1, 0.05] + 0.7 + rng.normal(0, 0.5, len(index)), index=index, name="y")
    return x, y


def closed_form_ridge(x: np.ndarray, y: np.ndarray, alpha: float, x_new: np.ndarray) -> np.ndarray:
    """Ridge with an unpenalised intercept: centre X and y, solve (XcᵀXc + αI)β = Xcᵀyc."""
    x_mean, y_mean = x.mean(axis=0), y.mean()
    xc, yc = x - x_mean, y - y_mean
    beta = np.linalg.solve(xc.T @ xc + alpha * np.eye(x.shape[1]), xc.T @ yc)
    return x_new @ beta + (y_mean - x_mean @ beta)


@pytest.mark.parametrize("alpha", [0.1, 1, 10])
def test_ridge_matches_the_closed_form_with_intercept(alpha):
    """RidgeModel(α) predictions equal the closed-form ridge with an unpenalised intercept."""
    x, y = ridge_data()
    model = models.RidgeModel(alpha)
    assert model.fit(x, y) is model
    score = model.score(x)
    expected = closed_form_ridge(x.to_numpy(), y.to_numpy(), alpha, x.to_numpy())
    np.testing.assert_allclose(score.to_numpy(), expected, rtol=1e-9, atol=1e-12)


def test_ridge_score_series_format_and_protocol():
    """score is a float64 Series named 'score' on X's index; the model follows ScoreModel, default name M1."""
    x, y = ridge_data()
    model = models.RidgeModel(1.0).fit(x, y)
    x_new = x.iloc[:18] * 1.5
    score = model.score(x_new)
    assert score.name == "score"
    assert score.dtype == np.float64
    assert score.index.equals(x_new.index)
    assert model.name == "M1"
    assert models.RidgeModel(1.0, name="M2").name == "M2"
    assert isinstance(model, contracts.ScoreModel)


def test_ridge_score_gives_nan_to_rows_with_a_missing_input():
    """A row with any NaN input gets a NaN score; the other rows keep their predictions."""
    x, y = ridge_data()
    model = models.RidgeModel(1.0).fit(x, y)
    x_new = x.iloc[:9].copy()
    x_new.iloc[2, 1] = np.nan
    x_new.iloc[5, 3] = np.nan
    score = model.score(x_new)
    assert np.isnan(score.iloc[2]) and np.isnan(score.iloc[5])
    complete = [0, 1, 3, 4, 6, 7, 8]
    expected = closed_form_ridge(x.to_numpy(), y.to_numpy(), 1.0, x.iloc[:9].to_numpy())
    np.testing.assert_allclose(score.iloc[complete].to_numpy(), expected[complete], rtol=1e-9, atol=1e-12)


def test_ridge_score_does_not_change_the_model():
    """Two score calls give identical values."""
    x, y = ridge_data()
    model = models.RidgeModel(10).fit(x, y)
    first = model.score(x).to_numpy().copy()
    model.score(x * 3.0)
    np.testing.assert_array_equal(model.score(x).to_numpy(), first)


def test_ridge_fit_refuses_non_finite_or_misaligned_inputs():
    """fit raises ValueError for NaN or inf in X or y, and for X and y on different indices."""
    x, y = ridge_data()
    bad_x = x.copy()
    bad_x.iloc[3, 0] = np.nan
    inf_x = x.copy()
    inf_x.iloc[4, 2] = np.inf
    bad_y = y.copy()
    bad_y.iloc[7] = np.nan
    for args in ((bad_x, y), (inf_x, y), (x, bad_y), (x.iloc[1:], y), (x, y.iloc[::-1])):
        with pytest.raises(ValueError):
            models.RidgeModel(1.0).fit(*args)


# ---------------------------------------------------------------- LightGBMModel


def tree_data(n: int, seed: int, target: str) -> tuple[pd.DataFrame, pd.Series]:
    index = pd.MultiIndex.from_product([pd.date_range("2000-01-07", periods=n // 9 + 1, freq="7D"), SECTORS],
                                       names=["date_close", "ticker"])[:n]
    rng = np.random.default_rng(seed)
    x = pd.DataFrame(rng.normal(size=(n, 3)), index=index, columns=["x1", "x2", "x3"])
    if target == "sum":
        y = (x["x1"] > 0).astype(float) + (x["x2"] > 0).astype(float)
    else:
        y = np.sign(x["x1"]) * np.sign(x["x2"])
    return x, y.rename("y").astype(np.float64)


def test_lightgbm_attributes_and_protocol():
    """Constructor values are kept; defaults are 200 trees, learning rate 0.03, seed 42, name M3."""
    model = models.LightGBMModel(3)
    assert model.max_depth == 3
    assert model.n_estimators == 200
    assert model.learning_rate == pytest.approx(0.03)
    assert model.seed == 42
    assert model.name == "M3"
    other = models.LightGBMModel(2, n_estimators=50, learning_rate=0.1, seed=7, name="M3_d2")
    assert (other.max_depth, other.n_estimators, other.seed, other.name) == (2, 50, 7, "M3_d2")
    assert isinstance(model, contracts.ScoreModel)


def test_lightgbm_learns_a_planted_additive_structure():
    """y = 1{x1 > 0} + 1{x2 > 0}: finite scores, highly correlated with y, float64 'score' on X's index."""
    x, y = tree_data(1800, 1, "sum")
    model = models.LightGBMModel(2)
    assert model.fit(x, y) is model
    score = model.score(x)
    assert score.name == "score" and score.dtype == np.float64
    assert score.index.equals(x.index)
    assert np.isfinite(score.to_numpy()).all()
    assert np.corrcoef(score.to_numpy(), y.to_numpy())[0, 1] > 0.95


def test_lightgbm_max_depth_limits_the_trees():
    """An x1·x2 sign interaction is learnt with depth 2 but not with depth-1 stumps (out of sample)."""
    x, y = tree_data(2000, 2, "xor")
    x_new, y_new = tree_data(2000, 3, "xor")
    stumps = models.LightGBMModel(1).fit(x, y).score(x_new).to_numpy()
    depth_two = models.LightGBMModel(2).fit(x, y).score(x_new).to_numpy()
    assert abs(np.corrcoef(stumps, y_new.to_numpy())[0, 1]) < 0.2
    assert np.corrcoef(depth_two, y_new.to_numpy())[0, 1] > 0.7


def test_lightgbm_is_deterministic():
    """Two separately built models fitted on the same data give identical scores; score does not change the model."""
    x, y = tree_data(900, 4, "sum")
    y = y + np.random.default_rng(5).normal(0, 0.3, len(y))
    a = models.LightGBMModel(3).fit(x, y)
    b = models.LightGBMModel(3).fit(x, y)
    np.testing.assert_array_equal(a.score(x).to_numpy(), b.score(x).to_numpy())
    np.testing.assert_array_equal(a.score(x).to_numpy(), a.score(x).to_numpy())


def test_lightgbm_nan_row_gets_nan_score_and_fit_refuses_nan():
    """A row with a missing input gets a NaN score; fit refuses a non-finite input or label."""
    x, y = tree_data(900, 6, "sum")
    model = models.LightGBMModel(2).fit(x, y)
    x_new = x.iloc[:20].copy()
    x_new.iloc[4, 0] = np.nan
    score = model.score(x_new)
    assert np.isnan(score.iloc[4])
    assert np.isfinite(score.drop(score.index[4]).to_numpy()).all()
    bad_x = x.copy()
    bad_x.iloc[0, 1] = np.nan
    bad_y = y.copy()
    bad_y.iloc[0] = np.inf
    with pytest.raises(ValueError):
        models.LightGBMModel(2).fit(bad_x, y)
    with pytest.raises(ValueError):
        models.LightGBMModel(2).fit(x, bad_y)


# ---------------------------------------------------------------- to_weekly and ensemble_scores


def test_to_weekly_pivots_scores_onto_the_given_weeks():
    """(date_close, ticker) scores become a weeks × 9 sectors float64 frame with NaN where a score is absent."""
    fridays = pd.date_range("2015-01-09", periods=3, freq="7D")
    weeks = weekly(fridays)
    rows, values = [], []
    for w, friday in enumerate(fridays):
        if w == 1:
            continue  # the middle week has no score at all
        for i, ticker in enumerate(SECTORS):
            if w == 2 and ticker == "XLE":
                continue
            rows.append((friday, ticker))
            values.append(10.0 * w + i)
    rows.append((fridays[-1] + 7 * DAY, "XLB"))  # a week outside `weeks` is ignored
    values.append(99.0)
    scores = pd.Series(values, index=pd.MultiIndex.from_tuples(rows, names=["date_close", "ticker"]), name="score")
    out = models.to_weekly(scores, weeks, LCFG)
    contracts.validate_scores(out)
    assert out.index.equals(weeks)
    assert list(out.columns) == SECTORS
    np.testing.assert_array_equal(out.iloc[0].to_numpy(), np.arange(9, dtype=np.float64))
    assert out.iloc[1].isna().all()
    expected = 20.0 + np.arange(9, dtype=np.float64)
    expected[SECTORS.index("XLE")] = np.nan
    np.testing.assert_array_equal(out.iloc[2].to_numpy(), expected)


def score_frame(rows, fridays) -> pd.DataFrame:
    return pd.DataFrame(np.asarray(rows, dtype=np.float64), index=weekly(fridays), columns=SECTORS)


def test_ensemble_scores_hand_example():
    """Mean of per-week average ranks (1 = lowest) of two models; a week with any NaN member score is all NaN."""
    fridays = pd.date_range("2016-01-08", periods=3, freq="7D")
    a = score_frame([[1, 2, 3, 4, 5, 6, 7, 8, 9],
                     [5, 5, 5, 5, 5, 5, 5, 5, 5],
                     [1, 2, np.nan, 4, 5, 6, 7, 8, 9]], fridays)
    b = score_frame([[0.5, 0.5, 3, 3, 3, -1, 10, 7, 2],
                     [9, 8, 7, 6, 5, 4, 3, 2, 1],
                     [9, 8, 7, 6, 5, 4, 3, 2, 1]], fridays)
    out = models.ensemble_scores([a, b])
    contracts.validate_scores(out)
    assert out.index.equals(a.index) and list(out.columns) == SECTORS
    # week 1: ranks a = 1..9, ranks b = [2.5, 2.5, 6, 6, 6, 1, 9, 8, 4]
    np.testing.assert_allclose(out.iloc[0].to_numpy(), [1.75, 2.25, 4.5, 5.0, 5.5, 3.5, 8.0, 8.0, 6.5], rtol=0, atol=1e-15)
    # week 2: a all tied (rank 5 each), b ranks 9..1
    np.testing.assert_allclose(out.iloc[1].to_numpy(), [7.0, 6.5, 6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0], rtol=0, atol=1e-15)
    assert out.iloc[2].isna().all()


def test_ensemble_scores_single_member_is_its_rank():
    """One member: the ensemble score is that member's cross-sectional average rank."""
    fridays = pd.date_range("2016-01-08", periods=2, freq="7D")
    a = score_frame([[0.3, -0.1, 0.3, 2.0, 1.0, 0.0, -5.0, 0.7, 0.2], [9, 8, 7, 6, 5, 4, 3, 2, 1]], fridays)
    out = models.ensemble_scores([a])
    np.testing.assert_allclose(out.iloc[0].to_numpy(), [5.5, 2.0, 5.5, 9.0, 8.0, 3.0, 1.0, 7.0, 4.0], atol=1e-15)
    np.testing.assert_allclose(out.iloc[1].to_numpy(), np.arange(9, 0, -1, dtype=np.float64), atol=1e-15)


def test_ensemble_scores_refuses_empty_or_mismatched_inputs():
    """An empty list, different weekly indices or different columns raise ValueError."""
    fridays = pd.date_range("2016-01-08", periods=2, freq="7D")
    a = score_frame(np.arange(18).reshape(2, 9), fridays)
    shifted = score_frame(np.arange(18).reshape(2, 9), fridays + 7 * DAY)
    with pytest.raises(ValueError):
        models.ensemble_scores([])
    with pytest.raises(ValueError):
        models.ensemble_scores([a, shifted])
    with pytest.raises(ValueError):
        models.ensemble_scores([a, a.drop(columns="XLY")])


# ---------------------------------------------------------------- choose_grid_value


def test_choose_grid_value_ties_go_to_the_tie_order():
    """{0.1: 0.5, 1: 0.7, 10: 0.7} with tie order [10, 1, 0.1] chooses 10."""
    assert models.choose_grid_value({0.1: 0.5, 1: 0.7, 10: 0.7}, [10, 1, 0.1]) == 10


def test_choose_grid_value_tolerance_is_1e_12():
    """Sharpes within 1e-12 are ties: {2: 0.3, 3: 0.3 + 1e-13} chooses 2; a gap of 1e-9 chooses 3."""
    assert models.choose_grid_value({2: 0.3, 3: 0.3 + 1e-13}, [2, 3]) == 2
    assert models.choose_grid_value({2: 0.3, 3: 0.3 + 1e-9}, [2, 3]) == 3


def test_choose_grid_value_highest_wins_and_nan_never_wins():
    """The highest Sharpe wins; NaN is never chosen while a number exists."""
    assert models.choose_grid_value({13: np.nan, 26: 0.1, 52: 0.2}, [26, 13, 52]) == 52
    assert models.choose_grid_value({13: 0.4, 26: np.nan, 52: -0.2}, [26, 13, 52]) == 13
    assert models.choose_grid_value({0.1: -0.3, 1: -0.1, 10: -0.2}, [10, 1, 0.1]) == 1


def test_choose_grid_value_all_nan_takes_the_first_of_the_tie_order():
    """All Sharpes NaN: the first value of the tie order."""
    assert models.choose_grid_value({13: np.nan, 26: np.nan, 52: np.nan}, [26, 13, 52]) == 26


def test_choose_grid_value_refuses_mismatched_keys():
    """Keys and tie order must be the same set of values."""
    with pytest.raises(ValueError):
        models.choose_grid_value({2: 0.1, 3: 0.2}, [2, 3, 4])
    with pytest.raises(ValueError):
        models.choose_grid_value({2: 0.1, 3: 0.2, 4: 0.0}, [2, 3])


# ---------------------------------------------------------------- config, tuning_spec, LadderData


def test_config_holds_the_tuning_and_inference_sections():
    """config.yaml: tuning.inner_validation_weeks 104, the tie orders of S31-3, inference.pbo_blocks 16, confidence 0.95."""
    assert CFG["tuning"]["inner_validation_weeks"] == 104
    assert CFG["tuning"]["tie_order"] == {"M1": [10, 1, 0.1], "M2": [10, 1, 0.1], "M3": [2, 3], "M0_star": [26, 13, 52]}
    assert CFG["inference"] == {"pbo_blocks": 16, "confidence": 0.95}


def test_tuning_spec_is_built_from_the_config():
    """tuning_spec(cfg) holds the C1 rule, the tuning section, baseline costs, zero-cost Sharpe, signal and P."""
    assert models.tuning_spec(CFG) == {
        "rule": "Amendment 5 C1", "tuning": CFG["tuning"], "cost_bps": CFG["costs"]["bps_baseline"],
        "borrow_annual": CFG["costs"]["borrow_baseline"], "sharpe": "zero_cost", "signal": CFG["signal"],
        "periods_per_year": CFG["metrics"]["periods_per_year"]}
    assert models.tuning_spec(LCFG)["tuning"]["inner_validation_weeks"] == INNER_WEEKS


def test_ladder_data_is_frozen_with_optional_fields():
    """LadderData needs features, states and labels; the other fields default to None; it is frozen."""
    frame = pd.DataFrame()
    bundle = models.LadderData(features=frame, states=frame, labels=frame)
    for name in ("betas", "fwd", "realised_on", "period", "momentum"):
        assert getattr(bundle, name) is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        bundle.fwd = frame


# ---------------------------------------------------------------- inner_fold and inner_sharpe


def test_inner_fold_splits_the_training_window(ladder):
    """Validation = the last 52 labelled training weeks ending at train_end; inner training purged with a 1-week embargo."""
    weeks, label_end = ladder["weeks"], ladder["label_end"]
    closes = closes_of(weeks)
    ends = pd.DatetimeIndex(label_end.to_numpy())
    for fold in ladder["folds"][:5]:
        inner = models.inner_fold(fold, label_end, INNER_WEEKS, 1)
        assert isinstance(inner, contracts.WalkForwardFold)
        training = np.asarray((closes >= fold.train_start) & (closes <= fold.train_end) & ~ends.isna()
                              & (ends <= fold.purge_end))
        train_closes = closes[training]
        assert inner.test_start == train_closes[-INNER_WEEKS]
        assert inner.test_end == fold.train_end
        assert len(train_closes[train_closes >= inner.test_start]) == INNER_WEEKS
        assert inner.purge_end == inner.test_start - 7 * DAY
        assert inner.train_start == fold.train_start
        assert (inner.test_year, inner.refit) == (fold.test_year, fold.refit)
        inner_training = training & np.asarray(closes <= inner.train_end)
        assert inner_training.any()
        assert (ends[inner_training] <= inner.purge_end).all()
        eligible = training & np.asarray(ends <= inner.purge_end)
        assert inner.train_end == closes[eligible].max()
        assert inner.train_end + 10 * DAY <= inner.purge_end


def test_inner_fold_refuses_a_window_without_room_for_validation(ladder):
    """Not more training weeks than inner_weeks raises ValueError."""
    weeks, label_end = ladder["weeks"], ladder["label_end"]
    fold = ladder["folds"][0]
    closes = closes_of(weeks)
    ends = pd.DatetimeIndex(label_end.to_numpy())
    n_train = int(np.sum((closes >= fold.train_start) & (closes <= fold.train_end) & ~ends.isna() & (ends <= fold.purge_end)))
    with pytest.raises(ValueError):
        models.inner_fold(fold, label_end, n_train, 1)
    with pytest.raises(ValueError):
        models.inner_fold(fold, label_end, n_train + 10, 1)


def test_inner_sharpe_is_the_zero_cost_sharpe_of_the_sized_book(synthetic_market):
    """inner_sharpe = annualised return / volatility of backtest.run(size_book(scores, betas)) at baseline costs."""
    market = synthetic_market
    weekly_close = market.weekly_close[SECTORS]
    scores = (-(weekly_close / weekly_close.shift(26) - 1.0)).astype(np.float64)
    closes = closes_of(scores.index)
    scores = scores[(closes >= pd.Timestamp("2013-01-01")) & (closes <= pd.Timestamp("2015-12-31"))]
    betas = features.sizing_betas(market.daily_close, CFG)
    fwd, _, period = backtest.forward_returns(market.weekly_open, market.is_end)
    book = sizing.size_book(scores, betas, CFG)
    result = backtest.run(book, fwd, period, CFG["costs"]["bps_baseline"], CFG["costs"]["borrow_baseline"])
    expected = metrics.annualized_return(result.net) / metrics.annualized_volatility(result.net)
    assert models.inner_sharpe(scores, betas, fwd, period, CFG) == pytest.approx(expected, rel=1e-12, abs=1e-15)


# ---------------------------------------------------------------- walkforward_rung: fixed runs


def manual_fixed(ladder: dict, rung: str, value, n_folds: int) -> pd.DataFrame:
    """Fixed-value walk-forward by hand: purged training rows, in-fold design, fit, score the test weeks."""
    d = ladder["data"]
    label_closes = closes_of(d.labels.index)
    feature_closes = closes_of(d.features.index)
    frames = []
    for fold in ladder["folds"][:n_folds]:
        train = d.labels.index[(label_closes >= fold.train_start) & (label_closes <= fold.train_end)]
        labels_mod.assert_purged(d.labels.loc[train, "label_end"], fold)
        x_train, params = models.fit_transform_train(d.features.loc[train], d.states, interactions=rung != "M1", cfg=LCFG)
        if rung == "M3":
            m3 = LCFG["models"]["M3"]
            model = models.LightGBMModel(value, n_estimators=m3["n_estimators"], learning_rate=m3["learning_rate"],
                                         seed=LCFG["seed"])
        else:
            model = models.RidgeModel(value)
        model.fit(x_train, d.labels.loc[train, "y"])
        test = d.features.index[(feature_closes >= fold.test_start) & (feature_closes <= fold.test_end)]
        x_test = models.transform_test(d.features.loc[test], d.states, params)
        frames.append(models.to_weekly(model.score(x_test), fold_weeks(ladder["weeks"], fold), LCFG))
    return pd.concat(frames)


@pytest.mark.parametrize(("rung", "value", "n_folds"), [("M1", 1, 4), ("M2", 10, 2), ("M3", 2, 2)])
def test_fixed_run_equals_a_manual_walk_forward(ladder, rung, value, n_folds):
    """A fixed-value run equals fit_transform_train + model.fit + transform_test + score, fold by fold."""
    scores, selection = run_rung(ladder, rung, n_folds, value=value)
    expected = manual_fixed(ladder, rung, value, n_folds)
    assert selection is None
    assert scores.index.equals(expected.index)
    assert list(scores.columns) == SECTORS
    np.testing.assert_allclose(scores.to_numpy(), expected.to_numpy(), rtol=1e-9, atol=1e-12)


def test_fixed_m0_runs_score_the_named_feature(ladder):
    """M0 with value MOM26_1 scores the asset feature; with MOM13_1 the momentum variant."""
    d = ladder["data"]
    weeks = expected_test_weeks(ladder["weeks"], ladder["folds"][:2])
    scores, selection = run_rung(ladder, "M0", 2, value="MOM26_1")
    assert selection is None
    expected = models.to_weekly(d.features["MOM26_1"], weeks, LCFG)
    np.testing.assert_allclose(scores.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-15)
    short, _ = run_rung(ladder, "M0", 2, value="MOM13_1")
    expected_short = models.to_weekly(d.momentum["MOM13_1"], weeks, LCFG)
    assert short.index.equals(weeks)
    np.testing.assert_allclose(short.to_numpy(), expected_short.to_numpy(), rtol=0, atol=1e-15)


# ---------------------------------------------------------------- walkforward_rung: Amendment 5 C1 runs


def test_c1_run_output_contract_and_selection_table(ladder):
    """M1 with C1: scores pass validate_scores on the test weeks; one selection row per refit with the agreed columns."""
    folds = ladder["folds"][:4]
    scores, selection = run_rung(ladder, "M1", 4)
    contracts.validate_scores(scores)
    assert scores.index.equals(expected_test_weeks(ladder["weeks"], folds))
    values = grid("M1")
    assert list(selection.columns) == SELECTION_BASE + [f"sharpe_{format(v, 'g')}" for v in values] + ["chosen"]
    assert ["sharpe_0.1", "sharpe_1", "sharpe_10"] == [f"sharpe_{format(v, 'g')}" for v in values]
    assert len(selection) == len(folds)
    tie_order = LCFG["tuning"]["tie_order"]["M1"]
    for k, fold in enumerate(folds):
        row = selection.iloc[k]
        inner = models.inner_fold(fold, ladder["label_end"], INNER_WEEKS, LCFG["split"]["embargo_weeks"])
        assert (int(row["test_year"]), int(row["refit"])) == (fold.test_year, fold.refit)
        for column, expected in (("test_start", fold.test_start), ("train_start", fold.train_start),
                                 ("train_end", fold.train_end), ("purge_end", fold.purge_end),
                                 ("inner_train_end", inner.train_end), ("inner_purge_end", inner.purge_end),
                                 ("inner_val_start", inner.test_start), ("inner_val_end", inner.test_end)):
            assert pd.Timestamp(row[column]) == expected, (k, column)
        assert int(row["inner_val_weeks"]) == INNER_WEEKS
        sharpes = {v: float(row[f"sharpe_{format(v, 'g')}"]) for v in values}
        assert row["chosen"] == models.choose_grid_value(sharpes, tie_order)


@pytest.mark.parametrize(("rung", "n_folds"), [("M1", 4), ("M2", 2), ("M3", 2)])
def test_c1_scores_equal_the_fixed_run_at_the_chosen_value(ladder, rung, n_folds):
    """At every refit the C1 run's test scores equal the fixed run's scores at the chosen value."""
    scores, selection = run_rung(ladder, rung, n_folds)
    for k, fold in enumerate(ladder["folds"][:n_folds]):
        value = matching_grid_value(rung, selection.iloc[k]["chosen"])
        fixed, _ = run_rung(ladder, rung, n_folds, value=value)
        np.testing.assert_allclose(fold_rows(scores, fold).to_numpy(), fold_rows(fixed, fold).to_numpy(), rtol=1e-12,
                                   atol=1e-12)


def test_m0_star_inner_sharpes_and_scores_by_hand(ladder):
    """M0*: each inner Sharpe equals inner_sharpe of MOM{L}_1 on the validation weeks; scores are MOM{chosen}_1."""
    d = ladder["data"]
    folds = ladder["folds"][:3]
    scores, selection = run_rung(ladder, "M0_star", 3)
    contracts.validate_scores(scores)
    assert scores.index.equals(expected_test_weeks(ladder["weeks"], folds))
    values = grid("M0_star")
    assert list(selection.columns) == SELECTION_BASE + [f"sharpe_{v}" for v in values] + ["chosen"]
    closes = closes_of(ladder["weeks"])
    for k, fold in enumerate(folds):
        inner = models.inner_fold(fold, ladder["label_end"], INNER_WEEKS, LCFG["split"]["embargo_weeks"])
        validation = ladder["weeks"][(closes >= inner.test_start) & (closes <= inner.test_end)]
        sharpes = {}
        for lookback in values:
            val_scores = models.to_weekly(d.momentum[f"MOM{lookback}_1"], validation, LCFG)
            sharpes[lookback] = models.inner_sharpe(val_scores, d.betas, d.fwd, d.period, LCFG)
            assert float(selection.iloc[k][f"sharpe_{lookback}"]) == pytest.approx(sharpes[lookback], rel=1e-12, abs=1e-15)
        chosen = models.choose_grid_value(sharpes, LCFG["tuning"]["tie_order"]["M0_star"])
        assert selection.iloc[k]["chosen"] == chosen
        expected = models.to_weekly(d.momentum[f"MOM{int(chosen)}_1"], fold_weeks(ladder["weeks"], fold), LCFG)
        np.testing.assert_allclose(fold_rows(scores, fold).to_numpy(), expected.to_numpy(), rtol=0, atol=1e-15)


def test_ens_is_the_rank_average_of_the_c1_members(ladder):
    """ENS (default members M1, M2, M3, each with C1) equals ensemble_scores of the members; no selection table."""
    scores, selection = run_rung(ladder, "ENS", 2)
    assert selection is None
    contracts.validate_scores(scores)
    members = [run_rung(ladder, rung, 2)[0] for rung in ("M1", "M2", "M3")]
    expected = models.ensemble_scores(members)
    assert scores.index.equals(expected_test_weeks(ladder["weeks"], ladder["folds"][:2]))
    np.testing.assert_allclose(scores.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12)
    pair, _ = run_rung(ladder, "ENS", 2, members=["M1", "M2"])
    np.testing.assert_allclose(pair.to_numpy(), models.ensemble_scores(members[:2]).to_numpy(), rtol=0, atol=1e-12)


def test_c1_run_is_deterministic(ladder):
    """Two M3 C1 runs on the same inputs give identical scores and selection tables."""
    folds = ladder["folds"][:2]
    first = models.walkforward_rung("M3", ladder["data"], folds, LCFG)
    second = models.walkforward_rung("M3", ladder["data"], folds, LCFG)
    pd.testing.assert_frame_equal(first[0], second[0], check_exact=True)
    pd.testing.assert_frame_equal(first[1], second[1], check_exact=True)


# ---------------------------------------------------------------- walkforward_rung: leakage


def corrupted(ladder: dict, cutoff: pd.Timestamp, seed: int = 99) -> models.LadderData:
    """Forward returns realised after `cutoff` replaced with noise, and the labels rebuilt from them."""
    d = ladder["data"]
    fwd = d.fwd.copy()
    late = np.asarray(d.realised_on > cutoff)
    fwd.loc[late] = np.random.default_rng(seed).normal(0.0, 0.05, (int(late.sum()), fwd.shape[1]))
    return dataclasses.replace(d, fwd=fwd, labels=labels_mod.make_labels(fwd, ladder["sessions"]))


@pytest.mark.parametrize("rung", ["M1", "M2", "M3", "M0_star"])
def test_c1_choice_and_scores_ignore_returns_realised_after_the_cutoff(ladder, rung):
    """Noise in every return and label realised after refit k's purge_end leaves refits 0..k unchanged."""
    folds = ladder["folds"][:3]
    k = 1
    base_scores, base_selection = run_rung(ladder, rung, 3)
    noisy_data = corrupted(ladder, folds[k].purge_end)
    assert not noisy_data.fwd.equals(ladder["data"].fwd)
    noisy_scores, noisy_selection = models.walkforward_rung(rung, noisy_data, folds, LCFG)
    pd.testing.assert_frame_equal(base_selection.iloc[: k + 1], noisy_selection.iloc[: k + 1], check_exact=True)
    upto = closes_of(base_scores.index) <= folds[k].test_end
    pd.testing.assert_frame_equal(base_scores[upto], noisy_scores[closes_of(noisy_scores.index) <= folds[k].test_end],
                                  check_exact=True)
    if rung in ("M1", "M2", "M3"):  # the corruption is visible to later refits, so the check has power
        later = fold_rows(base_scores, folds[k + 1]).to_numpy()
        assert not np.allclose(later, fold_rows(noisy_scores, folds[k + 1]).to_numpy())


@pytest.mark.parametrize(("rung", "value"), [("M1", 1), ("M1", None), ("M2", None), ("M3", 2)])
def test_a_training_label_ending_after_purge_end_raises(ladder, rung, value):
    """A training week whose label_end is moved after purge_end makes walkforward_rung raise ContractError."""
    d = ladder["data"]
    fold = ladder["folds"][0]
    label_closes = closes_of(d.labels.index)
    training = np.unique(label_closes[(label_closes >= fold.train_start) & (label_closes <= fold.train_end)])
    target = pd.Timestamp(training[20])
    bad = d.labels.copy()
    bad.loc[np.asarray(label_closes == target), "label_end"] = fold.purge_end + DAY
    with pytest.raises(ContractError):
        models.walkforward_rung(rung, dataclasses.replace(d, labels=bad), ladder["folds"][:1], LCFG, value=value)


@pytest.mark.parametrize("rung", ["M1", "M2", "M3"])
def test_c1_inner_sharpes_ignore_the_labels_of_the_inner_validation_weeks(ladder, rung):
    """The inner fits train only on the inner training window: noise in the labels y of the inner validation weeks leaves
    every inner Sharpe of that refit unchanged (the inner backtest reads forward returns, never labels), while the outer
    fit, which trains on those weeks, changes the test scores.
    """
    d = ladder["data"]
    fold = ladder["folds"][0]
    split = models.inner_fold(fold, ladder["label_end"], INNER_WEEKS, LCFG["split"]["embargo_weeks"])
    base_scores, base_selection = run_rung(ladder, rung, 1)
    label_closes = closes_of(d.labels.index)
    validation = np.asarray((label_closes >= split.test_start) & (label_closes <= split.test_end))
    noisy = d.labels.copy()
    noise = np.random.default_rng(5).normal(0.0, 0.05, (int(validation.sum()) // 9, 9))
    noisy.loc[validation, "y"] = (noise - noise.mean(axis=1, keepdims=True)).ravel()
    scores, selection = models.walkforward_rung(rung, dataclasses.replace(d, labels=noisy), ladder["folds"][:1], LCFG)
    sharpes = [column for column in selection.columns if column.startswith("sharpe_")]
    pd.testing.assert_frame_equal(base_selection[sharpes], selection[sharpes], check_exact=True)
    assert not np.allclose(base_scores.to_numpy(), scores.to_numpy())


@pytest.mark.parametrize("rung", ["M1", "M2", "M3"])
def test_an_inner_training_label_ending_after_the_inner_purge_raises(ladder, rung):
    """A label_end moved into (inner purge_end, outer purge_end] trips only the inner purge check (ContractError)."""
    d = ladder["data"]
    fold = ladder["folds"][0]
    split = models.inner_fold(fold, ladder["label_end"], INNER_WEEKS, LCFG["split"]["embargo_weeks"])
    label_closes = closes_of(d.labels.index)
    target = pd.Timestamp(np.unique(label_closes[label_closes <= split.train_end])[-5])
    moved = split.purge_end + DAY
    assert moved <= fold.purge_end  # still allowed by the outer fit
    bad = d.labels.copy()
    bad.loc[np.asarray(label_closes == target), "label_end"] = moved
    with pytest.raises(ContractError, match="purge_end"):
        models.walkforward_rung(rung, dataclasses.replace(d, labels=bad), ladder["folds"][:1], LCFG)

