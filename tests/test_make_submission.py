"""The submission file list: git ls-files + data/raw/** + data/processed/** + outputs/**, never local tool-settings files.

Forbidden names are assembled from fragments, so this file passes the commit-time scan.
"""

import shutil
import subprocess

import pytest

import make_submission

TOOL = "cla" + "ude"
TOOL_FILES = [f".{TOOL}/settings.json", f"{TOOL.upper()}.md", f"{TOOL.upper()}.local.md", ".mcp.json"]


def git(root, *args):
    subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=root, check=True, capture_output=True)


def make_files(root, paths):
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(b"x\n")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """tmp_path with git discovery stopped at its parent (the temp folder may sit inside another repository)."""
    if shutil.which("git") is None:
        pytest.skip("git not available")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    return tmp_path


@pytest.fixture
def repo(isolated):
    tmp_path = isolated
    git(tmp_path, "init", "-q")
    tracked = ["README.md", "src/a.py", "docs/x.md", "data/checksums.json", f"docs/{TOOL.upper()}.md"] + TOOL_FILES
    untracked = ["notes.txt", "src/b.py", ".venv/lib/site.py", "data/cache/c.json", f"sub/.{TOOL}/memory.md",
                 "data/raw/yahoo/XLB.csv", "data/raw/manifest.json", "data/processed/daily_open.csv", "outputs/metrics/m.csv",
                 f"outputs/.{TOOL}/settings.json", f"data/raw/{TOOL.upper()}.md"]
    make_files(tmp_path, tracked + untracked)
    git(tmp_path, "add", "-f", "--", *tracked)  # -f: a global ignore file must not change the fixture
    return tmp_path


def test_selection_is_tracked_plus_data_and_outputs(repo):
    assert make_submission.submission_files(repo) == [
        "README.md",
        "data/checksums.json",
        "data/processed/daily_open.csv",
        "data/raw/manifest.json",
        "data/raw/yahoo/XLB.csv",
        "docs/x.md",
        "outputs/metrics/m.csv",
        "src/a.py",
    ]


def test_tool_files_never_included_even_if_tracked(repo):
    files = make_submission.submission_files(repo)
    assert not [path for path in files if make_submission.FORBIDDEN.search(path)]
    for path in TOOL_FILES:
        assert path not in files


def test_untracked_files_outside_data_and_outputs_never_included(repo):
    files = make_submission.submission_files(repo)
    for path in ["notes.txt", "src/b.py", ".venv/lib/site.py", "data/cache/c.json"]:
        assert path not in files


def test_tracked_file_deleted_from_disk_is_dropped(repo):
    (repo / "docs/x.md").unlink()
    assert "docs/x.md" not in make_submission.submission_files(repo)


def test_forbidden_pattern():
    for path in TOOL_FILES + [f"a/.{TOOL}/x", f"a/{TOOL}.md", f"{TOOL.upper()}.LOCAL.MD", "x/.mcp.json"]:
        assert make_submission.FORBIDDEN.search(path), path
    for path in ["src/config.py", "docs/methods.md", f"docs/{TOOL}_notes.txt", "mcp.json"]:
        assert not make_submission.FORBIDDEN.search(path), path


def test_not_a_git_repository(isolated):
    with pytest.raises(RuntimeError, match="git ls-files failed"):
        make_submission.tracked_files(isolated)


def test_this_repository_list_has_no_tool_files():
    try:
        files = make_submission.submission_files()
    except RuntimeError:
        pytest.skip("not a git clone (e.g. the submission zip)")
    assert not [path for path in files if make_submission.FORBIDDEN.search(path)]
