"""§10 vault protocol step 3 (decision S34-4): CI fails if outputs/oos_access_log.json ever holds more than one entry.

The log is written once by 08_run_oos.py at Gate 4 and committed with `git add -f` (outputs/ is git-ignored). This test
reads the file in the working tree and every version of it in the git history available to the job.
"""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOG = "outputs/oos_access_log.json"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("run_oos_for_log_test", ROOT / "08_run_oos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_working_tree_log_holds_at_most_one_entry(script):
    path = ROOT / LOG
    if path.exists():
        script.check_oos_log_text(path.read_text(encoding="utf-8"), LOG)


def test_every_committed_version_of_the_log_holds_at_most_one_entry(script):
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("no git repository")
    log = subprocess.run(["git", "-C", str(ROOT), "log", "--all", "--format=%H", "--", LOG], check=False,
                         capture_output=True, text=True)
    if log.returncode != 0:
        pytest.skip(f"git log failed: {log.stderr.strip()}")
    for commit in log.stdout.split():
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{LOG}"], check=False,
                               capture_output=True, text=True)
        if shown.returncode == 0:  # the commit that deletes the file has no version of it
            script.check_oos_log_text(shown.stdout, f"{LOG} at {commit[:12]}")


def test_the_check_fails_on_two_entries(script, tmp_path):
    with pytest.raises(ValueError, match="2 entries"):
        script.check_oos_log_text('[{"utc": "2026-11-07T10:00:00+00:00"}, {"utc": "2026-11-08T10:00:00+00:00"}]')
