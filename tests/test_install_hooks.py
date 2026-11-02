"""tools/install_hooks.py lists the local tool-settings files in .git/info/exclude, idempotently."""

from tools import install_hooks


def test_entries_added_to_a_new_file(tmp_path):
    path = tmp_path / "info" / "exclude"
    added = install_hooks.ensure_excluded(path)
    assert added == install_hooks.EXCLUDE_LINES
    assert path.read_bytes().decode("utf-8") == "\n".join([install_hooks.EXCLUDE_HEADER, *install_hooks.EXCLUDE_LINES]) + "\n"


def test_second_run_changes_nothing(tmp_path):
    path = tmp_path / "exclude"
    install_hooks.ensure_excluded(path)
    before = path.read_bytes()
    assert install_hooks.ensure_excluded(path) == []
    assert path.read_bytes() == before


def test_existing_content_kept_and_only_missing_lines_added(tmp_path):
    path = tmp_path / "exclude"
    first, *rest = install_hooks.EXCLUDE_LINES
    path.write_bytes(f"# git ls-files --others --exclude-from=.git/info/exclude\n*.tmp\n{first}".encode())  # no final newline
    assert install_hooks.ensure_excluded(path) == rest
    lines = path.read_bytes().decode("utf-8").splitlines()
    assert lines[:3] == ["# git ls-files --others --exclude-from=.git/info/exclude", "*.tmp", first]
    assert lines.count(first) == 1
    assert set(install_hooks.EXCLUDE_LINES) <= set(lines)
    assert b"\r" not in path.read_bytes()


def test_entries_cover_the_forbidden_paths():
    tool = "cla" + "ude"
    assert install_hooks.EXCLUDE_LINES == [f".{tool}/", f"{tool.upper()}.md", f"{tool.upper()}.local.md", ".mcp.json"]
