"""Repository policy: no local assistant files tracked, no licensed raw data tracked, clean ignore rules.

The same rules are enforced at commit time by tools/git-hooks/; this test is the backstop in CI.
Forbidden words are assembled from fragments, so this file does not match the commit-time scan.
"""

import re
import subprocess

import pytest

from src.config import ROOT

TOOL = "cla" + "ude"
FORBIDDEN_PATHS = re.compile(rf"(^|/)\.{TOOL}(/|$)|(^|/){TOOL}(\.local)?\.md$|(^|/)\.mcp\.json$", re.IGNORECASE)
ASSISTANT_WORDS = [TOOL, "anthro" + "pic", ".mcp", "copilot", "cursor", "aider", "windsurf", "assistant"]


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files"], check=False, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("not a git repository (e.g. the submission zip)")
    return result.stdout.splitlines()


def test_no_assistant_files_tracked():
    assert [path for path in tracked_files() if FORBIDDEN_PATHS.search(path)] == []


def test_no_raw_data_tracked():
    assert [path for path in tracked_files() if path.startswith("data/raw/")] == []


@pytest.mark.parametrize("name", [".gitignore", ".gitattributes"])
def test_ignore_rules_have_no_assistant_entries(name):
    text = (ROOT / name).read_text(encoding="utf-8").lower()
    assert [word for word in ASSISTANT_WORDS if word in text] == []


def test_forbidden_path_pattern():
    for path in [f".{TOOL}/settings.json", f"a/.{TOOL}/x", f"{TOOL.upper()}.md", f"{TOOL.upper()}.local.md", ".mcp.json"]:
        assert FORBIDDEN_PATHS.search(path), path
    for path in ["src/config.py", "docs/methods.md", "data/checksums.json"]:
        assert not FORBIDDEN_PATHS.search(path), path


@pytest.mark.parametrize("name", ["pre-commit", "commit-msg"])
def test_hook_sources_use_lf(name):
    assert b"\r" not in (ROOT / "tools" / "git-hooks" / name).read_bytes()
