"""Tests of the feature DSL (src/agents/dsl.py, decision S33-3), written from the specification.

Hand-made markets have a few weeks of sessions where only the last session of each week carries the weekly value;
every other session holds an unrelated value, so sampling the wrong session changes the result. Leakage tests
perturb or change closes after a Friday cutoff and require bit-identical values on every week up to the cutoff.
"""

import copy
import dataclasses

import numpy as np
import pandas as pd
import pytest

from src import features
from src.agents import dsl
from src.agents.dsl import DSLError
from src.config import load_config
from src.contracts import universe

CFG = load_config()
SECTORS = sorted(universe(CFG).sectors)
N_SECTORS = len(SECTORS)

CLOSE = {"input": "close"}
SPY = {"input": "spy"}


def op(name: str, **kwargs) -> dict:
    return {"op": name, **kwargs}


def make_spec(expr: dict, name: str = "f") -> dict:
    return {"name": name, "expr": expr}


def log_close_returns() -> dict:
    return op("diff", n=1, x=op("log", x=CLOSE))


# ---------------------------------------------------------------------------------------------------------------------
# Hand-made market: 6 weeks from Mon 2021-03-01 to Fri 2021-04-09; Good Friday 2021-04-02 is a holiday
# ---------------------------------------------------------------------------------------------------------------------

TINY_SESSIONS = pd.bdate_range("2021-03-01", "2021-04-09").difference(pd.DatetimeIndex(["2021-04-02"])).rename("date")
TINY_FRIDAYS = pd.DatetimeIndex(["2021-03-05", "2021-03-12", "2021-03-19", "2021-03-26", "2021-04-02", "2021-04-09"],
                                name="date_close")
TINY_LAST = pd.DatetimeIndex(["2021-03-05", "2021-03-12", "2021-03-19", "2021-03-26", "2021-04-01", "2021-04-09"])
N_WEEKS = len(TINY_FRIDAYS)


def tiny_weekly_close() -> np.ndarray:
    """Weekly sector values W[week, sector] (sectors sorted): strictly increasing over weeks, ascending in week 0."""
    w = np.arange(N_WEEKS, dtype=np.float64)[:, None]
    j = np.arange(N_SECTORS, dtype=np.float64)[None, :]
    curve = ((7 * np.arange(N_SECTORS)) % 5).astype(np.float64)[None, :]
    return 10.0 * (j + 1) + 0.5 * (w + 1) * (j + 1) + 0.1 * w**2 * curve


W = tiny_weekly_close()
S = np.array([100.0, 101.0, 101.0, 103.0, 102.0, 105.0])  # SPY: zero change in week 2, a fall in week 4
TINY_INDEX = pd.MultiIndex.from_product([TINY_FRIDAYS, SECTORS], names=["date_close", "ticker"])


def tiny_close(weekly: np.ndarray = W, spy: np.ndarray = S) -> pd.DataFrame:
    """Daily closes: the weekly values on the last session of each week, unrelated positive values elsewhere."""
    columns = SECTORS + ["SPY", "IVV"]
    n = len(TINY_SESSIONS)
    junk = 1000.0 + 37.0 * np.arange(n)[:, None] + 3.0 * np.arange(len(columns))[None, :]
    frame = pd.DataFrame(junk, index=TINY_SESSIONS, columns=columns)
    for k, day in enumerate(TINY_LAST):
        frame.loc[day, SECTORS] = weekly[k]
        frame.loc[day, "SPY"] = spy[k]
        frame.loc[day, "IVV"] = np.nan
    frame.loc[pd.Timestamp("2021-03-10"), "XLK"] = np.nan  # a missing value on a session that is never sampled
    return frame


def as_frame(raw: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"f": np.asarray(raw, dtype=np.float64).reshape(-1)}, index=TINY_INDEX)


def expected_cs_z(raw: np.ndarray) -> np.ndarray:
    return features.cross_sectional_zscore(as_frame(raw))["f"].to_numpy()


def expected_cs_rank(raw: np.ndarray) -> np.ndarray:
    frame = pd.DataFrame(np.asarray(raw, dtype=np.float64))
    ranks = frame.rank(axis=1, method="average")
    mapped = (ranks - 1.0) / (N_SECTORS - 1) * 2.0 - 1.0
    mapped[frame.isna().any(axis=1)] = np.nan
    return mapped.to_numpy().reshape(-1)


def lagged(raw: np.ndarray, k: int) -> np.ndarray:
    out = np.full(raw.shape, np.nan)
    out[k:] = raw[:-k]
    return out


def rolled(raw: np.ndarray, n: int, stat: str) -> np.ndarray:
    out = np.full(raw.shape, np.nan)
    for t in range(n - 1, raw.shape[0]):
        window = raw[t - n + 1:t + 1]
        if not np.isfinite(window).all():
            continue
        if stat == "std":
            out[t] = window.std(axis=0, ddof=1)
        else:
            out[t] = getattr(window, stat)(axis=0)
    return out


def evaluate_tiny(expr: dict, daily: pd.DataFrame | None = None) -> pd.Series:
    result = dsl.evaluate(make_spec(expr), tiny_close() if daily is None else daily, CFG)
    assert isinstance(result, pd.Series)
    assert result.index.equals(TINY_INDEX)
    assert list(result.index.names) == ["date_close", "ticker"]
    assert result.dtype == np.float64
    assert result.name == "f"
    return result


def assert_values(result: pd.Series, expected: np.ndarray) -> None:
    np.testing.assert_allclose(result.to_numpy(), expected, rtol=1e-10, atol=1e-12, equal_nan=True)


# ---------------------------------------------------------------------------------------------------------------------
# API and constants
# ---------------------------------------------------------------------------------------------------------------------


def test_constants_and_error_type():
    assert dsl.STATES == ("BEAR24", "MKT_VAR", "VIX", "TERM", "CREDIT")
    assert dsl.MAX_WINDOW == 104
    assert dsl.MAX_NODES == 25
    assert dsl.MAX_DEPTH == 10
    assert issubclass(DSLError, ValueError)


def test_tiny_market_sampling_dates_match_the_feature_calendar():
    # Guards the hand-made market itself: the weekly index and the last sessions it assumes
    weeks = features.weekly_index(TINY_SESSIONS)
    assert weeks.get_level_values("date_close").equals(TINY_FRIDAYS)
    assert pd.DatetimeIndex(features.last_sessions(TINY_SESSIONS).to_numpy()).equals(TINY_LAST)


# ---------------------------------------------------------------------------------------------------------------------
# parse: valid specs
# ---------------------------------------------------------------------------------------------------------------------


VALID_ASSET_EXPRS = [
    op("cs_z", x=CLOSE),
    op("cs_rank", x=SPY),
    op("cs_z", x=op("lag", n=1, x=CLOSE)),
    op("cs_z", x=op("lag", n=104, x=CLOSE)),
    op("cs_rank", x=op("diff", n=1, x=CLOSE)),
    op("cs_rank", x=op("diff", n=104, x=CLOSE)),
    op("cs_z", x=op("rolling", stat="mean", n=2, x=CLOSE)),
    op("cs_z", x=op("rolling", stat="std", n=104, x=log_close_returns())),
    op("cs_z", x=op("rolling", stat="sum", n=13, x=log_close_returns())),
    op("cs_z", x=op("rolling", stat="min", n=26, x=CLOSE)),
    op("cs_z", x=op("rolling", stat="max", n=52, x=CLOSE)),
    op("cs_rank", x=op("ratio", a=CLOSE, b=SPY)),
    op("cs_z", x=op("log", x=op("ratio", a=op("rolling", stat="mean", n=4, x=CLOSE), b=op("lag", n=4, x=CLOSE)))),
]


@pytest.mark.parametrize("expr", VALID_ASSET_EXPRS, ids=lambda e: f"{e['op']}-{e['x'].get('op', e['x'].get('input'))}")
def test_parse_accepts_valid_asset_expressions(expr):
    spec = make_spec(expr, name="my_feature")
    before = copy.deepcopy(spec)
    parsed = dsl.parse(spec)
    assert spec == before  # parse does not modify its input
    assert parsed.name == "my_feature"
    assert parsed.expr == expr
    assert parsed.asset_expr == expr
    assert parsed.states == ()
    assert dsl.state_terms(parsed) == ()


def test_feature_spec_is_a_frozen_dataclass():
    parsed = dsl.parse(make_spec(op("cs_z", x=CLOSE)))
    assert dataclasses.is_dataclass(parsed)
    with pytest.raises(dataclasses.FrozenInstanceError):
        parsed.name = "other"


@pytest.mark.parametrize("state", ["BEAR24", "MKT_VAR", "VIX", "TERM", "CREDIT"])
def test_parse_mul_state_with_one_state(state):
    child = op("cs_rank", x=op("rolling", stat="sum", n=8, x=log_close_returns()))
    expr = op("mul_state", state=state, x=child)
    parsed = dsl.parse(make_spec(expr, name="g"))
    assert parsed.name == "g"
    assert parsed.expr == expr
    assert parsed.asset_expr == child
    assert parsed.states == (state,)
    assert isinstance(parsed.states, tuple)


@pytest.mark.parametrize("states", [["VIX", "BEAR24"], ["BEAR24", "VIX"], ["TERM", "CREDIT"], ["MKT_VAR", "TERM"]])
def test_parse_mul_state_with_two_states_puts_them_in_the_canonical_order(states):
    """S33-11: the product commutes, so the states follow the order of STATES whatever the order given."""
    child = op("cs_z", x=op("ratio", a=CLOSE, b=op("lag", n=13, x=CLOSE)))
    expr = op("mul_state", state=list(states), x=child)
    parsed = dsl.parse(make_spec(expr))
    ordered = tuple(sorted(states, key=dsl.STATES.index))
    assert parsed.expr == expr
    assert parsed.asset_expr == child
    assert parsed.states == ordered
    assert dsl.state_terms(parsed) == ordered
    assert dsl.state_terms(make_spec(expr)) == ordered
    swapped = op("mul_state", state=list(reversed(states)), x=child)
    assert dsl.canonical(make_spec(expr)) == dsl.canonical({"name": "another name", "expr": swapped})
    assert dsl.canonical(make_spec(expr)) == {"expr": op("mul_state", state=list(ordered), x=child)}


def log_chain(depth: int) -> dict:
    """cs_z(log(log(...(close)))) with the given depth (cs_z counts 1, the leaf counts 1); nodes = depth."""
    node = CLOSE
    for _ in range(depth - 2):
        node = op("log", x=node)
    return op("cs_z", x=node)


def ratio_tree(levels: int, wrap_leaves: bool) -> dict:
    """Full binary tree with `levels` levels of ratio nodes (2**levels - 1 of them) over 2**levels leaves, each leaf
    optionally wrapped in log (one more node per leaf)."""
    if levels == 0:
        return op("log", x=CLOSE) if wrap_leaves else CLOSE
    return op("ratio", a=ratio_tree(levels - 1, wrap_leaves), b=ratio_tree(levels - 1, wrap_leaves))


def count_nodes(node: dict) -> int:
    return 1 + sum(count_nodes(value) for value in node.values() if isinstance(value, dict))


def depth_of(node: dict) -> int:
    children = [depth_of(value) for value in node.values() if isinstance(value, dict)]
    return 1 + (max(children) if children else 0)


def expr_with_nodes(total: int) -> dict:
    """cs_z(log(...log(ratio tree of 3 levels with log leaves))): 1 + 7 + 8 + 8 = 24 nodes, plus total - 24 logs on top."""
    node = ratio_tree(3, wrap_leaves=True)
    for _ in range(total - 24):
        node = op("log", x=node)
    return op("cs_z", x=node)


def test_parse_node_and_depth_limits_are_inclusive():
    at_nodes = expr_with_nodes(25)
    assert count_nodes(at_nodes) == 25 and depth_of(at_nodes) <= 10
    dsl.parse(make_spec(at_nodes))
    at_depth = log_chain(10)
    assert depth_of(at_depth) == 10 and count_nodes(at_depth) == 10
    dsl.parse(make_spec(at_depth))


# ---------------------------------------------------------------------------------------------------------------------
# parse: invalid specs
# ---------------------------------------------------------------------------------------------------------------------

GOOD = op("cs_z", x=CLOSE)
TOO_MANY_NODES = expr_with_nodes(26)
TOO_DEEP = log_chain(11)
WIDE_TREE = op("cs_z", x=ratio_tree(4, wrap_leaves=False))  # 32 nodes, depth 6

INVALID_SPECS = {
    "not-a-dict": [GOOD],
    "missing-name": {"expr": GOOD},
    "missing-expr": {"name": "f"},
    "name-not-a-string": {"name": 3, "expr": GOOD},
    "extra-top-level-key": {"name": "f", "expr": GOOD, "notes": "x"},
    "expr-not-a-dict": {"name": "f", "expr": "close"},
    "root-is-a-leaf": make_spec(CLOSE),
    "root-is-lag": make_spec(op("lag", n=1, x=op("cs_z", x=CLOSE))),
    "root-is-rolling": make_spec(op("rolling", stat="mean", n=4, x=CLOSE)),
    "root-is-ratio": make_spec(op("ratio", a=op("cs_z", x=CLOSE), b=op("cs_z", x=SPY))),
    "mul-state-below-cs": make_spec(op("cs_z", x=op("mul_state", state="VIX", x=CLOSE))),
    "mul-state-child-not-cs": make_spec(op("mul_state", state="VIX", x=op("lag", n=1, x=CLOSE))),
    "mul-state-child-leaf": make_spec(op("mul_state", state="VIX", x=CLOSE)),
    "mul-state-nested": make_spec(op("mul_state", state="VIX", x=op("mul_state", state="TERM", x=GOOD))),
    "mul-state-unknown-state": make_spec(op("mul_state", state="VIX_Z", x=GOOD)),
    "mul-state-repeated-state": make_spec(op("mul_state", state=["VIX", "VIX"], x=GOOD)),
    "mul-state-three-states": make_spec(op("mul_state", state=["VIX", "TERM", "CREDIT"], x=GOOD)),
    "mul-state-empty-states": make_spec(op("mul_state", state=[], x=GOOD)),
    "mul-state-missing-state": make_spec(op("mul_state", x=GOOD)),
    "unknown-op": make_spec(op("cs_z", x=op("exp", x=CLOSE))),
    "unknown-root-op": make_spec(op("cs_mean", x=CLOSE)),
    "unknown-input": make_spec(op("cs_z", x={"input": "open"})),
    "leaf-extra-key": make_spec(op("cs_z", x={"input": "close", "n": 1})),
    "leaf-with-op": make_spec(op("cs_z", x={"input": "close", "op": "log"})),
    "node-extra-key": make_spec(op("cs_z", x=op("lag", n=1, x=CLOSE, extra=1))),
    "root-extra-key": make_spec(op("cs_z", x=CLOSE, n=3)),
    "node-not-a-dict": make_spec(op("cs_z", x="close")),
    "lag-missing-n": make_spec(op("cs_z", x=op("lag", x=CLOSE))),
    "lag-missing-x": make_spec(op("cs_z", x=op("lag", n=1))),
    "rolling-missing-stat": make_spec(op("cs_z", x=op("rolling", n=4, x=CLOSE))),
    "rolling-unknown-stat": make_spec(op("cs_z", x=op("rolling", stat="median", n=4, x=CLOSE))),
    "ratio-missing-b": make_spec(op("cs_z", x=op("ratio", a=CLOSE))),
    "ratio-with-x": make_spec(op("cs_z", x=op("ratio", x=CLOSE, b=SPY))),
    "log-missing-x": make_spec(op("cs_z", x=op("log"))),
    "lag-n-0": make_spec(op("cs_z", x=op("lag", n=0, x=CLOSE))),
    "lag-n-105": make_spec(op("cs_z", x=op("lag", n=105, x=CLOSE))),
    "lag-n-negative": make_spec(op("cs_z", x=op("lag", n=-1, x=CLOSE))),
    "diff-n-0": make_spec(op("cs_z", x=op("diff", n=0, x=CLOSE))),
    "diff-n-105": make_spec(op("cs_z", x=op("diff", n=105, x=CLOSE))),
    "rolling-n-1": make_spec(op("cs_z", x=op("rolling", stat="mean", n=1, x=CLOSE))),
    "rolling-n-105": make_spec(op("cs_z", x=op("rolling", stat="mean", n=105, x=CLOSE))),
    "n-bool": make_spec(op("cs_z", x=op("lag", n=True, x=CLOSE))),
    "n-float": make_spec(op("cs_z", x=op("lag", n=2.0, x=CLOSE))),
    "n-string": make_spec(op("cs_z", x=op("rolling", stat="mean", n="4", x=CLOSE))),
    "too-many-nodes": make_spec(TOO_MANY_NODES),
    "too-many-nodes-wide": make_spec(WIDE_TREE),
    "too-deep": make_spec(TOO_DEEP),
}


def test_invalid_size_fixtures_have_the_intended_shape():
    assert count_nodes(TOO_MANY_NODES) == 26 and depth_of(TOO_MANY_NODES) <= 10
    assert count_nodes(WIDE_TREE) == 32 and depth_of(WIDE_TREE) <= 10
    assert depth_of(TOO_DEEP) == 11 and count_nodes(TOO_DEEP) <= 25


@pytest.mark.parametrize("spec", list(INVALID_SPECS.values()), ids=list(INVALID_SPECS))
def test_parse_refuses_invalid_specs(spec):
    with pytest.raises(DSLError):
        dsl.parse(spec)


@pytest.mark.parametrize("key", ["root-is-a-leaf", "mul-state-below-cs", "unknown-op", "rolling-n-105", "too-deep"])
def test_evaluate_refuses_invalid_specs(key):
    with pytest.raises(DSLError):
        dsl.evaluate(INVALID_SPECS[key], tiny_close(), CFG)


# ---------------------------------------------------------------------------------------------------------------------
# evaluate: output index on the shared synthetic market
# ---------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def short_close(synthetic_market) -> pd.DataFrame:
    """Adjusted daily closes of the synthetic market, 2011 to 2014 (sectors, IVV and SPY)."""
    return synthetic_market.daily_close.loc[:"2014-12-31"].copy()


def test_evaluate_index_matches_asset_features(short_close):
    spec = make_spec(op("cs_rank", x=op("rolling", stat="mean", n=13, x=log_close_returns())), name="AGX")
    result = dsl.evaluate(spec, short_close, CFG)
    reference = features.asset_features(short_close, CFG)
    assert isinstance(result, pd.Series)
    assert result.name == "AGX"
    assert result.dtype == np.float64
    assert result.index.equals(reference.index)
    assert list(result.index.names) == ["date_close", "ticker"]
    # 13 weekly log returns need 14 weekly closes: the window is full from the 14th week (position 13) on
    weeks = result.index.get_level_values("date_close").unique()
    assert result.loc[weeks[13:]].notna().all()
    assert result.loc[weeks[:13]].isna().all()


def test_evaluate_accepts_a_parsed_spec_and_ignores_extra_columns(short_close):
    spec = make_spec(op("cs_z", x=op("ratio", a=CLOSE, b=op("lag", n=4, x=CLOSE))))
    from_dict = dsl.evaluate(spec, short_close, CFG)
    from_parsed = dsl.evaluate(dsl.parse(spec), short_close, CFG)
    without_ivv = dsl.evaluate(spec, short_close.drop(columns="IVV"), CFG)
    assert np.array_equal(from_dict.to_numpy(), from_parsed.to_numpy(), equal_nan=True)
    assert np.array_equal(from_dict.to_numpy(), without_ivv.to_numpy(), equal_nan=True)
    assert from_parsed.index.equals(from_dict.index)


def test_evaluate_with_default_config(short_close):
    spec = make_spec(op("cs_z", x=op("diff", n=2, x=CLOSE)))
    assert np.array_equal(dsl.evaluate(spec, short_close).to_numpy(), dsl.evaluate(spec, short_close, CFG).to_numpy(),
                          equal_nan=True)


# ---------------------------------------------------------------------------------------------------------------------
# evaluate: hand-computed values on the hand-made market
# ---------------------------------------------------------------------------------------------------------------------


def test_close_leaf_is_sampled_at_the_last_session_of_each_week():
    result = evaluate_tiny(op("cs_z", x=CLOSE))
    assert_values(result, expected_cs_z(W))
    assert result.notna().all()


def test_friday_holiday_uses_thursday_close():
    result = evaluate_tiny(op("cs_z", x=op("ratio", a=SPY, b=CLOSE)))
    holiday_week = pd.Timestamp("2021-04-02")
    expected = pd.Series(expected_cs_z(S[:, None] / W), index=TINY_INDEX)
    np.testing.assert_allclose(result.loc[holiday_week].to_numpy(), expected.loc[holiday_week].to_numpy(), rtol=1e-10)

    # Wednesday 31 March does not enter the week; Thursday 1 April does
    daily = tiny_close()
    daily.loc[pd.Timestamp("2021-03-31"), SECTORS] = np.arange(1.0, N_SECTORS + 1.0)[::-1]
    assert np.array_equal(evaluate_tiny(op("cs_z", x=op("ratio", a=SPY, b=CLOSE)), daily).to_numpy(), result.to_numpy())
    daily.loc[pd.Timestamp("2021-04-01"), SECTORS] = np.arange(1.0, N_SECTORS + 1.0)[::-1]
    changed = evaluate_tiny(op("cs_z", x=op("ratio", a=SPY, b=CLOSE)), daily)
    assert not np.allclose(changed.loc[holiday_week].to_numpy(), result.loc[holiday_week].to_numpy())


def test_cs_rank_of_close_maps_average_ranks_to_minus_one_plus_one():
    result = evaluate_tiny(op("cs_rank", x=CLOSE))
    # Week 0 is ascending in the sorted ticker order: ranks 1..9 map to -1, -0.75, ..., 1
    np.testing.assert_allclose(result.loc[TINY_FRIDAYS[0]].to_numpy(), np.linspace(-1.0, 1.0, N_SECTORS), atol=1e-15)
    assert_values(result, expected_cs_rank(W))
    for week in TINY_FRIDAYS:
        values = result.loc[week].to_numpy()
        assert values.min() == -1.0 and values.max() == 1.0 and np.median(values) == 0.0


def test_cs_rank_on_a_reversed_cross_section():
    result = evaluate_tiny(op("cs_rank", x=op("ratio", a=SPY, b=CLOSE)))
    np.testing.assert_allclose(result.loc[TINY_FRIDAYS[0]].to_numpy(), np.linspace(1.0, -1.0, N_SECTORS), atol=1e-15)
    assert_values(result, expected_cs_rank(S[:, None] / W))


def test_cs_rank_of_tied_values_is_zero():
    assert_values(evaluate_tiny(op("cs_rank", x=SPY)), np.zeros(N_WEEKS * N_SECTORS))
    assert_values(evaluate_tiny(op("cs_rank", x=op("ratio", a=CLOSE, b=CLOSE))), np.zeros(N_WEEKS * N_SECTORS))


def test_cs_z_of_spy_alone_is_zero_every_week():
    result = evaluate_tiny(op("cs_z", x=SPY))
    assert np.array_equal(result.to_numpy(), np.zeros(N_WEEKS * N_SECTORS))
    result = evaluate_tiny(op("cs_z", x=op("log", x=SPY)))
    assert np.array_equal(result.to_numpy(), np.zeros(N_WEEKS * N_SECTORS))


def test_cs_z_equals_cross_sectional_zscore():
    raw = np.log(W) - np.log(lagged(W, 2))
    assert_values(evaluate_tiny(op("cs_z", x=op("diff", n=2, x=op("log", x=CLOSE)))), expected_cs_z(raw))


@pytest.mark.parametrize("k", [1, 2, 5])
def test_lag(k):
    result = evaluate_tiny(op("cs_z", x=op("lag", n=k, x=CLOSE)))
    assert_values(result, expected_cs_z(lagged(W, k)))
    assert result.loc[TINY_FRIDAYS[:k]].isna().all()
    assert result.loc[TINY_FRIDAYS[k:]].notna().all()


def test_lag_beyond_the_sample_is_all_missing():
    assert evaluate_tiny(op("cs_z", x=op("lag", n=6, x=CLOSE))).isna().all()


@pytest.mark.parametrize("k", [1, 3])
def test_diff(k):
    result = evaluate_tiny(op("cs_z", x=op("diff", n=k, x=CLOSE)))
    assert_values(result, expected_cs_z(W - lagged(W, k)))
    assert result.loc[TINY_FRIDAYS[:k]].isna().all()


def test_lag_and_diff_values_through_cs_rank_and_ratio():
    # ratio(close, lag(close, 1)) = W(t) / W(t-1); its cs_z is checked against the hand formula
    result = evaluate_tiny(op("cs_z", x=op("ratio", a=CLOSE, b=op("lag", n=1, x=CLOSE))))
    assert_values(result, expected_cs_z(W / lagged(W, 1)))
    result = evaluate_tiny(op("cs_rank", x=op("diff", n=1, x=CLOSE)))
    assert_values(result, expected_cs_rank(W - lagged(W, 1)))


def test_log():
    assert_values(evaluate_tiny(op("cs_z", x=op("log", x=CLOSE))), expected_cs_z(np.log(W)))


def test_log_of_a_non_positive_value_is_missing():
    weekly = W.copy()
    weekly[3, SECTORS.index("XLF")] = weekly[2, SECTORS.index("XLF")] - 1.0  # XLF falls in week 3
    result = evaluate_tiny(op("cs_z", x=op("log", x=op("diff", n=1, x=CLOSE))), tiny_close(weekly))
    change = weekly - lagged(weekly, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where(change > 0, np.log(np.where(change > 0, change, 1.0)), np.nan)
    raw[0] = np.nan
    assert_values(result, expected_cs_z(raw))
    assert result.loc[TINY_FRIDAYS[3]].isna().all()
    assert result.loc[TINY_FRIDAYS[[0]]].isna().all()
    assert result.loc[TINY_FRIDAYS[[1, 2, 4, 5]]].notna().all()


def test_log_of_zero_is_missing():
    # diff(spy, 1) is 0 in week 2 and negative in week 4; log gives NaN there; cs_z of a constant is 0 elsewhere
    result = evaluate_tiny(op("cs_z", x=op("log", x=op("diff", n=1, x=SPY))))
    by_week = result.groupby(level="date_close").apply(lambda v: v.isna().all())
    assert by_week.to_numpy().tolist() == [True, False, True, False, True, False]
    assert (result.dropna() == 0.0).all()


def test_ratio():
    assert_values(evaluate_tiny(op("cs_z", x=op("ratio", a=SPY, b=CLOSE))), expected_cs_z(S[:, None] / W))


def test_ratio_with_zero_or_missing_denominator_is_missing():
    # diff(spy, 1): NaN in week 0, 0 in week 2, negative in week 4 (the sign of the cross-section flips)
    result = evaluate_tiny(op("cs_z", x=op("ratio", a=CLOSE, b=op("diff", n=1, x=SPY))))
    spy_change = S - np.r_[np.nan, S[:-1]]
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(spy_change[:, None] != 0, W / spy_change[:, None], np.nan)
    assert_values(result, expected_cs_z(raw))
    assert result.loc[TINY_FRIDAYS[[0, 2]]].isna().all()
    assert result.loc[TINY_FRIDAYS[[1, 3, 4, 5]]].notna().all()
    np.testing.assert_allclose(result.loc[TINY_FRIDAYS[4]].to_numpy(), -expected_cs_z(W)[4 * N_SECTORS:5 * N_SECTORS],
                               rtol=1e-10)


@pytest.mark.parametrize("stat", ["mean", "std", "sum", "min", "max"])
@pytest.mark.parametrize("n", [2, 3, 6])
def test_rolling(stat, n):
    result = evaluate_tiny(op("cs_z", x=op("rolling", stat=stat, n=n, x=CLOSE)))
    assert_values(result, expected_cs_z(rolled(W, n, stat)))
    assert result.loc[TINY_FRIDAYS[:n - 1]].isna().all()  # NaN while the window is not full
    assert result.loc[TINY_FRIDAYS[n - 1:]].notna().all()


def test_rolling_values_by_hand():
    # rolling(sum, 2, ratio(spy, spy)) = 2 for every sector from week 1; the cs_rank of equal values is 0
    result = evaluate_tiny(op("cs_rank", x=op("rolling", stat="sum", n=2, x=op("ratio", a=SPY, b=SPY))))
    assert result.loc[TINY_FRIDAYS[0]].isna().all()
    assert (result.loc[TINY_FRIDAYS[1:]] == 0.0).all()
    # rolling std (ddof = 1) over 3 weeks of a nested window, against the hand formula
    nested = op("rolling", stat="std", n=3, x=op("rolling", stat="mean", n=2, x=op("diff", n=1, x=op("log", x=CLOSE))))
    raw = rolled(rolled(np.log(W) - np.log(lagged(W, 1)), 2, "mean"), 3, "std")
    result = evaluate_tiny(op("cs_z", x=nested))
    assert_values(result, expected_cs_z(raw))
    assert result.loc[TINY_FRIDAYS[:4]].isna().all() and result.loc[TINY_FRIDAYS[4:]].notna().all()


def test_rolling_needs_every_value_of_its_window():
    daily = tiny_close()
    daily.loc[TINY_LAST[2], "XLE"] = np.nan  # XLE has no value at the sampled session of week 2
    result = evaluate_tiny(op("cs_z", x=op("rolling", stat="mean", n=3, x=CLOSE)), daily)
    weekly = W.copy()
    weekly[2, SECTORS.index("XLE")] = np.nan
    assert_values(result, expected_cs_z(rolled(weekly, 3, "mean")))
    by_week = result.groupby(level="date_close").apply(lambda v: v.isna().all())
    assert by_week.to_numpy().tolist() == [True, True, True, True, True, False]
    # The plain leaf is missing in week 2 only (no fallback to an earlier session)
    leaf = evaluate_tiny(op("cs_z", x=CLOSE), daily)
    assert leaf.loc[TINY_FRIDAYS[2]].isna().all()
    assert leaf.drop(index=TINY_FRIDAYS[2], level="date_close").notna().all()


def test_mul_state_is_not_applied_by_evaluate():
    asset = op("cs_rank", x=op("rolling", stat="max", n=3, x=op("ratio", a=CLOSE, b=SPY)))
    plain = evaluate_tiny(asset)
    for state in ("VIX", ["BEAR24", "TERM"]):
        spec = make_spec(op("mul_state", state=state, x=asset))
        result = dsl.evaluate(spec, tiny_close(), CFG)
        assert result.name == "f"
        assert result.index.equals(plain.index)
        assert np.array_equal(result.to_numpy(), plain.to_numpy(), equal_nan=True)
        expected_states = (state,) if isinstance(state, str) else tuple(state)
        assert dsl.state_terms(spec) == expected_states
        assert dsl.state_terms(dsl.parse(spec)) == expected_states


# ---------------------------------------------------------------------------------------------------------------------
# Leakage: perturbation after a cutoff and a planted change on the next session
# ---------------------------------------------------------------------------------------------------------------------

LEAKAGE_SPECS = {
    "nested-rolling-diff-log": make_spec(op("cs_z", x=op("rolling", stat="mean", n=4, x=op(
        "rolling", stat="std", n=13, x=op("diff", n=1, x=op("log", x=CLOSE)))))),
    "relative-momentum-cs-rank": make_spec(op("cs_rank", x=op("diff", n=4, x=op("log", x=op("ratio", a=CLOSE, b=SPY))))),
    "lag-over-rolling-max": make_spec(op("cs_z", x=op("ratio", a=op("lag", n=13, x=CLOSE),
                                                       b=op("rolling", stat="max", n=52, x=CLOSE)))),
    "ratio-to-spy-min-sum": make_spec(op("cs_rank", x=op("ratio", a=op("rolling", stat="sum", n=8, x=op("diff", n=1, x=CLOSE)),
                                                          b=op("rolling", stat="min", n=26, x=SPY)))),
    "mul-state-root": make_spec(op("mul_state", state=["VIX", "BEAR24"], x=op("cs_rank", x=op(
        "rolling", stat="sum", n=8, x=op("diff", n=1, x=op("log", x=CLOSE)))))),
}
# Fridays inside 2011-2014; 2014-04-18 is Good Friday (the last session of that week is Thursday 17 April)
CUTOFFS = ["2012-06-29", "2013-03-15", "2014-04-18", "2014-06-27"]


def weeks_up_to(result: pd.Series, cutoff: pd.Timestamp) -> np.ndarray:
    mask = result.index.get_level_values("date_close") <= cutoff
    return result.to_numpy()[mask]


def weeks_after(result: pd.Series, cutoff: pd.Timestamp) -> np.ndarray:
    mask = result.index.get_level_values("date_close") > cutoff
    return result.to_numpy()[mask]


def test_cutoffs_are_fridays_inside_the_sample(short_close):
    for cutoff in CUTOFFS:
        day = pd.Timestamp(cutoff)
        assert day.day_of_week == 4 and short_close.index[0] < day < short_close.index[-1]
    assert pd.Timestamp("2014-04-18") not in short_close.index


@pytest.mark.parametrize("name", list(LEAKAGE_SPECS))
def test_perturbing_closes_after_a_cutoff_leaves_earlier_weeks_bit_identical(name, short_close):
    spec = LEAKAGE_SPECS[name]
    base = dsl.evaluate(spec, short_close, CFG)
    assert np.isfinite(base.to_numpy()).sum() > 0.5 * len(base)
    rng = np.random.default_rng(20261104)
    for cutoff in map(pd.Timestamp, CUTOFFS):
        perturbed = short_close.copy()
        after = perturbed.index > cutoff
        perturbed.loc[after] = perturbed.loc[after].to_numpy() * np.exp(rng.normal(0.0, 0.05, (after.sum(), perturbed.shape[1])))
        result = dsl.evaluate(spec, perturbed, CFG)
        assert result.index.equals(base.index)
        assert np.array_equal(weeks_up_to(result, cutoff), weeks_up_to(base, cutoff), equal_nan=True), (name, cutoff)
        # The perturbation reaches the later weeks, so the comparison above is not vacuous
        assert not np.array_equal(weeks_after(result, cutoff), weeks_after(base, cutoff), equal_nan=True), (name, cutoff)


@pytest.mark.parametrize("name", list(LEAKAGE_SPECS))
def test_planted_change_on_the_next_session_does_not_reach_week_t(name, short_close):
    spec = LEAKAGE_SPECS[name]
    base = dsl.evaluate(spec, short_close, CFG)
    for cutoff in map(pd.Timestamp, CUTOFFS):
        next_session = short_close.index[short_close.index > cutoff][0]
        planted = short_close.copy()
        planted.loc[next_session] = planted.loc[next_session] * np.linspace(0.5, 2.0, planted.shape[1])
        result = dsl.evaluate(spec, planted, CFG)
        week_t = base.index.get_level_values("date_close") == cutoff
        assert week_t.sum() == N_SECTORS
        assert np.array_equal(result.to_numpy()[week_t], base.to_numpy()[week_t], equal_nan=True), (name, cutoff)
        assert np.array_equal(weeks_up_to(result, cutoff), weeks_up_to(base, cutoff), equal_nan=True), (name, cutoff)


def test_the_close_of_week_t_is_known_at_week_t(short_close):
    # A change at the last session on or before Friday t changes week t: the leaf is not shifted by a week
    spec = make_spec(op("cs_z", x=op("log", x=CLOSE)))
    base = dsl.evaluate(spec, short_close, CFG)
    for cutoff in map(pd.Timestamp, CUTOFFS):
        last = short_close.index[short_close.index <= cutoff][-1]
        changed = short_close.copy()
        changed.loc[last, SECTORS] = changed.loc[last, SECTORS] * np.linspace(0.5, 2.0, N_SECTORS)
        result = dsl.evaluate(spec, changed, CFG)
        week_t = base.index.get_level_values("date_close") == cutoff
        assert not np.allclose(result.to_numpy()[week_t], base.to_numpy()[week_t])
        earlier = base.index.get_level_values("date_close") < cutoff
        assert np.array_equal(result.to_numpy()[earlier], base.to_numpy()[earlier], equal_nan=True)


# ---------------------------------------------------------------- S33-11: fixes from the session audit


def test_a_feature_spec_object_is_validated_again():
    bad = dsl.FeatureSpec(name="x", expr=op("lag", n=-3, x=CLOSE), asset_expr=op("lag", n=-3, x=CLOSE), states=("FOO",))
    with pytest.raises(dsl.DSLError):
        dsl.parse(bad)


@pytest.mark.parametrize("expr", [
    {"op": ["cs_z"], "x": CLOSE},
    op("mul_state", state=[["VIX"]], x=op("cs_z", x=CLOSE)),
    op("cs_z", x={"input": ["close"]}),
    op("cs_z", x=op("rolling", stat=["mean"], n=4, x=CLOSE)),
])
def test_unhashable_values_raise_dsl_error(expr):
    with pytest.raises(dsl.DSLError):
        dsl.parse(make_spec(expr))


def test_canonical_drops_the_name_and_normalises_a_single_state():
    child = op("cs_rank", x=CLOSE)
    one = dsl.canonical({"name": "a", "expr": op("mul_state", state="VIX", x=child)})
    assert one == dsl.canonical({"name": "b", "expr": op("mul_state", state=["VIX"], x=child)})
    assert one == {"expr": op("mul_state", state=["VIX"], x=child)}
    assert dsl.canonical({"name": "c", "expr": child}) == {"expr": child}
