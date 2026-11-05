"""Vault and model pipeline for agent features (decisions S33-2 to S33-4, Amendment 7 C2): the sealed daily closes and
weekly T-bill, the agent_features spec key, the design columns of an agent feature and its in-fold state product.

Built from the shared synthetic market (sessions 2011-01-03 to 2020-12-31) with a copy of config.yaml whose split fits
it; the in-memory frames hold daily closes and DGS3MO past the In-Sample end, so the cut at the end is tested. No real
data, no network; temporary lock, logs and trial log.
"""

import copy
import csv
import json

import numpy as np
import pandas as pd
import pytest

from src import backtest, features, labels, models
from src.agents import dsl
from src.config import load_config
from src.metrics import tbill_weekly_returns
from src.vault import OOSAccessError, Vault

CFG = load_config()
IS_END = pd.Timestamp(CFG["split"]["in_sample_end"])


def agent_cfg() -> dict:
    cfg = copy.deepcopy(CFG)
    cfg["split"]["warmup_end"] = "2012-12-31"
    cfg["split"]["initial_train_years"] = [2013, 2014]
    cfg["split"]["test_years"] = [2015, 2019]
    cfg["tuning"]["inner_validation_weeks"] = 52
    return cfg


ACFG = agent_cfg()
LOG_RETURN = {"op": "diff", "n": 1, "x": {"op": "log", "x": {"input": "close"}}}
VOL_RATIO = {"name": "vol ratio", "expr": {"op": "cs_z", "x": {
    "op": "ratio", "a": {"op": "rolling", "stat": "std", "n": 4, "x": LOG_RETURN},
    "b": {"op": "rolling", "stat": "std", "n": 26, "x": LOG_RETURN}}}}
VOL_RATIO_X_STATES = {"name": "vol ratio in bear markets", "expr": {"op": "mul_state", "state": ["BEAR24", "VIX"],
                                                                     "x": VOL_RATIO["expr"]}}
_FRAMES: dict = {}


def frames(market) -> dict:
    """In-memory vault tables from the synthetic market: the built tables up to the IS end, daily_close and dgs3mo whole."""
    if not _FRAMES:
        keep = market.daily_close.index <= IS_END
        close, opens = market.daily_close.loc[keep], market.daily_open.loc[keep]
        weekly_open, _ = __import__("src.data", fromlist=["weekly_panel"]).weekly_panel(opens, close)
        fwd, realised_on, period = backtest.forward_returns(weekly_open, IS_END)
        table = fwd.copy()
        table["realised_on"], table["period"] = realised_on, period
        dgs3mo = market.fred[["DGS3MO"]].copy()
        dgs3mo.index = pd.DatetimeIndex(dgs3mo.index, name="date")
        _FRAMES.update({
            "features": features.asset_features(close, ACFG),
            "market_states": features.market_states(close, market.vix[market.vix.index <= IS_END],
                                                    market.fred[market.fred.index <= IS_END], ACFG),
            "labels": labels.make_labels(fwd, pd.DatetimeIndex(close.index)),
            "momentum_variants": features.momentum_variants(close, cfg=ACFG),
            "sizing_betas": features.sizing_betas(close, ACFG),
            "forward_returns": table,
            "daily_close": market.daily_close.copy(),  # runs to 2020-12-31: the vault must cut it
            "dgs3mo": dgs3mo,
        })
    return {name: frame.copy() for name, frame in _FRAMES.items()}


@pytest.fixture
def env(synthetic_market, tmp_path):
    paths = {"lock": tmp_path / "FROZEN.lock", "log": tmp_path / "log.jsonl", "trials": tmp_path / "trial_log.csv"}
    vault = Vault(IS_END, lock_path=paths["lock"], log_path=paths["log"], frames=frames(synthetic_market), cfg=ACFG)
    return vault, paths


def last_log(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()][-1]


def trial_rows(path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- daily closes and the weekly T-bill


def test_daily_closes_are_cut_at_the_in_sample_end_and_logged(env, synthetic_market):
    vault, paths = env
    got = vault.daily_closes(IS_END)
    assert got.index.max() <= IS_END
    assert list(got.columns) == list(CFG["data"]["tickers"]) + ["SPY"]
    expected = synthetic_market.daily_close.loc[synthetic_market.daily_close.index <= IS_END, got.columns]
    pd.testing.assert_frame_equal(got, expected, check_freq=False, check_names=False)
    assert (last_log(paths["log"])["method"], last_log(paths["log"])["result"]) == ("daily_closes", "ok")
    early = vault.daily_closes(pd.Timestamp("2015-06-10"))
    assert early.index.max() <= pd.Timestamp("2015-06-10")


@pytest.mark.parametrize("method", ["daily_closes", "tbill_weekly"])
@pytest.mark.parametrize("day", ["2019-12-30", "2020-06-30"])
def test_oos_dates_of_the_new_tables_are_refused_and_logged(env, method, day):
    vault, paths = env
    with pytest.raises(OOSAccessError):
        getattr(vault, method)(pd.Timestamp(day))
    assert (last_log(paths["log"])["method"], last_log(paths["log"])["result"]) == (method, "refused")


def test_tbill_weekly_is_mattias_function_on_the_realised_weeks(env, synthetic_market):
    vault, _ = env
    rf = vault.tbill_weekly(IS_END)
    table = _FRAMES["forward_returns"]
    realised = table.index[table["realised_on"].notna().to_numpy()]
    sessions = pd.DatetimeIndex(synthetic_market.daily_close.index[synthetic_market.daily_close.index <= IS_END])
    fred = synthetic_market.fred["DGS3MO"]
    expected = tbill_weekly_returns(fred[fred.index <= IS_END], realised, sessions)
    pd.testing.assert_series_equal(rf, expected)
    assert rf.index.equals(realised)


# ---------------------------------------------------------------- the DSL against the built features


def test_the_dsl_reproduces_mom26_1(env):
    """cs_z(log(close(t - 1w) / close(t - 26w))) is the z-scored MOM26_1 of §06 (same weekly sampling, S22-3)."""
    vault, _ = env
    spec = {"name": "mom", "expr": {"op": "cs_z", "x": {"op": "log", "x": {
        "op": "ratio", "a": {"op": "lag", "n": 1, "x": {"input": "close"}}, "b": {"op": "lag", "n": 26, "x": {"input": "close"}}}}}}
    got = dsl.evaluate(spec, vault.daily_closes(IS_END), ACFG)
    expected = _FRAMES["features"]["MOM26_1"]
    assert got.index.equals(expected.index)
    np.testing.assert_allclose(got.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)


# ---------------------------------------------------------------- the agent_features spec key


@pytest.mark.parametrize("spec", [
    {"rung": "M0", "agent_features": [VOL_RATIO]},
    {"rung": "M0_star", "tuning": "T", "agent_features": [VOL_RATIO]},
    {"rung": "ENS", "members": ["M1", "M2", "M3"], "tuning": "T", "agent_features": [VOL_RATIO]},
    {"rung": "M1", "params": {"alpha": 10}, "agent_features": []},
    {"rung": "M1", "params": {"alpha": 10}, "agent_features": [{"name": "x", "expr": {"input": "close"}}]},
    {"rung": "M1", "params": {"alpha": 10}, "agent_features": VOL_RATIO},
])
def test_invalid_agent_specs_are_refused_logged_and_add_no_trial(env, spec):
    vault, paths = env
    spec = {key: (models.tuning_spec(ACFG) if value == "T" else value) for key, value in spec.items()}
    with pytest.raises(ValueError):
        vault.run_walkforward(spec, trial_path=paths["trials"])
    assert last_log(paths["log"])["result"] == "refused"
    assert trial_rows(paths["trials"]) == []


def test_agent_run_adds_one_row_with_the_evaluators_notes_and_a_rerun_adds_none(env):
    vault, paths = env
    spec = {"rung": "M1", "params": {"alpha": 10}, "agent_features": [VOL_RATIO], "kind": "agent",
            "author": "agent lab", "notes": "agent lab candidate"}
    scores = vault.run_walkforward(spec, lambda s: (0.5, -0.1, '{"candidate":1}'), trial_path=paths["trials"])
    rows = trial_rows(paths["trials"])
    assert len(rows) == 1 and rows[0]["notes"] == '{"candidate":1}' and rows[0]["kind"] == "agent"
    assert (rows[0]["is_sharpe"], rows[0]["is_mdd"]) == ("0.5", "-0.1")
    again = vault.run_walkforward(spec, trial_path=paths["trials"])
    pd.testing.assert_frame_equal(scores, again)
    assert len(trial_rows(paths["trials"])) == 1
    base = vault.run_walkforward({"rung": "M1", "params": {"alpha": 10}}, trial_path=paths["trials"])
    assert len(trial_rows(paths["trials"])) == 2
    assert not np.allclose(base.to_numpy(), scores.to_numpy(), equal_nan=True)  # the feature changes the scores


def test_agent_run_equals_a_manual_walk_forward_with_the_agent_column(env):
    """The vault's agent run is walkforward_rung on LadderData with AG1 = the DSL asset part (S33-4)."""
    vault, paths = env
    spec = {"rung": "M2", "params": {"alpha": 1}, "agent_features": [VOL_RATIO_X_STATES]}
    got = vault.run_walkforward(spec, trial_path=paths["trials"])
    feats = _FRAMES["features"].copy()
    feats["AG1"] = dsl.evaluate(VOL_RATIO_X_STATES, vault.daily_closes(IS_END), ACFG).reindex(feats.index).to_numpy()
    data = models.LadderData(features=feats, states=_FRAMES["market_states"], labels=_FRAMES["labels"],
                             agent_columns=(("AG1", ("BEAR24", "VIX")),))
    weeks = data.states.index
    folds = labels.walk_forward_folds(weeks, labels.label_end_by_week(data.labels, weeks), ACFG)
    expected, _ = models.walkforward_rung("M2", data, folds, ACFG, value=1)
    pd.testing.assert_frame_equal(got, expected)


# ---------------------------------------------------------------- the design columns (Amendment 7 C2)


def test_agent_design_columns_names():
    assert models.agent_design_columns([("AG1", ()), ("AG2", ("BEAR24", "VIX")), ("AG3", ("MKT_VAR",))]) == [
        "AG1", "AG2", "AG3", "AG2_x_BEAR24_x_VIX_Z", "AG3_x_MKT_VAR"]


@pytest.mark.parametrize("interactions", [False, True])
def test_agent_product_uses_the_in_fold_scaled_states(env, interactions):
    """AG1_x_BEAR24_x_VIX_Z = AG1 × raw BEAR24 × VIX standardised on the training weeks only (Amendment 2 C1, C7;
    Amendment 4 C1), for M1 (no pre-registered interactions) and M2 alike; test rows reuse the training scaling."""
    vault, _ = env
    feats = _FRAMES["features"].copy()
    feats["AG1"] = dsl.evaluate(VOL_RATIO, vault.daily_closes(IS_END), ACFG).reindex(feats.index).to_numpy()
    states = _FRAMES["market_states"]
    closes = feats.index.get_level_values("date_close")
    train = feats.loc[(closes >= "2013-01-04") & (closes <= "2016-12-30")].dropna()
    test = feats.loc[(closes >= "2017-01-06") & (closes <= "2017-12-29")]
    pairs = (("AG1", ("BEAR24", "VIX")),)
    X, params = models.fit_transform_train(train, states, interactions, ACFG, agent_columns=pairs)
    n_inter = len(CFG["features"]["interactions"]) if interactions else 0
    assert list(X.columns) == list(CFG["features"]["asset"]) + ["AG1"] + list(X.columns[7:7 + n_inter]) + [
        "AG1_x_BEAR24_x_VIX_Z"]
    by_close = states.set_axis(pd.DatetimeIndex(states.index.get_level_values("date_close")))
    train_weeks = pd.DatetimeIndex(train.index.get_level_values("date_close")).unique()
    vix = by_close.loc[train_weeks, "VIX"].to_numpy()
    lo, hi = np.nanquantile(vix, CFG["features"]["winsor_quantiles"])
    clipped = np.clip(vix, lo, hi)
    mean, std = clipped.mean(), clipped.std(ddof=1)

    def expected(rows):
        week = pd.DatetimeIndex(rows.index.get_level_values("date_close"))
        z = (np.clip(by_close.loc[week, "VIX"].to_numpy(), lo, hi) - mean) / std
        return rows["AG1"].to_numpy() * by_close.loc[week, "BEAR24"].to_numpy() * z

    np.testing.assert_allclose(X["AG1_x_BEAR24_x_VIX_Z"].to_numpy(), expected(train), rtol=1e-12, atol=1e-14)
    np.testing.assert_array_equal(X["AG1"].to_numpy(), train["AG1"].to_numpy())
    X_test = models.transform_test(test, states, params)
    np.testing.assert_allclose(X_test["AG1_x_BEAR24_x_VIX_Z"].to_numpy(), expected(test), rtol=1e-12, atol=1e-14,
                               equal_nan=True)


def test_m0_refuses_agent_columns(env):
    feats = _FRAMES["features"].copy()
    feats["AG1"] = 0.0
    data = models.LadderData(features=feats, states=_FRAMES["market_states"], labels=_FRAMES["labels"],
                             agent_columns=(("AG1", ()),))
    weeks = data.states.index
    folds = labels.walk_forward_folds(weeks, labels.label_end_by_week(data.labels, weeks), ACFG)
    with pytest.raises(ValueError, match="no agent features"):
        models.walkforward_rung("M0", data, folds[:1], ACFG)


# ---------------------------------------------------------------- S33-11: fixes from the session audit


def test_one_configuration_has_one_spec_hash():
    from src.vault import spec_hash

    child = VOL_RATIO["expr"]
    forms = [{"name": "a", "expr": {"op": "mul_state", "state": ["VIX", "BEAR24"], "x": child}},
             {"name": "b", "expr": {"op": "mul_state", "state": ["BEAR24", "VIX"], "x": child}}]
    hashes = {spec_hash({"rung": "M1", "params": {"alpha": 10}, "agent_features": [f]}, ACFG) for f in forms}
    assert len(hashes) == 1
    single = [{"name": "a", "expr": {"op": "mul_state", "state": "VIX", "x": child}},
              {"name": "z", "expr": {"op": "mul_state", "state": ["VIX"], "x": child}}]
    assert len({spec_hash({"rung": "M1", "params": {"alpha": 10}, "agent_features": [f]}, ACFG) for f in single}) == 1
    other = spec_hash({"rung": "M1", "params": {"alpha": 10}, "agent_features": [VOL_RATIO]}, ACFG)
    assert other not in hashes


@pytest.mark.parametrize("agent", [
    [VOL_RATIO, {"name": "renamed", "expr": VOL_RATIO["expr"]}],
    [dsl.parse(VOL_RATIO)],
])
def test_duplicate_or_non_json_agent_features_are_refused(env, agent):
    vault, paths = env
    with pytest.raises(ValueError):
        vault.run_walkforward({"rung": "M1", "params": {"alpha": 10}, "agent_features": agent}, trial_path=paths["trials"])
    assert last_log(paths["log"])["result"] == "refused" and trial_rows(paths["trials"]) == []


def test_the_daily_table_is_cut_at_the_in_sample_end_on_reading(synthetic_market, tmp_path):
    """A row after is_end never enters the sealed vault, even one that would fail validation (±inf)."""
    tables = frames(synthetic_market)
    tables["daily_close"].loc[pd.Timestamp("2020-03-02")] = np.inf
    vault = Vault(IS_END, lock_path=tmp_path / "FROZEN.lock", log_path=tmp_path / "log.jsonl", frames=tables, cfg=ACFG)
    assert vault._frame("daily_close").index.max() <= IS_END
    assert np.isfinite(vault.daily_closes(IS_END).to_numpy(dtype=float)[-1]).all()


def test_unlock_clears_the_tables_cached_while_sealed(synthetic_market, tmp_path):
    lock = tmp_path / "FROZEN.lock"
    vault = Vault(IS_END, lock_path=lock, log_path=tmp_path / "log.jsonl", frames=frames(synthetic_market), cfg=ACFG)
    vault.daily_closes(IS_END)
    lock.write_text("test lock\n", encoding="utf-8")
    vault.unlock()
    assert vault.daily_closes(pd.Timestamp("2020-06-30")).index.max() > IS_END


def test_an_agent_value_missing_in_a_training_row_refuses_the_run(env, monkeypatch):
    vault, paths = env
    original = dsl.evaluate

    def holed(spec, closes, cfg=None):
        values = original(spec, closes, cfg)
        values.loc[(pd.Timestamp("2014-03-07"), slice(None))] = np.nan
        return values

    monkeypatch.setattr("src.vault.evaluate_feature", holed)
    with pytest.raises(ValueError, match="finite"):
        vault.run_walkforward({"rung": "M1", "params": {"alpha": 10}, "agent_features": [VOL_RATIO]},
                              trial_path=paths["trials"])
    assert last_log(paths["log"])["result"] == "refused" and trial_rows(paths["trials"]) == []


def test_an_agent_value_missing_in_a_test_row_gives_nan_scores_that_week(env, monkeypatch):
    vault, paths = env
    original = dsl.evaluate
    hole = pd.Timestamp("2019-11-08")  # a test week of the last refit (2019 Q4), never a training row

    def holed(spec, closes, cfg=None):
        values = original(spec, closes, cfg)
        values.loc[(hole, "XLK")] = np.nan
        return values

    monkeypatch.setattr("src.vault.evaluate_feature", holed)
    scores = vault.run_walkforward({"rung": "M1", "params": {"alpha": 10}, "agent_features": [VOL_RATIO]},
                                   trial_path=paths["trials"])
    week = scores.loc[pd.DatetimeIndex(scores.index.get_level_values("date_close")) == hole]
    assert np.isnan(week["XLK"].iloc[0]) and week.drop(columns="XLK").notna().all(axis=None)


def test_evaluate_must_return_two_or_three_values(env):
    vault, paths = env
    with pytest.raises(ValueError, match="evaluate must return"):
        vault.run_walkforward({"rung": "M1", "params": {"alpha": 10}}, lambda s: (1.0, -0.1, "n", "extra"),
                              trial_path=paths["trials"])
