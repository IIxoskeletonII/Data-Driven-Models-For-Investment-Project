"""Single Out-of-Sample run of the frozen system (protocol section 10, vault protocol steps 2 to 4), Phase 3.4 (Mattia,
decision S34-1), with the bug-fix rerun of Amendment 8 (decision S36-1).

  --freeze   writes FROZEN.lock: config hash, code commit, trial-log hash, the selected model (from the selection gate's
             output) and the SHA-256 of every model artefact and walk-forward output the run depends on (S34-3). Refuses
             a dirty working tree, an existing lock and an existing OOS access entry. The five signatures go into
             docs/decisions.md by hand at Gate 3.
  (no flag)  the run (S34-4 to S34-7): refuses unless FROZEN.lock exists and every hash matches the current tree, and
             unless outputs/oos_access_log.json is empty; appends its one timestamped entry; unlocks the vault
             (Vault.unlock); rebuilds the full-range tables through 03's unlock path into data/processed/oos/; continues
             the quarterly refits into the Out-of-Sample with each rung's last In-Sample grid value frozen (Amendment 6
             C2) for the selected model and every candidate (§07 step 6), M0 and M0*; backtests one continuous book per
             model across 2019-12-27 (Amendment 2 C5). The first run after the freeze is the run of record.
  --rerun ID a rerun to correct a bug found after the run of record (Amendment 8 C1, S36-1): refuses unless the run of
             record is logged and docs/decisions.md holds the rerun decision ID (fields Bug, Fix commit, Fix files), the
             fix commit comes after the freeze and changes exactly the Fix files, and nothing else changed since the
             freeze; then every check of the run, one more log entry naming ID, and the same run written to
             data/processed/oos_reruns/ID/ and outputs/oos_reruns/ID/, so the run of record's outputs stay untouched.

Inputs:  FROZEN.lock, config.yaml, docs/trial_log.csv, outputs/metrics/selection_gate.json (src.stats.selection_gate;
         the candidates of both rounds, Amendment 9 C3, S42-1),
         outputs/walkforward/<model>/, data/processed/ (the frozen In-Sample tables and daily prices), data/raw/
Outputs: FROZEN.lock (--freeze); outputs/oos_access_log.json, data/processed/oos/*.csv, outputs/oos/run.json and
         outputs/oos/<model>/{scores.csv, weekly.csv, metrics.csv, summary.json, used.yaml} (the run; git-ignored);
         the same under data/processed/oos_reruns/ID/ and outputs/oos_reruns/ID/ (--rerun ID)

Every function takes the project folder `root`, so the tests run the whole script on the synthetic market under a
temporary folder; main() works on the repository and is run on real data exactly once, at Gate 4.
"""

import argparse
import copy
import csv
import functools
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest import run as run_backtest
from src.config import ROOT, check_used, data_settings, load_config, save_used
from src.contracts import universe, validate_forward_returns, validate_scores
from src.data import DATE_FORMAT, file_stem, write_csv
from src.data import sha256 as file_sha256
from src.features import features_settings
from src.labels import label_end_by_week, walk_forward_folds
from src.metrics import period_metrics, tbill_weekly_returns
from src.models import ENS_MEMBERS, LadderData, ensemble_scores, grid, walkforward_rung, walkforward_settings
from src.sizing import signals_from_scores, size_book
from src.vault import Vault, logged_spec_hashes, spec_hash

CODE = Path(__file__).resolve().parent  # the scripts this file loads by path (03, 05, 06), whatever `root` is
LOCK_NAME = "FROZEN.lock"
LOCK_FORMAT = 1
OOS_LOG = "outputs/oos_access_log.json"
GATE_FILE = "outputs/metrics/selection_gate.json"
VAULT_LOG = "outputs/vault_access_log.jsonl"
TRIAL_LOG = "docs/trial_log.csv"
CONFIG = "config.yaml"
DECISIONS = "docs/decisions.md"
ALLOWED_AFTER_FREEZE = (LOCK_NAME, DECISIONS)  # the signatures of Gate 3 (S34-3)
RERUN_KEY = "rerun_decision"  # the log field naming a rerun's decision (Amendment 8 C1, S36-1)
RERUN_FIELDS = ("Bug", "Fix commit", "Fix files")  # the fields of a rerun decision (S36-1)
DECISION_ID = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")  # also a folder name on Windows and macOS
TABLES = ("features", "market_states", "labels", "momentum_variants", "sizing_betas", "forward_returns")
WALKFORWARD_FILES = ("scores.csv", "used.yaml", "summary.json", "selection.csv")
TUNED = ("M1", "M2", "M3", "M0_star")  # rungs whose grid value is frozen (Amendment 6 C2)
FIXED_RUNGS = ("M0", "M0_star")  # always run: the hurdle and the fallback (S34-6)
REPRODUCTION_TOLERANCE = 1e-12  # S34-2: numeric tolerance, never file hashes
WEEK_COLUMNS = ["date_open", "date_close"]


# -- scripts loaded by path (module names start with a digit) ------------------------------------------------------------


@functools.cache
def _script(filename: str):
    spec = importlib.util.spec_from_file_location(f"oos_{Path(filename).stem}", CODE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def features_script():
    """03_build_features.py (Eliya's; public functions only, S34-1)."""
    return _script("03_build_features.py")


def walkforward_script():
    """05_train_walkforward.py (Eliya's; spec_for only)."""
    return _script("05_train_walkforward.py")


def backtest_script():
    """06_backtest.py (Mattia's)."""
    return _script("06_backtest.py")


# -- small helpers --------------------------------------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(content, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(content, f, indent=2, sort_keys=True,
                  default=lambda value: value.item() if hasattr(value, "item") else str(value))
        f.write("\n")


def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def text_sha256(path: Path) -> str:
    """SHA-256 of a tracked text file with CRLF read as LF, so the checkout's line endings cannot change it (S34-3)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _closes(index: pd.MultiIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(index.get_level_values("date_close"))


def _week(stamp) -> str:
    return pd.Timestamp(stamp).strftime(DATE_FORMAT)


def lock_path(root: Path) -> Path:
    return Path(root) / LOCK_NAME


def processed_dir(root: Path, cfg: dict) -> Path:
    return Path(root) / cfg["data"]["data_dir"] / "processed"


def oos_data_dir(root: Path, cfg: dict, rerun: str | None = None) -> Path:
    """Folder of the full-range tables written by the run (S34-5): data/processed/oos/ (git-ignored); a rerun's own
    data/processed/oos_reruns/<ID>/ (S36-1)."""
    return processed_dir(root, cfg) / "oos" if rerun is None else processed_dir(root, cfg) / "oos_reruns" / rerun


def oos_out_dir(root: Path, rerun: str | None = None) -> Path:
    """outputs/oos/ for the run of record; outputs/oos_reruns/<ID>/ for the rerun of decision ID (S36-1)."""
    return Path(root) / "outputs" / "oos" if rerun is None else Path(root) / "outputs" / "oos_reruns" / rerun


# -- git ----------------------------------------------------------------------------------------------------------------


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)


def dirty_paths(root: Path) -> list[str]:
    """`git status --porcelain` lines: modified, staged and untracked files; git-ignored files are not listed."""
    return [line for line in git(root, "status", "--porcelain").stdout.splitlines() if line.strip()]


def head_commit(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def refuse_dirty(root: Path, what: str) -> None:
    dirty = dirty_paths(root)
    if dirty:
        shown = "; ".join(dirty[:5]) + (" …" if len(dirty) > 5 else "")
        raise SystemExit(f"{what}: refused, the working tree is not clean ({shown}); commit or remove these first (S34-3)")


# -- rerun decisions of docs/decisions.md (Amendment 8 C1, decision S36-1) ---------------------------------------------


@dataclass(frozen=True)
class RerunDecision:
    """A rerun decision: its ID, the bug, the fix commit (as written, or resolved to the full hash) and the Fix files."""

    id: str
    bug: str
    fix_commit: str
    files: tuple[str, ...]


_HEADING = re.compile(r"#{1,6} ")
_DECISION_HEADING = re.compile(r"### (\S+) · ")
_CELL_BORDER = re.compile(r"(?<!\\)\|")  # `\|` inside a cell is a literal bar, not a border


def decision_tables(text: str) -> dict[str, list[dict[str, str]]]:
    """{ID: [{Field: Content} of each entry headed `### <ID> · <title>`]} of a decisions.md text."""
    out: dict[str, list[dict[str, str]]] = {}
    current = None
    for line in text.splitlines():
        if _HEADING.match(line):
            match = _DECISION_HEADING.match(line)
            current = {} if match else None
            if match:
                out.setdefault(match.group(1), []).append(current)
            continue
        if current is not None and line.startswith("|"):
            cells = [cell.strip() for cell in _CELL_BORDER.split(line.strip())[1:-1]]
            if len(cells) == 2 and cells[0] != "Field" and set(cells[0]) - {"-", " "}:
                current.setdefault(cells[0], cells[1])
    return out


def parse_rerun_decision(decision_id: str, entries: list[dict[str, str]]) -> RerunDecision:
    """The rerun decision ID from its entries in decision_tables (S36-1). ValueError naming what is missing: the entry,
    a unique heading, a field of RERUN_FIELDS, exactly one commit hash in backticks in Fix commit, or a path in backticks
    in Fix files."""
    if not entries:
        raise ValueError(f"decision {decision_id} not found in {DECISIONS}")
    if len(entries) > 1:
        raise ValueError(f"decision {decision_id} heads {len(entries)} entries of {DECISIONS}; it must head exactly one")
    fields = entries[0]
    missing = [field for field in RERUN_FIELDS if not fields.get(field, "").strip()]
    if missing:
        raise ValueError(f"decision {decision_id} is not a rerun decision: it lacks {missing} (the fields "
                         f"{list(RERUN_FIELDS)}, Amendment 8 C1, S36-1)")
    hashes = re.findall(r"`([0-9a-fA-F]{7,40})`", fields["Fix commit"])
    if len(hashes) != 1:
        raise ValueError(f"decision {decision_id}: 'Fix commit' must hold exactly one commit hash in backticks")
    files = tuple(sorted({path.strip() for path in re.findall(r"`([^`]+)`", fields["Fix files"])}))
    if not files or not all(files):
        raise ValueError(f"decision {decision_id}: 'Fix files' must name the fix's files, each in backticks")
    return RerunDecision(decision_id, fields["Bug"].strip(), hashes[0].lower(), files)


def rerun_decisions(text: str) -> dict[str, RerunDecision]:
    """Every rerun decision recorded in a decisions.md text: the entries that parse_rerun_decision accepts."""
    out = {}
    for decision_id, entries in decision_tables(text).items():
        try:
            out[decision_id] = parse_rerun_decision(decision_id, entries)
        except ValueError:
            continue
    return out


# -- the OOS access log: the run of record, then one entry per rerun (§10 step 3, S34-4, Amendment 8 C1, S36-1) --------


def parse_oos_log(text: str, where: str = OOS_LOG) -> list[dict]:
    """Entries of an oos_access_log.json text: a JSON list of objects, each with a `utc` field. ValueError if malformed."""
    try:
        entries = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{where}: not valid JSON ({error})") from None
    if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get("utc"), str) for e in entries):
        raise ValueError(f"{where}: must be a JSON list of entries, each an object with a 'utc' time")
    return entries


def read_oos_log(path: Path) -> list[dict]:
    """Entries of outputs/oos_access_log.json; [] when it does not exist."""
    path = Path(path)
    return [] if not path.exists() else parse_oos_log(path.read_text(encoding="utf-8"), str(path))


def check_oos_log_entries(entries: list[dict], decisions_text: str = "", where: str = OOS_LOG) -> int:
    """Number of entries; ValueError unless the log follows Amendment 8 C1 against the rerun decisions recorded in
    `decisions_text` (docs/decisions.md in the same state): at most 1 + K entries for K recorded rerun decisions; the
    first entry (the run of record) names no decision; every later entry names a recorded rerun decision, each at most
    once. With no rerun decision recorded, at most one entry (§10 step 3)."""
    recorded = rerun_decisions(decisions_text)
    if len(entries) > 1 + len(recorded):
        raise ValueError(f"{where}: {len(entries)} entries; at most the run of record plus one per recorded rerun "
                         f"decision ({len(recorded)} in {DECISIONS}) are allowed (§10 step 3, Amendment 8 C1)")
    named = [entry.get(RERUN_KEY) for entry in entries]
    if named and named[0] is not None:
        raise ValueError(f"{where}: the first entry is the run of record and names no decision, but it names "
                         f"{named[0]!r} (Amendment 8 C1)")
    for number, name in enumerate(named[1:], start=2):
        if name is None:
            raise ValueError(f"{where}: entry {number} is a second run that names no rerun decision (Amendment 8 C1)")
        if not isinstance(name, str) or name not in recorded:
            raise ValueError(f"{where}: entry {number} names {name!r}, which is not a rerun decision recorded in "
                             f"{DECISIONS} (fields {list(RERUN_FIELDS)}, S36-1)")
    repeated = sorted({name for name in named[1:] if named[1:].count(name) > 1})
    if repeated:
        raise ValueError(f"{where}: decision(s) {repeated} named by more than one rerun entry; a decision allows one rerun")
    return len(entries)


def check_oos_log_text(text: str, where: str = OOS_LOG, decisions_text: str = "") -> int:
    """Number of entries of a log text; ValueError if malformed or breaking check_oos_log_entries (CI, S36-1)."""
    return check_oos_log_entries(parse_oos_log(text, where), decisions_text, where)


# -- the selection gate's output (decisions S34-3, S42-1) ---------------------------------------------------------------

FALLBACK = "M0_star"  # traded when no candidate passes (§07 step 5, Amendment 9 C3)
GATE_NUMBERS = ("sharpe", "sharpe_m0", "mdd", "mdd_m0", "p_uplift_positive")  # every evaluated row (src.stats.selection_gate)
GATE_VERDICTS = ("passes_sharpe", "passes_mdd", "passes_bootstrap", "passes")


def candidate_rounds(cfg: dict) -> tuple[list[str], list[str]]:
    """(round-1, round-2) candidates in order: models.candidate_order and round2.candidate_order. Amendment 9 C3 appends
    the second after the first; a config without a round2 section has no round-2 candidate."""
    return list(cfg["models"]["candidate_order"]), list((cfg.get("round2") or {}).get("candidate_order", []))


def bootstrap_threshold(name: str, cfg: dict) -> float:
    """The P(uplift > 0) threshold of a candidate's gate: selection.bootstrap_prob (0.80) in round 1,
    round2.selection.bootstrap_prob (0.90) in round 2 (Amendment 9 C3). The Sharpe uplift and the drawdown tolerance are
    those of selection: in both rounds."""
    first, second = candidate_rounds(cfg)
    if name in first:
        return float(cfg["selection"]["bootstrap_prob"])
    if name in second:
        return float(cfg["round2"]["selection"]["bootstrap_prob"])
    raise ValueError(f"{name} is not a candidate of models.candidate_order or round2.candidate_order")


def _first_passing(rows: list[dict]) -> str:
    return next((row["name"] for row in rows if row["status"] == "evaluated" and row["passes"]), FALLBACK)


def check_gate(gate, cfg: dict, where: str = GATE_FILE) -> dict:
    """Validate a selection-gate JSON (S34-3, S42-1). Its candidates are models.candidate_order followed, once round 2
    is in the file, by round2.candidate_order (Amendment 9 C3); each is `evaluated` or `absent`. Every evaluated row
    must hold the numbers and verdicts of src.stats.selection_gate, and its verdicts must follow from its numbers: Sharpe
    >= M0's + selection.sharpe_uplift, drawdown >= M0's - selection.mdd_tolerance, P(uplift > 0) >= its round's threshold
    (bootstrap_threshold), and passes = all three. Every evaluated row has the same hurdle (M0's Sharpe and drawdown).
    `selected` is the first passing candidate in the file's order, else M0_star.

    Returns {"names", "complete" (round 2 listed), "selected", "round1_selected" (the first passing round-1 candidate,
    else M0_star: the primary pre-registered result, Amendment 9 C3)}. SystemExit naming the first problem."""
    first, second = candidate_rounds(cfg)
    full = first + second
    candidates = gate.get("candidates") if isinstance(gate, dict) else None
    if not isinstance(candidates, list) or not all(isinstance(c, dict) for c in candidates):
        raise SystemExit(f"{where}: 'candidates' must be the list returned by src.stats.selection_gate")
    names = [c.get("name") for c in candidates]
    if names not in (first, full):
        raise SystemExit(f"{where}: candidates {names} differ from models.candidate_order + round2.candidate_order "
                         f"{full} (Amendment 9 C3; a file written before round 2 lists {first})")
    if any(c.get("status") not in ("evaluated", "absent") for c in candidates):
        raise SystemExit(f"{where}: every candidate status must be 'evaluated' or 'absent'")
    selected = gate.get("selected")
    evaluated = [c for c in candidates if c["status"] == "evaluated"]
    if selected != FALLBACK and selected not in [c["name"] for c in evaluated]:
        raise SystemExit(f"{where}: selected {selected!r} is neither an evaluated candidate nor M0_star")
    sel = cfg["selection"]
    for row in evaluated:
        name = row["name"]
        numbers = [k for k in GATE_NUMBERS if isinstance(row.get(k), bool) or not isinstance(row.get(k), (int, float))]
        flags = [k for k in GATE_VERDICTS if not isinstance(row.get(k), bool)]
        if numbers or flags:
            raise SystemExit(f"{where}: evaluated candidate {name} lacks {numbers + flags} (the row of "
                             "src.stats.selection_gate)")
        expected = {"passes_sharpe": row["sharpe"] >= row["sharpe_m0"] + sel["sharpe_uplift"],
                    "passes_mdd": row["mdd"] >= row["mdd_m0"] - sel["mdd_tolerance"],
                    "passes_bootstrap": row["p_uplift_positive"] >= bootstrap_threshold(name, cfg)}
        expected["passes"] = all(expected.values())
        wrong = [k for k in GATE_VERDICTS if row[k] != bool(expected[k])]
        if wrong:
            raise SystemExit(f"{where}: candidate {name}: {wrong} do not follow from its numbers and the thresholds "
                             f"(Sharpe uplift {sel['sharpe_uplift']}, drawdown tolerance {sel['mdd_tolerance']}, "
                             f"P(uplift > 0) >= {bootstrap_threshold(name, cfg)}; §07, Amendment 9 C3)")
    if len({(row["sharpe_m0"], row["mdd_m0"]) for row in evaluated}) > 1:
        raise SystemExit(f"{where}: the evaluated candidates do not share one hurdle (M0's Sharpe and drawdown); the "
                         "hurdle does not change in round 2 (Amendment 9 C4)")
    if selected != _first_passing(candidates):
        raise SystemExit(f"{where}: selected {selected!r}, but the first passing candidate in "
                         f"{names} is {_first_passing(candidates)!r} (§07 step 4, Amendment 9 C3)")
    return {"names": names, "complete": names == full, "selected": selected,
            "round1_selected": _first_passing([c for c in candidates if c["name"] in first])}


def read_gate(root: Path, cfg: dict) -> dict:
    """The JSON of the §07 selection step at outputs/metrics/selection_gate.json, validated by check_gate: `selected`
    and `candidates` (name, status evaluated/absent) of models.candidate_order + round2.candidate_order (Amendment 9 C3).
    Refused when it lists only the round-1 candidates: the order of Amendment 9 C3 includes round 2, whose candidates
    may be absent or evaluated (S42-1)."""
    path = Path(root) / GATE_FILE
    if not path.exists():
        raise SystemExit(f"{GATE_FILE} not found: apply the §07 selection gate (src.stats.selection_gate) and save its "
                         "result there first (missing hook, S34-5)")
    gate = _read_json(path)
    checked = check_gate(gate, cfg)
    if not checked["complete"]:
        first, second = candidate_rounds(cfg)
        raise SystemExit(f"{GATE_FILE}: lists only the round-1 candidates {first}; Amendment 9 C3 appends {second} "
                         "(each absent or evaluated), so the selection step must be run with round 2 first (S42-1)")
    return gate


def run_models(gate: dict, cfg: dict) -> list[str]:
    """The models of the OOS run (S34-6): the evaluated candidates in models.candidate_order + round2.candidate_order
    (the selected among them), then M0 and M0_star; ENS adds its members. An evaluated round-2 candidate is refused:
    its Out-of-Sample refit needs the round-2 refit hook of 05 (session 4.2b, S42-1)."""
    first, second = candidate_rounds(cfg)
    evaluated = [c["name"] for c in gate["candidates"] if c["status"] == "evaluated"]
    if "M5" in evaluated:
        raise SystemExit("M5 has no Out-of-Sample refit in 08_run_oos.py yet: its spec and refit hook come with Phase 3.3")
    round2 = [name for name in evaluated if name in second]
    if round2:
        raise SystemExit(f"round-2 candidates {round2} were evaluated, but 08_run_oos.py has no Out-of-Sample refit for "
                         "round 2 yet: it needs the round-2 refit hook of 05_train_walkforward.py (session 4.2b, S42-1)")
    models = list(evaluated)
    if "ENS" in models:
        models += [m for m in ENS_MEMBERS if m not in models]
    models += [m for m in FIXED_RUNGS if m not in models]
    order = first + second + list(FIXED_RUNGS)
    return sorted(dict.fromkeys(models), key=order.index)


# -- the frozen In-Sample artefacts -------------------------------------------------------------------------------------


def walkforward_dir(root: Path, name: str) -> Path:
    return Path(root) / "outputs" / "walkforward" / name


def expected_spec_hash(name: str, cfg: dict) -> str:
    return spec_hash(walkforward_script().spec_for(name, cfg), cfg)


def check_walkforward(root: Path, cfg: dict, name: str, trial_hashes: set[str]) -> str:
    """Stop unless outputs/walkforward/<name>/ holds scores built with this config (check_used), whose summary.json
    spec_hash is the one config.yaml gives (S32-10) and is a row of the trial log. Returns the spec_hash."""
    folder = walkforward_dir(root, name)
    if not (folder / "scores.csv").exists():
        raise SystemExit(f"outputs/walkforward/{name}/scores.csv not found: run 05_train_walkforward.py --model {name}")
    check_used(walkforward_settings(cfg), folder / "used.yaml", "05_train_walkforward.py")
    recorded = _read_json(folder / "summary.json").get("spec_hash") if (folder / "summary.json").exists() else None
    expected = expected_spec_hash(name, cfg)
    if recorded != expected:
        raise SystemExit(f"{name}: stale or missing walk-forward summary (spec_hash {str(recorded)[:12]}…, config.yaml "
                         f"gives {expected[:12]}…); rerun 05_train_walkforward.py (S32-10)")
    if expected not in trial_hashes:
        raise SystemExit(f"{name}: spec_hash {expected[:12]}… is not a row of {TRIAL_LOG}")
    return expected


def frozen_value(root: Path, cfg: dict, rung: str) -> dict:
    """The grid value chosen at the last In-Sample refit of a tuned rung (Amendment 6 C2, S31-14): the last row of
    outputs/walkforward/<rung>/selection.csv, cast to the grid value of the same number (int 10, float 0.1)."""
    path = walkforward_dir(root, rung) / "selection.csv"
    if not path.exists():
        raise SystemExit(f"outputs/walkforward/{rung}/selection.csv not found: the frozen grid value cannot be read")
    table = pd.read_csv(path).sort_values(["test_year", "refit"])
    last = table.iloc[-1]
    last_year = int(cfg["split"]["test_years"][1])
    if int(last["test_year"]) != last_year:
        raise SystemExit(f"{path}: last refit is in {int(last['test_year'])}, not the last In-Sample test year {last_year}")
    matches = [value for value in grid(rung, cfg) if float(value) == float(last["chosen"])]
    if len(matches) != 1:
        raise SystemExit(f"{path}: chosen value {last['chosen']!r} is not a grid value of {rung} {grid(rung, cfg)}")
    return {"value": matches[0], "test_year": int(last["test_year"]), "refit": int(last["refit"]),
            "test_start": str(last["test_start"])}


def artefact_paths(root: Path, cfg: dict, models: list[str]) -> list[str]:
    """Repository-relative paths of every artefact the run depends on (S34-3), sorted."""
    processed = processed_dir(root, cfg)
    paths = [processed / f"{name}.csv" for name in TABLES] + [processed / "features_config.yaml", Path(root) / GATE_FILE]
    for name in models:
        folder = walkforward_dir(root, name)
        paths += [folder / f for f in WALKFORWARD_FILES if f != "selection.csv" or (folder / f).exists()]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"artefact not found: {missing[0]}")
    return sorted(p.relative_to(root).as_posix() for p in paths)


# -- --freeze -----------------------------------------------------------------------------------------------------------


def freeze(root: Path = ROOT) -> dict:
    """Write FROZEN.lock (S34-3) after every check; returns its content. Nothing is written when a check fails."""
    root = Path(root)
    refuse_dirty(root, "--freeze")
    if lock_path(root).exists():
        raise SystemExit(f"--freeze: {LOCK_NAME} already exists; the system is frozen once")
    if read_oos_log(root / OOS_LOG):
        raise SystemExit(f"--freeze: {OOS_LOG} already has an entry; the Out-of-Sample run has happened")
    cfg = load_config(root / CONFIG)
    check_used(features_settings(cfg), processed_dir(root, cfg) / "features_config.yaml", "03_build_features.py")
    gate = read_gate(root, cfg)
    models = run_models(gate, cfg)
    trial_hashes = logged_spec_hashes(root / TRIAL_LOG)
    hashes = {name: check_walkforward(root, cfg, name, trial_hashes) for name in models}
    frozen = {rung: frozen_value(root, cfg, rung) for rung in TUNED if rung in models}
    with open(root / TRIAL_LOG, encoding="utf-8", newline="") as handle:
        trial_rows = max(sum(1 for row in csv.reader(handle) if row) - 1, 0)  # data rows: N of the DSR (S31-7)
    lock = {
        "format": LOCK_FORMAT, "created_utc": _utc_now(), "code_commit": head_commit(root),
        "config_sha256": text_sha256(root / CONFIG), "trial_log_sha256": text_sha256(root / TRIAL_LOG),
        "trial_count": trial_rows, "in_sample_end": cfg["split"]["in_sample_end"], "data_end": cfg["data"]["end"],
        "gate_file": GATE_FILE, "selected": gate["selected"], "models": models, "spec_hashes": hashes,
        "frozen_values": frozen, "allowed_after_freeze": list(ALLOWED_AFTER_FREEZE),
        "artefacts": {path: file_sha256(root / path) for path in artefact_paths(root, cfg, models)},
    }
    _write_json(lock, lock_path(root))
    return lock


# -- the run: checks before any Out-of-Sample access (decisions S34-4, S36-1) --------------------------------------------


def changed_files(root: Path, older: str, newer: str) -> set[str]:
    """Repository paths that differ between two commits (`git diff --name-only`)."""
    return {path for path in git(root, "diff", "--name-only", older, newer).stdout.splitlines() if path.strip()}


def check_rerun(root: Path, lock: dict, entries: list[dict], decision_id: str) -> tuple[RerunDecision, set[str]]:
    """The Amendment 8 C1 checks of --rerun ID (S36-1), before any Out-of-Sample access. Returns the decision, with its
    fix commit resolved to the full hash, and the files that may have changed since the freeze beyond
    allowed_after_freeze: its Fix files, those of the decisions of earlier rerun entries, and the access log."""
    root = Path(root)
    refused = f"--rerun {decision_id}: refused"
    if not entries:
        raise SystemExit(f"{refused}, {OOS_LOG} holds no run of record; the first run is 08_run_oos.py without --rerun")
    path = root / DECISIONS
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        check_oos_log_entries(entries, text)
    except ValueError as error:
        raise SystemExit(f"{refused}, {error}") from None
    if entries[0].get("lock_sha256") != file_sha256(lock_path(root)):
        raise SystemExit(f"{refused}, the run of record of {OOS_LOG} was not written for the current {LOCK_NAME}")
    if any(entry.get(RERUN_KEY) == decision_id for entry in entries[1:]):
        raise SystemExit(f"{refused}, {OOS_LOG} already holds the rerun of decision {decision_id}; a decision allows one "
                         "rerun")
    try:
        decision = parse_rerun_decision(decision_id, decision_tables(text).get(decision_id, []))
    except ValueError as error:
        raise SystemExit(f"{refused}, {error}") from None
    protected = sorted(set(decision.files) & {CONFIG, TRIAL_LOG, LOCK_NAME, *lock["artefacts"]})
    if protected:
        raise SystemExit(f"{refused}, 'Fix files' names {protected}: the fix changes no setting, threshold, grid, feature, "
                         "model, cost or selected model (Amendment 8 C1)")
    resolved = git(root, "rev-parse", "--verify", "--quiet", f"{decision.fix_commit}^{{commit}}", check=False)
    if resolved.returncode != 0:
        raise SystemExit(f"{refused}, the fix commit {decision.fix_commit} is not a commit of this repository")
    fix, frozen = resolved.stdout.strip(), lock["code_commit"]
    if fix == frozen or git(root, "merge-base", "--is-ancestor", frozen, fix, check=False).returncode != 0:
        raise SystemExit(f"{refused}, the fix commit {fix[:12]} does not come after the frozen commit {frozen[:12]}")
    if git(root, "merge-base", "--is-ancestor", fix, "HEAD", check=False).returncode != 0:
        raise SystemExit(f"{refused}, the fix commit {fix[:12]} is not an ancestor of HEAD")
    fixed = changed_files(root, f"{fix}^1", fix) - {DECISIONS}
    if fixed != set(decision.files):
        raise SystemExit(f"{refused}, the fix commit {fix[:12]} changes {sorted(fixed)}, but 'Fix files' names "
                         f"{list(decision.files)}")
    recorded = rerun_decisions(text)
    earlier = {name for entry in entries[1:] for name in recorded[entry[RERUN_KEY]].files}
    return replace(decision, fix_commit=fix), set(decision.files) | earlier | {OOS_LOG}


def verify_lock(root: Path, rerun: str | None = None) -> tuple[dict, dict, RerunDecision | None]:
    """Stop unless FROZEN.lock exists and matches the current tree, and the OOS access log is empty (the run of record)
    or, with rerun = a decision ID, check_rerun passes. Returns (lock, cfg, the rerun decision or None)."""
    root = Path(root)
    if rerun is not None and not DECISION_ID.fullmatch(rerun):
        raise SystemExit(f"--rerun: refused, {rerun!r} is not a decision ID (letters, digits, '.', '_' and '-', starting and "
                         "ending with a letter or digit)")
    if not lock_path(root).exists():
        raise SystemExit(f"refused: {LOCK_NAME} does not exist; run 08_run_oos.py --freeze and sign it at Gate 3 first")
    try:
        lock = _read_json(lock_path(root))
    except json.JSONDecodeError as error:
        raise SystemExit(f"refused: {LOCK_NAME} is not valid JSON ({error})") from None
    if not isinstance(lock, dict) or lock.get("format") != LOCK_FORMAT:
        raise SystemExit(f"refused: {LOCK_NAME} is not a format-{LOCK_FORMAT} lock written by --freeze")
    entries = read_oos_log(root / OOS_LOG)
    decision, fix_allowed = None, set()
    if rerun is None and entries:
        raise SystemExit(f"refused: {OOS_LOG} already has an entry; the Out-of-Sample run happens exactly once (§10); a "
                         "rerun to correct a recorded bug is 08_run_oos.py --rerun DECISION_ID (Amendment 8 C1)")
    if rerun is not None:
        decision, fix_allowed = check_rerun(root, lock, entries, rerun)
    refuse_dirty(root, "the run" if rerun is None else f"--rerun {rerun}")
    commit = lock["code_commit"]
    if git(root, "merge-base", "--is-ancestor", commit, "HEAD", check=False).returncode != 0:
        raise SystemExit(f"refused: the frozen commit {commit[:12]} is not an ancestor of HEAD")
    changed = changed_files(root, commit, "HEAD")
    allowed = set(lock.get("allowed_after_freeze", ())) | fix_allowed
    if changed - allowed:
        raise SystemExit(f"refused: files changed since the freeze: {sorted(changed - allowed)} (only {sorted(allowed)} "
                         "may change, S34-3, S36-1)")
    mismatched = []
    if text_sha256(root / CONFIG) != lock["config_sha256"]:
        mismatched.append(CONFIG)
    if text_sha256(root / TRIAL_LOG) != lock["trial_log_sha256"]:
        mismatched.append(TRIAL_LOG)
    for path, digest in sorted(lock["artefacts"].items()):
        if not (root / path).exists() or file_sha256(root / path) != digest:
            mismatched.append(path)
    if mismatched:
        raise SystemExit(f"refused: hashes differ from {LOCK_NAME} for {mismatched}")
    cfg = load_config(root / CONFIG)
    return lock, cfg, decision


def read_frozen_scores(root: Path, name: str, is_end: pd.Timestamp) -> pd.DataFrame:
    """The frozen In-Sample walk-forward scores of `name` (contract 8; every week <= is_end)."""
    path = walkforward_dir(root, name) / "scores.csv"
    scores = pd.read_csv(path, index_col=WEEK_COLUMNS, parse_dates=WEEK_COLUMNS).astype(np.float64)
    scores.columns.name = None
    validate_scores(scores)
    if _closes(scores.index).max() > is_end:
        raise SystemExit(f"{path}: a frozen In-Sample score is dated after {is_end.date()}")
    return scores


def input_files(root: Path, cfg: dict) -> list[Path]:
    """The daily and raw files the run reads after the access entry; checked to exist before it (S34-4)."""
    data_dir = Path(root) / cfg["data"]["data_dir"]
    files = [data_dir / "processed" / "daily_close.csv", data_dir / "processed" / "daily_open.csv",
             data_dir / "processed" / "config.yaml", data_dir / "raw" / "yahoo" / f"{file_stem(cfg['data']['vix'])}.csv"]
    files += [data_dir / "raw" / "fred" / f"{name}.csv" for name in cfg["data"]["fred"]]
    files += [data_dir / "raw" / "yahoo" / f"{file_stem(t)}.csv" for t in universe(cfg).tradables]
    return files


def append_entry(root: Path, lock: dict, decision: RerunDecision | None = None) -> dict:
    """Append the run's entry to outputs/oos_access_log.json before the vault is unlocked: the single entry of the run
    of record (S34-4), or one entry naming the rerun decision and its fix commit (Amendment 8 C1, S36-1)."""
    entry = {"utc": _utc_now(), "script": "08_run_oos.py", "code_commit": lock["code_commit"],
             "head_commit": head_commit(root), "lock_sha256": file_sha256(lock_path(root)), "selected": lock["selected"],
             "data_end": lock["data_end"]}
    path = Path(root) / OOS_LOG
    entries = read_oos_log(path)
    if decision is None and entries:
        raise SystemExit(f"refused: {OOS_LOG} already has an entry")
    if decision is not None:
        if not entries or any(e.get(RERUN_KEY) == decision.id for e in entries):
            raise SystemExit(f"refused: {OOS_LOG} has no run of record or already holds the rerun of {decision.id}")
        entry |= {RERUN_KEY: decision.id, "fix_commit": decision.fix_commit}
    _write_json(entries + [entry], path)
    return entry


# -- the run: tables, refits and the continuous book (decisions S34-5 to S34-7) -----------------------------------------


def rebuild_tables(root: Path, cfg: dict, out_dir: Path | None = None) -> dict:
    """The full-range tables through 03's unlock path (S34-5), written to out_dir (default data/processed/oos/; a
    rerun's data/processed/oos_reruns/<ID>/, S36-1): the six tables of
    03_build_features.py built from the inputs cut at data.end. The forward returns come from
    build_forward_returns(..., is_end, truncate_at=data.end, lock_path=FROZEN.lock) (S37-2, S38-1): the builder labels
    the period from realised_on against split.in_sample_end (contract 7) and raises OOSAccessError itself unless
    FROZEN.lock exists. Returns 03's {file: rows, dates, columns, bytes, sha256}."""
    s03 = features_script()
    data_dir = Path(root) / cfg["data"]["data_dir"]
    end, is_end = pd.Timestamp(cfg["data"]["end"]), pd.Timestamp(cfg["split"]["in_sample_end"])
    daily_close, vix, fred = s03.load_inputs(data_dir, end=end, cfg=cfg)
    daily_open = s03.load_opens(data_dir, end=end)
    forward = s03.build_forward_returns(daily_open, daily_close, is_end, truncate_at=end, lock_path=lock_path(root))
    validate_forward_returns(*s03.split_forward_returns(forward), is_end=is_end)
    tables = s03.build_tables(daily_close, vix, fred, cfg)
    tables["labels"] = s03.build_labels(daily_open, daily_close, end)
    tables["forward_returns"] = forward
    out_dir = oos_data_dir(root, cfg) if out_dir is None else Path(out_dir)
    return s03.write_tables(tables, out_dir, is_end, lock_path(root), allow_oos=True)


def vault_momentum(vault: Vault, as_of: pd.Timestamp) -> pd.DataFrame:
    """The M0* momentum variants through the vault (S34-5, missing hook 3): Vault.momentum_variants if it exists, else the
    vault's own sealed and logged table reader."""
    reader = getattr(vault, "momentum_variants", None)
    if callable(reader):
        return reader(as_of)
    return vault._rows_until("momentum_variants", "momentum_variants", as_of)


def ladder_data(vault: Vault, as_of: pd.Timestamp) -> LadderData:
    """Model inputs known by as_of, through the (unlocked) vault."""
    return LadderData(features=vault.features(as_of), states=vault.market_states(as_of), labels=vault.labels(as_of),
                      momentum=vault_momentum(vault, as_of))


def oos_folds(data: LadderData, cfg: dict, last_is_week: pd.Timestamp) -> list:
    """The quarterly refits that score the weeks after the last In-Sample scored week (S34-6): src.labels.
    walk_forward_folds with split.in_sample_end = data.end and split.test_years = [last In-Sample test year, year of
    data.end], from the refit whose window holds last_is_week (2019 Q4) on."""
    extended = copy.deepcopy(cfg)
    end = pd.Timestamp(cfg["data"]["end"])
    extended["split"]["in_sample_end"] = end.strftime(DATE_FORMAT)
    extended["split"]["test_years"] = [int(cfg["split"]["test_years"][1]), int(end.year)]
    weeks = data.states.index
    folds = walk_forward_folds(weeks, label_end_by_week(data.labels, weeks), extended)
    kept = [fold for fold in folds if fold.test_end > last_is_week]
    if not kept or not kept[0].test_start <= last_is_week:
        raise SystemExit(f"no refit window holds the last In-Sample scored week {last_is_week.date()}")
    return kept


def model_recipe(name: str, lock: dict, cfg: dict) -> tuple[str, object]:
    """(rung, value) of walkforward_rung for a model's OOS refits (Amendment 6 C2, S34-6); ENS is built from members."""
    if name == "M0":
        return "M0", cfg["models"]["M0"]["feature"]
    if name == "M0_star":
        return "M0", f"MOM{int(lock['frozen_values']['M0_star']['value'])}_1"
    if name in ("M1", "M2", "M3"):
        return name, lock["frozen_values"][name]["value"]
    raise SystemExit(f"{name}: no Out-of-Sample recipe")


def refit_scores(models: list[str], data: LadderData, folds: list, lock: dict, cfg: dict) -> dict[str, pd.DataFrame]:
    """Scores of the refit windows (the 2019 Q4 window included) of every model: walkforward_rung at the frozen values,
    every fit purged; ENS = ensemble_scores of its members' refit scores."""
    out = {}
    for name in models:
        if name != "ENS":
            rung, value = model_recipe(name, lock, cfg)
            out[name] = walkforward_rung(rung, data, folds, cfg, value=value)[0]
    if "ENS" in models:
        out["ENS"] = ensemble_scores([out[member] for member in ENS_MEMBERS])
    return out


def reproduction(frozen: pd.DataFrame, refit: pd.DataFrame, cfg: dict) -> dict:
    """S34-2 check on the weeks both frames score (the In-Sample part of the 2019 Q4 window): max |difference| and
    identity of the sector signals."""
    weeks = frozen.index.intersection(refit.index)
    a, b = frozen.loc[weeks], refit.loc[weeks]
    diff = float(np.nanmax(np.abs(a.to_numpy() - b.to_numpy()))) if len(weeks) else 0.0
    same_nan = bool((a.isna().to_numpy() == b.isna().to_numpy()).all())
    k = int(cfg["signal"]["top_k"])
    sa = _sector_signals(a, k)
    sb = _sector_signals(b, k)
    return {"weeks": len(weeks), "max_abs_diff": diff, "same_missing": same_nan,
            "signals_identical": bool(sa.equals(sb)), "within_tolerance": bool(diff <= REPRODUCTION_TOLERANCE and same_nan)}


def _sector_signals(scores: pd.DataFrame, k: int) -> pd.DataFrame:
    complete = scores.dropna()
    return signals_from_scores(complete, k, k) if len(complete) else complete


def oos_used(cfg: dict, model: str) -> dict:
    """used.yaml of outputs/oos/<model>/ (07_evaluate.py --period OOS checks it): the backtest settings of S23-10 and
    data.end."""
    return backtest_script().backtest_used(cfg, model) | {"oos": {"data_end": cfg["data"]["end"]}}


def backtest_book(root: Path, cfg: dict, name: str, scores: pd.DataFrame, market: dict, spec_digest: str,
                  frozen: dict | None, last_is_week: pd.Timestamp, out: Path | None = None) -> dict:
    """One continuous book (Amendment 2 C5, S34-7) in the three cost scenarios; writes `out` (default
    outputs/oos/<name>/)."""
    bt = backtest_script()
    u = universe(cfg)
    betas, fwd, realised_on, period, rf = market["betas"], market["fwd"], market["realised_on"], market["period"], market["rf"]
    sizing = size_book(scores, betas, cfg)
    scenarios = bt.cost_scenarios(cfg)
    results = {label: run_backtest(sizing, fwd, period, bps, borrow) for label, bps, borrow, _ in scenarios}
    baseline = next(label for label, *_, is_base in scenarios if is_base)
    base = results[baseline]
    weeks = base.net.index
    signals = sizing.signals.loc[weeks]
    benchmark = fwd.loc[weeks, u.benchmark]
    rf_constant = float(cfg["metrics"]["risk_free_constant"])
    rows, by_scenario = [], {}
    for label, bps, borrow, is_base in scenarios:
        result = results[label]
        per_rf = {}
        for rf_name, rf_value in (("tbill", rf.loc[weeks]), ("constant", rf_constant)):
            per_rf[rf_name] = period_metrics(result.net, result.period, signals, result.weights, benchmark, rf_value)
            for period_name, metrics in per_rf[rf_name].items():
                rows.append({"scenario": label, "cost_bps": bps, "borrow_annual": borrow, "baseline": is_base,
                             "rf": rf_name, "period": period_name} | metrics)
        by_scenario[label] = {p: {"net_sharpe_rf_tbill": per_rf["tbill"][p]["sharpe_rf"],
                                  "net_sharpe_rf_constant": per_rf["constant"][p]["sharpe_rf"],
                                  "net_sharpe_zero_cost": per_rf["tbill"][p]["sharpe_zero_cost"],
                                  "annualized_return": per_rf["tbill"][p]["annualized_return"],
                                  "max_drawdown": per_rf["tbill"][p]["max_drawdown"],
                                  "rf_annual": per_rf["tbill"][p]["rf_annual"]} for p in per_rf["tbill"]}
    weekly = pd.DataFrame({field: getattr(base, field) for field in bt.WEEKLY_FIELDS})
    weekly.insert(0, "realised_on", realised_on.loc[weeks])
    weekly.insert(1, "period", base.period)
    weekly["long_exposure"] = base.weights.clip(lower=0).sum(axis=1)
    weekly["short_exposure"] = base.weights.clip(upper=0).sum(axis=1)
    weekly["cap_binds"] = sizing.cap_binds.loc[weeks]
    weekly["rf"] = rf.loc[weeks]
    for label, *_, is_base in scenarios:
        if not is_base:
            weekly[f"net_{label}"] = results[label].net
    is_check = None
    frozen_weekly = Path(root) / "outputs" / "backtests" / name / "weekly.csv"
    if frozen_weekly.exists():
        old = pd.read_csv(frozen_weekly, index_col=WEEK_COLUMNS, parse_dates=WEEK_COLUMNS)["net"]
        common = old.index.intersection(weeks)
        is_check = {"weeks": len(common),
                    "max_abs_diff_net": float((old.loc[common] - base.net.loc[common]).abs().max()) if len(common) else None}
    oos_weeks = weeks[(base.period == "OOS").to_numpy()]
    summary = {
        "model": name, "spec_hash": spec_digest, "frozen_value": frozen, "baseline": baseline, "weeks": len(weeks),
        "weeks_is": int((base.period == "IS").sum()), "weeks_oos": len(oos_weeks),
        "first_week": _week(_closes(weeks)[0]), "last_week": _week(_closes(weeks)[-1]),
        "first_oos_week": _week(_closes(oos_weeks)[0]) if len(oos_weeks) else None,
        "first_oos_realised_on": _week(realised_on.loc[oos_weeks].iloc[0]) if len(oos_weeks) else None,
        "last_realised_on": _week(realised_on.loc[weeks].iloc[-1]),
        "first_oos_turnover": float(base.turnover.loc[oos_weeks].iloc[0]) if len(oos_weeks) else None,
        "mean_abs_residual_beta": {p: float(base.residual_beta[(base.period == p).to_numpy()].abs().mean())
                                   for p in ("IS", "OOS") if (base.period == p).any()},
        "cap_binding_weeks": int(sizing.cap_binds.loc[weeks].sum()),
        "missing_input_weeks": bt.missing_input_weeks(scores, betas, weeks),
        "in_sample_backtest_check": is_check, "scenarios": by_scenario, "rf_constant": rf_constant,
        "benchmark": u.benchmark,
    }
    out = oos_out_dir(root) / name if out is None else Path(out)
    write_csv(scores.loc[_closes(scores.index) > last_is_week], out / "scores.csv")  # the Out-of-Sample refit weeks
    write_csv(weekly, out / "weekly.csv")
    write_csv(pd.DataFrame(rows).set_index(["scenario", "rf", "period"]), out / "metrics.csv")
    save_used(oos_used(cfg, name), out / "used.yaml")
    _write_json(summary, out / "summary.json")
    return summary


def run_oos(root: Path = ROOT, rerun: str | None = None) -> dict:
    """The Out-of-Sample run of record (S34-4 to S34-7), or, with rerun = a decision ID, its rerun after a recorded bug
    fix (Amendment 8 C1, S36-1), written to the rerun's own folders. Returns run.json's content."""
    root = Path(root)
    lock, cfg, decision = verify_lock(root, rerun)
    tables_dir, out_dir = oos_data_dir(root, cfg, rerun), oos_out_dir(root, rerun)
    is_end, end = pd.Timestamp(cfg["split"]["in_sample_end"]), pd.Timestamp(cfg["data"]["end"])
    models = list(lock["models"])
    check_used(data_settings(cfg), processed_dir(root, cfg) / "config.yaml", "01_download_data.py")
    missing = [p for p in input_files(root, cfg) if not p.exists()]
    if missing:
        raise SystemExit(f"refused before any Out-of-Sample access: {missing[0]} not found")
    frozen_scores = {name: read_frozen_scores(root, name, is_end) for name in models}
    last_is_week = max(_closes(s.index).max() for s in frozen_scores.values())
    if any(_closes(s.index).max() != last_is_week for s in frozen_scores.values()):
        raise SystemExit("the frozen walk-forward scores do not end on the same week")

    entry = append_entry(root, lock, decision)  # every check passed: the access is logged before the vault opens
    vault = Vault(is_end, lock_path=lock_path(root), log_path=root / VAULT_LOG, data_dir=tables_dir, cfg=cfg)
    vault.unlock()
    tables = rebuild_tables(root, cfg, tables_dir)
    data = ladder_data(vault, end)
    folds = oos_folds(data, cfg, last_is_week)
    refits = refit_scores(models, data, folds, lock, cfg)

    bt = backtest_script()
    _, sessions, fwd, realised_on, period = bt.read_market(end, is_end, root=root)
    market = {"betas": vault.sizing_betas(end), "fwd": fwd, "realised_on": realised_on, "period": period,
              "rf": tbill_weekly_returns(bt.read_risk_free(cfg, end, root=root), fwd.index, sessions)}
    checks, summaries = {}, {}
    for name in models:
        frozen, refit = frozen_scores[name], refits[name]
        checks[name] = reproduction(frozen, refit, cfg)
        scores = pd.concat([frozen, refit.loc[_closes(refit.index) > last_is_week]])
        validate_scores(scores)
        value = lock["frozen_values"].get(name) if name in TUNED else None
        summaries[name] = backtest_book(root, cfg, name, scores, market, lock["spec_hashes"][name], value,
                                        last_is_week, out=out_dir / name)
    report = {
        "access_entry": entry, "lock_sha256": entry["lock_sha256"], "selected": lock["selected"], "models": models,
        "frozen_values": lock["frozen_values"], "last_in_sample_scored_week": _week(last_is_week),
        "folds": [{"test_year": f.test_year, "refit": f.refit, "train_start": _week(f.train_start),
                   "train_end": _week(f.train_end), "purge_end": _week(f.purge_end), "test_start": _week(f.test_start),
                   "test_end": _week(f.test_end)} for f in folds],
        "reproduction_2019q4": checks, "tables": tables,
        "in_sample_backtest_check": {name: s["in_sample_backtest_check"] for name, s in summaries.items()},
        "rerun": None if decision is None else {"decision": decision.id, "bug": decision.bug,
                                                "fix_commit": decision.fix_commit, "fix_files": list(decision.files)},
    }
    _write_json(report, out_dir / "run.json")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true", help="write FROZEN.lock (Gate 3); without a flag: the run of record")
    mode.add_argument("--rerun", metavar="DECISION_ID", default=None,
                      help="rerun after the fix of a bug recorded in decision DECISION_ID (Amendment 8 C1, S36-1)")
    args = parser.parse_args(argv)
    if args.freeze:
        lock = freeze(ROOT)
        print(f"Saved {LOCK_NAME}: commit {lock['code_commit'][:12]}, selected {lock['selected']}, {len(lock['artefacts'])} "
              f"artefacts, trial count {lock['trial_count']}. Sign it in docs/decisions.md and commit both (Gate 3).")
        return
    report = run_oos(ROOT, rerun=args.rerun)
    where = oos_out_dir(ROOT, args.rerun).relative_to(ROOT).as_posix()
    kind = "Out-of-Sample run" if args.rerun is None else f"Out-of-Sample rerun of decision {args.rerun}"
    print(f"{kind} done at {report['access_entry']['utc']}: {len(report['models'])} models, "
          f"{len(report['folds'])} refits -> {where}/; commit {OOS_LOG} with git add -f (S34-4, S36-1)")


if __name__ == "__main__":
    sys.exit(main())
