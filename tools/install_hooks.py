"""Install the repository's git hooks from tools/git-hooks/ into the local hooks folder of the clone.

Run once after cloning:  uv run python tools/install_hooks.py

The hooks enforce the repository policy on every commit: no local assistant files, no attribution
lines, no licensed raw data under data/raw/. Hooks are not versioned by git, so each member installs them.
"""

import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "git-hooks"
HOOKS = ["commit-msg", "pre-commit"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=False, cwd=ROOT, capture_output=True, text=True)


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


if __name__ == "__main__":
    main()
