"""Turn signals into sized, hedged weekly returns (protocol section 09): dollar-neutral core, IVV beta hedge,
costs on drifted-weight turnover, short borrow, no cash interest. Reconciled against src/ledger.py.

CLI wiring only: load config.yaml, call src.sizing / src.backtest / src.ledger / src.metrics, save outputs with the
config they were built with (src/config.py: save_used).

Modes (one is required):
  --model NAME            In-Sample backtest of a model's walk-forward scores on real data (decisions S23-4 to S23-10):
                          scores from 05_train_walkforward.py (outputs/walkforward/NAME/scores.csv, contract 8, check_used),
                          raw sizing betas (contract 10) through src/vault.py, forward returns cut at the In-Sample end
                          (refuse_oos_returns), the baseline and both stress cost scenarios, metrics of the IS period with
                          the weekly T-bill (headline) and the constant 2%, benchmark SPY
                          -> outputs/backtests/NAME/  (weekly.csv, metrics.csv, used.yaml, summary.json; git-ignored)
  --synthetic             the shared synthetic market of tests/conftest.py with seeded random scores (wiring check)
                          -> outputs/backtests/synthetic/
  --ledger-years [Y ..]   ledger reconciliation on real data (Levels A and B, Amendment 3), In-Sample years only: every date used
                          is <= split.in_sample_end; the weights are seeded random ±k books, no model. Without years it
                          replays ledger.years; books per year and tolerances always come from config.yaml (ledger.*)
                          -> outputs/ledger/  (differences only, no prices)
"""

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest import forward_returns, run
from src.config import ROOT, check_used, load_config, save_used
from src.contracts import universe, validate_betas, validate_scores
from src.data import DATE_FORMAT, adjust_ohlc, file_stem, weekly_panel, write_csv
from src.features import features_settings
from src.ledger import dividend_reinvestment_term, run_ledger
from src.metrics import period_metrics, tbill_weekly_returns
from src.models import walkforward_settings
from src.sizing import size_book
from src.vault import Vault

WEEK_COLUMNS = ["date_open", "date_close"]
WEEKLY_FIELDS = ("gross", "net", "turnover", "costs", "borrow", "residual_beta", "net_exposure", "hedge")


def used_settings(cfg: dict) -> dict:
    """The config sections that determine the backtest outputs."""
    return {key: cfg[key] for key in ("seed", "split", "execution", "signal", "costs", "metrics")}


def model_names(cfg: dict) -> list[str]:
    """Models whose walk-forward scores 06 can backtest: M0, the fallback M0_star and models.candidate_order."""
    return ["M0", "M0_star", *cfg["models"]["candidate_order"]]


def cost_scenarios(cfg: dict) -> list[tuple[str, float, float, bool]]:
    """(label, cost_bps, borrow_annual, is_baseline) of the §09 cost scenarios, pairing costs.bps and costs.borrow by
    position (5 bps with 1%, 10 with 2%, 20 with 5%: the §09 table; decision S23-7). Label e.g. "10bps_2pct"."""
    costs = cfg["costs"]
    bps, borrow = list(costs["bps"]), list(costs["borrow"])
    baseline = (costs["bps_baseline"], costs["borrow_baseline"])
    pairs = list(zip(bps, borrow, strict=False))
    if len(bps) != len(borrow) or baseline not in pairs:
        raise SystemExit(f"costs.bps {bps} and costs.borrow {borrow} must pair by position, with the baseline "
                         f"{baseline} as one pair (§09 cost scenarios, S23-7)")
    return [(f"{b:g}bps_{100 * r:g}pct", float(b), float(r), (b, r) == baseline) for b, r in pairs]


def ledger_settings(cfg: dict) -> dict:
    """The ledger section of config.yaml, checked: In-Sample years only (every week realised before split.in_sample_end),
    a positive number of books per year, tolerances in (0, 1e-6] (the pre-registered §09 tolerance is the loosest allowed).
    """
    if "ledger" not in cfg:
        raise SystemExit("config.yaml has no ledger: section (years, books_per_year, tolerance, tolerance_costs)")
    ledger = cfg["ledger"]
    missing = [key for key in ("years", "books_per_year", "tolerance", "tolerance_costs") if key not in ledger]
    if missing:
        raise SystemExit(f"config.yaml ledger: section lacks {missing}")
    years, books = ledger["years"], ledger["books_per_year"]
    if not years or not all(isinstance(year, int) and not isinstance(year, bool) for year in years):
        raise SystemExit(f"ledger.years must be a non-empty list of years, got {years!r}")
    _check_in_sample_years(years, pd.Timestamp(cfg["split"]["in_sample_end"]), "ledger.years")
    if not isinstance(books, int) or isinstance(books, bool) or books < 1:
        raise SystemExit(f"ledger.books_per_year must be a positive int, got {books!r}")
    for key in ("tolerance", "tolerance_costs"):
        if not 0 < float(ledger[key]) <= 1e-6:
            raise SystemExit(f"ledger.{key} must be in (0, 1e-6], the pre-registered §09 tolerance, got {ledger[key]!r}")
    return {"years": list(years), "books_per_year": books, "tolerance": float(ledger["tolerance"]),
            "tolerance_costs": float(ledger["tolerance_costs"])}


def _check_in_sample_years(years: list[int], is_end: pd.Timestamp, name: str) -> None:
    if any(pd.Timestamp(year, 12, 31) >= is_end for year in years):
        raise SystemExit(f"{name} must be In-Sample years whose weeks all realise before {is_end.date()}, got {years}")


def random_scores(index: pd.MultiIndex, seed: int) -> pd.DataFrame:
    """Seeded random sector scores: a placebo book for wiring and accounting checks, no model."""
    rng = np.random.default_rng(seed)
    sectors = list(universe().sectors)
    return pd.DataFrame(rng.normal(size=(len(index), len(sectors))), index=index, columns=sectors)


def random_betas(index: pd.MultiIndex, seed: int) -> pd.DataFrame:
    """Seeded random sizing betas in [0.6, 1.4] (IVV 1.0), so that the hedge is active: accounting checks only."""
    rng = np.random.default_rng(seed + 1)
    traded = list(universe().traded)
    betas = pd.DataFrame(rng.uniform(0.6, 1.4, size=(len(index), len(traded))), index=index, columns=traded)
    betas[universe().hedge] = 1.0
    return betas


def load_synthetic_market():
    """The shared synthetic market of tests/conftest.py (contract 18), loaded by path."""
    spec = importlib.util.spec_from_file_location("synthetic_conftest", ROOT / "tests" / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_synthetic_market()


def run_synthetic(cfg: dict) -> None:
    market = load_synthetic_market()
    fwd, _, period = forward_returns(market.weekly_open, is_end=market.is_end)
    true_betas = pd.DataFrame({t: market.true_beta[t] for t in universe().traded}, index=fwd.index)
    sizing = size_book(random_scores(fwd.index, cfg["seed"]), true_betas, cfg)
    costs = cfg["costs"]
    result = run(sizing, fwd, period, costs["bps_baseline"], costs["borrow_baseline"])
    benchmark = fwd.loc[result.net.index, universe().benchmark]
    metrics = period_metrics(result.net, result.period, sizing.signals.loc[result.net.index], result.weights, benchmark,
                             cfg["metrics"]["risk_free_constant"])

    out = ROOT / "outputs" / "backtests" / "synthetic"
    weekly = pd.DataFrame({name: getattr(result, name) for name in
                           ("gross", "net", "turnover", "costs", "borrow", "residual_beta", "net_exposure", "hedge")})
    weekly["period"] = result.period
    write_csv(weekly, out / "weekly.csv")
    write_csv(pd.DataFrame(metrics), out / "metrics.csv")
    save_used(used_settings(cfg), out / "used.yaml")
    print(f"synthetic backtest: {len(result.net)} weeks -> {out.relative_to(ROOT)}")
    print(pd.DataFrame(metrics).loc[["sharpe_rf", "annualized_return", "max_drawdown", "beta"]].to_string())


def read_raw_in_sample(tickers: list[str], is_end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Yahoo raw files of the tickers, cut at the In-Sample end before anything else is done with them."""
    raw = {}
    for ticker in tickers:
        path = ROOT / "data" / "raw" / "yahoo" / f"{file_stem(ticker)}.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path.relative_to(ROOT)} not found: run 01_download_data.py first")
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        raw[ticker] = frame.loc[frame.index <= is_end]
    return raw


def refuse_oos_returns(realised_on: pd.Series, is_end: pd.Timestamp) -> None:
    """Stop if any forward return on real data is realised after the In-Sample end (operating manual rule 3; contract 15).

    Applies to every real-data path of this script, whether FROZEN.lock exists or not: after the lock, Out-of-Sample
    returns are computed only through the unlock path of 08_run_oos.py. The synthetic mode is not restricted.
    """
    late = realised_on.dropna()
    late = late[late > is_end]
    if len(late):
        raise SystemExit(f"refused: {len(late)} forward return(s) realised after the In-Sample end {is_end.date()} "
                         f"(first {late.min().date()}); Out-of-Sample returns are computed only by 08_run_oos.py")


def in_sample_market(is_end: pd.Timestamp) -> tuple[dict[str, pd.DataFrame], pd.DatetimeIndex, pd.DataFrame, pd.Series,
                                                     pd.Series]:
    """Raw Yahoo files of the tradables cut at the In-Sample end, the equity calendar (union of their sessions), and the
    forward returns, realisation dates and periods of contract 7 on adjusted weekly opens. Stops (refuse_oos_returns)
    before returning if any forward return is realised after is_end."""
    tradables = list(universe().tradables)
    raw = read_raw_in_sample(tradables, is_end)
    adjusted = {t: adjust_ohlc(raw[t]) for t in tradables}
    sessions = pd.DatetimeIndex(sorted(set().union(*(f.index for f in raw.values()))), name="date")
    daily_open = pd.DataFrame({t: adjusted[t]["Open"] for t in tradables}).reindex(sessions)
    daily_close = pd.DataFrame({t: adjusted[t]["Close"] for t in tradables}).reindex(sessions)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    fwd, realised_on, period = forward_returns(weekly_open, is_end=is_end)
    refuse_oos_returns(realised_on, is_end)
    return raw, sessions, fwd, realised_on, period


def run_ledger_check(cfg: dict, years: list[int] | None = None) -> None:
    """Levels A and B of the ledger reconciliation on real In-Sample data (§09, Amendment 3), settings from ledger.*;
    `years` overrides ledger.years."""
    settings = ledger_settings(cfg)
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    years = settings["years"] if not years else list(years)
    _check_in_sample_years(years, is_end, "--ledger-years")
    books_per_year, tolerance, tolerance_costs = settings["books_per_year"], settings["tolerance"], settings["tolerance_costs"]
    traded = list(universe().traded)
    raw, _, fwd, _, period = in_sample_market(is_end)

    rows, details = [], []
    costs = cfg["costs"]
    bps, borrow = costs["bps_baseline"], costs["borrow_baseline"]
    fridays = pd.DatetimeIndex(fwd.index.get_level_values("date_close"))
    for year in years:
        weeks = fwd.index[(fridays.year == year) & fwd[traded].notna().all(axis=1).to_numpy()]
        diff_a, diff_a_costs, diff_b, terms, events = [], [], [], [], []
        for book in range(books_per_year):
            seed = cfg["seed"] + 100 * year + book
            sizing = size_book(random_scores(weeks, seed), random_betas(weeks, seed), cfg)
            zero = run(sizing, fwd, period, 0.0, 0.0)
            charged = run(sizing, fwd, period, bps, borrow)
            level_a = run_ledger(zero.weights, raw, mode="adjusted")
            level_a_costs = run_ledger(charged.weights, raw, mode="adjusted", cost_bps=bps, borrow_annual=borrow)
            level_b = run_ledger(zero.weights, raw, mode="raw")
            # differences are ledger minus engine, the sign of Amendment 3 C1
            diff_a.append(level_a["ret"] - zero.gross.loc[level_a.index])
            diff_a_costs.append(level_a_costs["ret"] - charged.net.loc[level_a_costs.index])
            diff_b.append(level_b["ret"] - zero.gross.loc[level_b.index])
            terms.append(dividend_reinvestment_term(zero.weights, raw).loc[level_b.index])
            events.append(level_b[["dividends", "splits"]])
        term_by_ticker = pd.concat(terms)
        diff_b_all, term_all, event_all = pd.concat(diff_b), term_by_ticker.sum(axis=1), pd.concat(events)
        remainder = diff_b_all - term_all
        dividend_weeks, split_weeks = (event_all["dividends"] != 0).to_numpy(), (event_all["splits"] > 0).to_numpy()

        def worst(values: pd.Series, mask=None) -> float:
            values = values if mask is None else values[mask]
            return float(values.abs().max()) if len(values) else 0.0

        rows.append({
            "year": year, "books": books_per_year, "book_weeks": len(diff_b_all),
            "A_max_abs_diff": worst(pd.concat(diff_a)),
            "A_costs_max_abs_diff": worst(pd.concat(diff_a_costs)),
            "B_max_abs_diff": worst(diff_b_all), "B_mean_abs_diff": float(diff_b_all.abs().mean()),
            "B_dividend_weeks": int(dividend_weeks.sum()),
            "B_max_abs_term": worst(term_all),
            "B_max_abs_remainder": worst(remainder),
            "B_max_abs_diff_non_dividend_weeks": worst(diff_b_all, ~dividend_weeks),
            "B_split_factor_weeks": int(split_weeks.sum()),
            "B_max_abs_remainder_split_factor_weeks": worst(remainder, split_weeks),
        })
        details.append(term_by_ticker.abs().max().rename(year))

    summary = pd.DataFrame(rows).set_index("year")
    by_ticker = pd.concat(details, axis=1).T.rename_axis("year")
    out = ROOT / "outputs" / "ledger"
    write_csv(summary, out / "reconciliation.csv", float_format="%.6g")
    write_csv(by_ticker, out / "level_b_reinvestment_term_by_ticker.csv", float_format="%.6g")
    save_used(used_settings(cfg) | {"ledger": cfg["ledger"]}, out / "used.yaml")
    print(summary.T.to_string(float_format=lambda x: f"{x:.3e}"))
    print()
    print("Level B: max |w * reinvestment term| by ticker and year")
    print(by_ticker.to_string(float_format=lambda x: f"{x:.2e}"))
    checks = {
        f"Level A, zero cost, |ledger - engine| <= {tolerance:g}": summary["A_max_abs_diff"] <= tolerance,
        f"Level A, with costs and borrow, |ledger - engine| <= {tolerance_costs:g}":
            summary["A_costs_max_abs_diff"] <= tolerance_costs,
        f"Level B, |ledger - engine - dividend-reinvestment term| <= {tolerance:g} (Amendment 3 C1)":
            summary["B_max_abs_remainder"] <= tolerance,
    }
    print()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed.all() else 'FAIL'}")


def _closes(index: pd.MultiIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def _refuse_after(index: pd.MultiIndex, is_end: pd.Timestamp, what: str) -> None:
    """Stop if a weekly table holds a week ending after the In-Sample end (operating manual rule 3)."""
    late = _closes(index)[_closes(index) > is_end]
    if len(late):
        raise SystemExit(f"refused: {what} has {len(late)} week(s) after the In-Sample end {is_end.date()} "
                         f"(first {late.min().date()}); Out-of-Sample weeks are backtested only by 08_run_oos.py")


def read_scores(model: str, cfg: dict, is_end: pd.Timestamp) -> pd.DataFrame:
    """Walk-forward scores of `model` written by 05_train_walkforward.py (decisions S23-3, S23-6).

    File outputs/walkforward/<model>/scores.csv in contract-8 format: columns date_open, date_close (ISO dates, the weekly
    index), then the 9 sectors in universe order, floats, empty for a missing score; row t known after Friday close t.
    Refuses scores built with a different config.yaml (check_used of src.models.walkforward_settings, exactly
    {seed, data, split, execution, features, models}, against used.yaml in the same folder) and scores of
    any week after is_end. Returns a frame that passes validate_scores.
    """
    folder = ROOT / "outputs" / "walkforward" / model
    check_used(walkforward_settings(cfg), folder / "used.yaml", "05_train_walkforward.py")
    path = folder / "scores.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(ROOT).as_posix()} not found: run 05_train_walkforward.py first")
    scores = pd.read_csv(path, index_col=WEEK_COLUMNS, parse_dates=WEEK_COLUMNS)
    scores = scores.astype(np.float64)
    scores.columns.name = None
    validate_scores(scores)
    if scores.empty:
        raise SystemExit(f"{path.relative_to(ROOT).as_posix()} has no scored week")
    _refuse_after(scores.index, is_end, f"outputs/walkforward/{model}/scores.csv")
    return scores


def open_vault(cfg: dict) -> Vault:
    """The vault of contract 15 on data/processed, sealed at split.in_sample_end (no unlock: 08_run_oos.py only)."""
    return Vault(pd.Timestamp(cfg["split"]["in_sample_end"]), lock_path=ROOT / "FROZEN.lock",
                 log_path=ROOT / "outputs" / "vault_access_log.jsonl",
                 data_dir=ROOT / cfg["data"]["data_dir"] / "processed", cfg=cfg)


def read_betas(vault, is_end: pd.Timestamp) -> pd.DataFrame:
    """Raw sizing betas (contract 10) of the weeks with date_close <= is_end, through Vault.sizing_betas (S23-4)."""
    betas = vault.sizing_betas(is_end)
    validate_betas(betas)
    _refuse_after(betas.index, is_end, "the sizing betas")
    return betas


def read_risk_free(cfg: dict, is_end: pd.Timestamp) -> pd.Series:
    """Daily FRED yield of metrics.risk_free_series (DGS3MO, percent per year) from data/raw/fred, cut at is_end right
    after reading (decision S23-8). Unlagged; tbill_weekly_returns applies the one-session lag (Amendment 1)."""
    name = cfg["metrics"]["risk_free_series"]
    path = ROOT / cfg["data"]["data_dir"] / "raw" / "fred" / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path.relative_to(ROOT).as_posix()} not found: run 01_download_data.py first")
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    series = frame.loc[frame.index <= is_end, name].astype(np.float64)
    series.index = pd.DatetimeIndex(series.index, name="date")
    return series


def missing_input_weeks(scores: pd.DataFrame, betas: pd.DataFrame, weeks: pd.MultiIndex) -> int:
    """Number of the backtested weeks with a missing input of Amendment 2 C3 (S21-2): a missing sector score, or a
    missing or non-finite BETA52 of the 10 traded columns, or a zero IVV beta. Those weeks carry the previous targets."""
    hedge = universe().hedge
    b = betas.reindex(weeks)
    missing = scores.reindex(weeks).isna().any(axis=1) | ~np.isfinite(b).all(axis=1) | (b[hedge] == 0)
    return int(missing.sum())


def _week(stamp: pd.Timestamp) -> str:
    return pd.Timestamp(stamp).strftime(DATE_FORMAT)


def backtest_model(cfg: dict, model: str) -> dict:
    """In-Sample backtest of `model`'s walk-forward scores (§09, §11; decisions S23-4 to S23-10). Writes
    outputs/backtests/<model>/ only after every input has passed its checks; returns the summary."""
    if model not in model_names(cfg):
        raise SystemExit(f"--model must be one of {model_names(cfg)}, got {model!r}")
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    u = universe()

    scores = read_scores(model, cfg, is_end)
    check_used(features_settings(cfg), ROOT / cfg["data"]["data_dir"] / "processed" / "features_config.yaml",
               "03_build_features.py")
    betas = read_betas(open_vault(cfg), is_end)
    _, sessions, fwd, realised_on, period = in_sample_market(is_end)
    rf_weekly = tbill_weekly_returns(read_risk_free(cfg, is_end), fwd.index, sessions)
    rf_constant = float(cfg["metrics"]["risk_free_constant"])

    sizing = size_book(scores, betas, cfg)
    scenarios = cost_scenarios(cfg)
    results = {label: run(sizing, fwd, period, bps, borrow) for label, bps, borrow, _ in scenarios}
    baseline = next(label for label, *_, is_baseline in scenarios if is_baseline)
    base = results[baseline]
    weeks = base.net.index
    if (base.period != "IS").any():  # unreachable after refuse_oos_returns; kept as a second guard
        raise SystemExit("refused: a backtested week is not In-Sample")
    signals = sizing.signals.loc[weeks]
    benchmark = fwd.loc[weeks, u.benchmark]
    rf_tbill = rf_weekly.loc[weeks]

    rows, scenario_summary, rf_tbill_annual = [], {}, np.nan
    for label, bps, borrow, is_baseline in scenarios:
        result = results[label]
        by_rf = {}
        for rf_name, rf in (("tbill", rf_tbill), ("constant", rf_constant)):
            by_rf[rf_name] = period_metrics(result.net, result.period, signals, result.weights, benchmark, rf)["IS"]
            rows.append({"scenario": label, "cost_bps": bps, "borrow_annual": borrow, "baseline": is_baseline,
                         "rf": rf_name, "period": "IS"} | by_rf[rf_name])
        rf_tbill_annual = by_rf["tbill"]["rf_annual"]  # the same weeks in every scenario
        scenario_summary[label] = {
            "cost_bps": bps, "borrow_annual": borrow, "baseline": is_baseline,
            "net_sharpe_rf_tbill": by_rf["tbill"]["sharpe_rf"],
            "net_sharpe_rf_constant": by_rf["constant"]["sharpe_rf"],
            "net_sharpe_zero_cost": by_rf["tbill"]["sharpe_zero_cost"],
            "annualized_return": by_rf["tbill"]["annualized_return"],
            "max_drawdown": by_rf["tbill"]["max_drawdown"],
            "mean_turnover": float(result.turnover.mean()),
        }

    weekly = pd.DataFrame({name: getattr(base, name) for name in WEEKLY_FIELDS})
    weekly.insert(0, "realised_on", realised_on.loc[weeks])
    weekly.insert(1, "period", base.period)
    weekly["cap_binds"] = sizing.cap_binds.loc[weeks]
    weekly["rf"] = rf_tbill
    for label, *_, is_baseline in scenarios:
        if not is_baseline:
            weekly[f"net_{label}"] = results[label].net

    summary = {
        "model": model, "period": "IS", "baseline": baseline, "weeks": len(weeks),
        "first_week": _week(_closes(weeks)[0]), "last_week": _week(_closes(weeks)[-1]),
        "first_realised_on": _week(realised_on.loc[weeks].iloc[0]),
        "last_realised_on": _week(realised_on.loc[weeks].iloc[-1]),
        "net_sharpe_rf_tbill": scenario_summary[baseline]["net_sharpe_rf_tbill"],
        "net_sharpe_rf_constant": scenario_summary[baseline]["net_sharpe_rf_constant"],
        "net_sharpe_zero_cost": scenario_summary[baseline]["net_sharpe_zero_cost"],
        "max_drawdown": scenario_summary[baseline]["max_drawdown"],
        "mean_turnover": scenario_summary[baseline]["mean_turnover"],
        "mean_abs_residual_beta": float(base.residual_beta.abs().mean()),
        "cap_binding_weeks": int(sizing.cap_binds.loc[weeks].sum()),
        "missing_input_weeks": missing_input_weeks(scores, betas, weeks),
        "rf_tbill_annual": rf_tbill_annual, "rf_constant": rf_constant,
        "benchmark": u.benchmark, "scenarios": scenario_summary,
    }

    out = ROOT / "outputs" / "backtests" / model
    write_csv(weekly, out / "weekly.csv")
    write_csv(pd.DataFrame(rows).set_index(["scenario", "rf"]), out / "metrics.csv")
    save_used(used_settings(cfg) | walkforward_settings(cfg) | {"model": model}, out / "used.yaml")
    _write_json(summary, out / "summary.json")
    return summary


def _write_json(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2)
        f.write("\n")


def run_model(cfg: dict, model: str) -> None:
    summary = backtest_model(cfg, model)
    out = (ROOT / "outputs" / "backtests" / model).relative_to(ROOT).as_posix()
    print(f"{model} In-Sample backtest: {summary['weeks']} weeks, {summary['first_week']} to {summary['last_week']} "
          f"(realised {summary['first_realised_on']} to {summary['last_realised_on']}) -> {out}")
    table = pd.DataFrame(summary["scenarios"]).T
    print(table.to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"mean |residual beta| {summary['mean_abs_residual_beta']:.4f}; cap-binding weeks {summary['cap_binding_weeks']}; "
          f"missing-input weeks {summary['missing_input_weeks']}; T-bill average {summary['rf_tbill_annual']:.4%}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", help="In-Sample backtest of a model's walk-forward scores on real data (e.g. M0)")
    parser.add_argument("--synthetic", action="store_true", help="run on the shared synthetic market")
    parser.add_argument("--ledger-years", type=int, nargs="*",
                        help="ledger reconciliation on In-Sample years of real data (default: ledger.years)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    if args.model is not None:
        run_model(cfg, args.model)
    elif args.synthetic:
        run_synthetic(cfg)
    elif args.ledger_years is not None:
        run_ledger_check(cfg, args.ledger_years)
    else:
        sys.exit("06_backtest.py: choose a mode: --model NAME (real data: walk-forward scores, betas through the vault), "
                 "--synthetic or --ledger-years.")


if __name__ == "__main__":
    main()
