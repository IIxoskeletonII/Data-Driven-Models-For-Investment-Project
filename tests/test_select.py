"""05_train_walkforward.py --select and --agent-returns (decisions S37-4 to S37-7), tested from the decision log.

S37-4: the §07 gate on the In-Sample baseline weekly net returns of outputs/backtests/<name>/weekly.csv for M0, M1, M2,
M3 and ENS, each refused when stale (used.yaml, spec_hash, trial log, period, baseline, In-Sample rows, finite values),
with rf the weekly T-bill of M0's weekly.csv, written to outputs/metrics/selection_gate.json.
S37-5: is_sharpe and is_mdd of the human trial rows from the backtest summaries (no overwrite, every other byte kept).
S37-6: weekly returns of the agent candidates that reached the walk-forward, re-scored through the vault server.
S37-7: DSR and PBO on the matrix of every distinct spec_hash with weekly In-Sample returns (selection_bias.json).

Every test builds a fake project root in a temporary folder: docs/trial_log.csv (header src.vault.TRIAL_COLUMNS, rows
through src.vault.append_trial), outputs/walkforward/<name>/summary.json and outputs/backtests/<name>/{used.yaml,
summary.json, weekly.csv} for the 17 names of S31-10, with seeded synthetic weekly net returns on 208 weeks ending Fri
2019-12-13 (realised 10 days after each Friday, period "IS", a constant weekly T-bill). The agent lab's server is a
lightweight fake with .vault.run_walkforward and .book. No real data, no network, nothing under data/ or outputs/ of the
repository is read or written.
"""

import copy
import csv
import functools
import hashlib
import importlib.util
import io
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import contracts
from src.config import load_config, save_used
from src.data import write_csv
from src.metrics import performance
from src.models import tuning_spec, walkforward_settings
from src.stats import deflated_sharpe_ratio, pbo_cscv, selection_gate
from src.vault import TRIAL_COLUMNS, append_trial, spec_hash

REPO = Path(__file__).resolve().parents[1]
CFG = load_config()
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])  # Fri 2019-12-27
SECTORS = list(contracts.universe(CFG).sectors)
N_WEEKS = 208
FRIDAYS = pd.date_range(end="2019-12-13", periods=N_WEEKS, freq="W-FRI")
WEEKS = pd.MultiIndex.from_arrays([FRIDAYS - pd.Timedelta(days=4), FRIDAYS], names=["date_open", "date_close"])
REALISED = FRIDAYS + pd.Timedelta(days=10)  # the Monday after next
RF = 0.0004  # weekly T-bill return, constant
CANDIDATES = ("M1", "M2", "M3", "ENS")
TRIAL_PATH = "docs/trial_log.csv"
TIMESTAMP = "2026-11-03T15:00:00+00:00"
FALLBACK_STATEMENT = ("No candidate passed the §07 gate, so M0* is traded: the ML models failed to beat the baseline "
                      "(pre-registration §07 step 5).")

# Three agent features in the DSL of src.agents.dsl (shapes taken from logged agent candidates)
AGENT_FEATURES = {
    1: {"name": "XS_RELSTRENGTH_13W",
        "expr": {"op": "cs_z", "x": {"n": 13, "op": "diff",
                                     "x": {"op": "log", "x": {"op": "ratio", "a": {"input": "close"},
                                                              "b": {"input": "spy"}}}}}},
    2: {"name": "vol_of_vol_mktvar",
        "expr": {"op": "mul_state", "state": "MKT_VAR",
                 "x": {"op": "cs_z", "x": {"n": 26, "op": "rolling", "stat": "std",
                                           "x": {"n": 4, "op": "rolling", "stat": "std",
                                                 "x": {"n": 1, "op": "diff", "x": {"op": "log", "x": {"input": "close"}}}}}}}},
    3: {"name": "mktvar_short_reversal",
        "expr": {"op": "mul_state", "state": "MKT_VAR",
                 "x": {"op": "cs_z", "x": {"n": 1, "op": "diff", "x": {"op": "log", "x": {"input": "close"}}}}}},
}
AGENT_STAGES = {1: "walk_forward", 2: "walk_forward", 3: "redundancy"}
AGENT_TRIAL_IDS = {1: 17, 2: 18, 3: 19}


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.cache
def s05():
    return load_script("train_walkforward_select", "05_train_walkforward.py")


@functools.cache
def s06():
    return load_script("backtest_for_select", "06_backtest.py")


@pytest.fixture(scope="module")
def script():
    return s05()


def names() -> list[str]:
    """The 17 backtest names of S31-10: the round-1 rungs and fixed grid values (the round-2 names of S41-5, which 05
    lists after them, are outside this fixture of the round-1 selection step)."""
    round2 = set(s05().round2_fixed_names(CFG))
    return list(s05().ROUND1_RUNGS) + [name for name in s05().fixed_names(CFG) if name not in round2]


def human_names() -> list[str]:
    """One name per human trial row (M0_L26 is trial 1, the M0 spec)."""
    return [name for name in names() if name != "M0_L26"]


def digest_of(name: str, cfg: dict = CFG) -> str:
    return spec_hash(s05().spec_for(name, cfg), cfg)


def baseline_label(cfg: dict = CFG) -> str:
    return next(label for label, _, _, is_baseline in s06().cost_scenarios(cfg) if is_baseline)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def agent_spec(candidate: int) -> dict:
    return {"agent_features": [AGENT_FEATURES[candidate]], "author": "agent lab", "kind": "agent",
            "notes": "agent lab candidate", "rung": "M2", "tuning": tuning_spec(CFG)}


def agent_digest(candidate: int) -> str:
    return spec_hash(agent_spec(candidate), CFG)


def rf_series(index=WEEKS) -> pd.Series:
    return pd.Series(RF, index=index, name="rf")


# ---------------------------------------------------------------- synthetic returns


def make_nets(passing=("M1",)) -> dict[str, pd.Series]:
    """Weekly net returns of the 17 names: candidates in `passing` beat M0 by a strong drift, the other candidates lose to
    it; M0_L26 is M0 (same spec); the other names are independent noise."""
    m0 = np.random.default_rng(7).normal(0.0005, 0.01, N_WEEKS)
    values = {"M0": m0, "M0_L26": m0.copy()}
    for i, name in enumerate(names()):
        if name in values:
            continue
        rng = np.random.default_rng(100 + i)
        if name in CANDIDATES:
            if name in passing:
                values[name] = m0 + 0.004 + rng.normal(0.0, 0.002, N_WEEKS)
            else:
                values[name] = m0 - 0.003 + rng.normal(0.0, 0.004, N_WEEKS)
        else:
            values[name] = rng.normal(0.0, 0.01, N_WEEKS)
    return {name: pd.Series(v, index=WEEKS, name="net") for name, v in values.items()}


def agent_nets() -> dict[int, pd.Series]:
    return {c: pd.Series(np.random.default_rng(500 + c).normal(0.0002, 0.01, N_WEEKS), index=WEEKS, name="net")
            for c in (1, 2)}


def headline(net: pd.Series, rf=None) -> tuple[float, float]:
    perf = performance(net, rf_series(net.index) if rf is None else rf)
    return float(perf["sharpe_rf"]), float(perf["max_drawdown"])


# ---------------------------------------------------------------- fake project root


def write_json(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2, sort_keys=True)
        f.write("\n")


def weekly_frame(net: pd.Series, rf=None) -> pd.DataFrame:
    index = net.index
    closes = pd.DatetimeIndex(index.get_level_values("date_close"))
    rf = rf_series(index) if rf is None else rf
    frame = pd.DataFrame({"realised_on": closes + pd.Timedelta(days=10), "period": "IS", "gross": net + 0.001,
                          "net": net, "turnover": 1.0, "rf": rf, "net_20bps_5pct": net - 0.001}, index=index)
    frame["realised_on"] = pd.DatetimeIndex(frame["realised_on"])
    return frame


def write_walkforward_summary(root: Path, name: str, digest: str | None = None, cfg: dict = CFG) -> None:
    folder = root / "outputs" / "walkforward" / name
    digest = digest_of(name, cfg) if digest is None else digest
    write_json({"name": name, "rung": s05().spec_for(name, cfg)["rung"], "spec_hash": digest}, folder / "summary.json")
    save_used(walkforward_settings(cfg), folder / "used.yaml")


def write_backtest(root: Path, name: str, net: pd.Series, *, weekly: pd.DataFrame | None = None, cfg: dict = CFG,
                   digest: str | None = None, period: str = "IS", baseline: str | None = None,
                   used: dict | None = None) -> None:
    """outputs/backtests/<name>/{weekly.csv, used.yaml, summary.json} as 06_backtest.py writes them (S23-10)."""
    folder = root / "outputs" / "backtests" / name
    weekly = weekly_frame(net) if weekly is None else weekly
    write_csv(weekly, folder / "weekly.csv")
    save_used(s06().backtest_used(cfg, name) if used is None else used, folder / "used.yaml")
    clean = "rf" in weekly.columns and bool(np.isfinite(weekly["rf"].to_numpy(dtype=float)).all())
    rf = weekly["rf"] if clean else rf_series(net.index)
    perf = performance(net, rf)
    closes = pd.DatetimeIndex(net.index.get_level_values("date_close"))
    realised = pd.DatetimeIndex(weekly["realised_on"])
    write_json({
        "model": name, "spec_hash": digest_of(name, cfg) if digest is None else digest, "period": period,
        "baseline": baseline_label(cfg) if baseline is None else baseline, "weeks": len(net),
        "first_week": closes[0].strftime("%Y-%m-%d"), "last_week": closes[-1].strftime("%Y-%m-%d"),
        "first_realised_on": realised[0].strftime("%Y-%m-%d"), "last_realised_on": realised[-1].strftime("%Y-%m-%d"),
        "net_sharpe_rf_tbill": float(perf["sharpe_rf"]),
        "net_sharpe_rf_constant": float(performance(net, 0.02)["sharpe_rf"]),
        "net_sharpe_zero_cost": float(perf["sharpe_zero_cost"]), "max_drawdown": float(perf["max_drawdown"]),
        "mean_turnover": 1.0, "rf_tbill_annual": float(perf["rf_annual"]), "rf_constant": 0.02, "benchmark": "SPY",
    }, folder / "summary.json")


def write_agent_folder(root: Path, candidate: int, net: pd.Series, digest: str | None = None) -> None:
    """outputs/agent_lab/walkforward/agent_cNN/{weekly.csv, summary.json} as --agent-returns writes them (S37-6)."""
    folder = root / "outputs" / "agent_lab" / "walkforward" / f"agent_c{candidate:02d}"
    weekly = weekly_frame(net)[["realised_on", "period", "net", "rf"]]
    write_csv(weekly, folder / "weekly.csv")
    sharpe, mdd = headline(net)
    closes = pd.DatetimeIndex(net.index.get_level_values("date_close"))
    write_json({"trial_id": AGENT_TRIAL_IDS[candidate], "candidate": candidate,
                "spec_hash": agent_digest(candidate) if digest is None else digest, "net_sharpe_rf_tbill": sharpe,
                "max_drawdown": mdd, "weeks": len(net), "first_week": closes[0].strftime("%Y-%m-%d"),
                "last_week": closes[-1].strftime("%Y-%m-%d")}, folder / "summary.json")


def human_row(name: str, trial_id: int, filled: dict | None = None) -> dict:
    spec = s05().spec_for(name, CFG)
    sharpe, mdd = (filled or {}).get(name, ("", ""))
    return {"trial_id": trial_id, "timestamp": TIMESTAMP, "author": "Eliya Allam", "kind": "human", "rung": spec["rung"],
            "spec_hash": digest_of(name), "params_json": canonical(spec), "is_sharpe": sharpe, "is_mdd": mdd,
            "notes": spec["notes"]}


def agent_row(candidate: int, *, digest: str | None = None) -> dict:
    spec = agent_spec(candidate)
    stage = AGENT_STAGES[candidate]
    if stage == "walk_forward":
        sharpe, mdd = headline(agent_nets()[candidate])
        sharpe, mdd = repr(sharpe), repr(mdd)
        notes = {"candidate": candidate, "cost_usd": 0.0018, "passed_gate": False, "stage": stage, "uplift": 0.01}
    else:
        sharpe, mdd = "", ""
        notes = {"candidate": candidate, "cost_usd": 0.002, "reason": "|corr| = 1.000 >= 0.9 with REV1", "stage": stage}
    return {"trial_id": AGENT_TRIAL_IDS[candidate], "timestamp": "2026-11-05T12:11:10+00:00", "author": "agent lab",
            "kind": "agent", "rung": "M2", "spec_hash": agent_digest(candidate) if digest is None else digest,
            "params_json": canonical(spec), "is_sharpe": sharpe, "is_mdd": mdd, "notes": canonical(notes)}


def write_trial_log(root: Path, *, filled: dict | None = None, skip: tuple = (), agent_digests: dict | None = None,
                    agents: bool = True) -> Path:
    """docs/trial_log.csv: 16 human rows (trial ids 1-16) and 3 agent rows (17, 18 walk_forward; 19 redundancy)."""
    path = root / TRIAL_PATH
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerow(TRIAL_COLUMNS)
    for trial_id, name in enumerate(human_names(), start=1):
        if name not in skip:
            append_trial(human_row(name, trial_id, filled), path=path)
    if agents:
        for candidate in (1, 2, 3):
            append_trial(agent_row(candidate, digest=(agent_digests or {}).get(candidate)), path=path)
    return path


def make_root(root: Path, passing=("M1",), *, agents: bool = True, agent_folders: bool = True) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    nets = make_nets(passing)
    for name in names():
        write_walkforward_summary(root, name)
        write_backtest(root, name, nets[name])
    write_trial_log(root, agents=agents)
    if agents and agent_folders:
        for candidate, net in agent_nets().items():
            write_agent_folder(root, candidate, net)
    return nets


def read_weekly(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col=["date_open", "date_close"], parse_dates=["date_open", "date_close"])


def backtest_net(root: Path, name: str) -> pd.Series:
    return read_weekly(root / "outputs" / "backtests" / name / "weekly.csv")["net"]


def trial_bytes(root: Path) -> bytes:
    return (root / TRIAL_PATH).read_bytes()


def trial_lines(text: str) -> list[str]:
    assert text.endswith("\n")
    return text[:-1].split("\n")


def assert_close(actual, expected, rel: float = 1e-12, where: str = "") -> None:
    """Equal structures, floats within a relative tolerance; lists and tuples alike."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), where
        assert set(actual) == set(expected), f"{where}: keys {sorted(actual)} != {sorted(expected)}"
        for key in expected:
            assert_close(actual[key], expected[key], rel, f"{where}.{key}")
    elif isinstance(expected, list | tuple):
        assert isinstance(actual, list | tuple) and len(actual) == len(expected), where
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_close(a, e, rel, f"{where}[{i}]")
    elif isinstance(expected, bool | np.bool_) or expected is None or isinstance(expected, str):
        assert actual == expected, f"{where}: {actual!r} != {expected!r}"
    elif isinstance(expected, int | float | np.integer | np.floating):
        assert isinstance(actual, int | float | np.integer | np.floating) and not isinstance(actual, bool), where
        if math.isnan(float(expected)):
            assert math.isnan(float(actual)), where
        else:
            assert math.isclose(float(actual), float(expected), rel_tol=rel, abs_tol=1e-15), \
                f"{where}: {actual!r} != {expected!r}"
    else:
        assert actual == expected, where


def numbers_in(mapping: dict) -> list[float]:
    return [float(v) for v in mapping.values() if isinstance(v, int | float | np.integer | np.floating)
            and not isinstance(v, bool)]


def contains_close(values, target: float, rel: float = 1e-12) -> bool:
    return any(math.isclose(v, target, rel_tol=rel, abs_tol=1e-15) for v in values)


@pytest.fixture(scope="module")
def pass_root(tmp_path_factory) -> Path:
    """A root where M1 passes the gate (read-only for the tests that use it)."""
    root = tmp_path_factory.mktemp("select_pass")
    make_root(root, passing=("M1",))
    return root


@pytest.fixture(scope="module")
def fail_root(tmp_path_factory) -> Path:
    """A root where no candidate passes the gate (read-only)."""
    root = tmp_path_factory.mktemp("select_fail")
    make_root(root, passing=())
    return root


@pytest.fixture
def root(tmp_path) -> Path:
    """A fresh root where M1 passes the gate, for the tests that change files."""
    make_root(tmp_path / "project", passing=("M1",))
    return tmp_path / "project"


# ---------------------------------------------------------------- constants


def test_constants_are_the_ones_of_the_decision_log(script):
    assert tuple(script.GATE_MODELS) == ("M0", "M1", "M2", "M3", "ENS")
    assert script.GATE_FILE == "outputs/metrics/selection_gate.json"
    assert script.BIAS_FILE == "outputs/metrics/selection_bias.json"
    assert script.AGENT_DIR == "outputs/agent_lab/walkforward"


def test_fixture_holds_the_17_backtest_names_and_16_distinct_human_hashes():
    """Sanity check of the fake root: 17 names, M0 and M0_L26 one spec_hash (S31-6), 16 human rows."""
    assert len(names()) == 17
    assert digest_of("M0") == digest_of("M0_L26")
    assert len({digest_of(name) for name in names()}) == 16
    assert len(human_names()) == 16


# ---------------------------------------------------------------- checked_backtest (S37-4)


@pytest.mark.parametrize("name", ["M0", "M1", "ENS", "M3_d2", "M0_L26"])
def test_checked_backtest_returns_the_weekly_table(script, pass_root, name):
    weekly = script.checked_backtest(name, CFG, pass_root)
    assert list(weekly.index.names) == ["date_open", "date_close"]
    assert pd.DatetimeIndex(weekly.index.get_level_values("date_close")).equals(pd.DatetimeIndex(FRIDAYS))
    assert pd.DatetimeIndex(weekly.index.get_level_values("date_open")).equals(pd.DatetimeIndex(FRIDAYS - pd.Timedelta(days=4)))
    for column in ("realised_on", "period", "net", "rf"):
        assert column in weekly.columns
    np.testing.assert_allclose(weekly["net"].to_numpy(dtype=float), make_nets()[name].to_numpy(), rtol=0, atol=0)
    np.testing.assert_allclose(weekly["rf"].to_numpy(dtype=float), RF, rtol=0, atol=0)
    assert (weekly["period"] == "IS").all()


def test_checked_backtest_refuses_a_used_yaml_of_another_model(script, root):
    save_used(s06().backtest_used(CFG, "M2"), root / "outputs" / "backtests" / "M1" / "used.yaml")
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_used_yaml_of_another_config(script, root):
    other = copy.deepcopy(CFG)
    other["costs"]["bps_baseline"] = 20
    other["costs"]["borrow_baseline"] = 0.05
    save_used(s06().backtest_used(other, "M1"), root / "outputs" / "backtests" / "M1" / "used.yaml")
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_missing_used_yaml(script, root):
    (root / "outputs" / "backtests" / "M1" / "used.yaml").unlink()
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_stale_walkforward_spec_hash(script, root):
    write_walkforward_summary(root, "M1", digest=digest_of("M2"))
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_stale_backtest_spec_hash(script, root):
    write_backtest(root, "M1", make_nets()["M1"], digest=digest_of("M2"))
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_both_hashes_stale_under_a_changed_config(script, root):
    """Outputs built under another models section carry another spec_hash: stale for the current config (S32-10)."""
    other = copy.deepcopy(CFG)
    other["models"]["M3"]["n_estimators"] = 300
    stale = digest_of("M3", other)
    assert stale != digest_of("M3")
    write_walkforward_summary(root, "M3", digest=stale)
    write_backtest(root, "M3", make_nets()["M3"], digest=stale)
    with pytest.raises(SystemExit):
        script.checked_backtest("M3", CFG, root)


def test_checked_backtest_refuses_a_hash_missing_from_the_trial_log(script, root):
    write_trial_log(root, skip=("M2",))
    with pytest.raises(SystemExit):
        script.checked_backtest("M2", CFG, root)


def test_checked_backtest_refuses_a_missing_trial_log(script, root):
    (root / TRIAL_PATH).unlink()
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


@pytest.mark.parametrize("period", ["OOS", "ALL", ""])
def test_checked_backtest_refuses_a_summary_period_other_than_is(script, root, period):
    write_backtest(root, "M1", make_nets()["M1"], period=period)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


@pytest.mark.parametrize("label", ["5bps_1pct", "20bps_5pct", "10bps"])
def test_checked_backtest_refuses_a_summary_baseline_other_than_the_configured_one(script, root, label):
    assert baseline_label() == "10bps_2pct"
    write_backtest(root, "M1", make_nets()["M1"], baseline=label)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_weekly_row_with_period_oos(script, root):
    net = make_nets()["M1"]
    weekly = weekly_frame(net)
    weekly.iloc[-1, weekly.columns.get_loc("period")] = "OOS"
    write_backtest(root, "M1", net, weekly=weekly)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_weekly_row_with_a_missing_period(script, root):
    net = make_nets()["M1"]
    weekly = weekly_frame(net)
    weekly["period"] = weekly["period"].astype(object)
    weekly.iloc[3, weekly.columns.get_loc("period")] = None
    write_backtest(root, "M1", net, weekly=weekly)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_realised_on_after_the_in_sample_end(script, root):
    net = make_nets()["M1"]
    weekly = weekly_frame(net)
    weekly.iloc[-1, weekly.columns.get_loc("realised_on")] = pd.Timestamp("2019-12-30")
    write_backtest(root, "M1", net, weekly=weekly)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


def test_checked_backtest_refuses_a_date_close_after_the_in_sample_end(script, root):
    fridays = FRIDAYS[:-1].append(pd.DatetimeIndex(["2020-01-03"]))
    index = pd.MultiIndex.from_arrays([fridays - pd.Timedelta(days=4), fridays], names=["date_open", "date_close"])
    net = pd.Series(make_nets()["M1"].to_numpy(), index=index, name="net")
    weekly = weekly_frame(net)
    weekly.iloc[-1, weekly.columns.get_loc("realised_on")] = pd.Timestamp("2019-12-23")  # only the week is late
    write_backtest(root, "M1", net, weekly=weekly)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


@pytest.mark.parametrize(("column", "value"), [("net", np.nan), ("net", np.inf), ("rf", np.nan), ("rf", -np.inf)])
def test_checked_backtest_refuses_a_missing_or_infinite_net_or_rf(script, root, column, value):
    net = make_nets()["M1"]
    weekly = weekly_frame(net)
    weekly.iloc[10, weekly.columns.get_loc(column)] = value
    write_backtest(root, "M1", net, weekly=weekly)
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


@pytest.mark.parametrize("column", ["net", "rf"])
def test_checked_backtest_refuses_a_weekly_table_without_net_or_rf(script, root, column):
    net = make_nets()["M1"]
    write_backtest(root, "M1", net, weekly=weekly_frame(net).drop(columns=[column]))
    with pytest.raises(SystemExit):
        script.checked_backtest("M1", CFG, root)


# ---------------------------------------------------------------- gate_inputs (S37-4)


def test_gate_inputs_returns_the_four_candidates_m0_and_rf(script, pass_root):
    results, m0, rf = script.gate_inputs(CFG, pass_root)
    assert set(results) == set(CANDIDATES)
    nets = make_nets()
    np.testing.assert_allclose(m0.to_numpy(dtype=float), nets["M0"].to_numpy(), rtol=0, atol=0)
    for name in CANDIDATES:
        assert results[name].index.equals(m0.index)
        np.testing.assert_allclose(results[name].to_numpy(dtype=float), nets[name].to_numpy(), rtol=0, atol=0)
    assert rf.index.equals(m0.index)
    np.testing.assert_allclose(rf.to_numpy(dtype=float), RF, rtol=0, atol=0)


def test_gate_inputs_refuses_a_candidate_on_other_weeks(script, root):
    net = make_nets()["M2"].iloc[1:]
    write_backtest(root, "M2", net)
    with pytest.raises(SystemExit):
        script.gate_inputs(CFG, root)


def test_gate_inputs_refuses_rf_columns_differing_by_more_than_1e_12(script, root):
    net = make_nets()["M3"]
    rf = rf_series() + 1e-9
    write_backtest(root, "M3", net, weekly=weekly_frame(net, rf=rf))
    with pytest.raises(SystemExit):
        script.gate_inputs(CFG, root)


def test_gate_inputs_accepts_rf_columns_within_1e_12(script, root):
    net = make_nets()["ENS"]
    rf = rf_series() + 1e-14
    write_backtest(root, "ENS", net, weekly=weekly_frame(net, rf=rf))
    results, _, _ = script.gate_inputs(CFG, root)
    assert set(results) == set(CANDIDATES)


@pytest.mark.parametrize("name", ["M0", "M1", "M2", "M3", "ENS"])
def test_gate_inputs_refuses_any_stale_gate_model(script, root, name):
    write_walkforward_summary(root, name, digest="0" * 64)
    with pytest.raises(SystemExit):
        script.gate_inputs(CFG, root)


@pytest.mark.parametrize("name", ["M0", "ENS"])
def test_gate_inputs_refuses_a_missing_gate_model(script, root, name):
    shutil.rmtree(root / "outputs" / "backtests" / name)
    with pytest.raises(SystemExit):
        script.gate_inputs(CFG, root)


# ---------------------------------------------------------------- gate_result (S37-4)

GATE_KEYS = {"selected", "candidates", "absent", "m0", "thresholds", "seed", "weeks", "first_week", "last_week",
             "first_realised_on", "last_realised_on", "rf_source", "rf_tbill_annual", "inputs", "fallback", "statement"}


def expected_gate(root: Path) -> dict:
    """src.stats.selection_gate on the weekly.csv files as written, rf the rf column of M0's weekly.csv."""
    results = {name: backtest_net(root, name) for name in CANDIDATES}
    m0 = backtest_net(root, "M0")
    rf = read_weekly(root / "outputs" / "backtests" / "M0" / "weekly.csv")["rf"]
    return selection_gate(results, m0, CFG, rf=rf, absent=("M5",))


@pytest.fixture(scope="module")
def pass_gate(pass_root) -> dict:
    return s05().gate_result(CFG, pass_root)


@pytest.fixture(scope="module")
def fail_gate(fail_root) -> dict:
    return s05().gate_result(CFG, fail_root)


def test_gate_result_has_the_keys_of_the_decision(pass_gate):
    assert GATE_KEYS <= set(pass_gate)


def test_gate_result_selects_the_passing_candidate(pass_gate):
    assert pass_gate["selected"] == "M1"
    assert pass_gate["fallback"] is False


def test_gate_result_candidates_are_selection_gates_unchanged(pass_root, pass_gate):
    expected = expected_gate(pass_root)
    assert expected["selected"] == "M1"
    assert_close(pass_gate["candidates"], expected["candidates"], where="candidates")


def test_gate_result_marks_m5_absent(pass_gate):
    assert list(pass_gate["absent"]) == ["M5"]
    rows = {row["name"]: row for row in pass_gate["candidates"]}
    assert [row["name"] for row in pass_gate["candidates"]] == list(CFG["models"]["candidate_order"])
    assert rows["M5"]["status"] == "absent"
    for name in CANDIDATES:
        assert rows[name]["status"] == "evaluated"


def test_gate_result_reports_the_passing_row(pass_gate):
    m1 = next(row for row in pass_gate["candidates"] if row["name"] == "M1")
    assert m1["passes"]
    for name in ("M2", "M3", "ENS"):
        row = next(r for r in pass_gate["candidates"] if r["name"] == name)
        assert not row["passes"]


def test_gate_result_thresholds_seed_and_weeks(pass_gate):
    assert pass_gate["thresholds"] == CFG["selection"]
    assert pass_gate["seed"] == CFG["seed"]
    assert pass_gate["weeks"] == N_WEEKS
    assert pass_gate["first_week"] == FRIDAYS[0].strftime("%Y-%m-%d")
    assert pass_gate["last_week"] == "2019-12-13"
    assert pass_gate["first_realised_on"] == REALISED[0].strftime("%Y-%m-%d")
    assert pass_gate["last_realised_on"] == "2019-12-23"


def test_gate_result_m0_figures_are_the_hurdles(pass_root, pass_gate):
    """m0 holds M0's headline Sharpe (weekly T-bill), zero-cost Sharpe and max drawdown."""
    row = next(r for r in expected_gate(pass_root)["candidates"] if r["name"] == "M1")
    values = numbers_in(pass_gate["m0"])
    for target in (row["sharpe_m0"], row["sharpe_m0_zero_cost"], row["mdd_m0"]):
        assert contains_close(values, target, rel=1e-9), (target, pass_gate["m0"])


def test_gate_result_rf_tbill_annual_is_m0s_summary_value(pass_root, pass_gate):
    summary = json.loads((pass_root / "outputs" / "backtests" / "M0" / "summary.json").read_text(encoding="utf-8"))
    assert pass_gate["rf_tbill_annual"] == pytest.approx(summary["rf_tbill_annual"], rel=1e-12)
    assert pass_gate["rf_source"]


@pytest.mark.parametrize("name", ["M0", "M1", "M2", "M3", "ENS"])
def test_gate_result_inputs_hold_each_spec_hash_and_weekly_sha256(pass_root, pass_gate, name):
    entry = pass_gate["inputs"][name]
    assert entry["spec_hash"] == digest_of(name)
    weekly = pass_root / "outputs" / "backtests" / name / "weekly.csv"
    assert hashlib.sha256(weekly.read_bytes()).hexdigest() in entry.values()


def test_gate_result_does_not_write_the_gate_file(script, pass_root, pass_gate):
    assert not (pass_root / script.GATE_FILE).exists()


def test_gate_result_with_no_passing_candidate_is_the_fallback(fail_root, fail_gate):
    assert fail_gate["selected"] == "M0_star"
    assert fail_gate["fallback"] is True
    assert "the ML models failed to beat the baseline" in fail_gate["statement"]
    assert fail_gate["statement"] == FALLBACK_STATEMENT
    assert not any(row.get("passes") for row in fail_gate["candidates"])
    assert_close(fail_gate["candidates"], expected_gate(fail_root)["candidates"], where="candidates")


def test_gate_result_selects_the_first_passing_candidate_in_order(script, tmp_path):
    """M2 and ENS pass, M1 does not: the first passing candidate of models.candidate_order is M2."""
    make_root(tmp_path / "p", passing=("M2", "ENS"))
    gate = script.gate_result(CFG, tmp_path / "p")
    assert gate["selected"] == "M2"
    assert gate["fallback"] is False
    assert_close(gate["candidates"], expected_gate(tmp_path / "p")["candidates"], where="candidates")


def test_gate_result_refuses_a_stale_candidate(script, root):
    write_backtest(root, "ENS", make_nets()["ENS"], digest=digest_of("M1"))
    with pytest.raises(SystemExit):
        script.gate_result(CFG, root)


# ---------------------------------------------------------------- trial_log_with_metrics (S37-5)


def expected_metrics(root: Path, name: str) -> tuple[str, str]:
    summary = json.loads((root / "outputs" / "backtests" / name / "summary.json").read_text(encoding="utf-8"))
    return repr(float(summary["net_sharpe_rf_tbill"])), repr(float(summary["max_drawdown"]))


def parse(text: str) -> list[dict]:
    return list(csv.DictReader(text[:-1].split("\n") if text.endswith("\n") else text.split("\n")))


def test_trial_log_with_metrics_fills_every_human_row(script, pass_root):
    before = trial_bytes(pass_root)
    text, filled = script.trial_log_with_metrics(CFG, pass_root)
    assert filled == 32  # 16 human rows, two cells each
    rows = parse(text)
    assert len(rows) == 19
    for trial_id, name in enumerate(human_names(), start=1):
        row = rows[trial_id - 1]
        assert row["trial_id"] == str(trial_id) and row["kind"] == "human"
        assert (row["is_sharpe"], row["is_mdd"]) == expected_metrics(pass_root, name)
    assert trial_bytes(pass_root) == before  # not written


def test_trial_log_with_metrics_m0_row_takes_m0s_figures(script, pass_root):
    text, _ = script.trial_log_with_metrics(CFG, pass_root)
    row = parse(text)[0]
    assert row["spec_hash"] == digest_of("M0")
    assert (row["is_sharpe"], row["is_mdd"]) == expected_metrics(pass_root, "M0")
    assert expected_metrics(pass_root, "M0") == expected_metrics(pass_root, "M0_L26")


def test_trial_log_with_metrics_values_are_shortest_float_text(script, pass_root):
    text, _ = script.trial_log_with_metrics(CFG, pass_root)
    for row in parse(text)[:16]:
        assert repr(float(row["is_sharpe"])) == row["is_sharpe"]
        assert repr(float(row["is_mdd"])) == row["is_mdd"]


def test_trial_log_with_metrics_keeps_every_other_byte(script, pass_root):
    """Header and agent rows byte-identical; a human row differs only by its two filled cells (csv writer, LF)."""
    old = (pass_root / TRIAL_PATH).read_text(encoding="utf-8")
    text, _ = script.trial_log_with_metrics(CFG, pass_root)
    assert "\r" not in text
    old_lines, new_lines = trial_lines(old), trial_lines(text)
    assert len(new_lines) == len(old_lines) == 20
    assert new_lines[0] == old_lines[0] == ",".join(TRIAL_COLUMNS)
    assert new_lines[17:] == old_lines[17:]  # the three agent rows
    for i, name in enumerate(human_names(), start=1):
        row = next(csv.reader([old_lines[i]]))
        row[TRIAL_COLUMNS.index("is_sharpe")], row[TRIAL_COLUMNS.index("is_mdd")] = expected_metrics(pass_root, name)
        sink = io.StringIO()
        csv.writer(sink, lineterminator="\n").writerow(row)
        assert new_lines[i] + "\n" == sink.getvalue()


def test_trial_log_with_metrics_keeps_agent_metrics(script, pass_root):
    text, _ = script.trial_log_with_metrics(CFG, pass_root)
    rows = parse(text)
    for candidate in (1, 2, 3):
        expected = agent_row(candidate)
        row = rows[AGENT_TRIAL_IDS[candidate] - 1]
        assert row["is_sharpe"] == expected["is_sharpe"] and row["is_mdd"] == expected["is_mdd"]
        assert row["notes"] == expected["notes"]


def test_trial_log_with_metrics_keeps_a_prefilled_equal_value(script, root):
    sharpe, mdd = expected_metrics(root, "M2")
    write_trial_log(root, filled={"M2": (sharpe, mdd)})
    old_line = trial_lines((root / TRIAL_PATH).read_text(encoding="utf-8"))[human_names().index("M2") + 1]
    text, filled = script.trial_log_with_metrics(CFG, root)
    assert filled == 30
    assert trial_lines(text)[human_names().index("M2") + 1] == old_line


def test_trial_log_with_metrics_refuses_a_prefilled_different_value(script, root):
    sharpe, mdd = expected_metrics(root, "M2")
    write_trial_log(root, filled={"M2": (repr(float(sharpe) + 0.01), mdd)})
    before = trial_bytes(root)
    with pytest.raises(SystemExit):
        script.trial_log_with_metrics(CFG, root)
    assert trial_bytes(root) == before


def test_trial_log_with_metrics_refuses_a_prefilled_different_mdd(script, root):
    sharpe, mdd = expected_metrics(root, "M3_d3")
    write_trial_log(root, filled={"M3_d3": (sharpe, repr(float(mdd) - 0.05))})
    with pytest.raises(SystemExit):
        script.trial_log_with_metrics(CFG, root)


def test_trial_log_with_metrics_refuses_a_human_row_without_a_backtest(script, root):
    shutil.rmtree(root / "outputs" / "backtests" / "M3_d2")
    with pytest.raises(SystemExit):
        script.trial_log_with_metrics(CFG, root)


def test_trial_log_with_metrics_m0_without_m0_l26_folder_is_still_matched(script, root):
    shutil.rmtree(root / "outputs" / "backtests" / "M0_L26")
    text, filled = script.trial_log_with_metrics(CFG, root)
    assert filled == 32
    assert (parse(text)[0]["is_sharpe"], parse(text)[0]["is_mdd"]) == expected_metrics(root, "M0")


def test_trial_log_with_metrics_refuses_m0_and_m0_l26_with_different_values(script, root):
    """M0 and M0_L26 share trial 1 and must give equal values (S37-5)."""
    other = make_nets()["M0_L26"] * 1.5
    write_backtest(root, "M0_L26", other)
    with pytest.raises(SystemExit):
        script.trial_log_with_metrics(CFG, root)


def test_trial_log_with_metrics_refuses_a_stale_backtest_folder(script, root):
    write_backtest(root, "M1_a1", make_nets()["M1_a1"], period="OOS")
    with pytest.raises(SystemExit):
        script.trial_log_with_metrics(CFG, root)


# ---------------------------------------------------------------- agent_returns (S37-6), with a fake server


class FakeVault:
    """The vault part of the agent lab's server: run_walkforward(spec, trial_path=...) returns weekly scores."""

    def __init__(self, append_on_call: bool = False):
        self.is_end = IS_END
        self.calls: list[tuple[dict, Path | None]] = []
        self.last: str | None = None
        self.append_on_call = append_on_call

    def run_walkforward(self, spec, evaluate=None, *, trial_path=None):
        digest = spec_hash(spec, CFG)
        self.calls.append((json.loads(json.dumps(spec)), None if trial_path is None else Path(trial_path)))
        self.last = digest
        if self.append_on_call and trial_path is not None:
            append_trial({"author": "agent lab", "kind": "agent", "rung": "M2", "spec_hash": "f" * 64,
                          "params_json": "{}", "notes": "{}"}, path=Path(trial_path))
        seed = int(digest[:8], 16)
        return pd.DataFrame(np.random.default_rng(seed).normal(size=(N_WEEKS, len(SECTORS))), index=WEEKS, columns=SECTORS)

    def forward_returns(self, as_of):
        fwd = pd.DataFrame(0.0, index=WEEKS, columns=list(contracts.universe(CFG).tradables))
        realised = pd.Series(pd.DatetimeIndex(REALISED), index=WEEKS, name="realised_on")
        period = pd.Series("IS", index=WEEKS, name="period", dtype=object)
        return fwd, realised, period

    def tbill_weekly(self, as_of):
        return rf_series()

    def market_states(self, as_of):
        return pd.DataFrame(index=WEEKS)


class FakeServer:
    """The agent lab's server: .vault and .book(scores) (§09 book of the lab; here a lookup of fixed net returns)."""

    def __init__(self, vault: FakeVault, nets: dict[str, pd.Series], *, sharpe_shift: float = 0.0, mdd_shift: float = 0.0):
        self.vault, self.nets = vault, nets
        self.cfg, self.end, self.base_rung = CFG, IS_END, "M2"
        self.sharpe_shift, self.mdd_shift = sharpe_shift, mdd_shift

    def inputs(self) -> dict:
        fwd, _, period = self.vault.forward_returns(self.end)
        return {"fwd": fwd, "period": period, "rf": rf_series()}

    def book(self, scores: pd.DataFrame) -> dict:
        net = self.nets[self.vault.last]
        rf = rf_series(net.index)
        perf = performance(net, rf)
        return {"net": net, "adverse_net": net - 0.001, "rf": rf, "scores": scores,
                "net_sharpe": float(perf["sharpe_rf"]) + self.sharpe_shift,
                "net_sharpe_zero_cost": float(perf["sharpe_zero_cost"]),
                "max_drawdown": float(perf["max_drawdown"]) + self.mdd_shift, "mean_turnover": 1.0,
                "mean_abs_residual_beta": 0.0, "adverse_net_sharpe": float(performance(net - 0.001, rf)["sharpe_rf"])}


def fake_server(**kwargs) -> FakeServer:
    vault = FakeVault(append_on_call=kwargs.pop("append_on_call", False))
    nets = {agent_digest(c): net for c, net in agent_nets().items()}
    return FakeServer(vault, nets, **kwargs)


@pytest.fixture
def agent_root(tmp_path) -> Path:
    """A root with the trial log and backtests but no agent folders yet."""
    make_root(tmp_path / "project", agent_folders=False)
    return tmp_path / "project"


AGENT_SUMMARY_KEYS = {"trial_id", "candidate", "spec_hash", "net_sharpe_rf_tbill", "max_drawdown", "weeks", "first_week",
                      "last_week"}


def agent_folder(root: Path, candidate: int) -> Path:
    return root / s05().AGENT_DIR / f"agent_c{candidate:02d}"


def test_agent_returns_rescores_only_the_walk_forward_rows(script, agent_root):
    server = fake_server()
    script.agent_returns(CFG, agent_root, server)
    specs = [canonical(spec) for spec, _ in server.vault.calls]
    assert specs == [canonical(agent_spec(1)), canonical(agent_spec(2))]
    for _, trial_path in server.vault.calls:
        assert trial_path is not None and trial_path.resolve() == (agent_root / TRIAL_PATH).resolve()
    assert not agent_folder(agent_root, 3).exists()


def test_agent_returns_writes_weekly_and_summary(script, agent_root):
    out = script.agent_returns(CFG, agent_root, fake_server())
    assert len(out) == 2
    for candidate, net in agent_nets().items():
        folder = agent_folder(agent_root, candidate)
        weekly = read_weekly(folder / "weekly.csv")
        for column in ("realised_on", "period", "net", "rf"):
            assert column in weekly.columns
        np.testing.assert_allclose(weekly["net"].to_numpy(dtype=float), net.to_numpy(), rtol=0, atol=1e-15)
        np.testing.assert_allclose(weekly["rf"].to_numpy(dtype=float), RF, rtol=0, atol=1e-15)
        assert (weekly["period"] == "IS").all()
        assert (pd.to_datetime(weekly["realised_on"]) <= IS_END).all()
        assert (pd.DatetimeIndex(weekly.index.get_level_values("date_close")) <= IS_END).all()
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        assert AGENT_SUMMARY_KEYS <= set(summary)
        sharpe, mdd = headline(net)
        assert str(summary["trial_id"]) == str(AGENT_TRIAL_IDS[candidate])
        assert int(summary["candidate"]) == candidate
        assert summary["spec_hash"] == agent_digest(candidate)
        assert summary["net_sharpe_rf_tbill"] == pytest.approx(sharpe, abs=1e-9)
        assert summary["max_drawdown"] == pytest.approx(mdd, abs=1e-9)
        assert summary["weeks"] == N_WEEKS
        assert summary["first_week"] == FRIDAYS[0].strftime("%Y-%m-%d")
        assert summary["last_week"] == "2019-12-13"
        assert not (folder / "used.yaml").exists()


def test_agent_returns_returns_one_summary_per_candidate(script, agent_root):
    out = script.agent_returns(CFG, agent_root, fake_server())
    assert [int(item["candidate"]) for item in out] == [1, 2]
    for item in out:
        on_disk = json.loads((agent_folder(agent_root, int(item["candidate"])) / "summary.json").read_text(encoding="utf-8"))
        assert_close(dict(item), on_disk, rel=1e-12, where="summary")


def test_agent_returns_keeps_the_trial_log_byte_identical(script, agent_root):
    before = trial_bytes(agent_root)
    script.agent_returns(CFG, agent_root, fake_server())
    assert trial_bytes(agent_root) == before


def test_agent_returns_refuses_a_stale_spec_hash(script, agent_root):
    write_trial_log(agent_root, agent_digests={2: "a" * 64})
    server = fake_server()
    with pytest.raises(SystemExit):
        script.agent_returns(CFG, agent_root, server)
    assert all(canonical(spec) != canonical(agent_spec(2)) for spec, _ in server.vault.calls)


def test_agent_returns_refuses_a_spec_hash_under_another_config(script, agent_root):
    other = copy.deepcopy(CFG)
    other["models"]["M2"]["alpha"] = [0.1, 1, 100]
    with pytest.raises(SystemExit):
        script.agent_returns(other, agent_root, fake_server())


@pytest.mark.parametrize(("sharpe_shift", "mdd_shift"), [(1e-6, 0.0), (0.0, 1e-6), (-1e-3, 0.0), (0.0, -1e-8)])
def test_agent_returns_refuses_a_figure_that_does_not_reproduce(script, agent_root, sharpe_shift, mdd_shift):
    with pytest.raises(SystemExit):
        script.agent_returns(CFG, agent_root, fake_server(sharpe_shift=sharpe_shift, mdd_shift=mdd_shift))


def test_agent_returns_accepts_differences_within_1e_9(script, agent_root):
    out = script.agent_returns(CFG, agent_root, fake_server(sharpe_shift=1e-12, mdd_shift=-1e-12))
    assert len(out) == 2


def test_agent_returns_refuses_a_trial_log_that_changed(script, agent_root):
    with pytest.raises(SystemExit):
        script.agent_returns(CFG, agent_root, fake_server(append_on_call=True))


def test_agent_returns_then_trial_matrix_holds_the_agent_columns(script, agent_root):
    script.agent_returns(CFG, agent_root, fake_server())
    matrix, columns, _ = script.trial_matrix(CFG, agent_root)
    assert matrix.shape[1] == 18
    for net in agent_nets().values():
        assert any(np.allclose(matrix[c].to_numpy(dtype=float), net.to_numpy(), rtol=0, atol=1e-15) for c in matrix.columns)
    assert sum(1 for c in columns if c["kind"] == "agent") == 2


# ---------------------------------------------------------------- trial_matrix (S37-7)

COLUMN_KEYS = {"name", "kind", "rung", "spec_hash", "trial_ids", "source"}


@pytest.fixture(scope="module")
def pass_matrix(pass_root):
    return s05().trial_matrix(CFG, pass_root)


def test_trial_matrix_has_one_column_per_distinct_spec_hash(pass_matrix):
    matrix, columns, _ = pass_matrix
    assert matrix.shape == (N_WEEKS, 18)  # 16 human hashes (M0 = M0_L26) and 2 agent candidates
    assert len(columns) == 18
    hashes = [c["spec_hash"] for c in columns]
    assert len(set(hashes)) == 18
    assert set(hashes) == {digest_of(name) for name in names()} | {agent_digest(1), agent_digest(2)}
    for c in columns:
        assert COLUMN_KEYS <= set(c)
    assert np.isfinite(matrix.to_numpy(dtype=float)).all()


def test_trial_matrix_kinds(pass_matrix):
    _, columns, _ = pass_matrix
    assert sum(1 for c in columns if c["kind"] == "human") == 16
    assert sum(1 for c in columns if c["kind"] == "agent") == 2
    for c in columns:
        if c["kind"] == "agent":
            assert c["rung"] == "M2"


def test_trial_matrix_m0_and_m0_l26_are_one_column(pass_matrix):
    matrix, columns, _ = pass_matrix
    m0 = [c for c in columns if c["spec_hash"] == digest_of("M0")]
    assert len(m0) == 1
    assert [str(t) for t in m0[0]["trial_ids"]] == ["1"]
    target = make_nets()["M0"].to_numpy()
    assert sum(np.allclose(matrix[c].to_numpy(dtype=float), target, rtol=0, atol=0) for c in matrix.columns) == 1


def test_trial_matrix_columns_carry_their_trial_ids(pass_matrix):
    _, columns, _ = pass_matrix
    by_hash = {c["spec_hash"]: [str(t) for t in c["trial_ids"]] for c in columns}
    for trial_id, name in enumerate(human_names(), start=1):
        assert by_hash[digest_of(name)] == [str(trial_id)]
    assert by_hash[agent_digest(1)] == ["17"] and by_hash[agent_digest(2)] == ["18"]


def test_trial_matrix_holds_every_backtest_and_agent_series(pass_matrix):
    matrix, _, _ = pass_matrix
    series = [net for name, net in make_nets().items() if name != "M0_L26"] + list(agent_nets().values())
    for net in series:
        assert any(np.allclose(matrix[c].to_numpy(dtype=float), net.to_numpy(), rtol=0, atol=0) for c in matrix.columns)


def test_trial_matrix_lists_the_excluded_trial_rows(pass_matrix):
    _, _, excluded = pass_matrix
    assert len(excluded) == 1
    assert str(excluded[0]["trial_id"]) == "19"
    assert excluded[0]["kind"] == "agent"
    assert excluded[0]["stage"] == "redundancy"


def test_trial_matrix_uses_the_common_weeks(script, root):
    net = agent_nets()[2].iloc[8:]
    write_agent_folder(root, 2, net)
    matrix, _, _ = script.trial_matrix(CFG, root)
    assert len(matrix) == N_WEEKS - 8
    closes = pd.DatetimeIndex(matrix.index.get_level_values("date_close")) if isinstance(matrix.index, pd.MultiIndex) \
        else pd.DatetimeIndex(matrix.index)
    assert closes.equals(pd.DatetimeIndex(FRIDAYS[8:]))
    target = make_nets()["M0"].iloc[8:].to_numpy()
    assert any(np.allclose(matrix[c].to_numpy(dtype=float), target, rtol=0, atol=0) for c in matrix.columns)


def test_trial_matrix_refuses_a_walk_forward_agent_row_without_its_folder(script, root):
    shutil.rmtree(agent_folder(root, 2))
    with pytest.raises(SystemExit):
        script.trial_matrix(CFG, root)


def test_trial_matrix_refuses_an_agent_folder_with_another_spec_hash(script, root):
    write_agent_folder(root, 1, agent_nets()[1], digest=agent_digest(2))
    with pytest.raises(SystemExit):
        script.trial_matrix(CFG, root)


def test_trial_matrix_refuses_a_stale_backtest_folder(script, root):
    write_walkforward_summary(root, "M3_d3", digest=digest_of("M3_d2"))
    with pytest.raises(SystemExit):
        script.trial_matrix(CFG, root)


# ---------------------------------------------------------------- selection_bias (S37-7)


@pytest.fixture(scope="module")
def pass_bias(pass_root):
    return s05().selection_bias(CFG, pass_root, "M1")


def test_selection_bias_keys(pass_bias):
    assert {"selected", "dsr", "pbo", "matrix", "excluded"} <= set(pass_bias)
    assert pass_bias["selected"] == "M1"


def test_selection_bias_dsr_is_the_deflated_sharpe_of_the_selected_model(pass_root, pass_matrix, pass_bias):
    matrix, _, _ = pass_matrix
    n_trials = len(parse((pass_root / TRIAL_PATH).read_text(encoding="utf-8")))
    assert n_trials == 19
    expected = deflated_sharpe_ratio(backtest_net(pass_root, "M1"), n_trials, trial_returns=matrix)
    assert pass_bias["dsr"]["value"] == pytest.approx(expected, rel=1e-12, abs=1e-15)


def test_selection_bias_dsr_counts_every_trial_row(pass_bias):
    values = numbers_in(pass_bias["dsr"])
    assert 19 in values  # N: every row of the trial log
    assert 16 in values and 3 in values  # human and agent rows
    assert N_WEEKS in values


def test_selection_bias_pbo_is_cscv_on_the_matrix(pass_matrix, pass_bias):
    matrix, _, _ = pass_matrix
    expected = pbo_cscv(matrix, CFG["inference"]["pbo_blocks"])
    assert pass_bias["pbo"]["value"] == pytest.approx(expected, rel=1e-12, abs=1e-15)
    assert CFG["inference"]["pbo_blocks"] in numbers_in(pass_bias["pbo"])
    assert math.comb(16, 8) in numbers_in(pass_bias["pbo"])  # 12,870 splits


def test_selection_bias_describes_the_matrix(pass_bias):
    described = pass_bias["matrix"]
    assert described["weeks"] == N_WEEKS
    lists = [v for v in described.values() if isinstance(v, list)]
    assert any(len(v) == 18 and all(isinstance(c, dict) and COLUMN_KEYS <= set(c) for c in v) for v in lists)


def test_selection_bias_lists_the_excluded_rows(pass_matrix, pass_bias):
    _, _, excluded = pass_matrix
    assert_close(list(pass_bias["excluded"]), list(excluded), where="excluded")


def test_selection_bias_of_the_fallback_uses_m0_stars_returns(fail_root):
    bias = s05().selection_bias(CFG, fail_root, "M0_star")
    matrix, _, _ = s05().trial_matrix(CFG, fail_root)
    expected = deflated_sharpe_ratio(backtest_net(fail_root, "M0_star"), 19, trial_returns=matrix)
    assert bias["selected"] == "M0_star"
    assert bias["dsr"]["value"] == pytest.approx(expected, rel=1e-12, abs=1e-15)


# ---------------------------------------------------------------- select: writes, format, atomicity


def json_pairs_sorted(text: str) -> bool:
    """True if every JSON object in the text lists its keys in sorted order."""
    ok = True

    def hook(pairs):
        nonlocal ok
        keys = [key for key, _ in pairs]
        ok = ok and keys == sorted(keys)
        return dict(pairs)

    json.loads(text, object_pairs_hook=hook)
    return ok


def test_select_writes_the_gate_the_diagnostics_and_the_trial_log(script, root):
    gate = script.gate_result(CFG, root)
    text, _ = script.trial_log_with_metrics(CFG, root)
    bias = script.selection_bias(CFG, root, gate["selected"])
    script.select(CFG, root)
    gate_file, bias_file = root / script.GATE_FILE, root / script.BIAS_FILE
    assert gate_file.exists() and bias_file.exists()
    assert_close(json.loads(gate_file.read_text(encoding="utf-8")), json.loads(json.dumps(gate, default=float)),
                 where="gate")
    assert_close(json.loads(bias_file.read_text(encoding="utf-8")), json.loads(json.dumps(bias, default=float)),
                 where="bias")
    assert (root / TRIAL_PATH).read_bytes() == text.encode("utf-8")


def test_select_files_are_sorted_json_with_lf(script, root):
    script.select(CFG, root)
    for name in (script.GATE_FILE, script.BIAS_FILE):
        raw = (root / name).read_bytes()
        assert b"\r" not in raw
        assert json_pairs_sorted(raw.decode("utf-8"))
    assert b"\r" not in trial_bytes(root)


def test_select_is_deterministic_and_rerunnable(script, root):
    """A second run gives the same bytes (no timestamp; the filled cells equal the values, so they are kept)."""
    script.select(CFG, root)
    first = [(root / name).read_bytes() for name in (script.GATE_FILE, script.BIAS_FILE, TRIAL_PATH)]
    script.select(CFG, root)
    assert [(root / name).read_bytes() for name in (script.GATE_FILE, script.BIAS_FILE, TRIAL_PATH)] == first


def test_select_with_no_passing_candidate_records_the_fallback(script, tmp_path):
    make_root(tmp_path / "f", passing=())
    script.select(CFG, tmp_path / "f")
    gate = json.loads((tmp_path / "f" / script.GATE_FILE).read_text(encoding="utf-8"))
    bias = json.loads((tmp_path / "f" / script.BIAS_FILE).read_text(encoding="utf-8"))
    assert gate["selected"] == "M0_star" and gate["fallback"] is True
    assert gate["statement"] == FALLBACK_STATEMENT
    assert bias["selected"] == "M0_star"


def _break_gate(root: Path) -> None:
    write_backtest(root, "ENS", make_nets()["ENS"], digest=digest_of("M1"))


def _break_trial_log(root: Path) -> None:
    sharpe, mdd = expected_metrics(root, "M2")
    write_trial_log(root, filled={"M2": (repr(float(sharpe) + 0.01), mdd)})


def _break_diagnostics(root: Path) -> None:
    shutil.rmtree(agent_folder(root, 1))


def _break_agent_hash(root: Path) -> None:
    write_agent_folder(root, 2, agent_nets()[2], digest="b" * 64)


def _break_human_backtest(root: Path) -> None:
    shutil.rmtree(root / "outputs" / "backtests" / "M2_a10")


@pytest.mark.parametrize("breaker", [_break_gate, _break_trial_log, _break_diagnostics, _break_agent_hash,
                                     _break_human_backtest])
def test_select_writes_nothing_when_any_check_fails(script, root, breaker):
    breaker(root)
    gate_file, bias_file = root / script.GATE_FILE, root / script.BIAS_FILE
    gate_file.parent.mkdir(parents=True, exist_ok=True)
    gate_file.write_bytes(b"old\n")
    log_before = trial_bytes(root)
    with pytest.raises(SystemExit):
        script.select(CFG, root)
    assert gate_file.read_bytes() == b"old\n"
    assert not bias_file.exists()
    assert trial_bytes(root) == log_before


def test_select_failure_leaves_no_metrics_files_on_a_fresh_root(script, root):
    _break_diagnostics(root)
    with pytest.raises(SystemExit):
        script.select(CFG, root)
    assert not (root / script.GATE_FILE).exists()
    assert not (root / script.BIAS_FILE).exists()


# ---------------------------------------------------------------- command line


@pytest.mark.parametrize("argv", [["--select", "--model", "M0"], ["--select", "--fixed", "M1_a1"],
                                  ["--agent-returns", "--model", "M1"], ["--agent-returns", "--fixed", "M0_L13"]])
def test_main_select_and_agent_returns_exclude_model_and_fixed(script, argv):
    with pytest.raises(SystemExit) as raised:
        script.main(argv)
    assert raised.value.code == 2  # argparse usage error, before anything runs


def test_main_help_lists_the_new_options(script, capsys):
    with pytest.raises(SystemExit) as raised:
        script.main(["--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert "--select" in out and "--agent-returns" in out
    assert "--model" in out and "--fixed" in out


# -- additions after the session audit (S37-8) ---------------------------------------------------------------------------


def test_select_refuses_once_frozen_lock_exists(script, root):
    (root / "FROZEN.lock").write_text("{}\n", encoding="utf-8")
    before = trial_bytes(root)
    with pytest.raises(SystemExit, match="FROZEN.lock"):
        script.select(CFG, root)
    assert trial_bytes(root) == before
    assert not (root / script.GATE_FILE).exists() and not (root / script.BIAS_FILE).exists()


def test_agent_returns_refuses_once_frozen_lock_exists(script, root):
    (root / "FROZEN.lock").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="FROZEN.lock"):
        script.agent_returns(CFG, root, server=None)


def test_select_leaves_no_temporary_file(script, root):
    script.select(CFG, root)
    leftovers = [p for p in root.rglob("*.tmp")]
    assert leftovers == []


def test_trial_rows_refuse_a_row_with_an_extra_field(script, root):
    path = root / TRIAL_PATH
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "99,x,y,human,M1,abc,{},,,notes,extra\n", encoding="utf-8", newline="\n")
    with pytest.raises(SystemExit, match="fields"):
        script.trial_rows(root)


def test_gate_frames_refuse_a_candidate_order_other_than_the_decision(script, root):
    cfg = copy.deepcopy(CFG)
    cfg["models"]["candidate_order"] = ["M1", "M2", "M5", "ENS"]
    with pytest.raises(SystemExit, match="S37-4"):
        script.gate_inputs(cfg, root)
