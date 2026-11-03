"""In-Sample evaluation of every backtested model (protocol section 11), Phase 3.2: one table of metrics, the benchmarks,
the §12 one-week-shift check, the §11 placebo, and the plots. In-Sample only: every input is checked to hold no week
realised after split.in_sample_end (operating manual rule 3); the selection gate of §07 is Phase 3.1 (src/stats.py).

Inputs:  outputs/backtests/<model>/        (06_backtest.py --model / --all; check_used of each used.yaml)
         outputs/diagnostics/shift/<model>/ (06_backtest.py --shift-check), outputs/diagnostics/placebo/ (--placebo)
         outputs/walkforward/<model>/scores.csv (rank IC) and the raw prices cut at the In-Sample end through
         06_backtest.py: in_sample_market (refuse_oos_returns), for SPY and the equal-weight basket
Outputs: outputs/metrics/  is_models.csv (one row per model), is_benchmarks.csv, shift_check.csv, placebo.csv, used.yaml
         outputs/plots/    <model>_{equity,drawdown,exposure,bridge}.{html,png}, all_models_equity, placebo_sharpe
"""

import argparse
import importlib.util
import json
import sys

import numpy as np
import pandas as pd

from src import plots
from src.config import ROOT, check_used, load_config, save_used
from src.contracts import universe
from src.data import write_csv
from src.metrics import performance, return_stats
from src.models import walkforward_settings

EQUAL_WEIGHT, TBILL = "Equal weight", "T-bill"
REFERENCE = "M0"  # the hurdle: benchmarks and the all-models chart use its weeks


def load_backtest_script():
    """06_backtest.py as a module (its file name is not importable), for its readers, guards and settings."""
    spec = importlib.util.spec_from_file_location("backtest_script", ROOT / "06_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bt = load_backtest_script()


def backtested_models() -> list[str]:
    """Folders of outputs/backtests/ written by 06_backtest.py --model (summary.json present; `synthetic` excluded)."""
    base = ROOT / "outputs" / "backtests"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and p.name != "synthetic"
                  and bt.MODEL_NAME.fullmatch(p.name) and (p / "summary.json").exists())


def _read_json(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def refuse_non_in_sample(weekly: pd.DataFrame, is_end: pd.Timestamp, what: str) -> None:
    """Stop if a weekly table holds a week that is not In-Sample: period other than IS, a signal week after is_end or a
    return realised after it (operating manual rule 3)."""
    closes = pd.DatetimeIndex(weekly.index.get_level_values("date_close"))
    realised = pd.DatetimeIndex(weekly["realised_on"])
    bad = (closes > is_end) | (realised > is_end)
    if "period" in weekly:
        bad |= (weekly["period"] != "IS").to_numpy()
    if bad.any():
        raise SystemExit(f"refused: {what} holds {int(bad.sum())} week(s) that are not In-Sample; Out-of-Sample results "
                         "are evaluated only after 08_run_oos.py")


def read_weekly(path) -> pd.DataFrame:
    weekly = pd.read_csv(path, index_col=["date_open", "date_close"], parse_dates=["date_open", "date_close", "realised_on"])
    return weekly


def read_backtest(cfg: dict, model: str, is_end: pd.Timestamp) -> dict:
    """summary.json, metrics.csv and weekly.csv of outputs/backtests/<model>/, after check_used and the IS check."""
    folder = ROOT / "outputs" / "backtests" / model
    check_used(bt.backtest_used(cfg, model), folder / "used.yaml", f"06_backtest.py --model {model}")
    weekly = read_weekly(folder / "weekly.csv")
    refuse_non_in_sample(weekly, is_end, f"outputs/backtests/{model}/weekly.csv")
    summary = _read_json(folder / "summary.json")
    if summary["period"] != "IS":
        raise SystemExit(f"refused: outputs/backtests/{model}/summary.json is not In-Sample")
    metrics = pd.read_csv(folder / "metrics.csv", index_col=["scenario", "rf"])
    if (metrics["period"] != "IS").any():
        raise SystemExit(f"refused: outputs/backtests/{model}/metrics.csv holds a non-IS row")
    return {"summary": summary, "metrics": metrics, "weekly": weekly}


def benchmark_returns(weekly: pd.DataFrame, fwd: pd.DataFrame) -> pd.DataFrame:
    """Weekly returns of the comparators on the weeks of `weekly` (§11): the T-bill (weekly.rf), SPY's forward return
    (never traded) and the equal-weight sector basket, 1/9 per sector rebalanced every week (skeleton "Equal weight")."""
    u = universe()
    weeks = weekly.index
    return pd.DataFrame({TBILL: weekly["rf"], u.benchmark: fwd.loc[weeks, u.benchmark],
                         EQUAL_WEIGHT: fwd.loc[weeks, list(u.sectors)].mean(axis=1)}, index=weeks)


def model_rank_ic(cfg: dict, model: str, weeks: pd.MultiIndex, fwd: pd.DataFrame, is_end: pd.Timestamp) -> float:
    """Mean weekly Spearman rank IC of the model's scores against the sector forward returns on the backtested weeks,
    through src.stats.rank_ic (hook; NaN while it is a Phase 3.1 stub; decision S32-3)."""
    scores = bt.read_scores(model, cfg, is_end).reindex(weeks)
    result = bt.stats_hook("rank_ic", scores, fwd.loc[weeks, list(universe().sectors)])
    if result is None:
        return np.nan
    return float(result[bt.RANK_IC_MEAN_KEY])


def model_row(model: str, backtest: dict, rank_ic: float, placebo_percentile: float) -> dict:
    """One row of is_models.csv: the baseline-cost figures of §09/§11 (Sharpe both conventions, with the weekly T-bill and
    the constant 2%; drawdown; turnover; residual beta; market relation), the stress Sharpes, rank IC and placebo
    percentile."""
    summary, metrics, weekly = backtest["summary"], backtest["metrics"], backtest["weekly"]
    base = summary["baseline"]
    tbill, constant = metrics.loc[(base, "tbill")], metrics.loc[(base, "constant")]
    gross = weekly["gross"]
    row = {
        "model": model, "weeks": summary["weeks"], "first_week": summary["first_week"], "last_week": summary["last_week"],
        "net_sharpe_rf_tbill": tbill["sharpe_rf"], "net_sharpe_rf_constant": constant["sharpe_rf"],
        "net_sharpe_zero_cost": tbill["sharpe_zero_cost"],
        "gross_sharpe_zero_cost": performance(gross, 0.0)["sharpe_zero_cost"],
        "annualized_return": tbill["annualized_return"], "annualized_volatility": tbill["annualized_volatility"],
        "sortino_ratio": tbill["sortino_ratio"], "max_drawdown": tbill["max_drawdown"], "calmar_ratio": tbill["calmar_ratio"],
        "hit_rate": tbill["hit_rate"],
        "mean_turnover": summary["mean_turnover"], "turnover_per_year_weights": tbill["turnover_per_year_weights"],
        "avg_holding": tbill["avg_holding"],
        "gross_return_annual": float(gross.mean() * 52), "costs_annual": float(weekly["costs"].mean() * 52),
        "borrow_annual": float(weekly["borrow"].mean() * 52),
        "beta": tbill["beta"], "correlation": tbill["correlation"], "alpha": tbill["alpha"],
        "mean_abs_residual_beta": summary["mean_abs_residual_beta"], "cap_binding_weeks": summary["cap_binding_weeks"],
        "missing_input_weeks": summary["missing_input_weeks"],
    }
    for label, scenario in summary["scenarios"].items():
        if not scenario["baseline"]:
            row[f"net_sharpe_rf_tbill_{label}"] = scenario["net_sharpe_rf_tbill"]
    row |= {"rank_ic_mean": rank_ic, "placebo_percentile": placebo_percentile, "rf_tbill_annual": summary["rf_tbill_annual"]}
    return row


def benchmark_table(returns: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    rows = {}
    for name, r in returns.items():
        rows[name] = performance(r, rf) | return_stats(r)
    return pd.DataFrame(rows).T.rename_axis("series")


def read_shift_checks(cfg: dict, is_end: pd.Timestamp) -> pd.DataFrame:
    """One row per outputs/diagnostics/shift/<model>/ (check_used, IS check): base and delayed figures and the verdict."""
    base = ROOT / "outputs" / "diagnostics" / "shift"
    rows = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        check_used(bt.backtest_used(cfg, folder.name), folder / "used.yaml", f"06_backtest.py --shift-check {folder.name}")
        refuse_non_in_sample(read_weekly(folder / "weekly.csv"), is_end, f"outputs/diagnostics/shift/{folder.name}")
        s = _read_json(folder / "summary.json")
        row = {"model": s["model"], "weeks": s["weeks"], "first_week": s["first_week"], "last_week": s["last_week"]}
        for book in ("base", "delayed"):
            for key in ("net_sharpe_rf_tbill", "net_sharpe_zero_cost", "gross_sharpe_zero_cost", "max_drawdown",
                        "mean_turnover", "rank_ic_mean"):
                row[f"{book}_{key}"] = s[book][key]
        row |= {"p_delayed_better": s["p_delayed_better"], "threshold": s["threshold"], "verdict": s["verdict"]}
        rows.append(row)
    return pd.DataFrame(rows)


def read_placebo(cfg: dict) -> tuple[dict, pd.DataFrame] | None:
    """summary.json and books.csv of outputs/diagnostics/placebo/ (check_used), or None if 06 --placebo has not run."""
    folder = ROOT / "outputs" / "diagnostics" / "placebo"
    if not (folder / "summary.json").exists():
        return None
    summary = _read_json(folder / "summary.json")
    check_used(bt.placebo_used(cfg, summary["reference"]), folder / "used.yaml", "06_backtest.py --placebo")
    if summary["period"] != "IS":
        raise SystemExit("refused: the placebo summary is not In-Sample")
    return summary, pd.read_csv(folder / "books.csv", index_col="book")


def _same_weeks(summary: dict, placebo: dict) -> bool:
    return all(summary[k] == placebo[k] for k in ("weeks", "first_week", "last_week"))


def evaluate(cfg: dict) -> pd.DataFrame:
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    models = backtested_models()
    if not models:
        raise SystemExit("07_evaluate.py: no outputs/backtests/<model>/; run 06_backtest.py --model NAME or --all first")
    backtests = {model: read_backtest(cfg, model, is_end) for model in models}
    shift = read_shift_checks(cfg, is_end)
    placebo = read_placebo(cfg)
    _, _, fwd, _, _ = bt.in_sample_market(is_end)  # stops before returning if any return is realised after is_end

    rows = []
    for model, backtest in backtests.items():
        summary = backtest["summary"]
        percentile = np.nan
        if placebo is not None and _same_weeks(summary, placebo[0]):
            percentile = bt.placebo_percentile(placebo[1]["net_sharpe_rf_tbill"], summary["net_sharpe_rf_tbill"])
        rows.append(model_row(model, backtest, model_rank_ic(cfg, model, backtest["weekly"].index, fwd, is_end), percentile))
    table = pd.DataFrame(rows).set_index("model")

    reference = REFERENCE if REFERENCE in backtests else models[0]
    ref_weekly = backtests[reference]["weekly"]
    comparators = benchmark_returns(ref_weekly, fwd)

    out = ROOT / "outputs" / "metrics"
    write_csv(table, out / "is_models.csv", float_format="%.6g")
    benchmarks = benchmark_table(comparators, ref_weekly["rf"]).assign(weeks_of=reference)
    write_csv(benchmarks, out / "is_benchmarks.csv", float_format="%.6g")
    if len(shift):
        write_csv(shift.set_index("model"), out / "shift_check.csv", float_format="%.6g")
    if placebo is not None:
        summary = placebo[0]
        flat = {"reference": summary["reference"], "books": summary["books"], "weeks": summary["weeks"],
                "first_week": summary["first_week"], "last_week": summary["last_week"],
                "seed_first": summary["seed_first"], "seed_last": summary["seed_last"],
                **{f"sharpe_{k}": v for k, v in summary["net_sharpe_rf_tbill"].items()},
                "mean_turnover": summary["mean_turnover"],
                "reference_net_sharpe_rf_tbill": summary["reference_row"]["net_sharpe_rf_tbill"],
                "reference_percentile": summary["reference_percentile"],
                "reference_gross_sharpe_zero_cost": summary["reference_row"]["gross_sharpe_zero_cost"],
                "placebo_gross_sharpe_median": summary["gross_sharpe_zero_cost"]["q50"],
                "reference_percentile_gross": summary["reference_percentile_gross"]}
        write_csv(pd.DataFrame([flat]).set_index("reference"), out / "placebo.csv", float_format="%.6g")
    save_used(bt.used_settings(cfg) | walkforward_settings(cfg) | {"placebo": cfg.get("placebo")}, out / "used.yaml")

    plot_dir = ROOT / "outputs" / "plots"
    for model, backtest in backtests.items():
        weekly = backtest["weekly"]
        series = pd.concat([weekly["net"].rename(model), benchmark_returns(weekly, fwd)], axis=1)
        plots.equity_curves(series, weekly["period"], weekly["realised_on"], plot_dir / f"{model}_equity",
                            title=f"{model}, In-Sample: net equity vs T-bill, SPY and equal weight (100 at start, log)")
        plots.drawdowns(series, weekly["period"], weekly["realised_on"], plot_dir / f"{model}_drawdown",
                        title=f"{model}, In-Sample: drawdown")
        plots.exposures(weekly, plot_dir / f"{model}_exposure", title=f"{model}, In-Sample: exposures (week of the signal)")
        plots.cost_bridge(weekly, plot_dir / f"{model}_bridge",
                          title=f"{model}, In-Sample: gross → costs → borrow → net (mean weekly return × 52)")
    same = [m for m in models if _same_weeks(backtests[m]["summary"], backtests[reference]["summary"])]
    together = pd.concat([backtests[m]["weekly"]["net"].rename(m) for m in same] + [comparators], axis=1)
    plots.equity_curves(together, ref_weekly["period"], ref_weekly["realised_on"], plot_dir / "all_models_equity",
                        title="In-Sample net equity of every model vs T-bill, SPY and equal weight (100 at start, log)")
    if placebo is not None:
        marks = {m: backtests[m]["summary"]["net_sharpe_rf_tbill"] for m in models
                 if _same_weeks(backtests[m]["summary"], placebo[0])}
        plots.placebo_histogram(placebo[1]["net_sharpe_rf_tbill"], marks, plot_dir / "placebo_sharpe")
    return table


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)
    cfg = load_config()
    table = evaluate(cfg)
    shown = ["weeks", "net_sharpe_rf_tbill", "net_sharpe_rf_constant", "net_sharpe_zero_cost", "gross_sharpe_zero_cost",
             "annualized_return", "max_drawdown", "mean_turnover", "rank_ic_mean", "placebo_percentile"]
    print(f"In-Sample metrics, baseline costs, {len(table)} model(s) -> outputs/metrics/is_models.csv")
    print(table[shown].to_string(float_format=lambda x: f"{x:.4f}"))
    print("plots -> outputs/plots/")


if __name__ == "__main__":
    sys.exit(main())
