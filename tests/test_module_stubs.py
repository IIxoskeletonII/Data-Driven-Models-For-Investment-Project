"""Every public name of contract 17 (docs/interfaces.md) exists, and functions not yet implemented say who builds them when."""

import importlib
import inspect

import pytest

# (module, functions, phase, owner) of the contract 17 table, for the functions that are stubs until their phase
STUB_FUNCTIONS = [
    ("src.models", ["ensemble_scores", "select_m0_star_lookback"], "3.1", "Eliya"),
    ("src.agents.vault_server", ["get_features", "run_walkforward", "get_trial_history"], "3.3", "Eliya"),
    ("src.agents.graph", ["build_graph", "run_lab"], "3.3", "Eliya"),
    ("src.stats", ["paired_block_bootstrap", "rank_ic", "deflated_sharpe_ratio", "pbo_cscv", "sharpe_difference_test",
                   "selection_gate"], "3.1", "Eliya"),
    ("src.plots", ["equity_curves", "drawdowns", "exposures"], "3.2", "Mattia"),
]

STUBS = [(module, name, phase, owner) for module, names, phase, owner in STUB_FUNCTIONS for name in names]

# public functions implemented in their phase: they must exist, be callable and documented
IMPLEMENTED = [
    ("src.features", ["lag_one_session", "asset_features", "momentum_variants", "market_states", "sizing_betas"]),
    ("src.labels", ["make_labels", "walk_forward_folds"]),
    ("src.vault", ["append_trial"]),
    ("src.models", ["fit_transform_train", "transform_test"]),
]
IMPLEMENTED_NAMES = [(module, name) for module, names in IMPLEMENTED for name in names]

# classes of the table: (module, class, methods it must define)
CLASSES = [
    ("src.vault", "Vault", ["features", "market_states", "labels", "run_walkforward"]),
    ("src.models", "M0", ["fit", "score"]),
    ("src.models", "RidgeModel", ["fit", "score"]),
    ("src.models", "LightGBMModel", ["fit", "score"]),
]

VALIDATORS = ["validate_weekly_index", "validate_daily_frame", "validate_features", "validate_market_states",
              "validate_labels", "validate_scores", "validate_signals", "validate_betas", "validate_weights",
              "validate_forward_returns", "validate_backtest_result", "validate_folds"]
CONTRACT_NAMES = ["ContractError", "Universe", "universe", "interaction_name", "interaction_columns", "SizingResult",
                  "BacktestResult", "WalkForwardFold", "ScoreModel"] + VALIDATORS


def call_with_nones(func):
    """Call func with None for every required parameter (positional or keyword-only)."""
    args, kwargs = [], {}
    for parameter in inspect.signature(func).parameters.values():
        if parameter.default is not inspect.Parameter.empty:
            continue
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            args.append(None)
        elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[parameter.name] = None
    return func(*args, **kwargs)


@pytest.mark.parametrize("name", CONTRACT_NAMES)
def test_contracts_public_names(name):
    contracts = importlib.import_module("src.contracts")
    assert hasattr(contracts, name), name


@pytest.mark.parametrize("module,name,phase,owner", STUBS, ids=[f"{m}.{n}" for m, n, _, _ in STUBS])
def test_stub_raises_with_phase_and_owner(module, name, phase, owner):
    func = getattr(importlib.import_module(module), name)
    assert callable(func)
    assert inspect.getdoc(func), f"{module}.{name} has no docstring"
    with pytest.raises(NotImplementedError) as raised:
        call_with_nones(func)
    message = str(raised.value)
    assert f"Phase {phase}" in message, message
    assert owner in message, message


@pytest.mark.parametrize("module,name", IMPLEMENTED_NAMES, ids=[f"{m}.{n}" for m, n in IMPLEMENTED_NAMES])
def test_implemented_functions_exist(module, name):
    func = getattr(importlib.import_module(module), name)
    assert callable(func)
    assert inspect.getdoc(func), f"{module}.{name} has no docstring"


@pytest.mark.parametrize("module,name,methods", CLASSES, ids=[f"{m}.{n}" for m, n, _ in CLASSES])
def test_classes_exist(module, name, methods):
    cls = getattr(importlib.import_module(module), name)
    assert inspect.isclass(cls)
    assert inspect.getdoc(cls), f"{module}.{name} has no docstring"
    for method in methods:
        assert callable(getattr(cls, method, None)), f"{name}.{method}"


def test_oos_access_error_is_permission_error():
    from src.vault import OOSAccessError

    assert inspect.isclass(OOSAccessError) and issubclass(OOSAccessError, PermissionError)
    with pytest.raises(PermissionError):
        raise OOSAccessError("2020-01-03 is after the In-Sample end")


def test_backtest_reexports_backtest_result():
    from src import backtest, contracts

    assert backtest.BacktestResult is contracts.BacktestResult
