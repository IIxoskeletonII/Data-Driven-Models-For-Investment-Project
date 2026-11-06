"""Run the whole In-Sample pipeline in order, from the archived raw snapshot to the In-Sample metrics and plots (Gate 5,
decisions S39-1 to S39-6).

Steps, each run as its own process from the project root, exactly as the README's commands:
    01_download_data.py                 verify data/raw/ against its manifest, rebuild data/processed/daily_*.csv
                                        (offline: refused before it starts if data/raw/manifest.json is missing)
    03_build_features.py                features, market states, labels, forward returns (In-Sample)
    05_train_walkforward.py --model R   every rung R of 05's RUNGS, then
    05_train_walkforward.py --fixed F   every fixed configuration F of 05's fixed_names(cfg): the list is read from 05,
                                        so a rung added there is run without a change here
    06_backtest.py --all                In-Sample backtest of every walk-forward
    06_backtest.py --shift-check R...   §12 one-week-shift check of every rung
    06_backtest.py --placebo            §11 placebo books on M0's weeks
    05_train_walkforward.py --agent-returns   re-score the agent candidates through the sealed vault (no LLM call)
    05_train_walkforward.py --select    §07 gate, trial metrics, DSR and PBO
    07_evaluate.py                      In-Sample metrics, benchmarks, shift check, placebo, plots
    06_backtest.py --ledger-years       ledger reconciliation of the engine (last: its failure leaves every result above)

It never runs 04_agent_lab.py (agent results replay from their committed caches) or 08_run_oos.py (the single
Out-of-Sample run, run by hand). It stops at the first failing step, naming it, and prints a table of every step with
its status and time. In a git checkout it refuses a dirty tree, and fails if the run changed a tracked file; outside one
(the submission zip) it says that the check is skipped. Once FROZEN.lock exists it refuses unless --after-freeze is
given; with it, --agent-returns and --select are skipped (their outputs are frozen, S37-8) and the rest is rerun.
Every step gets PYTHONHASHSEED = config seed.

Run:  uv run python run_all.py [--after-freeze]
"""

import argparse
import functools
import importlib.util
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.config import ROOT, load_config

LOCK_NAME = "FROZEN.lock"
RAW_MANIFEST = "data/raw/manifest.json"
NEVER_RUN = ("04_agent_lab.py", "08_run_oos.py")  # S39-2: the lab replays from its caches; the OOS run is by hand
WALKFORWARD = "05_train_walkforward.py"
BACKTEST = "06_backtest.py"


def say(text: str) -> None:
    """print, flushed, so the step headers and the summary keep their place among the steps' own output when stdout is
    a file or a pipe."""
    print(text, flush=True)


@dataclass(frozen=True)
class Step:
    """One command of the pipeline: argv[0] is the script (relative to the project root, or absolute), the rest its
    arguments. frozen: the step writes a frozen artefact and is skipped after the freeze (S37-8 point 2, S39-3)."""

    argv: tuple[str, ...]
    frozen: bool = False

    @property
    def name(self) -> str:
        return " ".join(self.argv)


@dataclass
class Result:
    step: Step
    status: str  # "ok", "FAILED", "skipped" or "not run"
    seconds: float = 0.0
    note: str = ""


@functools.cache
def _script(filename: str):
    """A pipeline script loaded by path (its name starts with a digit); read only."""
    spec = importlib.util.spec_from_file_location(f"run_all_{Path(filename).stem}", ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def walkforward_names(cfg: dict) -> tuple[list[str], list[str]]:
    """(rungs, fixed configurations) of 05_train_walkforward.py: its RUNGS and fixed_names(cfg), in 05's order."""
    s05 = _script(WALKFORWARD)
    return list(s05.RUNGS), list(s05.fixed_names(cfg))


def pipeline(cfg: dict) -> list[Step]:
    """The In-Sample pipeline in order (S39-2)."""
    rungs, fixed = walkforward_names(cfg)
    return [
        Step(("01_download_data.py",)),
        Step(("03_build_features.py",)),
        *(Step((WALKFORWARD, "--model", name)) for name in rungs),
        *(Step((WALKFORWARD, "--fixed", name)) for name in fixed),
        Step((BACKTEST, "--all")),
        Step((BACKTEST, "--shift-check", *rungs)),
        Step((BACKTEST, "--placebo")),
        Step((WALKFORWARD, "--agent-returns"), frozen=True),
        Step((WALKFORWARD, "--select"), frozen=True),
        Step(("07_evaluate.py",)),
        Step((BACKTEST, "--ledger-years")),
    ]


def git_dirty(root: Path) -> list[str] | None:
    """Paths of `git status --porcelain` (untracked files count, git-ignored ones do not), or None when root is not
    inside a git work tree or git is not installed (the submission zip, S39-4)."""
    try:
        inside = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True,
                                text=True, check=False)
    except FileNotFoundError:
        return None
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True,
                            check=True)
    return [line[3:] for line in status.stdout.splitlines() if line.strip()]


def preflight(root: Path, after_freeze: bool) -> None:
    """Stop (SystemExit) before any step: FROZEN.lock without --after-freeze or --after-freeze without it (S39-3);
    no data/raw/manifest.json, so that 01_download_data.py never downloads (S39-2)."""
    locked = (root / LOCK_NAME).exists()
    if locked and not after_freeze:
        raise SystemExit(f"refused: {LOCK_NAME} exists. Rerunning the pipeline rewrites frozen artefacts; pass "
                         "--after-freeze to do it on purpose (05 --agent-returns and --select are then skipped)")
    if after_freeze and not locked:
        raise SystemExit(f"refused: --after-freeze given, but {LOCK_NAME} does not exist")
    if not (root / RAW_MANIFEST).exists():
        raise SystemExit(f"refused: {RAW_MANIFEST} not found. Place the raw data snapshot first (README); run_all.py "
                         "never downloads data")


def summary_table(results: Sequence[Result]) -> str:
    """The table printed at the end of every run: step, status, seconds, note; then the total time."""
    width = max(len("step"), *(len(r.step.name) for r in results)) if results else len("step")
    lines = [f"{'step':<{width}}  {'status':<8}  {'seconds':>8}  note", "-" * (width + 30)]
    for r in results:
        lines.append(f"{r.step.name:<{width}}  {r.status:<8}  {r.seconds:>8.1f}  {r.note}".rstrip())
    lines.append(f"{'total':<{width}}  {'':<8}  {sum(r.seconds for r in results):>8.1f}")
    return "\n".join(lines)


def run_steps(steps: Sequence[Step], root: Path, *, seed: int, after_freeze: bool = False,
              python: str = sys.executable, out: Callable[[str], None] = say) -> list[Result]:
    """Run the steps in order from root, each as `python <argv>` with PYTHONHASHSEED = seed (S39-5). Stops at the first
    failing step (SystemExit naming it, after the summary). In a git work tree, refuses a dirty tree before the first
    step and fails if the run changed a tracked or untracked file (S39-4). Returns one Result per step."""
    root = Path(root)
    banned = [s.name for s in steps if Path(s.argv[0]).name in NEVER_RUN]
    if banned:
        raise SystemExit(f"refused: run_all.py never runs {banned} (S39-2)")
    dirty = git_dirty(root)
    if dirty:
        raise SystemExit(f"refused: the working tree is not clean ({len(dirty)} path(s), first {dirty[0]}); commit or "
                         "remove the changes first")
    if dirty is None:
        out("not a git checkout: the clean-tree check is skipped")
    env = os.environ | {"PYTHONHASHSEED": str(seed)}
    results = [Result(step, "not run") for step in steps]
    for result in results:
        step = result.step
        if step.frozen and after_freeze:
            result.status, result.note = "skipped", "frozen output (S37-8): the committed file is used"
            continue
        out(f"\n=== {step.name}")
        start = time.perf_counter()
        code = subprocess.run([python, *step.argv], cwd=root, env=env, check=False).returncode
        result.seconds = time.perf_counter() - start
        if code != 0:
            result.status, result.note = "FAILED", f"exit code {code}"
            out("\n" + summary_table(results))
            raise SystemExit(f"stopped: step '{step.name}' failed with exit code {code}; the steps before it completed")
        result.status = "ok"
    out("\n" + summary_table(results))
    if dirty is not None:
        changed = git_dirty(root)
        if changed:
            raise SystemExit(f"the run changed {len(changed)} file(s) of the working tree, first {changed[0]}: a "
                             "reproduction must leave it unchanged (new trial rows must be committed on purpose)")
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--after-freeze", action="store_true",
                        help="rerun once FROZEN.lock exists; 05 --agent-returns and --select are skipped (S39-3)")
    args = parser.parse_args(argv)
    cfg = load_config()
    preflight(ROOT, args.after_freeze)
    run_steps(pipeline(cfg), ROOT, seed=int(cfg["seed"]), after_freeze=args.after_freeze)


if __name__ == "__main__":
    main()
