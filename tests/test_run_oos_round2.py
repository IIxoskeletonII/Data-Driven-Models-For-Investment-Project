"""08_run_oos.py for the round-2 candidates M6, M7 and M8 (decision S42-8; Amendment 6 C2, Amendment 9 C1; S41-6).

The synthetic project is the one of test_run_oos_script.py (shared synthetic market, a temporary git repository, a
config copy with test years 2017-2019 and data.end 2020-12-18) with three additions: round2.test_weeks is the synthetic
test-week count, data/processed/ also holds the In-Sample labels_h4.csv, and the walk-forwards are those of M0, M0_star
and the tuned M7. The gate file lists the candidates of both rounds (models.candidate_order + round2.candidate_order)
with every one absent except M7, evaluated and passing, so the run's models are M7, M0 and M0_star.

The project is built, frozen, signed and run ONCE per module (the run is instrumented: every file opened and every
assert_purged call is recorded); tests that change something work on copies. Nothing reads the repository's own data/
folder and no FROZEN.lock is created in the repository.
"""

import builtins
import io
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src import features, models
from src.config import data_settings, load_config, save_used
from src.data import write_csv
from src.vault import Vault
from tests.test_run_oos_script import (
    DATA_END,
    IS_END,
    SPOTS,
    commit,
    copy_repo,
    gate_row,
    git,
    init_repo,
    load,
    repo_state,
    synthetic_cfg,
)

ROOT = Path(__file__).resolve().parents[1]
FIRST_TEST_WEEK, LAST_TEST_WEEK = "2017-01-06", "2019-12-13"  # test years 2017-2019 of the synthetic config
N_TEST_WEEKS = len(pd.date_range(FIRST_TEST_WEEK, LAST_TEST_WEEK, freq="7D"))
WALKFORWARDS = ("M0", "M0_star", "M7")
M7_FILES = ("scores.csv", "used.yaml", "summary.json", "selection.csv")
OOS_FILES = ("scores.csv", "weekly.csv", "metrics.csv", "summary.json", "used.yaml")


def round2_cfg() -> dict:
    """The synthetic config of test_run_oos_script.py with round2.test_weeks = the synthetic test-week count."""
    cfg = synthetic_cfg()
    cfg["round2"]["test_weeks"] = N_TEST_WEEKS
    return cfg


def candidate_names(cfg: dict) -> list[str]:
    return list(cfg["models"]["candidate_order"]) + list(cfg["round2"]["candidate_order"])


def gate_of(cfg: dict, evaluated: dict[str, dict] | None = None, selected: str = "M7") -> dict:
    """A gate file over both rounds: every candidate absent except the given evaluated rows (name -> row)."""
    evaluated = {"M7": gate_row("M7", True)} if evaluated is None else evaluated
    return {"selected": selected, "candidates": [evaluated.get(n, {"name": n, "status": "absent"})
                                                 for n in candidate_names(cfg)]}


def build_round2_project(root: Path, market) -> dict:
    """The synthetic project of test_run_oos_script.build_project (copied here because that helper writes neither
    labels_h4.csv nor round2.test_weeks): raw files, daily prices, the In-Sample tables of 03 with labels_h4.csv, the
    walk-forwards of 05 (M0, M0_star, M7), the In-Sample backtests of 06 and the gate file; everything but data/ and
    outputs/ committed."""
    cfg = round2_cfg()
    (root / "docs").mkdir(parents=True)
    with open(root / "config.yaml", "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    cfg = load_config(root / "config.yaml")
    (root / "docs" / "decisions.md").write_text("# Decision log\n", encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text("data/\noutputs/\n", encoding="utf-8", newline="\n")

    raw, fred_dir = root / "data" / "raw" / "yahoo", root / "data" / "raw" / "fred"
    raw.mkdir(parents=True)
    fred_dir.mkdir(parents=True)
    for ticker, frame in market.raw.items():
        frame.rename_axis("Date").to_csv(raw / f"{ticker}.csv")
    market.vix.rename("Close").to_frame().rename_axis("Date").to_csv(raw / "VIX.csv")
    for name in cfg["data"]["fred"]:
        market.fred[[name]].rename_axis("Date").to_csv(fred_dir / f"{name}.csv")
    processed = root / "data" / "processed"
    write_csv(market.daily_close.rename_axis("date"), processed / "daily_close.csv")
    write_csv(market.daily_open.rename_axis("date"), processed / "daily_open.csv")
    save_used(data_settings(cfg), processed / "config.yaml")

    s03 = load("round2_oos_test_03", "03_build_features.py")
    close, opens = market.daily_close, market.daily_open
    close, opens = close[close.index <= IS_END], opens[opens.index <= IS_END]
    vix, fred = market.vix[market.vix.index <= IS_END], market.fred[market.fred.index <= IS_END]
    tables = s03.build_tables(close, vix, fred, cfg)
    tables["labels"] = s03.build_labels(opens, close, IS_END)
    tables["forward_returns"] = s03.build_forward_returns(opens, close, IS_END)
    tables["labels_h4"] = s03.build_horizon_labels(opens, close, IS_END, 4)
    s03.write_tables(tables, processed, IS_END, root / "FROZEN.lock")
    save_used(features.features_settings(cfg), processed / "features_config.yaml")

    s05 = load("round2_oos_test_05", "05_train_walkforward.py")
    for name in WALKFORWARDS:
        s05.run(name, cfg, data_dir=processed, out_dir=root / "outputs" / "walkforward" / name,
                trial_path=root / "docs" / "trial_log.csv", log_path=root / "outputs" / "vault_access_log.jsonl",
                lock_path=root / "FROZEN.lock", spots=SPOTS)
    s06 = load("round2_oos_test_06", "06_backtest.py")
    s06.ROOT = root  # this module instance only
    inputs = s06.in_sample_inputs(cfg)
    for name in WALKFORWARDS:
        s06.backtest_model(cfg, name, inputs)
    gate = root / "outputs" / "metrics" / "selection_gate.json"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(json.dumps(gate_of(cfg)), encoding="utf-8")

    init_repo(root)
    commit(root, "chore: synthetic project")
    return cfg


_PROJECT: dict = {}
_RAN: dict = {}


@pytest.fixture(scope="module")
def script():
    return load("run_oos_round2_script", "08_run_oos.py")


@pytest.fixture
def project(synthetic_market, tmp_path_factory) -> dict:
    """The synthetic round-2 project, built once per module, not frozen (read-only: tests copy it before changing)."""
    if not _PROJECT:
        root = tmp_path_factory.mktemp("oos_round2_project") / "project"
        root.mkdir()
        _PROJECT.update(root=root, cfg=build_round2_project(root, synthetic_market))
    return _PROJECT


def under(path: Path, folder: Path) -> bool:
    return Path(os.path.normcase(os.path.realpath(path))).is_relative_to(Path(os.path.normcase(os.path.realpath(folder))))


@pytest.fixture
def ran(script, project, tmp_path_factory) -> dict:
    """A copy of the project frozen, signed and run once, with every opened path and every assert_purged call of the
    freeze and the run recorded (built once, read-only)."""
    if _RAN:
        return _RAN
    before = repo_state()
    root = tmp_path_factory.mktemp("oos_round2_ran") / "project"
    copy_repo(project["root"], root)
    opened: list[Path] = []
    purged: list[tuple[pd.Series, object]] = []
    real_open, original_purged = builtins.open, models.assert_purged

    def recording_open(file, *args, **kwargs):
        if isinstance(file, str | bytes | os.PathLike):
            opened.append(Path(os.path.abspath(os.fsdecode(file))))
        return real_open(file, *args, **kwargs)

    def spy(train_label_end, fold):
        purged.append((pd.Series(train_label_end).copy(), fold))
        return original_purged(train_label_end, fold)

    patches = pytest.MonkeyPatch()
    try:
        patches.setattr(builtins, "open", recording_open)
        patches.setattr(io, "open", recording_open)
        patches.setattr(models, "assert_purged", spy)
        lock = script.freeze(root)
        with open(root / "docs" / "decisions.md", "a", encoding="utf-8", newline="\n") as f:
            f.write("\nGate 3 signatures (synthetic test)\n")
        commit(root, "docs: sign the freeze")
        report = script.run_oos(root)
    finally:
        patches.undo()
    _RAN.update(root=root, cfg=project["cfg"], lock=lock, report=report, opened=opened, purged=purged, repo_state=before)
    return _RAN


def closes(frame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(frame.index.get_level_values("date_close"))


def read_scores(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, index_col=[0, 1], parse_dates=[0, 1])


def last_selection_row(root: Path) -> pd.Series:
    table = pd.read_csv(root / "outputs" / "walkforward" / "M7" / "selection.csv")
    return table.sort_values(["test_year", "refit"]).iloc[-1]


def open_vault(script, root: Path, cfg: dict) -> Vault:
    """An unlocked vault on the full-range tables the run wrote into the temporary project."""
    vault = Vault(IS_END, lock_path=root / "FROZEN.lock", log_path=root / "outputs" / "test_vault_log.jsonl",
                  data_dir=root / "data" / "processed" / "oos", cfg=cfg)
    vault.unlock()
    return vault


def oos_tables(script, ran: dict):
    """(LadderData, 4-week labels, Out-of-Sample folds) of the run, rebuilt from its own full-range tables."""
    root, cfg, end = ran["root"], ran["cfg"], pd.Timestamp(DATA_END)
    vault = open_vault(script, root, cfg)
    data = script.ladder_data(vault, end)
    labels_h4 = vault.labels(end, horizon=4)
    folds = script.oos_folds(data, cfg, pd.Timestamp(ran["report"]["last_in_sample_scored_week"]))
    return data, labels_h4, folds


# ---------------------------------------------------------------- a. end to end


def test_end_to_end_run_writes_the_five_files_and_one_continuous_book(script, ran):
    root, report = ran["root"], ran["report"]
    for name in ("M7", "M0", "M0_star"):
        assert all((root / "outputs" / "oos" / name / f).exists() for f in OOS_FILES), name
    run_json = json.loads((root / "outputs" / "oos" / "run.json").read_text(encoding="utf-8"))
    assert run_json["models"] == report["models"] == ["M7", "M0", "M0_star"]
    for key in ("models", "frozen_values", "folds", "reproduction_2019q4", "tables"):
        assert key in run_json
    assert "labels_h4.csv" in run_json["tables"]
    assert (run_json["folds"][0]["test_year"], run_json["folds"][0]["refit"]) == (2019, 4)

    weekly = pd.read_csv(root / "outputs" / "oos" / "M7" / "weekly.csv", index_col=[0, 1], parse_dates=[0, 1, "realised_on"])
    assert set(weekly["period"]) == {"IS", "OOS"}
    assert (weekly["period"] == np.where(weekly["realised_on"] <= IS_END, "IS", "OOS")).all()
    first_oos = weekly.loc[weekly["period"] == "OOS"].iloc[0]
    assert first_oos["realised_on"] == pd.Timestamp("2019-12-30")
    assert first_oos["turnover"] < 1.0  # costed from the drifted In-Sample book, not from cash (Amendment 2 C5)

    last_is_week = pd.Timestamp(report["last_in_sample_scored_week"])
    assert last_is_week == pd.Timestamp(LAST_TEST_WEEK)
    oos_scores = read_scores(root / "outputs" / "oos" / "M7" / "scores.csv")
    assert closes(oos_scores).min() == last_is_week + pd.Timedelta(days=7)  # right after the last In-Sample scored week
    check = report["reproduction_2019q4"]["M7"]
    assert check["within_tolerance"] is True and check["signals_identical"] is True
    assert check["max_abs_diff"] <= 1e-12


# ---------------------------------------------------------------- b. the frozen value


def test_frozen_value_is_the_last_in_sample_selection_row(script, ran, project, tmp_path):
    root, cfg, lock = ran["root"], ran["cfg"], ran["lock"]
    selection = pd.read_csv(root / "outputs" / "walkforward" / "M7" / "selection.csv")
    last = last_selection_row(root)
    expected = models.round2_frozen_value("M7", selection, cfg)
    on_disk = json.loads((root / "FROZEN.lock").read_text(encoding="utf-8"))["frozen_values"]["M7"]
    for frozen in (lock["frozen_values"]["M7"], on_disk):
        assert frozen["value"] == expected
        assert {k: type(v) for k, v in frozen["value"].items()} == {k: type(v) for k, v in expected.items()}
        assert frozen["value"]["alpha"] == last["chosen_alpha"]
        assert frozen["value"]["half_life_weeks"] == last["chosen_half_life_weeks"]
        assert frozen["chosen"] == last["chosen"]
        assert (frozen["test_year"], frozen["refit"]) == (int(last["test_year"]), int(last["refit"]))
        assert frozen["test_start"] == str(last["test_start"])
    assert isinstance(on_disk["value"]["half_life_weeks"], int) and isinstance(on_disk["value"]["alpha"], int | float)
    assert script.frozen_value(project["root"], cfg, "M7") == lock["frozen_values"]["M7"]


def test_frozen_value_types_are_the_grids_after_the_json_round_trip(script, ran):
    grid_types = {float(p["alpha"]): type(p["alpha"]) for p in models.round2_grid("M7", ran["cfg"])}
    value = json.loads((ran["root"] / "FROZEN.lock").read_text(encoding="utf-8"))["frozen_values"]["M7"]["value"]
    assert type(value["alpha"]) is grid_types[float(value["alpha"])]  # 10 stays int, 0.1 stays float
    assert type(value["half_life_weeks"]) is int


def test_oos_scores_equal_an_independent_walkforward_at_the_frozen_value(script, ran):
    root, cfg, lock = ran["root"], ran["cfg"], ran["lock"]
    data, labels_h4, folds = oos_tables(script, ran)
    expected_folds = ran["report"]["folds"]
    assert [(f.test_year, f.refit) for f in folds] == [(f["test_year"], f["refit"]) for f in expected_folds]
    independent = models.walkforward_round2("M7", data, labels_h4, folds, cfg, value=lock["frozen_values"]["M7"]["value"])[0]
    oos = read_scores(root / "outputs" / "oos" / "M7" / "scores.csv")
    last_is_week = pd.Timestamp(ran["report"]["last_in_sample_scored_week"])
    after = independent.loc[closes(independent) > last_is_week]
    assert after.index.equals(oos.index)
    assert np.allclose(oos.to_numpy(), after.to_numpy(), atol=1e-12, rtol=0)


# ---------------------------------------------------------------- c. purging by the 4-week label_end


def test_every_oos_fit_is_purged_by_the_four_week_label_end(script, ran):
    root = ran["root"]
    h4 = pd.read_csv(root / "data" / "processed" / "oos" / "labels_h4.csv", index_col=[0, 1], parse_dates=[0, "label_end"])
    four_week = []
    for label_end, fold in ran["purged"]:
        ends = pd.to_datetime(label_end)
        if ends.index.isin(h4.index).all() and (ends.to_numpy() == h4.loc[ends.index, "label_end"].to_numpy()).all():
            four_week.append((ends, fold))
    folds = ran["report"]["folds"]
    assert len(four_week) == len(folds)  # fixed value: one fit per refit
    for (ends, fold), expected in zip(four_week, folds, strict=True):
        assert fold.purge_end == pd.Timestamp(expected["purge_end"])
        assert ends.max() <= fold.purge_end
    assert any(ends.max() > IS_END for ends, _ in four_week)  # labels realised after 2019-12-27 are used by later folds
    assert max(ends.max() for ends, _ in four_week[:1]) <= four_week[0][1].purge_end


# ---------------------------------------------------------------- d. no real data is read


def test_no_file_of_the_repository_data_folder_is_opened(script, ran):
    assert ran["opened"], "the recorder saw no open() call"
    assert any(under(p, ran["root"]) for p in ran["opened"])
    inside = [p for p in ran["opened"] if under(p, ROOT / "data")]
    assert inside == []
    assert repo_state() == ran["repo_state"]  # each file identical, or still absent (S45-1)


# ---------------------------------------------------------------- e. the access log


def test_one_access_entry_per_run_and_a_second_plain_run_is_refused(script, ran):
    root = ran["root"]
    log = root / "outputs" / "oos_access_log.json"
    assert len(json.loads(log.read_text(encoding="utf-8"))) == 1
    with pytest.raises(SystemExit):
        script.run_oos(root)
    assert len(json.loads(log.read_text(encoding="utf-8"))) == 1


# ---------------------------------------------------------------- f. smoothing across the boundary


@pytest.mark.parametrize("fold_index", [0, 1])
def test_smoothing_uses_only_information_known_at_t(script, ran, fold_index):
    cfg, lock = ran["cfg"], ran["lock"]
    data, labels_h4, folds = oos_tables(script, ran)
    value = lock["frozen_values"]["M7"]["value"]
    fold = folds[fold_index]
    base = models.walkforward_round2("M7", data, labels_h4, [fold], cfg, value=value)[0]

    def later(index) -> np.ndarray:
        return np.asarray(pd.DatetimeIndex(index.get_level_values("date_close")) > fold.test_end)

    features_ = data.features.copy()
    mask = later(features_.index)
    assert mask.any()
    features_.loc[mask] = features_.loc[mask].to_numpy(dtype="float64") * -2.0 + 0.7
    states = data.states.copy()
    state_mask = later(states.index)
    assert state_mask.any()
    for column in states.columns:
        new = 1.0 - states[column] if column == "BEAR24" else states[column] * 1.5 + 0.37
        states.loc[state_mask, column] = new[state_mask]
    kept = labels_h4[pd.to_datetime(labels_h4["label_end"]) <= fold.purge_end]
    assert len(kept) < len(labels_h4)
    perturbed = models.walkforward_round2("M7", models.LadderData(features=features_, states=states, labels=data.labels,
                                                                   momentum=data.momentum), kept, [fold], cfg, value=value)[0]
    assert perturbed.index.equals(base.index)
    assert np.allclose(perturbed.to_numpy(), base.to_numpy(), atol=1e-12, rtol=0, equal_nan=True)

    # the test is meaningful: the first Out-of-Sample week's smoothing window reaches back into In-Sample weeks
    half_life = value["half_life_weeks"]
    lags = int(cfg["round2"]["smoothing"]["lags_per_half_life"])
    assert lags == 3 and len(models.smoothing_weights(half_life, lags)) > 1
    calendar = pd.DatetimeIndex(data.states.index.get_level_values("date_close"))
    first_oos = calendar[calendar > pd.Timestamp(ran["report"]["last_in_sample_scored_week"])][0]
    position = calendar.get_loc(first_oos)
    window = calendar[position - lags * half_life:position + 1]
    assert (window <= IS_END).sum() >= lags * half_life  # 3H lags before it are In-Sample weeks


# ---------------------------------------------------------------- g. run_models


@pytest.mark.parametrize("name", ["M6", "M7", "M8"])
def test_run_models_accepts_an_evaluated_round_2_candidate(script, name):
    cfg = load_config()
    gate = gate_of(cfg, {name: gate_row(name, True)}, selected=name)
    assert script.run_models(gate, cfg) == [name, "M0", "M0_star"]


def test_run_models_orders_round_1_then_round_2_then_the_fixed_rungs(script):
    cfg = load_config()
    rows = {n: gate_row(n, False) for n in ("M1", "M7", "M6", "M8")}
    assert script.run_models(gate_of(cfg, rows, selected="M0_star"), cfg) == ["M1", "M6", "M7", "M8", "M0", "M0_star"]


def test_run_models_refuses_an_evaluated_m9_naming_session_4_4_and_still_refuses_m5(script):
    cfg = load_config()
    with pytest.raises(SystemExit) as refused:
        script.run_models(gate_of(cfg, {"M9": gate_row("M9", True)}, selected="M9"), cfg)
    assert "M9" in str(refused.value) and "4.4" in str(refused.value)
    with pytest.raises(SystemExit, match="M5"):
        script.run_models(gate_of(cfg, {"M5": gate_row("M5", True)}, selected="M5"), cfg)


def test_tuned_rungs_include_the_round_2_candidates(script):
    assert {"M1", "M2", "M3", "M0_star", "M6", "M7", "M8"} <= set(script.TUNED)


# ---------------------------------------------------------------- h. the freeze and the round-2 artefacts


def test_lock_artefacts_hold_the_four_m7_files_and_the_four_week_labels(script, ran):
    artefacts = ran["lock"]["artefacts"]
    for file in M7_FILES:
        assert f"outputs/walkforward/M7/{file}" in artefacts, file
        assert artefacts[f"outputs/walkforward/M7/{file}"] == script.file_sha256(ran["root"] / "outputs" / "walkforward" / "M7" / file)
    assert "data/processed/labels_h4.csv" in artefacts
    assert ran["lock"]["models"] == ["M7", "M0", "M0_star"] and ran["lock"]["selected"] == "M7"


@pytest.mark.parametrize("file", M7_FILES)
def test_freeze_refuses_a_missing_walkforward_file_of_m7(script, project, tmp_path, file):
    root = copy_repo(project["root"], tmp_path / "project")
    (root / "outputs" / "walkforward" / "M7" / file).unlink()  # outputs/ is git-ignored: the tree stays clean
    assert git(root, "status", "--porcelain").strip() == ""
    with pytest.raises(SystemExit, match=rf"M7[/\\]{file}"):
        script.freeze(root)
    assert not (root / "FROZEN.lock").exists()
