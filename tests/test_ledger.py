"""src/ledger.py: the independent shares-and-cash ledger against the vectorised engine, on the shared synthetic market.

Level A (bookkeeping, adjusted opens): zero cost within the pre-registered 1e-6 per week (§09); with costs and borrow
within 1e-10, since Amendment 3 C2 divides the drifted weights by the book's value after costs and borrow.
Level B (corporate actions, raw opens, the planted 2:1 XLK split, cash dividends), Amendment 3 C1:
|ledger − engine − dividend-reinvestment term| ≤ 1e-6 every week, the term computed from the dividend series and prices
(src.ledger.dividend_reinvestment_term), never from the difference; the split contributes nothing.
Differences are ledger minus engine, the sign of Amendment 3 C1.
"""

import numpy as np
import pandas as pd
import pytest

from src.backtest import forward_returns, run
from src.config import load_config
from src.ledger import actual_prices, dividend_reinvestment_term, run_ledger
from src.sizing import size_book

CFG = load_config()
SECTORS = list(CFG["data"]["tickers"])
HEDGE = CFG["data"]["hedge"]
TRADED = SECTORS + [HEDGE]
COST_BPS, BORROW = CFG["costs"]["bps_baseline"], CFG["costs"]["borrow_baseline"]
PREREGISTERED = 1e-6  # §09: zero-cost ledger vs engine, per week (Level A); Level B remainder (Amendment 3 C1)
COSTS_TOLERANCE = 1e-10  # Level A with costs and borrow (Amendment 3 C2)
TOL = 1e-12


def _book(market, seed: int = 7):
    """Two years of a seeded random book on the synthetic market, XLK always long (so the planted split is held)."""
    fwd, _, period = forward_returns(market.weekly_open, is_end=market.is_end)
    fridays = pd.DatetimeIndex(fwd.index.get_level_values("date_close"))
    weeks = fwd.index[(fridays >= pd.Timestamp("2014-06-01")) & (fridays <= pd.Timestamp("2016-06-01"))]
    rng = np.random.default_rng(seed)
    scores = pd.DataFrame(rng.normal(size=(len(weeks), 9)), index=weeks, columns=SECTORS)
    scores["XLK"] = 10.0
    betas = pd.DataFrame(rng.uniform(0.6, 1.4, size=(len(weeks), 10)), index=weeks, columns=TRADED)
    betas[HEDGE] = 1.0
    sizing = size_book(scores, betas, CFG)
    return fwd, period, sizing


def test_actual_prices_undo_the_split(synthetic_market):
    for ticker in TRADED:
        rebuilt = actual_prices(synthetic_market.raw[ticker])["open"]
        expected = synthetic_market.unadjusted_open[ticker].dropna()
        assert np.allclose(rebuilt.to_numpy(), expected.loc[rebuilt.index].to_numpy(), rtol=TOL, atol=0)
    ticker, day, ratio = synthetic_market.split
    splits = actual_prices(synthetic_market.raw[ticker])["split"]
    assert splits.loc[day] == ratio and (splits.drop(day) == 1.0).all()


def test_level_a_zero_cost_matches_the_engine(synthetic_market):
    fwd, period, sizing = _book(synthetic_market)
    engine = run(sizing, fwd, period, 0.0, 0.0)
    ledger = run_ledger(engine.weights, synthetic_market.raw, mode="adjusted")
    assert len(ledger) == len(engine.gross)
    diff = (engine.gross.loc[ledger.index] - ledger["ret"]).abs()
    assert diff.max() <= PREREGISTERED
    assert diff.max() <= TOL  # same prices, so the bookkeeping agrees to rounding


def test_level_a_with_costs_matches_the_engine(synthetic_market):
    fwd, period, sizing = _book(synthetic_market)
    engine = run(sizing, fwd, period, COST_BPS, BORROW)
    ledger = run_ledger(engine.weights, synthetic_market.raw, mode="adjusted", cost_bps=COST_BPS, borrow_annual=BORROW)
    # the ledger's own accounting: ret = Σ w R − c · traded − borrow, borrow on the short value at entry
    assert np.allclose(ledger["ret"], engine.gross - COST_BPS / 10_000 * ledger["traded"] - ledger["borrow"], atol=TOL, rtol=0)
    assert np.allclose(ledger["borrow"], engine.borrow, atol=TOL, rtol=0)
    assert ledger["traded"].iloc[0] == pytest.approx(1.0, abs=TOL)  # entered from cash
    # Amendment 3 C2: the engine's drifted weights are the ledger's, so turnover and returns agree
    assert np.allclose(ledger["traded"], engine.turnover, atol=COSTS_TOLERANCE, rtol=0)
    assert (ledger["ret"] - engine.net).abs().max() <= COSTS_TOLERANCE


@pytest.mark.parametrize("bps,borrow", list(zip(CFG["costs"]["bps"], CFG["costs"]["borrow"])))
def test_level_a_with_every_cost_scenario(synthetic_market, bps, borrow):
    fwd, period, sizing = _book(synthetic_market)
    engine = run(sizing, fwd, period, bps, borrow)
    ledger = run_ledger(engine.weights, synthetic_market.raw, mode="adjusted", cost_bps=bps, borrow_annual=borrow)
    assert (ledger["ret"] - engine.net).abs().max() <= COSTS_TOLERANCE


def test_level_b_split_and_dividends(synthetic_market):
    fwd, period, sizing = _book(synthetic_market)
    engine = run(sizing, fwd, period, 0.0, 0.0)
    ledger = run_ledger(engine.weights, synthetic_market.raw, mode="raw")
    difference = ledger["ret"] - engine.gross.loc[ledger.index]
    term = dividend_reinvestment_term(engine.weights, synthetic_market.raw).loc[ledger.index]
    # the planted 2:1 split is held (XLK always long) and applied once
    split_weeks = ledger["splits"] > 0
    assert split_weeks.sum() == 1
    dividend_weeks = ledger["dividends"] != 0
    assert dividend_weeks.any() and difference[dividend_weeks].abs().max() > PREREGISTERED  # the term is material
    # Amendment 3 C1, the pass criterion
    assert (difference - term.sum(axis=1)).abs().max() <= PREREGISTERED
    # with exact float64 factors the term explains the difference to rounding; splits and event-free weeks give 0
    assert np.allclose(difference, term.sum(axis=1), atol=TOL, rtol=0)
    assert difference[~dividend_weeks].abs().max() <= TOL
    assert difference[split_weeks & ~dividend_weeks].abs().max() <= TOL
    assert term[[t for t in TRADED if t not in ("XLE", "XLF", "XLP", "XLU", HEDGE)]].abs().max().max() == 0  # no payer


def test_reinvestment_term_hand_case():
    # one ticker, sessions Mon..Mon; buy at O1 = 100 on Mon 4 Jan 2010, ex-date Wed 6 Jan with D = 1 and C(Tue) = 101,
    # value at O2 = 102 on Mon 11 Jan; w = 0.25 (other tickers flat)
    # engine 1 + R_E = (102 / 100) / (1 - 1/101) = 1.0302; ledger 1 + R_L = (102 + 1) / 100 = 1.03
    # term = 0.25 * (1.03 - 1.0302) = -0.00005
    days = pd.bdate_range("2010-01-04", "2010-01-11")
    frame = pd.DataFrame({"Open": 100.0, "High": 0.0, "Low": 0.0, "Close": 100.0, "Adj Close": 100.0, "Volume": 0,
                          "Dividends": 0.0, "Stock Splits": 0.0}, index=days)
    frame.loc["2010-01-05", "Close"] = 101.0
    frame.loc["2010-01-06", "Dividends"] = 1.0
    frame.loc["2010-01-11", "Open"] = 102.0
    raw = {t: frame for t in TRADED}
    index = pd.MultiIndex.from_arrays([[pd.Timestamp("2009-12-28")], [pd.Timestamp("2010-01-01")]],
                                      names=["date_open", "date_close"])
    weights = pd.DataFrame(0.0, index=index, columns=TRADED)
    weights["XLK"] = 0.25
    term = dividend_reinvestment_term(weights, raw)
    assert term.loc[index[0], "XLK"] == pytest.approx(0.25 * (1.03 - 1.02 / (1 - 1 / 101)), abs=TOL)
    assert term.loc[index[0], "XLK"] == pytest.approx(-0.00005, abs=TOL)
    assert term.drop(columns="XLK").abs().max().max() == 0


def test_level_b_short_pays_the_dividend(synthetic_market):
    fwd, period, sizing = _book(synthetic_market)
    engine = run(sizing, fwd, period, 0.0, 0.0)
    ledger = run_ledger(engine.weights, synthetic_market.raw, mode="raw")
    # a book short IVV in a dividend week pays it: the net dividend cash has the sign of the IVV weight there
    w_ivv = engine.weights.loc[ledger.index, HEDGE]
    only_ivv_pays = (engine.weights.loc[ledger.index, ["XLE", "XLF", "XLP", "XLU"]] == 0).all(axis=1)
    weeks = (ledger["dividends"] != 0) & only_ivv_pays & (w_ivv != 0)
    assert weeks.any()
    assert (np.sign(ledger.loc[weeks, "dividends"]) == np.sign(w_ivv[weeks])).all()


def test_ledger_refuses_non_consecutive_weeks(synthetic_market):
    fwd, period, sizing = _book(synthetic_market)
    engine = run(sizing, fwd, period, 0.0, 0.0)
    with pytest.raises(ValueError, match="not consecutive"):
        run_ledger(engine.weights.iloc[[0, 2]], synthetic_market.raw, mode="adjusted")


def test_ledger_mode_is_checked(synthetic_market):
    with pytest.raises(ValueError):
        run_ledger(pd.DataFrame(columns=TRADED), synthetic_market.raw, mode="other")
