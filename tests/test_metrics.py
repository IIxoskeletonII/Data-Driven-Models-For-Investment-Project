"""src/metrics.py against the course skeleton's docs/metrics.md, re-implemented independently below (P = 52).

Random weekly returns with seed 42; every metric must match the reference to 1e-12. Plus the edge cases of the skeleton
(starting capital as the first peak, NaN for a zero denominator, profit factor without losses), the T-bill conversion
with the one-session lag (Amendment 1) and the per-period metrics of one continuous book (Amendment 2 C5).
"""

import math

import numpy as np
import pandas as pd
import pytest

from src import metrics
from src.config import load_config

CFG = load_config()
P = CFG["metrics"]["periods_per_year"]
RF = CFG["metrics"]["risk_free_constant"]
TOL = 1e-12


def weeks(n: int, start: str = "2010-01-04") -> pd.MultiIndex:
    mondays = pd.date_range(start, periods=n, freq="7D")
    return pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])


# --- reference implementation, from the formulas of docs/metrics.md (plain Python on lists) ----------------------------

def ref_mean(x):
    return sum(x) / len(x)


def ref_std(x):  # sample standard deviation
    m = ref_mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def ref_ann(x):
    growth = 1.0
    for v in x:
        growth *= 1 + v
    return growth ** (P / len(x)) - 1


def ref_mdd(x):
    equity, peak, worst = 1.0, 1.0, 0.0
    for v in x:
        equity *= 1 + v
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
    return worst


def ref_skew(x):  # adjusted Fisher-Pearson sample skewness
    n, m, s = len(x), ref_mean(x), ref_std(x)
    return n / ((n - 1) * (n - 2)) * sum(((v - m) / s) ** 3 for v in x)


def ref_kurt(x):  # sample excess kurtosis
    n, m, s = len(x), ref_mean(x), ref_std(x)
    k4 = sum(((v - m) / s) ** 4 for v in x)
    return n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * k4 - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))


def ref_cov(x, y):
    mx, my = ref_mean(x), ref_mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)


@pytest.fixture
def returns():
    rng = np.random.default_rng(42)
    index = weeks(300)
    r = pd.Series(rng.normal(0.002, 0.02, 300), index=index)
    m = pd.Series(0.5 * r.to_numpy() + rng.normal(0.001, 0.02, 300), index=index)
    return r, m


def test_performance_matches_the_skeleton(returns):
    r, _ = returns
    x = r.tolist()
    got = metrics.performance(r, RF)
    ann, vol = ref_ann(x), ref_std(x) * math.sqrt(P)
    downside = math.sqrt(sum(min(v, 0) ** 2 for v in x) / len(x)) * math.sqrt(P)
    growth = 1.0
    for v in x:
        growth *= 1 + v
    expected = {
        "cumulative_return": growth - 1, "annualized_return": ann, "annualized_volatility": vol,
        "sharpe_rf": (ann - RF) / vol, "sharpe_zero_cost": ann / vol, "sharpe_textbook": math.sqrt(P) * ref_mean(x) / ref_std(x),
        "sortino_ratio": (ann - RF) / downside, "max_drawdown": ref_mdd(x), "calmar_ratio": ann / abs(ref_mdd(x)),
        "rf_annual": RF,
    }
    for key, value in expected.items():
        assert got[key] == pytest.approx(value, abs=TOL), key


def test_return_stats_match_the_skeleton(returns):
    r, _ = returns
    x = r.tolist()
    got = metrics.return_stats(r)
    gains, losses = [v for v in x if v > 0], [v for v in x if v < 0]
    expected = {
        "hit_rate": len(gains) / len(x), "avg_gain": ref_mean(gains), "avg_loss": ref_mean(losses),
        "profit_factor": sum(gains) / abs(sum(losses)), "best": max(x), "worst": min(x),
        "skew": ref_skew(x), "kurtosis": ref_kurt(x),
    }
    for key, value in expected.items():
        assert got[key] == pytest.approx(value, abs=TOL), key


def test_market_matches_the_skeleton(returns):
    r, m = returns
    x, y = r.tolist(), m.tolist()
    got = metrics.market(r, m, RF)
    beta = ref_cov(x, y) / ref_cov(y, y)
    te = ref_std([a - b for a, b in zip(x, y)]) * math.sqrt(P)
    sharpe = lambda z: (ref_ann(z) - RF) / (ref_std(z) * math.sqrt(P))
    expected = {
        "beta": beta, "correlation": ref_cov(x, y) / (ref_std(x) * ref_std(y)),
        "alpha": (ref_mean(x) - RF / P - beta * (ref_mean(y) - RF / P)) * P,
        "tracking_error": te, "information_ratio": (ref_mean(x) - ref_mean(y)) * P / te,
        "down_market": ref_mean([a for a, b in zip(x, y) if b < 0]), "up_market": ref_mean([a for a, b in zip(x, y) if b > 0]),
        "sharpe_vs_market": sharpe(x) - sharpe(y),
    }
    for key, value in expected.items():
        assert got[key] == pytest.approx(value, abs=TOL), key


def test_weekly_rf_series_conventions(returns):
    r, m = returns
    rf = pd.Series(np.linspace(0.0002, 0.0006, len(r)), index=r.index)
    rf_annual = ref_ann(rf.tolist())
    got = metrics.performance(r, rf)
    assert got["rf_annual"] == pytest.approx(rf_annual, abs=TOL)
    assert got["sharpe_rf"] == pytest.approx((ref_ann(r.tolist()) - rf_annual) / (ref_std(r.tolist()) * math.sqrt(P)), abs=TOL)
    beta = ref_cov(r.tolist(), m.tolist()) / ref_cov(m.tolist(), m.tolist())
    rf_w = ref_mean(rf.tolist())
    alpha = (ref_mean(r.tolist()) - rf_w - beta * (ref_mean(m.tolist()) - rf_w)) * P
    assert metrics.market(r, m, rf)["alpha"] == pytest.approx(alpha, abs=TOL)
    with pytest.raises(ValueError):
        metrics.performance(r, rf.iloc[:-1])


def test_max_drawdown_starting_capital_is_the_first_peak():
    # equity 90, 94.5, 103.95: the drawdown of the first week is measured from the starting 100
    assert metrics.max_drawdown(pd.Series([-0.10, 0.05, 0.10])) == pytest.approx(-0.10, abs=TOL)
    assert metrics.max_drawdown(pd.Series([0.10, -0.05])) == pytest.approx(-0.05, abs=TOL)


def test_zero_denominators_are_nan():
    flat = pd.Series(0.0, index=weeks(20))
    perf = metrics.performance(flat, RF)
    for key in ("sharpe_rf", "sharpe_zero_cost", "sharpe_textbook", "sortino_ratio", "calmar_ratio"):
        assert np.isnan(perf[key]), key
    stats = metrics.return_stats(flat)
    for key in ("profit_factor", "skew", "kurtosis", "avg_gain", "avg_loss"):
        assert np.isnan(stats[key]), key
    assert np.isnan(metrics.market(flat, flat, RF)["beta"])


def test_profit_factor_without_losses_is_nan():
    assert np.isnan(metrics.return_stats(pd.Series([0.01, 0.02, 0.0]))["profit_factor"])


def test_equity_curve_rebased_to_100():
    curve = metrics.equity_curve(pd.Series([0.10, -0.10]))
    assert curve.tolist() == pytest.approx([110.0, 99.0], abs=TOL)


def test_behaviour_matches_the_skeleton():
    traded = list(CFG["data"]["tickers"]) + [CFG["data"]["hedge"]]
    index = weeks(4)
    s = pd.DataFrame(0, index=index, columns=traded)
    s["XLK"] = [1, 1, -1, -1]
    s["XLE"] = [-1, -1, -1, 0]
    s["IVV"] = [0, -1, 0, 0]
    s = s.astype(np.int8)
    w = s.astype(float) * 0.25
    got = metrics.behaviour(s, w)
    n = len(traded)
    # trades (flat before week 1): week 1: |1| + |-1| = 2; week 2: IVV 1; week 3: XLK 2 + IVV 1 = 3; week 4: XLE 1
    assert got["turnover_per_year"] == pytest.approx((2 + 1 + 3 + 1) / n * P / 4, abs=TOL)
    # runs: XLK +1 (2), -1 (2); XLE -1 (3); IVV -1 (1) -> mean 2
    assert got["avg_holding"] == pytest.approx(2.0, abs=TOL)
    assert got["net_exposure"] == pytest.approx(np.mean([0, -1, -2, -1]) / n, abs=TOL)
    assert got["gross_exposure"] == pytest.approx(np.mean([2, 3, 2, 1]) / n, abs=TOL)
    assert got["long"] == pytest.approx(2 / 40, abs=TOL) and got["short"] == pytest.approx(6 / 40, abs=TOL)
    assert got["flat"] == pytest.approx(32 / 40, abs=TOL)
    assert got["gross_exposure_weights"] == pytest.approx(0.25 * np.mean([2, 3, 2, 1]), abs=TOL)
    assert got["turnover_per_year_weights"] == pytest.approx(0.25 * 7 * P / 4, abs=TOL)


def test_tbill_weekly_returns_lag_one_session():
    # week of Mon 2 Jan 2023 (holiday) to Fri 6 Jan; next week ends Fri 13 Jan
    sessions = pd.DatetimeIndex(["2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06",
                                 "2023-01-09", "2023-01-10", "2023-01-11", "2023-01-12", "2023-01-13"])
    dgs3mo = pd.Series([4.0, 4.1, np.nan, 4.3, 4.4, 4.5, 4.6, 4.7],
                       index=pd.DatetimeIndex(["2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06",
                                               "2023-01-09", "2023-01-10", "2023-01-11", "2023-01-12"]))
    index = weeks(2, start="2023-01-02")
    rf = metrics.tbill_weekly_returns(dgs3mo, index, sessions)
    # week 1: last session Fri 6 Jan, session before = Thu 5 Jan (missing) -> last observation on or before: 4.1 (Wed)
    # week 2: last session Fri 13 Jan, session before = Thu 12 Jan -> 4.7
    assert rf.iloc[0] == pytest.approx(4.1 / 100 * 7 / 365, abs=TOL)
    assert rf.iloc[1] == pytest.approx(4.7 / 100 * 7 / 365, abs=TOL)
    assert rf.name == "rf" and rf.dtype == np.float64


def test_tbill_on_the_synthetic_market(synthetic_market):
    weekly = synthetic_market.weekly_open.index
    rf = metrics.tbill_weekly_returns(synthetic_market.fred["DGS3MO"], weekly, synthetic_market.sessions)
    assert rf.iloc[1:].notna().all()
    assert (rf.dropna() >= 0).all() and rf.max() < 0.01


def test_period_average_rf():
    index = weeks(4)
    rf = pd.Series([0.001, 0.001, 0.002, 0.002], index=index)
    period = pd.Series(["IS", "IS", "OOS", "OOS"], index=index)
    got = metrics.period_average_rf(rf, period)
    assert got["IS"] == pytest.approx(1.001 ** P - 1, abs=TOL)
    assert got["OOS"] == pytest.approx(1.002 ** P - 1, abs=TOL)


def test_period_metrics_split_one_book(returns):
    r, m = returns
    period = pd.Series(["IS"] * 200 + ["OOS"] * 100, index=r.index)
    traded = list(CFG["data"]["tickers"]) + [CFG["data"]["hedge"]]
    s = pd.DataFrame(0, index=r.index, columns=traded, dtype=np.int8)
    s[["XLK", "XLY"]], s[["XLE", "XLU"]] = 1, -1
    got = metrics.period_metrics(r, period, s, s * 0.25, m, RF)
    assert set(got) == {"IS", "OOS"}
    oos = r.iloc[200:]
    assert got["OOS"]["weeks"] == 100
    assert got["OOS"]["sharpe_rf"] == pytest.approx(metrics.performance(oos, RF)["sharpe_rf"], abs=TOL)
    assert got["OOS"]["final_equity"] == pytest.approx(100 * (1 + oos).prod(), abs=1e-9)
    # turnover restarts at the first week of each period (skeleton)
    assert got["OOS"]["turnover_per_year"] == pytest.approx(got["IS"]["turnover_per_year"] * 200 / 100, abs=TOL)


# --- market-neutral bonus helpers (decision S34-9) ----------------------------------------------------------------------


def test_hac_beta_with_zero_lags_is_whites_robust_error():
    rng = np.random.default_rng(3)
    m = pd.Series(rng.normal(0, 0.02, 80), index=weeks(80))
    r = 0.3 * m + pd.Series(rng.normal(0, 0.01, 80), index=m.index)
    out = metrics.hac_beta(r, m, lags=0, confidence=0.95)
    x, y = m.to_numpy(), r.to_numpy()
    xc = x - x.mean()
    beta = (xc @ (y - y.mean())) / (xc @ xc)
    u = (y - y.mean()) - beta * xc
    white = math.sqrt(np.sum(xc ** 2 * u ** 2)) / (xc @ xc)
    assert out["beta"] == pytest.approx(beta, rel=TOL)
    assert out["beta"] == pytest.approx(metrics.market(r, m, 0.0)["beta"], rel=1e-10)
    assert out["se"] == pytest.approx(white, rel=1e-12)
    assert out["upper"] - out["beta"] == pytest.approx(1.959963984540054 * white, rel=1e-9)


def test_hac_beta_bartlett_weights_hand_case():
    m = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02], index=weeks(5))
    r = pd.Series([0.0, 0.01, -0.01, 0.02, 0.0], index=m.index)
    x, y = m.to_numpy(), r.to_numpy()
    xc = x - x.mean()
    beta = (xc @ (y - y.mean())) / (xc @ xc)
    z = xc * ((y - y.mean()) - beta * xc)
    t = len(z)
    s = z @ z / t + 2 * (1 - 1 / 3) * (z[1:] @ z[:-1]) / t + 2 * (1 - 2 / 3) * (z[2:] @ z[:-2]) / t
    expected = math.sqrt(s * t) / (xc @ xc)
    assert metrics.hac_beta(r, m, lags=2)["se"] == pytest.approx(expected, rel=1e-12)


def test_hac_beta_refuses_bad_inputs():
    m = pd.Series([0.01, 0.01, 0.01], index=weeks(3))
    with pytest.raises(ValueError, match="zero variance"):
        metrics.hac_beta(m, m, lags=0)
    with pytest.raises(ValueError, match="missing"):
        metrics.hac_beta(pd.Series([0.1, np.nan, 0.2], index=m.index), m + [0, 0.01, 0.02], lags=0)


def test_monthly_returns_compound_by_month_of_realisation():
    index = weeks(4, "2020-01-20")
    r = pd.Series([0.1, -0.5, 0.2, 0.1], index=index)
    realised = pd.Series(pd.to_datetime(["2020-01-27", "2020-01-31", "2020-02-03", "2020-02-10"]), index=index)
    out = metrics.monthly_returns(r, realised)
    assert list(out.index) == [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-29")]
    assert out.tolist() == pytest.approx([1.1 * 0.5 - 1, 1.2 * 1.1 - 1], rel=TOL)


def test_rolling_positive_share_hand_case():
    r = pd.Series([0.1, -0.2, 0.05, 0.3], index=weeks(4))
    # windows of 2: (1.1·0.8 − 1) < 0, (0.8·1.05 − 1) < 0, (1.05·1.3 − 1) > 0
    assert metrics.rolling_positive_share(r, 2) == pytest.approx(1 / 3)
    assert np.isnan(metrics.rolling_positive_share(r, 5))


def test_calendar_year_returns_by_year_of_realisation():
    index = weeks(3, "2019-12-16")
    r = pd.Series([0.1, 0.2, -0.1], index=index)
    realised = pd.Series(pd.to_datetime(["2019-12-30", "2020-01-06", "2020-01-13"]), index=index)
    out = metrics.calendar_year_returns(r, realised)
    assert out.to_dict() == pytest.approx({2019: 0.1, 2020: 1.2 * 0.9 - 1})
