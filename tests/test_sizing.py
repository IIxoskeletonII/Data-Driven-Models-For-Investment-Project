"""src/sizing.py against §09 and Amendment 2 (C2 dead-band, C3 missing input, C4 sensitivity k), with hand-computed cases.

Cases of PROMPT_2.1 §5: (b) hedge active, cap not binding; (c) cap binding; (d) dead-band; (g) tie-breaking;
(h) missing score keeps last week's signals. Cases (a), (e), (f) are in tests/test_backtest.py.
"""

import logging

import numpy as np
import pandas as pd
import pytest

from src.config import load_config
from src.contracts import ContractError, validate_signals, validate_weights
from src.sizing import core_weight_for, signals_from_scores, size_book, target_weights

CFG = load_config()
SECTORS = list(CFG["data"]["tickers"])
HEDGE = CFG["data"]["hedge"]
TRADED = SECTORS + [HEDGE]
SIGNAL = CFG["signal"]
CORE, CAP, BAND = SIGNAL["core_weight"], SIGNAL["hedge_cap"], SIGNAL["hedge_deadband"]
TOL = 1e-12


def weeks(n: int, start: str = "2010-01-04") -> pd.MultiIndex:
    mondays = pd.date_range(start, periods=n, freq="7D")
    return pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])


def scores_frame(rows: list[dict], index: pd.MultiIndex | None = None) -> pd.DataFrame:
    """Scores with 0 for every sector not named in a row."""
    index = weeks(len(rows)) if index is None else index
    return pd.DataFrame([{s: float(row.get(s, 0.0)) for s in SECTORS} for row in rows], index=index, columns=SECTORS)


def betas_frame(rows: list[dict], index: pd.MultiIndex | None = None) -> pd.DataFrame:
    """Betas with 1.0 for every traded ticker not named in a row."""
    index = weeks(len(rows)) if index is None else index
    return pd.DataFrame([{t: float(row.get(t, 1.0)) for t in TRADED} for row in rows], index=index, columns=TRADED)


def sector_signals(longs: list[str], shorts: list[str], n: int = 1) -> pd.DataFrame:
    row = {s: (1 if s in longs else -1 if s in shorts else 0) for s in SECTORS}
    return pd.DataFrame([row] * n, index=weeks(n), columns=SECTORS).astype(np.int8)


def size(longs, shorts, betas: dict):
    return target_weights(sector_signals(longs, shorts), betas_frame([betas]), CORE, CAP, BAND)


# --- signals_from_scores ----------------------------------------------------------------------------------------------

def test_top_two_long_bottom_two_short():
    scores = scores_frame([{"XLK": 3.0, "XLY": 2.0, "XLV": 1.0, "XLE": -2.0, "XLU": -3.0}])
    s = signals_from_scores(scores, 2, 2).iloc[0]
    assert s.dtype == np.int8
    assert list(s[s == 1].index) == ["XLK", "XLY"] and list(s[s == -1].index) == ["XLE", "XLU"]
    assert (s.drop(["XLK", "XLY", "XLE", "XLU"]) == 0).all()


def test_case_g_ties_are_broken_alphabetically():
    # (g) all scores equal: ranks follow the alphabet, XLB XLE on top, XLV XLY at the bottom
    s = signals_from_scores(scores_frame([{}]), 2, 2).iloc[0]
    assert list(s[s == 1].index) == ["XLB", "XLE"] and list(s[s == -1].index) == ["XLV", "XLY"]
    # a tie for the second long place: XLF (earlier) beats XLK; a tie for the last short place: XLU ranks above XLY,
    # so XLY takes the lowest rank
    s = signals_from_scores(scores_frame([{"XLV": 5.0, "XLK": 4.0, "XLF": 4.0, "XLU": -4.0, "XLY": -4.0}]), 2, 2).iloc[0]
    assert list(s[s == 1].index) == ["XLF", "XLV"]
    assert list(s[s == -1].index) == ["XLU", "XLY"]
    s = signals_from_scores(scores_frame([{"XLV": 5.0, "XLK": 4.0, "XLF": 4.0, "XLU": -4.0, "XLY": -4.0}]), 1, 1).iloc[0]
    assert list(s[s == 1].index) == ["XLV"] and list(s[s == -1].index) == ["XLY"]


def test_case_h_missing_score_keeps_last_signals(caplog):
    rows = [{"XLK": 3, "XLY": 2, "XLE": -2, "XLU": -3}, {"XLB": 3, "XLV": 2, "XLF": -2, "XLP": -3}]
    scores = scores_frame(rows + [rows[1]])
    scores.iloc[1, SECTORS.index("XLI")] = np.nan
    with caplog.at_level(logging.WARNING, logger="src.sizing"):
        signals = signals_from_scores(scores, 2, 2)
    assert (signals.iloc[1] == signals.iloc[0]).all()  # week 2 carried from week 1
    assert signals.iloc[2]["XLB"] == 1 and signals.iloc[2]["XLP"] == -1  # week 3 ranked again
    assert "2010-01-15: score XLI" in caplog.text  # the carried week is logged with the missing field (C3)


def test_leading_missing_scores_are_flat_rows_dropped():
    scores = scores_frame([{}, {}, {"XLK": 1}])
    scores.iloc[0] = np.nan
    scores.iloc[1, 0] = np.nan
    signals = signals_from_scores(scores, 2, 2)
    assert list(signals.index) == list(scores.index[2:])


def test_signals_pass_the_validator_with_an_ivv_column():
    rng = np.random.default_rng(0)
    scores = pd.DataFrame(rng.normal(size=(30, 9)), index=weeks(30), columns=SECTORS)
    for k in (1, 2, 3):
        signals = signals_from_scores(scores, k, k)
        validate_signals(signals.assign(**{HEDGE: np.int8(0)}).astype(np.int8), top_k=k, bottom_k=k)


def test_bad_k_raises():
    with pytest.raises(ValueError):
        signals_from_scores(scores_frame([{}]), 5, 5)


# --- target_weights ---------------------------------------------------------------------------------------------------

def test_case_b_hedge_active_cap_not_binding():
    # long XLK (1.2) and XLY (1.4), short XLP (0.6) and XLU (0.6), beta IVV 1.0
    # beta_c = 0.25 * (1.2 + 1.4 - 0.6 - 0.6) = 0.35; h = -0.35; scale 1.35
    sized = size(["XLK", "XLY"], ["XLP", "XLU"], {"XLK": 1.2, "XLY": 1.4, "XLP": 0.6, "XLU": 0.6})
    w = sized.weights.iloc[0]
    assert sized.hedge.iloc[0] == pytest.approx(-0.35, abs=TOL)
    assert w["XLK"] == pytest.approx(0.25 / 1.35, abs=TOL) and w["XLU"] == pytest.approx(-0.25 / 1.35, abs=TOL)
    assert w[HEDGE] == pytest.approx(-0.35 / 1.35, abs=TOL)
    betas = pd.Series({"XLK": 1.2, "XLY": 1.4, "XLP": 0.6, "XLU": 0.6}).reindex(TRADED, fill_value=1.0)
    assert abs((w * betas).sum()) <= TOL  # ex-ante beta exactly 0
    assert abs(w.abs().sum() - 1.0) <= TOL  # gross exactly 1
    assert abs(sized.residual_beta.iloc[0]) <= TOL
    assert sized.net_exposure.iloc[0] == pytest.approx(-0.35 / 1.35, abs=TOL)
    assert sized.signals.iloc[0][HEDGE] == -1 and not sized.cap_binds.iloc[0]


def test_case_c_cap_binding_residual_beta():
    # beta_c = 0.25 * (1.8 + 1.7 - 0.3 - 0.2) = 0.75; -beta_c / 1.0 = -0.75 -> h = -0.5 (cap); scale 1.5
    # residual beta = (0.75 - 0.5 * 1.0) / 1.5 = 1/6
    sized = size(["XLK", "XLY"], ["XLP", "XLU"], {"XLK": 1.8, "XLY": 1.7, "XLP": 0.3, "XLU": 0.2})
    assert sized.cap_binds.iloc[0]
    assert sized.hedge.iloc[0] == pytest.approx(-0.5, abs=TOL)
    assert sized.residual_beta.iloc[0] == pytest.approx(1 / 6, abs=TOL)
    assert sized.weights.iloc[0][HEDGE] == pytest.approx(-0.5 / 1.5, abs=TOL)
    assert sized.weights.iloc[0]["XLK"] == pytest.approx(0.25 / 1.5, abs=TOL)


def test_negative_core_beta_gives_a_long_hedge():
    # beta_c = 0.25 * (0.6 + 0.6 - 1.2 - 1.4) = -0.35 -> h = +0.35, IVV signal +1
    sized = size(["XLP", "XLU"], ["XLK", "XLY"], {"XLK": 1.2, "XLY": 1.4, "XLP": 0.6, "XLU": 0.6})
    assert sized.hedge.iloc[0] == pytest.approx(0.35, abs=TOL) and sized.signals.iloc[0][HEDGE] == 1


def test_case_d_dead_band_on_the_ivv_weight():
    # beta_c = 0.25 * (1.05 + 1.0 - 1.0 - 1.0) = 0.0125 -> h = -0.0125, |h| / (1 + |h|) = 0.0123 < 0.02 -> h = 0
    sized = size(["XLK", "XLY"], ["XLP", "XLU"], {"XLK": 1.05})
    assert sized.hedge.iloc[0] == 0 and sized.signals.iloc[0][HEDGE] == 0 and sized.weights.iloc[0][HEDGE] == 0
    assert sized.residual_beta.iloc[0] == pytest.approx(0.0125, abs=TOL)  # reported, not hedged
    assert sized.weights.iloc[0]["XLK"] == pytest.approx(0.25, abs=TOL)


def test_dead_band_uses_the_weight_not_h():
    # Amendment 2 C2: h = -0.0203 has |h| >= 0.02 but |h| / (1 + |h|) = 0.019896 < 0.02 -> zeroed
    # beta_c = 0.25 * 0.0812 = 0.0203
    inside = size(["XLK", "XLY"], ["XLP", "XLU"], {"XLK": 1.0812})
    assert inside.hedge.iloc[0] == 0
    # h = -0.0205: 0.0205 / 1.0205 = 0.020088 >= 0.02 -> kept; beta_c = 0.25 * 0.082 = 0.0205
    outside = size(["XLK", "XLY"], ["XLP", "XLU"], {"XLK": 1.082})
    assert outside.hedge.iloc[0] == pytest.approx(-0.0205, abs=TOL) and outside.signals.iloc[0][HEDGE] == -1


def test_weights_pass_the_validator_on_random_inputs():
    rng = np.random.default_rng(1)
    index = weeks(60)
    scores = pd.DataFrame(rng.normal(size=(60, 9)), index=index, columns=SECTORS)
    betas = pd.DataFrame(rng.uniform(0.2, 2.0, size=(60, 10)), index=index, columns=TRADED)
    sized = target_weights(signals_from_scores(scores, 2, 2), betas, CORE, CAP, BAND)
    validate_weights(sized.weights, sized.signals)
    validate_signals(sized.signals)
    assert np.allclose(sized.weights.abs().sum(axis=1), 1.0, atol=TOL)
    w_hedge = sized.weights[HEDGE]
    assert np.allclose(w_hedge, sized.hedge / (1 + sized.hedge.abs()), atol=TOL)
    assert np.allclose(sized.net_exposure, sized.weights.sum(axis=1), atol=TOL)
    # residual beta matches Σ w·β; it is 0 unless the cap binds or the dead-band zeroes the hedge
    exposure = (sized.weights * betas).sum(axis=1)
    assert np.allclose(sized.residual_beta, exposure, atol=TOL)
    free = ~sized.cap_binds & (sized.hedge != 0)
    assert (sized.residual_beta[free].abs() <= TOL).all()
    assert sized.cap_binds.any()


def test_c3_unusable_beta_carries_signals_and_targets(caplog):
    # week 2 has new signals but a zero IVV beta (h undefined): signals and targets of week 1 are carried (C3)
    signals = sector_signals(["XLK", "XLY"], ["XLP", "XLU"], n=3)
    signals.iloc[1] = sector_signals(["XLB", "XLE"], ["XLF", "XLI"]).iloc[0].to_numpy()
    betas = betas_frame([{"XLK": 1.2}, {"XLB": 1.5, HEDGE: 0.0}, {"XLK": 1.4}])
    with caplog.at_level(logging.WARNING, logger="src.sizing"):
        sized = target_weights(signals, betas, CORE, CAP, BAND)
    pd.testing.assert_series_equal(sized.weights.iloc[1], sized.weights.iloc[0], check_names=False)
    assert (sized.signals.iloc[1] == sized.signals.iloc[0]).all()
    assert sized.hedge.iloc[1] == sized.hedge.iloc[0]
    assert sized.weights.iloc[2]["XLK"] > 0 and sized.hedge.iloc[2] != sized.hedge.iloc[0]
    assert f"2010-01-15: BETA52 {HEDGE}" in caplog.text


def test_c3_missing_score_carries_the_target_weights_even_if_betas_change():
    index = weeks(3)
    scores = scores_frame([{"XLK": 3, "XLY": 2, "XLP": -2, "XLU": -3}] * 3, index)
    scores.iloc[1, 0] = np.nan
    betas = betas_frame([{"XLK": 1.2}, {"XLK": 1.9}, {"XLK": 1.9}], index)
    sized = size_book(scores, betas, CFG)
    pd.testing.assert_series_equal(sized.weights.iloc[1], sized.weights.iloc[0], check_names=False)
    assert sized.weights.iloc[2][HEDGE] != sized.weights.iloc[0][HEDGE]


def test_c3_flat_before_the_first_valid_week():
    signals = sector_signals(["XLK", "XLY"], ["XLP", "XLU"], n=3)
    betas = betas_frame([{}, {}, {}])
    betas.iloc[0, TRADED.index(HEDGE)] = np.nan  # warm-up: IVV beta not known yet
    sized = target_weights(signals, betas, CORE, CAP, BAND)
    assert list(sized.weights.index) == list(signals.index[1:])


def test_c3_every_beta_is_required_even_of_an_unheld_sector():
    # Amendment 2 C3: "any required BETA52 (9 sectors and IVV)". XLB has signal 0 but is in its beta warm-up (a leading
    # NaN, allowed by contract 10) in week 1: week 1 is not valid, so the book is flat until week 2
    signals = sector_signals(["XLK", "XLY"], ["XLP", "XLU"], n=2)
    betas = betas_frame([{}, {}])
    betas.iloc[0, TRADED.index("XLB")] = np.nan
    sized = target_weights(signals, betas, CORE, CAP, BAND)
    assert list(sized.weights.index) == list(signals.index[1:])


def test_betas_contract_is_enforced():
    signals = sector_signals(["XLK", "XLY"], ["XLP", "XLU"], n=3)
    betas = betas_frame([{}, {}, {}])
    betas.iloc[1, TRADED.index("XLB")] = np.nan  # a NaN after valid values breaks contract 10
    with pytest.raises(ContractError):
        target_weights(signals, betas, CORE, CAP, BAND)


@pytest.mark.parametrize("k,core", [(1, 0.5), (2, 0.25), (3, 1 / 6)])
def test_c4_sensitivity_core_weight(k, core):
    assert core_weight_for(k, CFG) == pytest.approx(core, abs=TOL)
    rng = np.random.default_rng(k)
    index = weeks(20)
    scores = pd.DataFrame(rng.normal(size=(20, 9)), index=index, columns=SECTORS)
    betas = pd.DataFrame(rng.uniform(0.5, 1.5, size=(20, 10)), index=index, columns=TRADED)
    sized = size_book(scores, betas, CFG, k=k)
    validate_weights(sized.weights, sized.signals, core_weight=core)
    validate_signals(sized.signals, top_k=k, bottom_k=k)
    # the core is 50% long and 50% short before the hedge scaling
    scale = 1 + sized.hedge.abs()
    long_core = sized.weights[SECTORS].clip(lower=0).sum(axis=1) * scale
    assert np.allclose(long_core, 0.5, atol=TOL)


def test_size_book_refuses_an_unregistered_k():
    with pytest.raises(ValueError):
        size_book(scores_frame([{}]), betas_frame([{}]), CFG, k=4)
