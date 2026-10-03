@.conventions/CLAUDE.md

# conventions

This repo is public, and every other repo copies from it. So:

- **Nothing private here, ever:** no machine names, addresses, paths or anything else from the private
  infrastructure. Tests that need such a string build it by concatenation, so the repo's own
  `check --public` stays clean.
- **The source of a synced file is under `src/conventions/files/`.** The copies at the repo root
  (`.conventions/`, `.gitattributes`, the managed blocks) are this repo adopting itself. Edit the source,
  then run `uv run conventions sync`.
- **A change that makes a passing repo fail is a major version** (see README "Releasing"). Say which
  kind of change a PR is.
- **Required check names come from job ids** (`PROFILE_CHECKS` in `config.py`). Renaming a job in a
  reusable workflow renames a required check in every repo, so it needs `repo-settings --apply`
  everywhere.
