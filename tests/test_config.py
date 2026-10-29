"""config.yaml follows the protocol's rules, and config validation rejects broken settings."""

import copy

import pandas as pd
import pytest

from src import config

CFG = config.load_config()


def broken(**changes) -> dict:
    """A copy of the config with some settings changed, e.g. broken(data__end="2026-10-15")."""
    cfg = copy.deepcopy(CFG)
    for key, value in changes.items():
        section, name = key.split("__")
        cfg[section][name] = value
    return cfg


def test_config_is_valid():
    config.validate_config(CFG)


def test_dates_are_fridays():
    assert pd.Timestamp(CFG["data"]["end"]).day_name() == "Friday"
    assert pd.Timestamp(CFG["split"]["in_sample_end"]).day_name() == "Friday"
    assert pd.Timestamp(CFG["split"]["oos_start"]).day_name() == "Monday"


def test_benchmark_and_hedge_never_traded():
    data = CFG["data"]
    assert data["benchmark"] not in data["tickers"]
    assert data["hedge"] not in data["tickers"]
    assert data["benchmark"] != data["hedge"]
    assert config.tradables(CFG) == data["tickers"] + [data["hedge"], data["benchmark"]]


@pytest.mark.parametrize(
    "changes",
    [
        {"data__end": "2026-10-15"},  # a Thursday
        {"split__in_sample_end": "2019-12-26"},  # a Thursday
        {"split__oos_start": "2020-01-01"},  # not the Monday after the In-Sample end
        {"data__benchmark": "XLK"},  # benchmark among the traded tickers
        {"data__benchmark": "IVV"},  # benchmark equal to the hedge
        {"data__hedge": "XLF"},  # hedge among the sector tickers
        {"data__tickers": ["XLB", "XLB", "XLE"]},  # duplicates
        {"split__warmup_end": "2020-12-31"},  # warm-up after the In-Sample end
        {"execution__type": "close_to_open"},
        {"costs__bps_baseline": 15},
    ],
)
def test_validation_rejects(changes):
    with pytest.raises(ValueError):
        config.validate_config(broken(**changes))


def test_check_used(tmp_path):
    settings = config.data_settings(CFG)
    path = tmp_path / "prices" / "config.yaml"
    with pytest.raises(FileNotFoundError):
        config.check_used(settings, path, "01_download_data.py")
    config.save_used(settings, path)
    config.check_used(settings, path, "01_download_data.py")
    with pytest.raises(ValueError, match="different config.yaml"):
        config.check_used(settings | {"end": "2026-10-09"}, path, "01_download_data.py")
