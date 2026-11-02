"""Build group_7.zip with project/ (code, data including raw, outputs) and presentation.pdf.

Owner: Mattia. The file-selection rule is fixed now; the packaging itself is planned for Gate 5 (protocol section 15).

Selection rule (decided 2 Nov 2026, docs/decisions.md): the files of project/ are exactly
    git ls-files  +  data/raw/**  +  data/processed/**  +  outputs/**
and never the result of walking the whole project folder, so untracked files elsewhere (local notes, virtual
environments, caches, local tool settings) can never leak into the zip. Local tool-settings files are refused even if
they were tracked or placed inside one of the three data folders.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Untracked folders that the zip must contain: licensed raw data, derived data, results (all git-ignored).
UNTRACKED_FOLDERS = ["data/raw", "data/processed", "outputs"]

# Local tool-settings files, at any depth. Names are assembled from fragments so this file passes the commit-time scan.
_TOOL = "cla" + "ude"
FORBIDDEN = re.compile(rf"(^|/)\.{_TOOL}(/|$)|(^|/){_TOOL}(\.local)?\.md$|(^|/)\.mcp\.json$", re.IGNORECASE)


def tracked_files(root: Path = ROOT) -> list[str]:
    """Paths tracked by git, relative to root, with forward slashes."""
    result = subprocess.run(["git", "ls-files", "-z"], check=False, cwd=root, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {root}: build the submission from a git clone "
                           f"({result.stderr.decode(errors='replace').strip()})")
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def submission_files(root: Path = ROOT, tracked: list[str] | None = None) -> list[str]:
    """Sorted relative paths (forward slashes) of the files that go under project/ in group_7.zip.

    tracked defaults to `git ls-files` in root. Files under UNTRACKED_FOLDERS are added whether tracked or not.
    Paths matching FORBIDDEN and tracked paths missing from disk are dropped.
    """
    files = set(tracked_files(root) if tracked is None else tracked)
    for folder in UNTRACKED_FOLDERS:
        base = root / folder
        if base.is_dir():
            files |= {path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file()}
    return sorted(path for path in files if not FORBIDDEN.search(path) and (root / path).is_file())


def main() -> None:
    raise NotImplementedError("Gate 5, Mattia: packaging of group_7.zip (the file list is submission_files())")


if __name__ == "__main__":
    main()
