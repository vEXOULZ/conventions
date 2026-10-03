from __future__ import annotations

from pathlib import Path

import pytest

from conventions import check, config, synced
from conventions.cli import main

from .conftest import git


def problems(root: Path, public: bool = False) -> list[str]:
    return check.run(root, config.load(root), public=public)


def test_synced_repo_passes(repo: Path) -> None:
    assert problems(repo, public=True) == []
    assert main(["-C", str(repo), "check", "--public"]) == 0


def test_sync_is_idempotent(repo: Path) -> None:
    assert synced.sync(repo, config.load(repo)) == []


def test_edited_synced_file_fails(repo: Path) -> None:
    path = repo / ".conventions/CLAUDE.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nAn extra rule.\n", encoding="utf-8")
    assert problems(repo) == [
        ".conventions/CLAUDE.md differs from conventions v1.0.0; "
        "run `conventions sync` at the pinned version and commit the result"
    ]
    assert main(["-C", str(repo), "check"]) == 1


def test_sync_repairs_an_edited_file(repo: Path) -> None:
    (repo / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
    assert synced.sync(repo, config.load(repo)) == ["updated .gitattributes"]
    assert problems(repo) == []


def test_crlf_checkout_still_matches(repo: Path) -> None:
    path = repo / ".conventions/CLAUDE.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert problems(repo) == []


def test_missing_and_stray_files_fail(repo: Path) -> None:
    (repo / ".conventions/ruff.toml").unlink()
    (repo / ".conventions/notes.md").write_text("mine\n", encoding="utf-8")
    found = problems(repo)
    assert any(p.startswith(".conventions/ruff.toml is missing") for p in found)
    assert any(p.startswith(".conventions/notes.md is not a synced file") for p in found)


def test_version_mismatch_fails(repo: Path) -> None:
    toml = repo / config.CONFIG_NAME
    toml.write_text(toml.read_text(encoding="utf-8").replace('"v1.0.0"', '"v0.9.0"'), encoding="utf-8")
    found = problems(repo)
    assert any("pins v0.9.0 but this is conventions v1.0.0" in p for p in found)
    assert any("uses conventions-check.yml@v1.0.0, but .conventions.toml pins v0.9.0" in p for p in found)


# --- managed blocks ----------------------------------------------------------------------------------


def test_block_keeps_repo_content_around_it(repo: Path) -> None:
    path = repo / "CONTRIBUTING.md"
    path.write_text(path.read_text(encoding="utf-8") + "\n## Local setup\n\nRun it.\n", encoding="utf-8")
    assert problems(repo) == []
    assert synced.sync(repo, config.load(repo)) == []
    assert path.read_text(encoding="utf-8").endswith("## Local setup\n\nRun it.\n")


def test_edited_block_fails(repo: Path) -> None:
    path = repo / ".gitignore"
    path.write_text(path.read_text(encoding="utf-8").replace("# conventions:end", "*.log\n# conventions:end"))
    assert problems(repo) == [
        ".gitignore: the conventions block differs from v1.0.0; "
        "run `conventions sync` at the pinned version and commit the result"
    ]


def test_block_inserted_below_existing_title(tmp_path: Path) -> None:
    block = synced.BLOCKS[0]
    managed = "<!-- conventions:begin -->\nX\n<!-- conventions:end -->\n"
    out = synced.put_block("# My project\n\nIntro.\n", block, managed)
    assert out == f"# My project\n\n{managed}\nIntro.\n"


def test_dev_flow_block_differs(repo: Path) -> None:
    trunk = config.load(repo)
    dev = config.Config(version=trunk.version, profile=trunk.profile, flow="dev")
    block = synced.BLOCKS[0]
    assert synced.block_text(trunk, block) != synced.block_text(dev, block)
    assert dev.protected_branches == ["main", "dev"]


# --- CLAUDE.md ---------------------------------------------------------------------------------------


def test_claude_md_import_is_first(repo: Path) -> None:
    path = repo / "CLAUDE.md"
    assert path.read_text(encoding="utf-8").startswith("@.conventions/CLAUDE.md\n")
    path.write_text("# Notes\n\n@.conventions/CLAUDE.md\n", encoding="utf-8")
    assert problems(repo) == ["CLAUDE.md must start with `@.conventions/CLAUDE.md`"]


def test_existing_claude_md_is_prepended(tmp_path: Path) -> None:
    assert synced.claude_md("# Mine\n", "x") == "@.conventions/CLAUDE.md\n\n# Mine\n"


# --- hooks -------------------------------------------------------------------------------------------


def test_hooks_are_executable_in_git(repo: Path) -> None:
    hook = ".conventions/githooks/pre-commit"
    assert git(repo, "ls-files", "-s", hook).split()[0] == "100755"
    git(repo, "update-index", "--chmod=-x", hook)
    assert problems(repo) == [f"{hook} is not executable in git; `git add --chmod=+x {hook}`"]


def test_hooks_path_is_set(repo: Path) -> None:
    assert git(repo, "config", "core.hooksPath").strip() == ".conventions/githooks"


# --- workflows and layout ----------------------------------------------------------------------------


def test_missing_ci_job_fails(repo: Path) -> None:
    ci = repo / ".github/workflows/ci.yml"
    ci.write_text(ci.read_text(encoding="utf-8").replace("  ci:\n", "  tests:\n"), encoding="utf-8")
    found = problems(repo)
    assert any("needs a job `ci` that uses vEXOULZ/conventions/.github/workflows/python-ci.yml" in p for p in found)


def test_stray_workflow_fails_unless_listed(repo: Path) -> None:
    (repo / ".github/workflows/tests.yml").write_text("name: tests\n", encoding="utf-8")
    assert any(p.startswith(".github/workflows/tests.yml") for p in problems(repo))
    toml = repo / config.CONFIG_NAME
    toml.write_text(toml.read_text(encoding="utf-8") + 'extra_workflows = ["tests.yml"]\n', encoding="utf-8")
    assert problems(repo) == []


@pytest.mark.parametrize(
    "rel",
    ["docker-compose.yml", "compose.override.yaml", "deploy/compose.yaml", "docker/Dockerfile", ".githooks/pre-push"],
)
def test_layout(repo: Path, rel: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    assert [p for p in problems(repo) if p.startswith(rel)]


def test_python_settings(repo: Path) -> None:
    py = repo / "pyproject.toml"
    py.write_text(
        py.read_text(encoding="utf-8").replace(">=3.13", ">=3.12").replace("strict = true", "strict = false")
        + "line-length = 100\n",
        encoding="utf-8",
    )
    found = problems(repo)
    assert any("requires-python" in p for p in found)
    assert any("strict = true" in p for p in found)


def test_required_checks() -> None:
    cfg = config.Config(version="v1.0.0", profile="python-service", extra_checks=["web-editor"])
    assert cfg.required_checks == [
        "conventions / branch-name",
        "conventions / check",
        "ci / lint",
        "ci / test",
        "image / build",
        "web-editor",
    ]


# --- private infrastructure --------------------------------------------------------------------------

# Built by concatenation, so this file doesn't trip the check it tests.
PRIVATE_IP = "192." + "168.1.20"
HOME = "/home/" + "vex/stacks"


@pytest.mark.parametrize("line", [f"host = {PRIVATE_IP}", f"cd {HOME}", "root /s" + "rv/www/site;"])
def test_private_infra_found_in_public_repo(repo: Path, line: str) -> None:
    (repo / "notes.md").write_text(f"one\n{line}\n", encoding="utf-8")
    found = problems(repo, public=True)
    assert len(found) == 1 and found[0].startswith("notes.md:2: ")
    assert problems(repo, public=False) == []


@pytest.mark.parametrize("line", ["version 10.2.3.4.5", "see https://example.com/srv/", "1.192.168.1.1"])
def test_private_infra_ignores_lookalikes(repo: Path, line: str) -> None:
    (repo / "notes.md").write_text(f"{line}\n", encoding="utf-8")
    assert problems(repo, public=True) == []


def test_private_infra_allow_marker(repo: Path) -> None:
    (repo / "notes.md").write_text(f"{PRIVATE_IP}  # conventions:allow-infra\n", encoding="utf-8")
    assert problems(repo, public=True) == []


def test_private_patterns_from_env(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (repo / "notes.md").write_text("ssh into secret-box-01 now\n", encoding="utf-8")
    monkeypatch.setenv(check.PRIVATE_PATTERNS_ENV, r"secret-box-\d+")
    found = problems(repo, public=True)
    assert found == [f"notes.md:1: matches a private pattern ({check.PRIVATE_PATTERNS_ENV}) in a public repo"]
    assert "secret-box" not in found[0]
