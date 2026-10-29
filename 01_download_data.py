"""Download the raw data once, archive it with checksums, and build the processed daily and weekly tables.

Raw data is downloaded only if data/raw/ does not exist (or with --refresh); otherwise the archived files are verified
against their SHA-256 in data/raw/manifest.json and nothing is downloaded, so the LUISS zip reproduces offline.

Outputs (raw, local only):
    data/raw/yahoo/<TICKER>.csv   daily Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits
                                  (and Capital Gains when reported), yfinance with auto_adjust=False, actions=True
    data/raw/fred/<SERIES>.csv    FRED public CSV endpoint
    data/raw/stooq/<TICKER>.csv   second price source, when reachable
    data/raw/manifest.json        source, call or URL, fetch time (UTC), rows, first and last date, SHA-256 per file
    data/raw/config.yaml          the data settings used
Outputs (processed, local only, rebuilt on every run):
    data/processed/daily_{open,high,low,close}.csv   fully adjusted prices of the tradables on the equity calendar
    data/processed/daily_market.csv                  VIX close, FRED series lagged one day, on the equity calendar
    data/processed/weekly_{open,close}.csv           first adjusted open and last adjusted close of each week,
                                                     indexed by (date_open, date_close) = (Monday, Friday)
    data/processed/config.yaml                       the data settings used
Output (committed):
    data/checksums.json   hashes and metadata of every raw and processed file, without the data

Run:  uv run python 01_download_data.py [--refresh]
"""

import argparse
import hashlib
import io
import json
import time
from datetime import UTC, datetime
from importlib.metadata import version

import pandas as pd
import requests
import yfinance as yf

from src.config import ROOT, check_used, data_settings, load_config, save_used, tradables
from src.data import (
    PRICE_FIELDS,
    RAW_FIELDS,
    adjust_ohlc,
    file_stem,
    lag_to_sessions,
    quiet_yfinance_deprecations,
    read_daily,
    sha256,
    weekly_panel,
    write_csv,
)

ATTEMPTS = 5
FIRST_WAIT = 5  # seconds, doubled after each failed attempt
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}.us&i=d"
FRED_LOOKBACK_DAYS = 31  # FRED rows kept before data.start, so the first sessions have a lagged value


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def with_retries(fetch, what: str):
    """Call fetch() until it succeeds, waiting 5, 10, 20, 40 seconds between attempts."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return fetch()
        except Exception as error:
            if attempt == ATTEMPTS:
                raise RuntimeError(f"{what}: failed after {ATTEMPTS} attempts: {error}") from error
            wait = FIRST_WAIT * 2 ** (attempt - 1)
            print(f"{what}: attempt {attempt} failed ({error}); retrying in {wait} s")
            time.sleep(wait)


def describe(path, entry: dict, table: pd.DataFrame) -> dict:
    """Manifest entry of a saved file."""
    dates = table.index.get_level_values(-1) if isinstance(table.index, pd.MultiIndex) else table.index
    return entry | {
        "rows": len(table),
        "first_date": str(dates.min().date()),
        "last_date": str(dates.max().date()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def download_yahoo(cfg: dict, raw_dir) -> dict:
    tickers = tradables(cfg) + [cfg["data"]["vix"]]
    start, end = cfg["data"]["start"], pd.Timestamp(cfg["data"]["end"])
    end_exclusive = str((end + pd.Timedelta(days=1)).date())  # yfinance excludes end
    call = (f"yfinance {version('yfinance')}: yf.download({tickers}, start='{start}', end='{end_exclusive}', "
            "auto_adjust=False, actions=True)")

    def fetch():
        data = yf.download(tickers, start=start, end=end_exclusive, auto_adjust=False, actions=True, progress=False)
        failed = [t for t in tickers if t not in data["Close"].columns or data["Close"][t].isna().all()]
        if failed:
            raise ValueError(f"no prices for {failed}")
        return data

    print(f"Downloading {len(tickers)} tickers from Yahoo in one batched call")
    data = with_retries(fetch, "Yahoo")
    fetched = now_utc()
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    entries = {}
    for ticker in tickers:
        frame = data.xs(ticker, axis=1, level=1)
        fields = RAW_FIELDS + (["Capital Gains"] if "Capital Gains" in frame and frame["Capital Gains"].notna().any() else [])
        frame = frame[fields].dropna(subset=PRICE_FIELDS + ["Adj Close"], how="all").rename_axis("Date")
        dropped = data.index.difference(frame.index)
        actions = data.loc[dropped].xs(ticker, axis=1, level=1)[["Dividends", "Stock Splits"]].fillna(0)
        if (actions != 0).any().any():
            raise ValueError(f"{ticker}: corporate actions on dates without prices: {actions[(actions != 0).any(axis=1)]}")
        if frame["Volume"].notna().all():
            frame["Volume"] = frame["Volume"].astype("int64")
        path = raw_dir / "yahoo" / f"{file_stem(ticker)}.csv"
        write_csv(frame, path)
        entries[path.relative_to(ROOT).as_posix()] = describe(
            path, {"source": "Yahoo Finance", "ticker": ticker, "call": call, "fetched_utc": fetched}, frame
        )
    return entries


def download_fred(cfg: dict, raw_dir) -> dict:
    start = pd.Timestamp(cfg["data"]["start"]) - pd.Timedelta(days=FRED_LOOKBACK_DAYS)
    end = pd.Timestamp(cfg["data"]["end"])
    entries = {}
    for series in cfg["data"]["fred"]:
        url = FRED_URL.format(series=series)

        def fetch(url=url):
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            return response.content

        content = with_retries(fetch, f"FRED {series}")
        fetched = now_utc()
        table = pd.read_csv(io.BytesIO(content), index_col=0, parse_dates=True, na_values=["."])
        table.columns, table.index.name = [series], "Date"
        response_rows = len(table)
        table = table.loc[start:end]
        path = raw_dir / "fred" / f"{series}.csv"
        write_csv(table, path)
        entries[path.relative_to(ROOT).as_posix()] = describe(path, {
            "source": "FRED, Federal Reserve Bank of St. Louis", "series": series, "url": url, "fetched_utc": fetched,
            "response_sha256": hashlib.sha256(content).hexdigest(), "response_rows": response_rows,
            "kept": f"{start.date()} to {end.date()}",
        }, table)
    return entries


def download_stooq(cfg: dict, raw_dir) -> tuple[dict, dict]:
    """Second price source. Returns the manifest entries, and the reason for every ticker that could not be fetched."""
    start, end = pd.Timestamp(cfg["data"]["start"]), pd.Timestamp(cfg["data"]["end"])
    entries, unavailable = {}, {}
    for ticker in tradables(cfg):
        url = STOOQ_URL.format(symbol=ticker.lower())
        try:
            response = requests.get(url, timeout=60)
        except requests.RequestException as error:
            unavailable[ticker] = {"url": url, "reason": f"request failed: {error}", "checked_utc": now_utc()}
            continue
        content = response.content
        if response.status_code != 200 or not content.startswith(b"Date,"):
            kind = response.headers.get("Content-Type", "?")
            unavailable[ticker] = {
                "url": url, "checked_utc": now_utc(),
                "reason": f"HTTP {response.status_code}, {kind}: not a CSV (first bytes: {content[:80]!r})",
            }
            continue
        table = pd.read_csv(io.BytesIO(content), index_col=0, parse_dates=True).loc[start:end]
        table.index.name = "Date"
        path = raw_dir / "stooq" / f"{file_stem(ticker)}.csv"
        write_csv(table, path)
        entries[path.relative_to(ROOT).as_posix()] = describe(path, {
            "source": "Stooq", "ticker": ticker, "url": url, "fetched_utc": now_utc(),
            "response_sha256": hashlib.sha256(content).hexdigest(),
        }, table)
    return entries, unavailable


def download(cfg: dict, raw_dir) -> None:
    files = download_yahoo(cfg, raw_dir) | download_fred(cfg, raw_dir)
    stooq, unavailable = download_stooq(cfg, raw_dir)
    files |= stooq
    if unavailable:
        reasons = {item["reason"].split(" (first bytes")[0] for item in unavailable.values()}
        print(f"Stooq unavailable for {len(unavailable)} tickers: {sorted(reasons)}")
    manifest = {
        "snapshot_end": cfg["data"]["end"],
        "created_utc": now_utc(),
        "versions": {"python-yfinance": version("yfinance"), "pandas": version("pandas")},
        "files": dict(sorted(files.items())),
        "unavailable": {"stooq": unavailable} if unavailable else {},
    }
    write_json(manifest, raw_dir / "manifest.json")
    save_used(data_settings(cfg), raw_dir / "config.yaml")


def write_json(content: dict, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2, sort_keys=True)
        f.write("\n")


def verify_raw(manifest: dict) -> None:
    """Stop if an archived raw file is missing or differs from its recorded SHA-256."""
    for name, entry in manifest["files"].items():
        path = ROOT / name
        if not path.exists():
            raise FileNotFoundError(f"{name} is listed in data/raw/manifest.json but missing")
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"{name} differs from its SHA-256 in data/raw/manifest.json: the archive was modified")
    print(f"Verified {len(manifest['files'])} raw files against data/raw/manifest.json")


def compare_with_committed(manifest: dict, path) -> None:
    """After a fresh download, report raw files that differ from the committed checksums (vendor revisions)."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        committed = json.load(f)["raw"]["files"]
    differ = [name for name, entry in manifest["files"].items() if committed.get(name, {}).get("sha256") != entry["sha256"]]
    missing = sorted(set(committed) - set(manifest["files"]))
    if differ or missing:
        print(f"Differences from data/checksums.json (vendor revisions are reported, not hidden): changed {differ}, missing {missing}")
    else:
        print("All raw files are identical to data/checksums.json")


def build_processed(cfg: dict, raw_dir, out_dir) -> dict:
    names = tradables(cfg)
    raw = {t: read_daily(raw_dir / "yahoo" / f"{file_stem(t)}.csv").astype("float64") for t in names}
    adjusted = {t: adjust_ohlc(frame) for t, frame in raw.items()}
    sessions = pd.DatetimeIndex(sorted(set().union(*(frame.index for frame in raw.values()))), name="Date")

    daily = {field: pd.DataFrame({t: adjusted[t][field] for t in names}).reindex(sessions) for field in PRICE_FIELDS}
    vix = read_daily(raw_dir / "yahoo" / f"{file_stem(cfg['data']['vix'])}.csv")["Close"].astype("float64")
    market = pd.DataFrame({"VIX": vix.reindex(sessions)})
    for series in cfg["data"]["fred"]:
        observed = read_daily(raw_dir / "fred" / f"{series}.csv")[series].astype("float64")
        market[series] = lag_to_sessions(observed, sessions, cfg["data"]["fred_lag_days"])
    weekly_open, weekly_close = weekly_panel(daily["Open"], daily["Close"])

    tables = {f"daily_{field.lower()}.csv": table for field, table in daily.items()}
    tables |= {"daily_market.csv": market, "weekly_open.csv": weekly_open, "weekly_close.csv": weekly_close}
    entries = {}
    for name, table in tables.items():
        path = out_dir / name
        write_csv(table, path)
        entries[path.relative_to(ROOT).as_posix()] = describe(path, {"columns": list(map(str, table.columns))}, table)
        print(f"Saved {path.relative_to(ROOT)}: {table.shape[0]} rows, {table.shape[1]} columns")
    save_used(data_settings(cfg), out_dir / "config.yaml")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="download again even if data/raw/ exists")
    args = parser.parse_args()

    quiet_yfinance_deprecations()
    cfg = load_config()
    data_dir = ROOT / cfg["data"]["data_dir"]
    raw_dir, out_dir = data_dir / "raw", data_dir / "processed"
    manifest_path = raw_dir / "manifest.json"

    if raw_dir.exists() and not args.refresh:
        if not manifest_path.exists():
            raise FileNotFoundError("data/raw/ exists without manifest.json: incomplete download, run with --refresh")
        check_used(data_settings(cfg), raw_dir / "config.yaml", "01_download_data.py --refresh")
        print("data/raw/ exists: using the archived raw data, nothing is downloaded (pass --refresh to download again)")
    else:
        download(cfg, raw_dir)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    verify_raw(manifest)
    compare_with_committed(manifest, data_dir / "checksums.json")

    processed = build_processed(cfg, raw_dir, out_dir)
    checksums = {"raw": manifest, "processed": dict(sorted(processed.items()))}
    write_json(checksums, data_dir / "checksums.json")
    print(f"Saved {(data_dir / 'checksums.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
