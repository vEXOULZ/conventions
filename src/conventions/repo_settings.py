"""`conventions repo-settings --check | --apply`: the GitHub settings every repo shares.

- Merge commits only (no squash, no rebase), and the head branch deleted on merge.
- `main` protected, and `dev` too in a `flow = "dev"` repo: changes only through a pull request, the
  required checks green on an up-to-date branch, admins included, conversations resolved, no force
  pushes or deletion.
- In a `flow = "dev"` repo, `dev` is the default branch, so pull requests target it by default.

This is the only way these settings change; the GitHub UI is for looking. It talks to GitHub through
the `gh` CLI, so it acts as whoever `gh auth status` says.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from conventions.config import Config

REPO_FIELDS = {
    "allow_merge_commit": True,
    "allow_squash_merge": False,
    "allow_rebase_merge": False,
    "delete_branch_on_merge": True,
}


class GhError(Exception):
    pass


def gh(*args: str, payload: dict[str, Any] | None = None) -> Any:
    cmd = ["gh", "api", *args]
    if payload is not None:
        cmd += ["--input", "-"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GhError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def current_repo() -> str:
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GhError(proc.stderr.strip())
    return proc.stdout.strip()


def protection_payload(cfg: Config) -> dict[str, Any]:
    return {
        "required_status_checks": {"strict": True, "contexts": cfg.required_checks},
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
        },
        "restrictions": None,
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
    }


def default_branch(cfg: Config) -> str:
    return "dev" if cfg.flow == "dev" else "main"


def diff_repo(actual: dict[str, Any], cfg: Config) -> list[str]:
    problems = [
        f"{key} is {actual.get(key)!r}, should be {want!r}"
        for key, want in REPO_FIELDS.items()
        if actual.get(key) != want
    ]
    if actual.get("default_branch") != default_branch(cfg):
        problems.append(f"default branch is {actual.get('default_branch')!r}, should be {default_branch(cfg)!r}")
    return problems


def diff_protection(branch: str, actual: dict[str, Any] | None, cfg: Config) -> list[str]:
    if actual is None:
        return [f"{branch} is not protected"]
    problems = []
    checks = actual.get("required_status_checks") or {}
    if not checks.get("strict"):
        problems.append(f"{branch}: branches need not be up to date before merging")
    have = sorted(checks.get("contexts") or [])
    want = sorted(cfg.required_checks)
    if have != want:
        problems.append(f"{branch}: required checks are {have}, should be {want}")
    if not (actual.get("enforce_admins") or {}).get("enabled"):
        problems.append(f"{branch}: admins are not included")
    if actual.get("required_pull_request_reviews") is None:
        problems.append(f"{branch}: changes need not go through a pull request")
    if (actual.get("allow_force_pushes") or {}).get("enabled"):
        problems.append(f"{branch}: force pushes are allowed")
    if (actual.get("allow_deletions") or {}).get("enabled"):
        problems.append(f"{branch}: the branch can be deleted")
    if not (actual.get("required_conversation_resolution") or {}).get("enabled"):
        problems.append(f"{branch}: conversations need not be resolved")
    return problems


def get_protection(repo: str, branch: str) -> dict[str, Any] | None:
    try:
        result: dict[str, Any] = gh(f"repos/{repo}/branches/{branch}/protection")
        return result
    except GhError as e:
        if "Branch not protected" in str(e) or "Not Found" in str(e):
            return None
        raise


def check(repo: str, cfg: Config) -> list[str]:
    problems = diff_repo(gh(f"repos/{repo}"), cfg)
    for branch in cfg.protected_branches:
        problems += diff_protection(branch, get_protection(repo, branch), cfg)
    return problems


def apply(repo: str, cfg: Config) -> list[str]:
    done = []
    gh("-X", "PATCH", f"repos/{repo}", payload={**REPO_FIELDS, "default_branch": default_branch(cfg)})
    done.append(f"{repo}: merge commits only, branches deleted on merge, default branch {default_branch(cfg)}")
    for branch in cfg.protected_branches:
        gh("-X", "PUT", f"repos/{repo}/branches/{branch}/protection", payload=protection_payload(cfg))
        done.append(f"{repo}: {branch} protected; required checks {', '.join(cfg.required_checks)}")
    return done
