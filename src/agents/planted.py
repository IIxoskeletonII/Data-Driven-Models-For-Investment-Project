"""The planted-signal market of the research lab (protocol section 08, bounded run step 1; decisions S33-8, S33-12).

A deterministic synthetic market (no real data) with the 11 tradables, VIX and FRED from 1999 to the In-Sample end, no
momentum, and one planted effect: each sector's expected log return in week t + 1 is kappa times its cross-sectional
z-score in week t of the DSL feature PLANTED_SPEC (a short-to-long volatility ratio of weekly log returns). Everything
else is noise. `build_data_dir` writes the tables of 03_build_features.py, daily_close.csv and DGS3MO into a folder that a
Vault reads like data/processed and data/raw. The lab runs on it with config.yaml unchanged: the real run's split, refit
schedule and inner window (S33-12).
"""

import copy
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from src.config import load_config, save_used
from src.contracts import universe
from src.data import write_csv
from src.features import features_settings

START = "1999-01-04"  # the warm-up of config.yaml's split fits (S33-12)
KAPPA = 0.002  # weekly log return per unit of the planted z-score (S33-12; set on this market before any real lab run)
MARKET_MU, MARKET_SIGMA, IDIO_SIGMA, TRACKING_SIGMA, GAP_SIGMA = 0.0002, 0.010, 0.007, 0.0002, 0.002
BETAS = {"XLB": 1.10, "XLE": 1.25, "XLF": 1.30, "XLI": 1.05, "XLK": 1.15, "XLP": 0.65, "XLU": 0.60, "XLV": 0.80, "XLY": 1.40}
SHORT_WEEKS, LONG_WEEKS = 4, 26

LOG_RETURN = {"op": "diff", "n": 1, "x": {"op": "log", "x": {"input": "close"}}}
PLANTED_SPEC = {"name": "short-to-long volatility ratio", "expr": {"op": "cs_z", "x": {
    "op": "ratio", "a": {"op": "rolling", "stat": "std", "n": SHORT_WEEKS, "x": LOG_RETURN},
    "b": {"op": "rolling", "stat": "std", "n": LONG_WEEKS, "x": LOG_RETURN}}}}
NOISE_SPECS = [  # fixed noise candidates (S33-8): no planted relation on this market
    {"name": "distance from the 52-week high of relative strength", "expr": {"op": "cs_z", "x": {
        "op": "ratio", "a": {"op": "ratio", "a": {"input": "close"}, "b": {"input": "spy"}},
        "b": {"op": "rolling", "stat": "max", "n": 52,
              "x": {"op": "ratio", "a": {"input": "close"}, "b": {"input": "spy"}}}}}},
    {"name": "13-week change of the log close", "expr": {"op": "cs_rank", "x": {
        "op": "diff", "n": 13, "x": {"op": "log", "x": {"input": "close"}}}}},
    {"name": "close against its 104-week mean", "expr": {"op": "cs_z", "x": {
        "op": "ratio", "a": {"input": "close"}, "b": {"op": "rolling", "stat": "mean", "n": 104, "x": {"input": "close"}}}}},
    {"name": "8-week return when VIX is high", "expr": {"op": "mul_state", "state": "VIX", "x": {"op": "cs_z", "x": {
        "op": "rolling", "stat": "sum", "n": 8, "x": LOG_RETURN}}}},
]


def planted_cfg(cfg: dict | None = None) -> dict:
    """The configuration of the planted run: config.yaml unchanged (split, refits, inner window; S33-12), as a copy."""
    return copy.deepcopy(load_config() if cfg is None else cfg)


def sessions(end) -> pd.DatetimeIndex:
    """Weekdays from START to `end` minus US federal holidays (the synthetic equity calendar)."""
    days = pd.bdate_range(START, end)
    holidays = USFederalHolidayCalendar().holidays(START, end)
    return days.difference(holidays).rename("date")


def _cs_z(values: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score of one week (ddof = 1); 0 when all equal, NaN when any value is missing."""
    if not np.isfinite(values).all():
        return np.full(values.shape, np.nan)
    std = values.std(ddof=1)
    return np.zeros(values.shape) if std == 0 else (values - values.mean()) / std


def planted_z(weekly_log_returns: np.ndarray) -> np.ndarray:
    """The planted z-score of the last row: cs_z of std(last 4 weekly log returns) / std(last 26), as PLANTED_SPEC."""
    if len(weekly_log_returns) < LONG_WEEKS:
        return np.full(weekly_log_returns.shape[1], np.nan)
    short = weekly_log_returns[-SHORT_WEEKS:].std(axis=0, ddof=1)
    long = weekly_log_returns[-LONG_WEEKS:].std(axis=0, ddof=1)
    return _cs_z(short / long)


def build_market(seed: int, end, kappa: float = KAPPA) -> dict:
    """Daily adjusted opens and closes of the 11 tradables, VIX and FRED (DGS3MO, DGS10, BAA10Y), to `end`.

    The weeks are generated in order: week t + 1's drift of sector i is kappa · planted_z(weekly log returns to week t)
    spread evenly over its sessions (0 before 26 weekly returns exist); daily log returns add the market factor times the
    sector's beta and idiosyncratic noise. Opens are the previous close times exp(N(0, 0.002²)).
    """
    cfg = load_config()
    u = universe(cfg)
    sectors, hedge, benchmark = sorted(u.sectors), u.hedge, u.benchmark
    rng = np.random.default_rng(seed)
    days = sessions(end)
    fridays = days + pd.to_timedelta((4 - days.day_of_week) % 7, unit="D")
    week_ids, week_of_day = np.unique(fridays.values, return_inverse=True)
    market = rng.normal(MARKET_MU, MARKET_SIGMA, len(days))
    idio = rng.normal(0.0, IDIO_SIGMA, (len(days), len(sectors)))
    betas = np.array([BETAS[s] for s in sectors])
    daily = np.zeros((len(days), len(sectors)))
    weekly_returns = np.zeros((0, len(sectors)))
    for w in range(len(week_ids)):
        rows = np.flatnonzero(week_of_day == w)
        z = planted_z(weekly_returns)
        drift = np.where(np.isfinite(z), kappa * z, 0.0) / len(rows)
        daily[rows] = betas * (market[rows, None] - MARKET_MU) + MARKET_MU + drift + idio[rows]
        weekly_returns = np.vstack([weekly_returns, daily[rows].sum(axis=0)])
    log_returns = {s: daily[:, j] for j, s in enumerate(sectors)}
    log_returns[benchmark] = market + rng.normal(0.0, TRACKING_SIGMA, len(days))
    log_returns[hedge] = log_returns[benchmark] + rng.normal(0.0, TRACKING_SIGMA, len(days))
    tradables = list(u.tradables)
    close = pd.DataFrame({t: 50.0 * np.exp(np.cumsum(log_returns[t])) for t in tradables}, index=days)[tradables]
    previous = close.shift(1).fillna(close.iloc[0])
    opens = previous * np.exp(rng.normal(0.0, GAP_SIGMA, close.shape))
    vix_log = np.empty(len(days))
    vix_log[0] = np.log(18.0)
    noise = rng.normal(0.0, 0.03, len(days))
    for t in range(1, len(days)):
        vix_log[t] = vix_log[t - 1] + 0.03 * (np.log(18.0) - vix_log[t - 1]) - 4.0 * market[t] + noise[t]
    vix = pd.Series(np.round(np.exp(vix_log), 2), index=days, name="VIX")
    fred = pd.DataFrame({"DGS3MO": np.clip(0.10 + np.cumsum(rng.normal(0, 0.01, len(days))), 0.0, None),
                         "DGS10": np.clip(2.50 + np.cumsum(rng.normal(0, 0.04, len(days))), 0.3, None),
                         "BAA10Y": np.clip(2.50 + np.cumsum(rng.normal(0, 0.02, len(days))), 1.0, None)},
                        index=days).round(2)
    return {"daily_open": opens.astype(np.float64), "daily_close": close.astype(np.float64), "vix": vix, "fred": fred}


def build_data_dir(root: Path, cfg: dict, *, seed: int | None = None, kappa: float = KAPPA) -> dict[str, Path]:
    """Write the planted market's tables to root/processed (features, market states, sizing betas, momentum variants,
    labels, forward returns, daily_close.csv, features_config.yaml) and root/raw/fred/DGS3MO.csv; returns the paths."""
    from src.agents.vault_server import load_script

    script03 = load_script("03_build_features.py")
    root = Path(root)
    is_end = pd.Timestamp(cfg["split"]["in_sample_end"])
    market = build_market(int(cfg["seed"]) if seed is None else seed, is_end, kappa)
    processed, raw = root / "processed", root / "raw"
    tables = script03.build_tables(market["daily_close"], market["vix"], market["fred"], cfg)
    labels = script03.build_labels(market["daily_open"], market["daily_close"], is_end)
    forward = script03.build_forward_returns(market["daily_open"], market["daily_close"], is_end)
    script03.write_tables({**tables, "labels": labels, "forward_returns": forward}, processed, is_end, root / "FROZEN.lock")
    write_csv(market["daily_close"], processed / "daily_close.csv")
    write_csv(market["fred"][["DGS3MO"]], raw / "fred" / "DGS3MO.csv")
    save_used(features_settings(cfg), processed / "features_config.yaml")
    return {"processed": processed, "raw": raw, "lock": root / "FROZEN.lock"}
