"""Load and validate config.yaml, and detect outputs built with a different config.yaml."""

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

# Settings that change the downloaded data
DATA_KEYS = ["tickers", "hedge", "benchmark", "vix", "fred", "start", "end"]

EXECUTION_TYPES = ["close_to_close", "open_to_open"]


def load_config(path: Path | None = None, validate: bool = True) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if validate:
        validate_config(cfg)
    return cfg


def data_settings(cfg: dict) -> dict:
    """The settings that change the downloaded data, as saved next to the data."""
    return {key: cfg["data"][key] for key in DATA_KEYS}


def tradables(cfg: dict) -> list[str]:
    """Tickers with prices that are traded or used as the benchmark: sectors, hedge, benchmark."""
    return cfg["data"]["tickers"] + [cfg["data"]["hedge"], cfg["data"]["benchmark"]]


def _friday(name: str, value: str) -> pd.Timestamp:
    day = pd.Timestamp(value)
    if day.day_name() != "Friday":
        raise ValueError(f"{name} ({day.date()}) must be a Friday: the period must end with a whole week")
    return day


def validate_config(cfg: dict) -> None:
    """Raise ValueError if the dates or the ticker sets break the protocol's rules."""
    data, split = cfg["data"], cfg["split"]

    tickers = data["tickers"]
    if len(set(tickers)) != len(tickers):
        raise ValueError(f"data.tickers has duplicates: {tickers}")
    if data["benchmark"] in tickers or data["benchmark"] == data["hedge"]:
        raise ValueError(f"data.benchmark ({data['benchmark']}) must never be traded: not in data.tickers, not the hedge")
    if data["hedge"] in tickers:
        raise ValueError(f"data.hedge ({data['hedge']}) must not be one of data.tickers")
    if data["vix"] in tradables(cfg):
        raise ValueError(f"data.vix ({data['vix']}) is a market state, not a traded ticker")
    signal = cfg["signal"]
    if signal["top_k"] + signal["bottom_k"] > len(tickers):
        raise ValueError("signal.top_k + signal.bottom_k must not exceed the number of traded tickers")

    start = pd.Timestamp(data["start"])
    end = _friday("data.end", data["end"])
    warmup_end = pd.Timestamp(split["warmup_end"])
    is_end = _friday("split.in_sample_end", split["in_sample_end"])
    oos_start = pd.Timestamp(split["oos_start"])
    if not start < warmup_end < is_end < oos_start <= end:
        raise ValueError("dates must satisfy data.start < split.warmup_end < split.in_sample_end < split.oos_start <= data.end")
    if oos_start != is_end + pd.Timedelta(days=3):
        raise ValueError(f"split.oos_start ({oos_start.date()}) must be the Monday after split.in_sample_end ({is_end.date()})")

    if cfg["execution"]["type"] not in EXECUTION_TYPES:
        raise ValueError(f"execution.type ({cfg['execution']['type']}) must be one of {EXECUTION_TYPES}")
    costs = cfg["costs"]
    if costs["bps_baseline"] not in costs["bps"] or costs["borrow_baseline"] not in costs["borrow"]:
        raise ValueError("costs: the baselines must be among the cost scenarios")


def _shown(path: Path) -> Path:
    """Path relative to the repository root when inside it, for messages."""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def save_used(settings: dict, path: Path) -> None:
    """Save the settings used to build the files of a folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(settings, f)


def check_used(settings: dict, path: Path, script: str) -> None:
    """Stop if the files of a folder were built with different settings."""
    if not path.exists():
        raise FileNotFoundError(f"{_shown(path)} not found: run the scripts in order")
    with open(path, encoding="utf-8") as f:
        if yaml.safe_load(f) != settings:
            raise ValueError(f"{_shown(path.parent)} was built with a different config.yaml: run {script} again")
