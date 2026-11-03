"""07_evaluate.py: In-Sample only; one table of every backtested model, the benchmarks, the shift check, the placebo and
the plots, built from the outputs of 06_backtest.py on the synthetic market laid out as real data (decisions S32-1 to
S32-6)."""

import copy
import importlib.util

import numpy as np
import pandas as pd
import pytest

from src.config import ROOT, load_config, save_used
from src.data import write_csv
from src.features import features_settings, sizing_betas
from src.models import walkforward_settings

IS_END = pd.Timestamp("2019-12-27")


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("evaluate_script", ROOT / "07_evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def layout(script, synthetic_market, tmp_path, monkeypatch):
    """Raw files cut at the In-Sample end, M0 rule scores 2013–2019 (and a copy as M0_L13), features_config.yaml and
    sizing betas under tmp_path; 06 --all, --shift-check M0 and a 5-book placebo already run."""
    cfg = copy.deepcopy(load_config())
    cfg["placebo"] = {"books": 5, "seed_offset": 0}
    market = synthetic_market
    yahoo, fred = tmp_path / "data" / "raw" / "yahoo", tmp_path / "data" / "raw" / "fred"
    yahoo.mkdir(parents=True)
    fred.mkdir(parents=True)
    for ticker, frame in market.raw.items():
        frame.loc[frame.index <= IS_END].rename_axis("Date").to_csv(yahoo / f"{ticker}.csv")
    dgs3mo = market.fred[["DGS3MO"]]
    dgs3mo.loc[dgs3mo.index <= IS_END].rename_axis("Date").to_csv(fred / "DGS3MO.csv")
    sectors = list(cfg["data"]["tickers"])
    log_close = np.log(market.weekly_close[sectors])
    scores = (log_close.shift(1) - log_close.shift(26)).astype(np.float64)
    closes = pd.DatetimeIndex(scores.index.get_level_values("date_close"))
    scores = scores.loc[(closes >= pd.Timestamp("2013-01-04")) & (closes <= pd.Timestamp("2019-12-13"))]
    for name in ("M0", "M0_L13"):
        folder = tmp_path / "outputs" / "walkforward" / name
        write_csv(scores, folder / "scores.csv")
        save_used(walkforward_settings(cfg), folder / "used.yaml")
    processed = tmp_path / "data" / "processed"
    save_used(features_settings(cfg), processed / "features_config.yaml")
    write_csv(sizing_betas(market.daily_close.loc[market.daily_close.index <= IS_END], cfg), processed / "sizing_betas.csv")
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script.bt, "ROOT", tmp_path)
    script.bt.run_all(cfg)
    script.bt.shift_check(cfg, "M0")
    script.bt.run_placebo(cfg, "M0")
    return {"cfg": cfg, "root": tmp_path}


def test_evaluate_writes_one_row_per_model_and_every_plot(script, layout):
    table = script.evaluate(layout["cfg"])
    root = layout["root"]
    assert list(table.index) == ["M0", "M0_L13"]
    summary = script._read_json(root / "outputs" / "backtests" / "M0" / "summary.json")
    row = table.loc["M0"]
    assert row["net_sharpe_rf_tbill"] == pytest.approx(summary["net_sharpe_rf_tbill"], rel=1e-12)
    assert row["net_sharpe_rf_constant"] == pytest.approx(summary["net_sharpe_rf_constant"], rel=1e-12)
    assert row["net_sharpe_zero_cost"] == pytest.approx(summary["net_sharpe_zero_cost"], rel=1e-12)
    assert row["max_drawdown"] == pytest.approx(summary["max_drawdown"], rel=1e-12)
    assert row["gross_return_annual"] - row["costs_annual"] - row["borrow_annual"] == pytest.approx(
        script.read_weekly(root / "outputs" / "backtests" / "M0" / "weekly.csv")["net"].mean() * 52, abs=1e-12)
    assert np.isnan(row["rank_ic_mean"])  # src.stats.rank_ic is a Phase 3.1 stub
    books = pd.read_csv(root / "outputs" / "diagnostics" / "placebo" / "books.csv", index_col=0)
    assert row["placebo_percentile"] == script.bt.placebo_percentile(books["net_sharpe_rf_tbill"], row["net_sharpe_rf_tbill"])
    assert {"net_sharpe_rf_tbill_5bps_1pct", "net_sharpe_rf_tbill_20bps_5pct"} <= set(table.columns)

    metrics = root / "outputs" / "metrics"
    assert sorted(p.name for p in metrics.iterdir()) == ["is_benchmarks.csv", "is_models.csv", "placebo.csv",
                                                          "shift_check.csv", "used.yaml"]
    benchmarks = pd.read_csv(metrics / "is_benchmarks.csv", index_col=0)
    assert list(benchmarks.index) == ["T-bill", "SPY", "Equal weight"]
    shift = pd.read_csv(metrics / "shift_check.csv", index_col=0)
    assert shift.loc["M0", "verdict"] in {"PASS", "PENDING"}
    plots = root / "outputs" / "plots"
    for model in ("M0", "M0_L13"):
        for chart in ("equity", "drawdown", "exposure", "bridge"):
            assert (plots / f"{model}_{chart}.png").exists() and (plots / f"{model}_{chart}.html").exists()
    assert (plots / "all_models_equity.png").exists() and (plots / "placebo_sharpe.png").exists()


def test_benchmark_returns_are_tbill_spy_and_the_equal_weight_basket(script):
    mondays = pd.date_range("2015-01-05", periods=2, freq="7D")
    index = pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])
    sectors = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
    fwd = pd.DataFrame(0.0, index=index, columns=sectors + ["IVV", "SPY"])
    fwd["XLB"] = [0.09, 0.0]
    fwd["SPY"] = [0.02, -0.01]
    weekly = pd.DataFrame({"rf": [0.0003, 0.0004]}, index=index)
    out = script.benchmark_returns(weekly, fwd)
    assert out["Equal weight"].tolist() == pytest.approx([0.01, 0.0])
    assert out["SPY"].tolist() == [0.02, -0.01] and out["T-bill"].tolist() == [0.0003, 0.0004]


def test_rank_ic_goes_through_the_stats_hook(script, layout, monkeypatch):
    monkeypatch.setattr(script.bt, "stats_hook", lambda name, *a, **k: {"mean": 0.031} if name == "rank_ic" else None)
    table = script.evaluate(layout["cfg"])
    assert table["rank_ic_mean"].tolist() == [0.031, 0.031]


def test_evaluate_refuses_a_week_that_is_not_in_sample(script, layout):
    path = layout["root"] / "outputs" / "backtests" / "M0" / "weekly.csv"
    weekly = script.read_weekly(path)
    weekly.iloc[-1, weekly.columns.get_loc("period")] = "OOS"
    write_csv(weekly, path)
    with pytest.raises(SystemExit, match="not In-Sample"):
        script.evaluate(layout["cfg"])
    assert not (layout["root"] / "outputs" / "metrics").exists()


def test_evaluate_refuses_a_return_realised_after_the_in_sample_end(script, layout):
    path = layout["root"] / "outputs" / "backtests" / "M0_L13" / "weekly.csv"
    weekly = script.read_weekly(path)
    weekly.iloc[-1, weekly.columns.get_loc("realised_on")] = pd.Timestamp("2019-12-30")
    write_csv(weekly, path)
    with pytest.raises(SystemExit, match="not In-Sample"):
        script.evaluate(layout["cfg"])


def test_evaluate_refuses_a_backtest_built_with_another_config(script, layout):
    other = copy.deepcopy(layout["cfg"])
    other["costs"]["bps_baseline"] = 5
    with pytest.raises(ValueError, match="different config.yaml"):
        script.evaluate(other)


def test_evaluate_refuses_a_placebo_built_with_another_config(script, layout):
    other = copy.deepcopy(layout["cfg"])
    other["placebo"]["books"] = 6
    with pytest.raises(ValueError, match="different config.yaml"):
        script.evaluate(other)


def test_evaluate_needs_a_backtest(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="no outputs/backtests"):
        script.evaluate(load_config())
