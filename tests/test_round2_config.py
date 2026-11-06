"""Amendment 9 C4 and decision S40-1: the round2: section of config.yaml leaves every round-1 identity unchanged.

Round-2 settings live in their own section. These tests prove that adding it changed no round-1 spec_hash, no
walk-forward or backtest settings and no other section, and that every existing outputs/<stage>/<name>/used.yaml still
passes check_used. The trial log and config.yaml are committed, so the hash tests run in CI. outputs/ is git-ignored, so
the used.yaml test skips where no output exists (CI) and runs on a machine with the In-Sample outputs.
"""

import csv
import functools
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from src.config import ROOT, check_used, load_config
from src.models import walkforward_settings
from src.vault import spec_hash

TRIAL_LOG = ROOT / "docs" / "trial_log.csv"

# SHA-256 of the canonical JSON (sorted keys, no spaces) of each set of sections, computed from config.yaml on main
# at commit 30ebd5c, before the round2: section existed (6 Nov 2026).
WALKFORWARD_DIGEST = "47492f2022a2efe4bad346c52bc3adf7aa425e1cd1a6ba74d490481c16c2af9b"  # seed data split execution features models
BACKTEST_DIGEST = "5ec84593f39547fd04a864fc88577bfe185f878a5ca4ac11255ecc6c641879d1"  # seed split execution signal costs metrics
ROUND1_DIGEST = "ddf598a3f0ce49153832fa52f76c327287f959e338bcc8b2fcc945f53b747ea1"  # every section but round2
BACKTEST_SECTIONS = ("seed", "split", "execution", "signal", "costs", "metrics")  # 06_backtest.py: used_settings


def digest(content: object) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@functools.cache
def backtest_script():
    spec = importlib.util.spec_from_file_location("backtest_script_round2", ROOT / "06_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def round1(cfg: dict) -> dict:
    return {key: value for key, value in cfg.items() if key != "round2"}


def test_config_has_a_round2_section():
    assert "round2" in load_config()


def test_round2_holds_the_amendment9_settings():
    round2 = load_config()["round2"]
    assert round2["test_weeks"] == 624
    assert round2["label"]["horizon_weeks"] == 4
    assert round2["smoothing"] == {"half_life_weeks": [2, 4], "lags_per_half_life": 3}
    models = round2["models"]
    assert models["M6"]["alpha"] == models["M7"]["alpha"] == [0.1, 1, 10]
    assert models["M7"]["half_life_weeks"] == models["M8"]["half_life_weeks"] == [2, 4]
    m8 = models["M8"]
    assert (m8["objective"], m8["max_depth"], m8["n_estimators"], m8["learning_rate"]) == ("lambdarank", [2, 3], 200, 0.03)
    assert (m8["num_threads"], m8["deterministic"], m8["relevance_levels"], m8["positions_evaluated"]) == (1, True, 9, 9)
    assert round2["tie_order"] == {"alpha": [10, 1, 0.1], "max_depth": [2, 3], "half_life_weeks": [4, 2]}
    assert round2["tie_precedence"] == ["alpha", "max_depth", "half_life_weeks"]
    assert round2["candidate_order"] == ["M6", "M7", "M8", "M9"]
    assert round2["selection"] == {"bootstrap_prob": 0.90}
    lab = round2["agent_lab"]
    assert (lab["base_rung"], lab["max_candidates"], lab["coder_repairs"], lab["budget_usd"]) == ("M7", 40, 1, 10)
    # S40-1: a DDMI_ variable, never the SDK default; the exact name is tested with the lab code (tests/test_agents*.py)
    assert lab["api_key_env"].startswith("DDMI_") and lab["api_key_env"].endswith("_API_KEY")


def test_editing_models_would_change_every_spec_hash():
    """The trap of S40-1: round-2 rungs written into models: would re-hash every round-1 trial."""
    cfg = load_config()
    edited = {**cfg, "models": {**cfg["models"], "M6": cfg["round2"]["models"]["M6"]}}
    with open(TRIAL_LOG, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert all(spec_hash(json.loads(row["params_json"]), edited) != row["spec_hash"] for row in rows)


def test_round2_is_outside_every_round1_identity():
    cfg = load_config()
    assert "round2" not in walkforward_settings(cfg)
    assert "round2" not in backtest_script().used_settings(cfg)
    assert walkforward_settings(cfg) == walkforward_settings(round1(cfg))


def test_walkforward_settings_unchanged():
    assert digest(walkforward_settings(load_config())) == WALKFORWARD_DIGEST, (
        "walkforward_settings(cfg) changed: every round-1 spec_hash and output is stale (Amendment 9 C4, S40-1)")


def test_backtest_settings_unchanged():
    cfg = load_config()
    assert backtest_script().used_settings(cfg) == {key: cfg[key] for key in BACKTEST_SECTIONS}
    assert digest({key: cfg[key] for key in BACKTEST_SECTIONS}) == BACKTEST_DIGEST


def test_no_round1_section_changed():
    assert digest(round1(load_config())) == ROUND1_DIGEST, (
        "a round-1 section of config.yaml changed; Amendment 9 C4 allows none (a change needs its own amendment)")


def test_every_trial_log_spec_hash_unchanged():
    cfg = load_config()
    with open(TRIAL_LOG, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows, "docs/trial_log.csv has no rows"
    changed = [row["trial_id"] for row in rows if spec_hash(json.loads(row["params_json"]), cfg) != row["spec_hash"]]
    assert not changed, f"trials {changed} no longer reproduce their logged spec_hash under config.yaml"


def used_files() -> list[Path]:
    return sorted((ROOT / "outputs").glob("*/*/used.yaml"))


def expected_used(path: Path, cfg: dict) -> tuple[dict, str]:
    stage, name = path.parent.parent.name, path.parent.name
    if stage == "walkforward":
        return walkforward_settings(cfg), f"05_train_walkforward.py for {name}"
    if stage == "backtests":
        return backtest_script().backtest_used(cfg, name), f"06_backtest.py --model {name}"
    raise AssertionError(f"{path.relative_to(ROOT)}: no known writer; extend this test")


def test_existing_used_yaml_pass_check_used():
    files = used_files()
    if not files:
        pytest.skip("no outputs/<stage>/<name>/used.yaml (outputs/ is git-ignored; CI has none)")
    cfg = load_config()
    for path in files:
        settings, script = expected_used(path, cfg)
        check_used(settings, path, script)
