"""§10 vault protocol step 3 with Amendment 8 C1 (decisions S34-4, S36-1): CI fails if outputs/oos_access_log.json
holds more than one entry plus one per rerun decision recorded in docs/decisions.md, or if its entries do not follow the
rule (the first is the run of record and names no decision; each later one names a recorded rerun decision, once).

The log is written by 08_run_oos.py at Gate 4 (and by any rerun) and committed with `git add -f` (outputs/ is
git-ignored). This test reads the file in the working tree against the working tree's docs/decisions.md, and every
version of it in the git history available to the job against docs/decisions.md at the same commit.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOG = "outputs/oos_access_log.json"
DECISIONS = "docs/decisions.md"

RERUN_DECISION = """# Decision log

### S99-1 · Rerun after the fix of a synthetic bug

| Field | Content |
| --- | --- |
| Bug | the book read the wrong week |
| Fix commit | `0123abc` |
| Fix files | `08_run_oos.py`, `tests/test_run_oos_script.py` |
"""


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("run_oos_for_log_test", ROOT / "08_run_oos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entries(*names) -> str:
    """A log text: one entry per name (None = the run of record, otherwise the rerun decision it names)."""
    out = []
    for number, name in enumerate(names):
        entry = {"utc": f"2026-11-{7 + number:02d}T10:00:00+00:00"}
        if name is not None:
            entry["rerun_decision"] = name
        out.append(entry)
    return json.dumps(out)


def test_the_working_tree_log_follows_the_rule(script):
    path = ROOT / LOG
    if path.exists():
        decisions = (ROOT / DECISIONS).read_text(encoding="utf-8")
        script.check_oos_log_text(path.read_text(encoding="utf-8"), LOG, decisions)


def test_every_committed_version_of_the_log_follows_the_rule(script):
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("no git repository")
    log = subprocess.run(["git", "-C", str(ROOT), "log", "--all", "--format=%H", "--", LOG], check=False,
                         capture_output=True, text=True)
    if log.returncode != 0:
        pytest.skip(f"git log failed: {log.stderr.strip()}")
    for commit in log.stdout.split():
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{LOG}"], check=False,
                               capture_output=True, text=True, encoding="utf-8")
        if shown.returncode != 0:  # the commit that deletes the file has no version of it
            continue
        decisions = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{DECISIONS}"], check=False,
                                   capture_output=True, text=True, encoding="utf-8")
        script.check_oos_log_text(shown.stdout, f"{LOG} at {commit[:12]}",
                                  decisions.stdout if decisions.returncode == 0 else "")


def test_the_check_fails_on_two_entries_without_a_recorded_rerun_decision(script):
    with pytest.raises(ValueError, match="2 entries"):
        script.check_oos_log_text('[{"utc": "2026-11-07T10:00:00+00:00"}, {"utc": "2026-11-08T10:00:00+00:00"}]')
    with pytest.raises(ValueError, match="2 entries"):  # the decision is named, but not recorded
        script.check_oos_log_text(entries(None, "S99-1"), LOG, "# Decision log\n")


def test_a_recorded_rerun_decision_allows_exactly_one_more_entry(script):
    assert script.check_oos_log_text(entries(None), LOG, RERUN_DECISION) == 1
    assert script.check_oos_log_text(entries(None, "S99-1"), LOG, RERUN_DECISION) == 2
    with pytest.raises(ValueError, match="3 entries"):
        script.check_oos_log_text(entries(None, "S99-1", "S99-1"), LOG, RERUN_DECISION)


def test_each_later_entry_must_name_a_recorded_rerun_decision_once(script):
    two = RERUN_DECISION + RERUN_DECISION.split("\n", 2)[2].replace("S99-1", "S99-2")
    assert set(script.rerun_decisions(two)) == {"S99-1", "S99-2"}
    assert script.check_oos_log_text(entries(None, "S99-1", "S99-2"), LOG, two) == 3
    with pytest.raises(ValueError, match="names no rerun decision"):
        script.check_oos_log_text(entries(None, None), LOG, RERUN_DECISION)
    with pytest.raises(ValueError, match="'S99-7', which is not a rerun decision"):
        script.check_oos_log_text(entries(None, "S99-7"), LOG, RERUN_DECISION)
    with pytest.raises(ValueError, match="more than one rerun entry"):
        script.check_oos_log_text(entries(None, "S99-1", "S99-1"), LOG, two)


def test_the_run_of_record_names_no_decision(script):
    with pytest.raises(ValueError, match="first entry is the run of record"):
        script.check_oos_log_text(entries("S99-1"), LOG, RERUN_DECISION)


def test_a_decision_without_the_rerun_fields_allows_no_rerun(script):
    ordinary = RERUN_DECISION.replace("| Fix files | `08_run_oos.py`, `tests/test_run_oos_script.py` |\n", "")
    assert script.rerun_decisions(ordinary) == {}
    with pytest.raises(ValueError, match="2 entries"):
        script.check_oos_log_text(entries(None, "S99-1"), LOG, ordinary)
