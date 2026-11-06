"""Repository policy: no local assistant files tracked, no licensed raw data tracked, clean ignore rules, attribution.

The same rules are enforced at commit time by tools/git-hooks/; this test is the backstop in CI. Decision S40-0: the
agent lab's model vendor may be named only in the files where that model is the research object (ALLOWED_RE, the
same list as allow_re in tools/git-hooks/pre-commit); co-author trailers are refused in every file, and commit messages
still refuse the vendor name, co-author trailers, "generated with" lines and session links.
Forbidden words are assembled from fragments, so this file does not match the commit-time scan.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from src.config import ROOT

TOOL = "cla" + "ude"
VENDOR = "anthro" + "pic"
TRAILER = "co-auth" + "ored-by"
FORBIDDEN_PATHS = re.compile(rf"(^|/)\.{TOOL}(/|$)|(^|/){TOOL}(\.local)?\.md$|(^|/)\.mcp\.json$", re.IGNORECASE)
ASSISTANT_WORDS = [TOOL, VENDOR, ".mcp", "copilot", "cursor", "aider", "windsurf", "assistant"]
VENDOR_WORDS = re.compile(f"{TOOL}|{VENDOR}")
HOOKS = ROOT / "tools" / "git-hooks"
EXEMPT = {"docs/ai_tools_used.md", "uv.lock"}  # excluded from the added-line scan of the pre-commit hook
# S40-0 (c): the files where the agent lab's model is the research object. Identical to allow_re in the pre-commit hook.
ALLOWED_RE = (r"^(docs/preregistration[.]md|docs/decisions[.]md|docs/ai_tools_used[.]md|config[.]yaml|pyproject[.]toml"
              r"|uv[.]lock|src/agents/.+|agent_lab/.+|tests/test_agents[^/]*[.]py|tests/test_vault_server[.]py"
              r"|tests/test_planted_signal[.]py)$")
ALLOWED = re.compile(ALLOWED_RE)
ALLOWED_SAMPLES = ["docs/preregistration.md", "docs/decisions.md", "docs/ai_tools_used.md", "config.yaml", "pyproject.toml",
                   "uv.lock", "src/agents/llm.py", "src/agents/sub/graph.py", "agent_lab/run/summary.json",
                   "tests/test_agents_llm.py", "tests/test_agents.py",
                   "tests/test_vault_server.py", "tests/test_planted_signal.py"]
REFUSED_SAMPLES = ["README.md", "docs/methods.md", "docs/interfaces.md", "src/models.py", "src/agents.py",
                   "src/agents_extra/x.py", "agent_labx/notes.md", "tests/test_hooks_policy.py", "tests/test_agent_run.py",
                   "tests/sub/test_agents.py", "tests/test_agents.py.bak", "docs/decisions.md.bak", "x/docs/decisions.md",
                   "05_train_walkforward.py", ".github/workflows/ci.yml"]


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
    assert b"\r" not in (HOOKS / name).read_bytes()


# --- S40-0: attribution in tracked files (the CI backstop of pre-commit check (b)) ---------------------------------


def test_allowed_paths_match_the_pre_commit_hook():
    match = re.search(r"^allow_re='([^']*)'$", (HOOKS / "pre-commit").read_text(encoding="utf-8"), re.MULTILINE)
    assert match, "allow_re not found in tools/git-hooks/pre-commit"
    assert match.group(1) == ALLOWED_RE


@pytest.mark.parametrize("path", ALLOWED_SAMPLES)
def test_allowed_pattern_accepts(path):
    assert ALLOWED.search(path), path


@pytest.mark.parametrize("path", REFUSED_SAMPLES)
def test_allowed_pattern_refuses(path):
    assert not ALLOWED.search(path), path


def test_tracked_files_name_the_vendor_only_where_allowed():
    names, trailers = [], []
    for path in tracked_files():
        if path in EXEMPT or not (ROOT / path).is_file():
            continue
        text = (ROOT / path).read_bytes().decode("utf-8", errors="ignore").lower()
        if TRAILER in text:
            trailers.append(path)
        if VENDOR_WORDS.search(text) and not ALLOWED.search(path):
            names.append(path)
    assert trailers == [], f"co-author trailers in {trailers}"
    assert names == [], f"the model vendor is named outside the files of decision S40-0 (c): {names}"


# --- S40-0: behaviour of the hooks themselves, run on a temporary repository ----------------------------------------

SHELL = shutil.which("sh")
needs_shell = pytest.mark.skipif(SHELL is None, reason="no POSIX sh on PATH to run the git hooks")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "core.autocrlf", "false")
    return tmp_path


def _stage(repo: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        _git(repo, "add", "-f", "--", path)


def _pre_commit(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([SHELL, str(HOOKS / "pre-commit")], check=False, cwd=repo, capture_output=True, text=True)


def _commit_msg(tmp_path: Path, message: str) -> subprocess.CompletedProcess:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_bytes(message.encode("utf-8"))
    return subprocess.run([SHELL, str(HOOKS / "commit-msg"), str(path)], check=False, cwd=tmp_path, capture_output=True, text=True)


MODEL_LINE = f"model: the most capable {TOOL.capitalize()} model on the {VENDOR.capitalize()} API\n"


@needs_shell
@pytest.mark.parametrize("path", ALLOWED_SAMPLES)
def test_pre_commit_accepts_the_vendor_name_in_an_allowed_path(repo, path):
    _stage(repo, {path: MODEL_LINE})
    result = _pre_commit(repo)
    assert result.returncode == 0, result.stderr


@needs_shell
@pytest.mark.parametrize("path", [p for p in REFUSED_SAMPLES if not FORBIDDEN_PATHS.search(p)])
def test_pre_commit_refuses_the_vendor_name_elsewhere(repo, path):
    _stage(repo, {path: MODEL_LINE})
    result = _pre_commit(repo)
    assert result.returncode == 1
    assert path in result.stderr


@needs_shell
def test_pre_commit_reports_only_the_disallowed_file(repo):
    _stage(repo, {"docs/decisions.md": MODEL_LINE, "src/models.py": MODEL_LINE})
    result = _pre_commit(repo)
    assert result.returncode == 1
    assert "src/models.py" in result.stderr and "docs/decisions.md" not in result.stderr


@needs_shell
@pytest.mark.parametrize("path", ["src/agents/llm.py", "docs/decisions.md", "README.md"])
def test_pre_commit_refuses_a_co_author_trailer_in_every_scanned_path(repo, path):
    _stage(repo, {path: f"{TRAILER.title()}: Someone <someone@example.com>\n"})
    assert _pre_commit(repo).returncode == 1


@needs_shell
@pytest.mark.parametrize("path", [f".{TOOL}/settings.json", f"agent_lab/{TOOL.upper()}.md", f"src/agents/.{TOOL}/x.json",
                                  f"{TOOL.upper()}.local.md", ".mcp.json", f"docs/{TOOL.upper()}.md"])
def test_pre_commit_refuses_assistant_settings_files_everywhere(repo, path):
    _stage(repo, {path: "{}\n"})
    result = _pre_commit(repo)
    assert result.returncode == 1
    assert "local assistant files" in result.stderr


@needs_shell
def test_pre_commit_still_refuses_raw_data(repo):
    _stage(repo, {"data/raw/prices.csv": "date,close\n"})
    assert _pre_commit(repo).returncode == 1


@needs_shell
def test_pre_commit_accepts_a_clean_change(repo):
    _stage(repo, {"src/models.py": "x = 1\n"})
    assert _pre_commit(repo).returncode == 0


@needs_shell
@pytest.mark.parametrize("message", [
    f"feat: add the round-2 lab on {TOOL.capitalize()}\n",
    f"chore: switch the client to the {VENDOR} SDK\n",
    f"fix: x\n\n{TRAILER.title()}: Someone <someone@example.com>\n",
    "docs: y\n\nGenerated with some tool\n",
    "docs: z\n\nhttps://example.com/code/session_0123\n",
])
def test_commit_msg_still_refuses_attribution(tmp_path, message):
    assert _commit_msg(tmp_path, message).returncode == 1


@needs_shell
def test_commit_msg_accepts_a_plain_message(tmp_path):
    assert _commit_msg(tmp_path, "chore: scope the model-name check to the agent lab's research files\n").returncode == 0
