"""Build the weekly features, market states and sizing betas of protocol section 06 from the daily data.

Until FROZEN.lock exists, every input is truncated at the In-Sample end (split.in_sample_end, 2019-12-27) right after
it is read, and no row with a later date_close is written (docs/decisions.md S22-5). Market series are read raw and
lagged one session here, never from data/processed/daily_market.csv (S22-2).

Inputs:  data/processed/daily_close.csv, data/processed/config.yaml (check_used),
         data/raw/yahoo/VIX.csv (Close), data/raw/fred/<SERIES>.csv
Outputs: data/processed/features.csv, market_states.csv, sizing_betas.csv, momentum_variants.csv (git-ignored),
         data/processed/features_config.yaml, data/checksums_features.json (rows, date range, columns, size, SHA-256)
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from src.config import ROOT, check_used, data_settings, load_config, save_used
from src.contracts import validate_betas, validate_daily_frame, validate_features, validate_market_states
from src.data import DATE_FORMAT, file_stem, read_daily, sha256, write_csv
from src.features import asset_features, market_states, momentum_variants, sizing_betas, weekly_index
from src.vault import OOSAccessError

TABLE_KEYS = ("features", "market_states", "sizing_betas", "momentum_variants")
LOCK_NAME = "FROZEN.lock"
CHECKSUMS_NAME = "checksums_features.json"
FEATURES_CONFIG_NAME = "features_config.yaml"


def _up_to(frame, end: pd.Timestamp):
    """Rows dated on or before `end` (the truncation of S22-5)."""
    return frame.loc[pd.DatetimeIndex(frame.index) <= end]


def load_inputs(data_dir: Path, end: pd.Timestamp, cfg: dict | None = None) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Daily closes, raw VIX closes and raw FRED series, each truncated to dates <= end immediately after reading.

    Returns (daily_close: adjusted closes of the tradables on the session calendar, index `date`; vix: Series named
    VIX, unlagged, index points; fred: DataFrame with the FRED series of data.fred, unlagged, percent, NaN where not
    published). Never reads data/processed/daily_market.csv.
    """
    cfg = load_config() if cfg is None else cfg
    data_dir, end = Path(data_dir), pd.Timestamp(end)

    daily_close = _up_to(read_daily(data_dir / "processed" / "daily_close.csv"), end).astype("float64")
    daily_close.index = pd.DatetimeIndex(daily_close.index, name="date")
    validate_daily_frame(daily_close)

    vix_raw = _up_to(read_daily(data_dir / "raw" / "yahoo" / f"{file_stem(cfg['data']['vix'])}.csv"), end)
    vix = vix_raw["Close"].astype("float64").rename("VIX")
    vix.index = pd.DatetimeIndex(vix.index, name="date")

    series = {}
    for name in cfg["data"]["fred"]:
        observed = _up_to(read_daily(data_dir / "raw" / "fred" / f"{name}.csv"), end)
        series[name] = observed[name].astype("float64")
    fred = pd.concat(series, axis=1).sort_index()
    fred.index = pd.DatetimeIndex(fred.index, name="date")
    return daily_close, vix, fred


def _check_calendar(weeks: pd.MultiIndex) -> None:
    """Raise ValueError if a calendar week between the first and the last week has no session (S22-3)."""
    closes = pd.DatetimeIndex(weeks.get_level_values("date_close"))
    gaps = closes[1:] - closes[:-1] != pd.Timedelta(days=7)
    if gaps.any():
        after = closes[:-1][gaps][0]
        raise ValueError(f"the session calendar has a calendar week without a session after the week ending "
                         f"{after.strftime(DATE_FORMAT)}: the week conventions of S22-3 assume none")


def build_tables(daily_close: pd.DataFrame, vix: pd.Series, fred: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    """The four weekly tables, each validated: features (contract 3), market_states (contract 4), sizing_betas
    (contract 10) and momentum_variants (contract 3, M0*). Row t of each is known after Friday close t.
    """
    _check_calendar(weekly_index(daily_close.index))
    lookbacks = list(cfg["models"]["M0_star"]["lookback_weeks"])
    tables = {
        "features": asset_features(daily_close, cfg),
        "market_states": market_states(daily_close, vix, fred, cfg),
        "sizing_betas": sizing_betas(daily_close, cfg),
        "momentum_variants": momentum_variants(daily_close, lookbacks, cfg=cfg),
    }
    validate_features(tables["features"], columns=cfg["features"]["asset"])
    validate_market_states(tables["market_states"])
    validate_betas(tables["sizing_betas"])
    validate_features(tables["momentum_variants"], columns=[f"MOM{int(weeks)}_1" for weeks in lookbacks])
    return tables


def _date_closes(table: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(table.index.get_level_values("date_close"))


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path, is_end, lock_path: Path, allow_oos: bool = False) -> dict:
    """Write `<key>.csv` for each table and describe it; refuse rows after the In-Sample end while sealed (S22-5).

    If any table has a date_close after is_end, raise src.vault.OOSAccessError unless lock_path exists and allow_oos
    is True (only 08_run_oos.py passes it, Gate 4); nothing is written when it raises. Returns {filename: {rows,
    first_date_close, last_date_close, columns, bytes, sha256}}.
    """
    out_dir, is_end = Path(out_dir), pd.Timestamp(is_end)
    unlocked = bool(allow_oos) and Path(lock_path).exists()
    for key, table in tables.items():
        dates = _date_closes(table)
        if len(dates) and dates.max() > is_end and not unlocked:
            raise OOSAccessError(f"table {key!r} has rows after the In-Sample end {is_end.strftime(DATE_FORMAT)}: "
                                 f"refused until {LOCK_NAME} exists and the unlock path of 08_run_oos.py is used")
    records = {}
    for key, table in tables.items():
        path = out_dir / f"{key}.csv"
        write_csv(table, path)
        dates = _date_closes(table)
        records[path.name] = {
            "rows": len(table),
            "first_date_close": dates.min().strftime(DATE_FORMAT) if len(dates) else None,
            "last_date_close": dates.max().strftime(DATE_FORMAT) if len(dates) else None,
            "columns": [str(column) for column in table.columns],
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    return records


def _write_json(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2, sort_keys=True)
        f.write("\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    cfg = load_config()
    data_dir = ROOT / cfg["data"]["data_dir"]
    processed = data_dir / "processed"
    check_used(data_settings(cfg), processed / "config.yaml", "01_download_data.py")
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])

    daily_close, vix, fred = load_inputs(data_dir, end=is_end, cfg=cfg)
    tables = build_tables(daily_close, vix, fred, cfg)
    records = write_tables(tables, processed, is_end, ROOT / LOCK_NAME)
    settings = {"data": data_settings(cfg), "features": cfg["features"], "in_sample_end": cfg["split"]["in_sample_end"]}
    save_used(settings, processed / FEATURES_CONFIG_NAME)
    _write_json(records, data_dir / CHECKSUMS_NAME)

    for name, record in sorted(records.items()):
        print(f"Saved {name}: {record['rows']} rows, date_close {record['first_date_close']} to {record['last_date_close']}")
    print(f"Saved {(data_dir / CHECKSUMS_NAME).relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
