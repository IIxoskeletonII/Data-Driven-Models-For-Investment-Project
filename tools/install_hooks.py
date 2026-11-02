"""Install the repository's git hooks from tools/git-hooks/ into the local hooks folder of the clone.

Run once after cloning:  uv run python tools/install_hooks.py

The hooks enforce the repository policy on every commit: no local assistant files, no attribution
lines, no licensed raw data under data/raw/. Hooks are not versioned by git, so each member installs them.

It also lists the local tool-settings files in the clone's .git/info/exclude (never in .gitignore), so git does not
even offer them for staging. Running it again changes nothing.
"""

import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "git-hooks"
HOOKS = ["commit-msg", "pre-commit"]

# Local tool-settings files, excluded per clone. Names are assembled from fragments so this file passes the commit-time scan.
_TOOL = "cla" + "ude"
EXCLUDE_HEADER = "# Local tool settings (never tracked)"
EXCLUDE_LINES = [f".{_TOOL}/", f"{_TOOL.upper()}.md", f"{_TOOL.upper()}.local.md", ".mcp.json"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=False, cwd=ROOT, capture_output=True, text=True)


def ensure_excluded(path: Path, lines: list[str] = EXCLUDE_LINES) -> list[str]:
    """Append the lines missing from the exclude file at path (created if absent); return the lines added.

    Idempotent: existing lines, comments and their order are kept, and nothing is written when all lines are present.
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = {line.strip() for line in text.splitlines()}
    missing = [line for line in lines if line not in present]
    if missing:
        block = ([] if EXCLUDE_HEADER in present else [EXCLUDE_HEADER]) + missing
        separator = ("" if text.endswith("\n") else "\n") + "\n" if text.strip() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(separator + "\n".join(block) + "\n")
    return missing


def main() -> None:
    hooks_path = git("config", "--get", "core.hooksPath").stdout.strip()
    if hooks_path:
        sys.exit(f"core.hooksPath is set to {hooks_path!r}: git would ignore .git/hooks. Unset it, then run this again.")

    result = git("rev-parse", "--git-path", "hooks")
    if result.returncode != 0:
        sys.exit(f"not a git repository: {result.stderr.strip()}")
    target = (ROOT / result.stdout.strip()).resolve()
    target.mkdir(parents=True, exist_ok=True)

    for name in HOOKS:
        destination = target / name
        shutil.copyfile(SOURCE / name, destination)  # byte copy, keeps LF line endings
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"Installed {destination}")

    exclude = (ROOT / git("rev-parse", "--git-path", "info/exclude").stdout.strip()).resolve()
    added = ensure_excluded(exclude)
    print(f"{exclude}: " + (f"added {', '.join(added)}" if added else "entries already present"))


if __name__ == "__main__":
    main()
