from __future__ import annotations

import json
from pathlib import Path

import pytest

from conventions import check, config, synced, version
from conventions.cli import main

from .conftest import PIN, git

PYPROJECT = """\
[project]
name = "sample-bot"
version = "0.9.1"
requires-python = ">=3.13"

[tool.uv]
required-version = ">=0.5"
version = "not this one"
"""

UV_LOCK = """\
version = 1

[[package]]
name = "helper"
version = "0.1.0"
source = { editable = "packages/helper" }

[[package]]
name = "sample-bot"
version = "0.9.1"
source = { editable = "." }
dependencies = [
    { name = "helper" },
]
"""

INIT = '"""The bot."""\n\n__version__ = "0.9.1"\n'


@pytest.fixture
def py(tmp_path: Path) -> Path:
    """A Python repo whose version is written in three places, on main with tag v0.9.1."""
    root = tmp_path / "py"
    (root / "src/sample_bot").mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
    (root / "src/sample_bot/__init__.py").write_text(INIT, encoding="utf-8")
    (root / config.CONFIG_NAME).write_text(config.render(PIN, "python-service", "dev"), encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: release 0.9.1")
    git(root, "tag", "v0.9.1")
    return root


def commit(root: Path, message: str) -> None:
    git(root, "commit", "-q", "--allow-empty", "-m", message)


def test_reads_every_place_the_version_is_written(py: Path) -> None:
    assert [(s.path, s.value) for s in version.sources(py)] == [
        ("pyproject.toml", "0.9.1"),
        ("uv.lock", "0.9.1"),
        ("src/sample_bot/__init__.py", "0.9.1"),
    ]
    assert version.current(py) == "0.9.1"


def test_a_module_named_unlike_the_project_is_found_when_it_is_the_only_one(py: Path) -> None:
    (py / "src/sample_bot").rename(py / "src/bot")
    assert [s.path for s in version.sources(py)][-1] == "src/bot/__init__.py"
    (py / "src/other").mkdir()
    (py / "src/other/__init__.py").write_text(INIT, encoding="utf-8")
    assert [s.path for s in version.sources(py)] == ["pyproject.toml", "uv.lock"]  # two: neither is chosen


def test_files_that_disagree_fail(py: Path) -> None:
    init = py / "src/sample_bot/__init__.py"
    init.write_text(INIT.replace("0.9.1", "0.9.0"), encoding="utf-8")
    with pytest.raises(version.VersionError, match="disagree"):
        version.current(py)
    problems, _ = version.check(py, config.load(py))
    assert problems and "src/sample_bot/__init__.py (__version__) 0.9.0" in problems[0]
    assert main(["-C", str(py), "version", "check"]) == 1


def test_set_writes_every_file_and_nothing_else(py: Path) -> None:
    assert version.set_version(py, "0.10.0") == ["pyproject.toml", "uv.lock", "src/sample_bot/__init__.py"]
    assert version.current(py) == "0.10.0"
    lock = (py / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "helper"\nversion = "0.1.0"' in lock  # a workspace member keeps its own
    assert 'version = "not this one"' in (py / "pyproject.toml").read_text(encoding="utf-8")


def test_set_keeps_crlf_line_endings(py: Path) -> None:
    path = py / "pyproject.toml"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    version.set_version(py, "1.0.0")
    assert b'version = "1.0.0"\r\n' in path.read_bytes()
    assert b"\n" not in path.read_bytes().replace(b"\r\n", b"")


def test_node_versions(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{\n  "name": "site",\n  "version": "1.2.3"\n}\n', encoding="utf-8")
    lock = {"name": "site", "version": "1.2.3", "lockfileVersion": 3, "packages": {"": {"version": "1.2.3"}}}
    (tmp_path / "package-lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    assert version.current(tmp_path) == "1.2.3"
    version.set_version(tmp_path, "1.3.0")
    written = json.loads((tmp_path / "package-lock.json").read_text(encoding="utf-8"))
    assert (written["version"], written["packages"][""]["version"]) == ("1.3.0", "1.3.0")
    assert (tmp_path / "package.json").read_text(encoding="utf-8").endswith('"version": "1.3.0"\n}\n')


def test_a_repo_without_a_version_passes(tmp_path: Path) -> None:
    (tmp_path / config.CONFIG_NAME).write_text(config.render(PIN, "docs", "trunk"), encoding="utf-8")
    assert version.current(tmp_path) is None
    assert version.check(tmp_path, config.load(tmp_path), against="origin/main")[0] == []


@pytest.mark.parametrize(
    ("messages", "kind"),
    [
        (["fix: a bug", "chore: tidy"], "patch"),
        (["fix: a bug", "feat(api): /readyz"], "minor"),
        (["feat!: drop the old endpoint"], "major"),
        (["refactor: x\n\nBREAKING CHANGE: the config moved"], "major"),
        (["Update README"], "patch"),
    ],
)
def test_kind_of(messages: list[str], kind: str) -> None:
    assert version.kind_of(messages) == kind


def test_bump() -> None:
    assert version.bump((0, 9, 1), "patch") == (0, 9, 2)
    assert version.bump((0, 9, 1), "minor") == (0, 10, 0)
    assert version.bump((0, 9, 1), "major") == (0, 10, 0)  # before 1.0 a breaking change is a minor
    assert version.bump((1, 4, 2), "major") == (2, 0, 0)


def test_next_reads_the_commits_since_the_last_tag(py: Path) -> None:
    commit(py, "fix(coverage): a gap")
    commit(py, "feat: /readyz")
    nxt = version.next_version(py)
    assert (nxt.version, nxt.kind, nxt.since, nxt.commits) == ("0.10.0", "minor", "v0.9.1", 2)
    assert version.next_version(py, "patch").version == "0.9.2"


def test_next_keeps_a_version_already_raised_by_hand(py: Path) -> None:
    version.set_version(py, "0.12.0")
    git(py, "commit", "-q", "-am", "chore: release 0.12.0")
    assert version.next_version(py).version == "0.12.0"


def test_next_refuses_when_nothing_happened(py: Path) -> None:
    with pytest.raises(version.VersionError, match="nothing to release"):
        version.next_version(py)


def test_a_release_must_raise_the_version(py: Path) -> None:
    git(py, "switch", "-q", "-c", "dev")
    commit(py, "feat: something")
    problems, _ = version.check(py, config.load(py), against="main")
    assert len(problems) == 2
    assert "must go up: main has 0.9.1, this branch 0.9.1" in problems[0]
    assert problems[1].startswith("tag v0.9.1 already exists")
    assert main(["-C", str(py), "version", "check", "--against", "main"]) == 1

    version.set_version(py, "0.10.0")
    problems, notes = version.check(py, config.load(py), against="main")
    assert problems == []
    assert "0.9.1 on main → 0.10.0" in notes
    assert main(["-C", str(py), "version", "check", "--against", "main"]) == 0


def test_a_trunk_repo_needs_no_bump(py: Path) -> None:
    (py / config.CONFIG_NAME).write_text(config.render(PIN, "python-service", "trunk"), encoding="utf-8")
    problems, notes = version.check(py, config.load(py), against="main")
    assert problems == []
    assert any("trunk" in n for n in notes)


def test_cli_show_and_set(py: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-C", str(py), "version", "set", "1.0.0"]) == 0
    assert main(["-C", str(py), "version", "show"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "1.0.0"
    assert main(["-C", str(py), "version", "set", "one"]) == 1


def test_a_dev_flow_repo_needs_release_yml(repo: Path) -> None:
    toml = repo / config.CONFIG_NAME
    toml.write_text(toml.read_text(encoding="utf-8").replace('flow = "trunk"', 'flow = "dev"'), encoding="utf-8")
    synced.sync(repo, config.load(repo))  # the CONTRIBUTING.md block follows the flow
    found = check.run(repo, config.load(repo))
    assert any("release.yml needs a job `prepare`" in p for p in found)
    assert any("release.yml needs a job `finish`" in p for p in found)

    (repo / ".github/workflows/release.yml").write_text(
        "name: release\non:\n  workflow_dispatch:\njobs:\n"
        f"  prepare:\n    uses: vEXOULZ/conventions/.github/workflows/release-prepare.yml@{PIN}\n"
        f"  finish:\n    uses: vEXOULZ/conventions/.github/workflows/release-finish.yml@{PIN}\n",
        encoding="utf-8",
    )
    assert check.run(repo, config.load(repo)) == []
