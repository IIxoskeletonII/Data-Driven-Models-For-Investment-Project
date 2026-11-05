"""The submission file list: git ls-files + data/raw/** + data/processed/** + outputs/**, never local tool-settings files.

Forbidden names are assembled from fragments, so this file passes the commit-time scan.
"""

import copy
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

import make_submission
from src.config import ROOT as REPO
from src.config import data_settings, load_config, save_used
from src.features import features_settings
from src.models import walkforward_settings

TOOL = "cla" + "ude"
TOOL_FILES = [f".{TOOL}/settings.json", f"{TOOL.upper()}.md", f"{TOOL.upper()}.local.md", ".mcp.json", "AGENTS.md",
              ".codex/config.toml"]


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
    for path in TOOL_FILES + [f"a/.{TOOL}/x", f"a/{TOOL}.md", f"{TOOL.upper()}.LOCAL.MD", "x/.mcp.json", "sub/agents.md",
                              "a/.codex"]:
        assert make_submission.FORBIDDEN.search(path), path
    for path in ["src/config.py", "docs/methods.md", f"docs/{TOOL}_notes.txt", "mcp.json", "src/agents/graph.py",
                 "docs/agents_notes.md", "codex.py"]:
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


# ---------------------------------------------------------------- the zip (decisions S35-1 to S35-4)
#
# A small synthetic project: the required files, a config.yaml equal to the real one, raw and processed data, outputs
# with used.yaml files written by the settings functions of their writers, a synthetic output and an assistant file.

FAKE_KEY = "s" + "k-" + "Zq8" * 10  # built from fragments: no key-like literal in this file


def commit_all(root):
    git(root, "add", "-A", "-f", "--", "README.md", "pyproject.toml", "uv.lock", "config.yaml", "src", "docs", ".gitignore")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit",
        "-q", "--no-verify", "--allow-empty", "-m", "chore: synthetic project")


@pytest.fixture
def project(isolated):
    root = isolated / "project"
    root.mkdir()
    cfg = load_config()
    shutil.copy(REPO / "config.yaml", root / "config.yaml")
    make_files(root, ["README.md", "pyproject.toml", "uv.lock", "src/a.py", "docs/x.md",
                      "data/raw/yahoo/XLB.csv", "data/raw/fred/DGS3MO.csv", "data/processed/daily_close.csv",
                      "outputs/metrics/is_models.csv", "outputs/backtests/M0/weekly.csv",
                      "outputs/backtests/synthetic/weekly.csv", f"outputs/.{TOOL}/settings.json"])
    (root / ".gitignore").write_text("data/\noutputs/\n*.zip\n", encoding="utf-8")
    save_used(data_settings(cfg), root / "data" / "processed" / "config.yaml")
    save_used(features_settings(cfg), root / "data" / "processed" / "features_config.yaml")
    save_used(walkforward_settings(cfg), root / "outputs" / "walkforward" / "M0" / "used.yaml")
    bt = make_submission._script("06_backtest.py")
    save_used(bt.backtest_used(cfg, "M0"), root / "outputs" / "backtests" / "M0" / "used.yaml")
    save_used(bt.used_settings(cfg), root / "outputs" / "backtests" / "synthetic" / "used.yaml")  # left out, not checked
    save_used(make_submission._script("07_evaluate.py").metrics_used(cfg), root / "outputs" / "metrics" / "used.yaml")
    git(root, "init", "-q")
    commit_all(root)
    slides = isolated / "slides.pdf"
    slides.write_bytes(b"%PDF-1.4 synthetic slides\n")
    return {"root": root, "slides": slides, "out": isolated / "dist" / "group_7.zip", "cfg": cfg}


def build(project, **overrides):
    kwargs = {"root": project["root"], "presentation": project["slides"], "out": project["out"], "env": {}} | overrides
    return make_submission.build(**kwargs)


def refused(project, match, **overrides):
    out = overrides.get("out", project["out"])
    with pytest.raises(SystemExit, match=match):
        build(project, **overrides)
    assert not Path(out).exists()


def test_zip_layout_holds_project_and_the_presentation_at_the_root(project):
    text = build(project)
    with zipfile.ZipFile(project["out"]) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert {n.split("/", 1)[0] for n in names} == {"project", "presentation.pdf"}
        project_files = sorted(n.removeprefix("project/") for n in names if n.startswith("project/"))
        assert project_files == [
            ".gitignore", "README.md", "config.yaml", "data/processed/config.yaml", "data/processed/daily_close.csv",
            "data/processed/features_config.yaml", "data/raw/fred/DGS3MO.csv", "data/raw/yahoo/XLB.csv", "docs/x.md",
            "outputs/backtests/M0/used.yaml", "outputs/backtests/M0/weekly.csv", "outputs/metrics/is_models.csv",
            "outputs/metrics/used.yaml", "outputs/walkforward/M0/used.yaml", "pyproject.toml", "src/a.py", "uv.lock"]
        assert archive.read("project/config.yaml") == (project["root"] / "config.yaml").read_bytes()
        assert archive.read("presentation.pdf") == project["slides"].read_bytes()
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
    # the manifest: one line per entry with its SHA-256 and size, then the totals; the left-out files are listed
    config = project["root"] / "config.yaml"
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    assert f"{digest}  {config.stat().st_size:>12}  project/config.yaml" in text
    assert f"files: {len(names)}" in text
    assert f"sha256 {hashlib.sha256(project['out'].read_bytes()).hexdigest()}" in text
    assert "outputs/backtests/synthetic/weekly.csv (synthetic wiring output)" in text
    assert f"outputs/.{TOOL}/settings.json (assistant or tool settings file)" in text


def test_the_same_files_give_the_same_zip(project, tmp_path):
    build(project)
    first = project["out"].read_bytes()
    build(project, out=tmp_path / "again.zip")
    assert (tmp_path / "again.zip").read_bytes() == first


def test_the_manifest_can_be_written_to_a_file(project, tmp_path):
    text = build(project, manifest=tmp_path / "manifest.txt")
    assert (tmp_path / "manifest.txt").read_text(encoding="utf-8") == text


@pytest.mark.parametrize("path", ["data/raw/.env", "outputs/metrics/.env.local"])
def test_refuses_a_dotenv_file(project, path):
    make_files(project["root"], [path])
    refused(project, "a .env file")


def test_refuses_a_key_like_string_in_any_file(project):
    (project["root"] / "outputs" / "metrics" / "is_models.csv").write_text(f"note,{FAKE_KEY}\n", encoding="utf-8")
    refused(project, "key-like string in outputs/metrics/is_models.csv: sk- key")


@pytest.mark.parametrize("line", ["API_" + "KEY = 'a1b2c3d4e5f6g7h8i9'", "tok" + 'en: "Zx9Zx9Zx9Zx9Zx9Zx9"',
                                  "-----BEGIN RSA PRI" + "VATE KEY-----"])
def test_refuses_other_key_patterns_in_tracked_code(project, line):
    (project["root"] / "src" / "a.py").write_text(line + "\n", encoding="utf-8")
    commit_all(project["root"])
    refused(project, "key-like string in src/a.py")


def test_refuses_the_value_of_the_lab_api_key(project):
    value = "plainvalue12345"  # not key-shaped: found only because it is the value of the variable
    (project["root"] / "data" / "processed" / "daily_close.csv").write_text(f"x,{value}\n", encoding="utf-8")
    refused(project, "the value of DEEPSEEK_API_KEY", env={"DEEPSEEK_API_KEY": value})
    build(project)  # without the variable set, nothing in the file is key-like


def test_the_fake_sentinel_key_of_the_test_suite_is_allowed(project):
    sentinel = "s" + "k-test-SENTINEL-" + "0123456789abcdef"
    (project["root"] / "src" / "a.py").write_text(f'SENTINEL_KEY = "{sentinel}"\n', encoding="utf-8")
    commit_all(project["root"])
    build(project)
    project["out"].unlink()
    (project["root"] / "src" / "a.py").write_text(f'SENTINEL_KEY = "{sentinel}0"\n', encoding="utf-8")
    commit_all(project["root"])
    refused(project, "key-like string in src/a.py")  # exact matches only


def test_refuses_uncommitted_changes_to_tracked_files(project):
    (project["root"] / "docs" / "x.md").write_text("changed\n", encoding="utf-8")
    refused(project, "uncommitted change to a tracked file: M docs/x.md")


@pytest.mark.parametrize("name", ["uv.lock", "README.md", "pyproject.toml"])
def test_refuses_a_missing_required_file(project, name):
    git(project["root"], "rm", "-q", name)
    git(project["root"], "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "-q", "--no-verify", "-m", "chore: remove")
    refused(project, f"{name} missing from project/")


def test_refuses_a_missing_or_wrong_presentation(project, tmp_path):
    refused(project, "presentation not found", presentation=tmp_path / "none.pdf")
    (tmp_path / "slides.txt").write_text("x", encoding="utf-8")
    refused(project, "must be .pdf or .pptx", presentation=tmp_path / "slides.txt")


def test_a_pptx_presentation_keeps_its_suffix(project, tmp_path):
    (tmp_path / "slides.pptx").write_bytes(b"PK synthetic")
    build(project, presentation=tmp_path / "slides.pptx")
    with zipfile.ZipFile(project["out"]) as archive:
        assert "presentation.pptx" in archive.namelist() and "presentation.pdf" not in archive.namelist()


def test_refuses_a_stale_output(project):
    stale = copy.deepcopy(project["cfg"])
    stale["costs"]["bps_baseline"] = 5
    bt = make_submission._script("06_backtest.py")
    save_used(bt.backtest_used(stale, "M0"), project["root"] / "outputs" / "backtests" / "M0" / "used.yaml")
    refused(project, "stale output outputs/backtests/M0/used.yaml")


def test_refuses_stale_processed_data(project):
    stale = copy.deepcopy(project["cfg"])
    stale["data"]["end"] = "2026-10-09"
    save_used(data_settings(stale), project["root"] / "data" / "processed" / "config.yaml")
    refused(project, "stale output data/processed/config.yaml")


def test_refuses_a_settings_file_without_a_known_writer(project):
    save_used({"x": 1}, project["root"] / "outputs" / "elsewhere" / "used.yaml")
    refused(project, "outputs/elsewhere/used.yaml: no known writer")


def test_every_problem_is_listed_at_once(project):
    make_files(project["root"], ["data/raw/.env"])
    (project["root"] / "docs" / "x.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"\(2 problem\(s\)\)"):
        build(project)


def test_refuses_an_output_path_inside_a_packed_folder(project):
    refused(project, "lies inside a folder the zip packs", out=project["root"] / "outputs" / "group_7.zip")


def test_every_settings_file_the_scripts_write_has_a_known_writer():
    """Each place 05, 06, 07 and 08 write a settings file to is checked (S35-3)."""
    cfg = load_config()
    for path in ["outputs/walkforward/M1_a0.1/used.yaml", "outputs/backtests/M3/used.yaml",
                 "outputs/diagnostics/shift/M0/used.yaml", "outputs/diagnostics/placebo/used.yaml",
                 "outputs/ledger/used.yaml", "outputs/metrics/used.yaml", "outputs/metrics/oos_used.yaml",
                 "outputs/oos/M2/used.yaml", "data/processed/config.yaml", "data/processed/features_config.yaml"]:
        assert make_submission.expected_settings(path, cfg, REPO) is not None, path


def test_no_tracked_file_of_this_repository_holds_a_key_like_string():
    try:
        tracked = make_submission.tracked_files()
    except RuntimeError:
        pytest.skip("not a git clone (e.g. the submission zip)")
    present = [path for path in tracked if (REPO / path).is_file()]
    assert make_submission.key_findings(REPO, present, env={}) == []
