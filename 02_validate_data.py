"""Run the QA gates of protocol section 04 on the archived data and write the QA report.

No strategy logic: only data-quality statistics on prices (returns, counts, flags).

Inputs:  data/raw/ (manifest.json, yahoo/, fred/, second_source/ when placed by hand), data/processed/
Outputs: docs/qa_report.md (generated, except the reviewer sign-off section, to be filled by hand)
         data/qa/*.csv (returns, counts and flags only: no price levels)
"""

import json

import pandas as pd

from src import validate
from src.config import ROOT, check_used, data_settings, load_config, tradables
from src.data import adjust_ohlc, file_stem, read_daily, read_weekly, sha256, write_csv

PASS, FAIL = "PASS", "FAIL"
SECOND_SOURCE_OWNER = "Simone"  # workstream A (protocol section 14)
PENDING = f"PENDING (owner: {SECOND_SOURCE_OWNER})"
EVENT_WINDOW = 2  # sessions shown before and after a corporate-action date
QA_FLOAT_FORMAT = "%.10g"  # QA tables are for reading: 10 significant digits

SECOND_SOURCE_FORMAT = """**Expected input.** One CSV file per ticker in `data/raw/second_source/` (git-ignored: licensed data, local and in
the LUISS zip only), named after the ticker (`XLB.csv`, ..., `IVV.csv`, `SPY.csv`), for the 11 tradables. Columns, exactly
and in this order: `date,open,high,low,close,adj_close,volume`. Dates are ISO (`YYYY-MM-DD`), one row per session; prices
in USD per share; `adj_close` may be left empty when the source publishes no adjusted close.

**investing.com exports** are accepted as downloaded ("Historical Data", daily), with this column mapping
(`src/validate.py: read_second_source`): `Date` (MM/DD/YYYY) -> `date`; `Price` -> `close`; `Open` -> `open`; `High` ->
`high`; `Low` -> `low`; `Vol.` (K/M/B suffixes) -> `volume`; `Change %` dropped; `adj_close` empty. Thousands separators
are removed and rows are sorted by date.

**Check.** Close-to-close returns of the second source's `close` (and `adj_close` when given) against Yahoo's adjusted
and split-only closes, on the 20 sampled dates (`qa.second_source_dates`, seed `seed`); PASS if the best-matching
convention differs by at most `qa.second_source_tol` (10 bps) on every comparison. The gate reads PENDING until all
11 files are present."""


class Report:
    """Collects the gate results, the CSV tables and the markdown sections of the QA report."""

    def __init__(self, qa_dir):
        self.qa_dir, self.gates, self.sections = qa_dir, [], []

    def gate(self, gate: str, status: str, detail: str) -> None:
        self.gates.append({"gate": gate, "status": status, "detail": detail})
        print(f"[{status}] {gate} - {detail}")

    def section(self, title: str, text: str) -> None:
        self.sections.append(f"## {title}\n\n{text.strip()}\n")

    def table(self, name: str, table: pd.DataFrame) -> str:
        """Save a QA table as data/qa/<name>.csv and return a pointer for the report."""
        write_csv(table, self.qa_dir / f"{name}.csv", float_format=QA_FLOAT_FORMAT)
        return f"Table: `data/qa/{name}.csv` ({len(table)} rows)."


def markdown(table: pd.DataFrame, floats: str = "{:.4f}") -> str:
    """A small markdown table writer (no extra dependency)."""
    if table.empty:
        return "_none_"
    table = table.reset_index() if table.index.name or isinstance(table.index, pd.MultiIndex) else table

    def cell(value) -> str:
        if isinstance(value, pd.Timestamp):
            return str(value.date())
        if isinstance(value, float):
            return "n/a" if pd.isna(value) else floats.format(value)
        return str(value)

    lines = ["| " + " | ".join(map(str, table.columns)) + " |", "|" + " --- |" * len(table.columns)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in table.itertuples(index=False)]
    return "\n".join(lines)


def daily_returns(prices: pd.Series) -> pd.Series:
    """Session-to-session return of a price series on its own sessions."""
    return prices.dropna().pct_change()


def main() -> None:
    cfg = load_config()
    data_dir = ROOT / cfg["data"]["data_dir"]
    raw_dir, processed_dir, qa_dir = data_dir / "raw", data_dir / "processed", data_dir / "qa"
    check_used(data_settings(cfg), raw_dir / "config.yaml", "01_download_data.py")
    check_used(data_settings(cfg), processed_dir / "config.yaml", "01_download_data.py")
    qa = cfg["qa"]
    with open(raw_dir / "manifest.json", encoding="utf-8") as f:
        manifest = json.load(f)

    names, vix, spy = tradables(cfg), cfg["data"]["vix"], cfg["data"]["benchmark"]
    scored_from = pd.Timestamp(cfg["split"]["warmup_end"]) + pd.Timedelta(days=1)
    is_end, end = pd.Timestamp(cfg["split"]["in_sample_end"]), pd.Timestamp(cfg["data"]["end"])
    raw = {t: read_daily(raw_dir / "yahoo" / f"{file_stem(t)}.csv").astype("float64") for t in names + [vix]}
    adjusted = {t: adjust_ohlc(raw[t]) for t in names}
    fred = {s: read_daily(raw_dir / "fred" / f"{s}.csv")[s].astype("float64") for s in cfg["data"]["fred"]}
    second_dir = raw_dir / "second_source"
    second = {t: validate.read_second_source(path) for t in names if (path := second_dir / f"{file_stem(t)}.csv").exists()}
    sessions = pd.DatetimeIndex(sorted(set().union(*(raw[t].index for t in names))))

    adj_close = pd.DataFrame({t: adjusted[t]["Close"] for t in names})
    adj_open = pd.DataFrame({t: adjusted[t]["Open"] for t in names})
    returns_close = pd.DataFrame({t: daily_returns(adj_close[t]) for t in names})
    returns_open = pd.DataFrame({t: daily_returns(adj_open[t]) for t in names})
    # Duplicated second-source dates are reported by the duplicate-date gate; the first row is used for the comparisons.
    second_close = {t: second[t]["close"][~second[t].index.duplicated()] for t in second}
    second_returns = pd.DataFrame({t: daily_returns(second_close[t]) for t in second}, index=sessions)

    report = Report(qa_dir)

    # 1. Raw files frozen with SHA-256, source and fetch time
    problems = []
    for name, entry in manifest["files"].items():
        if not (ROOT / name).exists() or sha256(ROOT / name) != entry["sha256"]:
            problems.append(f"{name}: missing or SHA-256 mismatch")
        if not entry.get("source") or not entry.get("fetched_utc") or not (entry.get("call") or entry.get("url")):
            problems.append(f"{name}: source, call/URL or fetch time missing")
    report.gate("Raw files frozen (SHA-256, source, fetch time)", FAIL if problems else PASS,
                "; ".join(problems) or f"{len(manifest['files'])} files verified against data/raw/manifest.json")
    files = pd.DataFrame([{"file": n, "source": e["source"], "fetched_utc": e["fetched_utc"], "rows": e["rows"],
                           "first_date": e["first_date"], "last_date": e["last_date"], "sha256": e["sha256"]}
                          for n, e in manifest["files"].items()])
    report.section("Raw files", f"Snapshot through {manifest['snapshot_end']}, downloaded {manifest['created_utc']} "
                   f"(yfinance {manifest['versions']['python-yfinance']}, pandas {manifest['versions']['pandas']}).\n\n"
                   + markdown(files.drop(columns="sha256")) + "\n\nSHA-256 of every file: `data/checksums.json`.")

    # 2. One row per ticker per session; monotonic dates; no duplicates
    rows, all_raw = [], {f"yahoo/{file_stem(t)}": raw[t] for t in raw} | {f"fred/{s}": fred[s].to_frame() for s in fred}
    all_raw |= {f"second_source/{file_stem(t)}": second[t] for t in second}
    for name, frame in all_raw.items():
        rows.append({"file": name, "duplicates": len(validate.duplicate_dates(frame.index)),
                     "non_monotonic": len(validate.non_monotonic_dates(frame.index)),
                     "weekend_dates": len(validate.weekend_dates(frame.index))})
    order = pd.DataFrame(rows)
    report.gate("Monotonic dates", PASS if order["non_monotonic"].sum() == 0 else FAIL,
                f"{order['non_monotonic'].sum()} out-of-order dates in {len(order)} raw files")
    report.gate("No duplicate dates", PASS if order["duplicates"].sum() == 0 else FAIL,
                f"{order['duplicates'].sum()} duplicated dates in {len(order)} raw files")

    calendar = []
    for t in names + [vix]:
        missing, extra = validate.session_gaps(raw[t].index, sessions)
        calendar.append({"ticker": t, "rows": len(raw[t]), "first_date": raw[t].index.min(), "last_date": raw[t].index.max(),
                         "missing_sessions": len(missing), "dates_outside_equity_calendar": len(extra),
                         "weekend_dates": len(validate.weekend_dates(raw[t].index))})
    calendar = pd.DataFrame(calendar).set_index("ticker")
    vix_only = raw[vix].index.difference(sessions)
    one_row = (calendar[["missing_sessions", "weekend_dates"]].sum().sum() == 0
               and calendar.loc[names, "dates_outside_equity_calendar"].sum() == 0)
    report.gate("One row per ticker per session", PASS if one_row else FAIL,
                f"equity calendar = union of the {len(names)} tradables' dates ({len(sessions)} sessions); "
                f"missing sessions {int(calendar['missing_sessions'].sum())}; {vix}-only dates {len(vix_only)} (listed, allowed)")
    report.section("Calendar, order and duplicates",
                   "The equity calendar is the union of the session dates of the tradables (9 sectors, IVV, SPY). "
                   f"Each ticker is checked from its own first date. {vix} is checked on the equity calendar; the dates "
                   f"where only {vix} has data are US market holidays on which Cboe published VIX: "
                   f"{', '.join(str(d.date()) for d in vix_only) or 'none'}. They stay in the raw file and are not equity sessions.\n\n"
                   + markdown(calendar) + "\n\n" + markdown(order) + "\n\n"
                   + report.table("calendar", calendar) + " " + report.table("raw_file_order", order.set_index("file")))
    report.table("vix_only_dates", pd.DataFrame({"date": vix_only}).set_index("date"))

    # 3. Positive prices
    price_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    bad = {t: len(validate.non_positive_prices(raw[t], price_columns)) for t in names + [vix]}
    bad |= {f"second_source/{t}": len(validate.non_positive_prices(second[t], ["open", "high", "low", "close"]))
            for t in second}
    report.gate("Positive prices", PASS if sum(bad.values()) == 0 else FAIL,
                f"{sum(bad.values())} rows with a zero or negative Open/High/Low/Close/Adj Close")
    inconsistent = {t: int(((raw[t]["Low"] > raw[t][["Open", "Close"]].min(axis=1) + 1e-9)
                            | (raw[t]["High"] < raw[t][["Open", "Close"]].max(axis=1) - 1e-9)).sum()) for t in names}

    # 4. No forward-filled tradable prices (scored window); warm-up rows reported
    stale_rows = []
    for t in names:
        stale = validate.stale_sessions(raw[t])
        stale_rows += [{"date": d, "ticker": t, "repeated_ohlc": bool(r.repeated_ohlc), "zero_volume": bool(r.zero_volume),
                        "window": "scored" if d >= scored_from else "warm-up"} for d, r in stale.iterrows()]
    stale = pd.DataFrame(stale_rows, columns=["date", "ticker", "repeated_ohlc", "zero_volume", "window"])
    in_scored = int((stale["window"] == "scored").sum())
    report.gate("No forward-filled tradable prices", PASS if in_scored == 0 else FAIL,
                f"{in_scored} stale sessions (OHLC equal to the previous session's, or zero volume) from {scored_from.date()}; "
                f"{len(stale) - in_scored} in the warm-up (reported)")
    report.section("Forward-filled prices and bar consistency",
                   "A session is flagged as stale if its Open, High, Low and Close all equal the previous session's, or if its "
                   "volume is zero. The gate applies to the tradable prices of the scored window; flags in the warm-up are "
                   "listed because warm-up prices only feed feature windows.\n\n" + markdown(stale.set_index("date"))
                   + "\n\n" + report.table("stale_sessions", stale.set_index("date"))
                   + f"\n\nInformation only: raw bars with Low above min(Open, Close) or High below max(Open, Close): {inconsistent}.")

    # 5. Daily moves above the threshold, for manual review
    def move_table(returns: pd.DataFrame) -> pd.DataFrame:
        flagged = returns.where(returns.abs() > qa["big_move"]).stack().dropna().rename("return")
        table = flagged.rename_axis(["date", "ticker"]).reset_index()
        table["spy_return"] = returns[spy].reindex(table["date"]).to_numpy()
        table["second_source_return"] = [second_returns[t].get(d, float("nan")) if t in second_returns else float("nan")
                                 for d, t in zip(table["date"], table["ticker"])]
        return table.set_index("date")

    big_close, big_open = move_table(returns_close), move_table(returns_open)
    split_like = {t: len(validate.split_like_moves(adj_close[t].dropna(), qa["split_tolerance"]))
                  + len(validate.split_like_moves(adj_open[t].dropna(), qa["split_tolerance"])) for t in names}
    report.gate(f"Daily moves above {qa['big_move']:.0%} listed for review", PASS if sum(split_like.values()) == 0 else FAIL,
                f"{len(big_close)} close-to-close and {len(big_open)} open-to-open moves listed; split-like moves in "
                f"adjusted prices: {sum(split_like.values())} (manual review pending)")
    report.section(f"Daily moves above {qa['big_move']:.0%}",
                   "Adjusted close-to-close returns, with SPY's return on the same day and the second source's return when "
                   "available. Automated part of the gate: no move in the adjusted closes or opens has a price ratio within "
                   f"{qa['split_tolerance']:.0%} of a split ratio (2, 3, 4, 5, 10 or their inverses). The economic review of "
                   "each move is in the reviewer sign-off below.\n\n"
                   + markdown(big_close) + "\n\n" + report.table("big_moves_close", big_close)
                   + "\n\nOpen-to-open moves (the execution prices): " + report.table("big_moves_open", big_open))

    # 6. Corporate-action dates: splits, and the XLF distribution booked as a split factor
    events = [(d, t, raw[t].loc[d, "Stock Splits"]) for t in names for d in raw[t].index[raw[t]["Stock Splits"] > 0]]
    windows = []
    for day, t, factor in events:
        position = sessions.get_loc(day)
        for s in sessions[max(position - EVENT_WINDOW, 1): position + EVENT_WINDOW + 1]:
            windows.append({"date": s, "event": f"{t} {day.date()}", "factor": factor,
                            "adj_close_to_close": returns_close[t].get(s), "adj_open_to_open": returns_open[t].get(s),
                            "yahoo_close_to_close": daily_returns(raw[t]["Close"]).get(s),
                            "yahoo_open_to_open": daily_returns(raw[t]["Open"]).get(s),
                            "spy_close_to_close": returns_close[spy].get(s),
                            "second_source_close_to_close": second_returns[t].get(s) if t in second_returns
                            else float("nan")})
    windows = pd.DataFrame(windows).set_index("date")
    columns = ["adj_close_to_close", "adj_open_to_open", "yahoo_close_to_close", "yahoo_open_to_open"]
    worst = windows.set_index("event")[columns].abs().max(axis=1).groupby(level=0).max()
    factor = windows.groupby("event")["factor"].first()
    for kind, chosen in [("2:1 splits", factor.index[factor == 2]), ("other split factors", factor.index[factor != 2])]:
        largest = worst.loc[chosen].max() if len(chosen) else float("nan")
        report.gate(f"Corporate actions: {kind}", PASS if len(chosen) and largest < qa["big_move"] else FAIL,
                    f"{', '.join(f'{e} ({factor[e]:g})' for e in chosen) or 'no event found'}; largest |return| within "
                    f"+/-{EVENT_WINDOW} sessions, adjusted and Yahoo open/close: {largest:.2%} (an unadjusted event would "
                    f"be about {1 / factor.loc[chosen].max() - 1:.0%})" if len(chosen) else "no event found")
    report.section("Corporate-action dates",
                   "Every date with a Yahoo split factor: the 2:1 splits of 5 Dec 2025 and the real-estate distribution of "
                   "19 Sep 2016, which Yahoo books for XLF as a split factor of 1.231. Returns of the event ticker within "
                   f"±{EVENT_WINDOW} sessions: adjusted (our series), Yahoo's Close and Open with auto_adjust=False, SPY, and the "
                   "second source. PASS if no return in the window exceeds the big-move threshold in absolute value: an "
                   "unadjusted split or distribution would show as a drop of about 50% or 19%.\n\n"
                   + markdown(windows) + "\n\n" + report.table("corporate_action_windows", windows))

    # 7. Adjusted versus raw: dividends and capital gains reconcile the adjustment factor
    recon = []
    for t in names:
        result = validate.adjustment_reconciliation(raw[t])
        result |= {"capital_gain_events": int((raw[t].get("Capital Gains", pd.Series(0.0)).fillna(0) > 0).sum()),
                   "annual_gap_adjusted_minus_raw": validate.annual_gap(raw[t]["Adj Close"], raw[t]["Close"]),
                   "implied_annual_distribution_yield": validate.distribution_yield(raw[t])}
        recon.append({"ticker": t} | result)
    recon = pd.DataFrame(recon).set_index("ticker")
    low, high = qa["dividend_yield_band"]
    ok = ((recon["total_gap"].abs() <= qa["reconciliation_total_tol"])
          & (recon["max_unexplained_step"] <= qa["reconciliation_step_tol"])
          & recon["annual_gap_adjusted_minus_raw"].between(low, high, inclusive="neither"))
    report.gate("Adjusted returns reconciled to dividends and splits", PASS if ok.all() else FAIL,
                f"{int(ok.sum())}/{len(ok)} tickers: |total gap| <= {qa['reconciliation_total_tol']}, unexplained daily step "
                f"<= {qa['reconciliation_step_tol']}, annual gap in ({low:.1%}, {high:.0%})"
                + ("" if ok.all() else f"; failing: {list(ok.index[~ok])}"))
    report.section("Adjusted versus raw reconciliation",
                   "With f = Adj Close / Close, a distribution D (dividend plus capital gain) with ex-date t should give "
                   "f(t-1) / f(t) = 1 - D / Close(t-1), and f should not move on other days. `total_gap` compares the log of "
                   "the whole adjustment with the sum of the log distribution factors; `max_unexplained_step` is the largest "
                   "move of f on a day without a distribution. Splits do not enter f, because Yahoo's Close is already "
                   "split-adjusted (see the corporate-action dates). The annual gap is the adjusted minus the raw annualised "
                   "return; the implied distribution yield is the average annual sum of D / Close(t-1).\n\n"
                   + markdown(recon) + "\n\n" + report.table("reconciliation", recon))

    # 8. Second source: 20 sampled dates (files placed by hand in data/raw/second_source/)
    gate_name = f"{qa['second_source_dates']} sampled dates checked against the second source"
    missing = [t for t in names if t not in second]
    stooq_failures = manifest.get("unavailable", {}).get("stooq", {})
    reasons = sorted({u["reason"].split(" (first bytes")[0] for u in stooq_failures.values()})
    history = (f"The automatic Stooq download of `01_download_data.py` failed for all {len(stooq_failures)} tickers "
               f"({'; '.join(reasons)}): the CSV endpoint now answers with an HTML page and a JavaScript verification "
               "page, which was not bypassed. " if stooq_failures else "")
    if not second:
        report.gate(gate_name, PENDING, f"no files in data/raw/second_source/ yet; {len(names)} tickers expected")
        result_text = "Not run yet: no file in `data/raw/second_source/`."
    else:
        window = sessions[(sessions >= scored_from) & (sessions <= end)]
        dates = validate.sample_dates(window, qa["second_source_dates"], cfg["seed"])
        unique = {t: second[t][~second[t].index.duplicated()] for t in second}
        comparison = pd.concat([validate.compare_second_source(adj_close[t], raw[t]["Close"], unique[t], dates).assign(ticker=t)
                                for t in second])
        comparison = comparison.dropna(subset=["difference"])
        error = comparison.groupby(["yahoo", "second_series"])["difference"].apply(lambda d: d.abs().max())
        convention = error.idxmin() if len(error) else ("none", "none")
        worst = error[convention] if len(error) else float("nan")
        used = (comparison["yahoo"] == convention[0]) & (comparison["second_series"] == convention[1])
        per_ticker = comparison[used].groupby("ticker").size().reindex(list(second), fill_value=0)
        short = list(per_ticker.index[per_ticker < qa["second_source_dates"]])  # every sampled date must be compared
        failed = not len(error) or worst > qa["second_source_tol"] or bool(short)
        status = FAIL if failed else (PENDING if missing else PASS)
        report.gate(gate_name, status,
                    f"{len(second)}/{len(names)} tickers; second-source {convention[1]} matches Yahoo's {convention[0]} "
                    f"series; max |return difference| {worst:.4%} over {int(used.sum())} comparisons"
                    + (f"; fewer than {qa['second_source_dates']} comparisons for {short}" if short else "")
                    + (f"; missing files: {missing}" if missing else ""))
        files = pd.DataFrame([{"file": f"data/raw/second_source/{file_stem(t)}.csv", "rows": len(second[t]),
                               "sha256": sha256(second_dir / f"{file_stem(t)}.csv")} for t in second])
        result_text = (f"Close-to-close returns, not price levels, on dates sampled with seed {cfg['seed']} from the scored "
                       "window. The convention used is the pairing with the smallest maximum |difference|.\n\n"
                       + markdown(error.to_frame()) + "\n\n" + report.table("second_source", comparison)
                       + "\n\nSecond-source files used (SHA-256):\n\n" + markdown(files))
    report.section("Second source", history + f"Owner: {SECOND_SOURCE_OWNER}. " + result_text + "\n\n" + SECOND_SOURCE_FORMAT)

    # 9. Coverage audit per ticker (scored window, processed tables)
    daily_open, daily_close = read_daily(processed_dir / "daily_open.csv"), read_daily(processed_dir / "daily_close.csv")
    market = read_daily(processed_dir / "daily_market.csv")
    coverage = []
    for t in names:
        start = max(scored_from, raw[t].index.min())
        in_window = (daily_close.index >= start) & (daily_close.index <= end)
        coverage.append({"ticker": t, "first_date": raw[t].index.min(), "last_date": raw[t].index.max(),
                         "scored_from": start, "sessions": int(in_window.sum()),
                         "missing_opens": int(daily_open.loc[in_window, t].isna().sum()),
                         "missing_closes": int(daily_close.loc[in_window, t].isna().sum())})
    coverage = pd.DataFrame(coverage).set_index("ticker")
    market_missing = market.isna().sum()
    complete = coverage[["missing_opens", "missing_closes"]].sum().sum() == 0 and market_missing.sum() == 0
    covered = (coverage["last_date"] == end).all() and (calendar.loc[names, "first_date"] <= scored_from).all()
    report.gate("Coverage audit per ticker", PASS if complete and covered else FAIL,
                f"missing opens/closes in the scored window: {int(coverage[['missing_opens', 'missing_closes']].sum().sum())}; "
                f"sessions without VIX or a lagged FRED value: {market_missing.to_dict()}; every ticker from before "
                f"{scored_from.date()} to {end.date()}")
    fred_last = {s: str(fred[s].dropna().index.max().date()) for s in fred}
    report.section("Coverage audit",
                   "Fixed ETF universe existing since 1998-2000 (survivorship bias avoided by construction, protocol section 12). "
                   "Missing values counted on the equity calendar of the scored window, each ticker from its own first date, "
                   "in the processed tables. FRED values are aligned with a one-day lag: a value observed for day d is first "
                   f"used on the first session after d. Last FRED observations in the snapshot: {fred_last}.\n\n"
                   + markdown(coverage) + "\n\n" + report.table("coverage", coverage))

    # 10. Weekly panel and scored weeks
    weekly_open, weekly_close = read_weekly(processed_dir / "weekly_open.csv"), read_weekly(processed_dir / "weekly_close.csv")
    date_open = weekly_close.index.get_level_values("date_open")
    date_close = weekly_close.index.get_level_values("date_close")
    first_session = pd.Series(sessions, index=sessions).resample("W-FRI").first().reindex(date_close)
    realised = pd.Series(first_session.shift(-2).to_numpy(), index=weekly_close.index)  # open of week t+2
    scored = date_close >= scored_from
    evaluable = scored & realised.notna().to_numpy()
    in_sample = evaluable & (realised <= is_end).to_numpy()
    oos = evaluable & (realised > is_end).to_numpy()
    shape_ok = ((date_open.day_name() == "Monday").all() and (date_close.day_name() == "Friday").all()
                and date_close.max() == end and weekly_open.equals(weekly_open.loc[weekly_close.index]))
    gaps = int(weekly_open.loc[scored, names].isna().sum().sum() + weekly_close.loc[scored, names].isna().sum().sum())
    counts = pd.DataFrame([
        {"count": "weeks in the panel", "value": len(weekly_close)},
        {"count": "scored signal weeks (date_close from the first scored week)", "value": int(scored.sum())},
        {"count": "In-Sample, by realisation date of the return (open of week t+2 <= in_sample_end)", "value": int(in_sample.sum())},
        {"count": "Out-of-Sample, by realisation date of the return", "value": int(oos.sum())},
        {"count": "scored weeks without a return in the data (last two weeks)", "value": int((scored & ~evaluable).sum())},
        {"count": "In-Sample, by week close (smoke-test definition)", "value": int((scored & (date_close <= is_end)).sum())},
        {"count": "Out-of-Sample, by week close (smoke-test definition)", "value": int((date_close > is_end).sum())},
    ]).set_index("count")
    first_oos = realised[oos].iloc[0]
    last_signal = date_close[evaluable].max()
    report.gate("Weekly panel", PASS if shape_ok and gaps == 0 else FAIL,
                f"(Monday, Friday) index through {date_close.max().date()}; {gaps} missing weekly opens/closes in the scored "
                f"window; scored weeks IS {int(in_sample.sum())}, OOS {int(oos.sum())}; first OOS return realised "
                f"{first_oos.date()}; last evaluable signal week ends {last_signal.date()}")
    report.section("Weekly panel and scored weeks",
                   "Weekly open = first adjusted open of the week, weekly close = last adjusted close, indexed by "
                   "(date_open, date_close) = (Monday, Friday). The signal of week t earns O(t+2) / O(t+1) - 1, realised at "
                   "the open of week t+2; a week is In-Sample if that open is on or before the In-Sample end "
                   f"({is_end.date()}), as in the skeleton. First OOS-realised return: open of {first_oos.date()} "
                   f"({first_oos.day_name()}). Last evaluable signal: week ending {last_signal.date()}.\n\n"
                   + markdown(counts, floats="{:.0f}") + "\n\n" + report.table("weekly_counts", counts))

    # 11. Composition breaks logged
    breaks = ROOT / "docs" / "composition_breaks.md"
    text = breaks.read_text(encoding="utf-8") if breaks.exists() else ""
    logged = "2016" in text and "2018" in text
    report.gate("Composition breaks logged", PASS if logged else FAIL,
                "docs/composition_breaks.md records the 2016 and 2018 GICS changes (draft, owner Simone)" if logged
                else "docs/composition_breaks.md missing or incomplete")

    gates = pd.DataFrame(report.gates).set_index("gate")
    report.table("gates", gates)
    write_report(ROOT / "docs" / "qa_report.md", manifest, report, gates)
    print(f"Saved docs/qa_report.md and {len(list(qa_dir.glob('*.csv')))} tables in data/qa/")


def write_report(path, manifest, report: Report, gates: pd.DataFrame) -> None:
    header = (
        "# Data QA report\n\n"
        "Generated by `02_validate_data.py` from the archived raw data (protocol section 04). Do not edit by hand, except "
        "the reviewer sign-off at the end. Tables contain returns, counts and flags only: no price levels.\n\n"
        f"Data snapshot through {manifest['snapshot_end']}; raw files downloaded {manifest['created_utc']}.\n"
    )
    summary = "## Gate summary\n\n" + markdown(gates) + "\n"
    signoff = (
        "## Reviewer sign-off (Simone)\n\n"
        "To be completed by the workstream A owner (protocol section 14).\n\n"
        "- Review of the flagged daily moves above 10%:\n"
        "- Interpretation of the second-source reconciliation:\n"
        "- PASS/FAIL confirmation of each gate:\n"
        "- Signed (name, date):\n"
    )
    content = "\n".join([header] + report.sections + [summary, signoff])
    path.write_bytes(content.encode("utf-8"))


if __name__ == "__main__":
    main()
