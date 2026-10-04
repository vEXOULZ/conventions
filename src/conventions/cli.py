"""The `conventions` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conventions import __version__, check, config, repo_settings, synced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conventions", description=__doc__)
    parser.add_argument("--version", action="version", version=f"conventions v{__version__}")
    parser.add_argument("-C", dest="root", type=Path, default=Path.cwd(), help="the repo (default: here)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="write .conventions.toml, then sync")
    p_init.add_argument("--profile", required=True, choices=config.PROFILES)
    p_init.add_argument("--flow", default="trunk", choices=config.FLOWS)
    p_init.add_argument("--force", action="store_true", help="overwrite an existing .conventions.toml")

    sub.add_parser("sync", help="rewrite the synced files and blocks")

    p_check = sub.add_parser("check", help="fail if the repo doesn't match its pinned conventions")
    p_check.add_argument("--public", action="store_true", help="also look for private infrastructure")

    p_settings = sub.add_parser("repo-settings", help="check or apply the GitHub repo settings")
    mode = p_settings.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p_settings.add_argument("--repo", help="OWNER/NAME (default: the repo gh sees here)")

    sub.add_parser("required-checks", help="print the required check names for this repo")

    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    try:
        if args.command == "init":
            path = root / config.CONFIG_NAME
            if path.exists() and not args.force:
                print(f"{config.CONFIG_NAME} already exists; use --force to replace it", file=sys.stderr)
                return 1
            path.write_bytes(config.render(f"v{__version__}", args.profile, args.flow).encode())
            print(f"wrote {config.CONFIG_NAME}")
            return _sync(root)

        if args.command == "sync":
            return _sync(root)

        cfg = config.load(root)

        if args.command == "check":
            problems = check.run(root, cfg, public=args.public)
            for problem in problems:
                print(f"::error::{problem}" if _in_ci() else f"error: {problem}")
            if problems:
                print(f"\n{len(problems)} problem(s) against conventions {cfg.version}", file=sys.stderr)
                return 1
            print(f"ok: matches conventions {cfg.version} ({cfg.profile}, flow {cfg.flow})")
            return 0

        if args.command == "required-checks":
            print("\n".join(cfg.required_checks))
            return 0

        if args.command == "repo-settings":
            repo = args.repo or repo_settings.current_repo()
            if args.apply:
                done, warnings = repo_settings.apply(repo, cfg)
                for line in done:
                    print(f"ok: {line}")
                for warning in warnings:
                    print(f"warning: {repo}: {warning}")
                return 0
            problems, warnings = repo_settings.check(repo, cfg)
            for warning in warnings:
                print(f"warning: {repo}: {warning}")
            for problem in problems:
                print(f"error: {repo}: {problem}")
            if problems:
                print("\nfix with `conventions repo-settings --apply`", file=sys.stderr)
                return 1
            protected = [b for b in cfg.protected_branches if repo_settings.free_warning(b) not in warnings]
            print(f"ok: {repo} settings match" + (f" ({', '.join(protected)} protected)" if protected else ""))
            return 0
    except (config.ConfigError, repo_settings.GhError) as e:
        print(f"conventions: {e}", file=sys.stderr)
        return 1
    return 2


def _sync(root: Path) -> int:
    try:
        cfg = config.load(root)
    except config.ConfigError as e:
        print(f"conventions: {e}", file=sys.stderr)
        return 1
    changes = synced.sync(root, cfg)
    for line in changes:
        print(f"  {line}")
    print(f"ok: synced conventions v{__version__} ({len(changes)} change(s))")
    if cfg.version != f"v{__version__}" and not cfg.self_repo:
        print(f"note: .conventions.toml pins {cfg.version}; check will refuse to run at a different version")
    return 0


def _in_ci() -> bool:
    import os

    return os.environ.get("GITHUB_ACTIONS") == "true"
