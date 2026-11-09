"""M7 as the base rung of the round-2 lab: the vault, the model pipeline and the ddmi-vault server (decision S43-3;
Amendment 9 C2 with Amendment 7 C2 and C3).

Written from the decisions and the session's interface only. The market is the shared synthetic market (sessions
2011-01-03 to 2020-12-31) truncated at the In-Sample end, held in memory by the Vault (frames), with a copy of
config.yaml whose warm-up ends in 2012, whose test years are 2014-2019, whose inner validation window is 26 weeks and
whose round2.test_weeks is the synthetic test-week count (as tests/test_round2_walkforward.py). Temporary lock, logs and
trial logs; no real data, no network, no LLM.
"""

import copy
import csv
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src import backtest, contracts, data, features, models
from src import labels as labels_mod
from src.agents import dsl
from src.agents.vault_server import VaultServer
from src.config import load_config
from src.vault import Vault, spec_hash

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])
FIRST_WEEK, LAST_WEEK = "2014-01-03", "2019-12-13"
N_TEST_WEEKS = len(pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D"))
VENDOR = re.compile(r"anthropic|claude", re.IGNORECASE)

LOG_CLOSE = {"op": "log", "x": {"input": "close"}}
LOG_RETURN = {"op": "diff", "n": 1, "x": LOG_CLOSE}
VOL_RATIO = {"name": "vol ratio 4 over 26", "expr": {"op": "cs_z", "x": {
    "op": "ratio", "a": {"op": "rolling", "stat": "std", "n": 4, "x": LOG_RETURN},
    "b": {"op": "rolling", "stat": "std", "n": 26, "x": LOG_RETURN}}}}
VOL_RATIO_X_STATES = {"name": "vol ratio in bear markets", "expr": {"op": "mul_state", "state": ["BEAR24", "VIX"],
                                                                     "x": VOL_RATIO["expr"]}}
FIXED_M7 = {"alpha": 1, "half_life_weeks": 2}


def synthetic_cfg() -> dict:
    cfg = copy.deepcopy(CFG)
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2013]
    cfg["split"]["test_years"] = [2014, 2019]
    cfg["tuning"]["inner_validation_weeks"] = 26
    cfg["round2"]["test_weeks"] = N_TEST_WEEKS
    return cfg


SYN_CFG = synthetic_cfg()
_FRAMES: dict = {}
_RUNS: dict = {}


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frames(market) -> dict:
    """In-memory vault tables: the built tables to the IS end, the 4-week labels, daily_close and dgs3mo."""
    if not _FRAMES:
        keep = market.daily_close.index <= IS_END
        close, opens = market.daily_close.loc[keep], market.daily_open.loc[keep]
        sessions = pd.DatetimeIndex(close.index)
        weekly_open, _ = data.weekly_panel(opens, close)
        fwd, realised_on, period = backtest.forward_returns(weekly_open, IS_END)
        table = fwd.copy()
        table["realised_on"], table["period"] = realised_on, period
        dgs3mo = market.fred[["DGS3MO"]].copy()
        dgs3mo.index = pd.DatetimeIndex(dgs3mo.index, name="date")
        _FRAMES.update({
            "features": features.asset_features(close, SYN_CFG),
            "market_states": features.market_states(close, market.vix[market.vix.index <= IS_END],
                                                    market.fred[market.fred.index <= IS_END], SYN_CFG),
            "labels": labels_mod.make_labels(fwd, sessions),
            "labels_h4": labels_mod.make_horizon_labels(weekly_open, sessions, 4),
            "momentum_variants": features.momentum_variants(close, cfg=SYN_CFG),
            "sizing_betas": features.sizing_betas(close, SYN_CFG),
            "forward_returns": table,
            "daily_close": market.daily_close.copy(),
            "dgs3mo": dgs3mo,
            "_fwd": (fwd, realised_on, period),
        })
    return {name: (frame.copy() if hasattr(frame, "copy") else frame) for name, frame in _FRAMES.items()
            if not name.startswith("_")}


def make_vault(market, root: Path) -> Vault:
    return Vault(IS_END, lock_path=root / "FROZEN.lock", log_path=root / "vault_access_log.jsonl",
                 frames=frames(market), cfg=SYN_CFG)


def ladder(market, agent=None, pairs=()) -> dict:
    """LadderData (with betas and forward returns for tuning), the 4-week labels and round 1's folds."""
    frames(market)
    feats = _FRAMES["features"].copy()
    if agent is not None:
        feats["AG1"] = agent
    fwd, realised_on, period = _FRAMES["_fwd"]
    d = models.LadderData(features=feats, states=_FRAMES["market_states"], labels=_FRAMES["labels"],
                          betas=_FRAMES["sizing_betas"], fwd=fwd, realised_on=realised_on, period=period,
                          momentum=_FRAMES["momentum_variants"], agent_columns=tuple(pairs))
    weeks = fwd.index
    folds = labels_mod.walk_forward_folds(weeks, labels_mod.label_end_by_week(d.labels, weeks), SYN_CFG)
    return {"data": d, "labels4": _FRAMES["labels_h4"], "folds": folds}


def m7_plain(market, value):
    key = ("M7", None if value is None else tuple(sorted(value.items())))
    if key not in _RUNS:
        r = ladder(market)
        _RUNS[key] = models.walkforward_round2("M7", r["data"], r["labels4"], r["folds"], SYN_CFG, value=value)
    return _RUNS[key]


def closes_of(index) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def read_trials(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def log_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------- src.models: walkforward_round2 with an agent column


@pytest.mark.parametrize("rung, value", [("M6", {"alpha": 1}), ("M8", {"max_depth": 2, "half_life_weeks": 2})])
def test_m6_and_m8_refuse_agent_columns(synthetic_market, rung, value):
    r = ladder(synthetic_market, agent=0.0, pairs=(("AG1", ()),))
    with pytest.raises(ValueError):
        models.walkforward_round2(rung, r["data"], r["labels4"], r["folds"], SYN_CFG, value=value)


@pytest.mark.parametrize("value", [FIXED_M7, {"alpha": 10, "half_life_weeks": 4}])
def test_a_zero_information_column_reproduces_m7(synthetic_market, value):
    """AG1 = 0 everywhere adds nothing to the ridge fit: M7 + AG1 scores equal M7's within 1e-9, on the same weeks."""
    r = ladder(synthetic_market, agent=0.0, pairs=(("AG1", ()),))
    got, selection = models.walkforward_round2("M7", r["data"], r["labels4"], r["folds"], SYN_CFG, value=value)
    expected, _ = m7_plain(synthetic_market, value)
    assert selection is None
    assert got.index.equals(expected.index) and list(got.columns) == list(expected.columns)
    np.testing.assert_allclose(got.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-9)


def test_a_candidate_scores_the_same_weeks_as_m7(synthetic_market):
    close = synthetic_market.daily_close[synthetic_market.daily_close.index <= IS_END]
    frames(synthetic_market)
    u = contracts.universe(SYN_CFG)
    agent = dsl.evaluate(VOL_RATIO, close[list(u.sectors) + [u.benchmark]], SYN_CFG)
    agent = agent.reindex(_FRAMES["features"].index).to_numpy()
    r = ladder(synthetic_market, agent=agent, pairs=(("AG1", ()),))
    got, _ = models.walkforward_round2("M7", r["data"], r["labels4"], r["folds"], SYN_CFG, value=FIXED_M7)
    expected, _ = m7_plain(synthetic_market, FIXED_M7)
    assert got.index.equals(expected.index)
    assert len(got) == N_TEST_WEEKS
    assert list(closes_of(got.index)) == list(pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D"))
    assert not np.allclose(got.to_numpy(), expected.to_numpy(), equal_nan=True)  # the feature changes the scores


def test_every_candidate_fit_is_purged_by_the_four_week_label_end(synthetic_market, monkeypatch):
    """Every assert_purged call of an M7 + AG1 run (inner and full fits) gets 4-week label_ends, all <= purge_end."""
    calls = []
    original = models.assert_purged

    def spy(label_end, fold, *args, **kwargs):
        calls.append((label_end.copy(), fold))
        return original(label_end, fold, *args, **kwargs)

    monkeypatch.setattr(models, "assert_purged", spy)
    r = ladder(synthetic_market, agent=0.0, pairs=(("AG1", ()),))
    labels4 = r["labels4"]
    models.walkforward_round2("M7", r["data"], labels4, r["folds"][:2], SYN_CFG)  # tuned: inner and full fits
    assert len(calls) >= 4
    for label_end, fold in calls:
        assert len(label_end) > 0
        ends = pd.to_datetime(label_end)
        assert (ends <= fold.purge_end).all()
        expected = pd.to_datetime(labels4.loc[label_end.index, "label_end"])
        np.testing.assert_array_equal(ends.to_numpy(), expected.to_numpy())  # the 4-week label_end, not the 1-week one


def test_a_late_four_week_label_in_a_candidate_fit_raises(synthetic_market):
    r = ladder(synthetic_market, agent=0.0, pairs=(("AG1", ()),))
    labels4, fold = r["labels4"], r["folds"][0]
    closes = closes_of(labels4.index)
    ends = pd.DatetimeIndex(labels4["label_end"])
    train_weeks = np.unique(closes[np.asarray((closes >= fold.train_start) & (ends <= fold.purge_end))])
    bad = labels4.copy()
    bad.loc[np.asarray(closes == pd.Timestamp(train_weeks[20])), "label_end"] = fold.purge_end + pd.Timedelta(days=1)
    contracts.validate_labels(bad)
    with pytest.raises(contracts.ContractError):
        models.walkforward_round2("M7", r["data"], bad, r["folds"], SYN_CFG, value=FIXED_M7)


def test_a_mul_state_candidate_joins_the_design_with_its_in_fold_product(synthetic_market, monkeypatch):
    """S43-3: AG1 and AG1_x_BEAR24_x_VIX_Z join M7's design (the six asset features and the five interactions)."""
    seen = []
    original = models.fit_transform_train

    def spy(*args, **kwargs):
        X, params = original(*args, **kwargs)
        seen.append(list(params["columns"]))
        return X, params

    monkeypatch.setattr(models, "fit_transform_train", spy)
    pairs = (("AG1", ("BEAR24", "VIX")),)
    r = ladder(synthetic_market, agent=0.5, pairs=pairs)
    models.walkforward_round2("M7", r["data"], r["labels4"], r["folds"][:1], SYN_CFG, value=FIXED_M7)
    asset = list(SYN_CFG["features"]["asset"])
    interactions = list(contracts.interaction_columns(SYN_CFG))
    assert seen
    for columns in seen:
        assert columns[:6] == asset
        assert set(columns) == set(asset) | set(interactions) | {"AG1", "AG1_x_BEAR24_x_VIX_Z"}
        assert len(columns) == 6 + len(interactions) + 2


# ---------------------------------------------------------------- src.vault: agent_features on M7


def m7_specs() -> dict:
    round2, tuning = models.round2_spec_settings(SYN_CFG), models.tuning_spec(SYN_CFG)
    return {"round2": round2, "tuning": tuning}


@pytest.mark.parametrize("spec", [
    {"rung": "M6", "params": {"alpha": 1}, "agent_features": [VOL_RATIO]},
    {"rung": "M6", "tuning": "T", "agent_features": [VOL_RATIO]},
    {"rung": "M8", "params": {"max_depth": 2, "half_life_weeks": 2}, "agent_features": [VOL_RATIO]},
    {"rung": "M8", "tuning": "T", "agent_features": [VOL_RATIO]},
    {"rung": "M7", "tuning": "T", "agent_features": []},
    {"rung": "M7", "tuning": "T", "agent_features": VOL_RATIO},
    {"rung": "M7", "tuning": "T", "agent_features": [VOL_RATIO, VOL_RATIO]},
    {"rung": "M7", "tuning": "T", "agent_features": [{"name": "x", "expr": {"input": "close"}}]},
    {"rung": "M7", "agent_features": [VOL_RATIO]},  # neither params nor tuning (S41-5 still applies)
    {"rung": "M7", "tuning": "T", "agent_features": [VOL_RATIO], "round2": "whole"},  # the whole round2 section
])
def test_the_vault_refuses_agent_features_outside_m7_and_bad_m7_specs(synthetic_market, tmp_path, spec):
    vault = make_vault(synthetic_market, tmp_path)
    full = {"round2": models.round2_spec_settings(SYN_CFG), **spec, "author": "agent lab", "kind": "agent"}
    if full.get("tuning") == "T":
        full["tuning"] = models.tuning_spec(SYN_CFG)
    if full.get("round2") == "whole":
        full["round2"] = SYN_CFG["round2"]
    trials = tmp_path / "trial_log.csv"
    with pytest.raises(ValueError):
        vault.run_walkforward(full, trial_path=trials)
    assert log_lines(tmp_path / "vault_access_log.jsonl")[-1]["result"] == "refused"
    assert not trials.exists()


def test_the_vault_runs_a_fixed_m7_spec_with_an_agent_feature_like_the_pipeline(synthetic_market, tmp_path):
    """The vault's M7 + agent run equals walkforward_round2 on LadderData with AG1 = the DSL asset part (S43-3)."""
    vault = make_vault(synthetic_market, tmp_path)
    spec = {"rung": "M7", "round2": models.round2_spec_settings(SYN_CFG), "params": dict(FIXED_M7),
            "agent_features": [VOL_RATIO_X_STATES], "author": "agent lab", "kind": "agent",
            "notes": "agent lab candidate"}
    trials = tmp_path / "trial_log.csv"
    got = vault.run_walkforward(spec, trial_path=trials)
    contracts.validate_scores(got)
    agent = dsl.evaluate(VOL_RATIO_X_STATES, vault.daily_closes(IS_END), SYN_CFG)
    r = ladder(synthetic_market, agent=agent.reindex(_FRAMES["features"].index).to_numpy(),
               pairs=(("AG1", ("BEAR24", "VIX")),))
    expected, _ = models.walkforward_round2("M7", r["data"], r["labels4"], r["folds"], SYN_CFG, value=FIXED_M7)
    pd.testing.assert_frame_equal(got, expected)
    rows = read_trials(trials)
    assert len(rows) == 1 and rows[0]["rung"] == "M7" and rows[0]["kind"] == "agent"
    assert rows[0]["spec_hash"] == spec_hash(spec, SYN_CFG)
    assert not VENDOR.search(rows[0]["params_json"] + rows[0]["notes"])


# ---------------------------------------------------------------- src.agents.vault_server with base rung M7


_ENV: dict = {}


@pytest.fixture
def m7_env(synthetic_market, tmp_path_factory):
    """A VaultServer on M7 (05's model_spec) over the synthetic vault, and one full Validator run of VOL_RATIO; built
    once per module and shared (read-only)."""
    if not _ENV:
        _ENV["env"] = _build_m7_env(synthetic_market, tmp_path_factory)
    return _ENV["env"]


def _build_m7_env(market, tmp_path_factory):
    base = tmp_path_factory.mktemp("round2_server")
    vault = make_vault(market, base)
    w05 = load_script("train_walkforward_round2_lab", "05_train_walkforward.py")
    base_spec = w05.model_spec("M7", SYN_CFG)
    trial_path, server_log = base / "trial_log.csv", base / "vault_server_log.jsonl"
    core = VaultServer(SYN_CFG, vault, "M7", base_spec, trial_path=trial_path, server_log=server_log)
    before = read_trials(trial_path)
    result = core.run_walkforward(VOL_RATIO, candidate=4, cost_usd=0.0123)
    added = [row for row in read_trials(trial_path)[len(before):] if row["kind"] == "agent"]
    return SimpleNamespace(market=market, vault=vault, core=core, base=base, w05=w05, base_spec=base_spec,
                           trial_path=trial_path, server_log=server_log, result=result, added=added)


def test_candidate_spec_with_base_m7(m7_env):
    assert m7_env.core.candidate_spec(VOL_RATIO) == {
        "rung": "M7", "round2": models.round2_spec_settings(SYN_CFG), "tuning": models.tuning_spec(SYN_CFG),
        "agent_features": [VOL_RATIO], "author": "agent lab", "kind": "agent", "notes": "agent lab candidate"}


def test_m7_validator_reaches_the_walk_forward(m7_env):
    result = m7_env.result
    assert result["stage"] == "walk_forward", result.get("reason")
    metrics = result["metrics"]
    assert metrics["weeks"] == N_TEST_WEEKS
    assert metrics["base_net_sharpe"] == pytest.approx(m7_env.core.base()["net_sharpe"], abs=1e-3)
    assert metrics["uplift"] == pytest.approx(metrics["net_sharpe"] - metrics["base_net_sharpe"], abs=1e-3)
    assert {"turnover", "residual_beta", "cost_sensitivity", "passed"} <= set(result["risk_checks"])
    assert result["passed"] is bool(metrics["passed_gate"])


def test_m7_validator_uses_the_lab_gate_of_s33_6(m7_env):
    """S43-3 (a): uplift >= 0.15, drawdown no more than 2 points worse, P(uplift > 0) >= 0.80 (selection:)."""
    m = m7_env.result["metrics"]
    sel = SYN_CFG["selection"]
    assert float(sel["bootstrap_prob"]) == 0.80
    expected = bool(m["uplift"] >= float(sel["sharpe_uplift"]) - 1e-4
                    and m["max_drawdown_change"] >= -float(sel["mdd_tolerance"]) - 1e-4
                    and m["p_uplift_positive"] >= 0.80 - 1e-4)
    borderline = any(abs(x) < 1e-4 for x in (m["uplift"] - 0.15, m["max_drawdown_change"] + 0.02,
                                              m["p_uplift_positive"] - 0.80))
    if not borderline:
        assert m["passed_gate"] is expected


def test_m7_candidate_trial_row(m7_env):
    assert len(m7_env.added) == 1
    row = m7_env.added[0]
    spec = m7_env.core.candidate_spec(VOL_RATIO)
    assert (row["kind"], row["author"], row["rung"]) == ("agent", "agent lab", "M7")
    assert row["spec_hash"] == spec_hash(spec, SYN_CFG) == m7_env.result["spec_hash"]
    assert json.loads(row["params_json"]) == spec
    assert "round2" in json.loads(row["params_json"])
    notes = json.loads(row["notes"])
    assert notes["stage"] == "walk_forward" and notes["candidate"] == 4
    assert notes["cost_usd"] == pytest.approx(0.0123)
    assert not VENDOR.search(row["params_json"] + row["notes"])


def test_the_m7_base_reuses_05s_spec(m7_env):
    """The base book is 05's tuned M7 spec; its row (if written to this scratch log) is that spec's hash."""
    m7_env.core.base()
    rows = [row for row in read_trials(m7_env.trial_path) if row["kind"] == "human"]
    assert all(row["spec_hash"] == spec_hash(m7_env.base_spec, SYN_CFG) for row in rows)
    assert m7_env.base_spec["rung"] == "M7" and "tuning" in m7_env.base_spec


def _server(m7_env, tmp_path, rung="M7", spec=None):
    trial_path, server_log = tmp_path / "trial_log.csv", tmp_path / "vault_server_log.jsonl"
    base_spec = m7_env.base_spec if spec is None else spec
    core = VaultServer(SYN_CFG, m7_env.vault, rung, base_spec, trial_path=trial_path, server_log=server_log)
    return core, trial_path, server_log


INVALID = {"name": "unknown op", "expr": {"op": "cs_z", "x": {"op": "rank_all", "x": {"input": "close"}}}}


def test_a_non_final_invalid_spec_writes_no_trial_row_and_returns_the_error(m7_env, tmp_path):
    core, trial_path, server_log = _server(m7_env, tmp_path)
    with pytest.raises(dsl.DSLError) as raised:
        dsl.parse(INVALID)
    result = core.run_walkforward(INVALID, candidate=1, cost_usd=0.01, final=False)
    assert result["stage"] == "invalid_spec" and result["passed"] is False
    assert result["reason"] == str(raised.value)
    assert read_trials(trial_path) == []
    last = log_lines(server_log)[-1]
    assert last["result"] == "refused" and str(raised.value) in last.get("reason", "")


def test_a_final_invalid_spec_is_one_row_hashed_with_the_rung(m7_env, tmp_path):
    core, trial_path, _ = _server(m7_env, tmp_path)
    result = core.run_walkforward(INVALID, candidate=2, cost_usd=0.02, final=True, attempts=2)
    assert result["stage"] == "invalid_spec"
    rows = read_trials(trial_path)
    assert len(rows) == 1
    row = rows[0]
    invalid = {"invalid_dsl": INVALID, "rung": "M7"}
    assert json.loads(row["params_json"]) == invalid
    assert row["spec_hash"] == spec_hash(invalid, SYN_CFG) == result["spec_hash"]
    assert (row["kind"], row["author"], row["rung"]) == ("agent", "agent lab", "M7")
    notes = json.loads(row["notes"])
    assert notes["stage"] == "invalid_spec" and notes["attempts"] == 2
    assert not VENDOR.search(row["params_json"] + row["notes"])
    core.run_walkforward(INVALID, candidate=2, cost_usd=0.02, final=True, attempts=2)
    assert len(read_trials(trial_path)) == 1  # one row per configuration


def test_run_walkforward_defaults_are_final_with_one_attempt(m7_env, tmp_path):
    core, trial_path, _ = _server(m7_env, tmp_path)
    core.run_walkforward(INVALID)
    rows = read_trials(trial_path)
    assert len(rows) == 1
    assert json.loads(rows[0]["notes"]).get("attempts", 1) == 1


def test_round1_invalid_rows_keep_their_hash(m7_env, tmp_path):
    """S43-3 (d): a round-1 server (base M1) still hashes an invalid proposal as {"invalid_dsl": X}."""
    m1_spec = m7_env.w05.model_spec("M1", SYN_CFG)
    core, trial_path, _ = _server(m7_env, tmp_path, rung="M1", spec=m1_spec)
    core.run_walkforward(INVALID)
    rows = read_trials(trial_path)
    assert len(rows) == 1
    assert json.loads(rows[0]["params_json"]) == {"invalid_dsl": INVALID}
    assert rows[0]["spec_hash"] == spec_hash({"invalid_dsl": INVALID}, SYN_CFG)
    assert rows[0]["rung"] == "M1"
    assert canonical(m7_env.core.candidate_spec(VOL_RATIO)) != canonical(core.candidate_spec(VOL_RATIO))
    assert core.candidate_spec(VOL_RATIO) == {"rung": "M1", "tuning": models.tuning_spec(SYN_CFG),
                                              "agent_features": [VOL_RATIO], "author": "agent lab", "kind": "agent",
                                              "notes": "agent lab candidate"}


def test_the_server_still_refuses_m0_as_base_rung(m7_env, tmp_path):
    rung, spec = "M0", m7_env.w05.model_spec("M0", SYN_CFG)
    with pytest.raises(ValueError):
        _server(m7_env, tmp_path, rung=rung, spec=spec)


def test_the_committed_trial_log_names_no_vendor():
    text = (ROOT / "docs" / "trial_log.csv").read_text(encoding="utf-8")
    assert not VENDOR.search(text)
