"""Validators, dataclasses and helpers of src/contracts.py, checked against docs/interfaces.md.

Every validator gets small hand-made valid objects that must pass, then one focused failure per invariant of the
contract. Settings (universe, signal parameters, split, costs) come from config.yaml.
"""

import copy
import dataclasses

import numpy as np
import pandas as pd
import pytest

from src import contracts
from src.config import load_config

ContractError = contracts.ContractError
SizingResult = contracts.SizingResult
BacktestResult = contracts.BacktestResult
WalkForwardFold = contracts.WalkForwardFold

CFG = load_config()
SECTORS = list(CFG["data"]["tickers"])
HEDGE = CFG["data"]["hedge"]
BENCHMARK = CFG["data"]["benchmark"]
TRADED = SECTORS + [HEDGE]
TRADABLES = TRADED + [BENCHMARK]
ASSET = list(CFG["features"]["asset"])
STATES = list(CFG["features"]["states"])
TOP_K, BOTTOM_K = CFG["signal"]["top_k"], CFG["signal"]["bottom_k"]
CORE = CFG["signal"]["core_weight"]  # 0.25
CAP = CFG["signal"]["hedge_cap"]  # 0.5
DEAD_BAND = CFG["signal"]["hedge_deadband"]  # 0.02
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
EMBARGO = CFG["split"]["embargo_weeks"]  # 1
COST_BPS = CFG["costs"]["bps_baseline"]  # 10
BORROW = CFG["costs"]["borrow_baseline"]  # 0.02
WEEK = ["date_open", "date_close"]
DAY = pd.Timedelta(days=1)


# ---------------------------------------------------------------- builders of valid objects


def week_index(open_dates, close_dates, names=WEEK) -> pd.MultiIndex:
    return pd.MultiIndex.from_arrays([pd.DatetimeIndex(open_dates), pd.DatetimeIndex(close_dates)], names=names)


def weekly_index(first_monday: str = "2019-11-25", n: int = 8) -> pd.MultiIndex:
    """n consecutive weeks (Monday, Friday). The default runs from the week of 25 Nov 2019 to the week of 13 Jan 2020."""
    mondays = pd.date_range(first_monday, periods=n, freq="7D")
    return week_index(mondays, mondays + 4 * DAY)


def daily_frame() -> pd.DataFrame:
    """Ten weekdays from Mon 6 Jan 2020, all tradables, IVV starting on the fourth session."""
    dates = pd.bdate_range("2020-01-06", periods=10, name="date")
    rng = np.random.default_rng(1)
    values = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(dates), len(TRADABLES))), axis=0))
    frame = pd.DataFrame(values, index=dates, columns=TRADABLES)
    frame.iloc[:3, frame.columns.get_loc(HEDGE)] = np.nan  # before IVV's first date
    return frame


def zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score per date_close, sample std (ddof=1)."""
    grouped = frame.groupby(level="date_close")
    return (frame - grouped.transform("mean")) / grouped.transform("std")


def features_frame(columns=None) -> pd.DataFrame:
    """Four Fridays x 9 sectors, z-scored; BETA52 still in warm-up (NaN) on the first Friday."""
    columns = list(columns or ASSET)
    fridays = pd.date_range("2019-11-29", periods=4, freq="7D")
    index = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    rng = np.random.default_rng(2)
    frame = zscore(pd.DataFrame(rng.normal(size=(len(index), len(columns))), index=index, columns=columns))
    if "BETA52" in columns:
        frame.loc[fridays[0], "BETA52"] = np.nan
    return frame


def states_frame() -> pd.DataFrame:
    """Market states on 6 weeks, unscaled, with a warm-up first row."""
    index = weekly_index(n=6)
    states = pd.DataFrame(
        {"BEAR24": [np.nan, 0.0, 0.0, 1.0, 1.0, 0.0], "MKT_VAR": [np.nan, 1e-4, 1.2e-4, 1.1e-4, 0.9e-4, 1e-4],
         "VIX_Z": [np.nan, 13.1, 12.6, 14.0, 15.2, 13.8], "TERM": [np.nan, 0.3, 0.25, 0.28, 0.31, 0.27],
         "CREDIT": [np.nan, 2.1, 2.05, 2.0, 2.02, 2.04]}, index=index)
    return states[STATES]


def forward_objects(n: int = 8):
    """fwd, realised_on, period on the 8 weeks from 25 Nov 2019.

    Row t is realised at date_open of week t+2: rows 0..5 at 9, 16, 23, 30 Dec 2019, 6, 13 Jan 2020; rows 6, 7 NaT.
    Row 2 (week ending Fri 2019-12-13) is realised Mon 2019-12-23 <= 2019-12-27 -> "IS" (the last IS signal week);
    row 3 (week ending 2019-12-20) is realised Mon 2019-12-30 > 2019-12-27 -> "OOS".
    """
    index = weekly_index(n=n)
    rng = np.random.default_rng(3)
    opens = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, len(TRADABLES))), axis=0)), index=index,
                         columns=TRADABLES)
    fwd = opens.shift(-2) / opens.shift(-1) - 1  # O(t+2)/O(t+1) - 1, NaN on the last two rows
    date_open = index.get_level_values("date_open")
    realised_on = pd.Series(list(date_open[2:]) + [pd.NaT, pd.NaT], index=index, name="realised_on")
    labels = ["IS" if day <= IS_END else "OOS" for day in realised_on.iloc[:-2]] + [None, None]
    period = pd.Series(labels, index=index, name="period")
    return fwd, realised_on, period


def labels_frame() -> pd.DataFrame:
    """Labels of the 6 weeks with a defined forward return: y demeaned over the 9 sectors, label_end = O(t+2) session."""
    fwd, realised_on, _ = forward_objects()
    keep = realised_on.notna()
    fwd, realised_on = fwd.loc[keep, SECTORS], realised_on[keep]
    y = fwd.sub(fwd.mean(axis=1), axis=0)  # sums to 0 across the 9 sectors
    fridays = fwd.index.get_level_values("date_close")
    index = pd.MultiIndex.from_product([fridays, SECTORS], names=["date_close", "ticker"])
    return pd.DataFrame({"y": y.to_numpy().ravel(),
                         "label_end": np.repeat(realised_on.to_numpy(), len(SECTORS))}, index=index)


def scores_frame() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    scores = pd.DataFrame(rng.normal(size=(4, len(SECTORS))), index=weekly_index(n=4), columns=SECTORS)
    scores.iloc[1, 3] = np.nan  # a missing score is allowed
    return scores


# Sizing example: 4 weeks from Mon 2 Dec 2019. Raw BETA52 (columns TRADED), sector longs and shorts per week.
SIZING_INDEX = weekly_index("2019-12-02", 4)  # Fridays 6, 13, 20, 27 Dec 2019
_BASE_BETA = {"XLB": 1.1, "XLE": 1.2, "XLF": 1.3, "XLI": 1.0, "XLK": 1.4, "XLP": 0.6, "XLU": 0.5, "XLV": 0.8, "XLY": 1.2,
              "IVV": 1.0}
BETA_ROWS = [
    _BASE_BETA,
    _BASE_BETA,
    {**_BASE_BETA, "IVV": 0.7},
    {**_BASE_BETA, "XLI": 0.96},
]
LEGS = [
    (("XLK", "XLY"), ("XLP", "XLU")),  # β_c = 0.25 (1.4 + 1.2 - 0.6 - 0.5) = 0.375; h = -0.375 / 1.0 = -0.375
    (("XLP", "XLU"), ("XLE", "XLK")),  # β_c = 0.25 (0.6 + 0.5 - 1.2 - 1.4) = -0.375; h = +0.375
    (("XLK", "XLY"), ("XLP", "XLU")),  # β_c = 0.375, β_IVV = 0.7: -0.5357 -> clipped to h = -0.5 (cap binds)
    (("XLB", "XLE"), ("XLF", "XLI")),  # β_c = 0.25 (1.1 + 1.2 - 1.3 - 0.96) = 0.01; |h| = 0.01 < 0.02 -> h = 0
]


def betas_frame() -> pd.DataFrame:
    return pd.DataFrame(BETA_ROWS, index=SIZING_INDEX)[TRADED].astype("float64")


def sector_signals() -> pd.DataFrame:
    rows = []
    for longs, shorts in LEGS:
        rows.append({ticker: (1 if ticker in longs else -1 if ticker in shorts else 0) for ticker in SECTORS})
    return pd.DataFrame(rows, index=SIZING_INDEX)[SECTORS].astype("int8")


def sizing() -> SizingResult:
    """The §09 formulas row by row:
    β_c = Σ 0.25 s_i β̂_i;  h = clip(-β_c / β̂_IVV, -0.5, 0.5), 0 if |h| < 0.02;
    w_i = 0.25 s_i / (1 + |h|);  w_IVV = h / (1 + |h|);  β_res = (β_c + h β̂_IVV) / (1 + |h|).
    """
    signals, betas = sector_signals(), betas_frame()
    weights = pd.DataFrame(0.0, index=SIZING_INDEX, columns=TRADED)
    all_signals = pd.DataFrame(0, index=SIZING_INDEX, columns=TRADED, dtype="int8")
    hedge, residual, cap_binds = [], [], []
    for t in SIZING_INDEX:
        s = signals.loc[t].astype("float64")
        b = betas.loc[t]
        beta_c = float((CORE * s * b[SECTORS]).sum())
        ratio = -beta_c / b[HEDGE]
        h = float(np.clip(ratio, -CAP, CAP))
        if abs(h) < DEAD_BAND:
            h = 0.0
        weights.loc[t, SECTORS] = (CORE * s / (1 + abs(h))).to_numpy()
        weights.loc[t, HEDGE] = h / (1 + abs(h))
        all_signals.loc[t, SECTORS] = signals.loc[t].to_numpy()
        all_signals.loc[t, HEDGE] = int(np.sign(h))
        hedge.append(h)
        residual.append((beta_c + h * b[HEDGE]) / (1 + abs(h)))
        cap_binds.append(bool(abs(ratio) > CAP))
    hedge = pd.Series(hedge, index=SIZING_INDEX, name="hedge", dtype="float64")
    return SizingResult(
        weights=weights,
        signals=all_signals.astype("int8"),
        hedge=hedge,
        residual_beta=pd.Series(residual, index=SIZING_INDEX, name="residual_beta", dtype="float64"),
        net_exposure=(hedge / (1 + hedge.abs())).rename("net_exposure"),
        cap_binds=pd.Series(cap_binds, index=SIZING_INDEX, name="cap_binds", dtype="bool"),
    )


def backtest_result(cost_bps: float = COST_BPS, borrow_annual: float = BORROW) -> BacktestResult:
    """The §09 accounting on the sizing example with hand-chosen forward returns of the traded columns.

    Periods: weeks ending 6, 13 Dec are realised 16, 23 Dec (IS); weeks ending 20, 27 Dec are realised 30 Dec, 6 Jan (OOS).
    """
    size = sizing()
    w = size.weights
    rng = np.random.default_rng(5)
    fwd = pd.DataFrame(rng.normal(0.001, 0.02, w.shape), index=SIZING_INDEX, columns=TRADED)
    gross = (w * fwd).sum(axis=1)
    w_pre = pd.DataFrame(0.0, index=SIZING_INDEX, columns=TRADED)  # entered from cash in the first week
    for i in range(1, len(SIZING_INDEX)):
        w_pre.iloc[i] = (w.iloc[i - 1] * (1 + fwd.iloc[i - 1]) / (1 + gross.iloc[i - 1])).to_numpy()
    turnover = (w - w_pre).abs().sum(axis=1)
    costs = cost_bps / 10_000 * turnover
    borrow = borrow_annual * 7 / 365 * w.clip(upper=0).abs().sum(axis=1)
    net = gross - costs - borrow
    return BacktestResult(
        weights=w,
        gross=gross.rename("gross"),
        net=net.rename("net"),
        turnover=turnover.rename("turnover"),
        costs=costs.rename("costs"),
        borrow=borrow.rename("borrow"),
        residual_beta=size.residual_beta.rename("residual_beta"),
        net_exposure=size.net_exposure.rename("net_exposure"),
        hedge=size.hedge.rename("hedge"),
        period=pd.Series(["IS", "IS", "OOS", "OOS"], index=SIZING_INDEX, name="period"),
    )


TRAIN_START = pd.Timestamp("2003-01-03")  # first date_close after split.warmup_end


def fold(year: int, refit: int, test_start: pd.Timestamp, test_end: pd.Timestamp) -> WalkForwardFold:
    """purge_end = test_start - 7 days x embargo. label_end of week t is about date_close + 10 days (Monday of week t+2),
    so the last week with label_end <= purge_end ends 14 days before purge_end: train_end = test_start - 7 x embargo - 14."""
    purge_end = test_start - pd.Timedelta(days=7 * EMBARGO)
    return WalkForwardFold(test_year=year, refit=refit, train_start=TRAIN_START, train_end=purge_end - 14 * DAY,
                           purge_end=purge_end, test_start=test_start, test_end=test_end)


def folds_list() -> list[WalkForwardFold]:
    """Quarterly refits of 2008 and 2009: the first Friday of each quarter; consecutive test windows touch without gaps."""
    fridays = pd.date_range("2008-01-01", "2009-12-31", freq="W-FRI")
    starts = [(year, q, fridays[(fridays.year == year) & (fridays.quarter == q)][0]) for year in (2008, 2009) for q in (1, 2, 3, 4)]
    out = []
    for i, (year, q, start) in enumerate(starts):
        end = starts[i + 1][2] - 7 * DAY if i + 1 < len(starts) else fridays[-1]
        out.append(fold(year, q, start, end))
    return out


def with_value(frame: pd.DataFrame, row: int, column: str, value) -> pd.DataFrame:
    out = frame.copy()
    out.iloc[row, out.columns.get_loc(column)] = value
    return out


def with_index(frame, index):
    out = frame.copy()
    out.index = index
    return out


# ---------------------------------------------------------------- ContractError, universe, interactions


def test_contract_error_is_value_error():
    assert issubclass(ContractError, ValueError)


def test_universe_from_config():
    u = contracts.universe()
    assert u.sectors == tuple(SECTORS) == ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
    assert u.hedge == HEDGE == "IVV"
    assert u.benchmark == BENCHMARK == "SPY"
    assert u.traded == tuple(TRADED) and len(u.traded) == 10
    assert u.tradables == tuple(TRADABLES) and len(u.tradables) == 11
    assert isinstance(u.sectors, tuple) and isinstance(u.traded, tuple) and isinstance(u.tradables, tuple)
    assert contracts.universe(CFG) == u


def test_universe_follows_the_config_given():
    cfg = copy.deepcopy(CFG)
    cfg["data"]["tickers"] = ["XLB", "XLE", "XLF", "XLK"]
    u = contracts.universe(cfg)
    assert u.sectors == ("XLB", "XLE", "XLF", "XLK")
    assert u.traded == ("XLB", "XLE", "XLF", "XLK", "IVV")
    assert u.tradables == ("XLB", "XLE", "XLF", "XLK", "IVV", "SPY")


def test_interaction_name():
    assert contracts.interaction_name(("BETA52", "BEAR24")) == "BETA52_x_BEAR24"
    assert contracts.interaction_name(["BETA52", "BEAR24", "MKT_VAR"]) == "BETA52_x_BEAR24_x_MKT_VAR"


def test_interaction_columns():
    expected = ["BETA52_x_BEAR24_x_MKT_VAR", "BETA52_x_BEAR24", "MOM26_1_x_BEAR24", "MOM26_1_x_MKT_VAR", "VOL13_x_VIX_Z"]
    assert contracts.interaction_columns() == expected
    assert contracts.interaction_columns(CFG) == ["_x_".join(terms) for terms in CFG["features"]["interactions"]]
    cfg = copy.deepcopy(CFG)
    cfg["features"]["interactions"] = [["VOL13", "VIX_Z"], ["BETA52", "BEAR24"]]
    assert contracts.interaction_columns(cfg) == ["VOL13_x_VIX_Z", "BETA52_x_BEAR24"]


# ---------------------------------------------------------------- dataclasses

FIELDS = {
    contracts.Universe: ["sectors", "hedge", "benchmark", "traded", "tradables"],
    SizingResult: ["weights", "signals", "hedge", "residual_beta", "net_exposure", "cap_binds"],
    BacktestResult: ["weights", "gross", "net", "turnover", "costs", "borrow", "residual_beta", "net_exposure", "hedge",
                     "period"],
    WalkForwardFold: ["test_year", "refit", "train_start", "train_end", "purge_end", "test_start", "test_end"],
}


@pytest.mark.parametrize("cls", list(FIELDS), ids=lambda cls: cls.__name__)
def test_dataclass_field_names_in_order(cls):
    assert dataclasses.is_dataclass(cls)
    assert [field.name for field in dataclasses.fields(cls)] == FIELDS[cls]


@pytest.mark.parametrize("make", [contracts.universe, sizing, backtest_result, lambda: folds_list()[0]],
                         ids=["Universe", "SizingResult", "BacktestResult", "WalkForwardFold"])
def test_dataclass_is_frozen(make):
    instance = make()
    first = dataclasses.fields(instance)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, first, None)


def test_backtest_result_reexported_from_backtest():
    from src import backtest

    assert backtest.BacktestResult is BacktestResult


# ---------------------------------------------------------------- hand-computed sizing example (the fixture itself)


def test_hand_sizing_numbers():
    size = sizing()
    w, h = size.weights, size.hedge
    # week 1: h = -0.375; w_XLK = 0.25 / 1.375 = 0.181818..; w_IVV = -0.375 / 1.375 = -0.272727..
    assert h.iloc[0] == pytest.approx(-0.375)
    assert w.iloc[0]["XLK"] == pytest.approx(0.25 / 1.375) == pytest.approx(0.18181818)
    assert w.iloc[0]["XLP"] == pytest.approx(-0.18181818)
    assert w.iloc[0]["IVV"] == pytest.approx(-0.27272727)
    # week 2: the defensive long book is hedged long: h = +0.375
    assert h.iloc[1] == pytest.approx(0.375) and w.iloc[1]["IVV"] == pytest.approx(0.27272727)
    # week 3: cap binds, h = -0.5, w_IVV = -0.5 / 1.5 = -1/3 = -cap / (1 + cap); β_res = (0.375 - 0.5 * 0.7) / 1.5 = 0.016667
    assert h.iloc[2] == -0.5 and w.iloc[2]["IVV"] == pytest.approx(-1 / 3) and w.iloc[2]["XLK"] == pytest.approx(1 / 6)
    assert size.residual_beta.iloc[2] == pytest.approx(0.025 / 1.5)
    # week 4: dead-band, h = 0, plain 0.25 weights, β_res = β_c = 0.01
    assert h.iloc[3] == 0.0 and w.iloc[3]["XLB"] == 0.25 and w.iloc[3]["IVV"] == 0.0
    assert size.residual_beta.iloc[3] == pytest.approx(0.01)
    assert list(size.cap_binds) == [False, False, True, False]
    assert list(size.signals[HEDGE]) == [-1, 1, -1, 0]
    assert abs(size.residual_beta.iloc[0]) < 1e-12 and abs(size.residual_beta.iloc[1]) < 1e-12
    np.testing.assert_allclose(w.abs().sum(axis=1), 1.0, atol=1e-12)


def test_hand_backtest_numbers():
    result = backtest_result()
    # first week entered from cash: turnover = Σ|w| = 1; costs = 10 bps x 1 = 0.0010;
    # borrow = 0.02 x 7/365 x (2 x 0.181818 + 0.272727) = 0.02 x 0.0191781 x 0.636364 = 0.000244085
    assert result.turnover.iloc[0] == pytest.approx(1.0)
    assert result.costs.iloc[0] == pytest.approx(0.0010)
    assert result.borrow.iloc[0] == pytest.approx(0.000244085, rel=1e-5)


# ---------------------------------------------------------------- validate_weekly_index

GOOD_INDEX = weekly_index()
_OPEN = GOOD_INDEX.get_level_values("date_open")
_CLOSE = GOOD_INDEX.get_level_values("date_close")


def test_weekly_index_valid():
    contracts.validate_weekly_index(GOOD_INDEX)
    contracts.validate_weekly_index(weekly_index("2019-12-23", 2))  # holiday weeks keep their nominal labels


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_weekly_index_any_datetime_resolution(unit):
    contracts.validate_weekly_index(week_index(_OPEN.as_unit(unit), _CLOSE.as_unit(unit)))


BAD_WEEK_INDEXES = {
    "wrong level names": GOOD_INDEX.set_names(["monday", "friday"]),
    "levels swapped": week_index(_CLOSE, _OPEN),
    "date_open not a Monday": week_index(_OPEN + DAY, _CLOSE + DAY),
    "date_close not date_open + 4 days": week_index(_OPEN, _OPEN + 3 * DAY),
    "duplicate week": week_index(list(_OPEN) + [_OPEN[-1]], list(_CLOSE) + [_CLOSE[-1]]),
    "unsorted": GOOD_INDEX[::-1],
    "not a MultiIndex": pd.DatetimeIndex(_CLOSE, name="date_close"),
}


@pytest.mark.parametrize("name", list(BAD_WEEK_INDEXES))
def test_weekly_index_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_weekly_index(BAD_WEEK_INDEXES[name])


# ---------------------------------------------------------------- validate_daily_frame


def test_daily_frame_valid():
    frame = daily_frame()
    contracts.validate_daily_frame(frame)
    contracts.validate_daily_frame(frame[["XLB", "XLK", "SPY"]])  # a subset in universe order
    contracts.validate_daily_frame(frame[SECTORS], columns=SECTORS)


def _reordered_columns(frame):
    return frame[["XLE", "XLB"] + TRADABLES[2:]]


def _dates_replaced(frame, position, day):
    dates = list(frame.index)
    dates[position] = pd.Timestamp(day)
    return with_index(frame, pd.DatetimeIndex(dates, name="date"))


BAD_DAILY = {
    "index not named date": lambda f: with_index(f, f.index.rename("Date")),
    "weekend date": lambda f: _dates_replaced(f, 5, "2020-01-11"),  # Mon 13 Jan -> Sat 11 Jan, still increasing
    "duplicate date": lambda f: _dates_replaced(f, 5, "2020-01-10"),
    "unsorted": lambda f: f.iloc[::-1],
    "columns out of universe order": _reordered_columns,
    "unknown column": lambda f: f.rename(columns={"XLB": "AAPL"}),
    "float32": lambda f: f.astype("float32"),
    "zero price": lambda f: with_value(f, 4, "XLK", 0.0),
    "negative price": lambda f: with_value(f, 4, "XLK", -1.0),
    "NaN after the first date": lambda f: with_value(f, 6, "XLB", np.nan),
}


@pytest.mark.parametrize("name", list(BAD_DAILY))
def test_daily_frame_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_daily_frame(BAD_DAILY[name](daily_frame()))


def test_daily_frame_columns_restrict_the_allowed_set():
    with pytest.raises(ContractError):
        contracts.validate_daily_frame(daily_frame(), columns=SECTORS)  # IVV and SPY not allowed here


# ---------------------------------------------------------------- validate_features


def test_features_valid():
    contracts.validate_features(features_frame())
    contracts.validate_features(features_frame(ASSET), columns=ASSET)


def test_features_custom_columns():
    variants = ["MOM13_1", "MOM26_1", "MOM52_1"]
    frame = features_frame(variants)
    contracts.validate_features(frame, columns=variants)
    with pytest.raises(ContractError):
        contracts.validate_features(frame)  # default columns are the six asset features
    with pytest.raises(ContractError):
        contracts.validate_features(frame, columns=["MOM26_1", "MOM13_1", "MOM52_1"])  # exact order


def test_features_week_with_equal_raw_values_has_zero_z():
    frame = features_frame()
    frame.loc[frame.index.get_level_values("date_close")[-1], "REV1"] = 0.0  # every sector equal -> z = 0
    contracts.validate_features(frame)


def _features_non_friday(frame):
    dates = frame.index.get_level_values("date_close") - DAY  # Thursdays
    return with_index(frame, pd.MultiIndex.from_arrays([dates, frame.index.get_level_values("ticker")],
                                                       names=["date_close", "ticker"]))


def _features_ticker_replaced(frame):
    tickers = ["IVV" if ticker == "XLB" else ticker for ticker in frame.index.get_level_values("ticker")]
    return with_index(frame, pd.MultiIndex.from_arrays([frame.index.get_level_values("date_close"), tickers],
                                                       names=["date_close", "ticker"]))


BAD_FEATURES = {
    "wrong index names": lambda f: with_index(f, f.index.set_names(["date", "ticker"])),
    "columns out of order": lambda f: f[ASSET[::-1]],
    "missing column": lambda f: f.drop(columns="DD13"),
    "extra column": lambda f: f.assign(EXTRA=0.0),
    "float32": lambda f: f.astype("float32"),
    "+inf": lambda f: with_value(f, 12, "REV1", np.inf),
    "-inf": lambda f: with_value(f, 12, "VOL13", -np.inf),
    "a sector missing on a date": lambda f: f.drop(index=f.index[10]),
    "unsorted": lambda f: f.iloc[::-1],
    "ticker outside the sectors": _features_ticker_replaced,
    "date_close not a Friday": _features_non_friday,
    "NaN after the warm-up": lambda f: with_value(f, 20, "MOM26_1", np.nan),
}


@pytest.mark.parametrize("name", list(BAD_FEATURES))
def test_features_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_features(BAD_FEATURES[name](features_frame()))


# ---------------------------------------------------------------- validate_market_states


def test_market_states_valid():
    contracts.validate_market_states(states_frame())


BAD_STATES = {
    "columns out of order": lambda f: f[STATES[::-1]],
    "extra column": lambda f: f.assign(EXTRA=0.0),
    "missing column": lambda f: f.drop(columns="TERM"),
    "float32": lambda f: f.astype("float32"),
    "NaN after the warm-up": lambda f: with_value(f, 3, "VIX_Z", np.nan),
    "unsorted weeks": lambda f: f.iloc[::-1],
    "index not the weekly index": lambda f: with_index(f, f.index.get_level_values("date_close")),
}


@pytest.mark.parametrize("name", list(BAD_STATES))
def test_market_states_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_market_states(BAD_STATES[name](states_frame()))


# ---------------------------------------------------------------- validate_labels


def test_labels_valid():
    labels = labels_frame()
    assert len(labels) == 6 * 9  # the last two weeks have no forward return
    contracts.validate_labels(labels)


def _label_end_varies(labels):
    out = labels.copy()
    out.iloc[1, out.columns.get_loc("label_end")] = out["label_end"].iloc[1] + DAY  # one sector of week 1 differs
    return out


def _label_end_at_close(labels):
    out = labels.copy()
    out["label_end"] = labels.index.get_level_values("date_close")
    return out


def _label_end_before_close(labels):
    out = labels.copy()
    out["label_end"] = labels.index.get_level_values("date_close") - 4 * DAY
    return out


BAD_LABELS = {
    "y does not sum to zero": lambda f: with_value(f, 0, "y", f["y"].iloc[0] + 1e-9),
    "label_end varies within a week": _label_end_varies,
    "label_end equals date_close": _label_end_at_close,
    "label_end before date_close": _label_end_before_close,
    "a sector missing": lambda f: f.drop(index=f.index[4]),
    "y float32": lambda f: f.astype({"y": "float32"}),
    "extra column": lambda f: f.assign(extra=0.0),
    "columns out of order": lambda f: f[["label_end", "y"]],
    "unsorted": lambda f: f.iloc[::-1],
    "wrong index names": lambda f: with_index(f, f.index.set_names(["date", "ticker"])),
}


@pytest.mark.parametrize("name", list(BAD_LABELS))
def test_labels_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_labels(BAD_LABELS[name](labels_frame()))


# ---------------------------------------------------------------- validate_scores


def test_scores_valid_with_a_missing_score():
    contracts.validate_scores(scores_frame())


BAD_SCORES = {
    "+inf": lambda f: with_value(f, 0, "XLK", np.inf),
    "-inf": lambda f: with_value(f, 2, "XLB", -np.inf),
    "IVV column": lambda f: f.assign(IVV=0.0),
    "columns out of order": lambda f: f[SECTORS[::-1]],
    "missing sector": lambda f: f.drop(columns="XLY"),
    "float32": lambda f: f.astype("float32"),
    "unsorted weeks": lambda f: f.iloc[::-1],
    "wrong index level names": lambda f: with_index(f, f.index.set_names(["open", "close"])),
}


@pytest.mark.parametrize("name", list(BAD_SCORES))
def test_scores_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_scores(BAD_SCORES[name](scores_frame()))


# ---------------------------------------------------------------- validate_signals


def test_signals_valid():
    signals = sizing().signals
    assert signals.dtypes.eq("int8").all()
    contracts.validate_signals(signals)
    contracts.validate_signals(signals, top_k=TOP_K, bottom_k=BOTTOM_K)


def test_signals_sensitivity_k():
    values = {ticker: [1 if ticker == "XLK" else -1 if ticker == "XLU" else 0] * len(SIZING_INDEX) for ticker in TRADED}
    signals = pd.DataFrame(values, index=SIZING_INDEX)[TRADED].astype("int8")  # one +1 and one -1 per week
    contracts.validate_signals(signals, top_k=1, bottom_k=1)
    with pytest.raises(ContractError):
        contracts.validate_signals(signals)  # default k = 2


def _three_longs(signals):
    out = signals.copy()
    out.iloc[0, out.columns.get_loc("XLV")] = 1  # XLV was 0 in week 1
    return out


def _sector_moved(signals):
    out = signals.copy()
    out.iloc[0, out.columns.get_loc("XLK")] = 0
    out.iloc[0, out.columns.get_loc("XLB")] = 1
    return out


BAD_SIGNALS = {
    "int64": lambda f: f.astype("int64"),
    "float64": lambda f: f.astype("float64"),
    "value 2": lambda f: with_value(f, 0, "XLK", 2),
    "three +1": _three_longs,
    "a +1 removed": lambda f: with_value(f, 1, "XLP", 0),
    "IVV 2": lambda f: with_value(f, 0, HEDGE, 2),
    "IVV column missing": lambda f: f.drop(columns=HEDGE),
    "IVV first": lambda f: f[[HEDGE] + SECTORS],
    "benchmark column": lambda f: f.assign(SPY=np.int8(0)),
    "unsorted weeks": lambda f: f.iloc[::-1],
}


@pytest.mark.parametrize("name", list(BAD_SIGNALS))
def test_signals_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_signals(BAD_SIGNALS[name](sizing().signals))


# ---------------------------------------------------------------- validate_betas


def test_betas_valid():
    contracts.validate_betas(betas_frame())
    warm = pd.concat([pd.DataFrame(np.nan, index=weekly_index("2019-11-25", 1), columns=TRADED), betas_frame()])
    contracts.validate_betas(warm)  # NaN in the warm-up week


BAD_BETAS = {
    "IVV missing": lambda f: f.drop(columns=HEDGE),
    "columns out of order": lambda f: f[TRADED[::-1]],
    "float32": lambda f: f.astype("float32"),
    "NaN after the warm-up": lambda f: with_value(f, 2, "XLE", np.nan),
    "unsorted weeks": lambda f: f.iloc[::-1],
}


@pytest.mark.parametrize("name", list(BAD_BETAS))
def test_betas_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_betas(BAD_BETAS[name](betas_frame()))


# ---------------------------------------------------------------- validate_weights


def test_weights_valid():
    size = sizing()
    contracts.validate_weights(size.weights)
    contracts.validate_weights(size.weights, signals=size.signals)


def test_weights_within_tolerance():
    weights = sizing().weights.copy()
    weights.iloc[0, weights.columns.get_loc(HEDGE)] -= 1e-13  # Σ|w| off by 1e-13 < 1e-12
    contracts.validate_weights(weights)


def test_weights_flat_row_allowed():
    weights = sizing().weights.copy()
    weights.iloc[1] = 0.0  # an all-zero row is flat
    contracts.validate_weights(weights)


def _off_by(weights):
    return weights * (1 + 1e-9)  # Σ|w| = 1 + 1e-9


def _not_neutral(weights):
    out = weights.copy()  # week 1: longs +0.005, shorts -0.005 smaller in size: Σ|w| unchanged, Σ_sectors w = 0.02
    out.iloc[0, out.columns.get_indexer(["XLK", "XLY"])] += 0.005
    out.iloc[0, out.columns.get_indexer(["XLP", "XLU"])] += 0.005
    return out


def _unequal_legs(weights):
    out = weights.copy()  # week 1: XLK 0.186818, XLY 0.176818; still neutral and Σ|w| = 1
    out.iloc[0, out.columns.get_loc("XLK")] += 0.005
    out.iloc[0, out.columns.get_loc("XLY")] -= 0.005
    return out


def _hedge_above_cap(weights):
    # h = -0.6 (above the cap): w_IVV = -0.6 / 1.6 = -0.375 > 0.5 / 1.5; sectors ±0.25 / 1.6 = ±0.15625
    # Σ|w| = (1 + 0.6) / 1.6 = 1; legs equal 0.25 (1 - 0.375) = 0.15625; only the cap is broken
    out = weights.copy()
    s = np.sign(out.iloc[0][SECTORS])
    out.iloc[0, out.columns.get_indexer(SECTORS)] = (0.25 * s / 1.6).to_numpy()
    out.iloc[0, out.columns.get_loc(HEDGE)] = -0.6 / 1.6
    return out


BAD_WEIGHTS = {
    "sum of |w| off by 1e-9": _off_by,
    "sector legs not dollar-neutral": _not_neutral,
    "unequal leg sizes": _unequal_legs,
    "|w_IVV| above cap / (1 + cap)": _hedge_above_cap,
    "float32": lambda f: f.astype("float32"),
    "columns out of order": lambda f: f[TRADED[::-1]],
    "IVV missing": lambda f: f.drop(columns=HEDGE),
    "unsorted weeks": lambda f: f.iloc[::-1],
}


@pytest.mark.parametrize("name", list(BAD_WEIGHTS))
def test_weights_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_weights(BAD_WEIGHTS[name](sizing().weights))


def test_weights_sector_sign_mismatch_with_signals():
    size = sizing()
    signals = _sector_moved(size.signals)  # still a valid signal row, but XLK holds +w while its signal is 0
    with pytest.raises(ContractError):
        contracts.validate_weights(size.weights, signals=signals)


def test_weights_hedge_sign_mismatch_with_signals():
    size = sizing()
    signals = with_value(size.signals, 0, HEDGE, 1)  # w_IVV < 0 in week 1
    with pytest.raises(ContractError):
        contracts.validate_weights(size.weights, signals=signals)


# ---------------------------------------------------------------- validate_forward_returns


def test_forward_returns_valid():
    fwd, realised_on, period = forward_objects()
    assert list(period.iloc[:6]) == ["IS", "IS", "IS", "OOS", "OOS", "OOS"]
    assert realised_on.iloc[2] == pd.Timestamp("2019-12-23") and realised_on.iloc[3] == pd.Timestamp("2019-12-30")
    contracts.validate_forward_returns(fwd, realised_on, period)
    contracts.validate_forward_returns(fwd, realised_on, period, is_end=IS_END)


def test_forward_returns_is_end_inclusive():
    # realised_on is always a Monday, so the inclusive rule realised_on <= is_end is tested with is_end on a Monday:
    # with is_end = 2019-12-30, the row realised exactly on 2019-12-30 is "IS"
    fwd, realised_on, period = forward_objects()
    is_end = pd.Timestamp("2019-12-30")
    period = period.copy()
    period.iloc[3] = "IS"
    contracts.validate_forward_returns(fwd, realised_on, period, is_end=is_end)
    with pytest.raises(ContractError):
        contracts.validate_forward_returns(fwd, realised_on, period)  # default is_end 2019-12-27: row 3 is OOS


def _set(series, position, value):
    out = series.copy()
    out.iloc[position] = value
    return out


BAD_FORWARD = {
    "realised_on not date_open of t+2": lambda f, r, p: (f, _set(r, 1, r.iloc[1] + 7 * DAY), p),
    "realised_on set on the last row": lambda f, r, p: (f, _set(r, 7, pd.Timestamp("2020-01-27")), p),
    "last row of fwd not NaN": lambda f, r, p: (with_value(f, 7, "XLK", 0.01), r, p),
    "second-last row of fwd not NaN": lambda f, r, p: (with_value(f, 6, "SPY", 0.01), r, p),
    "realised 2019-12-23 labelled OOS": lambda f, r, p: (f, r, _set(p, 2, "OOS")),
    "realised 2019-12-30 labelled IS": lambda f, r, p: (f, r, _set(p, 3, "IS")),
    "period present where realised_on is NaT": lambda f, r, p: (f, r, _set(p, 7, "OOS")),
    "period value not IS/OOS": lambda f, r, p: (f, r, _set(p, 0, "TRAIN")),
    "fwd without the benchmark": lambda f, r, p: (f[TRADED], r, p),
    "fwd columns out of order": lambda f, r, p: (f[TRADABLES[::-1]], r, p),
    "fwd float32": lambda f, r, p: (f.astype("float32"), r, p),
    "realised_on misnamed": lambda f, r, p: (f, r.rename("label_end"), p),
    "period misnamed": lambda f, r, p: (f, r, p.rename("split")),
    "realised_on on another index": lambda f, r, p: (f, with_index(r, weekly_index("2019-12-02", 8)), p),
}


@pytest.mark.parametrize("name", list(BAD_FORWARD))
def test_forward_returns_invalid(name):
    fwd, realised_on, period = BAD_FORWARD[name](*forward_objects())
    with pytest.raises(ContractError):
        contracts.validate_forward_returns(fwd, realised_on, period)


# ---------------------------------------------------------------- validate_backtest_result


def test_backtest_result_valid():
    result = backtest_result()
    contracts.validate_weights(result.weights)
    contracts.validate_backtest_result(result)
    contracts.validate_backtest_result(result, cost_bps=COST_BPS, borrow_annual=BORROW)


def test_backtest_result_stress_rates():
    result = backtest_result(cost_bps=20, borrow_annual=0.05)
    contracts.validate_backtest_result(result, cost_bps=20, borrow_annual=0.05)


def _replace(result, **changes):
    return dataclasses.replace(result, **changes)


def _net_off(r):
    return _replace(r, net=r.net + 1e-9)


def _gross_other_index(r):
    return _replace(r, gross=with_index(r.gross, weekly_index("2019-12-09", 4)))


def _negative_turnover(r):
    return _replace(r, turnover=_set(r.turnover, 1, -0.1))


def _negative_costs(r):
    costs = _set(r.costs, 0, -0.001)
    return _replace(r, costs=costs, net=(r.gross - costs - r.borrow).rename("net"))


def _negative_borrow(r):
    borrow = _set(r.borrow, 0, -0.001)
    return _replace(r, borrow=borrow, net=(r.gross - r.costs - borrow).rename("net"))


def _net_exposure_off(r):
    return _replace(r, net_exposure=r.net_exposure + 1e-9)


def _hedge_off(r):
    return _replace(r, hedge=_set(r.hedge, 0, r.hedge.iloc[0] + 1e-6))  # w_IVV no longer h / (1 + |h|)


def _weights_off(r):
    return _replace(r, weights=r.weights * (1 + 1e-9))


BAD_BACKTEST = {
    "net != gross - costs - borrow": _net_off,
    "gross on another index": _gross_other_index,
    "gross misnamed": lambda r: _replace(r, gross=r.gross.rename("gross_return")),
    "net misnamed": lambda r: _replace(r, net=r.net.rename("returns")),
    "negative turnover": _negative_turnover,
    "negative costs": _negative_costs,
    "negative borrow": _negative_borrow,
    "net_exposure != sum of w": _net_exposure_off,
    "w_IVV != h / (1 + |h|)": _hedge_off,
    "weights break the weight contract": _weights_off,
    "period value not IS/OOS": lambda r: _replace(r, period=_set(r.period, 0, "TEST")),
}


@pytest.mark.parametrize("name", list(BAD_BACKTEST))
def test_backtest_result_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_backtest_result(BAD_BACKTEST[name](backtest_result()))


def test_backtest_result_wrong_cost_rate():
    with pytest.raises(ContractError):
        contracts.validate_backtest_result(backtest_result(), cost_bps=20, borrow_annual=BORROW)


def test_backtest_result_wrong_borrow_rate():
    with pytest.raises(ContractError):
        contracts.validate_backtest_result(backtest_result(), cost_bps=COST_BPS, borrow_annual=0.05)


def test_backtest_result_costs_not_from_turnover():
    r = backtest_result()
    costs = r.costs + 1e-9  # net kept consistent, so only the cost formula is broken
    broken = _replace(r, costs=costs, net=(r.gross - costs - r.borrow).rename("net"))
    contracts.validate_backtest_result(broken)  # without rates the formula is not checked
    with pytest.raises(ContractError):
        contracts.validate_backtest_result(broken, cost_bps=COST_BPS, borrow_annual=BORROW)


# ---------------------------------------------------------------- validate_folds


def test_folds_valid():
    folds = folds_list()
    assert len(folds) == 8
    assert folds[0].test_start == pd.Timestamp("2008-01-04") and folds[0].purge_end == pd.Timestamp("2007-12-28")
    assert folds[0].train_end == pd.Timestamp("2007-12-14") and folds[0].test_end == pd.Timestamp("2008-03-28")
    contracts.validate_folds(folds)
    contracts.validate_folds(folds, embargo_weeks=EMBARGO)


def _restart(f: WalkForwardFold, start: pd.Timestamp) -> WalkForwardFold:
    """Same fold with another test_start; purge_end and train_end moved consistently."""
    moved = fold(f.test_year, f.refit, start, f.test_end)
    return dataclasses.replace(moved, train_start=f.train_start)


def _overlap(folds):
    out = list(folds)
    out[1] = _restart(out[1], out[0].test_end)  # starts on the last week of the previous fold
    return out


def _edit(folds, position, **changes):
    out = list(folds)
    out[position] = dataclasses.replace(out[position], **changes)
    return out


BAD_FOLDS = {
    "overlapping test windows": _overlap,
    "train_end equals test_start": lambda fs: _edit(fs, 2, train_end=fs[2].test_start),
    "train_end after test_start": lambda fs: _edit(fs, 2, train_end=fs[2].test_start + 7 * DAY),
    "train_start after train_end": lambda fs: _edit(fs, 0, train_start=fs[0].train_end + 7 * DAY),
    "test_start after test_end": lambda fs: _edit(fs, 7, test_end=fs[7].test_start - 7 * DAY),
    "purge_end without embargo": lambda fs: _edit(fs, 3, purge_end=fs[3].test_start),
    "purge_end two weeks back": lambda fs: _edit(fs, 3, purge_end=fs[3].test_start - 14 * DAY),
    "records out of order": lambda fs: list(reversed(fs)),
}


@pytest.mark.parametrize("name", list(BAD_FOLDS))
def test_folds_invalid(name):
    with pytest.raises(ContractError):
        contracts.validate_folds(BAD_FOLDS[name](folds_list()))


def test_folds_embargo_argument():
    with pytest.raises(ContractError):
        contracts.validate_folds(folds_list(), embargo_weeks=EMBARGO + 1)  # purge_end built with one week


def test_folds_last_training_label_must_end_by_purge_end():
    # train_end one week later than allowed: its label ends on the Monday after purge_end (purge_end - 7 + 10 = +3 days)
    folds = folds_list()
    late = _edit(folds, 2, train_end=folds[2].purge_end - 7 * DAY)
    with pytest.raises(ContractError, match="purge_end"):
        contracts.validate_folds(late)


def _label_end(folds, shift_days: int = 10) -> pd.Series:
    """Per-week label_end on a weekly index: the Monday of week t+2 (date_close + 10 days), optionally moved."""
    fridays = pd.date_range(TRAIN_START, folds[-1].test_end, freq="W-FRI")
    weeks = pd.MultiIndex.from_arrays([fridays - 4 * DAY, fridays], names=["date_open", "date_close"])
    return pd.Series(fridays + shift_days * DAY, index=weeks, name="label_end")


def test_folds_exact_label_end_check():
    folds = folds_list()
    contracts.validate_folds(folds, label_end=_label_end(folds))
    # a holiday Monday moves label_end to Tuesday: still before purge_end (train_end + 11 days <= train_end + 14 days)
    contracts.validate_folds(folds, label_end=_label_end(folds, shift_days=11))
    with pytest.raises(ContractError, match="label_end"):  # labels ending after purge_end
        contracts.validate_folds(folds, label_end=_label_end(folds, shift_days=15))
    with pytest.raises(ContractError, match="rows for train_end"):  # train_end missing from the label_end series
        series = _label_end(folds)
        contracts.validate_folds(folds, label_end=series[series.index.get_level_values("date_close") != folds[0].train_end])


# ---------------------------------------------------------------- validators never modify their inputs


def test_validators_do_not_modify_inputs():
    size, result = sizing(), backtest_result()
    fwd, realised_on, period = forward_objects()
    calls = [
        (contracts.validate_weekly_index, (GOOD_INDEX.copy(),)),
        (contracts.validate_daily_frame, (daily_frame(),)),
        (contracts.validate_features, (features_frame(),)),
        (contracts.validate_market_states, (states_frame(),)),
        (contracts.validate_labels, (labels_frame(),)),
        (contracts.validate_scores, (scores_frame(),)),
        (contracts.validate_signals, (size.signals,)),
        (contracts.validate_betas, (betas_frame(),)),
        (contracts.validate_weights, (size.weights, size.signals)),
        (contracts.validate_forward_returns, (fwd, realised_on, period)),
    ]
    for validator, args in calls:
        before = copy.deepcopy(args)
        validator(*args)
        for original, after in zip(before, args):
            if isinstance(original, pd.DataFrame):
                pd.testing.assert_frame_equal(after, original)
            elif isinstance(original, pd.Series):
                pd.testing.assert_series_equal(after, original)
            else:
                pd.testing.assert_index_equal(after, original)

    before = copy.deepcopy(result)
    contracts.validate_backtest_result(result, cost_bps=COST_BPS, borrow_annual=BORROW)
    for field in dataclasses.fields(result):
        old, new = getattr(before, field.name), getattr(result, field.name)
        if isinstance(old, pd.DataFrame):
            pd.testing.assert_frame_equal(new, old)
        else:
            pd.testing.assert_series_equal(new, old)

    folds = folds_list()
    before = list(folds)
    contracts.validate_folds(folds)
    assert folds == before
