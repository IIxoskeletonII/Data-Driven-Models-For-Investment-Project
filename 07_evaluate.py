"""In-Sample evaluation of every backtested model (protocol section 11), Phase 3.2: one table of metrics, the benchmarks,
the §12 one-week-shift check, the §11 placebo, and the plots. In-Sample only: every input is checked to hold no week
realised after split.in_sample_end (operating manual rule 3); the selection gate of §07 is Phase 3.1 (src/stats.py).

Inputs:  outputs/backtests/<model>/        (06_backtest.py --model / --all; check_used of each used.yaml)
         outputs/diagnostics/shift/<model>/ (06_backtest.py --shift-check), outputs/diagnostics/placebo/ (--placebo)
         outputs/walkforward/<model>/scores.csv (rank IC) and the raw prices cut at the In-Sample end through
         06_backtest.py: in_sample_market (refuse_oos_returns), for SPY and the equal-weight basket
Outputs: outputs/metrics/  is_models.csv (one row per model), is_benchmarks.csv, shift_check.csv, placebo.csv, used.yaml
         outputs/plots/    <model>_{equity,drawdown,exposure,bridge}.{html,png}, all_models_equity, placebo_sharpe

--period OOS (decisions S34-8 to S34-11): only after the single run of 08_run_oos.py (FROZEN.lock and exactly one entry in
outputs/oos_access_log.json for it). Reads outputs/oos/ and writes outputs/metrics/oos_models.csv (per model and period),
oos_benchmarks.csv, oos_bonus.csv (the §11 market-neutral tests), oos_secondary.csv (Sharpe and drawdown vs SPY,
Ledoit-Wolf), oos_inference.csv (DSR with the full trial count, PBO), oos_used.yaml, and outputs/plots/oos_*.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src import metrics, plots, stats
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


# -- --period OOS: after the single run of 08_run_oos.py (decisions S34-8 to S34-11) ------------------------------------

CODE = Path(__file__).resolve().parent


def load_run_script():
    """08_run_oos.py as a module, for its lock and log readers and oos_used (S34-8)."""
    spec = importlib.util.spec_from_file_location("run_oos_script_for_07", CODE / "08_run_oos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_after_the_run(run_script) -> dict:
    """Stop unless FROZEN.lock exists and outputs/oos_access_log.json holds exactly one entry, written for that lock
    (S34-8). Returns the entry."""
    lock = ROOT / run_script.LOCK_NAME
    if not lock.exists():
        raise SystemExit("refused: --period OOS needs FROZEN.lock and the single run of 08_run_oos.py")
    entries = run_script.read_oos_log(ROOT / run_script.OOS_LOG)
    if len(entries) != 1:
        raise SystemExit(f"refused: {run_script.OOS_LOG} holds {len(entries)} entries; --period OOS runs only after the "
                         "single Out-of-Sample run")
    if entries[0].get("lock_sha256") != run_script.file_sha256(lock):
        raise SystemExit(f"refused: the entry of {run_script.OOS_LOG} was not written for the current FROZEN.lock")
    return entries[0]


def read_oos_book(cfg: dict, model: str, run_script) -> dict:
    """summary.json, metrics.csv, weekly.csv and the Out-of-Sample scores of outputs/oos/<model>/, after check_used."""
    folder = ROOT / "outputs" / "oos" / model
    check_used(run_script.oos_used(cfg, model), folder / "used.yaml", "08_run_oos.py")
    weekly = read_weekly(folder / "weekly.csv")
    scores = pd.read_csv(folder / "scores.csv", index_col=["date_open", "date_close"], parse_dates=["date_open", "date_close"])
    metrics = pd.read_csv(folder / "metrics.csv", index_col=["scenario", "rf", "period"])
    return {"summary": _read_json(folder / "summary.json"), "metrics": metrics, "weekly": weekly, "scores": scores}


def _period_rows(weekly: pd.DataFrame, name: str) -> pd.DataFrame:
    return weekly.loc[(weekly["period"] == name).to_numpy()]


def oos_model_rows(model: str, book: dict, frozen_scores: pd.DataFrame, fwd: pd.DataFrame, selected: str) -> list[dict]:
    """Rows of oos_models.csv: per period, the baseline-cost metrics of S32-7 and the mean rank IC (S34-8)."""
    summary, table, weekly = book["summary"], book["metrics"], book["weekly"]
    base = summary["baseline"]
    scores = pd.concat([frozen_scores, book["scores"]])
    sectors = list(universe().sectors)
    rows = []
    for name in ("IS", "OOS"):
        part = _period_rows(weekly, name)
        if part.empty:
            continue
        tbill, constant = table.loc[(base, "tbill", name)], table.loc[(base, "constant", name)]
        ic = stats.rank_ic(scores.reindex(part.index), fwd.loc[part.index, sectors])
        rows.append({
            "model": model, "period": name, "selected": model == selected, "weeks": len(part),
            "first_week": _day(part.index.get_level_values("date_close")[0]),
            "last_week": _day(part.index.get_level_values("date_close")[-1]),
            "net_sharpe_rf_tbill": tbill["sharpe_rf"], "net_sharpe_rf_constant": constant["sharpe_rf"],
            "net_sharpe_zero_cost": tbill["sharpe_zero_cost"],
            "gross_sharpe_zero_cost": performance(part["gross"], 0.0)["sharpe_zero_cost"],
            "annualized_return": tbill["annualized_return"], "annualized_volatility": tbill["annualized_volatility"],
            "sortino_ratio": tbill["sortino_ratio"], "max_drawdown": tbill["max_drawdown"],
            "calmar_ratio": tbill["calmar_ratio"], "hit_rate": tbill["hit_rate"], "final_equity": tbill["final_equity"],
            "mean_turnover": float(part["turnover"].mean()), "turnover_per_year_weights": tbill["turnover_per_year_weights"],
            "avg_holding": tbill["avg_holding"], "gross_return_annual": float(part["gross"].mean() * 52),
            "costs_annual": float(part["costs"].mean() * 52), "borrow_annual": float(part["borrow"].mean() * 52),
            "beta": tbill["beta"], "correlation": tbill["correlation"], "alpha": tbill["alpha"],
            "mean_abs_residual_beta": float(part["residual_beta"].abs().mean()),
            "cap_binding_weeks": int(part["cap_binds"].sum()), "rank_ic_mean": ic["mean"], "rank_ic_t": ic["t_stat"],
            "rf_tbill_annual": tbill["rf_annual"],
        })
    return rows


def _day(stamp) -> str:
    return pd.Timestamp(stamp).strftime("%Y-%m-%d")


def down_market_mean(r: pd.Series, m: pd.Series, *, n_resamples: int, block: float, seed: int,
                     confidence: float) -> dict[str, float]:
    """Mean of r over the periods where m < 0 and its stationary-bootstrap percentile interval (§11 bonus test 3,
    decision S34-9): the paired series (r, m) is resampled with src.stats.stationary_bootstrap_indices (mean block
    `block` periods, numpy default_rng(seed)) and the mean is taken over the resampled down periods (resamples without
    one are skipped). Returns mean, lower, upper, n_down, n_resamples_used."""
    m = m.reindex(r.index)
    x, y = r.to_numpy(dtype=np.float64), m.to_numpy(dtype=np.float64)
    down = y < 0
    if not down.any():
        return {"mean": np.nan, "lower": np.nan, "upper": np.nan, "n_down": 0.0, "n_resamples_used": 0.0}
    rows = stats.stationary_bootstrap_indices(len(x), int(n_resamples), float(block), np.random.default_rng(seed))
    mask = down[rows]
    counts = mask.sum(axis=1)
    used = counts > 0
    means = (x[rows] * mask).sum(axis=1)[used] / counts[used]
    tail = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(means, [tail, 1.0 - tail])
    return {"mean": float(x[down].mean()), "lower": float(lower), "upper": float(upper), "n_down": float(down.sum()),
            "n_resamples_used": float(used.sum())}


def bonus_row(model: str, weekly: pd.DataFrame, spy: pd.Series, cfg: dict, selected: str) -> dict:
    """The four market-neutral tests of §11 on the Out-of-Sample weeks of one book (decision S34-9)."""
    part = _period_rows(weekly, "OOS")
    r, m = part["net"].astype(np.float64), spy.loc[part.index].astype(np.float64)
    limits, gate, confidence = cfg["metrics"]["market_neutral"], cfg["selection"], float(cfg["inference"]["confidence"])
    beta = metrics.hac_beta(r, m, stats.newey_west_lags(len(r)), confidence)
    rho = float(np.corrcoef(r.to_numpy(), m.to_numpy())[0, 1])
    boot = {"n_resamples": gate["bootstrap_resamples"], "seed": int(cfg["seed"]), "confidence": confidence}
    weeks_down = down_market_mean(r, m, block=gate["bootstrap_block"], **boot)
    months_r = metrics.monthly_returns(r, part["realised_on"])
    months_m = metrics.monthly_returns(m, part["realised_on"])
    months_down = down_market_mean(months_r, months_m, block=1, **boot)
    years = metrics.calendar_year_returns(r, part["realised_on"])
    row = {"model": model, "selected": model == selected, "weeks": len(r),
           "beta": beta["beta"], "beta_hac_se": beta["se"], "beta_lower": beta["lower"], "beta_upper": beta["upper"],
           "beta_lags": beta["lags"],
           "passes_beta": bool(abs(beta["beta"]) < limits["beta_abs_max"] and beta["lower"] <= 0 <= beta["upper"]),
           "correlation": rho, "passes_correlation": bool(abs(rho) < limits["corr_abs_max"])}
    for label, result in (("down_week", weeks_down), ("down_month", months_down)):
        row |= {f"{label}_mean": result["mean"], f"{label}_lower": result["lower"], f"{label}_upper": result["upper"],
                f"{label}_count": result["n_down"], f"passes_{label}": bool(result["mean"] > 0)}
    row |= {"mean_weekly": float(r.mean()), "passes_mean_weekly": bool(r.mean() > 0),
            "rolling_52w_positive_share": metrics.rolling_positive_share(r, 52)}
    row |= {f"return_{year}": float(value) for year, value in years.items()}
    row["all_pass"] = all(row[key] for key in ("passes_beta", "passes_correlation", "passes_down_week",
                                               "passes_down_month", "passes_mean_weekly"))
    row["claimed"] = bool(row["all_pass"] and model == selected)
    return row


def secondary_row(model: str, weekly: pd.DataFrame, spy: pd.Series, selected: str) -> dict:
    """The alternative bonus of §11 on the Out-of-Sample weeks (decision S34-10): headline Sharpe and max drawdown of
    the book and of SPY, and the Ledoit–Wolf test of the Sharpe difference."""
    part = _period_rows(weekly, "OOS")
    r, m, rf = part["net"].astype(np.float64), spy.loc[part.index].astype(np.float64), part["rf"]
    book, market = performance(r, rf), performance(m, rf)
    test = stats.sharpe_difference_test(r, m)
    meets = bool(book["sharpe_rf"] > market["sharpe_rf"] and book["max_drawdown"] > market["max_drawdown"])
    return {"model": model, "selected": model == selected, "weeks": len(r),
            "sharpe_rf_tbill": book["sharpe_rf"], "spy_sharpe_rf_tbill": market["sharpe_rf"],
            "max_drawdown": book["max_drawdown"], "spy_max_drawdown": market["max_drawdown"],
            "lw_sharpe_difference_weekly": test["difference"], "lw_sharpe_difference_annual": test["difference_annual"],
            "lw_z": test["z"], "lw_p_value": test["p_value"], "meets": meets}


def trial_matrix(cfg: dict, run_script) -> tuple[pd.DataFrame, int]:
    """In-Sample baseline net returns of every backtested trial (decision S34-11): one column per distinct spec_hash of
    the trial log, on the common weeks; and N = the number of trial-log rows (S31-7)."""
    trial_log = ROOT / run_script.TRIAL_LOG
    hashes = run_script.logged_spec_hashes(trial_log)
    n_trials = len(pd.read_csv(trial_log))
    columns = {}
    for model in backtested_models():
        digest = _read_json(ROOT / "outputs" / "backtests" / model / "summary.json").get("spec_hash")
        if digest not in hashes:
            raise SystemExit(f"refused: outputs/backtests/{model} has spec_hash {str(digest)[:12]}…, not a trial-log row")
        if digest not in columns:
            weekly = read_weekly(ROOT / "outputs" / "backtests" / model / "weekly.csv")
            refuse_non_in_sample(weekly, pd.Timestamp(cfg["split"]["in_sample_end"]), f"outputs/backtests/{model}")
            columns[digest] = weekly["net"].rename(model)
    matrix = pd.concat(list(columns.values()), axis=1).dropna()
    return matrix, n_trials


def inference_row(cfg: dict, run_script, selected: str, selected_oos: pd.Series) -> dict:
    """DSR with the full trial count and PBO (decision S34-11)."""
    matrix, n_trials = trial_matrix(cfg, run_script)
    is_path = ROOT / "outputs" / "backtests" / selected / "weekly.csv"
    selected_is = read_weekly(is_path)["net"] if is_path.exists() else None
    return {"selected": selected, "n_trials": n_trials, "matrix_columns": matrix.shape[1], "matrix_weeks": matrix.shape[0],
            "dsr_in_sample": (stats.deflated_sharpe_ratio(selected_is, n_trials, trial_returns=matrix)
                              if selected_is is not None else np.nan),
            "dsr_out_of_sample": stats.deflated_sharpe_ratio(selected_oos, n_trials, trial_returns=matrix),
            "pbo": stats.pbo_cscv(matrix, int(cfg["inference"]["pbo_blocks"]))}


def evaluate_oos(cfg: dict) -> dict[str, pd.DataFrame]:
    """--period OOS (decisions S34-8 to S34-11). Returns the written tables."""
    run_script = load_run_script()
    check_after_the_run(run_script)
    report = _read_json(ROOT / "outputs" / "oos" / "run.json")
    models, selected = list(report["models"]), report["selected"]
    books = {model: read_oos_book(cfg, model, run_script) for model in models}
    is_end, end = pd.Timestamp(cfg["split"]["in_sample_end"]), pd.Timestamp(cfg["data"]["end"])
    _, _, fwd, _, _ = bt.read_market(end, is_end, root=ROOT)
    spy = fwd[universe().benchmark]

    rows = []
    for model, book in books.items():
        frozen = run_script.read_frozen_scores(ROOT, model, is_end)
        rows += oos_model_rows(model, book, frozen, fwd, selected)
    table = pd.DataFrame(rows).set_index(["model", "period"])
    reference = books[selected]["weekly"]
    bench = []
    for name in ("IS", "OOS"):
        part = _period_rows(reference, name)
        bench.append(benchmark_table(benchmark_returns(part, fwd), part["rf"]).assign(period=name, weeks_of=selected))
    benchmarks = pd.concat(bench).reset_index().set_index(["series", "period"])
    bonus = pd.DataFrame([bonus_row(m, b["weekly"], spy, cfg, selected) for m, b in books.items()]).set_index("model")
    secondary = pd.DataFrame([secondary_row(m, b["weekly"], spy, selected) for m, b in books.items()]).set_index("model")
    selected_oos = _period_rows(books[selected]["weekly"], "OOS")["net"]
    inference = pd.DataFrame([inference_row(cfg, run_script, selected, selected_oos)]).set_index("selected")

    out = ROOT / "outputs" / "metrics"
    write_csv(table, out / "oos_models.csv", float_format="%.6g")
    write_csv(benchmarks, out / "oos_benchmarks.csv", float_format="%.6g")
    write_csv(bonus, out / "oos_bonus.csv", float_format="%.6g")
    write_csv(secondary, out / "oos_secondary.csv", float_format="%.6g")
    write_csv(inference, out / "oos_inference.csv", float_format="%.6g")
    save_used(bt.used_settings(cfg) | walkforward_settings(cfg) | {"oos": {"data_end": cfg["data"]["end"]}},
              out / "oos_used.yaml")

    plot_dir = ROOT / "outputs" / "plots"
    for model, book in books.items():
        weekly = book["weekly"]
        series = pd.concat([weekly["net"].rename(model), benchmark_returns(weekly, fwd)], axis=1)
        plots.equity_curves(series, weekly["period"], weekly["realised_on"], plot_dir / f"oos_{model}_equity",
                            title=f"{model}: net equity vs T-bill, SPY and equal weight, In-Sample and Out-of-Sample "
                                  "(100 at the start of each period, log)")
        plots.drawdowns(series, weekly["period"], weekly["realised_on"], plot_dir / f"oos_{model}_drawdown",
                        title=f"{model}: drawdown per period")
        plots.exposures(weekly, plot_dir / f"oos_{model}_exposure", title=f"{model}: exposures (week of the signal)")
        plots.cost_bridge(_period_rows(weekly, "OOS"), plot_dir / f"oos_{model}_bridge",
                          title=f"{model}, Out-of-Sample: gross → costs → borrow → net (mean weekly return × 52)")
    together = pd.concat([books[m]["weekly"]["net"].rename(m) for m in models] + [benchmark_returns(reference, fwd)],
                         axis=1).loc[reference.index]
    plots.equity_curves(together, reference["period"], reference["realised_on"], plot_dir / "oos_all_models_equity",
                        title="Net equity of every model vs T-bill, SPY and equal weight (100 at the start of each "
                              "period, log)")
    return {"models": table.reset_index(), "benchmarks": benchmarks, "bonus": bonus, "secondary": secondary,
            "inference": inference}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--period", choices=("IS", "OOS"), default="IS",
                        help="IS (default): the In-Sample evaluation; OOS: after the single run of 08_run_oos.py (S34-8)")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.period == "OOS":
        tables = evaluate_oos(cfg)
        print(f"Out-of-Sample evaluation of {tables['models']['model'].nunique()} model(s) -> outputs/metrics/oos_*.csv")
        print(tables["bonus"].to_string(float_format=lambda x: f"{x:.4f}"))
        print("plots -> outputs/plots/oos_*")
        return
    table = evaluate(cfg)
    shown = ["weeks", "net_sharpe_rf_tbill", "net_sharpe_rf_constant", "net_sharpe_zero_cost", "gross_sharpe_zero_cost",
             "annualized_return", "max_drawdown", "mean_turnover", "rank_ic_mean", "placebo_percentile"]
    print(f"In-Sample metrics, baseline costs, {len(table)} model(s) -> outputs/metrics/is_models.csv")
    print(table[shown].to_string(float_format=lambda x: f"{x:.4f}"))
    print("plots -> outputs/plots/")


if __name__ == "__main__":
    sys.exit(main())
