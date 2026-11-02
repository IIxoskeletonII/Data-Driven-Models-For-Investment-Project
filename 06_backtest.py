"""Turn signals into sized, hedged weekly returns (protocol section 09): dollar-neutral core, IVV beta hedge,
costs on drifted-weight turnover, short borrow, no cash interest. Reconciled against src/ledger.py.

CLI wiring only: load config.yaml, call src.sizing / src.backtest / src.ledger / src.metrics, save outputs with the
config they were built with (src/config.py: save_used).

Modes (real-data backtests come in Phase 2.3, through src/vault.py; until then the script refuses to run without a flag):
  --synthetic             the shared synthetic market of tests/conftest.py with seeded random scores (wiring check)
                          -> outputs/backtests/synthetic/
  --ledger-years Y [Y..]  ledger reconciliation on real data (Levels A and B, Amendment 3), In-Sample years only: every date used
                          is <= split.in_sample_end; the weights are seeded random ±k books, no model
                          -> outputs/ledger/  (differences only, no prices)
"""

import argparse
import importlib.util
import sys

import numpy as np
import pandas as pd

from src.backtest import forward_returns, run
from src.config import ROOT, load_config, save_used
from src.contracts import universe
from src.data import adjust_ohlc, file_stem, weekly_panel, write_csv
from src.ledger import dividend_reinvestment_term, run_ledger
from src.metrics import period_metrics
from src.sizing import size_book

LEDGER_TOLERANCE = 1e-6  # pre-registered (§09): zero-cost ledger vs engine, per week
LEDGER_COSTS_TOLERANCE = 1e-10  # Level A with costs and borrow, after Amendment 3 C2
LEDGER_BOOKS = 10  # seeded random books replayed per year


def used_settings(cfg: dict) -> dict:
    """The config sections that determine the backtest outputs."""
    return {key: cfg[key] for key in ("seed", "split", "execution", "signal", "costs", "metrics")}


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


def run_ledger_check(cfg: dict, years: list[int]) -> None:
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    if any(pd.Timestamp(year, 12, 31) >= is_end for year in years):
        raise SystemExit(f"--ledger-years must be In-Sample years whose weeks all realise before {is_end.date()}")
    traded, tradables = list(universe().traded), list(universe().tradables)
    raw = read_raw_in_sample(tradables, is_end)
    adjusted = {t: adjust_ohlc(raw[t]) for t in tradables}
    sessions = pd.DatetimeIndex(sorted(set().union(*(f.index for f in raw.values()))), name="date")
    daily_open = pd.DataFrame({t: adjusted[t]["Open"] for t in tradables}).reindex(sessions)
    daily_close = pd.DataFrame({t: adjusted[t]["Close"] for t in tradables}).reindex(sessions)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    fwd, realised_on, period = forward_returns(weekly_open, is_end=is_end)
    refuse_oos_returns(realised_on, is_end)

    rows, details = [], []
    costs = cfg["costs"]
    bps, borrow = costs["bps_baseline"], costs["borrow_baseline"]
    fridays = pd.DatetimeIndex(fwd.index.get_level_values("date_close"))
    for year in years:
        weeks = fwd.index[(fridays.year == year) & fwd[traded].notna().all(axis=1).to_numpy()]
        diff_a, diff_a_costs, diff_b, terms, events = [], [], [], [], []
        for book in range(LEDGER_BOOKS):
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
            "year": year, "books": LEDGER_BOOKS, "book_weeks": len(diff_b_all),
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
    save_used(used_settings(cfg), out / "used.yaml")
    print(summary.T.to_string(float_format=lambda x: f"{x:.3e}"))
    print()
    print("Level B: max |w * reinvestment term| by ticker and year")
    print(by_ticker.to_string(float_format=lambda x: f"{x:.2e}"))
    checks = {
        f"Level A, zero cost, |ledger - engine| <= {LEDGER_TOLERANCE:g}": summary["A_max_abs_diff"] <= LEDGER_TOLERANCE,
        f"Level A, with costs and borrow, |ledger - engine| <= {LEDGER_COSTS_TOLERANCE:g}":
            summary["A_costs_max_abs_diff"] <= LEDGER_COSTS_TOLERANCE,
        f"Level B, |ledger - engine - dividend-reinvestment term| <= {LEDGER_TOLERANCE:g} (Amendment 3 C1)":
            summary["B_max_abs_remainder"] <= LEDGER_TOLERANCE,
    }
    print()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed.all() else 'FAIL'}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--synthetic", action="store_true", help="run on the shared synthetic market")
    parser.add_argument("--ledger-years", type=int, nargs="+", help="ledger reconciliation on In-Sample years of real data")
    args = parser.parse_args(argv)
    cfg = load_config()
    if args.synthetic:
        run_synthetic(cfg)
    elif args.ledger_years:
        run_ledger_check(cfg, args.ledger_years)
    else:
        sys.exit("06_backtest.py: real-data backtests need the vault (src/vault.py, Phase 2.3). "
                 "Use --synthetic or --ledger-years.")


if __name__ == "__main__":
    main()
