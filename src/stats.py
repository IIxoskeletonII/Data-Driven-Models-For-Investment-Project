"""Inference of protocol section 11 (and the §07 gate): paired stationary block bootstrap, HAC rank IC, Ledoit-Wolf
Sharpe test, Deflated Sharpe Ratio, PBO by CSCV and the selection rule.

Phase 3.1 (Eliya); decisions S31-7 to S31-9. Interfaces: docs/interfaces.md, contract 16. Every input is a weekly series
or frame on the weekly index (date_open, date_close); returns are decimal net weekly returns, P = 52 per year.
"""

import itertools
import math
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats as sps

from src.config import load_config
from src.contracts import universe
from src.metrics import max_drawdown, sharpe_ratio

EULER_GAMMA = 0.5772156649015329
FALLBACK = "M0_star"  # §07 step 5: traded when no candidate passes the gate


def _cfg(cfg: dict | None) -> dict:
    return load_config() if cfg is None else cfg


def _periods_per_year(cfg: dict | None = None) -> int:
    return int(_cfg(cfg)["metrics"]["periods_per_year"])


# -- stationary bootstrap (§07, §11) -------------------------------------------------------------------------------------


def stationary_bootstrap_indices(n: int, n_resamples: int, block: float, rng: np.random.Generator) -> np.ndarray:
    """Politis and Romano (1994) stationary bootstrap indices, shape (n_resamples, n), int64 in [0, n).

    The first index of each resample is uniform; each later index starts a new block (a new uniform draw) with
    probability 1/block, else continues the previous one with wrap-around ((previous + 1) mod n). Block lengths are
    geometric with mean `block` weeks.
    """
    if n < 1 or n_resamples < 1:
        raise ValueError("stationary_bootstrap_indices: n and n_resamples must be positive")
    if block < 1:
        raise ValueError(f"stationary_bootstrap_indices: the mean block length must be at least 1, got {block}")
    starts = rng.integers(0, n, size=(n_resamples, n))
    new_block = rng.random((n_resamples, n)) < 1.0 / block
    new_block[:, 0] = True
    indices = np.empty((n_resamples, n), dtype=np.int64)
    indices[:, 0] = starts[:, 0]
    for t in range(1, n):
        indices[:, t] = np.where(new_block[:, t], starts[:, t], (indices[:, t - 1] + 1) % n)
    return indices


def _sharpe_rows(r: np.ndarray, rf_annual: np.ndarray | float, periods: int) -> np.ndarray:
    """Skeleton Sharpe per row of r (resamples × weeks): ((Π(1+r))^(P/T) − 1 − rf) / (std(ddof=1)·√P); NaN if std = 0."""
    t = r.shape[1]
    annual = np.prod(1.0 + r, axis=1) ** (periods / t) - 1.0
    vol = r.std(axis=1, ddof=1) * math.sqrt(periods)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(vol > 0, (annual - rf_annual) / vol, np.nan)


def _aligned(candidate: pd.Series, baseline: pd.Series, rf) -> tuple[np.ndarray, np.ndarray, np.ndarray | float | None]:
    if not candidate.index.equals(baseline.index):
        raise ValueError("paired series must share the same weekly index")
    a, b = candidate.to_numpy(dtype=np.float64), baseline.to_numpy(dtype=np.float64)
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError("paired series must not contain missing or infinite values")
    if isinstance(rf, pd.Series):
        rf = rf.reindex(candidate.index).to_numpy(dtype=np.float64)  # as src.metrics: the weeks of the returns
        if not np.isfinite(rf).all():
            raise ValueError("the weekly risk-free series has no value for some weeks of the return series")
    elif rf is not None:
        rf = float(rf)
    return a, b, rf


def _annual_rf(rf: np.ndarray | float | None, rows: np.ndarray | None, periods: int) -> np.ndarray | float:
    """Annual rf per resample: 0 (zero-cost), a constant, or the compound average of the resampled weekly series."""
    if rf is None:
        return 0.0
    if isinstance(rf, float):
        return rf
    weekly = rf[rows] if rows is not None else rf[None, :]
    return np.prod(1.0 + weekly, axis=1) ** (periods / weekly.shape[1]) - 1.0


def paired_block_bootstrap(candidate: pd.Series, baseline: pd.Series, n_resamples: int = 5000, block: int = 4,
                           seed: int = 42, *, rf: pd.Series | float | None = None,
                           confidence: float | None = None) -> dict[str, float]:
    """Paired stationary block bootstrap of the Sharpe uplift candidate − baseline (§07, §11, S31-8).

    candidate, baseline: weekly net returns on the same weekly index. One set of stationary-bootstrap indices (mean block
    `block` weeks: 4, sensitivity 8; `n_resamples` 5,000; numpy default_rng(seed)) resamples both series (and a weekly rf
    series, if given). Sharpe = (annualised return − rf) / annualised volatility, as src.metrics.sharpe_ratio; rf None
    means 0 (zero-cost convention), a float is an annual rate. Returns "uplift" (observed Sharpe difference), "lower",
    "upper" (percentile interval at `confidence`, default inference.confidence = 0.95), "p_uplift_positive" (share of resamples
    with uplift > 0), "mean_diff" with "mean_diff_lower"/"mean_diff_upper" (mean weekly difference, decimal),
    "n_weeks", "block", "n_resamples".
    """
    a, b, rf_values = _aligned(candidate, baseline, rf)
    confidence = float(_cfg(None)["inference"]["confidence"] if confidence is None else confidence)
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    periods = _periods_per_year()
    n = len(a)
    if n < 2:
        raise ValueError("paired_block_bootstrap: at least two weeks are needed")
    rows = stationary_bootstrap_indices(n, int(n_resamples), float(block), np.random.default_rng(seed))
    rf_observed = _annual_rf(rf_values, None, periods)
    rf_resampled = _annual_rf(rf_values, rows, periods)
    observed = float(_sharpe_rows(a[None, :], rf_observed, periods)[0] - _sharpe_rows(b[None, :], rf_observed, periods)[0])
    uplift = _sharpe_rows(a[rows], rf_resampled, periods) - _sharpe_rows(b[rows], rf_resampled, periods)
    diff = (a - b)[rows].mean(axis=1)
    tail = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(uplift, [tail, 1.0 - tail])
    diff_lower, diff_upper = np.quantile(diff, [tail, 1.0 - tail])
    return {"uplift": observed, "lower": float(lower), "upper": float(upper), "p_uplift_positive": float(np.mean(uplift > 0)),
            "mean_diff": float(np.mean(a - b)), "mean_diff_lower": float(diff_lower), "mean_diff_upper": float(diff_upper),
            "n_weeks": float(n), "block": float(block), "n_resamples": float(n_resamples)}


# -- HAC rank IC (§11) ---------------------------------------------------------------------------------------------------


def newey_west_lags(n: int) -> int:
    """Newey and West (1994) lag rule: floor(4 · (n / 100)^(2/9)) (S31-9)."""
    if n < 1:
        raise ValueError("newey_west_lags: n must be positive")
    return math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))


def hac_variance_of_mean(x: np.ndarray, lags: int) -> float:
    """Newey-West (Bartlett) variance of the sample mean: (γ0 + 2 Σ_{l=1..L} (1 − l/(L+1)) γ_l) / n, with
    γ_l = (1/n) Σ_t (x_t − x̄)(x_{t−l} − x̄).
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 1 or lags < 0:
        raise ValueError("hac_variance_of_mean: need at least one value and lags >= 0")
    e = x - x.mean()
    long_run = float(e @ e) / n
    for lag in range(1, min(lags, n - 1) + 1):
        long_run += 2.0 * (1.0 - lag / (lags + 1.0)) * float(e[lag:] @ e[:-lag]) / n
    return long_run / n


def weekly_rank_ic(scores: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    """Weekly Spearman rank IC (S31-9): per week t, the correlation of the average ranks of the 9 sector scores (known
    after Friday close t) and of their forward returns of contract 7 (realised at O(t+2)), on the scores' weekly index.
    Weeks without all 9 pairs finite, or with constant scores or returns, are skipped. Series named "rank_ic".
    """
    sectors = list(universe().sectors)
    missing = [ticker for ticker in sectors if ticker not in scores.columns or ticker not in fwd.columns]
    if missing:
        raise ValueError(f"weekly_rank_ic: scores and fwd need the sector columns, missing {missing}")
    s = scores[sectors].to_numpy(dtype=np.float64)
    r = fwd[sectors].reindex(scores.index).to_numpy(dtype=np.float64)
    keep = np.isfinite(s).all(axis=1) & np.isfinite(r).all(axis=1)
    keep &= (np.ptp(np.where(np.isfinite(s), s, 0), axis=1) > 0) & (np.ptp(np.where(np.isfinite(r), r, 0), axis=1) > 0)
    rank_s = sps.rankdata(s[keep], axis=1)
    rank_r = sps.rankdata(r[keep], axis=1)
    rank_s -= rank_s.mean(axis=1, keepdims=True)
    rank_r -= rank_r.mean(axis=1, keepdims=True)
    ic = (rank_s * rank_r).sum(axis=1) / np.sqrt((rank_s ** 2).sum(axis=1) * (rank_r ** 2).sum(axis=1))
    return pd.Series(ic, index=scores.index[keep], name="rank_ic", dtype=np.float64)


def rank_ic(scores: pd.DataFrame, fwd: pd.DataFrame, lags: int | None = None) -> dict[str, float]:
    """Mean weekly Spearman rank IC with its Newey-West HAC standard error and t-statistic (§11, S31-9).

    scores: weekly score frame (contract 8), known after Friday close t; fwd: forward returns of contract 7 on the same
    weekly index. lags None uses newey_west_lags(number of weekly ICs). Returns "mean", "hac_se", "t_stat", "n_weeks",
    "lags".
    """
    ic = weekly_rank_ic(scores, fwd).to_numpy()
    n = len(ic)
    if n < 2:
        raise ValueError("rank_ic: fewer than two weeks with a rank IC")
    lags = newey_west_lags(n) if lags is None else int(lags)
    se = math.sqrt(hac_variance_of_mean(ic, lags))
    mean = float(ic.mean())
    return {"mean": mean, "hac_se": se, "t_stat": mean / se if se > 0 else float("nan"), "n_weeks": float(n),
            "lags": float(lags)}


# -- Deflated Sharpe Ratio (§10, §11) ------------------------------------------------------------------------------------


def expected_max_sharpe(n_trials: int, variance: float) -> float:
    """Expected maximum Sharpe of N unskilled trials (Bailey and López de Prado 2014): √V · ((1 − γ) Φ⁻¹(1 − 1/N) +
    γ Φ⁻¹(1 − 1/(N e))), γ the Euler-Mascheroni constant; 0 for N = 1. Units of the trial Sharpes (weekly).
    """
    if n_trials < 1:
        raise ValueError("expected_max_sharpe: n_trials must be at least 1")
    if variance < 0:
        raise ValueError("expected_max_sharpe: variance must be non-negative")
    if n_trials == 1:
        return 0.0
    z1 = sps.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = sps.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(math.sqrt(variance) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def probabilistic_sharpe_ratio(returns: pd.Series, benchmark_sharpe: float = 0.0) -> float:
    """Probabilistic Sharpe ratio: Φ((SR − SR*) √(T − 1) / √(1 − γ3 SR + (γ4 − 1)/4 SR²)), with the weekly Sharpe
    SR = mean / std (ddof=1), sample skewness γ3 and Pearson kurtosis γ4 (population moments), T weeks (S31-9).
    """
    r = pd.Series(returns).to_numpy(dtype=np.float64)
    if len(r) < 3 or not np.isfinite(r).all():
        raise ValueError("probabilistic_sharpe_ratio: need at least three finite weekly returns")
    std = r.std(ddof=1)
    if std == 0:
        raise ValueError("probabilistic_sharpe_ratio: the returns have zero variance")
    sr = r.mean() / std
    skew = sps.skew(r, bias=True)
    kurt = sps.kurtosis(r, fisher=False, bias=True)
    denominator = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if denominator <= 0:
        raise ValueError("probabilistic_sharpe_ratio: non-positive variance term")
    return float(sps.norm.cdf((sr - benchmark_sharpe) * math.sqrt(len(r) - 1) / math.sqrt(denominator)))


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int, trial_sharpes: pd.Series | None = None, *,
                          trial_returns: pd.DataFrame | None = None) -> float:
    """Deflated Sharpe Ratio (Bailey and López de Prado 2014; §10, §11, S31-7, S31-9): the probabilistic Sharpe ratio
    of the weekly returns against SR₀ = expected_max_sharpe(N, V), with N = n_trials (every row of docs/trial_log.csv)
    and V the sample variance (ddof=1) of the trials' Sharpes. N = 1 gives SR₀ = 0.

    The trial Sharpes are PER WEEK, mean / std (ddof=1), never annualised (the annualised is_sharpe of the trial log
    would inflate SR₀ by √52): pass `trial_returns` (weekly net returns, one column per trial, e.g. the PBO matrix), from
    which they are computed, or `trial_sharpes` already in weekly units (S31-12).
    """
    n_trials = int(n_trials)
    if trial_returns is not None:
        if trial_sharpes is not None:
            raise ValueError("deflated_sharpe_ratio: pass trial_returns or trial_sharpes, not both")
        trial_sharpes = pd.Series(_column_sharpes(trial_returns.to_numpy(dtype=np.float64)), index=trial_returns.columns)
    if n_trials == 1:
        return probabilistic_sharpe_ratio(returns, 0.0)
    if trial_sharpes is None or len(trial_sharpes) < 2:
        raise ValueError("deflated_sharpe_ratio: N > 1 needs the weekly Sharpes of at least two trials")
    values = pd.Series(trial_sharpes).to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("deflated_sharpe_ratio: trial Sharpes must be finite")
    return probabilistic_sharpe_ratio(returns, expected_max_sharpe(n_trials, float(values.var(ddof=1))))


# -- PBO by CSCV (§10, §11) ----------------------------------------------------------------------------------------------


def _column_sharpes(block: np.ndarray) -> np.ndarray:
    mean = block.mean(axis=0)
    std = block.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(std > 0, mean / std, np.nan)


def cscv_logits(returns: pd.DataFrame, n_blocks: int = 16) -> np.ndarray:
    """Logits λ of combinatorially symmetric cross-validation (Bailey, Borwein, López de Prado and Zhu 2017; S31-9).

    returns: In-Sample weekly net returns, one column per configuration. The oldest T mod n_blocks weeks are dropped; the
    rest is cut into n_blocks contiguous equal blocks. For each choice of n_blocks/2 blocks as In-Sample (in
    itertools.combinations order), the configuration with the highest In-Sample Sharpe (mean/std, ddof=1; first column on
    ties) gets ω = rank of its Out-of-Sample Sharpe among all columns (average ranks, 1 = lowest, NaN lowest) / (N + 1),
    and λ = ln(ω / (1 − ω)).
    """
    values = returns.to_numpy(dtype=np.float64)
    t, n = values.shape
    if n_blocks < 2 or n_blocks % 2:
        raise ValueError(f"cscv_logits: n_blocks must be even and at least 2, got {n_blocks}")
    if n < 2:
        raise ValueError("cscv_logits: at least two configurations are needed")
    if t < 2 * n_blocks:
        raise ValueError(f"cscv_logits: {t} weeks are too few for {n_blocks} blocks")
    if not np.isfinite(values).all():
        raise ValueError("cscv_logits: returns must not contain missing values")
    size = t // n_blocks
    blocks = values[t - size * n_blocks:].reshape(n_blocks, size, n)
    logits = []
    for chosen in itertools.combinations(range(n_blocks), n_blocks // 2):
        other = [b for b in range(n_blocks) if b not in chosen]
        sharpe_in = _column_sharpes(blocks[list(chosen)].reshape(-1, n))
        sharpe_out = _column_sharpes(blocks[other].reshape(-1, n))
        winner = int(np.argmax(np.where(np.isnan(sharpe_in), -np.inf, sharpe_in)))
        ranks = sps.rankdata(np.where(np.isnan(sharpe_out), -np.inf, sharpe_out), method="average")
        omega = ranks[winner] / (n + 1.0)
        logits.append(math.log(omega / (1.0 - omega)))
    return np.asarray(logits, dtype=np.float64)


def pbo_cscv(returns: pd.DataFrame, n_blocks: int = 16) -> float:
    """Probability of backtest overfitting (§10, §11): share of CSCV splits whose In-Sample winner ranks at or below the
    Out-of-Sample median (λ ≤ 0), with n_blocks = inference.pbo_blocks (16). A diagnostic; it never chooses the model.
    """
    return float(np.mean(cscv_logits(returns, n_blocks) <= 0))


# -- Ledoit-Wolf (2008) Sharpe difference test (§11) ---------------------------------------------------------------------


def _qs_kernel(x: np.ndarray) -> np.ndarray:
    """Quadratic-spectral kernel; k(0) = 1."""
    x = np.asarray(x, dtype=np.float64)
    out = np.ones_like(x)
    nz = x != 0
    z = 6.0 * math.pi * x[nz] / 5.0
    out[nz] = 25.0 / (12.0 * math.pi ** 2 * x[nz] ** 2) * (np.sin(z) / z - np.cos(z))
    return out


def _andrews_qs_bandwidth(y: np.ndarray) -> float:
    """Andrews (1991) AR(1) plug-in bandwidth for the QS kernel, equal weights over the columns of y; each AR(1)
    coefficient (OLS without intercept) is bounded to [-0.97, 0.97] so that a near-unit root cannot blow up the bandwidth.
    """
    numerator = denominator = 0.0
    for column in y.T:
        lagged, current = column[:-1], column[1:]
        rho = float(lagged @ current / (lagged @ lagged)) if lagged @ lagged > 0 else 0.0
        rho = min(max(rho, -0.97), 0.97)
        sigma2 = float(np.mean((current - rho * lagged) ** 2))
        numerator += 4.0 * rho ** 2 * sigma2 ** 2 / (1.0 - rho) ** 8
        denominator += sigma2 ** 2 / (1.0 - rho) ** 4
    alpha2 = numerator / denominator if denominator > 0 else 0.0
    return 1.3221 * (alpha2 * len(y)) ** 0.2


def sharpe_difference_test(a: pd.Series, b: pd.Series, *, kernel: str = "qs", bandwidth: float | None = None) -> dict[str, float]:
    """Ledoit and Wolf (2008) HAC test of SR_a − SR_b for two weekly return series on the same index (§11, S31-9).

    SR = μ / σ per week with σ² = E[r²] − μ². Delta method on (μ_a, μ_b, E[r_a²], E[r_b²]) with the HAC covariance
    Ψ = T/(T−4) · Σ_j k(j/S) Γ(j); kernel "qs" (quadratic spectral, S from Andrews 1991 when None) or "bartlett"
    (S = newey_west_lags(T) + 1 when None). Returns "sharpe_a", "sharpe_b", "difference", "difference_annual"
    (× √52), "se", "z", "p_value" (two-sided normal), "bandwidth", "n_weeks".
    """
    if not a.index.equals(b.index):
        raise ValueError("sharpe_difference_test: series must share the same weekly index")
    x, w = a.to_numpy(dtype=np.float64), b.to_numpy(dtype=np.float64)
    if not (np.isfinite(x).all() and np.isfinite(w).all()):
        raise ValueError("sharpe_difference_test: series must not contain missing values")
    t = len(x)
    if t < 6:
        raise ValueError("sharpe_difference_test: at least six weeks are needed")
    mu_a, mu_b = x.mean(), w.mean()
    g_a, g_b = np.mean(x ** 2), np.mean(w ** 2)
    var_a, var_b = g_a - mu_a ** 2, g_b - mu_b ** 2
    if var_a <= 0 or var_b <= 0:
        raise ValueError("sharpe_difference_test: a series has zero variance")
    sr_a, sr_b = mu_a / math.sqrt(var_a), mu_b / math.sqrt(var_b)
    y = np.column_stack([x - mu_a, w - mu_b, x ** 2 - g_a, w ** 2 - g_b])
    if kernel == "qs":
        s = _andrews_qs_bandwidth(y) if bandwidth is None else float(bandwidth)
        weight = lambda j: float(_qs_kernel(np.array([j / s]))[0]) if s > 0 else 0.0
    elif kernel == "bartlett":
        s = float(newey_west_lags(t) + 1) if bandwidth is None else float(bandwidth)
        weight = lambda j: max(0.0, 1.0 - j / s) if s > 0 else 0.0
    else:
        raise ValueError(f"sharpe_difference_test: kernel must be 'qs' or 'bartlett', got {kernel!r}")
    psi = y.T @ y / t
    for j in range(1, t):
        k = weight(j)
        if k == 0.0 and kernel == "bartlett":
            break
        gamma = y[j:].T @ y[:-j] / t
        psi += k * (gamma + gamma.T)
    psi *= t / (t - 4.0)
    gradient = np.array([g_a / var_a ** 1.5, -g_b / var_b ** 1.5, -mu_a / (2.0 * var_a ** 1.5), mu_b / (2.0 * var_b ** 1.5)])
    difference = sr_a - sr_b
    variance = float(gradient @ psi @ gradient) / t
    se = math.sqrt(variance) if variance > 0 else 0.0
    if se == 0.0:
        z = 0.0 if difference == 0 else math.copysign(math.inf, difference)
    else:
        z = difference / se
    p_value = float(2.0 * (1.0 - sps.norm.cdf(abs(z))))
    return {"sharpe_a": float(sr_a), "sharpe_b": float(sr_b), "difference": float(difference),
            "difference_annual": float(difference * math.sqrt(_periods_per_year())), "se": se, "z": float(z),
            "p_value": p_value, "bandwidth": float(s), "n_weeks": float(t)}


# -- the §07 selection gate ----------------------------------------------------------------------------------------------


def selection_gate(results: Mapping[str, pd.Series], m0: pd.Series, cfg: dict | None = None, *,
                   rf: pd.Series | float, absent: Sequence[str] = ()) -> dict:
    """The §07 selection rule on In-Sample walk-forward weekly net returns (S31-8).

    results: candidate name → weekly net returns of the test weeks (same weekly index as m0, the hurdle's). A candidate
    passes with Sharpe ≥ Sharpe(M0) + selection.sharpe_uplift, max drawdown ≥ M0's − selection.mdd_tolerance (drawdowns
    are negative), and paired block bootstrap P(uplift > 0) ≥ selection.bootstrap_prob (selection.bootstrap_resamples,
    block selection.bootstrap_block, seed config.seed; block selection.bootstrap_block_sensitivity reported as
    information). Sharpe is src.metrics.sharpe_ratio(r, rf), the §09 headline with rf the weekly FRED 3-month T-bill
    returns over the same weeks (Amendment 6 C1, S31-13; src.metrics.tbill_weekly_returns); rf stays a required keyword,
    and the zero-cost Sharpe (rf = 0) is reported alongside as information. Every name of models.candidate_order must be in results
    or in `absent` (e.g. M5 without approved agent features). Returns {"selected": the first passing candidate in
    order, else "M0_star", "candidates": one dict per candidate in order}.
    """
    cfg = _cfg(cfg)
    gate = cfg["selection"]
    order = list(cfg["models"]["candidate_order"])
    unknown = sorted(set(results) - set(order))
    if unknown:
        raise ValueError(f"selection_gate: {unknown} are not candidates of models.candidate_order {order}")
    missing = [name for name in order if name not in results and name not in absent]
    if missing:
        raise ValueError(f"selection_gate: no results for {missing}; name a candidate that does not exist in absent=")
    for name, series in results.items():
        if not series.index.equals(m0.index):
            raise ValueError(f"selection_gate: {name} and M0 must share the same weekly index")
    sharpe_m0, mdd_m0 = sharpe_ratio(m0, rf), max_drawdown(m0)
    sharpe_m0_zero_cost = sharpe_ratio(m0, 0.0)
    candidates, selected = [], None
    for name in order:
        if name not in results:
            candidates.append({"name": name, "status": "absent"})
            continue
        r = results[name]
        boot = paired_block_bootstrap(r, m0, gate["bootstrap_resamples"], gate["bootstrap_block"], int(cfg["seed"]), rf=rf)
        sensitivity = paired_block_bootstrap(r, m0, gate["bootstrap_resamples"], gate["bootstrap_block_sensitivity"],
                                             int(cfg["seed"]), rf=rf)
        sharpe, mdd = sharpe_ratio(r, rf), max_drawdown(r)
        row = {"name": name, "status": "evaluated", "sharpe": sharpe, "sharpe_m0": sharpe_m0, "mdd": mdd, "mdd_m0": mdd_m0,
               "p_uplift_positive": boot["p_uplift_positive"], "uplift_lower": boot["lower"], "uplift_upper": boot["upper"],
               "p_uplift_positive_sensitivity": sensitivity["p_uplift_positive"],
               "sharpe_zero_cost": sharpe_ratio(r, 0.0), "sharpe_m0_zero_cost": sharpe_m0_zero_cost,
               "passes_sharpe": bool(sharpe >= sharpe_m0 + gate["sharpe_uplift"]),
               "passes_mdd": bool(mdd >= mdd_m0 - gate["mdd_tolerance"]),
               "passes_bootstrap": bool(boot["p_uplift_positive"] >= gate["bootstrap_prob"])}
        row["passes"] = row["passes_sharpe"] and row["passes_mdd"] and row["passes_bootstrap"]
        if row["passes"] and selected is None:
            selected = name
        candidates.append(row)
    return {"selected": selected or FALLBACK, "candidates": candidates}
