"""Round-2 rungs M6, M7 and M8 in src/models.py (Amendment 9 C1, Amendment 5 C1, Amendment 6 C2; decisions S41-2,
S41-3, S41-4 and S41-6): the smoothing, the LambdaRank relevance and estimator, the grids, tie order and tags, the
round-2 walk-forward with its 4-week purge, the frozen value and the Out-of-Sample hook.

Small checks use hand-built frames. The walk-forward checks use the shared synthetic market of contract 18 (sessions
2011-01-03 to 2020-12-31): In-Sample inputs are truncated at 2019-12-27, with a copy of config.yaml whose warm-up ends in
2012, whose test years are 2014-2019, whose inner validation window is 26 weeks and whose round2.test_weeks is the
synthetic count of test weeks. The Out-of-Sample hook is exercised only on the synthetic market, with a temporary
FROZEN.lock. No data file is read.
"""

import copy
import dataclasses
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import backtest, contracts, data, features, models
from src import labels as labels_mod
from src.config import load_config

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
SECTORS = list(contracts.universe(CFG).sectors)
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
LAST_WEEK = pd.Timestamp("2019-12-13")  # last In-Sample scored week (contract 7)
FIRST_WEEK = pd.Timestamp("2014-01-03")  # first Friday of the first synthetic test year
DAY = pd.Timedelta(days=1)
INNER_WEEKS = 26
ContractError = contracts.ContractError
SELECTION_BASE = ["test_year", "refit", "test_start", "train_start", "train_end", "purge_end", "inner_train_end",
                  "inner_purge_end", "inner_val_start", "inner_val_end", "inner_val_weeks"]
N_TEST_WEEKS = len(pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D"))


def round2_cfg() -> dict:
    """config.yaml with a split that fits the synthetic market; round2.test_weeks = the synthetic test-week count."""
    cfg = copy.deepcopy(CFG)
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2013]
    cfg["split"]["test_years"] = [2014, 2019]
    cfg["tuning"]["inner_validation_weeks"] = INNER_WEEKS
    cfg["round2"]["test_weeks"] = N_TEST_WEEKS
    return cfg


R2CFG = round2_cfg()


@pytest.fixture(scope="module")
def script03():
    spec = importlib.util.spec_from_file_location("build_features_script_round2_models", ROOT / "03_build_features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def closes_of(index: pd.MultiIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def key_of(value):
    return None if value is None else tuple(sorted(value.items()))


# ---------------------------------------------------------------- smoothing_weights


@pytest.mark.parametrize("half_life, count", [(2, 7), (4, 13)])
def test_smoothing_weights_are_normalised_powers_of_two(half_life, count):
    """S41-3: w_k = 2^(-k/H) for k = 0 ... 3H, normalised to sum 1."""
    weights = np.asarray(models.smoothing_weights(half_life, 3), dtype=np.float64)
    assert weights.shape == (count,)
    raw = 2.0 ** (-np.arange(count) / half_life)
    np.testing.assert_allclose(weights, raw / raw.sum(), rtol=1e-14, atol=0)
    assert weights.sum() == pytest.approx(1.0, abs=1e-15)


def test_smoothing_weights_halve_every_half_life():
    weights = np.asarray(models.smoothing_weights(2, 3), dtype=np.float64)
    assert np.all(np.diff(weights) < 0)
    assert weights[2] / weights[0] == pytest.approx(0.5, rel=1e-14)
    assert weights[6] / weights[0] == pytest.approx(0.125, rel=1e-14)
    four = np.asarray(models.smoothing_weights(4, 3), dtype=np.float64)
    assert four[4] / four[0] == pytest.approx(0.5, rel=1e-14)


def test_smoothing_weights_follow_lags_per_half_life_from_the_config():
    lags = int(CFG["round2"]["smoothing"]["lags_per_half_life"])
    assert lags == 3
    for half_life in CFG["round2"]["smoothing"]["half_life_weeks"]:
        assert len(models.smoothing_weights(half_life, lags)) == lags * half_life + 1


# ---------------------------------------------------------------- smooth_weekly


def weekly(fridays) -> pd.MultiIndex:
    fridays = pd.DatetimeIndex(fridays)
    return pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])


def raw_scores(n_weeks: int = 7) -> pd.DataFrame:
    """raw[t, i] = 10 (t + 1) + i on n_weeks Fridays from 2015-01-09, columns the 9 sectors."""
    index = weekly(pd.date_range("2015-01-09", periods=n_weeks, freq="7D"))
    values = 10.0 * (np.arange(n_weeks)[:, None] + 1) + np.arange(len(SECTORS))[None, :]
    return pd.DataFrame(values, index=index, columns=SECTORS)


def test_smooth_weekly_hand_example():
    """Weights (0.5, 0.3, 0.2): score[t] = 0.5 raw[t] + 0.3 raw[t-1] + 0.2 raw[t-2]; NaN where a lag is absent."""
    raw = raw_scores()
    weights = np.array([0.5, 0.3, 0.2])
    weeks = raw.index[1:]
    got = models.smooth_weekly(raw, weights, weeks)
    assert got.index.equals(weeks)
    assert list(got.columns) == SECTORS
    assert all(dtype == np.float64 for dtype in got.dtypes)
    assert got.iloc[0].isna().all()  # week 1 has no row two places earlier
    values = raw.to_numpy()
    for t in range(2, len(raw)):
        expected = 0.5 * values[t] + 0.3 * values[t - 1] + 0.2 * values[t - 2]
        np.testing.assert_allclose(got.loc[raw.index[t]].to_numpy(), expected, rtol=1e-14, atol=0)
    # by hand for XLB (column 0) at week 4: 0.5 * 50 + 0.3 * 40 + 0.2 * 30 = 43
    assert got.loc[raw.index[4], "XLB"] == pytest.approx(43.0, rel=1e-14)


def test_smooth_weekly_missing_lag_gives_nan_for_that_sector_only():
    raw = raw_scores()
    raw.iloc[3, SECTORS.index("XLE")] = np.nan
    weights = np.array([0.5, 0.3, 0.2])
    got = models.smooth_weekly(raw, weights, raw.index)
    xle = got["XLE"].to_numpy()
    assert np.isnan(xle[[0, 1, 3, 4, 5]]).all()
    assert np.isfinite(xle[[2, 6]]).all()
    others = got.drop(columns="XLE").iloc[2:]
    assert np.isfinite(others.to_numpy()).all()
    np.testing.assert_allclose(got.iloc[6]["XLE"], 0.5 * 71 + 0.3 * 61 + 0.2 * 51, rtol=1e-14)


def test_smooth_weekly_with_a_single_weight_returns_the_raw_scores():
    raw = raw_scores()
    got = models.smooth_weekly(raw, np.array([1.0]), raw.index[2:])
    np.testing.assert_allclose(got.to_numpy(), raw.iloc[2:].to_numpy(), rtol=0, atol=0)


def test_smooth_weekly_uses_the_rows_of_raws_index_not_the_requested_weeks():
    """The lag is k rows earlier in raw's weekly index, whatever subset of weeks is requested."""
    raw = raw_scores()
    weights = np.array([0.6, 0.4])
    got = models.smooth_weekly(raw, weights, raw.index[[5]])
    expected = 0.6 * raw.iloc[5].to_numpy() + 0.4 * raw.iloc[4].to_numpy()
    np.testing.assert_allclose(got.iloc[0].to_numpy(), expected, rtol=1e-14)


# ---------------------------------------------------------------- within_week_relevance


def week_series(values_by_week: dict[str, list[float]]) -> pd.Series:
    fridays = pd.DatetimeIndex(sorted(values_by_week))
    index = pd.MultiIndex.from_product([fridays, sorted(SECTORS)], names=["date_close", "ticker"])
    values = np.concatenate([values_by_week[str(day.date())] for day in fridays]).astype(np.float64)
    return pd.Series(values, index=index, name="y")


def relevance_values(y: pd.Series) -> np.ndarray:
    rel = models.within_week_relevance(y)
    if isinstance(rel, pd.Series):
        assert rel.index.equals(y.index)
    values = np.asarray(rel)
    assert np.issubdtype(values.dtype, np.integer)
    return values


def test_within_week_relevance_is_the_rank_from_0_to_8():
    y = week_series({"2015-01-09": [0.03, -0.01, 0.05, 0.0, -0.04, 0.02, 0.01, -0.02, -0.03]})
    # sorted tickers XLB XLE XLF XLI XLK XLP XLU XLV XLY
    assert list(relevance_values(y)) == [7, 3, 8, 4, 0, 6, 5, 2, 1]


def test_within_week_relevance_is_a_permutation_in_every_week():
    rng = np.random.default_rng(3)
    y = week_series({str(day.date()): list(rng.normal(size=9)) for day in pd.date_range("2015-01-09", periods=5,
                                                                                          freq="7D")})
    values = relevance_values(y).reshape(5, 9)
    for row in values:
        assert sorted(row) == list(range(9))
    for w in range(5):
        week = y.iloc[9 * w: 9 * (w + 1)].to_numpy()
        assert values[w][np.argmax(week)] == 8 and values[w][np.argmin(week)] == 0


def test_within_week_relevance_exact_ties_go_to_the_alphabetically_earlier_ticker():
    """S41-3 (a): equal y within a week: the earlier ticker gets the higher relevance."""
    y = week_series({
        "2015-01-09": [0.0] * 9,
        "2015-01-16": [0.01, 0.05, -0.02, 0.05, 0.0, -0.02, 0.01, -0.03, -0.05],
    })
    values = relevance_values(y).reshape(2, 9)
    assert list(values[0]) == [8, 7, 6, 5, 4, 3, 2, 1, 0]
    # XLE and XLI tie at the top (XLE 8, XLI 7); XLB and XLU tie at 0.01 (XLB 6, XLU 5); XLF and XLP at -0.02 (3, 2)
    assert list(values[1]) == [6, 8, 3, 7, 4, 2, 5, 1, 0]


def test_within_week_relevance_does_not_depend_on_row_order():
    y = week_series({"2015-01-09": [0.02, 0.02, -0.01, 0.0, 0.03, -0.04, 0.0, 0.01, -0.03]})
    ordered = relevance_values(y)
    shuffled = y.iloc[[4, 0, 8, 2, 6, 1, 3, 7, 5]]
    rel = models.within_week_relevance(shuffled)
    back = pd.Series(np.asarray(rel), index=shuffled.index).reindex(y.index)
    np.testing.assert_array_equal(back.to_numpy(), ordered)


# ---------------------------------------------------------------- RankerModel


def ranker_data(n_weeks: int, seed: int, noise: float = 0.3) -> tuple[pd.DataFrame, pd.Series]:
    """Weekly panels of 9 sectors with three inputs; y = x1 + noise, demeaned within each week."""
    fridays = pd.date_range("2005-01-07", periods=n_weeks, freq="7D")
    index = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(seed)
    x = pd.DataFrame(rng.normal(size=(len(index), 3)), index=index, columns=["x1", "x2", "x3"])
    raw = x["x1"].to_numpy() + rng.normal(0, noise, len(index))
    raw = raw.reshape(n_weeks, 9)
    y = pd.Series((raw - raw.mean(axis=1, keepdims=True)).ravel(), index=index, name="y")
    return x, y


def expected_params(max_depth, n_estimators=200, learning_rate=0.03, seed=42) -> dict:
    return {"objective": "lambdarank", "max_depth": max_depth, "n_estimators": n_estimators,
            "learning_rate": learning_rate, "num_threads": 1, "deterministic": True, "force_row_wise": True,
            "random_state": seed, "verbose": -1, "label_gain": list(range(9)), "lambdarank_truncation_level": 9}


@pytest.mark.parametrize("depth", [2, 3])
def test_ranker_params_are_exactly_the_s41_3_settings(depth):
    params = dict(models.RankerModel(depth).params())
    expected = expected_params(depth, seed=CFG["seed"])
    assert set(params) == set(expected)
    for key, value in expected.items():
        if key == "label_gain":
            assert [float(g) for g in params[key]] == [float(g) for g in value]
        elif key == "learning_rate":
            assert params[key] == pytest.approx(value, rel=1e-15)
        else:
            assert params[key] == value, key


def test_ranker_constructor_values_reach_the_params():
    model = models.RankerModel(3, n_estimators=50, learning_rate=0.1, seed=7, name="M8_d3")
    params = dict(model.params())
    assert (params["max_depth"], params["n_estimators"], params["random_state"]) == (3, 50, 7)
    assert params["learning_rate"] == pytest.approx(0.1)
    assert model.name == "M8_d3"
    assert models.RankerModel(2).name == "M8"
    assert isinstance(models.RankerModel(2), contracts.ScoreModel)


def test_ranker_fit_and_score_follow_contract_14():
    x, y = ranker_data(60, 1)
    model = models.RankerModel(2, n_estimators=60)
    assert model.fit(x, y) is model
    x_new, _ = ranker_data(10, 2)
    score = model.score(x_new)
    assert isinstance(score, pd.Series)
    assert score.name == "score"
    assert score.dtype == np.float64
    assert score.index.equals(x_new.index)
    assert np.isfinite(score.to_numpy()).all()


def test_ranker_score_does_not_change_the_model():
    x, y = ranker_data(60, 3)
    model = models.RankerModel(2, n_estimators=60).fit(x, y)
    first = model.score(x).to_numpy().copy()
    model.score(x * 2.0)
    np.testing.assert_array_equal(model.score(x).to_numpy(), first)


def test_ranker_is_deterministic_across_two_fits():
    x, y = ranker_data(80, 4, noise=1.0)
    a = models.RankerModel(3, n_estimators=80).fit(x, y)
    b = models.RankerModel(3, n_estimators=80).fit(x, y)
    np.testing.assert_array_equal(a.score(x).to_numpy(), b.score(x).to_numpy())


def test_ranker_learns_a_planted_monotone_signal():
    """Relevance follows x1: on new weeks the scores rank the sectors like x1 (mean within-week Spearman > 0.8)."""
    x, y = ranker_data(150, 5)
    model = models.RankerModel(2).fit(x, y)
    x_new, _ = ranker_data(40, 6)
    score = model.score(x_new)
    frame = pd.DataFrame({"score": score, "x1": x_new["x1"]})
    rho = frame.groupby(level="date_close").apply(lambda week: week["score"].rank().corr(week["x1"].rank()))
    assert rho.mean() > 0.8


def test_ranker_score_depends_only_on_the_within_week_order_of_y():
    """The ranker trains on relevance levels: a monotone transform of y inside every week leaves the fit unchanged."""
    x, y = ranker_data(60, 7)
    a = models.RankerModel(2, n_estimators=60).fit(x, y)
    b = models.RankerModel(2, n_estimators=60).fit(x, (y * 3.0 + 0.5).rename("y"))
    np.testing.assert_array_equal(a.score(x).to_numpy(), b.score(x).to_numpy())


def test_ranker_fit_refuses_an_incomplete_week_or_non_finite_inputs():
    x, y = ranker_data(30, 8)
    with pytest.raises(ValueError):
        models.RankerModel(2, n_estimators=20).fit(x.iloc[1:], y.iloc[1:])  # the first week holds 8 sectors
    bad_x = x.copy()
    bad_x.iloc[10, 1] = np.nan
    with pytest.raises(ValueError):
        models.RankerModel(2, n_estimators=20).fit(bad_x, y)
    bad_y = y.copy()
    bad_y.iloc[5] = np.inf
    with pytest.raises(ValueError):
        models.RankerModel(2, n_estimators=20).fit(x, bad_y)


# ---------------------------------------------------------------- grids, tie order and tags (S41-4)


def test_round2_rungs():
    assert tuple(models.ROUND2_RUNGS) == ("M6", "M7", "M8")


def assert_points_equal(got, expected):
    """Same points in the same order, with the YAML types of the grid (0.1 float, 1 and 10 int)."""
    got = [dict(point) for point in got]
    assert got == expected
    for point, want in zip(got, expected, strict=True):
        assert list(point) == list(want)
        for key in want:
            assert type(point[key]) is type(want[key]), (point, key)


def test_round2_grid_in_config_order():
    assert_points_equal(models.round2_grid("M6", CFG), [{"alpha": 0.1}, {"alpha": 1}, {"alpha": 10}])
    assert_points_equal(models.round2_grid("M7", CFG), [
        {"alpha": 0.1, "half_life_weeks": 2}, {"alpha": 0.1, "half_life_weeks": 4},
        {"alpha": 1, "half_life_weeks": 2}, {"alpha": 1, "half_life_weeks": 4},
        {"alpha": 10, "half_life_weeks": 2}, {"alpha": 10, "half_life_weeks": 4}])
    assert_points_equal(models.round2_grid("M8", CFG), [
        {"max_depth": 2, "half_life_weeks": 2}, {"max_depth": 2, "half_life_weeks": 4},
        {"max_depth": 3, "half_life_weeks": 2}, {"max_depth": 3, "half_life_weeks": 4}])


def test_round2_tie_order_is_lambda_or_depth_first_then_h():
    assert_points_equal(models.round2_tie_order("M6", CFG), [{"alpha": 10}, {"alpha": 1}, {"alpha": 0.1}])
    assert_points_equal(models.round2_tie_order("M7", CFG), [
        {"alpha": 10, "half_life_weeks": 4}, {"alpha": 10, "half_life_weeks": 2},
        {"alpha": 1, "half_life_weeks": 4}, {"alpha": 1, "half_life_weeks": 2},
        {"alpha": 0.1, "half_life_weeks": 4}, {"alpha": 0.1, "half_life_weeks": 2}])
    assert_points_equal(models.round2_tie_order("M8", CFG), [
        {"max_depth": 2, "half_life_weeks": 4}, {"max_depth": 2, "half_life_weeks": 2},
        {"max_depth": 3, "half_life_weeks": 4}, {"max_depth": 3, "half_life_weeks": 2}])


@pytest.mark.parametrize("rung, point, tag", [
    ("M6", {"alpha": 0.1}, "a0.1"), ("M6", {"alpha": 1}, "a1"), ("M6", {"alpha": 10}, "a10"),
    ("M7", {"alpha": 10, "half_life_weeks": 4}, "a10_h4"), ("M7", {"alpha": 0.1, "half_life_weeks": 2}, "a0.1_h2"),
    ("M7", {"alpha": 1, "half_life_weeks": 2}, "a1_h2"),
    ("M8", {"max_depth": 2, "half_life_weeks": 2}, "d2_h2"), ("M8", {"max_depth": 3, "half_life_weeks": 4}, "d3_h4"),
])
def test_round2_tag(rung, point, tag):
    assert models.round2_tag(rung, point) == tag


def test_round2_tags_are_distinct_and_in_grid_order():
    tags = {rung: [models.round2_tag(rung, point) for point in models.round2_grid(rung, CFG)] for rung in
            ("M6", "M7", "M8")}
    assert tags == {"M6": ["a0.1", "a1", "a10"],
                    "M7": ["a0.1_h2", "a0.1_h4", "a1_h2", "a1_h4", "a10_h2", "a10_h4"],
                    "M8": ["d2_h2", "d2_h4", "d3_h2", "d3_h4"]}


# ---------------------------------------------------------------- shared synthetic round-2 data

_DATA: dict = {}
_RUNS: dict = {}


def build_round2(market) -> dict:
    """Ladder inputs, 1-week and 4-week labels and round 1's folds, from the synthetic market up to the IS end."""
    keep = market.daily_close.index <= IS_END
    daily_close, daily_open = market.daily_close.loc[keep], market.daily_open.loc[keep]
    sessions = pd.DatetimeIndex(daily_close.index)
    vix = market.vix[market.vix.index <= IS_END]
    fred = market.fred[market.fred.index <= IS_END]
    weekly_open, _ = data.weekly_panel(daily_open, daily_close)
    fwd, realised_on, period = backtest.forward_returns(weekly_open, IS_END)
    labels1 = labels_mod.make_labels(fwd, sessions)
    labels4 = labels_mod.make_horizon_labels(weekly_open, sessions, 4)
    ladder = models.LadderData(
        features=features.asset_features(daily_close, R2CFG), states=features.market_states(daily_close, vix, fred, R2CFG),
        labels=labels1, betas=features.sizing_betas(daily_close, R2CFG), fwd=fwd, realised_on=realised_on,
        period=period, momentum=features.momentum_variants(daily_close, cfg=R2CFG))
    weeks = fwd.index
    folds = labels_mod.walk_forward_folds(weeks, labels_mod.label_end_by_week(labels1, weeks), R2CFG)
    return {"data": ladder, "labels4": labels4, "weeks": weeks, "folds": folds,
            "label_end4": labels_mod.label_end_by_week(labels4, weeks)}


@pytest.fixture
def r2(synthetic_market) -> dict:
    """One synthetic round-2 data set shared by the tests of this module (read-only)."""
    if not _DATA:
        _DATA.update(build_round2(synthetic_market))
    return _DATA


def run_round2(r2: dict, rung: str, value=None):
    """walkforward_round2 on all In-Sample folds, cached by rung and value (inputs are never modified)."""
    key = (rung, key_of(value))
    if key not in _RUNS:
        _RUNS[key] = models.walkforward_round2(rung, r2["data"], r2["labels4"], r2["folds"], R2CFG, value=value)
    return _RUNS[key]


def expected_test_weeks(weeks: pd.MultiIndex, folds) -> pd.MultiIndex:
    closes = closes_of(weeks)
    mask = np.zeros(len(weeks), dtype=bool)
    for fold in folds:
        mask |= np.asarray((closes >= fold.test_start) & (closes <= fold.test_end))
    return weeks[mask]


def fold_rows(scores: pd.DataFrame, fold) -> pd.DataFrame:
    closes = closes_of(scores.index)
    return scores[np.asarray((closes >= fold.test_start) & (closes <= fold.test_end))]


def training_rows(labels4: pd.DataFrame, fold, purge_end=None) -> pd.MultiIndex:
    """Rows with date_close from train_start and a 4-week label_end <= purge_end (S41-2)."""
    purge_end = fold.purge_end if purge_end is None else purge_end
    closes = closes_of(labels4.index)
    ends = pd.DatetimeIndex(labels4["label_end"])
    return labels4.index[np.asarray((closes >= fold.train_start) & (ends <= purge_end))]


def round2_train_end(labels4: pd.DataFrame, fold) -> pd.Timestamp:
    return pd.Timestamp(closes_of(training_rows(labels4, fold)).max())


def manual_ridge(r2: dict, fold, alpha, purge_end=None):
    """M6 fit by hand: purged 4-week training rows, M2 design with in-fold scaling, Ridge(alpha) on y4."""
    d, labels4 = r2["data"], r2["labels4"]
    rows = training_rows(labels4, fold, purge_end)
    labels_mod.assert_purged(labels4.loc[rows, "label_end"], dataclasses.replace(
        fold, purge_end=fold.purge_end if purge_end is None else purge_end))
    x_train, params = models.fit_transform_train(d.features.loc[rows], d.states, interactions=True, cfg=R2CFG)
    model = models.RidgeModel(alpha).fit(x_train, labels4.loc[rows, "y"])
    return model, params


def raw_weekly(r2: dict, model, params, first: pd.Timestamp, last: pd.Timestamp, lags: int) -> pd.DataFrame:
    """f(x[w]) of a fitted model on every calendar week from `lags` weeks before `first` to `last` (weeks x sectors)."""
    d = r2["data"]
    calendar = closes_of(d.states.index)
    start = calendar.get_loc(first) - lags
    assert start >= 0
    needed = calendar[start: calendar.get_loc(last) + 1]
    rows = d.features.loc[np.asarray(closes_of(d.features.index).isin(needed))]
    raw = model.score(models.transform_test(rows, d.states, params))
    return raw.unstack("ticker").reindex(columns=SECTORS).reindex(needed)


def manual_smoothed(r2: dict, fold, alpha, half_life: int) -> np.ndarray:
    """M7 by hand at the test weeks of `fold`: sum_k w_k f(x[t-k]), w_k = 2^(-k/H) normalised, k = 0 ... 3H."""
    lags = 3 * half_life
    weights = 2.0 ** (-np.arange(lags + 1) / half_life)
    weights /= weights.sum()
    model, params = manual_ridge(r2, fold, alpha)
    test = closes_of(fold_rows_index(r2["weeks"], fold))
    wide = raw_weekly(r2, model, params, test[0], test[-1], lags)
    out = []
    for t in test:
        p = wide.index.get_loc(t)
        out.append(sum(weights[k] * wide.iloc[p - k].to_numpy() for k in range(lags + 1)))
    return np.vstack(out)


def fold_rows_index(weeks: pd.MultiIndex, fold) -> pd.MultiIndex:
    closes = closes_of(weeks)
    return weeks[np.asarray((closes >= fold.test_start) & (closes <= fold.test_end))]


# ---------------------------------------------------------------- walkforward_round2: fixed values


def test_round2_four_week_labels_end_three_weeks_after_round1(r2):
    assert closes_of(r2["labels4"].index).max() == pd.Timestamp("2019-11-22")
    assert pd.DatetimeIndex(r2["labels4"]["label_end"]).max() <= IS_END
    assert len(r2["folds"]) == 24


def test_fixed_m6_scores_round1_test_weeks(r2):
    """S41-2: the scored weeks are exactly round 1's test weeks (here the synthetic count) on the same refits."""
    scores, selection = run_round2(r2, "M6", {"alpha": 1})
    assert selection is None
    expected = expected_test_weeks(r2["weeks"], r2["folds"])
    assert list(closes_of(scores.index)) == list(closes_of(expected))
    assert len(scores) == N_TEST_WEEKS == R2CFG["round2"]["test_weeks"]
    assert list(scores.columns) == SECTORS
    contracts.validate_scores(scores)
    assert np.isfinite(scores.to_numpy()).all()
    round1, _ = models.walkforward_rung("M2", r2["data"], r2["folds"], R2CFG, value=1)
    assert list(closes_of(scores.index)) == list(closes_of(round1.index))


@pytest.mark.parametrize("fold_no", [0, 1, 23])
def test_fixed_m6_equals_a_manual_ridge_on_the_four_week_label(r2, fold_no):
    """M6 = Ridge(alpha) on the M2 design and y4, trained on the rows with 4-week label_end <= purge_end."""
    scores, _ = run_round2(r2, "M6", {"alpha": 1})
    fold = r2["folds"][fold_no]
    model, params = manual_ridge(r2, fold, 1)
    d = r2["data"]
    test_closes = closes_of(fold_rows_index(r2["weeks"], fold))
    rows = d.features.loc[np.asarray(closes_of(d.features.index).isin(test_closes))]
    expected = models.to_weekly(model.score(models.transform_test(rows, d.states, params)),
                                fold_rows_index(r2["weeks"], fold), R2CFG)
    np.testing.assert_allclose(fold_rows(scores, fold).to_numpy(), expected.to_numpy(), rtol=1e-9, atol=1e-12)


@pytest.mark.parametrize("fold_no, alpha, half_life", [(0, 1, 2), (5, 10, 4)])
def test_m7_score_is_the_weighted_average_of_m6_scores_over_the_lagged_weeks(r2, fold_no, alpha, half_life):
    """S41-3: M7[t] = sum_k w_k f(x[t-k]) with the current refit's M6 fit (same lambda), k = 0 ... 3H."""
    scores, selection = run_round2(r2, "M7", {"alpha": alpha, "half_life_weeks": half_life})
    assert selection is None
    fold = r2["folds"][fold_no]
    np.testing.assert_allclose(fold_rows(scores, fold).to_numpy(), manual_smoothed(r2, fold, alpha, half_life),
                               rtol=1e-9, atol=1e-12)


def test_m7_differs_from_m6_at_the_same_lambda(r2):
    """M7 differs from M6 at the same lambda (the smoothing changes the scores), and both are finite."""
    m6, _ = run_round2(r2, "M6", {"alpha": 1})
    m7, _ = run_round2(r2, "M7", {"alpha": 1, "half_life_weeks": 2})
    assert m7.index.equals(m6.index)
    assert np.isfinite(m7.to_numpy()).all()
    assert not np.allclose(m7.to_numpy(), m6.to_numpy())


def test_fixed_m8_scores_round1_test_weeks(r2):
    scores, selection = run_round2(r2, "M8", {"max_depth": 2, "half_life_weeks": 2})
    assert selection is None
    assert list(closes_of(scores.index)) == list(closes_of(expected_test_weeks(r2["weeks"], r2["folds"])))
    contracts.validate_scores(scores)
    assert np.isfinite(scores.to_numpy()).all()


def test_fixed_run_is_deterministic(r2):
    first, _ = run_round2(r2, "M7", {"alpha": 1, "half_life_weeks": 2})
    second, _ = models.walkforward_round2("M7", r2["data"], r2["labels4"], r2["folds"], R2CFG,
                                          value={"alpha": 1, "half_life_weeks": 2})
    pd.testing.assert_frame_equal(first, second, check_exact=True)


# ---------------------------------------------------------------- walkforward_round2: the 4-week purge


def with_late_label(labels4: pd.DataFrame, week: pd.Timestamp, label_end: pd.Timestamp) -> pd.DataFrame:
    bad = labels4.copy()
    bad.loc[np.asarray(closes_of(bad.index) == week), "label_end"] = label_end
    contracts.validate_labels(bad)
    return bad


@pytest.mark.parametrize("rung, value", [("M6", {"alpha": 1}), ("M6", None),
                                         ("M7", {"alpha": 1, "half_life_weeks": 4}),
                                         ("M8", {"max_depth": 2, "half_life_weeks": 2})])
def test_a_training_label_ending_after_purge_end_raises(r2, rung, value):
    """A training week whose 4-week label_end is moved after purge_end makes walkforward_round2 raise ContractError."""
    fold = r2["folds"][0]
    weeks = np.unique(closes_of(training_rows(r2["labels4"], fold)))
    bad = with_late_label(r2["labels4"], pd.Timestamp(weeks[20]), fold.purge_end + DAY)
    with pytest.raises(ContractError):
        models.walkforward_round2(rung, r2["data"], bad, r2["folds"], R2CFG, value=value)


def test_an_inner_training_label_ending_after_the_inner_purge_raises(r2):
    """A 4-week label_end moved into (inner purge_end, outer purge_end] trips the inner purge check (ContractError)."""
    fold = r2["folds"][0]
    inner = models.inner_fold(fold, r2["label_end4"], INNER_WEEKS, R2CFG["split"]["embargo_weeks"])
    weeks = np.unique(closes_of(training_rows(r2["labels4"], fold, inner.purge_end)))
    moved = inner.purge_end + DAY
    assert moved <= fold.purge_end
    bad = with_late_label(r2["labels4"], pd.Timestamp(weeks[-5]), moved)
    with pytest.raises(ContractError):
        models.walkforward_round2("M6", r2["data"], bad, r2["folds"], R2CFG)


def test_scores_ignore_every_four_week_label_realised_after_the_cutoff(r2):
    """Noise in every y4 whose label_end is after refit k's purge_end leaves refits 0..k unchanged and changes k+1.
    A purge by the 1-week label_end would let those labels in, so the check has power."""
    folds = r2["folds"]
    k = 1
    base, _ = run_round2(r2, "M6", {"alpha": 1})
    noisy = r2["labels4"].copy()
    late = np.asarray(pd.DatetimeIndex(noisy["label_end"]) > folds[k].purge_end)
    noise = np.random.default_rng(11).normal(0.0, 0.1, (int(late.sum()) // 9, 9))
    noisy.loc[late, "y"] = (noise - noise.mean(axis=1, keepdims=True)).ravel()
    one_week_late = np.asarray(pd.DatetimeIndex(r2["data"].labels["label_end"]) > folds[k].purge_end)
    assert closes_of(noisy.index[late]).min() < closes_of(r2["data"].labels.index[one_week_late]).min()
    scores, _ = models.walkforward_round2("M6", r2["data"], noisy, folds, R2CFG, value={"alpha": 1})
    upto = np.asarray(closes_of(base.index) <= folds[k].test_end)
    pd.testing.assert_frame_equal(base[upto], scores[upto], check_exact=True)
    assert not np.allclose(fold_rows(base, folds[k + 1]).to_numpy(), fold_rows(scores, folds[k + 1]).to_numpy())


# ---------------------------------------------------------------- walkforward_round2: Amendment 5 C1 on the grids


def tags_of(rung: str) -> list[str]:
    return [models.round2_tag(rung, point) for point in models.round2_grid(rung, R2CFG)]


def tie_tags(rung: str) -> list[str]:
    return [models.round2_tag(rung, point) for point in models.round2_tie_order(rung, R2CFG)]


CHOSEN_COLUMNS = {"M6": ["chosen_alpha"], "M7": ["chosen_alpha", "chosen_half_life_weeks"],
                  "M8": ["chosen_max_depth", "chosen_half_life_weeks"]}


def check_selection(r2: dict, rung: str, selection: pd.DataFrame) -> None:
    tags = tags_of(rung)
    assert list(selection.columns) == (SELECTION_BASE + [f"sharpe_{tag}" for tag in tags] + ["chosen"]
                                       + CHOSEN_COLUMNS[rung])
    assert len(selection) == len(r2["folds"])
    points = {models.round2_tag(rung, point): point for point in models.round2_grid(rung, R2CFG)}
    for k, fold in enumerate(r2["folds"]):
        row = selection.iloc[k]
        inner = models.inner_fold(fold, r2["label_end4"], INNER_WEEKS, R2CFG["split"]["embargo_weeks"])
        assert (int(row["test_year"]), int(row["refit"])) == (fold.test_year, fold.refit)
        for column, expected in (("test_start", fold.test_start), ("train_start", fold.train_start),
                                 ("train_end", round2_train_end(r2["labels4"], fold)), ("purge_end", fold.purge_end),
                                 ("inner_train_end", inner.train_end), ("inner_purge_end", inner.purge_end),
                                 ("inner_val_start", inner.test_start), ("inner_val_end", inner.test_end)):
            assert pd.Timestamp(row[column]) == expected, (k, column)
        assert pd.Timestamp(row["train_end"]) < fold.train_end  # the 4-week window ends earlier than round 1's
        assert pd.Timestamp(row["inner_val_end"]) == pd.Timestamp(row["train_end"])
        assert int(row["inner_val_weeks"]) == INNER_WEEKS
        sharpes = {tag: float(row[f"sharpe_{tag}"]) for tag in tags}
        assert row["chosen"] == models.choose_grid_value(sharpes, tie_tags(rung)), k
        point = points[row["chosen"]]
        for column in CHOSEN_COLUMNS[rung]:
            assert row[column] == point[column.removeprefix("chosen_")], (k, column)


def test_tuned_m6_selection_table(r2):
    scores, selection = run_round2(r2, "M6")
    contracts.validate_scores(scores)
    assert list(closes_of(scores.index)) == list(closes_of(expected_test_weeks(r2["weeks"], r2["folds"])))
    check_selection(r2, "M6", selection)


def test_tuned_m7_selection_table_uses_the_combined_tie_order(r2):
    scores, selection = run_round2(r2, "M7")
    contracts.validate_scores(scores)
    check_selection(r2, "M7", selection)


def test_tuned_m8_selection_table(r2):
    scores, selection = run_round2(r2, "M8")
    contracts.validate_scores(scores)
    assert list(closes_of(scores.index)) == list(closes_of(expected_test_weeks(r2["weeks"], r2["folds"])))
    check_selection(r2, "M8", selection)


@pytest.mark.parametrize("fold_no", [0, 7])
def test_m6_inner_sharpes_by_hand(r2, fold_no):
    """Each inner Sharpe = inner_sharpe of the inner fit's scores on the 26 validation weeks (1-week returns, §09)."""
    _, selection = run_round2(r2, "M6")
    d = r2["data"]
    fold = r2["folds"][fold_no]
    inner = models.inner_fold(fold, r2["label_end4"], INNER_WEEKS, R2CFG["split"]["embargo_weeks"])
    closes = closes_of(r2["weeks"])
    validation = r2["weeks"][np.asarray((closes >= inner.test_start) & (closes <= inner.test_end))]
    assert len(validation) == INNER_WEEKS
    for point in models.round2_grid("M6", R2CFG):
        model, params = manual_ridge(r2, fold, point["alpha"], purge_end=inner.purge_end)
        rows = d.features.loc[np.asarray(closes_of(d.features.index).isin(closes_of(validation)))]
        val_scores = models.to_weekly(model.score(models.transform_test(rows, d.states, params)), validation, R2CFG)
        expected = models.inner_sharpe(val_scores, d.betas, d.fwd, d.period, R2CFG)
        got = float(selection.iloc[fold_no][f"sharpe_{models.round2_tag('M6', point)}"])
        assert got == pytest.approx(expected, rel=1e-9, abs=1e-12), point


def test_tuned_m7_scores_equal_the_fixed_run_at_the_chosen_point(r2):
    """Each refit of the tuned run scores its test weeks exactly like the fixed run at the point it chose."""
    tuned, selection = run_round2(r2, "M7")
    points = {models.round2_tag("M7", point): point for point in models.round2_grid("M7", R2CFG)}
    for k, fold in enumerate(r2["folds"]):
        fixed, _ = run_round2(r2, "M7", points[selection.iloc[k]["chosen"]])
        np.testing.assert_allclose(fold_rows(tuned, fold).to_numpy(), fold_rows(fixed, fold).to_numpy(), rtol=1e-12,
                                   atol=1e-12)


def test_tuned_m6_scores_equal_the_fixed_run_at_the_chosen_value(r2):
    tuned, selection = run_round2(r2, "M6")
    points = {models.round2_tag("M6", point): point for point in models.round2_grid("M6", R2CFG)}
    for k, fold in enumerate(r2["folds"]):
        fixed, _ = run_round2(r2, "M6", points[selection.iloc[k]["chosen"]])
        np.testing.assert_allclose(fold_rows(tuned, fold).to_numpy(), fold_rows(fixed, fold).to_numpy(), rtol=1e-12,
                                   atol=1e-12)


def test_tuned_run_is_deterministic(r2):
    first = run_round2(r2, "M6")
    second = models.walkforward_round2("M6", r2["data"], r2["labels4"], r2["folds"], R2CFG)
    pd.testing.assert_frame_equal(first[0], second[0], check_exact=True)
    pd.testing.assert_frame_equal(first[1], second[1], check_exact=True)


# ---------------------------------------------------------------- the frozen value (S41-6)


def test_frozen_value_is_the_last_refits_point_with_grid_types(r2):
    _, selection = run_round2(r2, "M7")
    frozen = models.round2_frozen_value("M7", selection, R2CFG)
    points = {models.round2_tag("M7", point): point for point in models.round2_grid("M7", R2CFG)}
    expected = points[selection.iloc[-1]["chosen"]]
    assert isinstance(frozen, dict)
    assert frozen == expected
    for key in expected:
        assert type(frozen[key]) is type(expected[key])


def test_frozen_value_from_selection_csv_keeps_the_grid_types(r2, tmp_path):
    """Read back from selection.csv (chosen_alpha may come back as a float), the value has the grid's types."""
    for rung in ("M6", "M7"):
        _, selection = run_round2(r2, rung)
        path = tmp_path / f"{rung}_selection.csv"
        selection.to_csv(path, index=False)
        frozen = models.round2_frozen_value(rung, pd.read_csv(path), R2CFG)
        points = {models.round2_tag(rung, point): point for point in models.round2_grid(rung, R2CFG)}
        expected = points[selection.iloc[-1]["chosen"]]
        assert frozen == expected
        for key in expected:
            assert type(frozen[key]) is type(expected[key]), (rung, key)


def test_frozen_value_refuses_a_selection_without_the_last_test_year(r2):
    _, selection = run_round2(r2, "M7")
    last_year = int(R2CFG["split"]["test_years"][1])
    earlier = selection[selection["test_year"].astype(int) != last_year].reset_index(drop=True)
    assert int(earlier.iloc[-1]["test_year"]) == last_year - 1
    with pytest.raises(ValueError):
        models.round2_frozen_value("M7", earlier, R2CFG)


# ---------------------------------------------------------------- the Out-of-Sample hook (S41-6), synthetic only


def build_oos(script03, market, lock: Path, r2: dict) -> dict:
    """Inputs to the synthetic data end, 4-week labels built through the lock, and 08's extended folds."""
    data_end = pd.Timestamp(market.sessions.max())
    labels4 = script03.build_horizon_labels(market.daily_open, market.daily_close, IS_END, 4, truncate_at=data_end,
                                            lock_path=lock)
    fwd, realised_on, period = backtest.forward_returns(market.weekly_open, IS_END)
    labels1 = labels_mod.make_labels(fwd, market.sessions)
    ladder = models.LadderData(
        features=features.asset_features(market.daily_close, R2CFG),
        states=features.market_states(market.daily_close, market.vix, market.fred, R2CFG), labels=labels1,
        betas=features.sizing_betas(market.daily_close, R2CFG), fwd=fwd, realised_on=realised_on, period=period)
    extended = copy.deepcopy(R2CFG)
    extended["split"]["in_sample_end"] = data_end.strftime("%Y-%m-%d")
    extended["split"]["test_years"] = [int(R2CFG["split"]["test_years"][1]), int(data_end.year)]
    weeks = ladder.states.index
    folds = labels_mod.walk_forward_folds(weeks, labels_mod.label_end_by_week(labels1, weeks), extended)
    kept = [fold for fold in folds if fold.test_end > LAST_WEEK]
    assert kept and kept[0].test_start <= LAST_WEEK
    return {"data": ladder, "labels4": labels4, "folds": kept, "data_end": data_end}


_OOS: dict = {}


@pytest.fixture
def oos(script03, synthetic_market, r2, tmp_path_factory) -> dict:
    if not _OOS:
        lock = tmp_path_factory.mktemp("frozen") / "FROZEN.lock"
        lock.write_text("signed\n", encoding="utf-8")
        _OOS.update(build_oos(script03, synthetic_market, lock, r2))
        _, selection = run_round2(r2, "M7")
        _OOS["frozen"] = models.round2_frozen_value("M7", selection, R2CFG)
        _OOS["scores"], _OOS["selection"] = models.walkforward_round2(
            "M7", _OOS["data"], _OOS["labels4"], _OOS["folds"], R2CFG, value=_OOS["frozen"])
    return _OOS


def test_oos_labels_reach_past_the_in_sample_end(oos):
    assert pd.DatetimeIndex(oos["labels4"]["label_end"]).max() > IS_END
    assert pd.DatetimeIndex(oos["labels4"]["label_end"]).max() <= oos["data_end"]


def test_oos_hook_scores_the_weeks_after_the_last_in_sample_week(oos):
    scores = oos["scores"]
    assert oos["selection"] is None
    closes = closes_of(scores.index)
    assert closes.max() > LAST_WEEK
    assert closes.min() == oos["folds"][0].test_start
    assert closes.max() == oos["folds"][-1].test_end
    expected = expected_test_weeks(oos["data"].states.index, oos["folds"])
    assert list(closes) == list(closes_of(expected))
    later = scores[np.asarray(closes > LAST_WEEK)]
    assert len(later) > 40 and np.isfinite(later.to_numpy()).all()
    contracts.validate_scores(scores)


def test_oos_hook_reproduces_the_in_sample_scores_of_the_last_in_sample_refit(oos, r2):
    """The refit window holding 2019-12-13 refits on the same purged rows, so its In-Sample weeks match (1e-12)."""
    in_sample, _ = run_round2(r2, "M7", oos["frozen"])
    first = oos["folds"][0]
    is_closes = closes_of(in_sample.index)
    oos_closes = closes_of(oos["scores"].index)
    window_is = in_sample[np.asarray((is_closes >= first.test_start) & (is_closes <= LAST_WEEK))]
    window_oos = oos["scores"][np.asarray((oos_closes >= first.test_start) & (oos_closes <= LAST_WEEK))]
    assert len(window_is) > 0
    assert list(closes_of(window_is.index)) == list(closes_of(window_oos.index))
    np.testing.assert_allclose(window_oos.to_numpy(), window_is.to_numpy(), rtol=0, atol=1e-12)


def test_oos_hook_purges_every_refit(oos):
    """A training week of an Out-of-Sample refit whose 4-week label_end is after that refit's purge_end raises."""
    last = oos["folds"][-1]
    weeks = np.unique(closes_of(training_rows(oos["labels4"], last)))
    target = pd.Timestamp(weeks[weeks > np.datetime64(IS_END)][2])
    bad = with_late_label(oos["labels4"], target, last.purge_end + DAY)
    with pytest.raises(ContractError):
        models.walkforward_round2("M7", oos["data"], bad, oos["folds"], R2CFG, value=oos["frozen"])


def test_oos_hook_ignores_four_week_labels_realised_after_each_cutoff(oos):
    """Noise in every y4 realised after the first kept refit's purge_end leaves that refit's scores unchanged."""
    first = oos["folds"][0]
    noisy = oos["labels4"].copy()
    late = np.asarray(pd.DatetimeIndex(noisy["label_end"]) > first.purge_end)
    noise = np.random.default_rng(13).normal(0.0, 0.1, (int(late.sum()) // 9, 9))
    noisy.loc[late, "y"] = (noise - noise.mean(axis=1, keepdims=True)).ravel()
    scores, _ = models.walkforward_round2("M7", oos["data"], noisy, oos["folds"], R2CFG, value=oos["frozen"])
    pd.testing.assert_frame_equal(fold_rows(oos["scores"], first), fold_rows(scores, first), check_exact=True)


def test_tuning_is_refused_on_a_fold_ending_after_the_in_sample_end(oos):
    """S41-2, S41-6: with value=None, a fold whose test window ends after split.in_sample_end is refused."""
    with pytest.raises((ValueError, PermissionError)):
        models.walkforward_round2("M6", oos["data"], oos["labels4"], oos["folds"], R2CFG)
    with pytest.raises((ValueError, PermissionError)):
        models.walkforward_round2("M6", oos["data"], oos["labels4"], oos["folds"][-1:], R2CFG)
