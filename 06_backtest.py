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
                          -> outputs/backtests/NAME/  (weekly.csv, metrics.csv, used.yaml, summary.json; git-ignored).
                          NAME is any folder of outputs/walkforward/ with a scores.csv (rungs and variants, S32-1)
  --all                   --model for every folder of outputs/walkforward/, inputs read once (S32-1)
  --shift-check [NAME ..] §12 leakage check: the book with its sector signals delayed one extra week against the book itself,
                          baseline costs, common weeks (default M0; S32-3) -> outputs/diagnostics/shift/NAME/
  --placebo [REFERENCE]   §11 placebo: placebo.books seeded random ±2/±2 books with the same hedge on the weeks of REFERENCE
                          (default M0; S32-4) -> outputs/diagnostics/placebo/
  --synthetic            the shared synthetic market of tests/conftest.py with seeded random scores (wiring check)
                          -> outputs/backtests/synthetic/
  --ledger-years [Y ..]   ledger reconciliation on real data (Levels A and B, Amendment 3), In-Sample years only: every date used
                          is <= split.in_sample_end; the weights are seeded random ±k books, no model. Without years it
                          replays ledger.years; books per year and tolerances always come from config.yaml (ledger.*)
                          -> outputs/ledger/  (differences only, no prices)
"""

import argparse
import functools
import importlib.util
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from src import stats
from src.backtest import forward_returns, run
from src.config import ROOT, check_used, load_config, save_used
from src.contracts import universe, validate_betas, validate_scores
from src.data import DATE_FORMAT, adjust_ohlc, file_stem, weekly_panel, write_csv
from src.features import features_settings
from src.ledger import dividend_reinvestment_term, run_ledger
from src.metrics import performance, period_metrics, tbill_weekly_returns
from src.models import walkforward_settings
from src.sizing import size_book
from src.vault import Vault, spec_hash

WEEK_COLUMNS = ["date_open", "date_close"]
WEEKLY_FIELDS = ("gross", "net", "turnover", "costs", "borrow", "residual_beta", "net_exposure", "hedge")


def used_settings(cfg: dict) -> dict:
    """The config sections that determine the backtest outputs."""
    return {key: cfg[key] for key in ("seed", "split", "execution", "signal", "costs", "metrics")}


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
    {seed, data, split, execution, features, models}, against used.yaml in the same folder), scores whose
    summary.json["spec_hash"] differs from the one the current config.yaml gives (check_spec_hash, decision S32-10) and
    scores of any week after is_end. Returns a frame that passes validate_scores.
    """
    folder = ROOT / "outputs" / "walkforward" / model
    check_used(walkforward_settings(cfg), folder / "used.yaml", "05_train_walkforward.py")
    check_spec_hash(model, cfg)
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


@functools.cache
def _walkforward_script():
    """05_train_walkforward.py, loaded by path (read only: its spec_for builds the spec of every --model and --fixed
    name; decision S32-10)."""
    path = Path(__file__).resolve().parent / "05_train_walkforward.py"  # the code next to this file, whatever ROOT is
    spec = importlib.util.spec_from_file_location("walkforward_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_spec_hash(model: str, cfg: dict) -> str:
    """The trial log's spec_hash of `model` under `cfg` (S23-6, decision S32-10): src.vault.spec_hash of the spec that
    05_train_walkforward.py's spec_for builds for that --model rung or --fixed name. Stops for a name 05 has no spec for,
    since its scores cannot be checked."""
    try:
        spec = _walkforward_script().spec_for(model, cfg)
    except ValueError as error:
        raise SystemExit(f"{model}: 05_train_walkforward.py has no spec for this name, so its spec_hash cannot be checked "
                         f"(decision S32-10): {error}") from None
    return spec_hash(spec, cfg)


def check_spec_hash(model: str, cfg: dict) -> str:
    """Stop unless outputs/walkforward/<model>/summary.json (written by 05_train_walkforward.py) holds the spec_hash the
    current config.yaml gives (expected_spec_hash): scores built before a change of any setting in the trial's identity
    (the walk-forward settings, models.*, the Amendment 5 C1 tuning entry) are stale (decision S32-10). Returns it."""
    path = ROOT / "outputs" / "walkforward" / model / "summary.json"
    shown = path.relative_to(ROOT).as_posix()
    if not path.exists():
        raise SystemExit(f"{shown} not found: run 05_train_walkforward.py for {model} (its spec_hash is checked, S32-10)")
    recorded = json.loads(path.read_text(encoding="utf-8")).get("spec_hash")
    if not isinstance(recorded, str) or not recorded:
        raise SystemExit(f"{shown} has no spec_hash: run 05_train_walkforward.py for {model} again (S32-10)")
    expected = expected_spec_hash(model, cfg)
    if recorded != expected:
        raise SystemExit(f"{model}: stale scores. {shown} has spec_hash {recorded[:12]}…, the current config.yaml gives "
                         f"{expected[:12]}…; run 05_train_walkforward.py for {model} again (decision S32-10)")
    return expected


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


# -- models: any folder of outputs/walkforward/ (decision S32-1) ----------------------------------------------------------

# letters, digits and underscores, with single dots inside (M1_a0.1, M2_a0.1; decisions S32-1, S32-9): no "..", no path
# separator, no leading or trailing dot (Windows drops a trailing dot from a folder name)
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*")


def walkforward_models() -> list[str]:
    """Names of the folders under outputs/walkforward/ that hold a scores.csv (rungs and fixed variants, e.g. M1, M3_d2,
    M0_L13), sorted: the models --model accepts and --all backtests (decision S32-1)."""
    base = ROOT / "outputs" / "walkforward"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir()
                  if p.is_dir() and MODEL_NAME.fullmatch(p.name) and (p / "scores.csv").exists())


def check_model(model: str) -> None:
    """Stop unless `model` is a plain name (letters, digits, underscores, single inner dots: MODEL_NAME) with walk-forward
    scores."""
    if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
        raise SystemExit(f"--model: {model!r} is not a model name (letters, digits, underscores and single inner dots)")
    available = walkforward_models()
    if model not in available:
        raise SystemExit(f"--model {model}: no outputs/walkforward/{model}/scores.csv; run 05_train_walkforward.py first "
                         f"(available: {', '.join(available) or 'none'})")


@dataclass(frozen=True)
class InSampleInputs:
    """Real-data inputs shared by the In-Sample backtests of one run (decisions S23-4, S23-8): raw sizing betas through
    the sealed vault (contract 10), the equity calendar, forward returns, realisation dates and periods cut at the
    In-Sample end (contract 7, refuse_oos_returns) and the weekly T-bill (S21-4)."""

    betas: pd.DataFrame
    sessions: pd.DatetimeIndex
    fwd: pd.DataFrame
    realised_on: pd.Series
    period: pd.Series
    rf_weekly: pd.Series


def in_sample_inputs(cfg: dict) -> InSampleInputs:
    """Check the features build (check_used of features_config.yaml), read the betas through the vault and the market
    cut at the In-Sample end; stops before returning if any forward return is realised after it."""
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    check_used(features_settings(cfg), ROOT / cfg["data"]["data_dir"] / "processed" / "features_config.yaml",
               "03_build_features.py")
    betas = read_betas(open_vault(cfg), is_end)
    _, sessions, fwd, realised_on, period = in_sample_market(is_end)
    rf_weekly = tbill_weekly_returns(read_risk_free(cfg, is_end), fwd.index, sessions)
    return InSampleInputs(betas, sessions, fwd, realised_on, period, rf_weekly)


def stats_hook(name: str, *args, **kwargs) -> dict | None:
    """Result of src.stats.<name>(*args, **kwargs), or None while that function is still a Phase 3.1 stub
    (NotImplementedError). Used for the rank IC and the paired block bootstrap (decision S32-3)."""
    try:
        return getattr(stats, name)(*args, **kwargs)
    except NotImplementedError:
        return None


def _baseline(cfg: dict) -> tuple[str, float, float]:
    return next((label, bps, borrow) for label, bps, borrow, is_baseline in cost_scenarios(cfg) if is_baseline)


def _in_sample_only(result) -> None:
    if (result.period != "IS").any():  # unreachable after refuse_oos_returns; kept as a second guard
        raise SystemExit("refused: a backtested week is not In-Sample")


def book_row(result, inputs: InSampleInputs, rf_constant: float) -> dict:
    """Headline figures of one book's net returns (§09, §11): Sharpe with the weekly T-bill and with the constant rf,
    zero-cost Sharpe, gross zero-cost Sharpe, annualised return, max drawdown, mean drifted-weight turnover."""
    weeks = result.net.index
    tbill = performance(result.net, inputs.rf_weekly.loc[weeks])
    return {
        "net_sharpe_rf_tbill": tbill["sharpe_rf"],
        "net_sharpe_rf_constant": performance(result.net, rf_constant)["sharpe_rf"],
        "net_sharpe_zero_cost": tbill["sharpe_zero_cost"],
        "gross_sharpe_zero_cost": performance(result.gross, 0.0)["sharpe_zero_cost"],
        "annualized_return": tbill["annualized_return"],
        "max_drawdown": tbill["max_drawdown"],
        "mean_turnover": float(result.turnover.mean()),
    }


def backtest_model(cfg: dict, model: str, inputs: InSampleInputs | None = None) -> dict:
    """In-Sample backtest of `model`'s walk-forward scores (§09, §11; decisions S23-4 to S23-10, S32-1, S32-2). Writes
    outputs/backtests/<model>/ only after every input has passed its checks; returns the summary."""
    check_model(model)
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    u = universe()

    scores = read_scores(model, cfg, is_end)
    inputs = inputs or in_sample_inputs(cfg)
    betas, fwd, realised_on, period = inputs.betas, inputs.fwd, inputs.realised_on, inputs.period
    rf_constant = float(cfg["metrics"]["risk_free_constant"])

    sizing = size_book(scores, betas, cfg)
    scenarios = cost_scenarios(cfg)
    results = {label: run(sizing, fwd, period, bps, borrow) for label, bps, borrow, _ in scenarios}
    baseline = _baseline(cfg)[0]
    base = results[baseline]
    weeks = base.net.index
    _in_sample_only(base)
    signals = sizing.signals.loc[weeks]
    benchmark = fwd.loc[weeks, u.benchmark]
    rf_tbill = inputs.rf_weekly.loc[weeks]

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
    weekly["long_exposure"] = base.weights.clip(lower=0).sum(axis=1)  # Σ w > 0, IVV included (S32-2)
    weekly["short_exposure"] = base.weights.clip(upper=0).sum(axis=1)
    weekly["cap_binds"] = sizing.cap_binds.loc[weeks]
    weekly["rf"] = rf_tbill
    for label, *_, is_baseline in scenarios:
        if not is_baseline:
            weekly[f"net_{label}"] = results[label].net

    summary = {
        "model": model, "spec_hash": expected_spec_hash(model, cfg), "period": "IS", "baseline": baseline,
        "weeks": len(weeks),
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
    save_used(backtest_used(cfg, model), out / "used.yaml")
    _write_json(summary, out / "summary.json")
    return summary


def backtest_used(cfg: dict, model: str) -> dict:
    """used.yaml of outputs/backtests/<model>/ (S23-10), which 07_evaluate.py checks."""
    return used_settings(cfg) | walkforward_settings(cfg) | {"model": model}


def _write_json(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2, default=lambda value: value.item() if hasattr(value, "item") else str(value))
        f.write("\n")


def run_model(cfg: dict, model: str, inputs: InSampleInputs | None = None) -> None:
    summary = backtest_model(cfg, model, inputs)
    out = (ROOT / "outputs" / "backtests" / model).relative_to(ROOT).as_posix()
    print(f"{model} In-Sample backtest: {summary['weeks']} weeks, {summary['first_week']} to {summary['last_week']} "
          f"(realised {summary['first_realised_on']} to {summary['last_realised_on']}) -> {out}")
    table = pd.DataFrame(summary["scenarios"]).T
    print(table.to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"mean |residual beta| {summary['mean_abs_residual_beta']:.4f}; cap-binding weeks {summary['cap_binding_weeks']}; "
          f"missing-input weeks {summary['missing_input_weeks']}; T-bill average {summary['rf_tbill_annual']:.4%}")


def run_all(cfg: dict) -> None:
    """--all: backtest every model of walkforward_models(), with the inputs read once."""
    models = walkforward_models()
    if not models:
        raise SystemExit("--all: no outputs/walkforward/<model>/scores.csv; run 05_train_walkforward.py first")
    for model in models:  # every score file is checked before any real-data input is read
        read_scores(model, cfg, pd.Timestamp(cfg["split"]["in_sample_end"]))
    inputs = in_sample_inputs(cfg)
    for model in models:
        run_model(cfg, model, inputs)
        print()


# -- §12 one-week-shift check (decision S32-3) ----------------------------------------------------------------------------

BOOTSTRAP_P_KEY = "p_uplift_positive"  # key of P(uplift > 0) in the result of src.stats.paired_block_bootstrap (S32-3)
RANK_IC_MEAN_KEY = "mean"  # key of the mean weekly rank IC in the result of src.stats.rank_ic (S32-3)


def delayed_scores(scores: pd.DataFrame, weekly_index: pd.MultiIndex, weeks: int = 1) -> pd.DataFrame:
    """Scores delayed by `weeks` rows of the full weekly index: row t holds the scores of week t − weeks, so the book of
    week t trades the sector signals of week t − weeks (§12 shift check). Rows of `scores.index` whose delayed week has no
    score are NaN (a missing input, Amendment 2 C3); the first `weeks` scored weeks are dropped."""
    if weeks < 1:
        raise ValueError("weeks must be >= 1")
    if not scores.index.isin(weekly_index).all():
        raise ValueError("the scores hold weeks outside the weekly index")
    shifted = scores.reindex(weekly_index).shift(weeks).reindex(scores.index)
    return shifted.iloc[weeks:]


def shift_verdict(base_sharpe: float, delayed_sharpe: float, p_delayed_better: float | None, threshold: float) -> str:
    """S32-3: FAIL only if the delayed book has the higher net Sharpe AND the paired bootstrap gives
    P(delayed > base) >= threshold (selection.bootstrap_prob, 0.80); PENDING if it is higher but the bootstrap is not
    available yet; otherwise PASS."""
    if not delayed_sharpe > base_sharpe:
        return "PASS"
    if p_delayed_better is None:
        return "PENDING"
    return "FAIL" if p_delayed_better >= threshold else "PASS"


def shift_check(cfg: dict, model: str, inputs: InSampleInputs | None = None) -> dict:
    """§12 leakage check on `model` (any walk-forward folder): its book with the sector signals delayed one extra week
    (hedge re-sized from week t's BETA52, baseline costs) against the book itself, on their common weeks. Writes
    outputs/diagnostics/shift/<model>/ (summary.json, weekly.csv of the two net series, used.yaml); returns the summary."""
    check_model(model)
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    scores = read_scores(model, cfg, is_end)
    inputs = inputs or in_sample_inputs(cfg)
    label, bps, borrow = _baseline(cfg)
    rf_constant = float(cfg["metrics"]["risk_free_constant"])
    sectors = list(universe().sectors)
    books = {"base": scores, "delayed": delayed_scores(scores, inputs.fwd.index)}
    results = {name: run(size_book(book, inputs.betas, cfg), inputs.fwd, inputs.period, bps, borrow)
               for name, book in books.items()}
    for result in results.values():
        _in_sample_only(result)
    common = results["base"].net.index[results["base"].net.index.isin(results["delayed"].net.index)]
    trimmed = {name: _restrict(result, common) for name, result in results.items()}

    rows = {}
    for name, result in trimmed.items():
        ic = stats_hook("rank_ic", books[name].reindex(common), inputs.fwd.loc[common, sectors])
        rows[name] = book_row(result, inputs, rf_constant) | {
            "rank_ic_mean": None if ic is None else ic.get(RANK_IC_MEAN_KEY), "rank_ic": ic}
    selection = cfg["selection"]
    # the gate's Sharpe: the §09 headline with the weekly T-bill over the same weeks (Amendment 6 C1, S32-9)
    boot = stats_hook("paired_block_bootstrap", trimmed["delayed"].net, trimmed["base"].net,
                      n_resamples=selection["bootstrap_resamples"], block=selection["bootstrap_block"], seed=cfg["seed"],
                      rf=inputs.rf_weekly.loc[common])
    if boot is not None and BOOTSTRAP_P_KEY not in boot:
        raise SystemExit(f"src.stats.paired_block_bootstrap returned no {BOOTSTRAP_P_KEY!r} (keys {sorted(boot)}); "
                         "update BOOTSTRAP_P_KEY in 06_backtest.py (decision S32-3)")
    p_better = None if boot is None else float(boot[BOOTSTRAP_P_KEY])
    verdict = shift_verdict(rows["base"]["net_sharpe_rf_tbill"], rows["delayed"]["net_sharpe_rf_tbill"], p_better,
                            float(selection["bootstrap_prob"]))
    summary = {
        "model": model, "period": "IS", "baseline": label, "delay_weeks": 1, "weeks": len(common),
        "first_week": _week(_closes(common)[0]), "last_week": _week(_closes(common)[-1]),
        "base": rows["base"], "delayed": rows["delayed"],
        "sharpe_difference_delayed_minus_base": rows["delayed"]["net_sharpe_rf_tbill"] - rows["base"]["net_sharpe_rf_tbill"],
        "bootstrap": boot, "p_delayed_better": p_better, "threshold": float(selection["bootstrap_prob"]),
        "verdict": verdict,
    }
    out = ROOT / "outputs" / "diagnostics" / "shift" / model
    weekly = pd.DataFrame({"realised_on": inputs.realised_on.loc[common], "net_base": trimmed["base"].net,
                           "net_delayed": trimmed["delayed"].net})
    write_csv(weekly, out / "weekly.csv")
    save_used(backtest_used(cfg, model), out / "used.yaml")
    _write_json(summary, out / "summary.json")
    return summary


def _restrict(result, weeks: pd.Index):
    """Net, gross and turnover of a BacktestResult on a subset of its weeks (the book itself is not re-run)."""
    return SimpleNamespace(net=result.net.loc[weeks], gross=result.gross.loc[weeks], turnover=result.turnover.loc[weeks])


def run_shift_check(cfg: dict, models: list[str]) -> None:
    models = models or ["M0"]
    for model in models:  # every score file is checked before any real-data input is read
        check_model(model)
        read_scores(model, cfg, pd.Timestamp(cfg["split"]["in_sample_end"]))
    inputs = in_sample_inputs(cfg)
    for model in models:
        s = shift_check(cfg, model, inputs)
        p = "n/a (src.stats.paired_block_bootstrap pending, Phase 3.1)" if s["p_delayed_better"] is None \
            else f"{s['p_delayed_better']:.3f}"
        print(f"{model} one-week-shift check, {s['weeks']} common weeks {s['first_week']} to {s['last_week']}, "
              f"{s['baseline']}:")
        table = pd.DataFrame({k: {c: v for c, v in s[k].items() if c != "rank_ic"} for k in ("base", "delayed")})
        print(table.to_string(float_format=lambda x: f"{x:.4f}"))
        print(f"P(delayed > base) {p}; verdict {s['verdict']}")
        print()


# -- §11 placebo: random ±2/±2 books with the same hedge (decision S32-4) -------------------------------------------------

def placebo_settings(cfg: dict) -> dict:
    """The placebo section of config.yaml, checked: a positive int `books` and a non-negative int `seed_offset`."""
    if "placebo" not in cfg:
        raise SystemExit("config.yaml has no placebo: section (books, seed_offset)")
    placebo = cfg["placebo"]
    for key, low in (("books", 1), ("seed_offset", 0)):
        value = placebo.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < low:
            raise SystemExit(f"placebo.{key} must be an int >= {low}, got {value!r}")
    return {"books": placebo["books"], "seed_offset": placebo["seed_offset"]}


def placebo_seeds(cfg: dict) -> list[int]:
    """Seed of book i (0-based): seed + placebo.seed_offset + i (S32-4)."""
    settings = placebo_settings(cfg)
    return [cfg["seed"] + settings["seed_offset"] + i for i in range(settings["books"])]


def placebo_percentile(values: pd.Series, x: float) -> float:
    """Percentile of x in the placebo distribution: 100 · (#{v < x} + ½ #{v = x}) / n."""
    v = values.dropna().to_numpy(dtype=np.float64)
    return float(100 * ((v < x).sum() + 0.5 * (v == x).sum()) / len(v))


def run_placebo(cfg: dict, reference: str = "M0", inputs: InSampleInputs | None = None) -> dict:
    """§11 placebo: placebo.books random ±2/±2 books (seeded random sector scores through the same signal rule, hedge,
    sizing and baseline costs) on the scored weeks of `reference`, and the reference model's percentile in the
    distribution of net Sharpe (T-bill). Writes outputs/diagnostics/placebo/ (books.csv, summary.json, used.yaml)."""
    check_model(reference)
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    seeds = placebo_seeds(cfg)
    scores = read_scores(reference, cfg, is_end)
    inputs = inputs or in_sample_inputs(cfg)
    label, bps, borrow = _baseline(cfg)
    rf_constant = float(cfg["metrics"]["risk_free_constant"])

    ref = run(size_book(scores, inputs.betas, cfg), inputs.fwd, inputs.period, bps, borrow)
    _in_sample_only(ref)
    rows = []
    for book, seed in enumerate(seeds):
        result = run(size_book(random_scores(scores.index, seed), inputs.betas, cfg), inputs.fwd, inputs.period, bps, borrow)
        _in_sample_only(result)
        if not result.net.index.equals(ref.net.index):
            raise SystemExit(f"placebo book {book} is not on the weeks of {reference}")
        rows.append({"book": book, "seed": seed} | book_row(result, inputs, rf_constant))
    table = pd.DataFrame(rows).set_index("book")
    ref_row = book_row(ref, inputs, rf_constant)
    sharpe = table["net_sharpe_rf_tbill"]
    weeks = ref.net.index
    summary = {
        "reference": reference, "period": "IS", "baseline": label, "books": len(table), "weeks": len(weeks),
        "first_week": _week(_closes(weeks)[0]), "last_week": _week(_closes(weeks)[-1]),
        "seed_first": seeds[0], "seed_last": seeds[-1],
        "net_sharpe_rf_tbill": {"mean": float(sharpe.mean()), "std": float(sharpe.std()),
                                **{f"q{int(q * 100):02d}": float(sharpe.quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}},
        "mean_turnover": float(table["mean_turnover"].mean()),
        "reference_row": ref_row,
        "reference_percentile": placebo_percentile(sharpe, ref_row["net_sharpe_rf_tbill"]),
        # information only (S32-4): random books trade far more than a model, so the cost-free comparison is shown too
        "reference_percentile_gross": placebo_percentile(table["gross_sharpe_zero_cost"], ref_row["gross_sharpe_zero_cost"]),
        "gross_sharpe_zero_cost": {"mean": float(table["gross_sharpe_zero_cost"].mean()),
                                   "q50": float(table["gross_sharpe_zero_cost"].median())},
    }
    out = ROOT / "outputs" / "diagnostics" / "placebo"
    write_csv(table, out / "books.csv")
    save_used(placebo_used(cfg, reference), out / "used.yaml")
    _write_json(summary, out / "summary.json")
    return summary


def placebo_used(cfg: dict, reference: str) -> dict:
    """used.yaml of outputs/diagnostics/placebo/, which 07_evaluate.py checks."""
    return used_settings(cfg) | walkforward_settings(cfg) | {"placebo": cfg["placebo"], "reference": reference}


def print_placebo(summary: dict) -> None:
    s = summary["net_sharpe_rf_tbill"]
    print(f"placebo: {summary['books']} books on the {summary['weeks']} weeks of {summary['reference']} "
          f"({summary['first_week']} to {summary['last_week']}), {summary['baseline']}, seeds {summary['seed_first']} to "
          f"{summary['seed_last']}")
    print(f"net Sharpe (T-bill): mean {s['mean']:.3f}, sd {s['std']:.3f}, 5% {s['q05']:.3f}, median {s['q50']:.3f}, "
          f"95% {s['q95']:.3f}; mean turnover {summary['mean_turnover']:.3f}")
    print(f"{summary['reference']}: net Sharpe {summary['reference_row']['net_sharpe_rf_tbill']:.3f}, "
          f"percentile {summary['reference_percentile']:.1f}; gross zero-cost Sharpe "
          f"{summary['reference_row']['gross_sharpe_zero_cost']:.3f} vs placebo median "
          f"{summary['gross_sharpe_zero_cost']['q50']:.3f}, percentile {summary['reference_percentile_gross']:.1f}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--model", help="In-Sample backtest of one model's walk-forward scores on real data (e.g. M0, M3_d2)")
    mode.add_argument("--all", action="store_true", help="In-Sample backtest of every folder of outputs/walkforward/")
    mode.add_argument("--shift-check", nargs="*", metavar="MODEL",
                      help="§12 one-week-shift leakage check of the models (default M0)")
    mode.add_argument("--placebo", nargs="?", const="M0", metavar="REFERENCE",
                      help="§11 placebo books on the weeks of REFERENCE (default M0)")
    mode.add_argument("--synthetic", action="store_true", help="run on the shared synthetic market")
    mode.add_argument("--ledger-years", type=int, nargs="*",
                      help="ledger reconciliation on In-Sample years of real data (default: ledger.years)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    if args.model is not None:
        run_model(cfg, args.model)
    elif args.all:
        run_all(cfg)
    elif args.shift_check is not None:
        run_shift_check(cfg, args.shift_check)
    elif args.placebo is not None:
        print_placebo(run_placebo(cfg, args.placebo))
    elif args.synthetic:
        run_synthetic(cfg)
    elif args.ledger_years is not None:
        run_ledger_check(cfg, args.ledger_years)
    else:
        sys.exit("06_backtest.py: choose a mode: --model NAME or --all (real data: walk-forward scores, betas through the "
                 "vault), --shift-check, --placebo, --synthetic or --ledger-years.")


if __name__ == "__main__":
    main()
