"""src/backtest.py against §05, §09, §10 and Amendment 2 C5 (one continuous book), with hand-computed cases.

Cases of PROMPT_2.1 §5: (a) one week, 2 long + 2 short, no hedge; (e) two-week drift with a +25% -> -25% flip;
(f) costs and borrow amounts. Properties on the shared synthetic fixture (contract 18).
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.backtest import forward_returns, run
from src.config import load_config
from src.contracts import ContractError, SizingResult, validate_backtest_result, validate_signals, validate_weights
from src.sizing import size_book, target_weights

CFG = load_config()
SECTORS = list(CFG["data"]["tickers"])
HEDGE, BENCHMARK = CFG["data"]["hedge"], CFG["data"]["benchmark"]
TRADED = SECTORS + [HEDGE]
TRADABLES = TRADED + [BENCHMARK]
SIGNAL = CFG["signal"]
CORE, CAP, BAND = SIGNAL["core_weight"], SIGNAL["hedge_cap"], SIGNAL["hedge_deadband"]
COST_BPS, BORROW = CFG["costs"]["bps_baseline"], CFG["costs"]["borrow_baseline"]
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])
TOL = 1e-12


def weeks(n: int, start: str = "2010-01-04") -> pd.MultiIndex:
    mondays = pd.date_range(start, periods=n, freq="7D")
    return pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])


def sized_book(rows: list[tuple[list[str], list[str]]], betas: list[dict] | None = None) -> SizingResult:
    """Sizing of hand-made weeks: (longs, shorts) per week; betas default to 1.0 (no hedge)."""
    index = weeks(len(rows))
    signals = pd.DataFrame([{s: (1 if s in longs else -1 if s in shorts else 0) for s in SECTORS} for longs, shorts in rows],
                           index=index, columns=SECTORS).astype(np.int8)
    betas = betas or [{}] * len(rows)
    beta = pd.DataFrame([{t: float(b.get(t, 1.0)) for t in TRADED} for b in betas], index=index, columns=TRADED)
    return target_weights(signals, beta, CORE, CAP, BAND)


def fwd_frame(rows: list[dict], index: pd.MultiIndex) -> tuple[pd.DataFrame, pd.Series]:
    """Forward returns (0 for every ticker not named) and an all-IS period on the given weeks."""
    fwd = pd.DataFrame([{t: float(row.get(t, 0.0)) for t in TRADABLES} for row in rows], index=index, columns=TRADABLES)
    return fwd, pd.Series("IS", index=index, name="period", dtype=object)


# --- forward_returns --------------------------------------------------------------------------------------------------

def test_forward_returns_definition():
    index = weeks(5)
    opens = pd.DataFrame({t: [100.0, 101.0, 102.0, 99.0, 98.0] for t in TRADABLES}, index=index)
    fwd, realised_on, period = forward_returns(opens)
    assert fwd["XLK"].iloc[0] == pytest.approx(102.0 / 101.0 - 1, abs=TOL)  # O(t+2) / O(t+1) - 1
    assert fwd["XLK"].iloc[2] == pytest.approx(98.0 / 99.0 - 1, abs=TOL)
    assert fwd.iloc[-2:].isna().all().all()
    assert realised_on.iloc[0] == index[2][0] and realised_on.iloc[-2:].isna().all()
    assert (period.iloc[:3] == "IS").all() and period.iloc[-2:].isna().all()


def test_is_oos_boundary_by_realisation_date():
    index = weeks(6, start="2019-12-02")  # Fridays 6, 13, 20, 27 Dec 2019, 3 and 10 Jan 2020
    opens = pd.DataFrame(100.0, index=index, columns=TRADABLES)
    _, realised_on, period = forward_returns(opens)
    fridays = pd.DatetimeIndex(index.get_level_values("date_close"))
    by_friday = dict(zip(fridays.strftime("%Y-%m-%d"), period))
    assert by_friday["2019-12-13"] == "IS"  # realised Mon 2019-12-23
    assert by_friday["2019-12-20"] == "OOS"  # realised Mon 2019-12-30, the first OOS return
    assert realised_on.iloc[2] == pd.Timestamp("2019-12-30")


def test_forward_returns_require_every_tradable():
    with pytest.raises(ContractError):
        forward_returns(pd.DataFrame(100.0, index=weeks(4), columns=SECTORS))


# --- run: hand cases --------------------------------------------------------------------------------------------------

def test_case_a_one_week_two_long_two_short():
    # long XLK, XLY; short XLE, XLU; betas 1 -> beta_c = 0 -> no hedge; w = ±0.25
    # gross = 0.25 * (0.04 + 0.02) - 0.25 * (-0.01 + 0.03) = 0.015 - 0.005 = 0.010
    # turnover = 1 (entered from cash); costs = 0.0010 * 1; borrow = 0.02 * 7/365 * 0.5 = 0.000191780821917...
    sizing = sized_book([(["XLK", "XLY"], ["XLE", "XLU"])])
    fwd, period = fwd_frame([{"XLK": 0.04, "XLY": 0.02, "XLE": -0.01, "XLU": 0.03, "XLB": 0.5, HEDGE: 0.01}], sizing.weights.index)
    result = run(sizing, fwd, period, COST_BPS, BORROW)
    assert result.gross.iloc[0] == pytest.approx(0.010, abs=TOL)
    assert result.turnover.iloc[0] == pytest.approx(1.0, abs=TOL)
    assert result.costs.iloc[0] == pytest.approx(0.0010, abs=TOL)
    assert result.borrow.iloc[0] == pytest.approx(0.02 * 7 / 365 * 0.5, abs=TOL)
    assert result.net.iloc[0] == pytest.approx(0.010 - 0.0010 - 0.02 * 7 / 365 * 0.5, abs=TOL)


def test_case_e_two_week_drift_with_a_flip():
    # week 1: +XLK +XLY -XLE -XLU; R: XLK +10%, XLE -10%, others 0 -> gross_1 = 0.025 + 0.025 = 0.05
    # Amendment 3 C2: w_pre_2 = w_1 (1 + R_1) / (1 + net_1) = XLK 0.275/D, XLY 0.25/D, XLE -0.225/D, XLU -0.25/D, D = 1 + net_1
    # week 2: +XLB +XLY -XLE -XLK (XLK flips from +25% to -25%, XLU closes, XLB opens)
    # turnover_2 = 0.25 (XLB) + (0.25 - 0.25/D) (XLY) + (0.25 + 0.275/D) (XLK) + (0.25 - 0.225/D) (XLE) + 0.25/D (XLU)
    #            = 1 + 0.05/D
    # zero cost: D = 1.05 -> turnover_2 = 1 + 0.05/1.05 = 1.047619047619...
    # 10 bps + 2%: net_1 = 0.05 - 0.0010 * 1 - 0.02 * 7/365 * 0.5 = 0.048808219178..., turnover_2 = 1 + 0.05/1.048808219178...
    sizing = sized_book([(["XLK", "XLY"], ["XLE", "XLU"]), (["XLB", "XLY"], ["XLE", "XLK"])])
    fwd, period = fwd_frame([{"XLK": 0.10, "XLE": -0.10}, {}], sizing.weights.index)
    free = run(sizing, fwd, period, 0.0, 0.0)
    assert free.gross.iloc[0] == pytest.approx(0.05, abs=TOL)
    assert free.turnover.iloc[1] == pytest.approx(1 + 0.05 / 1.05, abs=TOL)
    result = run(sizing, fwd, period, COST_BPS, BORROW)
    net_1 = 0.05 - 0.0010 - 0.02 * 7 / 365 * 0.5
    assert result.net.iloc[0] == pytest.approx(net_1, abs=TOL)
    assert result.turnover.iloc[1] == pytest.approx(1 + 0.05 / (1 + net_1), abs=TOL)
    # (f) costs of week 2 at 10 bps
    assert result.costs.iloc[1] == pytest.approx(0.0010 * (1 + 0.05 / (1 + net_1)), abs=TOL)


def test_case_f_costs_and_borrow_with_the_hedge_and_the_stress_rates():
    # case (b) book: h = -0.35, short gross = (0.25 + 0.25 + 0.35) / 1.35 = 0.85 / 1.35
    sizing = sized_book([(["XLK", "XLY"], ["XLP", "XLU"])], [{"XLK": 1.2, "XLY": 1.4, "XLP": 0.6, "XLU": 0.6}])
    fwd, period = fwd_frame([{}], sizing.weights.index)
    short = 0.85 / 1.35
    for bps, borrow in zip(CFG["costs"]["bps"], CFG["costs"]["borrow"]):  # (5, 1%), (10, 2%), (20, 5%)
        result = run(sizing, fwd, period, bps, borrow)
        assert result.costs.iloc[0] == pytest.approx(bps / 10_000 * 1.0, abs=TOL)  # entered from cash: turnover 1
        assert result.borrow.iloc[0] == pytest.approx(borrow * 7 / 365 * short, abs=TOL)
        assert result.net.iloc[0] == pytest.approx(-bps / 10_000 - borrow * 7 / 365 * short, abs=TOL)


def test_carried_week_rebalances_back_to_the_targets():
    # Amendment 2 C3: a missing score in week 2 carries the week-1 targets; turnover is the drift back to them
    index = weeks(2)
    scores = pd.DataFrame([[0.0] * 9, [np.nan] * 9], index=index, columns=SECTORS)
    scores.loc[index[0], ["XLK", "XLY", "XLE", "XLU"]] = [3.0, 2.0, -2.0, -3.0]
    sizing = size_book(scores, pd.DataFrame(1.0, index=index, columns=TRADED), CFG)
    fwd, period = fwd_frame([{"XLK": 0.10, "XLE": -0.10}, {}], index)
    result = run(sizing, fwd, period, COST_BPS, BORROW)
    w1 = result.weights.iloc[0]
    w_pre = w1 * (1 + fwd.loc[index[0], TRADED]) / (1 + result.net.iloc[0])  # Amendment 3 C2
    assert (result.weights.iloc[1] == w1).all()
    assert result.turnover.iloc[1] == pytest.approx(float((w1 - w_pre).abs().sum()), abs=TOL)


def test_run_refuses_a_gap_between_weeks():
    sizing = sized_book([(["XLK", "XLY"], ["XLE", "XLU"])] * 3)
    fwd, period = fwd_frame([{}] * 3, sizing.weights.index)
    fwd.iloc[1, 0] = np.nan
    with pytest.raises(ValueError, match="not consecutive"):
        run(sizing, fwd, period, COST_BPS, BORROW)


def test_sensitivity_core_weight_is_validated():
    rng = np.random.default_rng(3)
    index = weeks(10)
    scores = pd.DataFrame(rng.normal(size=(10, 9)), index=index, columns=SECTORS)
    sizing = size_book(scores, pd.DataFrame(1.0, index=index, columns=TRADED), CFG, k=1)
    fwd, period = fwd_frame([{"XLK": 0.01}] * 10, index)
    result = run(sizing, fwd, period, COST_BPS, BORROW, core_weight=0.5)
    assert np.allclose(result.net, result.gross - result.costs - result.borrow, atol=TOL)
    with pytest.raises(ContractError):
        run(sizing, fwd, period, COST_BPS, BORROW)  # validated with the pre-registered 0.25: sizes do not match


# --- properties on the shared synthetic fixture ------------------------------------------------------------------------

@pytest.fixture
def synthetic_run(synthetic_market):
    fwd, realised_on, period = forward_returns(synthetic_market.weekly_open, is_end=synthetic_market.is_end)
    rng = np.random.default_rng(42)
    scores = pd.DataFrame(rng.normal(size=(len(fwd), 9)), index=fwd.index, columns=SECTORS)
    betas = pd.DataFrame({t: synthetic_market.true_beta[t] for t in TRADED}, index=fwd.index)
    sizing = size_book(scores, betas, CFG)
    return SimpleNamespace(market=synthetic_market, fwd=fwd, realised_on=realised_on, period=period, sizing=sizing,
                           result=run(sizing, fwd, period, COST_BPS, BORROW))


def test_synthetic_book_properties(synthetic_run):
    result = synthetic_run.result
    sizing = synthetic_run.sizing
    fwd = synthetic_run.fwd
    validate_backtest_result(result, cost_bps=COST_BPS, borrow_annual=BORROW)
    validate_weights(result.weights, sizing.signals.loc[result.weights.index])
    validate_signals(sizing.signals)
    assert np.allclose(result.weights.abs().sum(axis=1), 1.0, atol=TOL)
    assert np.allclose(result.net, result.gross - result.costs - result.borrow, atol=TOL)
    # gross = Σ w R_fwd, recomputed directly
    assert np.allclose(result.gross, (result.weights * fwd.loc[result.weights.index, TRADED]).sum(axis=1), atol=TOL)
    # the first week starts after IVV's first two opens exist, the last one is the last realised week
    assert result.weights.index[-1] == fwd.index[-3]


def test_synthetic_period_boundary(synthetic_run):
    result = synthetic_run.result
    realised_on = synthetic_run.realised_on
    market = synthetic_run.market
    realised = realised_on.loc[result.period.index]
    assert ((result.period == "IS") == (realised <= market.is_end)).all()
    fridays = pd.DatetimeIndex(result.period.index.get_level_values("date_close"))
    assert result.period[fridays == pd.Timestamp("2019-12-13")].item() == "IS"
    assert result.period[fridays == pd.Timestamp("2019-12-20")].item() == "OOS"


def test_c5_one_continuous_book_across_the_boundary(synthetic_run):
    # the first OOS week is not entered from cash: its turnover is the rebalance from the drifted IS book
    result = synthetic_run.result
    fwd = synthetic_run.fwd
    first_oos = int(np.flatnonzero((result.period == "OOS").to_numpy())[0])
    w = result.weights.to_numpy()
    r = fwd.loc[result.weights.index, TRADED].to_numpy()
    w_pre = w[first_oos - 1] * (1 + r[first_oos - 1]) / (1 + result.net.iloc[first_oos - 1])  # Amendment 3 C2
    assert result.turnover.iloc[first_oos] == pytest.approx(np.abs(w[first_oos] - w_pre).sum(), abs=TOL)
    assert abs(result.turnover.iloc[first_oos] - 1.0) > 1e-6  # a restart from cash would give Σ|w| = 1


def test_engine_is_deterministic(synthetic_run):
    result = synthetic_run.result
    sizing = synthetic_run.sizing
    fwd = synthetic_run.fwd
    period = synthetic_run.period
    again = run(sizing, fwd, period, COST_BPS, BORROW)
    pd.testing.assert_series_equal(result.net, again.net, check_exact=True)
