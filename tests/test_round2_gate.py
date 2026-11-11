"""The §07 gate of both rounds (decisions S44-1, S44-2; Amendment 9 C3), tested from the decision log.

S44-1: src.stats.selection_gate(..., rounds=2) runs one gate over models.candidate_order + round2.candidate_order (M1, M2,
M3, M5, ENS, M6, M7, M8, M9) with one hurdle (M0): Sharpe >= Sharpe(M0) + selection.sharpe_uplift and drawdown >= M0's -
selection.mdd_tolerance for every candidate; P(uplift > 0) >= selection.bootstrap_prob (0.80) in round 1 and
round2.selection.bootstrap_prob (0.90) in round 2. Every row carries its round, every evaluated row its bootstrap
threshold; `selected` is the first passing candidate of the combined order, `round1_selected` the first passing round-1
candidate (the primary pre-registered result), each else M0_star. rounds=1 is unchanged.
05_train_walkforward.py --select checks M6, M7 and M8 exactly as S37-4 checks the round-1 backtests, keeps every key of
the S37-4 file and adds round1_selected, thresholds_round2, absent [M5, M9], a statement of both results and a rule naming
Amendment 9 C3. The file must pass 08_run_oos.py's check_gate and read_gate (08 loaded by path, read only).
S44-2: the round-2 human trial rows get only their empty is_sharpe and is_mdd cells filled; N of the DSR counts every
trial row and the PBO matrix holds the round-2 columns.

Synthetic data only: the fake project root of tests/test_select.py (round 1: 17 backtest folders, 16 human and 3 agent
trial rows) extended with the 16 round-2 backtest folders (M6, M7, M8 and the 13 fixed grid points of S41-5) and their
16 human trial rows (trial ids 20 to 35), all in temporary folders. Nothing under data/ or outputs/ of the repository is
read or written.
"""

import copy
import csv
import functools
import hashlib
import inspect
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import stats
from src.config import save_used
from src.models import ROUND2_RUNGS
from src.stats import deflated_sharpe_ratio, paired_block_bootstrap, pbo_cscv, selection_gate
from src.vault import TRIAL_COLUMNS, append_trial
from tests import test_select as base

CFG = base.CFG
WEEKS = base.WEEKS
N_WEEKS = base.N_WEEKS
TRIAL_PATH = base.TRIAL_PATH
ROUND1_ORDER = list(CFG["models"]["candidate_order"])  # M1, M2, M3, M5, ENS
ROUND2_ORDER = list(CFG["round2"]["candidate_order"])  # M6, M7, M8, M9
FULL_ORDER = ROUND1_ORDER + ROUND2_ORDER
ROUND1_CANDIDATES = ("M1", "M2", "M3", "ENS")
ROUND2_CANDIDATES = ("M6", "M7", "M8")
ABSENT2 = ("M5", "M9")
FALLBACK = "M0_star"
ROUND2_FIRST_TRIAL = 20  # round-1 rows: human 1-16, agent 17-19
ROUND1_RULE = "pre-registration §07 steps 1 to 5; headline Sharpe of Amendment 6 C1; M5 absent (S33-19, S37-1)"
GATE_KEYS_ROUND1 = base.GATE_KEYS | {"rule"}  # the S37-4 file as 05 wrote it before session 4.4
GATE_KEYS_ROUND2 = GATE_KEYS_ROUND1 | {"round1_selected", "thresholds_round2"}
RUN_MODELS_ALL = ["M1", "M2", "M3", "ENS", "M6", "M7", "M8", "M0", "M0_star"]


def s05():
    return base.s05()


@functools.cache
def s08():
    return base.load_script("run_oos_for_round2_gate", "08_run_oos.py")


@pytest.fixture(scope="module")
def script():
    return s05()


def assert_close(actual, expected, rel: float = 1e-12, where: str = "") -> None:
    base.assert_close(actual, expected, rel, where)


def mentions(text: str, name: str) -> int:
    """Position of the first mention of a model in a statement (M0_star may be written M0*), or -1."""
    spellings = [name] + (["M0*"] if name == FALLBACK else [])
    found = [text.find(s) for s in spellings if s in text]
    return min(found) if found else -1


def last_mention(text: str, name: str) -> int:
    spellings = [name] + (["M0*"] if name == FALLBACK else [])
    return max(text.rfind(s) for s in spellings)


# ---------------------------------------------------------------- the round-2 part of the fake root


def round2_names() -> list[str]:
    """The 16 round-2 backtest names of S41-5: the rungs M6, M7, M8, then the fixed grid points."""
    return list(ROUND2_RUNGS) + list(s05().round2_fixed_names(CFG))


def make_nets2(passing2=()) -> dict[str, pd.Series]:
    """Weekly net returns of the round-2 names: candidates in `passing2` beat M0 by a strong drift, the other candidates
    lose to it; the fixed grid points are independent noise."""
    m0 = base.make_nets()["M0"].to_numpy()
    values = {}
    for i, name in enumerate(round2_names()):
        rng = np.random.default_rng(300 + i)
        if name in ROUND2_CANDIDATES:
            if name in passing2:
                values[name] = m0 + 0.004 + rng.normal(0.0, 0.002, N_WEEKS)
            else:
                values[name] = m0 - 0.003 + rng.normal(0.0, 0.004, N_WEEKS)
        else:
            values[name] = rng.normal(0.0, 0.01, N_WEEKS)
    return {name: pd.Series(v, index=WEEKS, name="net") for name, v in values.items()}


def write_trial_log2(root: Path, *, filled: dict | None = None, filled2: dict | None = None, skip2: tuple = ()) -> Path:
    """The round-1 trial log of test_select.py (ids 1-19), then one human row per round-2 name (ids 20-35)."""
    path = base.write_trial_log(root, filled=filled)
    for trial_id, name in enumerate(round2_names(), start=ROUND2_FIRST_TRIAL):
        if name not in skip2:
            append_trial(base.human_row(name, trial_id, filled2), path=path)
    return path


def make_root2(root: Path, passing=(), passing2=()) -> dict[str, pd.Series]:
    nets = base.make_root(root, passing=passing)
    nets2 = make_nets2(passing2)
    for name in round2_names():
        base.write_walkforward_summary(root, name)
        base.write_backtest(root, name, nets2[name])
    write_trial_log2(root)
    return {**nets, **nets2}


def round1_filled(root: Path) -> dict:
    """The round-1 metric cells as the S37-9 run filled them (the trial log of S44-2's starting point)."""
    return {name: base.expected_metrics(root, name) for name in base.human_names()}


def expected_gate2(root: Path) -> dict:
    """src.stats.selection_gate(rounds=2) on the weekly.csv files as written, rf of M0's weekly.csv, M5 and M9 absent."""
    results = {name: base.backtest_net(root, name) for name in (*ROUND1_CANDIDATES, *ROUND2_CANDIDATES)}
    m0 = base.backtest_net(root, "M0")
    rf = base.read_weekly(root / "outputs" / "backtests" / "M0" / "weekly.csv")["rf"]
    return selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)


SCENARIOS = {  # name: (round-1 passing, round-2 passing, selected, round1_selected)
    "round2_only": ((), ("M7",), "M7", FALLBACK),
    "both_rounds": (("M2",), ("M6",), "M2", "M2"),
    "none": ((), (), FALLBACK, FALLBACK),
}


@pytest.fixture(scope="module")
def roots(tmp_path_factory) -> dict[str, Path]:
    """One read-only root per scenario."""
    out = {}
    for name, (passing, passing2, _, _) in SCENARIOS.items():
        out[name] = tmp_path_factory.mktemp(f"round2_{name}")
        make_root2(out[name], passing, passing2)
    return out


@pytest.fixture(scope="module")
def gates(roots) -> dict[str, dict]:
    return {name: s05().gate_result(CFG, root, rounds=2) for name, root in roots.items()}


@pytest.fixture
def root2(tmp_path) -> Path:
    """A fresh root where only M7 passes, for the tests that change files."""
    make_root2(tmp_path / "project", passing=(), passing2=("M7",))
    return tmp_path / "project"


# ================================================================ src.stats.selection_gate, rounds=2


def stats_inputs(good=()) -> tuple[dict[str, pd.Series], pd.Series, pd.Series]:
    """Candidates M1, M2, M3, ENS, M6, M7, M8: those in `good` pass the Sharpe and drawdown tests by a wide margin, the
    others fail the Sharpe test."""
    m0 = base.make_nets()["M0"]
    results = {}
    for i, name in enumerate((*ROUND1_CANDIDATES, *ROUND2_CANDIDATES)):
        rng = np.random.default_rng(900 + i)
        if name in good:
            values = m0.to_numpy() + 0.004 + rng.normal(0.0, 0.002, N_WEEKS)
        else:
            values = m0.to_numpy() - 0.003 + rng.normal(0.0, 0.004, N_WEEKS)
        results[name] = pd.Series(values, index=WEEKS, name=name)
    return results, m0, base.rf_series()


def round1_only(results: dict) -> dict:
    return {name: s for name, s in results.items() if name in ROUND1_CANDIDATES}


@pytest.fixture
def chosen_p(monkeypatch):
    """Replace src.stats.paired_block_bootstrap: the real computation, with P(uplift > 0) at the main block
    (selection.bootstrap_block) set per candidate. Returns a function taking (results, {name: P})."""
    real = stats.paired_block_bootstrap
    main_block = CFG["selection"]["bootstrap_block"]

    def install(results: dict, probabilities: dict) -> None:
        def fake(candidate, baseline, n_resamples=5000, block=4, seed=42, *, rf=None, confidence=None):
            out = real(candidate, baseline, n_resamples, block, seed, rf=rf, confidence=confidence)
            if block == main_block:
                values = np.asarray(candidate, dtype=float)
                names = [n for n, s in results.items() if np.array_equal(values, s.to_numpy(dtype=float))]
                assert len(names) == 1, "the fake bootstrap could not identify the candidate"
                if names[0] in probabilities:
                    out["p_uplift_positive"] = float(probabilities[names[0]])
            return out

        monkeypatch.setattr(stats, "paired_block_bootstrap", fake)

    return install


def rows_by_name(gate: dict) -> dict[str, dict]:
    return {row["name"]: row for row in gate["candidates"]}


def test_selection_gate_default_is_round_1():
    assert inspect.signature(selection_gate).parameters["rounds"].default == 1


def test_p_085_passes_a_round_1_candidate_and_fails_a_round_2_candidate(chosen_p):
    results, m0, rf = stats_inputs(good=("M1", "M6"))
    chosen_p(results, {"M1": 0.85, "M6": 0.85})
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    rows = rows_by_name(gate)
    assert rows["M1"]["p_uplift_positive"] == 0.85 and rows["M6"]["p_uplift_positive"] == 0.85
    assert rows["M1"]["passes_sharpe"] and rows["M1"]["passes_mdd"]
    assert rows["M6"]["passes_sharpe"] and rows["M6"]["passes_mdd"]
    assert rows["M1"]["passes_bootstrap"] is True and rows["M1"]["passes"] is True
    assert rows["M6"]["passes_bootstrap"] is False and rows["M6"]["passes"] is False
    assert rows["M1"]["bootstrap_threshold"] == pytest.approx(0.80)
    assert rows["M6"]["bootstrap_threshold"] == pytest.approx(0.90)
    assert gate["selected"] == "M1" and gate["round1_selected"] == "M1"


def test_a_round_2_candidate_at_085_is_not_selected(chosen_p):
    """Only M6 passes the Sharpe and drawdown tests; at P = 0.85 it fails round 2's 0.90, so M0* is traded."""
    results, m0, rf = stats_inputs(good=("M6",))
    chosen_p(results, {"M6": 0.85})
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    assert gate["selected"] == FALLBACK and gate["round1_selected"] == FALLBACK
    assert not rows_by_name(gate)["M6"]["passes"]


def test_a_round_1_candidate_at_085_is_selected(chosen_p):
    results, m0, rf = stats_inputs(good=("M3",))
    chosen_p(results, {"M3": 0.85})
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    assert gate["selected"] == "M3" and gate["round1_selected"] == "M3"


@pytest.mark.parametrize(("name", "p", "passes"), [("M2", 0.80, True), ("M2", 0.7998, False), ("M7", 0.90, True),
                                                   ("M7", 0.8998, False), ("M8", 0.95, True), ("ENS", 0.95, True)])
def test_the_bootstrap_threshold_is_inclusive_and_per_round(chosen_p, name, p, passes):
    results, m0, rf = stats_inputs(good=(name,))
    chosen_p(results, {name: p})
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    row = rows_by_name(gate)[name]
    assert row["passes_bootstrap"] is passes and row["passes"] is passes
    assert gate["selected"] == (name if passes else FALLBACK)


def test_the_sharpe_and_drawdown_tests_apply_to_round_2(chosen_p):
    """A round-2 candidate with P = 0.99 that loses to M0 fails: the uplift and the drawdown tolerance are round 1's."""
    results, m0, rf = stats_inputs(good=())
    chosen_p(results, {"M6": 0.99, "M7": 0.99, "M8": 0.99})
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    for name in ROUND2_CANDIDATES:
        row = rows_by_name(gate)[name]
        assert row["passes_bootstrap"] and not row["passes_sharpe"] and not row["passes"]
    assert gate["selected"] == FALLBACK


def test_every_verdict_follows_from_its_numbers_and_its_rounds_thresholds():
    results, m0, rf = stats_inputs(good=("M2", "M7"))
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    sel = CFG["selection"]
    for row in gate["candidates"]:
        if row["status"] != "evaluated":
            continue
        threshold = sel["bootstrap_prob"] if row["round"] == 1 else CFG["round2"]["selection"]["bootstrap_prob"]
        assert row["bootstrap_threshold"] == pytest.approx(threshold)
        assert row["passes_sharpe"] == (row["sharpe"] >= row["sharpe_m0"] + sel["sharpe_uplift"])
        assert row["passes_mdd"] == (row["mdd"] >= row["mdd_m0"] - sel["mdd_tolerance"])
        assert row["passes_bootstrap"] == (row["p_uplift_positive"] >= threshold)
        assert row["passes"] == (row["passes_sharpe"] and row["passes_mdd"] and row["passes_bootstrap"])
    assert len({(row["sharpe_m0"], row["mdd_m0"]) for row in gate["candidates"] if row["status"] == "evaluated"}) == 1


def test_rounds_2_order_and_round_fields():
    results, m0, rf = stats_inputs(good=("M1",))
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    assert [row["name"] for row in gate["candidates"]] == FULL_ORDER
    assert FULL_ORDER == ["M1", "M2", "M3", "M5", "ENS", "M6", "M7", "M8", "M9"]
    assert [row["round"] for row in gate["candidates"]] == [1, 1, 1, 1, 1, 2, 2, 2, 2]
    rows = rows_by_name(gate)
    assert rows["M5"]["status"] == "absent" and rows["M9"]["status"] == "absent"
    for name in (*ROUND1_CANDIDATES, *ROUND2_CANDIDATES):
        assert rows[name]["status"] == "evaluated"
        assert "bootstrap_threshold" in rows[name]
    assert set(gate) == {"selected", "candidates", "round1_selected"}


def test_m9_absent_works_and_an_evaluated_m9_would_be_a_candidate():
    results, m0, rf = stats_inputs(good=())
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    m9 = rows_by_name(gate)["M9"]
    assert m9["status"] == "absent" and m9["round"] == 2
    extra = dict(results, M9=results["M8"].rename("M9") + 0.0)
    gate9 = selection_gate(extra, m0, CFG, rf=rf, absent=("M5",), rounds=2)
    assert rows_by_name(gate9)["M9"]["status"] == "evaluated"
    assert rows_by_name(gate9)["M9"]["bootstrap_threshold"] == pytest.approx(0.90)


@pytest.mark.parametrize(("good", "selected", "round1_selected"), [
    (("ENS", "M6"), "ENS", "ENS"),
    (("M3", "M8"), "M3", "M3"),
    (("M7", "M8"), "M7", FALLBACK),
    (("M8",), "M8", FALLBACK),
    ((), FALLBACK, FALLBACK),
])
def test_selected_is_the_first_passing_candidate_of_the_combined_order(good, selected, round1_selected):
    """Real bootstrap: the good candidates pass every test (P close to 1). A round-2 candidate is traded only when no
    round-1 candidate passes."""
    results, m0, rf = stats_inputs(good=good)
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    assert gate["selected"] == selected
    assert gate["round1_selected"] == round1_selected
    for name in good:
        assert rows_by_name(gate)[name]["passes"]


@pytest.mark.parametrize("good", [("ENS", "M6"), ("M7",), ("M2", "M3"), ()])
def test_round1_selected_and_round_1_rows_are_independent_of_round_2(good):
    """Round 1 inside rounds=2 is the round-1 gate: same verdict, same rows apart from the added round and threshold."""
    results, m0, rf = stats_inputs(good=good)
    gate2 = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    gate1 = selection_gate(round1_only(results), m0, CFG, rf=rf, absent=("M5",), rounds=1)
    assert gate2["round1_selected"] == gate1["selected"]
    rows2 = rows_by_name(gate2)
    for row in gate1["candidates"]:
        stripped = {k: v for k, v in rows2[row["name"]].items() if k not in ("round", "bootstrap_threshold")}
        assert_close(stripped, row, where=row["name"])
        assert rows2[row["name"]]["round"] == 1


def test_round_2_rows_use_the_same_bootstrap_as_round_1():
    """5,000 resamples, block 4, seed config.seed, block 8 as information (S44-1, S37-4)."""
    results, m0, rf = stats_inputs(good=("M7",))
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    sel = CFG["selection"]
    for name in ROUND2_CANDIDATES:
        row = rows_by_name(gate)[name]
        main = paired_block_bootstrap(results[name], m0, sel["bootstrap_resamples"], sel["bootstrap_block"],
                                      int(CFG["seed"]), rf=rf)
        info = paired_block_bootstrap(results[name], m0, sel["bootstrap_resamples"], sel["bootstrap_block_sensitivity"],
                                      int(CFG["seed"]), rf=rf)
        assert row["p_uplift_positive"] == pytest.approx(main["p_uplift_positive"], abs=0)
        assert row["p_uplift_positive_sensitivity"] == pytest.approx(info["p_uplift_positive"], abs=0)


@pytest.mark.parametrize("good", [("M1",), ("M2", "ENS"), ()])
def test_rounds_1_output_is_unchanged(good):
    results, m0, rf = stats_inputs(good=good)
    r1 = round1_only(results)
    default = selection_gate(r1, m0, CFG, rf=rf, absent=("M5",))
    explicit = selection_gate(r1, m0, CFG, rf=rf, absent=("M5",), rounds=1)
    assert set(explicit) == {"selected", "candidates"}
    assert_close(explicit, default, where="rounds=1")
    for row in explicit["candidates"]:
        assert "round" not in row and "bootstrap_threshold" not in row
    assert [row["name"] for row in explicit["candidates"]] == ROUND1_ORDER


def test_rounds_2_output_passes_08s_check_gate():
    results, m0, rf = stats_inputs(good=("M7",))
    gate = selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    checked = s08().check_gate({"selected": gate["selected"], "candidates": gate["candidates"]}, CFG)
    assert checked["complete"] is True
    assert checked["names"] == FULL_ORDER
    assert checked["selected"] == gate["selected"] == "M7"
    assert checked["round1_selected"] == gate["round1_selected"] == FALLBACK


def test_rounds_2_needs_every_round_2_name_in_results_or_absent():
    results, m0, rf = stats_inputs()
    with pytest.raises(ValueError):
        selection_gate(results, m0, CFG, rf=rf, absent=("M5",), rounds=2)  # M9 neither evaluated nor absent
    without_m6 = {k: v for k, v in results.items() if k != "M6"}
    with pytest.raises(ValueError):
        selection_gate(without_m6, m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    with pytest.raises(ValueError):
        selection_gate(round1_only(results), m0, CFG, rf=rf, absent=("M5",), rounds=2)


def test_unknown_names_are_refused():
    results, m0, rf = stats_inputs()
    with pytest.raises(ValueError):
        selection_gate(dict(results, M4=results["M1"]), m0, CFG, rf=rf, absent=ABSENT2, rounds=2)
    with pytest.raises(ValueError):  # under rounds=1, a round-2 name is not a candidate
        selection_gate(results, m0, CFG, rf=rf, absent=("M5",), rounds=1)


@pytest.mark.parametrize("rounds", [0, 3, -1])
def test_rounds_other_than_1_or_2_are_refused(rounds):
    results, m0, rf = stats_inputs()
    with pytest.raises(ValueError):
        selection_gate(results, m0, CFG, rf=rf, absent=ABSENT2, rounds=rounds)


# ================================================================ 05_train_walkforward.py, rounds=2


def test_round2_fixture_has_16_names_and_16_distinct_hashes():
    names = round2_names()
    assert len(names) == 16
    assert len({base.digest_of(name) for name in names}) == 16
    assert not {base.digest_of(name) for name in names} & {base.digest_of(name) for name in base.names()}


def test_gate_result_and_select_default_to_both_rounds(script):
    assert inspect.signature(script.gate_result).parameters["rounds"].default == 2
    assert inspect.signature(script.select).parameters["rounds"].default == 2
    assert tuple(script.GATE_MODELS) == ("M0", "M1", "M2", "M3", "ENS", "M6", "M7", "M8")
    assert tuple(script.ROUND1_GATE_MODELS) == ("M0", "M1", "M2", "M3", "ENS")
    assert tuple(script.ABSENT) == ABSENT2 and tuple(script.ROUND1_ABSENT) == ("M5",)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_gate_result_rounds_2_keys(gates, scenario):
    assert GATE_KEYS_ROUND2 <= set(gates[scenario])


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_gate_result_rounds_2_selected_round1_selected_and_fallback(gates, scenario):
    _, _, selected, round1_selected = SCENARIOS[scenario]
    gate = gates[scenario]
    assert gate["selected"] == selected
    assert gate["round1_selected"] == round1_selected
    assert gate["fallback"] is (selected == FALLBACK)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_gate_result_rounds_2_candidates_are_selection_gates_unchanged(roots, gates, scenario):
    expected = expected_gate2(roots[scenario])
    assert_close(gates[scenario]["candidates"], expected["candidates"], where="candidates")
    assert gates[scenario]["selected"] == expected["selected"]
    assert gates[scenario]["round1_selected"] == expected["round1_selected"]


def test_gate_result_rounds_2_thresholds(gates):
    gate = gates["round2_only"]
    assert gate["thresholds"] == CFG["selection"]
    assert gate["thresholds_round2"] == {"bootstrap_prob": CFG["round2"]["selection"]["bootstrap_prob"]}
    assert gate["thresholds_round2"] == {"bootstrap_prob": 0.9}


def test_gate_result_rounds_2_absent_and_order(gates):
    gate = gates["round2_only"]
    assert list(gate["absent"]) == ["M5", "M9"]
    assert [row["name"] for row in gate["candidates"]] == FULL_ORDER
    rows = rows_by_name(gate)
    assert rows["M5"]["status"] == "absent" and rows["M9"]["status"] == "absent"
    for name in (*ROUND1_CANDIDATES, *ROUND2_CANDIDATES):
        assert rows[name]["status"] == "evaluated"
        assert rows[name]["round"] == (1 if name in ROUND1_CANDIDATES else 2)


def test_gate_result_rounds_2_rule_names_amendment_9_c3(gates):
    for gate in gates.values():
        assert "Amendment 9 C3" in gate["rule"]


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_gate_result_rounds_2_statement_names_both_results(gates, scenario):
    """Round 1's verdict first, labelled primary; then the traded model (S44-1)."""
    _, _, selected, round1_selected = SCENARIOS[scenario]
    statement = gates[scenario]["statement"]
    assert "primary" in statement.lower()
    assert "traded" in statement.lower()
    assert mentions(statement, round1_selected) >= 0
    assert mentions(statement, selected) >= 0
    assert mentions(statement, round1_selected) <= last_mention(statement, selected)


def test_gate_result_rounds_2_statement_of_a_round_2_trade(gates):
    statement = gates["round2_only"]["statement"]
    assert mentions(statement, FALLBACK) < last_mention(statement, "M7")
    # audit finding (a) of session 4.4: when only a round-2 candidate passes, the round-1 sentence gives round 1's
    # verdict (M0*) without claiming that M0* is traded; only the both-rounds sentence names the traded model
    round1, both = statement.split("Both rounds", 1)
    assert "is traded" not in round1 and "M0*" in round1 and "M7" in both and "is traded" in both


def test_gate_result_rounds_2_m0_seed_weeks_and_rf(roots, gates):
    gate = gates["round2_only"]
    row = next(r for r in expected_gate2(roots["round2_only"])["candidates"] if r["name"] == "M7")
    values = base.numbers_in(gate["m0"])
    for target in (row["sharpe_m0"], row["sharpe_m0_zero_cost"], row["mdd_m0"]):
        assert base.contains_close(values, target, rel=1e-9)
    assert gate["seed"] == CFG["seed"]
    assert gate["weeks"] == N_WEEKS
    assert gate["first_week"] == base.FRIDAYS[0].strftime("%Y-%m-%d") and gate["last_week"] == "2019-12-13"
    assert gate["last_realised_on"] == "2019-12-23"
    summary = json.loads((roots["round2_only"] / "outputs" / "backtests" / "M0" / "summary.json").read_text("utf-8"))
    assert gate["rf_tbill_annual"] == pytest.approx(summary["rf_tbill_annual"], rel=1e-12)
    assert gate["rf_source"]


@pytest.mark.parametrize("name", ["M0", "M1", "M2", "M3", "ENS", "M6", "M7", "M8"])
def test_gate_result_rounds_2_inputs_hold_each_spec_hash_and_weekly_sha256(roots, gates, name):
    entry = gates["round2_only"]["inputs"][name]
    assert entry["spec_hash"] == base.digest_of(name)
    weekly = roots["round2_only"] / "outputs" / "backtests" / name / "weekly.csv"
    assert hashlib.sha256(weekly.read_bytes()).hexdigest() in entry.values()


def test_gate_result_rounds_2_does_not_write_the_gate_file(script, roots, gates):
    for root in roots.values():
        assert not (root / script.GATE_FILE).exists()


# ---------------------------------------------------------------- rounds=1 on a root that holds round 2


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_gate_result_rounds_1_is_the_s37_4_file(script, roots, scenario):
    """rounds=1 behaves exactly as before session 4.4, round-2 folders present or not."""
    root = roots[scenario]
    _, _, _, round1_selected = SCENARIOS[scenario]
    gate = script.gate_result(CFG, root, rounds=1)
    assert set(gate) == GATE_KEYS_ROUND1
    assert list(gate["absent"]) == ["M5"]
    assert gate["rule"] == ROUND1_RULE
    assert gate["thresholds"] == CFG["selection"]
    assert [row["name"] for row in gate["candidates"]] == ROUND1_ORDER
    assert all("round" not in row and "bootstrap_threshold" not in row for row in gate["candidates"])
    assert set(gate["inputs"]) == {"M0", *ROUND1_CANDIDATES}
    assert gate["selected"] == round1_selected
    assert_close(gate["candidates"], base.expected_gate(root)["candidates"], where="candidates")
    if round1_selected == FALLBACK:
        assert gate["statement"] == base.FALLBACK_STATEMENT and gate["fallback"] is True
    else:
        assert gate["statement"] == (f"{round1_selected} is the first candidate to pass all three tests of the §07 gate "
                                     "and is traded (pre-registration §07 step 4).")


def test_rounds_1_ignores_a_round_2_setting_and_rounds_2_refuses_it(script, roots):
    """A change of round2.models.M8 stales M8's spec_hash although every used.yaml still matches (S40-1): rounds=2
    refuses, rounds=1 (which reads only M0, M1, M2, M3, ENS) is unaffected."""
    other = copy.deepcopy(CFG)
    other["round2"]["models"]["M8"]["learning_rate"] = 0.05
    assert base.digest_of("M8", other) != base.digest_of("M8")
    assert base.digest_of("M1", other) == base.digest_of("M1")
    with pytest.raises(SystemExit):
        script.gate_result(other, roots["round2_only"], rounds=2)
    assert script.gate_result(other, roots["round2_only"], rounds=1)["selected"] == FALLBACK


# ---------------------------------------------------------------- every S37-4 check applies to a round-2 model


def _stale_walkforward_m7(root):
    base.write_walkforward_summary(root, "M7", digest=base.digest_of("M6"))


def _stale_backtest_m7(root):
    base.write_backtest(root, "M7", make_nets2(("M7",))["M7"], digest=base.digest_of("M8"))


def _m8_on_other_weeks(root):
    base.write_backtest(root, "M8", make_nets2(("M7",))["M8"].iloc[1:])


def _m6_rf_mismatch(root):
    net = make_nets2(("M7",))["M6"]
    base.write_backtest(root, "M6", net, weekly=base.weekly_frame(net, rf=base.rf_series() + 1e-9))


def _m6_used_yaml_of_another_model(root):
    save_used(base.s06().backtest_used(CFG, "M7"), root / "outputs" / "backtests" / "M6" / "used.yaml")


def _m8_missing(root):
    shutil.rmtree(root / "outputs" / "backtests" / "M8")


def _m7_not_in_trial_log(root):
    write_trial_log2(root, skip2=("M7",))


def _m6_summary_period_oos(root):
    base.write_backtest(root, "M6", make_nets2(("M7",))["M6"], period="OOS")


def _m8_other_baseline(root):
    base.write_backtest(root, "M8", make_nets2(("M7",))["M8"], baseline="20bps_5pct")


def _m7_weekly_row_oos(root):
    net = make_nets2(("M7",))["M7"]
    weekly = base.weekly_frame(net)
    weekly.iloc[-1, weekly.columns.get_loc("period")] = "OOS"
    base.write_backtest(root, "M7", net, weekly=weekly)


def _m6_realised_after_is_end(root):
    net = make_nets2(("M7",))["M6"]
    weekly = base.weekly_frame(net)
    weekly.iloc[-1, weekly.columns.get_loc("realised_on")] = pd.Timestamp("2019-12-30")
    base.write_backtest(root, "M6", net, weekly=weekly)


def _m7_net_nan(root):
    net = make_nets2(("M7",))["M7"]
    weekly = base.weekly_frame(net)
    weekly.iloc[10, weekly.columns.get_loc("net")] = np.nan
    base.write_backtest(root, "M7", net, weekly=weekly)


def _m8_without_rf(root):
    net = make_nets2(("M7",))["M8"]
    base.write_backtest(root, "M8", net, weekly=base.weekly_frame(net).drop(columns=["rf"]))


ROUND2_BREAKERS = [_stale_walkforward_m7, _stale_backtest_m7, _m8_on_other_weeks, _m6_rf_mismatch,
                   _m6_used_yaml_of_another_model, _m8_missing, _m7_not_in_trial_log, _m6_summary_period_oos,
                   _m8_other_baseline, _m7_weekly_row_oos, _m6_realised_after_is_end, _m7_net_nan, _m8_without_rf]


@pytest.mark.parametrize("breaker", ROUND2_BREAKERS, ids=lambda f: f.__name__.strip("_"))
def test_gate_result_rounds_2_refuses_a_stale_or_invalid_round_2_backtest(script, root2, breaker):
    breaker(root2)
    with pytest.raises(SystemExit):
        script.gate_result(CFG, root2, rounds=2)


@pytest.mark.parametrize("breaker", [_stale_backtest_m7, _m8_on_other_weeks, _m6_rf_mismatch, _m8_missing],
                         ids=lambda f: f.__name__.strip("_"))
def test_select_rounds_2_writes_nothing_when_a_round_2_check_fails(script, root2, breaker):
    breaker(root2)
    gate_file, bias_file = root2 / script.GATE_FILE, root2 / script.BIAS_FILE
    gate_file.parent.mkdir(parents=True, exist_ok=True)
    gate_file.write_bytes(b"old\n")
    log_before = base.trial_bytes(root2)
    with pytest.raises(SystemExit):
        script.select(CFG, root2, rounds=2)
    assert gate_file.read_bytes() == b"old\n"
    assert not bias_file.exists()
    assert base.trial_bytes(root2) == log_before
    assert [p for p in root2.rglob("*.tmp")] == []


def test_select_rounds_2_refuses_once_frozen_lock_exists(script, root2):
    (root2 / "FROZEN.lock").write_text("{}\n", encoding="utf-8")
    before = base.trial_bytes(root2)
    with pytest.raises(SystemExit, match="FROZEN.lock"):
        script.select(CFG, root2, rounds=2)
    assert base.trial_bytes(root2) == before
    assert not (root2 / script.GATE_FILE).exists()


# ---------------------------------------------------------------- the written file and 08_run_oos.py


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_select_rounds_2_file_passes_08s_check_gate_read_gate_and_run_models(script, tmp_path, scenario):
    passing, passing2, selected, round1_selected = SCENARIOS[scenario]
    root = tmp_path / "project"
    make_root2(root, passing, passing2)
    result = script.select(CFG, root, rounds=2)
    written = json.loads((root / script.GATE_FILE).read_text(encoding="utf-8"))
    assert_close(written, json.loads(json.dumps(result["gate"], default=float)), where="gate")
    assert written["selected"] == selected and written["round1_selected"] == round1_selected
    checked = s08().check_gate(written, CFG)
    assert checked["complete"] is True
    assert checked["names"] == FULL_ORDER
    assert checked["selected"] == selected
    assert checked["round1_selected"] == round1_selected
    read = s08().read_gate(root, CFG)
    assert read == written
    assert s08().run_models(read, CFG) == RUN_MODELS_ALL


def test_select_rounds_2_file_is_sorted_json_with_lf(script, root2):
    script.select(CFG, root2, rounds=2)
    for name in (script.GATE_FILE, script.BIAS_FILE):
        raw = (root2 / name).read_bytes()
        assert b"\r" not in raw
        assert base.json_pairs_sorted(raw.decode("utf-8"))


def test_select_rounds_2_is_deterministic_and_rerunnable(script, root2):
    script.select(CFG, root2, rounds=2)
    paths = (script.GATE_FILE, script.BIAS_FILE, TRIAL_PATH)
    first = [(root2 / name).read_bytes() for name in paths]
    script.select(CFG, root2, rounds=2)
    assert [(root2 / name).read_bytes() for name in paths] == first


def test_a_rounds_1_file_is_refused_by_read_gate(script, root2):
    script.select(CFG, root2, rounds=1)
    written = json.loads((root2 / script.GATE_FILE).read_text(encoding="utf-8"))
    checked = s08().check_gate(written, CFG)
    assert checked["complete"] is False and checked["names"] == ROUND1_ORDER
    with pytest.raises(SystemExit, match="round-1"):
        s08().read_gate(root2, CFG)


def test_the_command_line_select_uses_both_rounds(script, monkeypatch, tmp_path):
    real = script.select
    calls = []

    def fake_select(*args, **kwargs):
        bound = inspect.signature(real).bind(*args, **kwargs)
        bound.apply_defaults()
        calls.append(dict(bound.arguments))
        return {"gate": {}, "bias": {}, "filled": 0}

    monkeypatch.setattr(script, "select", fake_select)
    monkeypatch.setattr(script, "print_selection", lambda result, *a, **k: None)
    monkeypatch.setattr(script, "ROOT", tmp_path)
    script.main(["--select"])
    assert len(calls) == 1
    assert calls[0]["rounds"] == 2
    assert Path(calls[0]["root"]) == tmp_path


def test_print_selection_reports_a_rounds_2_result(script, root2, capsys):
    result = script.select(CFG, root2, rounds=2)
    script.print_selection(result)
    out = capsys.readouterr().out
    assert "M7" in out
    for name in FULL_ORDER:
        assert name in out


# ================================================================ S44-2: trial metrics and diagnostics with round 2


def round2_line_numbers() -> range:
    """Line numbers (0 = header) of the round-2 human rows in the fake trial log."""
    return range(ROUND2_FIRST_TRIAL, ROUND2_FIRST_TRIAL + len(round2_names()))


def with_metrics(line: str, sharpe: str, mdd: str) -> str:
    row = next(csv.reader([line]))
    row[TRIAL_COLUMNS.index("is_sharpe")], row[TRIAL_COLUMNS.index("is_mdd")] = sharpe, mdd
    sink = io.StringIO()
    csv.writer(sink, lineterminator="\n").writerow(row)
    return sink.getvalue()[:-1]


@pytest.fixture
def prefilled_root(root2) -> Path:
    """root2 with the round-1 human rows already filled, as after S37-9: only the round-2 cells are empty."""
    write_trial_log2(root2, filled=round1_filled(root2))
    return root2


def test_trial_log_with_metrics_fills_only_the_round_2_cells(script, prefilled_root):
    old = (prefilled_root / TRIAL_PATH).read_text(encoding="utf-8")
    text, filled = script.trial_log_with_metrics(CFG, prefilled_root)
    assert filled == 32  # 16 round-2 human rows, two cells each
    old_lines, new_lines = base.trial_lines(old), base.trial_lines(text)
    assert len(new_lines) == len(old_lines) == 1 + 16 + 3 + 16
    changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)) if a != b]
    assert changed == list(round2_line_numbers())
    for i, name in zip(round2_line_numbers(), round2_names(), strict=True):
        assert new_lines[i] == with_metrics(old_lines[i], *base.expected_metrics(prefilled_root, name))
    assert base.trial_bytes(prefilled_root) == old.encode("utf-8")  # not written


def test_trial_log_with_metrics_fills_both_rounds_on_an_empty_log(script, root2):
    text, filled = script.trial_log_with_metrics(CFG, root2)
    assert filled == 64
    rows = base.parse(text)
    for trial_id, name in enumerate(round2_names(), start=ROUND2_FIRST_TRIAL):
        row = rows[trial_id - 1]
        assert row["trial_id"] == str(trial_id) and row["kind"] == "human"
        assert row["spec_hash"] == base.digest_of(name)
        assert (row["is_sharpe"], row["is_mdd"]) == base.expected_metrics(root2, name)
        assert repr(float(row["is_sharpe"])) == row["is_sharpe"]


def test_trial_log_with_metrics_refuses_a_round_2_cell_that_differs(script, root2):
    sharpe, mdd = base.expected_metrics(root2, "M7_a1_h4")
    write_trial_log2(root2, filled2={"M7_a1_h4": (repr(float(sharpe) + 0.01), mdd)})
    with pytest.raises(SystemExit):
        script.trial_log_with_metrics(CFG, root2)


def test_trial_log_with_metrics_keeps_an_equal_round_2_cell(script, root2):
    write_trial_log2(root2, filled=round1_filled(root2), filled2={"M8": base.expected_metrics(root2, "M8")})
    _, filled = script.trial_log_with_metrics(CFG, root2)
    assert filled == 30


def test_select_rounds_2_changes_only_the_empty_round_2_metric_cells(script, prefilled_root):
    old = (prefilled_root / TRIAL_PATH).read_text(encoding="utf-8")
    script.select(CFG, prefilled_root, rounds=2)
    new = (prefilled_root / TRIAL_PATH).read_text(encoding="utf-8")
    old_lines, new_lines = base.trial_lines(old), base.trial_lines(new)
    for i, (a, b) in enumerate(zip(old_lines, new_lines, strict=True)):
        if i not in round2_line_numbers():
            assert a == b, f"line {i} changed"
    old_rows, new_rows = base.parse(old), base.parse(new)
    assert len(old_rows) == len(new_rows) == 35
    for before, after in zip(old_rows, new_rows, strict=True):
        for column in TRIAL_COLUMNS:
            if column in ("is_sharpe", "is_mdd") and before["trial_id"] in {str(i) for i in round2_line_numbers()}:
                assert before[column] == "" and after[column] != ""
            else:
                assert after[column] == before[column], (before["trial_id"], column)


def test_trial_matrix_holds_the_round_2_columns(script, roots):
    matrix, columns, excluded = script.trial_matrix(CFG, roots["round2_only"])
    assert matrix.shape == (N_WEEKS, 18 + 16)
    hashes = {c["spec_hash"] for c in columns}
    assert {base.digest_of(name) for name in round2_names()} <= hashes
    assert sum(1 for c in columns if c["kind"] == "human") == 32
    by_hash = {c["spec_hash"]: [str(t) for t in c["trial_ids"]] for c in columns}
    for trial_id, name in enumerate(round2_names(), start=ROUND2_FIRST_TRIAL):
        assert by_hash[base.digest_of(name)] == [str(trial_id)]
    assert [str(e["trial_id"]) for e in excluded] == ["19"]


def test_select_rounds_2_bias_counts_every_trial_row_and_round_2_columns(script, root2):
    result = script.select(CFG, root2, rounds=2)
    bias = json.loads((root2 / script.BIAS_FILE).read_text(encoding="utf-8"))
    assert bias["selected"] == result["gate"]["selected"] == "M7"
    values = base.numbers_in(bias["dsr"])
    assert 35 in values  # N: every row of the trial log, both rounds
    assert 32 in values and 3 in values  # human and agent rows
    lists = [v for v in bias["matrix"].values() if isinstance(v, list)]
    assert any(len(v) == 34 for v in lists)
    matrix, _, _ = script.trial_matrix(CFG, root2)
    expected_dsr = deflated_sharpe_ratio(base.backtest_net(root2, "M7"), 35, trial_returns=matrix)
    assert bias["dsr"]["value"] == pytest.approx(expected_dsr, rel=1e-12, abs=1e-15)
    assert bias["pbo"]["value"] == pytest.approx(pbo_cscv(matrix, CFG["inference"]["pbo_blocks"]), rel=1e-12, abs=1e-15)


def test_select_rounds_2_of_the_fallback_uses_m0_stars_returns(script, tmp_path):
    make_root2(tmp_path / "f", passing=(), passing2=())
    script.select(CFG, tmp_path / "f", rounds=2)
    bias = json.loads((tmp_path / "f" / script.BIAS_FILE).read_text(encoding="utf-8"))
    gate = json.loads((tmp_path / "f" / script.GATE_FILE).read_text(encoding="utf-8"))
    assert gate["selected"] == FALLBACK and gate["fallback"] is True
    matrix, _, _ = script.trial_matrix(CFG, tmp_path / "f")
    expected = deflated_sharpe_ratio(base.backtest_net(tmp_path / "f", "M0_star"), 35, trial_returns=matrix)
    assert bias["selected"] == FALLBACK
    assert bias["dsr"]["value"] == pytest.approx(expected, rel=1e-12, abs=1e-15)
