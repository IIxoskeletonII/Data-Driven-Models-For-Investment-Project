"""Amendment 9 C4 and decision S40-1: the round2: section of config.yaml leaves every round-1 identity unchanged.

Round-2 settings live in their own section. These tests prove that adding it changed no round-1 spec_hash, no
walk-forward or backtest settings and no other section, and that every used.yaml and oos_used.yaml under outputs/
(any depth, synthetic wiring outputs skipped, each mapped to its writer; S41-8) still passes check_used. The trial log and config.yaml are committed, so the hash tests run in CI. outputs/ is git-ignored, so
the real-tree test skips where no output exists (CI) and runs on a machine with the outputs; the mapping itself is
tested on a temporary outputs tree.
"""

import copy
import csv
import functools
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from src.config import ROOT, check_used, load_config, save_used
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


SETTINGS_NAMES = ("used.yaml", "oos_used.yaml")  # the settings files check_used verifies (make_submission.py, S35-3)


@functools.cache
def script(filename: str):
    """06_backtest.py, 07_evaluate.py or 08_run_oos.py, loaded by path (their settings functions only)."""
    spec = importlib.util.spec_from_file_location(f"round2_config_{filename[:2]}", ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def used_files(root: Path = ROOT) -> list[Path]:
    """Every used.yaml and oos_used.yaml under root/outputs at any depth, sorted, without synthetic wiring outputs (a
    folder named synthetic, as make_submission.py leaves out of the zip, S35-3; decision S41-8)."""
    outputs = Path(root) / "outputs"
    if not outputs.is_dir():
        return []
    files = sorted(p for name in SETTINGS_NAMES for p in outputs.rglob(name) if p.is_file())
    return [p for p in files if "synthetic" not in p.relative_to(outputs).parts[:-1]]


def expected_used(path: Path, cfg: dict, root: Path = ROOT) -> tuple[dict, str]:
    """(settings, writer) that the writer of `path` saves under cfg (S41-8); AssertionError for an unknown place, or for
    the placebo file without its summary.json (its reference is read from there, never assumed)."""
    outputs = Path(root) / "outputs"
    parts = path.relative_to(outputs).parts
    bt = backtest_script()
    if len(parts) == 3 and parts[0] == "walkforward" and parts[2] == "used.yaml":
        return walkforward_settings(cfg), f"05_train_walkforward.py for {parts[1]}"
    if len(parts) == 3 and parts[0] == "backtests" and parts[2] == "used.yaml":
        return bt.backtest_used(cfg, parts[1]), f"06_backtest.py --model {parts[1]}"
    if len(parts) == 4 and parts[:2] == ("diagnostics", "shift") and parts[3] == "used.yaml":
        return bt.backtest_used(cfg, parts[2]), f"06_backtest.py --shift-check {parts[2]}"
    if parts == ("diagnostics", "placebo", "used.yaml"):
        summary = outputs / "diagnostics" / "placebo" / "summary.json"
        assert summary.exists(), f"{summary.relative_to(root)} not found: the placebo reference cannot be read"
        reference = json.loads(summary.read_text(encoding="utf-8"))["reference"]
        return bt.placebo_used(cfg, reference), "06_backtest.py --placebo"
    if parts == ("ledger", "used.yaml"):
        return bt.ledger_used(cfg), "06_backtest.py --ledger-years"
    if parts == ("metrics", "used.yaml"):
        return script("07_evaluate.py").metrics_used(cfg), "07_evaluate.py"
    if parts == ("metrics", "oos_used.yaml"):
        return script("07_evaluate.py").oos_metrics_used(cfg), "07_evaluate.py --period OOS"
    if len(parts) == 3 and parts[0] == "oos" and parts[2] == "used.yaml":
        return script("08_run_oos.py").oos_used(cfg, parts[1]), "08_run_oos.py"
    if len(parts) == 4 and parts[0] == "oos_reruns" and parts[3] == "used.yaml":
        return script("08_run_oos.py").oos_used(cfg, parts[2]), f"08_run_oos.py --rerun {parts[1]}"
    raise AssertionError(f"{path.relative_to(root)}: no known writer; extend this test")


def check_tree(root: Path, cfg: dict) -> None:
    for path in used_files(root):
        settings, writer = expected_used(path, cfg, root)
        check_used(settings, path, writer)


def test_existing_used_yaml_pass_check_used():
    files = used_files()
    if not files:
        pytest.skip("no used.yaml or oos_used.yaml under outputs/ (outputs/ is git-ignored; CI has none)")
    check_tree(ROOT, load_config())


# -- the collection and the mapping on a temporary outputs tree (S41-8) ---------------------------------------------------

PLACEBO_REFERENCE = "M2"  # not the default M0, so the test shows the reference is read from summary.json


def writer_files(cfg: dict) -> dict[str, dict]:
    """Every place of S41-8 (path under outputs/) and the settings its writer saves, from the writer's own function."""
    bt, ev, oos = backtest_script(), script("07_evaluate.py"), script("08_run_oos.py")
    return {
        "walkforward/M7/used.yaml": walkforward_settings(cfg),
        "backtests/M6/used.yaml": bt.backtest_used(cfg, "M6"),
        "diagnostics/shift/M8/used.yaml": bt.backtest_used(cfg, "M8"),
        "diagnostics/placebo/used.yaml": bt.placebo_used(cfg, PLACEBO_REFERENCE),
        "ledger/used.yaml": bt.ledger_used(cfg),
        "metrics/used.yaml": ev.metrics_used(cfg),
        "metrics/oos_used.yaml": ev.oos_metrics_used(cfg),
        "oos/M0_star/used.yaml": oos.oos_used(cfg, "M0_star"),
        "oos_reruns/S99-1/M0/used.yaml": oos.oos_used(cfg, "M0"),
    }


def build_tree(root: Path, cfg: dict, *, written_with: dict | None = None) -> Path:
    """root/outputs with one settings file per writer place, the placebo summary.json, a synthetic file with other
    settings and nothing else; written_with (default cfg) is the config the files are written under."""
    source = cfg if written_with is None else written_with
    for relative, settings in writer_files(source).items():
        save_used(settings, root / "outputs" / relative)
    summary = root / "outputs" / "diagnostics" / "placebo" / "summary.json"
    summary.write_text(json.dumps({"reference": PLACEBO_REFERENCE}), encoding="utf-8")
    save_used({"something": "else"}, root / "outputs" / "backtests" / "synthetic" / "used.yaml")
    save_used({"something": "else"}, root / "outputs" / "diagnostics" / "synthetic" / "M0" / "oos_used.yaml")
    return root / "outputs"


def other_config() -> dict:
    cfg = copy.deepcopy(load_config())
    cfg["seed"] = int(cfg["seed"]) + 1  # in every writer's settings (walkforward_settings and 06 used_settings)
    return cfg


def test_every_writer_place_is_collected_and_synthetic_folders_are_skipped(tmp_path):
    cfg = load_config()
    outputs = build_tree(tmp_path, cfg)
    found = [p.relative_to(outputs).as_posix() for p in used_files(tmp_path)]
    assert len(found) == len(set(found)) == len(writer_files(cfg))
    assert sorted(found) == sorted(writer_files(cfg))
    assert not any("synthetic" in rel.split("/") for rel in found)


def test_every_writer_file_written_under_the_current_config_is_accepted(tmp_path):
    cfg = load_config()
    build_tree(tmp_path, cfg)
    check_tree(tmp_path, cfg)


@pytest.mark.parametrize("relative", sorted(writer_files(load_config())))
def test_a_writer_file_written_under_another_config_is_refused(tmp_path, relative):
    cfg = load_config()
    outputs = build_tree(tmp_path, cfg)
    save_used(writer_files(other_config())[relative], outputs / relative)
    with pytest.raises(ValueError, match="different config.yaml"):
        check_tree(tmp_path, cfg)


def test_an_unknown_place_is_refused(tmp_path):
    cfg = load_config()
    outputs = build_tree(tmp_path, cfg)
    save_used(walkforward_settings(cfg), outputs / "elsewhere" / "M6" / "used.yaml")
    with pytest.raises(AssertionError, match="no known writer"):
        check_tree(tmp_path, cfg)


@pytest.mark.parametrize("relative", ["walkforward/M6/extra/used.yaml", "used.yaml", "ledger/2016/used.yaml",
                                      "backtests/M6/oos_used.yaml", "oos/M0/extra/used.yaml"])
def test_a_known_folder_at_another_depth_or_file_name_is_refused(tmp_path, relative):
    cfg = load_config()
    outputs = build_tree(tmp_path, cfg)
    save_used(walkforward_settings(cfg), outputs / relative)
    with pytest.raises(AssertionError, match="no known writer"):
        check_tree(tmp_path, cfg)


def test_the_placebo_file_without_its_summary_is_refused(tmp_path):
    cfg = load_config()
    outputs = build_tree(tmp_path, cfg)
    (outputs / "diagnostics" / "placebo" / "summary.json").unlink()
    with pytest.raises(AssertionError, match="placebo reference"):
        check_tree(tmp_path, cfg)


def test_the_placebo_reference_comes_from_its_summary(tmp_path):
    cfg = load_config()
    outputs = build_tree(tmp_path, cfg)
    (outputs / "diagnostics" / "placebo" / "summary.json").write_text(json.dumps({"reference": "M0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="different config.yaml"):
        check_tree(tmp_path, cfg)


def test_a_missing_outputs_folder_gives_no_file(tmp_path):
    assert used_files(tmp_path) == []
