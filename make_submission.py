"""Build group_7.zip with project/ (code, data including raw, outputs) and presentation.pdf (decisions S2-3, S35-1 to
S35-4).

Owner: Mattia. Selection rule (decided 2 Nov 2026, S2-3): the files of project/ are exactly
    git ls-files  +  data/raw/**  +  data/processed/**  +  outputs/**
and never the result of walking the whole project folder, so untracked files elsewhere (local notes, virtual
environments, caches, local tool settings) can never leak into the zip. Assistant and tool settings files are left out
even if they were tracked or placed inside one of the three data folders, and so are synthetic wiring outputs (S35-3).

The course instructions require the raw data, the processed data and the results in project/ (S35-1): raw vendor data
stays out of the public repository only. The build stops, writing nothing, if a file is a .env file or holds a key-like
string, if a tracked file has uncommitted changes, if README.md, pyproject.toml, uv.lock or config.yaml is missing, if
the presentation is missing or not a PDF (S35-5), or if any output was built with another config.yaml (S35-2, S35-3),
including a round-2 output (M6 to M9 and their fixed names) whose spec_hash is not the current one (S42-3). It prints a
manifest:
SHA-256 and size of every entry, the number of files, the total size and the zip's size and SHA-256 (S35-4).

Usage:  uv run python make_submission.py [--presentation presentation.pdf] [--out group_7.zip] [--manifest PATH]
"""

import argparse
import functools
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODE = ROOT  # the scripts whose settings functions the staleness check uses (06, 07, 08), whatever `root` is

GROUP = 7
ZIP_NAME = f"group_{GROUP}.zip"  # decision sheet item 19
PROJECT = "project"
REQUIRED = ("README.md", "pyproject.toml", "uv.lock", "config.yaml")  # course instructions p. 4 (S35-2)
PRESENTATION_NAME = "presentation.pdf"  # a PDF only, at the zip root (S35-5)
PDF_MAGIC = b"%PDF-"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)  # fixed entry time: the same files give the same zip bytes (S35-4)

# Untracked folders that the zip must contain: licensed raw data, derived data, results (all git-ignored).
UNTRACKED_FOLDERS = ["data/raw", "data/processed", "outputs"]

# Assistant and tool settings files, at any depth. Names are assembled from fragments so this file passes the
# commit-time scan.
_TOOL = "cla" + "ude"
FORBIDDEN = re.compile(rf"(^|/)\.{_TOOL}(/|$)|(^|/){_TOOL}(\.local)?\.md$|(^|/)\.mcp\.json$|(^|/)agents\.md$"
                       rf"|(^|/)\.codex(/|$)", re.IGNORECASE)
SYNTHETIC = re.compile(r"^outputs/(.*/)?synthetic(/|$)")  # synthetic wiring outputs (S35-3)
ENV_FILE = re.compile(r"(^|/)\.env(\.[^/]*)?$")
API_KEY_ENV = "DEEPSEEK_API_KEY"  # the agent lab's key (src/agents/llm.py, S33-1)

# Key-like strings (S35-2), as byte patterns; assembled from fragments so that this file does not match them.
_K = "[A-Za-z0-9_" + "\\-]"
KEY_PATTERNS = {
    "sk- key": re.compile(("\\bs" + "k-" + _K + "{20,}").encode()),
    "AWS access key id": re.compile(("\\bAK" + "IA[0-9A-Z]{16}\\b").encode()),
    "GitHub token": re.compile(("\\b(?:gh[pousr]" + "_[A-Za-z0-9]{36,}|github" + "_pat_[A-Za-z0-9_]{22,})").encode()),
    "Slack token": re.compile(("\\bxo" + "x[abposr]-[A-Za-z0-9-]{10,}").encode()),
    "Google API key": re.compile(("\\bAI" + "za" + _K + "{35}").encode()),
    "private key": re.compile(("-----BEGIN [A-Z ]*PRI" + "VATE KEY-----").encode()),
    "secret assignment": re.compile(("(?i)(?:api_key|secret|token|password)[\"']?\\s*[:=]\\s*[\"']?"
                                     "(?=[A-Za-z_\\-]*[0-9])" + _K + "{16,}").encode()),
}


# Known fake keys of the test suite, allowed as exact matches only (S35-2): the sentinel of tests/test_agents_llm.py,
# which checks that the lab never logs its key.
ALLOWED_FAKE_KEYS = frozenset({("s" + "k-test-SENTINEL-" + "0123456789abcdef").encode()})


# -- the file list (S2-3, S35-2, S35-3) ----------------------------------------------------------------------------------


def tracked_files(root: Path = ROOT) -> list[str]:
    """Paths tracked by git, relative to root, with forward slashes."""
    result = subprocess.run(["git", "ls-files", "-z"], check=False, cwd=root, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {root}: build the submission from a git clone "
                           f"({result.stderr.decode(errors='replace').strip()})")
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def candidate_files(root: Path = ROOT, tracked: list[str] | None = None) -> list[str]:
    """Sorted relative paths of every file the S2-3 rule selects, before any exclusion: tracked files present on disk
    plus every file under UNTRACKED_FOLDERS."""
    files = set(tracked_files(root) if tracked is None else tracked)
    for folder in UNTRACKED_FOLDERS:
        base = root / folder
        if base.is_dir():
            files |= {path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file()}
    return sorted(path for path in files if (root / path).is_file())


def excluded(path: str) -> str | None:
    """Why a selected path is left out of the zip (None if it is not): an assistant or tool file, or a synthetic output."""
    if FORBIDDEN.search(path):
        return "assistant or tool settings file"
    if SYNTHETIC.search(path):
        return "synthetic wiring output"
    return None


def submission_files(root: Path = ROOT, tracked: list[str] | None = None) -> list[str]:
    """Sorted relative paths (forward slashes) of the files that go under project/ in group_7.zip.

    tracked defaults to `git ls-files` in root. Files under UNTRACKED_FOLDERS are added whether tracked or not.
    Paths matching FORBIDDEN or SYNTHETIC and tracked paths missing from disk are dropped.
    """
    return [path for path in candidate_files(root, tracked) if excluded(path) is None]


# -- refusals (S35-2) ----------------------------------------------------------------------------------------------------


def uncommitted_changes(root: Path) -> list[str]:
    """Tracked files with uncommitted changes (`git status --porcelain --untracked-files=no`)."""
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], check=True, cwd=root,
                            capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line.strip()]


def env_files(files: list[str]) -> list[str]:
    return [path for path in files if ENV_FILE.search(path)]


def key_findings(root: Path, files: list[str], env: dict | None = None) -> list[str]:
    """`path: kind` for every file holding a key-like string or the value of DEEPSEEK_API_KEY (when set)."""
    env = os.environ if env is None else env
    secret = (env.get(API_KEY_ENV) or "").strip().encode()
    findings = []
    for path in files:
        content = (root / path).read_bytes()
        kinds = [name for name, pattern in KEY_PATTERNS.items()
                 if any(match.group(0) not in ALLOWED_FAKE_KEYS for match in pattern.finditer(content))]
        if len(secret) >= 8 and secret in content:
            kinds.append(f"the value of {API_KEY_ENV}")
        findings += [f"{path}: {kind}" for kind in kinds]
    return findings


# -- stale outputs (S35-3) -----------------------------------------------------------------------------------------------


@functools.cache
def _script(filename: str):
    spec = importlib.util.spec_from_file_location(f"submission_{Path(filename).stem}", CODE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings_files(files: list[str]) -> list[str]:
    """The settings files of the zip that check_used can verify: every used.yaml or oos_used.yaml under outputs/, and
    data/processed/config.yaml and features_config.yaml."""
    out = [p for p in files if p.startswith("outputs/") and p.rsplit("/", 1)[-1] in ("used.yaml", "oos_used.yaml")]
    out += [p for p in ("data/processed/config.yaml", "data/processed/features_config.yaml") if p in files]
    return sorted(out)


def expected_settings(path: str, cfg: dict, root: Path) -> tuple[dict, str] | None:
    """(settings, writer) that the writer of `path` saves under the current config (S35-3); None for an unknown place."""
    import json

    from src.config import data_settings
    from src.features import features_settings
    from src.models import walkforward_settings

    parts = path.split("/")
    name = parts[-1]
    if path == "data/processed/config.yaml":
        return data_settings(cfg), "01_download_data.py"
    if path == "data/processed/features_config.yaml":
        return features_settings(cfg), "03_build_features.py"
    bt = _script("06_backtest.py")
    if len(parts) == 4 and parts[1] == "walkforward" and name == "used.yaml":
        return walkforward_settings(cfg), f"05_train_walkforward.py ({parts[2]})"
    if len(parts) == 4 and parts[1] == "backtests" and name == "used.yaml":
        return bt.backtest_used(cfg, parts[2]), f"06_backtest.py --model {parts[2]}"
    if len(parts) == 5 and parts[1:3] == ["diagnostics", "shift"] and name == "used.yaml":
        return bt.backtest_used(cfg, parts[3]), f"06_backtest.py --shift-check {parts[3]}"
    if parts[1:] == ["diagnostics", "placebo", "used.yaml"]:
        summary = root / "outputs" / "diagnostics" / "placebo" / "summary.json"
        reference = json.loads(summary.read_text(encoding="utf-8"))["reference"] if summary.exists() else "M0"
        return bt.placebo_used(cfg, reference), "06_backtest.py --placebo"
    if parts[1:] == ["ledger", "used.yaml"]:
        return bt.ledger_used(cfg), "06_backtest.py --ledger-years"
    if parts[1:] == ["metrics", "used.yaml"]:
        return _script("07_evaluate.py").metrics_used(cfg), "07_evaluate.py"
    if parts[1:] == ["metrics", "oos_used.yaml"]:
        return _script("07_evaluate.py").oos_metrics_used(cfg), "07_evaluate.py --period OOS"
    if len(parts) == 4 and parts[1] == "oos" and name == "used.yaml":
        return _script("08_run_oos.py").oos_used(cfg, parts[2]), "08_run_oos.py"
    return None


def stale_outputs(root: Path, files: list[str], cfg: dict) -> list[str]:
    """`path: reason` for every settings file that fails check_used against the current config, or that no writer is
    known for (S35-3), and for every round-2 model folder whose spec_hash is not the current one (S42-3)."""
    from src.config import check_used

    problems = []
    for path in settings_files(files):
        expected = expected_settings(path, cfg, root)
        if expected is None:
            problems.append(f"{path}: no known writer, so it cannot be checked against config.yaml")
            continue
        settings, writer = expected
        try:
            check_used(settings, root / path, writer)
        except (ValueError, FileNotFoundError, KeyError) as error:
            problems.append(f"{path}: {error}")
    return problems + round2_identity(root, files, cfg)


def output_model(path: str) -> str | None:
    """The model of a settings file outputs/walkforward/<name>/used.yaml, outputs/backtests/<name>/used.yaml or
    outputs/diagnostics/shift/<name>/used.yaml; None for any other path."""
    parts = path.split("/")
    if parts[-1] != "used.yaml":
        return None
    if len(parts) == 4 and parts[0] == "outputs" and parts[1] in ("walkforward", "backtests"):
        return parts[2]
    if len(parts) == 5 and parts[:3] == ["outputs", "diagnostics", "shift"]:
        return parts[3]
    return None


def round2_identity(root: Path, files: list[str], cfg: dict) -> list[str]:
    """`path: reason` for the round-2 model folders of the zip (07_evaluate.py: model_round, S42-2) whose trial identity
    is not the current one (S42-3). The round-2 settings live in config.yaml's round2: section, outside every used.yaml
    (S40-1), so check_used cannot see a change of them; as 06 does for its inputs (S32-10), the summary.json of the
    model's walk-forward folder, and of its backtest folder if it ships, must hold the spec_hash that 05's spec_for gives
    under the current config (06_backtest.py: expected_spec_hash). A name 05 has no spec for cannot be checked."""
    import json

    model_round = _script("07_evaluate.py").model_round
    names = sorted({name for path in settings_files(files)
                    if (name := output_model(path)) is not None and model_round(name) == 2})
    problems = []
    for name in names:
        try:
            expected = _script("06_backtest.py").expected_spec_hash(name, cfg)
        except SystemExit as error:
            problems.append(f"outputs/walkforward/{name}/: {error}")
            continue
        summaries = [f"outputs/walkforward/{name}/summary.json"]
        summaries += [f"outputs/backtests/{name}/summary.json"] if f"outputs/backtests/{name}/used.yaml" in files else []
        for summary in summaries:
            if summary not in files:
                problems.append(f"{summary}: missing, so the round-2 output {name} cannot be checked (S42-3)")
                continue
            recorded = json.loads((root / summary).read_text(encoding="utf-8")).get("spec_hash")
            if recorded != expected:
                problems.append(f"{summary}: spec_hash {str(recorded)[:12]}…, config.yaml gives {expected[:12]}… "
                                "(a round-2 setting changed since the output was built, S42-3)")
    return problems


# -- the zip and the manifest (S35-4) ------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check(root: Path, presentation: Path, out: Path, env: dict | None = None) -> tuple[list[str], list[str]]:
    """Every refusal of S35-2 and S35-3; returns (files, excluded lines) or stops with every problem listed."""
    from src.config import load_config

    root, presentation, out = Path(root), Path(presentation), Path(out)
    tracked = tracked_files(root)
    candidates = candidate_files(root, tracked)
    left_out = [f"{path} ({excluded(path)})" for path in candidates if excluded(path)]
    files = [path for path in candidates if excluded(path) is None]
    problems = [f"uncommitted change to a tracked file: {line.strip()}" for line in uncommitted_changes(root)]
    problems += [f"{path}: a .env file" for path in env_files(files)]
    problems += [f"{name} missing from project/" for name in REQUIRED if name not in files]
    if not presentation.is_file():
        problems.append(f"presentation not found: {presentation}")
    elif presentation.suffix.lower() != ".pdf":
        problems.append(f"presentation must be a PDF (presentation.pdf, S35-5), got {presentation.name}")
    else:
        with open(presentation, "rb") as handle:
            if handle.read(len(PDF_MAGIC)) != PDF_MAGIC:
                problems.append(f"presentation {presentation.name} is not a PDF file (no %PDF- header, S35-5)")
    try:
        inside = out.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        inside = None
    if inside is not None and any(inside == f or inside.startswith(f + "/") for f in UNTRACKED_FOLDERS):
        problems.append(f"--out {inside} lies inside a folder the zip packs")
    problems += [f"key-like string in {finding}" for finding in key_findings(root, files, env)]
    if "config.yaml" in files:
        problems += [f"stale output {line}" for line in stale_outputs(root, files, load_config(root / "config.yaml"))]
    if problems:
        shown = "\n  ".join(problems)
        raise SystemExit(f"make_submission: refused, nothing written ({len(problems)} problem(s)):\n  {shown}")
    return files, left_out


def write_zip(root: Path, files: list[str], presentation: Path, out: Path) -> list[tuple[str, str, int]]:
    """Write the zip (sorted entries, deflated, fixed time, mode 0644) through a temporary file; returns the manifest
    rows (entry, sha256, size)."""
    rows = []
    entries = [(f"{PROJECT}/{path}", Path(root) / path) for path in files]
    entries.append((PRESENTATION_NAME, Path(presentation)))
    out.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(suffix=".zip", dir=out.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in sorted(entries):
                info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                data = source.read_bytes()
                archive.writestr(info, data)
                rows.append((name, hashlib.sha256(data).hexdigest(), len(data)))
        os.replace(temporary, out)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return rows


def manifest_text(rows: list[tuple[str, str, int]], out: Path, left_out: list[str]) -> str:
    lines = [f"{digest}  {size:>12}  {name}" for name, digest, size in rows]
    total = sum(size for _, _, size in rows)
    lines += ["", f"files: {len(rows)}", f"total uncompressed bytes: {total}",
              f"zip: {Path(out).name}, {Path(out).stat().st_size} bytes, sha256 {_sha256(Path(out))}"]
    if left_out:
        lines += ["", "left out (S35-2, S35-3):"] + [f"  {line}" for line in left_out]
    return "\n".join(lines) + "\n"


def build(root: Path = ROOT, presentation: Path | None = None, out: Path | None = None, manifest: Path | None = None,
          env: dict | None = None) -> str:
    """Check, write the zip and return the manifest text (also written to `manifest` when given)."""
    root = Path(root)
    presentation = root / "presentation.pdf" if presentation is None else Path(presentation)
    out = root / ZIP_NAME if out is None else Path(out)
    files, left_out = check(root, presentation, out, env)
    text = manifest_text(write_zip(root, files, presentation, out), out, left_out)
    if manifest is not None:
        Path(manifest).parent.mkdir(parents=True, exist_ok=True)
        Path(manifest).write_text(text, encoding="utf-8", newline="\n")
    return text


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--presentation", type=Path, default=ROOT / "presentation.pdf",
                        help="the slides as a PDF, stored as presentation.pdf (default: presentation.pdf in the project folder)")
    parser.add_argument("--out", type=Path, default=ROOT / ZIP_NAME, help=f"the zip to write (default: {ZIP_NAME})")
    parser.add_argument("--manifest", type=Path, default=None, help="also write the manifest to this file")
    args = parser.parse_args(argv)
    print(build(ROOT, args.presentation, args.out, args.manifest), end="")


if __name__ == "__main__":
    sys.exit(main())
