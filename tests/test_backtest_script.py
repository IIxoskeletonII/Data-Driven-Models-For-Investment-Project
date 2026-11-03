"""06_backtest.py: CLI wiring only; refuses to run without a mode, the ledger check accepts In-Sample years only, and the
--model backtest reads walk-forward scores and vault betas and never computes an Out-of-Sample return."""

import copy
import importlib.util
import json
import logging

import numpy as np
import pandas as pd
import pytest
import yaml

from src.config import ROOT, load_config, save_used
from src.data import write_csv
from src.features import features_settings
from src.models import walkforward_settings
from src.vault import OOSAccessError


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("backtest_script", ROOT / "06_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refuses_to_run_without_a_flag(script):
    with pytest.raises(SystemExit) as raised:
        script.main([])
    assert "--model" in str(raised.value) and "vault" in str(raised.value)


@pytest.mark.parametrize("year", [2019, 2020, 2024])
def test_ledger_check_refuses_years_reaching_the_oos(script, year):
    with pytest.raises(SystemExit) as raised:
        script.main(["--ledger-years", "2012", str(year)])
    assert "In-Sample" in str(raised.value)


def test_read_raw_cuts_at_the_in_sample_end(script, tmp_path, monkeypatch):
    days = pd.bdate_range("2019-12-20", "2020-01-10")
    frame = pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=pd.DatetimeIndex(days, name="Date"))
    (tmp_path / "data" / "raw" / "yahoo").mkdir(parents=True)
    frame.to_csv(tmp_path / "data" / "raw" / "yahoo" / "XLK.csv")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    raw = script.read_raw_in_sample(["XLK"], pd.Timestamp("2019-12-27"))
    assert raw["XLK"].index.max() == pd.Timestamp("2019-12-27")


def test_random_placebo_inputs_are_seeded(script):
    mondays = pd.date_range("2010-01-04", periods=5, freq="7D")
    index = pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])
    pd.testing.assert_frame_equal(script.random_scores(index, 1), script.random_scores(index, 1))
    betas = script.random_betas(index, 1)
    assert (betas["IVV"] == 1.0).all() and betas.drop(columns="IVV").stack().between(0.6, 1.4).all()


def test_oos_guard_refuses_a_return_realised_after_the_in_sample_end(script):
    is_end = pd.Timestamp("2019-12-27")
    script.refuse_oos_returns(pd.Series(pd.to_datetime(["2019-12-23", "2019-12-27", None])), is_end)  # passes
    with pytest.raises(SystemExit) as raised:
        script.refuse_oos_returns(pd.Series(pd.to_datetime(["2019-12-23", "2019-12-30"])), is_end)
    assert "2019-12-30" in str(raised.value)


def test_ledger_check_stops_before_any_oos_return_even_with_frozen_lock(script, synthetic_market, tmp_path, monkeypatch):
    # if the In-Sample cut of the raw files failed, the guard still stops the run before any return is computed;
    # an existing FROZEN.lock does not unlock this script (contract 15: only 08_run_oos.py)
    (tmp_path / "FROZEN.lock").write_text("signed")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "read_raw_in_sample", lambda tickers, is_end: {t: synthetic_market.raw[t] for t in tickers})
    monkeypatch.setattr(script, "run_ledger", lambda *args, **kwargs: pytest.fail("ledger ran on an OOS return"))
    with pytest.raises(SystemExit) as raised:
        script.main(["--ledger-years", "2012"])
    assert "after the In-Sample end" in str(raised.value)
    assert not (tmp_path / "outputs").exists()


def test_ledger_settings_come_from_config(script):
    cfg = load_config()
    settings = script.ledger_settings(cfg)
    assert settings == {"years": [2005, 2012, 2016, 2018], "books_per_year": 10, "tolerance": 1e-6, "tolerance_costs": 1e-10}
    assert settings["tolerance"] == 1e-6  # §09 pre-registered, never loosened (Amendment 3 C1 keeps it)


@pytest.mark.parametrize("change,message", [
    ({"years": [2012, 2020]}, "In-Sample"),
    ({"years": []}, "non-empty"),
    ({"books_per_year": 0}, "positive int"),
    ({"tolerance": 1e-5}, "(0, 1e-6]"),
    ({"tolerance_costs": 0.0}, "(0, 1e-6]"),
])
def test_ledger_settings_refuse_bad_values(script, change, message):
    cfg = copy.deepcopy(load_config())
    cfg["ledger"] |= change
    with pytest.raises(SystemExit) as raised:
        script.ledger_settings(cfg)
    assert message in str(raised.value)


def test_ledger_settings_require_the_section(script):
    cfg = copy.deepcopy(load_config())
    del cfg["ledger"]
    with pytest.raises(SystemExit, match="no ledger"):
        script.ledger_settings(cfg)


def test_ledger_years_default_to_config_and_can_be_overridden(script, monkeypatch):
    calls = []
    monkeypatch.setattr(script, "run_ledger_check", lambda cfg, years: calls.append(years))
    script.main(["--ledger-years"])
    script.main(["--ledger-years", "2012"])
    assert calls == [[], [2012]]


def test_ledger_check_uses_the_configured_books_and_tolerances(script, synthetic_market, tmp_path, monkeypatch, capsys):
    # synthetic raw data cut at the In-Sample end; 2 books per year and a tolerance of 1e-7 are read from the config
    is_end = pd.Timestamp("2019-12-27")
    cut = {t: frame.loc[frame.index <= is_end] for t, frame in synthetic_market.raw.items()}
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "read_raw_in_sample", lambda tickers, end: {t: cut[t] for t in tickers})
    cfg = copy.deepcopy(load_config())
    cfg["ledger"] |= {"books_per_year": 2, "tolerance": 1e-7}
    script.run_ledger_check(cfg, [2012])
    summary = pd.read_csv(tmp_path / "outputs" / "ledger" / "reconciliation.csv", index_col=0)
    assert summary.loc[2012, "books"] == 2
    out = capsys.readouterr().out
    assert "|ledger - engine| <= 1e-07: PASS" in out and "<= 1e-10: PASS" in out


# -- --model: In-Sample backtest of walk-forward scores (session 2.3b, decisions S23-4 to S23-10) -------------------------

IS_END = pd.Timestamp("2019-12-27")
FIRST_SCORED = pd.Timestamp("2013-01-04")
LAST_IS_SIGNAL_WEEK = pd.Timestamp("2019-12-13")  # contract 7: its return is realised at the open of 2019-12-23


def _m0_scores(market) -> pd.DataFrame:
    """Contract-8 scores of the M0 rule on the synthetic weekly closes, ln C(t−1) − ln C(t−26), weeks 2013 to the last
    In-Sample signal week."""
    sectors = list(load_config()["data"]["tickers"])
    log_close = np.log(market.weekly_close[sectors])
    scores = (log_close.shift(1) - log_close.shift(26)).astype(np.float64)
    closes = pd.DatetimeIndex(scores.index.get_level_values("date_close"))
    return scores.loc[(closes >= FIRST_SCORED) & (closes <= LAST_IS_SIGNAL_WEEK)]


@pytest.fixture
def model_inputs(script, synthetic_market, tmp_path, monkeypatch):
    """The real-data layout of --model M0 under tmp_path, built from the synthetic market: raw Yahoo and FRED files cut
    at the In-Sample end, walk-forward scores with used.yaml (src.models.walkforward_settings, as 05 saves it),
    features_config.yaml (src.features.features_settings, as 03 saves it) and data/processed/sizing_betas.csv, which the
    real src.vault.Vault serves (S23-4)."""
    from src.features import sizing_betas

    cfg = load_config()
    market = synthetic_market
    yahoo, fred = tmp_path / "data" / "raw" / "yahoo", tmp_path / "data" / "raw" / "fred"
    yahoo.mkdir(parents=True)
    fred.mkdir(parents=True)
    for ticker, frame in market.raw.items():
        frame.loc[frame.index <= IS_END].rename_axis("Date").to_csv(yahoo / f"{ticker}.csv")
    dgs3mo = market.fred[["DGS3MO"]]
    dgs3mo.loc[dgs3mo.index <= IS_END].rename_axis("Date").to_csv(fred / "DGS3MO.csv")

    scores = _m0_scores(market)
    folder = tmp_path / "outputs" / "walkforward" / "M0"
    write_csv(scores, folder / "scores.csv")
    save_used(walkforward_settings(cfg), folder / "used.yaml")
    processed = tmp_path / cfg["data"]["data_dir"] / "processed"
    save_used(features_settings(cfg), processed / "features_config.yaml")

    betas = sizing_betas(market.daily_close.loc[market.daily_close.index <= IS_END], cfg)
    write_csv(betas, processed / "sizing_betas.csv")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    return {"cfg": cfg, "scores": scores, "betas": betas, "log": tmp_path / "outputs" / "vault_access_log.jsonl",
            "out": tmp_path / "outputs" / "backtests" / "M0"}


def test_settings_checked_are_those_03_and_05_save(script):
    # S23-1, S23-5, S23-6: 06 checks the walk-forward used.yaml and features_config.yaml with the functions that write them
    assert script.walkforward_settings is walkforward_settings and script.features_settings is features_settings
    cfg = load_config()
    settings = script.walkforward_settings(cfg)
    assert sorted(settings) == sorted(["seed", "data", "split", "execution", "features", "models"])
    assert all(settings[key] == cfg[key] for key in settings)  # whole sections


def test_cost_scenarios_pair_costs_and_borrow_by_position(script):
    cfg = load_config()
    assert script.cost_scenarios(cfg) == [("5bps_1pct", 5.0, 0.01, False), ("10bps_2pct", 10.0, 0.02, True),
                                          ("20bps_5pct", 20.0, 0.05, False)]
    bad = copy.deepcopy(cfg)
    bad["costs"]["borrow"] = [0.01, 0.02]
    with pytest.raises(SystemExit, match="pair by position"):
        script.cost_scenarios(bad)


def test_model_backtest_writes_the_four_outputs(script, model_inputs):
    script.main(["--model", "M0"])
    out = model_inputs["out"]
    assert sorted(p.name for p in out.iterdir()) == ["metrics.csv", "summary.json", "used.yaml", "weekly.csv"]

    weekly = pd.read_csv(out / "weekly.csv", index_col=[0, 1], parse_dates=[0, 1, 2])
    closes = pd.DatetimeIndex(weekly.index.get_level_values("date_close"))
    assert closes[0] == FIRST_SCORED and closes[-1] == LAST_IS_SIGNAL_WEEK
    assert (weekly["period"] == "IS").all()
    assert pd.Timestamp(weekly["realised_on"].max()) <= IS_END
    assert weekly["turnover"].iloc[0] == pytest.approx(1.0)  # first week entered from cash
    np.testing.assert_allclose(weekly["costs"], 10 / 10_000 * weekly["turnover"], rtol=0, atol=1e-12)
    assert "SPY" not in weekly.columns  # the benchmark is never traded and no per-ticker series is written
    assert {"net_5bps_1pct", "net_20bps_5pct"} <= set(weekly.columns)
    assert weekly["net_5bps_1pct"].sum() > weekly["net"].sum() > weekly["net_20bps_5pct"].sum()

    metrics = pd.read_csv(out / "metrics.csv", index_col=[0, 1])
    assert len(metrics) == 6 and (metrics["period"] == "IS").all()
    assert set(metrics.index.get_level_values("rf")) == {"tbill", "constant"}
    assert metrics.loc[("10bps_2pct", "constant"), "rf_annual"] == pytest.approx(0.02)

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "M0" and summary["period"] == "IS" and summary["baseline"] == "10bps_2pct"
    assert summary["weeks"] == len(weekly)
    assert (summary["first_week"], summary["last_week"]) == ("2013-01-04", "2019-12-13")
    assert summary["last_realised_on"] == "2019-12-23"
    assert summary["cap_binding_weeks"] == int(weekly["cap_binds"].sum())
    assert summary["mean_abs_residual_beta"] == pytest.approx(weekly["residual_beta"].abs().mean(), abs=1e-12)
    assert summary["mean_turnover"] == pytest.approx(weekly["turnover"].mean(), abs=1e-12)
    assert summary["missing_input_weeks"] == 0
    assert set(summary["scenarios"]) == {"5bps_1pct", "10bps_2pct", "20bps_5pct"}

    # headline Sharpe recomputed from the weekly file: (annualised net return − compound annual T-bill) / volatility
    r, rf = weekly["net"], weekly["rf"]
    annual = (1 + r).prod() ** (52 / len(r)) - 1
    rf_annual = (1 + rf).prod() ** (52 / len(rf)) - 1
    vol = r.std() * np.sqrt(52)
    assert summary["net_sharpe_rf_tbill"] == pytest.approx((annual - rf_annual) / vol, rel=1e-9)
    assert summary["net_sharpe_rf_constant"] == pytest.approx((annual - 0.02) / vol, rel=1e-9)
    assert summary["net_sharpe_zero_cost"] == pytest.approx(annual / vol, rel=1e-9)
    assert summary["max_drawdown"] == pytest.approx(metrics.loc[("10bps_2pct", "tbill"), "max_drawdown"], abs=1e-12)
    assert summary["rf_tbill_annual"] == pytest.approx(rf_annual, rel=1e-9)

    used = yaml.safe_load((out / "used.yaml").read_text(encoding="utf-8"))
    assert used["model"] == "M0" and used["costs"] == model_inputs["cfg"]["costs"]


def test_model_backtest_asks_the_vault_only_for_in_sample_dates(script, model_inputs):
    script.main(["--model", "M0"])
    lines = [json.loads(line) for line in model_inputs["log"].read_text(encoding="utf-8").splitlines()]
    assert [(r["method"], r["as_of"], r["result"]) for r in lines] == [("sizing_betas", "2019-12-27", "ok")]


def test_model_backtest_vault_is_sealed_at_the_in_sample_end(script, model_inputs):
    vault = script.open_vault(model_inputs["cfg"])
    assert vault.is_end == IS_END
    with pytest.raises(OOSAccessError):
        vault.sizing_betas(pd.Timestamp("2020-01-03"))
    betas = script.read_betas(vault, IS_END)
    pd.testing.assert_frame_equal(betas, model_inputs["betas"], check_freq=False, atol=1e-12)


def test_model_backtest_refuses_a_features_build_with_another_config(script, model_inputs):
    other = copy.deepcopy(model_inputs["cfg"])
    other["execution"]["type"] = "close_to_close"
    processed = model_inputs["out"].parents[2] / other["data"]["data_dir"] / "processed"
    save_used(features_settings(other), processed / "features_config.yaml")
    with pytest.raises(ValueError, match="different config.yaml"):
        script.main(["--model", "M0"])
    assert not model_inputs["out"].exists()


def test_model_backtest_refuses_scores_built_with_another_config(script, model_inputs):
    folder = model_inputs["out"].parents[1] / "walkforward" / "M0"
    other = copy.deepcopy(model_inputs["cfg"])
    other["models"]["M0"]["feature"] = "MOM52_4"
    save_used(walkforward_settings(other), folder / "used.yaml")
    with pytest.raises(ValueError, match="different config.yaml"):
        script.main(["--model", "M0"])
    assert not model_inputs["out"].exists()


def test_model_backtest_refuses_scores_after_the_in_sample_end(script, model_inputs):
    folder = model_inputs["out"].parents[1] / "walkforward" / "M0"
    scores = model_inputs["scores"]
    late = scores.iloc[[-1]].copy()
    late.index = pd.MultiIndex.from_arrays([[pd.Timestamp("2019-12-30")], [pd.Timestamp("2020-01-03")]],
                                           names=["date_open", "date_close"])
    write_csv(pd.concat([scores, late]), folder / "scores.csv")
    with pytest.raises(SystemExit, match="after the In-Sample end"):
        script.main(["--model", "M0"])
    assert not model_inputs["out"].exists()


def test_model_backtest_stops_before_any_oos_return(script, model_inputs, synthetic_market, monkeypatch):
    # if the In-Sample cut of the raw files failed, refuse_oos_returns stops the run before the engine and writes nothing
    monkeypatch.setattr(script, "read_raw_in_sample", lambda tickers, is_end: {t: synthetic_market.raw[t] for t in tickers})
    monkeypatch.setattr(script, "run", lambda *args, **kwargs: pytest.fail("the engine ran on an OOS return"))
    with pytest.raises(SystemExit, match="after the In-Sample end"):
        script.main(["--model", "M0"])
    assert not model_inputs["out"].exists()


def test_model_backtest_counts_a_missing_score_week(script, model_inputs, caplog):
    folder = model_inputs["out"].parents[1] / "walkforward" / "M0"
    scores = model_inputs["scores"].copy()
    scores.iloc[100, 3] = np.nan  # one sector score missing: Amendment 2 C3 carries the previous targets
    write_csv(scores, folder / "scores.csv")
    with caplog.at_level(logging.WARNING, logger="src.sizing"):
        summary = script.backtest_model(model_inputs["cfg"], "M0")
    assert summary["missing_input_weeks"] == 1
    week = pd.Timestamp(scores.index[100][1]).strftime("%Y-%m-%d")
    assert any(week in record.getMessage() for record in caplog.records)


def test_model_backtest_refuses_a_model_without_walkforward_scores(script, model_inputs):
    # S32-1: --model accepts any folder of outputs/walkforward/ with a scores.csv, and nothing else
    with pytest.raises(SystemExit, match="no outputs/walkforward/M9/scores.csv"):
        script.main(["--model", "M9"])
    for name in ("../M0", "M0/..", "", "M-0"):
        with pytest.raises(SystemExit, match="not a model name"):
            script.check_model(name)
    assert not model_inputs["out"].exists()


def test_read_scores_round_trips_the_contract_8_file(script, model_inputs):
    read = script.read_scores("M0", model_inputs["cfg"], IS_END)
    pd.testing.assert_frame_equal(read, model_inputs["scores"], check_freq=False, check_index_type=False, atol=1e-12)


# -- session 3.2: every walk-forward folder, --all, exposures, shift check, placebo (decisions S32-1 to S32-4) -----------

def _copy_walkforward(model_inputs, name: str, scores: pd.DataFrame | None = None) -> None:
    folder = model_inputs["out"].parents[1] / "walkforward" / name
    write_csv(model_inputs["scores"] if scores is None else scores, folder / "scores.csv")
    save_used(walkforward_settings(model_inputs["cfg"]), folder / "used.yaml")


def test_walkforward_models_lists_folders_with_scores(script, model_inputs):
    _copy_walkforward(model_inputs, "M3_d2")
    _copy_walkforward(model_inputs, "M0_L13")
    (model_inputs["out"].parents[1] / "walkforward" / "empty").mkdir()  # no scores.csv: not a model
    assert script.walkforward_models() == ["M0", "M0_L13", "M3_d2"]


def test_a_fixed_variant_folder_is_backtested(script, model_inputs):
    _copy_walkforward(model_inputs, "M3_d2")
    script.main(["--model", "M3_d2"])
    folder = model_inputs["out"].parent / "M3_d2"
    assert json.loads((folder / "summary.json").read_text(encoding="utf-8"))["model"] == "M3_d2"
    assert yaml.safe_load((folder / "used.yaml").read_text(encoding="utf-8"))["model"] == "M3_d2"


def test_all_backtests_every_folder_with_one_vault_read(script, model_inputs):
    _copy_walkforward(model_inputs, "M0_L13")
    script.main(["--all"])
    out = model_inputs["out"].parent
    assert sorted(p.name for p in out.iterdir()) == ["M0", "M0_L13"]
    a = pd.read_csv(out / "M0" / "weekly.csv", index_col=[0, 1])
    b = pd.read_csv(out / "M0_L13" / "weekly.csv", index_col=[0, 1])
    pd.testing.assert_frame_equal(a, b)  # same scores, same book
    lines = model_inputs["log"].read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["method"] for line in lines] == ["sizing_betas"]


def test_all_refuses_when_there_is_no_model(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="--all: no outputs/walkforward"):
        script.main(["--all"])


def test_weekly_exposures_add_up(script, model_inputs):
    script.main(["--model", "M0"])
    weekly = pd.read_csv(model_inputs["out"] / "weekly.csv", index_col=[0, 1])
    # Σ|w| = 1, and Σw = the IVV weight h / (1 + |h|) because the core is dollar-neutral (§09)
    np.testing.assert_allclose(weekly["long_exposure"] - weekly["short_exposure"], 1.0, rtol=0, atol=1e-12)
    np.testing.assert_allclose(weekly["long_exposure"] + weekly["short_exposure"], weekly["net_exposure"], rtol=0,
                               atol=1e-12)


def _week_index(n: int, start: str = "2010-01-04") -> pd.MultiIndex:
    mondays = pd.date_range(start, periods=n, freq="7D")
    return pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])


def test_delayed_scores_hand_case(script):
    index = _week_index(6)
    scores = pd.DataFrame({"XLB": [1.0, 2, 3, 4], "XLE": [5.0, 6, 7, 8]}, index=index[[1, 2, 4, 5]])  # week 3 unscored
    delayed = script.delayed_scores(scores, index)
    assert list(delayed.index) == list(index[[2, 4, 5]])  # the first scored week has no delayed score
    assert delayed["XLB"].iloc[0] == 1.0  # week 2 trades the scores of week 1
    assert np.isnan(delayed["XLB"].iloc[1])  # week 4 would trade week 3's, which has none: a missing input (C3)
    assert delayed["XLE"].iloc[2] == 7.0
    with pytest.raises(ValueError, match="outside the weekly index"):
        script.delayed_scores(scores, index[:3])


@pytest.mark.parametrize("base,delayed,p,verdict", [
    (0.5, 0.4, None, "PASS"),
    (0.5, 0.5, None, "PASS"),
    (0.5, 0.6, None, "PENDING"),
    (0.5, 0.6, 0.79, "PASS"),
    (0.5, 0.6, 0.80, "FAIL"),
    (0.5, 0.4, 0.95, "PASS"),
])
def test_shift_verdict(script, base, delayed, p, verdict):
    assert script.shift_verdict(base, delayed, p, 0.80) == verdict


def test_shift_check_writes_both_books_on_common_weeks(script, model_inputs):
    script.main(["--shift-check"])  # default M0
    out = model_inputs["out"].parents[1] / "diagnostics" / "shift" / "M0"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    weekly = pd.read_csv(out / "weekly.csv", index_col=[0, 1], parse_dates=[0, 1, 2])
    assert summary["weeks"] == len(model_inputs["scores"]) - 1 == len(weekly)
    assert summary["first_week"] == pd.Timestamp(model_inputs["scores"].index[1][1]).strftime("%Y-%m-%d")
    assert pd.Timestamp(weekly["realised_on"].max()) <= IS_END
    r = weekly["net_delayed"]
    annual = (1 + r).prod() ** (52 / len(r)) - 1
    assert summary["delayed"]["net_sharpe_zero_cost"] == pytest.approx(annual / (r.std() * np.sqrt(52)), rel=1e-9)
    assert summary["p_delayed_better"] is None  # src.stats is still a Phase 3.1 stub: the hook returns None
    assert summary["verdict"] == script.shift_verdict(summary["base"]["net_sharpe_rf_tbill"],
                                                      summary["delayed"]["net_sharpe_rf_tbill"], None, 0.80)


def test_shift_check_flags_scores_that_are_one_week_early(script, model_inputs, synthetic_market, monkeypatch):
    # planted misalignment: the score of week t is the forward return of week t + 1, so the delayed book trades on the
    # return it earns and beats the base book; with a bootstrap P of 1 the check fails
    fwd, _, _ = script.forward_returns(synthetic_market.weekly_open, is_end=IS_END)
    sectors = list(model_inputs["scores"].columns)
    early = fwd[sectors].shift(-1).reindex(model_inputs["scores"].index).iloc[:-2]
    write_csv(early, model_inputs["out"].parents[1] / "walkforward" / "M0" / "scores.csv")
    real_hook = script.stats_hook

    def hook(name, *args, **kwargs):
        return {"p_uplift_positive": 1.0} if name == "paired_block_bootstrap" else real_hook(name, *args, **kwargs)

    monkeypatch.setattr(script, "stats_hook", hook)
    summary = script.shift_check(model_inputs["cfg"], "M0")
    assert summary["delayed"]["net_sharpe_rf_tbill"] > summary["base"]["net_sharpe_rf_tbill"]
    assert summary["verdict"] == "FAIL"


def test_shift_check_refuses_a_bootstrap_without_the_probability_key(script, model_inputs, monkeypatch):
    monkeypatch.setattr(script, "stats_hook", lambda name, *a, **k: {"p": 0.5} if name == "paired_block_bootstrap" else None)
    with pytest.raises(SystemExit, match="p_uplift_positive"):
        script.shift_check(model_inputs["cfg"], "M0")


def test_placebo_seeds_follow_the_config(script):
    cfg = load_config()
    assert cfg["placebo"] == {"books": 1000, "seed_offset": 1000000}  # §11: 1,000 books, pre-registered
    seeds = script.placebo_seeds(cfg)
    assert len(seeds) == 1000 and seeds[0] == 42 + 1_000_000 and seeds[-1] == 42 + 1_000_000 + 999


@pytest.mark.parametrize("change,message", [({"books": 0}, "books"), ({"books": 2.5}, "books"),
                                            ({"seed_offset": -1}, "seed_offset"), ({"books": True}, "books")])
def test_placebo_settings_refuse_bad_values(script, change, message):
    cfg = copy.deepcopy(load_config())
    cfg["placebo"] |= change
    with pytest.raises(SystemExit, match=message):
        script.placebo_settings(cfg)


def test_placebo_percentile_hand_case(script):
    values = pd.Series([0.1, 0.2, 0.3, 0.4])
    assert script.placebo_percentile(values, 0.25) == 50.0
    assert script.placebo_percentile(values, 0.3) == 62.5  # a tie counts half
    assert script.placebo_percentile(values, -1.0) == 0.0


def test_placebo_books_are_seeded_and_on_the_reference_weeks(script, model_inputs):
    cfg = copy.deepcopy(model_inputs["cfg"])
    cfg["placebo"] = {"books": 4, "seed_offset": 7}
    first = script.run_placebo(cfg, "M0")
    out = model_inputs["out"].parents[1] / "diagnostics" / "placebo"
    books = pd.read_csv(out / "books.csv", index_col=0)
    assert books["seed"].tolist() == [49, 50, 51, 52]
    assert first["weeks"] == len(model_inputs["scores"]) and first["books"] == 4
    assert first["reference_percentile"] == script.placebo_percentile(books["net_sharpe_rf_tbill"],
                                                                      first["reference_row"]["net_sharpe_rf_tbill"])
    assert books["mean_turnover"].min() > first["reference_row"]["mean_turnover"]  # random books trade more than M0
    assert first["reference_percentile_gross"] == script.placebo_percentile(
        books["gross_sharpe_zero_cost"], first["reference_row"]["gross_sharpe_zero_cost"])
    assert script.run_placebo(cfg, "M0") == first  # fixed seeds: the same distribution
    used = yaml.safe_load((out / "used.yaml").read_text(encoding="utf-8"))
    assert used["placebo"] == cfg["placebo"] and used["reference"] == "M0"


@pytest.mark.parametrize("argv", [["--shift-check", "M0"], ["--placebo"], ["--all"]])
def test_diagnostics_stop_before_any_oos_return(script, model_inputs, synthetic_market, monkeypatch, argv):
    monkeypatch.setattr(script, "read_raw_in_sample", lambda tickers, is_end: {t: synthetic_market.raw[t] for t in tickers})
    monkeypatch.setattr(script, "run", lambda *args, **kwargs: pytest.fail("the engine ran on an OOS return"))
    with pytest.raises(SystemExit, match="after the In-Sample end"):
        script.main(argv)
    outputs = model_inputs["out"].parents[1]
    assert not (outputs / "diagnostics").exists() and not (outputs / "backtests").exists()
