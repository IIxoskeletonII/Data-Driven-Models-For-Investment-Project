"""Feature DSL of the research lab (protocol sections 06 and 08; decision S33-3, Amendment 7 C2): agent features are JSON
expression trees, never raw Python.

A spec is {"name": str, "expr": node}. Leaves {"input": "close"} (the asset's adjusted close) and {"input": "spy"} (SPY's,
the same value for every sector) are sampled at the last session on or before Friday t (TR(t) of decision S22-3; NaN
when the week has no session). Operations act on that weekly grid, every window ending at t:

Weeks are the rows of src.features.weekly_index (calendar weeks with at least one session), so n counts those rows.

- {"op": "lag", "n": k, "x": node}: x(t - k weeks), 1 <= k <= 104
- {"op": "rolling", "stat": "mean"|"std"|"sum"|"min"|"max", "n": k, "x": node}: the k weekly values ending at t
  (std with ddof = 1), 2 <= k <= 104; NaN unless all k values are finite
- {"op": "diff", "n": k, "x": node}: x(t) - x(t - k), 1 <= k <= 104
- {"op": "log", "x": node}; {"op": "ratio", "a": node, "b": node}
- {"op": "cs_z", "x": node} (src.features.cross_sectional_zscore) and {"op": "cs_rank", "x": node} (average rank across
  the 9 sectors mapped linearly to [-1, 1]; a week with a missing value is NaN for every sector)
- {"op": "mul_state", "state": S or [S1, S2], "x": node}, S in BEAR24, MKT_VAR, VIX, TERM, CREDIT

Root rule: the root is cs_rank or cs_z, or mul_state whose child is one of them; mul_state appears only at the root.
Canonical form (S33-11): `canonical(spec)` writes a root mul_state's states as a list in the order of STATES (the product
commutes) and drops the name, so one configuration has one form; FeatureSpec.states follow the same order.
`evaluate` returns the cross-sectional asset part; the product with the in-fold scaled states is formed by the model
pipeline (src.models), like the pre-registered interactions. Every window is computed on its own values
(sliding_window_view), so no value after t can change a value at t. Non-finite results become NaN.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from scipy.stats import rankdata

from src.config import load_config
from src.contracts import universe
from src.features import FEATURE_LEVELS, _calendar, _close_weeks_ago, cross_sectional_zscore

STATES = ("BEAR24", "MKT_VAR", "VIX", "TERM", "CREDIT")
INPUTS = ("close", "spy")
ROLLING_STATS = ("mean", "std", "sum", "min", "max")
CROSS_SECTIONAL = ("cs_rank", "cs_z")
MAX_WINDOW = 104
MAX_NODES = 25
MAX_DEPTH = 10
# operation -> (required keys besides "op", minimum n or None)
OPERATIONS = {
    "lag": (("n", "x"), 1),
    "rolling": (("stat", "n", "x"), 2),
    "diff": (("n", "x"), 1),
    "log": (("x",), None),
    "ratio": (("a", "b"), None),
    "cs_rank": (("x",), None),
    "cs_z": (("x",), None),
    "mul_state": (("state", "x"), None),
}
SPEC_KEYS = ("name", "expr")


class DSLError(ValueError):
    """An agent feature spec that the DSL refuses (S33-3)."""


@dataclass(frozen=True)
class FeatureSpec:
    """A validated feature spec: `expr` the whole tree, `asset_expr` the cross-sectional root below a root mul_state
    (the whole tree when there is none), `states` the root mul_state's states in the given order (() if none)."""

    name: str
    expr: dict
    asset_expr: dict
    states: tuple[str, ...]


def _children(node: Mapping) -> list[Mapping]:
    if "input" in node:
        return []
    return [node[key] for key in ("x", "a", "b") if key in node]


def _check_node(node, depth: int, counter: list[int], root: bool) -> None:
    """Raise DSLError unless `node` is a valid node; counts nodes in counter[0]."""
    if not isinstance(node, Mapping):
        raise DSLError(f"a node must be a JSON object, got {type(node).__name__}")
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise DSLError(f"the expression has more than {MAX_NODES} nodes")
    if depth > MAX_DEPTH:
        raise DSLError(f"the expression is deeper than {MAX_DEPTH}")
    if "input" in node:
        if set(node) != {"input"}:
            raise DSLError(f"an input node holds only 'input', got keys {sorted(node)}")
        if not isinstance(node["input"], str) or node["input"] not in INPUTS:
            raise DSLError(f"unknown input {node['input']!r}; allowed {list(INPUTS)}")
        return
    op = node.get("op")
    if not isinstance(op, str) or op not in OPERATIONS:
        raise DSLError(f"unknown operation {op!r}; allowed {sorted(OPERATIONS)}")
    keys, minimum = OPERATIONS[op]
    if set(node) != {"op", *keys}:
        raise DSLError(f"operation {op!r} takes exactly the keys {sorted(('op',) + keys)}, got {sorted(node)}")
    if op == "mul_state" and not root:
        raise DSLError("mul_state may appear only at the root (Amendment 7 C2)")
    if minimum is not None:
        n = node["n"]
        if isinstance(n, bool) or not isinstance(n, int) or not minimum <= n <= MAX_WINDOW:
            raise DSLError(f"{op}: n must be an integer in [{minimum}, {MAX_WINDOW}] weeks, got {n!r}")
    if op == "rolling" and (not isinstance(node["stat"], str) or node["stat"] not in ROLLING_STATS):
        raise DSLError(f"rolling: unknown stat {node['stat']!r}; allowed {list(ROLLING_STATS)}")
    if op == "mul_state":
        states = _state_list(node["state"])
        if (not 1 <= len(states) <= 2 or not all(isinstance(s, str) for s in states) or len(set(states)) != len(states)
                or any(s not in STATES for s in states)):
            raise DSLError(f"mul_state: one or two distinct states of {list(STATES)}, got {node['state']!r}")
    for child in _children(node):
        _check_node(child, depth + 1, counter, root=False)


def _state_list(state) -> list:
    return list(state) if isinstance(state, list | tuple) else [state]


def parse(spec) -> FeatureSpec:
    """Validate a feature spec (S33-3) and return it as a FeatureSpec; DSLError on any invalid spec. A FeatureSpec is
    validated again from its name and expr (S33-11)."""
    if isinstance(spec, FeatureSpec):
        spec = {"name": spec.name, "expr": spec.expr}
    if not isinstance(spec, Mapping):
        raise DSLError(f"a feature spec must be a JSON object, got {type(spec).__name__}")
    if set(spec) != set(SPEC_KEYS):
        raise DSLError(f"a feature spec holds exactly the keys {list(SPEC_KEYS)}, got {sorted(spec)}")
    name = spec["name"]
    if not isinstance(name, str) or not name.strip():
        raise DSLError("the feature name must be a non-empty string")
    expr = spec["expr"]
    _check_node(expr, 1, [0], root=True)
    if expr.get("op") == "mul_state":
        asset = expr["x"]
        states = tuple(sorted(_state_list(expr["state"]), key=STATES.index))  # canonical order (S33-11)
    else:
        asset, states = expr, ()
    if asset.get("op") not in CROSS_SECTIONAL:
        raise DSLError("the root must be cs_rank or cs_z, or mul_state of cs_rank or cs_z (S33-3)")
    return FeatureSpec(name=name, expr=expr, asset_expr=asset, states=states)


def state_terms(spec) -> tuple[str, ...]:
    """The states of the spec's root mul_state, in the order of STATES (() if none)."""
    return parse(spec).states


def canonical(spec) -> dict:
    """The canonical form of a valid spec (S33-11): {"expr": expr} with a root mul_state's states as a list in the order
    of STATES; the name is dropped, since it never reaches the model design."""
    parsed = parse(spec)
    expr = parsed.expr
    if parsed.states:
        expr = {"op": "mul_state", "state": list(parsed.states), "x": parsed.asset_expr}
    return {"expr": expr}


def _finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.where(np.isfinite(values), values, np.nan)


def _lag(values: np.ndarray, k: int) -> np.ndarray:
    out = np.full(values.shape, np.nan)
    if k < len(values):
        out[k:] = values[:-k]
    return out


def _rolling(values: np.ndarray, k: int, stat: str) -> np.ndarray:
    """Statistic of the k rows ending at each row; NaN unless all k values are finite; each window computed alone."""
    out = np.full(values.shape, np.nan)
    if k > len(values):
        return out
    windows = sliding_window_view(values, k, axis=0)  # (rows - k + 1, columns, k)
    complete = np.isfinite(windows).all(axis=-1)
    with np.errstate(invalid="ignore", over="ignore"):
        if stat == "mean":
            result = windows.mean(axis=-1)
        elif stat == "std":
            result = windows.std(axis=-1, ddof=1)
        elif stat == "sum":
            result = windows.sum(axis=-1)
        elif stat == "min":
            result = windows.min(axis=-1)
        else:
            result = windows.max(axis=-1)
    out[k - 1:] = np.where(complete, result, np.nan)
    return out


def _cs_rank(values: np.ndarray) -> np.ndarray:
    """Average rank across columns mapped to [-1, 1]; a row with any NaN is NaN everywhere."""
    n = values.shape[1]
    ranks = rankdata(np.nan_to_num(values), method="average", axis=1)
    out = (ranks - 1.0) / (n - 1) * 2.0 - 1.0
    out[~np.isfinite(values).all(axis=1)] = np.nan
    return out


class _Inputs:
    """Weekly samples of the asset and SPY closes and the feature index."""

    def __init__(self, daily_close: pd.DataFrame, cfg: dict) -> None:
        u = universe(cfg)
        self.sectors = sorted(u.sectors)
        cal = _calendar(pd.DatetimeIndex(daily_close.index))
        self.close = _close_weeks_ago(cal, daily_close[self.sectors].to_numpy(dtype=np.float64), 0)
        spy = _close_weeks_ago(cal, daily_close[[u.benchmark]].to_numpy(dtype=np.float64), 0)
        self.spy = np.repeat(spy, len(self.sectors), axis=1)
        closes = pd.DatetimeIndex(cal.weeks.get_level_values("date_close"), name="date_close")
        self.index = pd.MultiIndex.from_product([closes, self.sectors], names=FEATURE_LEVELS)


def _eval(node: Mapping, inputs: _Inputs) -> np.ndarray:
    """(weeks, sectors) values of a node."""
    if "input" in node:
        return (inputs.close if node["input"] == "close" else inputs.spy).copy()
    op = node["op"]
    if op == "ratio":
        a, b = _eval(node["a"], inputs), _eval(node["b"], inputs)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            return _finite(np.where(np.isfinite(b) & (b != 0), a / np.where(b == 0, np.nan, b), np.nan))
    x = _eval(node["x"], inputs)
    if op == "lag":
        return _lag(x, node["n"])
    if op == "diff":
        return _finite(x - _lag(x, node["n"]))
    if op == "rolling":
        return _finite(_rolling(x, node["n"], node["stat"]))
    if op == "log":
        with np.errstate(divide="ignore", invalid="ignore"):
            return _finite(np.where(np.isfinite(x) & (x > 0), np.log(np.where(x > 0, x, 1.0)), np.nan))
    if op == "cs_z":
        frame = pd.DataFrame({"v": x.reshape(-1)}, index=inputs.index)
        return cross_sectional_zscore(frame)["v"].to_numpy(dtype=np.float64).reshape(x.shape)
    if op == "cs_rank":
        return _cs_rank(x)
    return x  # mul_state: the product with the in-fold scaled states is formed in src.models (Amendment 7 C2)


def evaluate(spec, daily_close: pd.DataFrame, cfg: dict | None = None) -> pd.Series:
    """The asset part of an agent feature (contract 3 index), known after Friday close t (S33-3).

    daily_close: adjusted daily closes (total-return index) on the session calendar with the 9 sectors and SPY (other
    columns ignored). Returns a float64 Series named spec.name on (date_close, ticker) = every week of
    src.features.weekly_index(daily_close.index) x the sorted sectors; the root mul_state is not applied.
    """
    parsed = parse(spec)
    cfg = load_config() if cfg is None else cfg
    inputs = _Inputs(daily_close, cfg)
    values = _finite(_eval(parsed.asset_expr, inputs))
    return pd.Series(values.reshape(-1), index=inputs.index, name=parsed.name, dtype=np.float64)
