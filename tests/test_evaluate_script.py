"""07_evaluate.py: In-Sample only; one table of every backtested model, the benchmarks, the shift check, the placebo and
the plots, built from the outputs of 06_backtest.py on the synthetic market laid out as real data (decisions S32-1 to
S32-6)."""

import contextlib
import copy
import csv
import importlib.util
import json

import numpy as np
import pandas as pd
import pytest

from src.config import ROOT, load_config, save_used
from src.data import write_csv
from src.features import features_settings, sizing_betas
from src.models import walkforward_settings
from src.vault import spec_hash

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
        digest = spec_hash(script.bt._walkforward_script().spec_for(name, cfg), cfg)  # summary.json of 05 (S32-10)
        (folder / "summary.json").write_text(json.dumps({"name": name, "spec_hash": digest}), encoding="utf-8")
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
    assert np.isfinite(row["rank_ic_mean"])  # src.stats.rank_ic (Phase 3.1)
    books = pd.read_csv(root / "outputs" / "diagnostics" / "placebo" / "books.csv", index_col=0)
    assert row["placebo_percentile"] == script.bt.placebo_percentile(books["net_sharpe_rf_tbill"], row["net_sharpe_rf_tbill"])
    assert {"net_sharpe_rf_tbill_5bps_1pct", "net_sharpe_rf_tbill_20bps_5pct"} <= set(table.columns)

    metrics = root / "outputs" / "metrics"
    assert sorted(p.name for p in metrics.iterdir()) == ["is_benchmarks.csv", "is_models.csv", "placebo.csv",
                                                          "shift_check.csv", "used.yaml"]
    benchmarks = pd.read_csv(metrics / "is_benchmarks.csv", index_col=0)
    assert list(benchmarks.index) == ["T-bill", "SPY", "Equal weight"]
    shift = pd.read_csv(metrics / "shift_check.csv", index_col=0)
    p = shift.loc["M0", "p_delayed_better"]  # src.stats.paired_block_bootstrap (Phase 3.1)
    assert isinstance(p, float) and 0.0 <= p <= 1.0
    assert shift.loc["M0", "verdict"] in {"PASS", "FAIL"}  # the bootstrap is available: never PENDING
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


# ---------------------------------------------------------------- round 1 and round 2 (Amendment 9, S42-2)

ROUND2_FOLDERS = ("M7", "M7_a0.1_h2", "M8_d2_h4", "M6_a10")


@pytest.mark.parametrize("name, expected", [
    ("M0", 1), ("M0_star", 1), ("M5", 1), ("ENS", 1), ("M1_a0.1", 1), ("M2_a10", 1), ("M3_d2", 1), ("M0_L13", 1),
    ("M6", 2), ("M9", 2), ("M6_a0.1", 2), ("M6_a10", 2), ("M7_a0.1_h2", 2), ("M7_a1_h4", 2), ("M8_d3_h2", 2),
    ("M10", None), ("M6_d2", None), ("M7_a0.1", None), ("M8_d2", None), ("M9_a1_h2", None), ("M7_a0..1_h2", None),
    ("agent_c01", None), ("synthetic", None)])
def test_model_round_follows_the_folder_names_of_both_rounds(script, name, expected):
    assert script.model_round(name) == expected


def test_the_round_2_rungs_of_the_name_patterns_are_round2_candidate_order(script):
    assert [n for n in ("M6", "M7", "M8", "M9") if script.model_round(n) == 2] == \
        load_config()["round2"]["candidate_order"]


@pytest.fixture
def with_round2(script, layout, monkeypatch):
    """The layout plus M0_star and four round-2 folders (copies of M0's scores), backtested by 06. 05 has no spec for a
    round-2 name before session 4.1, so its spec_for is stubbed for them; everything else is the real path."""
    cfg, root = layout["cfg"], layout["root"]
    s05 = script.bt._walkforward_script()
    real = s05.spec_for
    monkeypatch.setattr(s05, "spec_for", lambda name, c: {"rung": name, "round": 2, "synthetic": True}
                        if script.model_round(name) == 2 else real(name, c))
    source = root / "outputs" / "walkforward" / "M0"
    for name in ("M0_star",) + ROUND2_FOLDERS:
        folder = root / "outputs" / "walkforward" / name
        folder.mkdir(parents=True)
        for file in ("scores.csv", "used.yaml"):
            (folder / file).write_bytes((source / file).read_bytes())
        digest = spec_hash(s05.spec_for(name, cfg), cfg)
        (folder / "summary.json").write_text(json.dumps({"name": name, "spec_hash": digest}), encoding="utf-8")
        script.bt.run_model(cfg, name)
    return layout


def write_gate(root, gate) -> None:
    path = root / "outputs" / "metrics" / "selection_gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gate), encoding="utf-8")


def test_the_table_holds_round_1_then_round_2_with_round_1s_verdict_primary(script, with_round2):
    """Round 1 fails (M0* traded in round 1, the primary pre-registered result); M7 passes the round-2 gate."""
    cfg, root = with_round2["cfg"], with_round2["root"]
    helpers = _oos_helpers()
    round1 = [helpers.gate_row(c["name"], False) if c["status"] == "evaluated" else c for c in helpers.GATE["candidates"][:5]]
    gate = {"selected": "M7", "candidates": round1 + [{"name": "M6", "status": "absent"}, helpers.gate_row("M7", True),
                                                      helpers.gate_row("M8", False), {"name": "M9", "status": "absent"}]}
    write_gate(root, gate)
    table = script.evaluate(cfg)
    assert list(table.index) == ["M0", "M0_star", "M0_L13", "M7", "M6_a10", "M7_a0.1_h2", "M8_d2_h4"]
    assert table["round"].tolist() == [1, 1, 1, 2, 2, 2, 2]
    assert table["role"].tolist() == ["hurdle", "fallback", "fixed configuration", "candidate"] + 3 * ["fixed configuration"]
    assert table.loc["M0", "section"] == script.SECTIONS[1] and table.loc["M7", "section"] == script.SECTIONS[2]
    assert table.loc["M0_star", "verdict"] == script.PRIMARY
    assert table.loc["M7", "verdict"] == script.TRADED
    assert table.loc[["M0", "M0_L13", "M6_a10"], "verdict"].fillna("").tolist() == ["", "", ""]
    assert table.loc["M7", "gate_bootstrap_prob"] == 0.90 and bool(table.loc["M7", "gate_passes"]) is True
    assert table.loc["M7", "gate_status"] == "evaluated" and np.isnan(table.loc["M0", "gate_bootstrap_prob"])
    m7 = script._read_json(root / "outputs" / "backtests" / "M7" / "summary.json")
    assert table.loc["M7", "net_sharpe_rf_tbill"] == pytest.approx(m7["net_sharpe_rf_tbill"], rel=1e-12)
    on_disk = pd.read_csv(root / "outputs" / "metrics" / "is_models.csv", index_col="model")
    assert list(on_disk.index) == list(table.index) and on_disk["round"].tolist() == [1, 1, 1, 2, 2, 2, 2]
    text = script.sections_text(table, cfg)
    assert text.index(script.SECTIONS[1]) < text.index("M0_L13") < text.index(script.SECTIONS[2]) < text.index("M8_d2_h4")
    assert "= 0.8" in text and "= 0.9" in text
    assert f"M0_star: {script.PRIMARY}" in text and f"M7: {script.TRADED}" in text
    assert (root / "outputs" / "plots" / "M7_a0.1_h2_equity.png").exists()


def test_a_round_1_gate_file_labels_only_the_primary_result(script, with_round2):
    """The file of S37-9 (round 1 only): M0* is the primary pre-registered result; nothing is labelled traded yet."""
    helpers = _oos_helpers()
    round1 = [helpers.gate_row(c["name"], False) if c["status"] == "evaluated" else c for c in helpers.GATE["candidates"][:5]]
    write_gate(with_round2["root"], {"selected": "M0_star", "candidates": round1})
    table = script.evaluate(with_round2["cfg"])
    assert table.loc["M0_star", "verdict"] == script.PRIMARY
    assert (table["verdict"].fillna("") == script.TRADED).sum() == 0
    assert table.loc["M7", "gate_status"] != table.loc["M7", "gate_status"]  # NaN: M7 is not in a round-1 file


def test_without_a_gate_file_the_sections_say_so(script, layout):
    table = script.evaluate(layout["cfg"])
    assert table["round"].tolist() == [1, 1] and table["verdict"].fillna("").tolist() == ["", ""]
    text = script.sections_text(table, layout["cfg"])
    assert "(no output yet)" in text and "selection_gate.json not found" in text


def test_a_gate_file_that_breaks_the_rule_stops_the_evaluation(script, with_round2):
    helpers = _oos_helpers()
    lenient = helpers.gate_row("M7", True) | {"p_uplift_positive": 0.85}  # passes 0.80, not the round-2 0.90
    gate = {"selected": "M7", "candidates": [helpers.gate_row(c["name"], False) if c["status"] == "evaluated" else c
                                             for c in helpers.GATE["candidates"][:5]]
            + [{"name": "M6", "status": "absent"}, lenient, {"name": "M8", "status": "absent"},
               {"name": "M9", "status": "absent"}]}
    write_gate(with_round2["root"], gate)
    with pytest.raises(SystemExit, match="do not follow from its numbers"):
        script.evaluate(with_round2["cfg"])
    assert not (with_round2["root"] / "outputs" / "metrics" / "is_models.csv").exists()


def test_a_backtest_folder_of_neither_round_is_refused(script, layout):
    folder = layout["root"] / "outputs" / "backtests" / "M10"
    folder.mkdir()
    (folder / "summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="M10/ is not a model of round 1 or round 2"):
        script.evaluate(layout["cfg"])


# ---------------------------------------------------------------- --period OOS (decisions S34-8 to S34-11)
#
# A light synthetic project (M0 and M0* only; every candidate absent, M0* selected) is built, frozen and run once by
# 08_run_oos.py under a temporary folder, with the builder of tests/test_run_oos_script.py.

_OOS: dict = {}


def _oos_helpers():
    spec = importlib.util.spec_from_file_location("oos_project_helpers", ROOT / "tests" / "test_run_oos_script.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_agent_trials(helpers, root, cfg) -> dict:
    """Two synthetic agent rows appended to the trial log, one that reached the walk-forward (with its folder of S37-6:
    weekly.csv and summary.json, net returns derived from M0's) and one that stopped before it; then
    outputs/metrics/selection_bias.json written by 05's own selection_bias (S37-7), the reference of S38-2."""
    s05 = helpers.load("oos_evaluate_05", "05_train_walkforward.py")
    rows = s05.trial_rows(root)
    first = max(int(row["trial_id"]) for row in rows) + 1
    with open(root / "docs" / "trial_log.csv", "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        for offset, stage in enumerate(("walk_forward", "invalid_spec")):
            spec = {"rung": "M2", "agent_feature": f"synthetic_{offset + 1}"}
            writer.writerow([first + offset, "2026-11-05T00:00:00+00:00", "agent", "agent", "M2", spec_hash(spec, cfg),
                             json.dumps(spec, sort_keys=True, separators=(",", ":")), "", "",
                             json.dumps({"stage": stage, "candidate": offset + 1})])
    m0 = s05.read_weekly(root / "outputs" / "backtests" / "M0" / "weekly.csv")
    weekly = m0[["realised_on", "period", "net", "rf"]].copy()
    weekly["net"] = 0.6 * m0["net"] + 0.002 * np.sin(np.arange(len(m0)))
    folder = root / "outputs" / "agent_lab" / "walkforward" / "agent_c01"
    write_csv(weekly, folder / "weekly.csv")
    agent_hash = spec_hash({"rung": "M2", "agent_feature": "synthetic_1"}, cfg)
    (folder / "summary.json").write_text(json.dumps({"trial_id": first, "candidate": 1, "spec_hash": agent_hash}),
                                         encoding="utf-8")
    bias = s05.selection_bias(cfg, root, "M0_star")
    path = root / "outputs" / "metrics" / "selection_bias.json"
    path.write_text(json.dumps(bias, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    helpers.commit(root, "data: synthetic agent trials")
    return bias


@contextlib.contextmanager
def changed(path, edit):
    """Rewrite a file of the shared OOS layout with edit(text) for the duration of the block, then restore it."""
    original = path.read_bytes()
    path.write_text(edit(original.decode("utf-8")), encoding="utf-8")
    try:
        yield
    finally:
        path.write_bytes(original)


@pytest.fixture
def oos_layout(script, synthetic_market, tmp_path_factory, monkeypatch):
    if not _OOS:
        helpers = _oos_helpers()
        root = tmp_path_factory.mktemp("oos_evaluate") / "project"
        root.mkdir()
        order = load_config()["models"]["candidate_order"] + load_config()["round2"]["candidate_order"]  # S42-1
        gate = {"selected": "M0_star", "candidates": [{"name": name, "status": "absent"} for name in order]}
        cfg = helpers.build_project(root, synthetic_market, walkforwards=("M0", "M0_star"), gate_content=gate)
        bias = add_agent_trials(helpers, root, cfg)
        run_script = helpers.load("oos_evaluate_08", "08_run_oos.py")
        run_script.freeze(root)
        helpers.commit(root, "docs: lock")
        run_script.run_oos(root)
        _OOS.update(root=root, cfg=cfg, helpers=helpers, bias=bias)
    monkeypatch.setattr(script, "ROOT", _OOS["root"])
    monkeypatch.setattr(script.bt, "ROOT", _OOS["root"])
    return _OOS


def test_oos_evaluation_writes_every_table_and_plot(script, oos_layout):
    root, cfg = oos_layout["root"], oos_layout["cfg"]
    tables = script.evaluate_oos(cfg)
    metrics_dir = root / "outputs" / "metrics"
    for name in ("oos_models.csv", "oos_benchmarks.csv", "oos_bonus.csv", "oos_secondary.csv", "oos_inference.csv",
                 "oos_used.yaml"):
        assert (metrics_dir / name).exists(), name
    models = tables["models"].set_index(["model", "period"])
    assert set(models.index) == {(m, p) for m in ("M0", "M0_star") for p in ("IS", "OOS")}
    summary = json.loads((root / "outputs" / "oos" / "M0_star" / "summary.json").read_text(encoding="utf-8"))
    for period in ("IS", "OOS"):
        row = models.loc[("M0_star", period)]
        assert row["net_sharpe_rf_tbill"] == pytest.approx(summary["scenarios"]["10bps_2pct"][period]["net_sharpe_rf_tbill"],
                                                           rel=1e-12)
        assert np.isfinite(row["rank_ic_mean"]) and row["selected"]
        assert row["final_equity"] > 0
    assert not models.loc[("M0", "OOS"), "selected"]
    plots_dir = root / "outputs" / "plots"
    for model in ("M0", "M0_star"):
        for chart in ("equity", "drawdown", "exposure", "bridge"):
            assert (plots_dir / f"oos_{model}_{chart}.png").exists() and (plots_dir / f"oos_{model}_{chart}.html").exists()
    assert (plots_dir / "oos_all_models_equity.png").exists()
    benchmarks = tables["benchmarks"]
    assert set(benchmarks.index) == {(s, p) for s in ("T-bill", "SPY", "Equal weight") for p in ("IS", "OOS")}


def test_oos_bonus_tests_follow_s34_9(script, oos_layout):
    root, cfg = oos_layout["root"], oos_layout["cfg"]
    bonus = script.evaluate_oos(cfg)["bonus"]
    weekly = script.read_weekly(root / "outputs" / "oos" / "M0" / "weekly.csv")
    oos = weekly.loc[weekly["period"] == "OOS"]
    market = script.bt.read_market(pd.Timestamp(cfg["data"]["end"]), IS_END, root=root)[2]
    spy = market.loc[oos.index, "SPY"]
    r = oos["net"]
    row = bonus.loc["M0"]
    assert row["beta"] == pytest.approx(r.cov(spy) / spy.var(), rel=1e-10)
    assert row["correlation"] == pytest.approx(r.corr(spy), rel=1e-10)
    assert row["beta_lower"] < row["beta"] < row["beta_upper"]
    assert row["down_week_mean"] == pytest.approx(r[spy < 0].mean(), rel=1e-12)
    assert row["down_week_count"] == (spy < 0).sum()
    assert row["mean_weekly"] == pytest.approx(r.mean(), rel=1e-12)
    assert len(r) == 51 and np.isnan(row["rolling_52w_positive_share"])  # 51 synthetic OOS weeks: no 52-week window
    assert row["return_2020"] == pytest.approx((1 + r[oos["realised_on"].dt.year == 2020]).prod() - 1, rel=1e-12)
    assert row["return_2019"] == pytest.approx(r[oos["realised_on"].dt.year == 2019].add(1).prod() - 1, rel=1e-12)
    expected = all(bool(row[k]) for k in ("passes_beta", "passes_correlation", "passes_down_week", "passes_down_month",
                                          "passes_mean_weekly"))
    assert bool(row["all_pass"]) == expected
    assert not bonus.loc["M0", "claimed"]  # M0 is not the selected model: no claim, whatever it shows
    assert bool(bonus.loc["M0_star", "claimed"]) == bool(bonus.loc["M0_star", "all_pass"])


def test_oos_secondary_and_inference(script, oos_layout):
    root, cfg = oos_layout["root"], oos_layout["cfg"]
    tables = script.evaluate_oos(cfg)
    secondary = tables["secondary"].loc["M0_star"]
    assert 0.0 <= secondary["lw_p_value"] <= 1.0
    assert bool(secondary["meets"]) == bool(secondary["sharpe_rf_tbill"] > secondary["spy_sharpe_rf_tbill"]
                                            and secondary["max_drawdown"] > secondary["spy_max_drawdown"])
    inference = tables["inference"].loc["M0_star"]
    assert inference["n_trials"] == len(pd.read_csv(root / "docs" / "trial_log.csv"))
    for key in ("dsr_in_sample", "dsr_out_of_sample", "pbo"):
        assert 0.0 <= inference[key] <= 1.0


def test_oos_inference_uses_the_matrix_of_selection_bias(script, oos_layout):
    """S38-2: the columns of selection_bias.json (M0, M0_star and the agent candidate), and its In-Sample DSR and PBO."""
    bias = oos_layout["bias"]
    assert [c["name"] for c in bias["matrix"]["columns"]] == ["M0", "M0_star", "agent_c01"]
    assert len(bias["excluded"]) == 1 and bias["excluded"][0]["stage"] == "invalid_spec"
    inference = script.evaluate_oos(oos_layout["cfg"])["inference"].loc["M0_star"]
    assert inference["matrix_columns"] == 3 and inference["matrix_columns_agent"] == 1
    assert inference["matrix_weeks"] == bias["matrix"]["weeks"] and inference["n_trials"] == bias["dsr"]["n_trials"]
    assert inference["dsr_in_sample"] == pytest.approx(bias["dsr"]["value"], abs=1e-12, rel=0)
    assert inference["pbo"] == pytest.approx(bias["pbo"]["value"], abs=1e-12, rel=0)


def _bias_check(script, oos_layout):
    return script.in_sample_inference(oos_layout["cfg"], script.load_run_script(), "M0_star")


def test_oos_inference_needs_selection_bias(script, oos_layout):
    path = oos_layout["root"] / "outputs" / "metrics" / "selection_bias.json"
    original = path.read_bytes()
    path.unlink()
    try:
        with pytest.raises(SystemExit, match="selection_bias.json not found"):
            _bias_check(script, oos_layout)
    finally:
        path.write_bytes(original)
    assert _bias_check(script, oos_layout)[0]["matrix_columns"] == 3


def _edit_json(edit):
    def apply(text):
        content = json.loads(text)
        edit(content)
        return json.dumps(content)
    return apply


@pytest.mark.parametrize("case, expected", [
    ("pbo", "In-Sample PBO .* differs"),
    ("dsr", "In-Sample DSR .* differs"),
    ("selected", "written for M0, the run selected M0_star"),
    ("n_trials", "counts 99 trials"),
    ("drop_column", "do not cover each spec_hash"),
    ("source", "not a backtest or agent weekly.csv"),
])
def test_oos_inference_refuses_a_selection_bias_that_does_not_match(script, oos_layout, case, expected):
    edits = {
        "pbo": lambda c: c["pbo"].update(value=c["pbo"]["value"] + 1e-6),
        "dsr": lambda c: c["dsr"].update(value=c["dsr"]["value"] + 1e-6),
        "selected": lambda c: c.update(selected="M0"),
        "n_trials": lambda c: c["dsr"].update(n_trials=99),
        "drop_column": lambda c: c["matrix"].update(columns=c["matrix"]["columns"][:2]),
        "source": lambda c: c["matrix"]["columns"][2].update(source="outputs/oos/M0/weekly.csv"),
    }
    path = oos_layout["root"] / "outputs" / "metrics" / "selection_bias.json"
    with changed(path, _edit_json(edits[case])), pytest.raises(SystemExit, match=expected):
        _bias_check(script, oos_layout)


def test_oos_inference_refuses_a_stale_or_changed_column(script, oos_layout):
    folder = oos_layout["root"] / "outputs" / "agent_lab" / "walkforward" / "agent_c01"
    with changed(folder / "summary.json", _edit_json(lambda c: c.update(spec_hash="0" * 64))), \
            pytest.raises(SystemExit, match="does not hold the spec_hash of column agent_c01"):
        _bias_check(script, oos_layout)
    lines = (folder / "weekly.csv").read_text(encoding="utf-8").splitlines(keepends=True)
    header, rows = lines[0], lines[1:]
    with changed(folder / "weekly.csv", lambda _: header + "".join(rows[:-1])), \
            pytest.raises(SystemExit, match="complete common weeks"):
        _bias_check(script, oos_layout)
    net = header.strip().split(",").index("net")

    def bump(_):
        first = rows[0].rstrip("\n").split(",")
        first[net] = repr(float(first[net]) + 0.01)
        return header + ",".join(first) + "\n" + "".join(rows[1:])
    with changed(folder / "weekly.csv", bump), pytest.raises(SystemExit, match="differs from"):
        _bias_check(script, oos_layout)
    assert _bias_check(script, oos_layout)[0]["dsr_in_sample"] == pytest.approx(oos_layout["bias"]["dsr"]["value"],
                                                                               abs=1e-12, rel=0)


def test_oos_evaluation_refuses_before_the_run(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="needs FROZEN.lock"):
        script.evaluate_oos(load_config())
    (tmp_path / "FROZEN.lock").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="holds 0 entries"):
        script.evaluate_oos(load_config())
    log = tmp_path / "outputs" / "oos_access_log.json"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps([{"utc": "a", "lock_sha256": "x"}, {"utc": "b", "lock_sha256": "x"}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="holds 2 entries"):
        script.evaluate_oos(load_config())
    log.write_text(json.dumps([{"utc": "a", "lock_sha256": "not the lock"}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="not written for the current FROZEN.lock"):
        script.evaluate_oos(load_config())


def test_oos_evaluation_refuses_outputs_built_with_another_config(script, oos_layout):
    other = copy.deepcopy(oos_layout["cfg"])
    other["costs"]["bps_baseline"] = 5
    with pytest.raises(ValueError, match="different config.yaml"):
        script.evaluate_oos(other)


def test_down_market_mean_hand_case(script):
    mondays = pd.date_range("2020-01-06", periods=6, freq="7D")
    index = pd.MultiIndex.from_arrays([mondays, mondays + pd.Timedelta(days=4)], names=["date_open", "date_close"])
    r = pd.Series([0.01, 0.05, 0.01, -0.02, 0.01, 0.03], index=index)
    m = pd.Series([-0.01, 0.02, -0.03, 0.01, -0.02, 0.0], index=index)
    out = script.down_market_mean(r, m, n_resamples=200, block=2, seed=1, confidence=0.95)
    assert out["mean"] == pytest.approx(0.01) and out["n_down"] == 3
    assert out["lower"] == pytest.approx(0.01) and out["upper"] == pytest.approx(0.01)  # r is 0.01 in every down week
    none = script.down_market_mean(r, m.abs() + 0.001, n_resamples=10, block=2, seed=1, confidence=0.95)
    assert np.isnan(none["mean"]) and none["n_down"] == 0
