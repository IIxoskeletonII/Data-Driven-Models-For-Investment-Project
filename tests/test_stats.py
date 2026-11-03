"""Inference statistics of src/stats.py (§07 gate, §11; Amendment 5; S31-8, S31-9).

Expected values are computed here independently: explicit loops over lags, splits and resamples, scipy and statsmodels
reference implementations, and published constants. Every series is synthetic (fixed seeds); no data file is read.
"""

import copy
import itertools
import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from scipy import stats as sps

from src import metrics, stats
from src.config import load_config

CFG = load_config()
SECTORS = list(CFG["data"]["tickers"])
P = 52
EULER_GAMMA = 0.5772156649015329
BOOT_KEYS = {"uplift", "lower", "upper", "p_uplift_positive", "mean_diff", "mean_diff_lower", "mean_diff_upper", "n_weeks", "block",
             "n_resamples"}
CANDIDATE_KEYS = {"name", "status", "sharpe", "sharpe_m0", "mdd", "mdd_m0", "p_uplift_positive", "p_uplift_positive_sensitivity",
                  "uplift_lower", "uplift_upper", "sharpe_zero_cost", "sharpe_m0_zero_cost",
                  "passes_sharpe", "passes_mdd", "passes_bootstrap", "passes"}


def weekly_index(n: int, start: str = "2010-01-08") -> pd.MultiIndex:
    closes = pd.date_range(start, periods=n, freq="7D")
    return pd.MultiIndex.from_arrays([closes - pd.Timedelta(days=4), closes], names=["date_open", "date_close"])


def weekly_series(values, start: str = "2010-01-08", name: str = "net") -> pd.Series:
    values = np.asarray(values, dtype=np.float64)
    return pd.Series(values, index=weekly_index(len(values), start), name=name)


def ref_sharpe(r: np.ndarray, rf_annual: float = 0.0) -> float:
    """Skeleton Sharpe of a weekly array: (Π(1 + r)^(52/T) − 1 − rf) / (std(ddof=1)·√52)."""
    annual = np.prod(1.0 + r) ** (P / len(r)) - 1.0
    return (annual - rf_annual) / (np.std(r, ddof=1) * np.sqrt(P))


# ---------------------------------------------------------------- stationary bootstrap indices


def test_stationary_bootstrap_indices_shape_dtype_and_range():
    """Indices have shape (n_resamples, n), an integer dtype and values in [0, n)."""
    idx = stats.stationary_bootstrap_indices(37, 250, 4, np.random.default_rng(1))
    assert idx.shape == (250, 37)
    assert np.issubdtype(idx.dtype, np.integer)
    assert idx.min() >= 0 and idx.max() < 37


def test_stationary_bootstrap_indices_are_deterministic_for_a_seed():
    """The same seed gives identical indices; another seed gives different ones."""
    a = stats.stationary_bootstrap_indices(100, 50, 4, np.random.default_rng(42))
    b = stats.stationary_bootstrap_indices(100, 50, 4, np.random.default_rng(42))
    c = stats.stationary_bootstrap_indices(100, 50, 4, np.random.default_rng(43))
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


def _mean_run_length(idx: np.ndarray, n: int) -> float:
    """Average length of the runs of consecutive (circular) indices, each resample starting a new run."""
    breaks = (idx[:, 1:] != (idx[:, :-1] + 1) % n).sum()
    return idx.size / (breaks + idx.shape[0])


@pytest.mark.parametrize("block", [4, 8])
def test_stationary_bootstrap_mean_run_length_is_the_block(block):
    """The mean run length of consecutive indices is close to the mean block length."""
    n = 1000
    idx = stats.stationary_bootstrap_indices(n, 300, block, np.random.default_rng(7))
    assert _mean_run_length(idx, n) == pytest.approx(block, rel=0.05)


def test_stationary_bootstrap_block_one_draws_independent_indices():
    """block = 1: a consecutive pair occurs only by chance (rate about 1/n)."""
    n = 1000
    idx = stats.stationary_bootstrap_indices(n, 300, 1, np.random.default_rng(3))
    continued = (idx[:, 1:] == (idx[:, :-1] + 1) % n).mean()
    assert continued < 5.0 / n


def test_stationary_bootstrap_indices_are_uniform_over_positions():
    """Every position is drawn with roughly equal frequency (circular wrap keeps the marginal uniform)."""
    n = 50
    idx = stats.stationary_bootstrap_indices(n, 4000, 4, np.random.default_rng(11))
    counts = np.bincount(idx.ravel(), minlength=n)
    expected = idx.size / n
    assert np.all(np.abs(counts - expected) < 0.2 * expected)


def test_stationary_bootstrap_indices_wrap_circularly():
    """After the last position a continued block resumes at position 0."""
    n = 5
    idx = stats.stationary_bootstrap_indices(n, 2000, 50, np.random.default_rng(5))
    after_last = idx[:, 1:][idx[:, :-1] == n - 1]
    assert (after_last == 0).mean() > 0.9


# ---------------------------------------------------------------- paired block bootstrap


@pytest.fixture(scope="module")
def pair() -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(2024)
    baseline = weekly_series(rng.normal(0.001, 0.02, 160))
    candidate = weekly_series(0.6 * baseline.to_numpy() + rng.normal(0.0015, 0.015, 160))
    return candidate, baseline


def reference_bootstrap(c: np.ndarray, b: np.ndarray, n_resamples: int, block: float, seed: int, rf=None,
                        confidence: float = 0.95) -> dict:
    """Independent re-implementation of S31-8 on top of stationary_bootstrap_indices."""
    idx = stats.stationary_bootstrap_indices(len(c), n_resamples, block, np.random.default_rng(seed))
    uplifts, diffs = np.empty(n_resamples), np.empty(n_resamples)
    for k in range(n_resamples):
        rows = idx[k]
        if rf is None:
            rf_annual = 0.0
        elif np.isscalar(rf):
            rf_annual = float(rf)
        else:
            rf_annual = np.prod(1.0 + rf[rows]) ** (P / len(rows)) - 1.0
        uplifts[k] = ref_sharpe(c[rows], rf_annual) - ref_sharpe(b[rows], rf_annual)
        diffs[k] = np.mean(c[rows] - b[rows])
    alpha = (1 - confidence) / 2
    return {"p_uplift_positive": float(np.mean(uplifts > 0)), "lower": float(np.quantile(uplifts, alpha)),
            "upper": float(np.quantile(uplifts, 1 - alpha)), "mean_diff_lower": float(np.quantile(diffs, alpha)),
            "mean_diff_upper": float(np.quantile(diffs, 1 - alpha))}


def test_paired_block_bootstrap_keys_and_metadata(pair):
    """The result has the agreed keys, and n_weeks, block and n_resamples echo the inputs."""
    c, b = pair
    out = stats.paired_block_bootstrap(c, b, n_resamples=300, block=4, seed=1)
    assert set(out) == BOOT_KEYS
    assert out["n_weeks"] == len(c)
    assert out["block"] == 4
    assert out["n_resamples"] == 300


def test_paired_block_bootstrap_observed_uplift_is_the_metrics_sharpe_difference(pair):
    """uplift = metrics.sharpe_ratio(c, 0) − metrics.sharpe_ratio(b, 0); mean_diff = mean(c − b)."""
    c, b = pair
    out = stats.paired_block_bootstrap(c, b, n_resamples=200, block=4, seed=3)
    expected = metrics.sharpe_ratio(c, 0.0) - metrics.sharpe_ratio(b, 0.0)
    assert out["uplift"] == pytest.approx(expected, rel=1e-12, abs=1e-14)
    assert out["uplift"] == pytest.approx(ref_sharpe(c.to_numpy()) - ref_sharpe(b.to_numpy()), rel=1e-12)
    assert out["mean_diff"] == pytest.approx(float(np.mean(c.to_numpy() - b.to_numpy())), rel=1e-12)


def test_paired_block_bootstrap_matches_an_independent_reimplementation(pair):
    """p_uplift and both percentile intervals equal a loop over the same stationary-bootstrap indices."""
    c, b = pair
    out = stats.paired_block_bootstrap(c, b, n_resamples=500, block=4, seed=42)
    ref = reference_bootstrap(c.to_numpy(), b.to_numpy(), 500, 4, 42)
    assert out["p_uplift_positive"] == pytest.approx(ref["p_uplift_positive"], abs=1e-12)
    for key in ("lower", "upper", "mean_diff_lower", "mean_diff_upper"):
        assert out[key] == pytest.approx(ref[key], rel=1e-10, abs=1e-12), key


def test_paired_block_bootstrap_confidence_level_sets_the_interval(pair):
    """confidence = 0.80 gives the 10% and 90% quantiles of the resampled uplifts."""
    c, b = pair
    out = stats.paired_block_bootstrap(c, b, n_resamples=400, block=8, seed=9, confidence=0.80)
    ref = reference_bootstrap(c.to_numpy(), b.to_numpy(), 400, 8, 9, confidence=0.80)
    assert out["lower"] == pytest.approx(ref["lower"], rel=1e-10, abs=1e-12)
    assert out["upper"] == pytest.approx(ref["upper"], rel=1e-10, abs=1e-12)
    assert out["block"] == 8


def test_paired_block_bootstrap_with_a_constant_annual_rf(pair):
    """A float rf is subtracted from both annualised returns on the sample and on every resample."""
    c, b = pair
    out = stats.paired_block_bootstrap(c, b, n_resamples=300, block=4, seed=5, rf=0.02)
    assert out["uplift"] == pytest.approx(metrics.sharpe_ratio(c, 0.02) - metrics.sharpe_ratio(b, 0.02), rel=1e-12)
    ref = reference_bootstrap(c.to_numpy(), b.to_numpy(), 300, 4, 5, rf=0.02)
    assert out["p_uplift_positive"] == pytest.approx(ref["p_uplift_positive"], abs=1e-12)
    assert out["lower"] == pytest.approx(ref["lower"], rel=1e-10, abs=1e-12)
    assert out["upper"] == pytest.approx(ref["upper"], rel=1e-10, abs=1e-12)


def test_paired_block_bootstrap_with_a_weekly_rf_series(pair):
    """A weekly rf series is resampled with the same indices and annualised like the returns."""
    c, b = pair
    rf = pd.Series(np.linspace(0.0002, 0.0009, len(c)), index=c.index, name="rf")
    out = stats.paired_block_bootstrap(c, b, n_resamples=300, block=4, seed=6, rf=rf)
    assert out["uplift"] == pytest.approx(metrics.sharpe_ratio(c, rf) - metrics.sharpe_ratio(b, rf), rel=1e-12)
    ref = reference_bootstrap(c.to_numpy(), b.to_numpy(), 300, 4, 6, rf=rf.to_numpy())
    assert out["p_uplift_positive"] == pytest.approx(ref["p_uplift_positive"], abs=1e-12)
    assert out["lower"] == pytest.approx(ref["lower"], rel=1e-10, abs=1e-12)
    assert out["upper"] == pytest.approx(ref["upper"], rel=1e-10, abs=1e-12)


def test_paired_block_bootstrap_rf_none_equals_rf_zero(pair):
    """rf = None is the zero-cost convention, identical to rf = 0.0."""
    c, b = pair
    a = stats.paired_block_bootstrap(c, b, n_resamples=200, block=4, seed=8)
    z = stats.paired_block_bootstrap(c, b, n_resamples=200, block=4, seed=8, rf=0.0)
    for key in BOOT_KEYS:
        assert a[key] == pytest.approx(z[key], rel=1e-12, abs=1e-15), key


def test_paired_block_bootstrap_identical_series_give_zero_uplift(pair):
    """candidate == baseline: uplift 0, P(uplift > 0) = 0, interval [0, 0], mean difference 0."""
    _, b = pair
    out = stats.paired_block_bootstrap(b.copy(), b, n_resamples=300, block=4, seed=1)
    assert out["uplift"] == 0.0
    assert out["p_uplift_positive"] == 0.0
    assert out["lower"] == 0.0 and out["upper"] == 0.0
    assert out["mean_diff"] == 0.0
    assert out["mean_diff_lower"] == 0.0 and out["mean_diff_upper"] == 0.0


def test_paired_block_bootstrap_constant_weekly_gain_gives_probability_one(pair):
    """candidate = baseline + 1% per week: every resample has a higher Sharpe, so P(uplift > 0) = 1."""
    _, b = pair
    c = b + 0.01
    out = stats.paired_block_bootstrap(c, b, n_resamples=500, block=4, seed=2)
    assert out["p_uplift_positive"] == 1.0
    assert out["lower"] > 0
    assert out["mean_diff"] == pytest.approx(0.01, rel=1e-10)
    assert out["mean_diff_lower"] == pytest.approx(0.01, rel=1e-10)
    assert out["mean_diff_upper"] == pytest.approx(0.01, rel=1e-10)


def test_paired_block_bootstrap_is_deterministic(pair):
    """The same seed gives an identical result dictionary."""
    c, b = pair
    first = stats.paired_block_bootstrap(c, b, n_resamples=400, block=4, seed=42)
    second = stats.paired_block_bootstrap(c, b, n_resamples=400, block=4, seed=42)
    assert first == second


def test_paired_block_bootstrap_defaults_are_5000_resamples_block_4_seed_42(pair):
    """Defaults: 5,000 resamples, block 4, seed 42, confidence 0.95."""
    c, b = pair
    out = stats.paired_block_bootstrap(c, b)
    assert out["n_resamples"] == 5000 and out["block"] == 4
    ref = reference_bootstrap(c.to_numpy(), b.to_numpy(), 5000, 4, 42)
    assert out["p_uplift_positive"] == pytest.approx(ref["p_uplift_positive"], abs=1e-12)
    assert out["lower"] == pytest.approx(ref["lower"], rel=1e-10, abs=1e-12)


def test_paired_block_bootstrap_refuses_different_indices(pair):
    """Series on different weekly indices raise ValueError."""
    c, b = pair
    shifted = weekly_series(c.to_numpy(), start="2010-01-15")
    with pytest.raises(ValueError):
        stats.paired_block_bootstrap(shifted, b, n_resamples=50)
    with pytest.raises(ValueError):
        stats.paired_block_bootstrap(c.iloc[1:], b, n_resamples=50)


def test_paired_block_bootstrap_refuses_nan(pair):
    """A NaN in either series raises ValueError."""
    c, b = pair
    bad = c.copy()
    bad.iloc[10] = np.nan
    with pytest.raises(ValueError):
        stats.paired_block_bootstrap(bad, b, n_resamples=50)
    with pytest.raises(ValueError):
        stats.paired_block_bootstrap(b, bad, n_resamples=50)


# ---------------------------------------------------------------- Newey-West lags and HAC variance


@pytest.mark.parametrize("n", [1, 3, 50, 100, 200, 624, 1000])
def test_newey_west_lags_formula(n):
    """L = floor(4 (n/100)^(2/9))."""
    assert stats.newey_west_lags(n) == math.floor(4 * (n / 100) ** (2 / 9))


def test_newey_west_lags_known_values():
    """Known values: n = 1 -> 1, n = 100 -> 4, n = 624 -> 6, n = 1000 -> 6."""
    assert stats.newey_west_lags(1) == 1
    assert stats.newey_west_lags(100) == 4
    assert stats.newey_west_lags(624) == 6
    assert stats.newey_west_lags(1000) == 6
    assert isinstance(stats.newey_west_lags(624), int)


@pytest.mark.parametrize(("lags", "expected"), [(0, 0.4), (1, 0.44), (2, 0.4533333333333333)])
def test_hac_variance_of_mean_hand_values(lags, expected):
    """x = [1, 2, 4, 3, 5]: gamma0 = 2, gamma1 = 0.2, gamma2 = 0, Bartlett weights 1 − l/(L+1), divided by n = 5."""
    x = np.array([1.0, 2.0, 4.0, 3.0, 5.0])
    assert stats.hac_variance_of_mean(x, lags) == pytest.approx(expected, rel=1e-12)


def test_hac_variance_of_mean_lag_zero_is_population_variance_over_n():
    """lags = 0 gives var(x, ddof=0) / n."""
    x = np.random.default_rng(0).normal(size=41)
    assert stats.hac_variance_of_mean(x, 0) == pytest.approx(np.var(x) / len(x), rel=1e-12)


@pytest.mark.parametrize("lags", [1, 4, 7])
def test_hac_variance_of_mean_equals_statsmodels(lags):
    """Equals the squared HAC standard error of OLS on a constant (statsmodels, no small-sample correction)."""
    rng = np.random.default_rng(lags)
    x = 0.1 * np.cumsum(rng.normal(size=80)) + rng.normal(size=80)
    fit = sm.OLS(x, np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": False})
    assert stats.hac_variance_of_mean(x, lags) == pytest.approx(fit.bse[0] ** 2, rel=1e-10)


# ---------------------------------------------------------------- rank IC


def sector_frame(rows, start: str = "2010-01-08", extra: dict | None = None) -> pd.DataFrame:
    rows = np.asarray(rows, dtype=np.float64)
    frame = pd.DataFrame(rows, index=weekly_index(len(rows), start), columns=SECTORS)
    for name, values in (extra or {}).items():
        frame[name] = values
    return frame


def three_week_example() -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Week 1 identical order (IC 1), week 2 reversed (IC −1), week 3 two adjacent ranks swapped (IC 1 − 12/720)."""
    fwd_rows = np.array([[0.01, -0.02, 0.03, 0.005, -0.01, 0.02, 0.0, 0.015, -0.005],
                         [0.02, 0.01, -0.01, 0.03, -0.02, 0.0, 0.004, -0.003, 0.012],
                         [-0.01, 0.02, 0.01, 0.0, 0.03, -0.02, 0.025, 0.005, -0.015]])
    score_rows = np.empty_like(fwd_rows)
    score_rows[0] = 3.0 * fwd_rows[0] + 1.0
    score_rows[1] = -fwd_rows[1]
    ranks = sps.rankdata(fwd_rows[2])
    swapped = ranks.copy()
    i, j = int(np.flatnonzero(ranks == 4)[0]), int(np.flatnonzero(ranks == 5)[0])
    swapped[i], swapped[j] = ranks[j], ranks[i]
    score_rows[2] = swapped
    fwd = sector_frame(fwd_rows, extra={"IVV": [0.5, -0.5, 0.9], "SPY": [-0.7, 0.3, 0.1]})
    scores = sector_frame(score_rows)
    return scores, fwd, np.array([1.0, -1.0, 1.0 - 6 * 2 / (9 * 80)])


def test_weekly_rank_ic_hand_three_weeks():
    """ICs of the three hand weeks are 1, −1 and 0.98333, equal to scipy's spearmanr; IVV and SPY are ignored."""
    scores, fwd, expected = three_week_example()
    ic = stats.weekly_rank_ic(scores, fwd)
    assert ic.name == "rank_ic"
    assert ic.index.equals(scores.index)
    np.testing.assert_allclose(ic.to_numpy(), expected, rtol=0, atol=1e-12)
    for t in range(3):
        rho = sps.spearmanr(scores.iloc[t].to_numpy(), fwd[SECTORS].iloc[t].to_numpy()).statistic
        assert ic.iloc[t] == pytest.approx(rho, abs=1e-12)


def test_weekly_rank_ic_identical_and_opposite_scores():
    """Scores equal to the forward returns give IC 1 every week; their negatives give −1."""
    rng = np.random.default_rng(4)
    fwd = sector_frame(rng.normal(0, 0.02, (30, 9)))
    np.testing.assert_allclose(stats.weekly_rank_ic(fwd.copy(), fwd).to_numpy(), np.ones(30), atol=1e-12)
    np.testing.assert_allclose(stats.weekly_rank_ic(-fwd, fwd).to_numpy(), -np.ones(30), atol=1e-12)


def test_weekly_rank_ic_uses_average_ranks_for_ties():
    """Tied scores get average ranks: the IC equals the Pearson correlation of average ranks."""
    scores = sector_frame([[1.0, 1.0, 2.0, 3.0, 3.0, 3.0, 0.0, 5.0, 4.0]])
    fwd = sector_frame([[0.01, 0.02, 0.0, 0.03, -0.01, 0.04, -0.02, 0.05, 0.015]])
    expected = np.corrcoef(sps.rankdata(scores.iloc[0]), sps.rankdata(fwd.iloc[0]))[0, 1]
    assert stats.weekly_rank_ic(scores, fwd).iloc[0] == pytest.approx(expected, abs=1e-12)


def test_weekly_rank_ic_skips_incomplete_and_constant_weeks():
    """Weeks with a non-finite pair, constant scores or constant returns are left out of the output."""
    rng = np.random.default_rng(5)
    fwd = sector_frame(rng.normal(0, 0.02, (6, 9)))
    scores = sector_frame(rng.normal(0, 1, (6, 9)))
    scores.iloc[1, 3] = np.nan
    fwd.iloc[2, 0] = np.inf
    scores.iloc[3] = 0.7
    fwd.iloc[4] = 0.001
    ic = stats.weekly_rank_ic(scores, fwd)
    assert list(ic.index) == [scores.index[0], scores.index[5]]
    for position, t in enumerate((0, 5)):
        rho = sps.spearmanr(scores.iloc[t].to_numpy(), fwd.iloc[t].to_numpy()).statistic
        assert ic.iloc[position] == pytest.approx(rho, abs=1e-12)


def test_weekly_rank_ic_aligns_returns_on_the_scores_index():
    """fwd covering more weeks than the scores is aligned on the scores' index (row t with row t)."""
    rng = np.random.default_rng(6)
    fwd = sector_frame(rng.normal(0, 0.02, (10, 9)), extra={"IVV": 0.0, "SPY": 0.0})
    scores = sector_frame(rng.normal(0, 1, (4, 9)), start=str(fwd.index.get_level_values("date_close")[3].date()))
    ic = stats.weekly_rank_ic(scores, fwd)
    assert ic.index.equals(scores.index)
    for t in range(4):
        rho = sps.spearmanr(scores.iloc[t].to_numpy(), fwd[SECTORS].iloc[t + 3].to_numpy()).statistic
        assert ic.iloc[t] == pytest.approx(rho, abs=1e-12)


def hac_loop(x: np.ndarray, lags: int) -> float:
    n = len(x)
    d = x - x.mean()
    lrv = sum(d[t] * d[t] for t in range(n)) / n
    for lag in range(1, lags + 1):
        gamma = sum(d[t] * d[t - lag] for t in range(lag, n)) / n
        lrv += 2 * (1 - lag / (lags + 1)) * gamma
    return lrv / n


def test_rank_ic_hand_three_weeks_with_default_lags():
    """Mean of the three ICs, Newey-West lags = floor(4·0.03^(2/9)) = 1, HAC se from an explicit loop, t = mean / se."""
    scores, fwd, ics = three_week_example()
    out = stats.rank_ic(scores, fwd)
    assert set(out) == {"mean", "hac_se", "t_stat", "n_weeks", "lags"}
    assert out["n_weeks"] == 3
    assert out["lags"] == 1
    assert out["mean"] == pytest.approx(ics.mean(), abs=1e-12)
    se = math.sqrt(hac_loop(ics, 1))
    assert out["hac_se"] == pytest.approx(se, rel=1e-10)
    assert out["t_stat"] == pytest.approx(ics.mean() / se, rel=1e-10)


def test_rank_ic_explicit_lags_on_random_weeks():
    """With lags given, hac_se = sqrt(HAC variance of the mean at those lags) of the weekly ICs."""
    rng = np.random.default_rng(8)
    fwd = sector_frame(rng.normal(0, 0.02, (60, 9)))
    scores = sector_frame(fwd.to_numpy() + rng.normal(0, 0.03, (60, 9)))
    ics = stats.weekly_rank_ic(scores, fwd).to_numpy()
    out = stats.rank_ic(scores, fwd, lags=3)
    assert out["lags"] == 3 and out["n_weeks"] == 60
    assert out["mean"] == pytest.approx(ics.mean(), rel=1e-12)
    assert out["hac_se"] == pytest.approx(math.sqrt(hac_loop(ics, 3)), rel=1e-10)
    assert out["t_stat"] == pytest.approx(out["mean"] / out["hac_se"], rel=1e-12)
    default = stats.rank_ic(scores, fwd)
    assert default["lags"] == math.floor(4 * (60 / 100) ** (2 / 9))


# ---------------------------------------------------------------- expected maximum Sharpe, PSR, DSR


@pytest.mark.parametrize(("n_trials", "variance"), [(2, 0.5), (16, 0.01), (100, 1.0), (1000, 0.003)])
def test_expected_max_sharpe_formula(n_trials, variance):
    """sqrt(V)·((1 − γ) Φ⁻¹(1 − 1/N) + γ Φ⁻¹(1 − 1/(N e))) with γ the Euler-Mascheroni constant."""
    expected = math.sqrt(variance) * ((1 - EULER_GAMMA) * sps.norm.ppf(1 - 1 / n_trials)
                                      + EULER_GAMMA * sps.norm.ppf(1 - 1 / (n_trials * math.e)))
    assert stats.expected_max_sharpe(n_trials, variance) == pytest.approx(expected, rel=1e-12)


def test_expected_max_sharpe_one_trial_is_zero():
    """N = 1 gives SR0 = 0."""
    assert stats.expected_max_sharpe(1, 0.7) == 0.0


def test_expected_max_sharpe_approximates_the_maximum_of_100_normals():
    """N = 100, V = 1 is within 0.05 of E[max of 100 iid N(0,1)] ≈ 2.5076."""
    assert stats.expected_max_sharpe(100, 1.0) == pytest.approx(2.5076, abs=0.05)


def ref_psr(r: np.ndarray, benchmark: float) -> float:
    sr = r.mean() / r.std(ddof=1)
    g3 = sps.skew(r, bias=True)
    g4 = sps.kurtosis(r, fisher=False, bias=True)
    z = (sr - benchmark) * math.sqrt(len(r) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2)
    return float(sps.norm.cdf(z))


@pytest.fixture(scope="module")
def skewed_returns() -> pd.Series:
    rng = np.random.default_rng(12)
    r = rng.normal(0.002, 0.02, 300) + 0.02 * (rng.exponential(1.0, 300) - 1.0)
    return weekly_series(r)


@pytest.mark.parametrize("benchmark", [0.0, 0.05, -0.02])
def test_probabilistic_sharpe_ratio_formula(skewed_returns, benchmark):
    """PSR = Φ((SR − SR*)·sqrt(T−1) / sqrt(1 − γ3·SR + (γ4 − 1)/4·SR²)), weekly SR, population moments."""
    r = skewed_returns.to_numpy()
    assert sps.skew(r) > 0.2  # the skewness term matters in this example
    assert stats.probabilistic_sharpe_ratio(skewed_returns, benchmark) == pytest.approx(ref_psr(r, benchmark), rel=1e-10)


def test_probabilistic_sharpe_ratio_at_its_own_sharpe_is_one_half(skewed_returns):
    """With SR* equal to the sample weekly Sharpe the PSR is 0.5."""
    r = skewed_returns.to_numpy()
    sr = r.mean() / r.std(ddof=1)
    assert stats.probabilistic_sharpe_ratio(skewed_returns, sr) == pytest.approx(0.5, abs=1e-12)


def test_probabilistic_sharpe_ratio_default_benchmark_is_zero(skewed_returns):
    """benchmark_sharpe defaults to 0."""
    assert stats.probabilistic_sharpe_ratio(skewed_returns) == pytest.approx(ref_psr(skewed_returns.to_numpy(), 0.0),
                                                                             rel=1e-10)


@pytest.fixture(scope="module")
def trial_sharpes() -> pd.Series:
    return pd.Series([0.02, 0.05, -0.01, 0.08, 0.03, 0.04, 0.0, 0.06], name="sharpe")


def test_deflated_sharpe_ratio_is_psr_at_the_expected_maximum(skewed_returns, trial_sharpes):
    """DSR = PSR(returns, expected_max_sharpe(N, var(trial Sharpes, ddof=1)))."""
    variance = float(np.var(trial_sharpes.to_numpy(), ddof=1))
    for n_trials in (2, 16, 40):
        sr0 = math.sqrt(variance) * ((1 - EULER_GAMMA) * sps.norm.ppf(1 - 1 / n_trials)
                                     + EULER_GAMMA * sps.norm.ppf(1 - 1 / (n_trials * math.e)))
        expected = ref_psr(skewed_returns.to_numpy(), sr0)
        assert stats.deflated_sharpe_ratio(skewed_returns, n_trials, trial_sharpes) == pytest.approx(expected, rel=1e-10)


def test_deflated_sharpe_ratio_one_trial_is_the_psr(skewed_returns):
    """N = 1 gives the probabilistic Sharpe ratio against 0, with or without trial Sharpes."""
    psr = stats.probabilistic_sharpe_ratio(skewed_returns, 0.0)
    assert stats.deflated_sharpe_ratio(skewed_returns, 1) == pytest.approx(psr, rel=1e-12)
    assert stats.deflated_sharpe_ratio(skewed_returns, 1, None) == pytest.approx(psr, rel=1e-12)


def test_deflated_sharpe_ratio_needs_trial_sharpes_for_several_trials(skewed_returns):
    """N > 1 with no trial Sharpes, or fewer than two, raises ValueError."""
    with pytest.raises(ValueError):
        stats.deflated_sharpe_ratio(skewed_returns, 5)
    with pytest.raises(ValueError):
        stats.deflated_sharpe_ratio(skewed_returns, 5, None)
    with pytest.raises(ValueError):
        stats.deflated_sharpe_ratio(skewed_returns, 5, pd.Series([0.1]))


def test_deflated_sharpe_ratio_decreases_with_the_number_of_trials(skewed_returns, trial_sharpes):
    """More trials at a fixed positive variance give a lower DSR."""
    values = [stats.deflated_sharpe_ratio(skewed_returns, n, trial_sharpes) for n in (2, 5, 20, 100, 1000)]
    assert all(later < earlier for earlier, later in itertools.pairwise(values))


# ---------------------------------------------------------------- PBO by CSCV


def ref_logits(values: np.ndarray, n_blocks: int) -> np.ndarray:
    """Explicit CSCV loop (S31-9): drop the oldest T mod S rows, S equal blocks, all C(S, S/2) splits in order."""
    t, n = values.shape
    values = values[t % n_blocks:]
    size = len(values) // n_blocks
    blocks = [np.arange(b * size, (b + 1) * size) for b in range(n_blocks)]

    def sharpe(rows: np.ndarray) -> np.ndarray:
        sub = values[rows]
        sd = sub.std(axis=0, ddof=1)
        return np.where(sd > 0, sub.mean(axis=0) / np.where(sd > 0, sd, 1.0), np.nan)

    logits = []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_rows = np.concatenate([blocks[b] for b in combo])
        oos_rows = np.concatenate([blocks[b] for b in range(n_blocks) if b not in combo])
        s_is, s_oos = sharpe(is_rows), sharpe(oos_rows)
        filled = np.where(np.isnan(s_is), -np.inf, s_is)
        best = int(np.flatnonzero(filled == filled.max())[0])
        ranks = sps.rankdata(np.where(np.isnan(s_oos), -np.inf, s_oos), method="average")
        omega = ranks[best] / (n + 1)
        logits.append(math.log(omega / (1 - omega)))
    return np.array(logits)


def returns_frame(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(values, index=weekly_index(len(values)), columns=[f"c{j}" for j in range(values.shape[1])])


def test_cscv_logits_hand_case_four_blocks_two_columns():
    """n_blocks = 4, N = 2, T = 27 (3 oldest rows dropped): the 6 logits equal an explicit loop, in combinations order."""
    rng = np.random.default_rng(21)
    values = rng.normal(0.001, 0.02, (27, 2))
    values[:3] = 50.0  # dropped rows: any influence would show
    logits = stats.cscv_logits(returns_frame(values), n_blocks=4)
    expected = ref_logits(values, 4)
    assert len(logits) == 6
    np.testing.assert_allclose(np.asarray(logits, dtype=np.float64), expected, rtol=1e-12, atol=1e-12)
    assert stats.pbo_cscv(returns_frame(values), n_blocks=4) == pytest.approx(np.mean(expected <= 0), abs=1e-15)


def test_cscv_logits_match_the_loop_with_eight_blocks_and_a_constant_column():
    """n_blocks = 8, N = 5 with a constant column (NaN Sharpe ranks lowest): 70 logits equal the loop."""
    rng = np.random.default_rng(22)
    values = rng.normal(0.0, 0.02, (85, 5))
    values[:, 4] = 0.003
    logits = stats.cscv_logits(returns_frame(values), n_blocks=8)
    expected = ref_logits(values, 8)
    assert len(logits) == math.comb(8, 4)
    np.testing.assert_allclose(np.asarray(logits, dtype=np.float64), expected, rtol=1e-12, atol=1e-12)


def test_cscv_logits_default_has_12870_splits():
    """The default 16 blocks give C(16, 8) = 12,870 logits."""
    rng = np.random.default_rng(23)
    logits = stats.cscv_logits(returns_frame(rng.normal(0, 0.01, (64, 3))))
    assert len(logits) == 12870


def test_pbo_dominating_column_is_zero():
    """One column better than the others in every block gives PBO 0 (default 16 blocks)."""
    rng = np.random.default_rng(24)
    values = rng.normal(0.0, 0.01, (160, 6))
    values[:, 2] += 0.05
    assert stats.pbo_cscv(returns_frame(values)) == 0.0


def test_pbo_reversal_is_one():
    """Column B = −A with block means (4, 2, −1, −5): the In-Sample winner always loses Out-of-Sample, PBO 1."""
    rng = np.random.default_rng(25)
    means = np.repeat([0.04, 0.02, -0.01, -0.05], 10)
    a = means + rng.normal(0.0, 0.002, 40)
    values = np.column_stack([a, -a])
    logits = np.asarray(stats.cscv_logits(returns_frame(values), n_blocks=4), dtype=np.float64)
    np.testing.assert_allclose(logits, np.full(6, math.log(0.5)), atol=1e-12)
    assert stats.pbo_cscv(returns_frame(values), n_blocks=4) == 1.0


def test_pbo_iid_noise_is_near_one_half():
    """Many iid noise columns: PBO averaged over five seeds is near 0.5 and equals the loop seed by seed."""
    pbos = []
    for seed in range(5):
        values = np.random.default_rng(100 + seed).normal(0.0, 0.01, (400, 40))
        pbo = stats.pbo_cscv(returns_frame(values), n_blocks=10)
        assert pbo == pytest.approx(np.mean(ref_logits(values, 10) <= 0), abs=1e-12)
        pbos.append(pbo)
    assert 0.3 < np.mean(pbos) < 0.7


def test_pbo_refuses_bad_inputs():
    """Odd n_blocks, a single column, or fewer than 2·n_blocks rows raise ValueError."""
    rng = np.random.default_rng(26)
    with pytest.raises(ValueError):
        stats.pbo_cscv(returns_frame(rng.normal(size=(100, 3))), n_blocks=5)
    with pytest.raises(ValueError):
        stats.pbo_cscv(returns_frame(rng.normal(size=(100, 1))), n_blocks=4)
    with pytest.raises(ValueError):
        stats.pbo_cscv(returns_frame(rng.normal(size=(31, 3))), n_blocks=16)
    assert 0.0 <= stats.pbo_cscv(returns_frame(rng.normal(size=(32, 3))), n_blocks=16) <= 1.0


# ---------------------------------------------------------------- Ledoit-Wolf Sharpe difference


def bartlett(x: float) -> float:
    return max(0.0, 1.0 - abs(x))


def quadratic_spectral(x: float) -> float:
    if x == 0:
        return 1.0
    z = 6 * math.pi * x / 5
    return 25 / (12 * math.pi**2 * x**2) * (math.sin(z) / z - math.cos(z))


def lw_components(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    mu_a, mu_b = a.mean(), b.mean()
    g_a, g_b = (a**2).mean(), (b**2).mean()
    y = np.column_stack([a - mu_a, b - mu_b, a**2 - g_a, b**2 - g_b])
    return y, (mu_a, mu_b, g_a, g_b)


def andrews_bandwidth(y: np.ndarray) -> float:
    """Andrews (1991) AR(1) plug-in for the quadratic-spectral kernel, equal weights."""
    t = len(y)
    num = den = 0.0
    for c in range(y.shape[1]):
        z = y[:, c]
        rho = np.sum(z[1:] * z[:-1]) / np.sum(z[:-1] ** 2)
        sigma2 = np.mean((z[1:] - rho * z[:-1]) ** 2)
        num += 4 * rho**2 * sigma2**2 / (1 - rho) ** 8
        den += sigma2**2 / (1 - rho) ** 4
    return 1.3221 * (num / den * t) ** 0.2


def ref_lw(a: np.ndarray, b: np.ndarray, kernel: str, bandwidth: float | None) -> dict:
    """Ledoit-Wolf (2008) HAC test by explicit loops over lags and dates."""
    t = len(a)
    y, (mu_a, mu_b, g_a, g_b) = lw_components(a, b)
    if bandwidth is None:
        bandwidth = math.floor(4 * (t / 100) ** (2 / 9)) + 1 if kernel == "bartlett" else andrews_bandwidth(y)
    k = bartlett if kernel == "bartlett" else quadratic_spectral
    psi = np.zeros((4, 4))
    for t_ in range(t):
        psi += np.outer(y[t_], y[t_]) / t
    for j in range(1, t):
        weight = k(j / bandwidth)
        if weight == 0.0:
            continue
        gamma = np.zeros((4, 4))
        for t_ in range(j, t):
            gamma += np.outer(y[t_], y[t_ - j])
        gamma /= t
        psi += weight * (gamma + gamma.T)
    psi *= t / (t - 4)
    va, vb = g_a - mu_a**2, g_b - mu_b**2
    grad = np.array([g_a / va**1.5, -g_b / vb**1.5, -mu_a / (2 * va**1.5), mu_b / (2 * vb**1.5)])
    se = math.sqrt(grad @ psi @ grad / t)
    diff = mu_a / math.sqrt(va) - mu_b / math.sqrt(vb)
    z = diff / se
    return {"sharpe_a": mu_a / math.sqrt(va), "sharpe_b": mu_b / math.sqrt(vb), "difference": diff, "se": se, "z": z,
            "p_value": 2 * (1 - sps.norm.cdf(abs(z))), "bandwidth": bandwidth}


@pytest.fixture(scope="module")
def lw_pair() -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(31)
    common = rng.normal(0, 0.015, 60)
    a = weekly_series(0.003 + common + rng.normal(0, 0.01, 60))
    b = weekly_series(0.001 + 0.8 * common + rng.normal(0, 0.012, 60))
    return a, b


def assert_lw_close(out: dict, ref: dict) -> None:
    for key in ("sharpe_a", "sharpe_b", "difference", "se", "z", "p_value", "bandwidth"):
        assert out[key] == pytest.approx(ref[key], rel=1e-9, abs=1e-12), key


def test_sharpe_difference_bartlett_bandwidth_one_is_gamma_zero_only(lw_pair):
    """kernel = bartlett, bandwidth = 1: Ψ = T/(T−4)·Γ(0); every field equals the explicit computation."""
    a, b = lw_pair
    out = stats.sharpe_difference_test(a, b, kernel="bartlett", bandwidth=1)
    assert set(out) == {"sharpe_a", "sharpe_b", "difference", "difference_annual", "se", "z", "p_value", "bandwidth",
                        "n_weeks"}
    assert_lw_close(out, ref_lw(a.to_numpy(), b.to_numpy(), "bartlett", 1))
    assert out["n_weeks"] == 60


def test_sharpe_difference_bartlett_bandwidth_three(lw_pair):
    """kernel = bartlett, bandwidth = 3: lags 1 and 2 with weights 2/3 and 1/3."""
    a, b = lw_pair
    assert_lw_close(stats.sharpe_difference_test(a, b, kernel="bartlett", bandwidth=3),
                    ref_lw(a.to_numpy(), b.to_numpy(), "bartlett", 3))


def test_sharpe_difference_bartlett_default_bandwidth(lw_pair):
    """kernel = bartlett without bandwidth uses newey_west_lags(T) + 1."""
    a, b = lw_pair
    out = stats.sharpe_difference_test(a, b, kernel="bartlett")
    assert out["bandwidth"] == pytest.approx(math.floor(4 * 0.6 ** (2 / 9)) + 1)
    assert_lw_close(out, ref_lw(a.to_numpy(), b.to_numpy(), "bartlett", None))


def test_sharpe_difference_quadratic_spectral_default(lw_pair):
    """Default kernel: quadratic spectral with the Andrews (1991) AR(1) plug-in bandwidth."""
    a, b = lw_pair
    ref = ref_lw(a.to_numpy(), b.to_numpy(), "qs", None)
    out = stats.sharpe_difference_test(a, b)
    assert out["bandwidth"] == pytest.approx(andrews_bandwidth(lw_components(a.to_numpy(), b.to_numpy())[0]), rel=1e-10)
    assert_lw_close(out, ref)
    assert_lw_close(stats.sharpe_difference_test(a, b, kernel="qs"), ref)


def test_sharpe_difference_quadratic_spectral_explicit_bandwidth(lw_pair):
    """kernel = qs with an explicit bandwidth uses it as given."""
    a, b = lw_pair
    assert_lw_close(stats.sharpe_difference_test(a, b, kernel="qs", bandwidth=2.5),
                    ref_lw(a.to_numpy(), b.to_numpy(), "qs", 2.5))


def test_sharpe_difference_per_week_sharpes_and_annual_difference(lw_pair):
    """sharpe = μ/σ with σ the ddof-0 std; difference_annual = difference·√52; p = 2(1 − Φ(|z|))."""
    a, b = lw_pair
    out = stats.sharpe_difference_test(a, b)
    assert out["sharpe_a"] == pytest.approx(a.mean() / a.std(ddof=0), rel=1e-12)
    assert out["sharpe_b"] == pytest.approx(b.mean() / b.std(ddof=0), rel=1e-12)
    assert out["difference"] == pytest.approx(out["sharpe_a"] - out["sharpe_b"], rel=1e-12)
    assert out["difference_annual"] == pytest.approx(out["difference"] * math.sqrt(52), rel=1e-12)
    assert out["z"] == pytest.approx(out["difference"] / out["se"], rel=1e-12)
    assert out["p_value"] == pytest.approx(2 * (1 - sps.norm.cdf(abs(out["z"]))), rel=1e-12)


def test_sharpe_difference_identical_series_has_z_zero_and_p_one(lw_pair):
    """a == b: difference 0, z 0 and p-value 1, for both kernels."""
    a, _ = lw_pair
    for kernel in ("qs", "bartlett"):
        out = stats.sharpe_difference_test(a, a.copy(), kernel=kernel)
        assert out["difference"] == 0.0
        assert out["z"] == 0.0
        assert out["p_value"] == 1.0


def test_sharpe_difference_monte_carlo_standard_error_of_iid_normals():
    """Independent iid normals, T = 5000: se ≈ sqrt((2 + SRa²/2 + SRb²/2) / T) within 15%."""
    rng = np.random.default_rng(32)
    t = 5000
    a = weekly_series(rng.normal(0.05, 1.0, t), start="1920-01-02")
    b = weekly_series(rng.normal(0.02, 1.0, t), start="1920-01-02")
    out = stats.sharpe_difference_test(a, b)
    sr_a, sr_b = out["sharpe_a"], out["sharpe_b"]
    expected = math.sqrt((1 + sr_a**2 / 2 + 1 + sr_b**2 / 2) / t)
    assert out["se"] == pytest.approx(expected, rel=0.15)
    assert out["n_weeks"] == t


# ---------------------------------------------------------------- selection gate


@pytest.fixture(scope="module")
def gate_series() -> dict[str, pd.Series]:
    rng = np.random.default_rng(7)
    m0 = weekly_series(rng.normal(0.001, 0.005, 200))
    strong = m0 + 0.004
    deep = strong.copy()
    deep.iloc[100:105] = -0.04
    return {"m0": m0, "equal": m0.copy(), "strong": strong, "deep": deep}


def gate_entry(out: dict, name: str) -> dict:
    return next(c for c in out["candidates"] if c["name"] == name)


def test_selection_gate_picks_the_first_passing_candidate(gate_series):
    """M1 equal to M0 fails; M2 = M0 + 0.4% a week passes every criterion and is selected before M3 and ENS."""
    s = gate_series
    results = {"M1": s["equal"], "M2": s["strong"], "M3": s["strong"].copy(), "ENS": s["equal"].copy()}
    out = stats.selection_gate(results, s["m0"], CFG, rf=0.0, absent=("M5",))
    assert out["selected"] == "M2"
    assert [c["name"] for c in out["candidates"]] == list(CFG["models"]["candidate_order"])
    m1, m2 = gate_entry(out, "M1"), gate_entry(out, "M2")
    assert m1["status"] == "evaluated" and m2["status"] == "evaluated"
    assert set(m2) == CANDIDATE_KEYS
    assert not m1["passes_sharpe"] and not m1["passes_bootstrap"] and not m1["passes"]
    assert m2["passes_sharpe"] and m2["passes_mdd"] and m2["passes_bootstrap"] and m2["passes"]
    assert gate_entry(out, "M3")["passes"]  # evaluated too, but M2 comes first


def test_selection_gate_reports_the_metrics_and_bootstrap_values(gate_series):
    """Sharpe, drawdown and both bootstrap probabilities equal metrics.* and paired_block_bootstrap (blocks 4 and 8)."""
    s = gate_series
    results = {"M1": s["equal"], "M2": s["strong"], "M3": s["deep"], "ENS": s["equal"].copy()}
    out = stats.selection_gate(results, s["m0"], CFG, rf=0.0, absent=("M5",))
    sel = CFG["selection"]
    for name, series in results.items():
        entry = gate_entry(out, name)
        assert entry["sharpe"] == pytest.approx(metrics.sharpe_ratio(series, 0.0), rel=1e-12)
        assert entry["sharpe_m0"] == pytest.approx(metrics.sharpe_ratio(s["m0"], 0.0), rel=1e-12)
        assert entry["mdd"] == pytest.approx(metrics.max_drawdown(series), rel=1e-12)
        assert entry["mdd_m0"] == pytest.approx(metrics.max_drawdown(s["m0"]), rel=1e-12)
        main = stats.paired_block_bootstrap(series, s["m0"], sel["bootstrap_resamples"], sel["bootstrap_block"],
                                            seed=CFG["seed"], rf=0.0)
        sens = stats.paired_block_bootstrap(series, s["m0"], sel["bootstrap_resamples"], sel["bootstrap_block_sensitivity"],
                                            seed=CFG["seed"], rf=0.0)
        assert entry["p_uplift_positive"] == pytest.approx(main["p_uplift_positive"], abs=1e-12)
        assert entry["p_uplift_positive_sensitivity"] == pytest.approx(sens["p_uplift_positive"], abs=1e-12)
        assert entry["passes_sharpe"] == (entry["sharpe"] >= entry["sharpe_m0"] + sel["sharpe_uplift"])
        assert entry["passes_mdd"] == (entry["mdd"] >= entry["mdd_m0"] - sel["mdd_tolerance"])
        assert entry["passes_bootstrap"] == (entry["p_uplift_positive"] >= sel["bootstrap_prob"])
        assert entry["passes"] == (entry["passes_sharpe"] and entry["passes_mdd"] and entry["passes_bootstrap"])


def test_selection_gate_all_equal_to_m0_falls_back_to_m0_star(gate_series):
    """Every candidate equal to M0: nothing passes and M0_star is selected."""
    s = gate_series
    results = {name: s["equal"].copy() for name in ("M1", "M2", "M3", "ENS")}
    out = stats.selection_gate(results, s["m0"], CFG, rf=0.0, absent=("M5",))
    assert out["selected"] == "M0_star"
    assert not any(c.get("passes", False) for c in out["candidates"])


def test_selection_gate_deep_drawdown_fails_the_drawdown_criterion(gate_series):
    """M1 with a higher Sharpe but a drawdown more than 2 points deeper than M0 fails passes_mdd."""
    s = gate_series
    deep, m0 = s["deep"], s["m0"]
    assert metrics.sharpe_ratio(deep, 0.0) >= metrics.sharpe_ratio(m0, 0.0) + 0.15
    assert metrics.max_drawdown(deep) < metrics.max_drawdown(m0) - 0.02
    results = {"M1": deep, "M2": s["equal"], "M3": s["equal"].copy(), "ENS": s["equal"].copy()}
    out = stats.selection_gate(results, m0, CFG, rf=0.0, absent=("M5",))
    m1 = gate_entry(out, "M1")
    assert m1["passes_sharpe"] and not m1["passes_mdd"] and not m1["passes"]
    assert out["selected"] == "M0_star"


def test_selection_gate_reports_absent_candidates(gate_series):
    """A candidate named in absent is reported with status 'absent' in its config position."""
    s = gate_series
    results = {"M1": s["equal"], "M2": s["equal"].copy(), "M3": s["equal"].copy(), "ENS": s["equal"].copy()}
    out = stats.selection_gate(results, s["m0"], CFG, rf=0.0, absent=("M5",))
    names = [c["name"] for c in out["candidates"]]
    assert names == ["M1", "M2", "M3", "M5", "ENS"]
    assert gate_entry(out, "M5")["status"] == "absent"


def test_selection_gate_missing_candidate_raises(gate_series):
    """A candidate missing from the results and not named absent raises ValueError."""
    s = gate_series
    results = {"M1": s["equal"], "M2": s["equal"].copy(), "ENS": s["equal"].copy()}
    with pytest.raises(ValueError):
        stats.selection_gate(results, s["m0"], CFG, rf=0.0, absent=("M5",))
    with pytest.raises(ValueError):
        stats.selection_gate({**results, "M3": s["equal"].copy()}, s["m0"], CFG, rf=0.0)


def test_selection_gate_requires_rf_keyword(gate_series):
    """rf has no default: calling without it raises TypeError."""
    s = gate_series
    results = {name: s["equal"].copy() for name in ("M1", "M2", "M3", "ENS")}
    with pytest.raises(TypeError):
        stats.selection_gate(results, s["m0"], CFG, absent=("M5",))


def test_selection_gate_refuses_a_different_index(gate_series):
    """A candidate series not on M0's index raises ValueError."""
    s = gate_series
    shifted = weekly_series(s["strong"].to_numpy(), start="2010-01-15")
    results = {"M1": shifted, "M2": s["equal"].copy(), "M3": s["equal"].copy(), "ENS": s["equal"].copy()}
    with pytest.raises(ValueError):
        stats.selection_gate(results, s["m0"], CFG, rf=0.0, absent=("M5",))


def test_selection_gate_with_a_weekly_rf_series(gate_series):
    """With a weekly rf series the Sharpes use metrics.sharpe_ratio(r, rf) and the bootstrap resamples rf."""
    s = gate_series
    rf = pd.Series(np.full(len(s["m0"]), 0.0004), index=s["m0"].index, name="rf")
    results = {"M1": s["strong"], "M2": s["equal"].copy(), "M3": s["equal"].copy(), "ENS": s["equal"].copy()}
    out = stats.selection_gate(results, s["m0"], CFG, rf=rf, absent=("M5",))
    m1 = gate_entry(out, "M1")
    assert m1["sharpe"] == pytest.approx(metrics.sharpe_ratio(s["strong"], rf), rel=1e-12)
    assert m1["sharpe_m0"] == pytest.approx(metrics.sharpe_ratio(s["m0"], rf), rel=1e-12)
    boot = stats.paired_block_bootstrap(s["strong"], s["m0"], 5000, 4, seed=CFG["seed"], rf=rf)
    assert m1["p_uplift_positive"] == pytest.approx(boot["p_uplift_positive"], abs=1e-12)
    assert out["selected"] == "M1"


def test_selection_gate_reads_thresholds_from_cfg(gate_series):
    """A stricter sharpe_uplift in cfg makes the strong candidate fail."""
    s = gate_series
    cfg = copy.deepcopy(CFG)
    gap = metrics.sharpe_ratio(s["strong"], 0.0) - metrics.sharpe_ratio(s["m0"], 0.0)
    cfg["selection"]["sharpe_uplift"] = gap + 0.5
    results = {"M1": s["strong"], "M2": s["equal"].copy(), "M3": s["equal"].copy(), "ENS": s["equal"].copy()}
    out = stats.selection_gate(results, s["m0"], cfg, rf=0.0, absent=("M5",))
    assert not gate_entry(out, "M1")["passes_sharpe"]
    assert out["selected"] == "M0_star"


def test_deflated_sharpe_ratio_from_trial_returns_uses_weekly_sharpes():
    """S31-12: trial_returns gives the same DSR as the weekly (mean/std, ddof=1) Sharpes of its columns."""
    rng = np.random.default_rng(3)
    trials = pd.DataFrame(rng.normal(0.001, 0.02, (300, 6)), columns=[f"t{i}" for i in range(6)])
    returns = pd.Series(rng.normal(0.002, 0.02, 300))
    weekly = trials.mean() / trials.std(ddof=1)
    expected = stats.deflated_sharpe_ratio(returns, 16, weekly)
    assert stats.deflated_sharpe_ratio(returns, 16, trial_returns=trials) == pytest.approx(expected, rel=1e-12)
    with pytest.raises(ValueError):
        stats.deflated_sharpe_ratio(returns, 16, weekly, trial_returns=trials)


def test_paired_block_bootstrap_reindexes_a_longer_weekly_rf_series():
    """A weekly rf series covering more weeks than the returns is cut to their weeks, as in src.metrics."""
    rng = np.random.default_rng(4)
    closes = pd.date_range("2010-01-08", periods=120, freq="7D")
    weeks = pd.MultiIndex.from_arrays([closes - pd.Timedelta(days=4), closes], names=["date_open", "date_close"])
    a = pd.Series(rng.normal(0.002, 0.02, 120), index=weeks)
    b = pd.Series(rng.normal(0.001, 0.02, 120), index=weeks)
    long_closes = pd.date_range("2009-01-09", periods=200, freq="7D")
    long_weeks = pd.MultiIndex.from_arrays([long_closes - pd.Timedelta(days=4), long_closes],
                                           names=["date_open", "date_close"])
    rf_long = pd.Series(0.0004, index=long_weeks)
    out = stats.paired_block_bootstrap(a, b, 200, 4, 1, rf=rf_long)
    same = stats.paired_block_bootstrap(a, b, 200, 4, 1, rf=rf_long.reindex(weeks))
    assert out == same
    with pytest.raises(ValueError):
        stats.paired_block_bootstrap(a, b, 200, 4, 1, rf=rf_long.iloc[:60])


def test_selection_gate_uses_the_headline_rf_and_reports_the_zero_cost_sharpe_alongside():
    """Amendment 6 C1 (S31-13): the criterion uses sharpe_ratio(r, rf) with the weekly T-bill series; the zero-cost
    Sharpe is reported alongside and decides nothing.
    """
    rng = np.random.default_rng(11)
    closes = pd.date_range("2010-01-08", periods=200, freq="7D")
    weeks = pd.MultiIndex.from_arrays([closes - pd.Timedelta(days=4), closes], names=["date_open", "date_close"])
    m0 = pd.Series(rng.normal(0.0005, 0.02, 200), index=weeks)
    results = {name: pd.Series(rng.normal(0.001, 0.02, 200), index=weeks) for name in ["M1", "M2", "M3", "ENS"]}
    rf = pd.Series(0.0006, index=weeks)
    out = stats.selection_gate(results, m0, CFG, rf=rf, absent=("M5",))
    for entry in out["candidates"]:
        if entry["status"] != "evaluated":
            continue
        r = results[entry["name"]]
        assert entry["sharpe"] == pytest.approx(metrics.sharpe_ratio(r, rf), rel=1e-12)
        assert entry["sharpe_zero_cost"] == pytest.approx(metrics.sharpe_ratio(r, 0.0), rel=1e-12)
        assert entry["sharpe_m0_zero_cost"] == pytest.approx(metrics.sharpe_ratio(m0, 0.0), rel=1e-12)
        assert entry["passes_sharpe"] == (entry["sharpe"] >= entry["sharpe_m0"] + CFG["selection"]["sharpe_uplift"])

