from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conventions import config

from .conftest import git

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")


def pr(root: Path, head: str, base: str) -> int:
    return subprocess.run(
        ["sh", ".conventions/githooks/check-pr-branches.sh", head, base], cwd=root, capture_output=True
    ).returncode


@pytest.mark.parametrize(
    ("head", "ok"),
    [
        ("feature/add-quotes", True),
        ("bugfix/issue-42-off-by-one", True),
        ("chore/bump-deps", True),
        ("docs/readme", False),
        ("claude/some-worktree", False),
        ("feature/Add_Quotes", False),
        ("feature/trailing-", False),
        ("main", False),
    ],
)
def test_trunk_flow_branch_names(repo: Path, head: str, ok: bool) -> None:
    assert (pr(repo, head, "main") == 0) is ok


@pytest.mark.parametrize(
    ("head", "base", "ok"),
    [
        ("feature/add-quotes", "dev", True),
        ("feature/add-quotes", "main", False),
        ("dev", "main", True),
        ("release/v1-2-0", "main", True),
        ("hotfix/crash-on-start", "main", True),
        ("main", "dev", True),
        ("docs/readme", "dev", False),
    ],
)
def test_dev_flow_targets(repo: Path, head: str, base: str, ok: bool) -> None:
    (repo / config.CONFIG_NAME).write_text(config.render("v1.0.0", "python-lib", "dev"), encoding="utf-8")
    assert (pr(repo, head, base) == 0) is ok


def commit(root: Path) -> subprocess.CompletedProcess[str]:
    (root / "file.txt").write_text("x\n", encoding="utf-8")
    git(root, "add", "file.txt")
    return subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "x"], capture_output=True, text=True)


def test_pre_commit_refuses_main(repo: Path) -> None:
    result = commit(repo)
    assert result.returncode != 0
    assert "Refusing to commit on 'main'" in result.stderr


def test_pre_commit_allows_conventional_branch(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature/first")
    assert commit(repo).returncode == 0


def test_pre_commit_runs_local_hook(repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feature/first")
    local = repo / ".githooks/local/pre-commit"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\necho local hook ran >&2\nexit 1\n", encoding="utf-8")
    local.chmod(0o755)
    result = commit(repo)
    if not shutil.which("chmod") or not (local.stat().st_mode & 0o111):
        pytest.skip("no executable bit on this filesystem")
    assert result.returncode != 0
    assert "local hook ran" in result.stderr
