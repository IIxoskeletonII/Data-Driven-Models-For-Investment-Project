"""Build the weekly features, market states and sizing betas of protocol section 06, and the training labels of
section 05, and the forward returns of contract 7 (S31-1), from the daily data. Session 4.1 (S41-1): also the 4-week
labels of Amendment 9 C1 (round2.label.horizon_weeks), labels_h4.csv.

Until FROZEN.lock exists, every input is truncated at the In-Sample end (split.in_sample_end, 2019-12-27) right after
it is read, and no row with a later date_close, and no label with a later label_end, is written (docs/decisions.md
S22-5, S23-1). Market series are read raw and lagged one session here, never from data/processed/daily_market.csv
(S22-2). Labels come from src.backtest.forward_returns on the truncated adjusted opens, so the last label is the week
ending 2019-12-13 (label_end 2019-12-23).

Inputs:  data/processed/daily_close.csv, daily_open.csv, data/processed/config.yaml (check_used),
         data/raw/yahoo/VIX.csv (Close), data/raw/fred/<SERIES>.csv
Outputs: data/processed/features.csv, market_states.csv, sizing_betas.csv, momentum_variants.csv, labels.csv,
         labels_h4.csv (S41-1; label_end <= 2019-12-27), forward_returns.csv (git-ignored; realised_on <= 2019-12-27), data/processed/features_config.yaml, data/checksums_features.json (rows, date range, columns,
         size, SHA-256)
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest import forward_returns
from src.config import ROOT, check_used, data_settings, load_config, save_used
from src.contracts import (
    validate_betas,
    validate_daily_frame,
    validate_features,
    validate_forward_returns,
    validate_labels,
    validate_market_states,
)
from src.data import DATE_FORMAT, file_stem, read_daily, sha256, weekly_panel, write_csv
from src.features import (
    asset_features,
    features_settings,
    market_states,
    momentum_variants,
    sizing_betas,
    weekly_index,
)
from src.labels import make_horizon_labels, make_labels
from src.vault import OOSAccessError

TABLE_KEYS = ("features", "market_states", "sizing_betas", "momentum_variants")
LABELS_KEY = "labels"
LABELS_H4_KEY = "labels_h4"  # 4-week labels of Amendment 9 C1 (S41-1)
LABEL_KEYS = (LABELS_KEY, LABELS_H4_KEY)  # tables whose label_end is sealed at the In-Sample end
FORWARD_KEY = "forward_returns"  # S31-1
REALISED_ON, PERIOD = "realised_on", "period"
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


def load_opens(data_dir: Path, end: pd.Timestamp) -> pd.DataFrame:
    """Fully adjusted daily opens of the tradables (data/processed/daily_open.csv, written by 01_download_data.py),
    truncated to dates <= end immediately after reading (S23-1). Index `date` (equity sessions), float64.
    """
    daily_open = _up_to(read_daily(Path(data_dir) / "processed" / "daily_open.csv"), pd.Timestamp(end)).astype("float64")
    daily_open.index = pd.DatetimeIndex(daily_open.index, name="date")
    validate_daily_frame(daily_open)
    return daily_open


def build_forward_returns(daily_open: pd.DataFrame, daily_close: pd.DataFrame, is_end, truncate_at=None,
                          lock_path: Path | None = None) -> pd.DataFrame:
    """Forward returns of contract 7 on the truncated weekly index, as one table (S31-1, S37-2).

    Both inputs are truncated to dates <= truncate_at first (default is_end, the In-Sample end); weekly opens come from
    src.data.weekly_panel and fwd[t] = O(t+2) / O(t+1) − 1 from src.backtest.forward_returns (Mattia's, unchanged). A
    return of week t is realised at the open of week t+2 (realised_on); the last two weeks before the truncation have
    none (NaN, NaT). period is "IS" if realised_on <= is_end, "OOS" if later, missing where realised_on is NaT.

    A truncate_at after is_end (08_run_oos.py at data.end, Gate 4) needs lock_path to be an existing FROZEN.lock, else
    OOSAccessError; without it, any realised_on after is_end raises OOSAccessError. A truncate_at before is_end raises
    ValueError. Returns the weekly index with the 11 tradables (float64, simple returns), realised_on and period; its
    three parts pass validate_forward_returns.
    """
    is_end = pd.Timestamp(is_end)
    truncate_at = is_end if truncate_at is None else pd.Timestamp(truncate_at)
    if truncate_at < is_end:
        raise ValueError(f"build_forward_returns: truncate_at {truncate_at.date()} is before the In-Sample end "
                         f"{is_end.date()}")
    unlocked = lock_path is not None and Path(lock_path).exists()
    if truncate_at > is_end and not unlocked:
        raise OOSAccessError(f"build_forward_returns: truncating at {truncate_at.date()}, after the In-Sample end "
                             f"{is_end.date()}, needs an existing FROZEN.lock (S37-2)")
    daily_open, daily_close = _up_to(daily_open, truncate_at), _up_to(daily_close, truncate_at)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    fwd, realised_on, period = forward_returns(weekly_open, is_end=is_end)
    if not unlocked and (realised_on.dropna() > is_end).any():
        raise OOSAccessError(f"build_forward_returns: a forward return is realised after {is_end.strftime(DATE_FORMAT)}")
    table = fwd.copy()
    table[REALISED_ON] = realised_on
    table[PERIOD] = period
    return table


def split_forward_returns(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """(fwd, realised_on, period) of contract 7 from the table of build_forward_returns."""
    fwd = table.drop(columns=[REALISED_ON, PERIOD]).astype(np.float64)
    return fwd, pd.to_datetime(table[REALISED_ON]).rename(REALISED_ON), table[PERIOD].astype(object).rename(PERIOD)


def build_labels(daily_open: pd.DataFrame, daily_close: pd.DataFrame, is_end) -> pd.DataFrame:
    """Training labels of §05 (contract 6) from the adjusted daily opens and closes, In-Sample only (S23-1, S31-1).

    Forward returns come from build_forward_returns (both inputs truncated to dates <= is_end); labels from
    src.labels.make_labels with the truncated session calendar. A label of week t is realised at label_end = the
    session of O(t+2); only rows with label_end <= is_end are kept, so the weeks ending 2019-12-20 and 2019-12-27 have
    none. Returns index (date_close, ticker), columns [y, label_end]; passes validate_labels.
    """
    is_end = pd.Timestamp(is_end)
    fwd, _, _ = split_forward_returns(build_forward_returns(daily_open, daily_close, is_end))
    labels = make_labels(fwd, pd.DatetimeIndex(_up_to(daily_close, is_end).index))
    labels = labels.loc[np.asarray(pd.DatetimeIndex(labels["label_end"]) <= is_end)]
    validate_labels(labels)
    return labels


def build_horizon_labels(daily_open: pd.DataFrame, daily_close: pd.DataFrame, is_end, horizon: int, truncate_at=None,
                         lock_path: Path | None = None) -> pd.DataFrame:
    """Relative labels over `horizon` weeks (Amendment 9 C1: 4 weeks), In-Sample only unless unlocked (S41-1, S41-6).

    Both inputs are truncated to dates <= truncate_at (default is_end, the In-Sample end) right away; weekly opens come
    from src.data.weekly_panel and the labels from src.labels.make_horizon_labels with the truncated session calendar:
    y[t, i] = O(t+h+1, i) / O(t+1, i) − 1 minus its mean over the 9 sectors, label_end = the session of O(t+h+1). Only
    rows with label_end <= truncate_at are kept (for h = 4 at the In-Sample end: last week 2019-11-22, label_end
    2019-12-23). A truncate_at after is_end (08_run_oos.py at data.end, Gate 4) needs lock_path to be an existing
    FROZEN.lock, else OOSAccessError; one before is_end raises ValueError. Returns index (date_close, ticker), columns
    [y, label_end]; passes validate_labels.
    """
    is_end = pd.Timestamp(is_end)
    truncate_at = is_end if truncate_at is None else pd.Timestamp(truncate_at)
    if truncate_at < is_end:
        raise ValueError(f"build_horizon_labels: truncate_at {truncate_at.date()} is before the In-Sample end "
                         f"{is_end.date()}")
    if truncate_at > is_end and not (lock_path is not None and Path(lock_path).exists()):
        raise OOSAccessError(f"build_horizon_labels: truncating at {truncate_at.date()}, after the In-Sample end "
                             f"{is_end.date()}, needs an existing FROZEN.lock (S41-6)")
    daily_open, daily_close = _up_to(daily_open, truncate_at), _up_to(daily_close, truncate_at)
    weekly_open, _ = weekly_panel(daily_open, daily_close)
    labels = make_horizon_labels(weekly_open, pd.DatetimeIndex(daily_close.index), horizon)
    labels = labels.loc[np.asarray(pd.DatetimeIndex(labels["label_end"]) <= truncate_at)]
    validate_labels(labels)
    return labels


def _check_label_weeks(labels: pd.DataFrame, features: pd.DataFrame) -> None:
    """Raise ValueError unless every label week is a week of the features (the same weekly index)."""
    extra = pd.DatetimeIndex(labels.index.get_level_values("date_close").unique()).difference(
        pd.DatetimeIndex(features.index.get_level_values("date_close").unique()))
    if len(extra):
        raise ValueError(f"labels have weeks that the features do not have, first {extra[0].strftime(DATE_FORMAT)}")


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
    """Write `<key>.csv` for each table and describe it; refuse rows after the In-Sample end while sealed (S22-5, S23-1).

    If any table has a date_close after is_end, a label table ("labels", "labels_h4") a label_end after is_end, or the
    "forward_returns"
    table a realised_on after is_end, raise
    src.vault.OOSAccessError unless lock_path exists and allow_oos is True (only 08_run_oos.py passes it, Gate 4);
    nothing is written when it raises. Returns {filename: {rows, first_date_close, last_date_close, columns, bytes,
    sha256}}.
    """
    out_dir, is_end = Path(out_dir), pd.Timestamp(is_end)
    unlocked = bool(allow_oos) and Path(lock_path).exists()
    for key, table in tables.items():
        dates = _date_closes(table)
        late = len(dates) and dates.max() > is_end
        if key in LABEL_KEYS and len(table):
            late = late or pd.DatetimeIndex(table["label_end"]).max() > is_end
        if key == FORWARD_KEY and len(table):
            late = late or bool((pd.DatetimeIndex(table[REALISED_ON]).dropna() > is_end).any())
        if late and not unlocked:
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
    daily_open = load_opens(data_dir, end=is_end)
    tables = build_tables(daily_close, vix, fred, cfg)
    tables[LABELS_KEY] = build_labels(daily_open, daily_close, is_end)
    tables[LABELS_H4_KEY] = build_horizon_labels(daily_open, daily_close, is_end, int(cfg["round2"]["label"]["horizon_weeks"]))
    tables[FORWARD_KEY] = build_forward_returns(daily_open, daily_close, is_end)
    validate_forward_returns(*split_forward_returns(tables[FORWARD_KEY]), is_end=is_end)
    _check_label_weeks(tables[LABELS_KEY], tables["features"])
    _check_label_weeks(tables[LABELS_H4_KEY], tables["features"])
    records = write_tables(tables, processed, is_end, ROOT / LOCK_NAME)
    save_used(features_settings(cfg), processed / FEATURES_CONFIG_NAME)
    _write_json(records, data_dir / CHECKSUMS_NAME)

    for name, record in sorted(records.items()):
        print(f"Saved {name}: {record['rows']} rows, date_close {record['first_date_close']} to {record['last_date_close']}")
    print(f"Saved {(data_dir / CHECKSUMS_NAME).relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
