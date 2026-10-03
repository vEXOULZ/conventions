# conventions

The shared conventions for the vEXOULZ repos, and the tooling that keeps every repo on them. Each job
has one name and one way of being done. A conventions change reaches every repo as a pull request, and
CI fails when a repo drifts.

A rule written only in a document still drifts. So everything here is also code that is copied into the
repos and checked:

| What | How it reaches a repo | What catches drift |
|---|---|---|
| Shared Claude rules, hooks, `.gitattributes`, ruff config, `.nvmrc` | copied whole by `conventions sync` | `conventions / check` |
| `CONTRIBUTING.md`, PR template and `.gitignore` sections | a managed block inside the repo's own file | `conventions / check` |
| CI: lint, types, tests, image and site publishing | reusable workflows, pinned to a tag | `conventions / check` (the pin) |
| Merge methods, branch protection, required checks | `conventions repo-settings --apply` | `conventions repo-settings --check` |
| New versions | the Renovate preset opens a PR | — |

## Adopting it

From the repo's root, on a Conventional Branch (`chore/adopt-conventions`):

```sh
uvx --from git+https://github.com/vEXOULZ/conventions@v1.0.0 conventions init --profile python-service
```

This writes `.conventions.toml` and then syncs. Then:

1. Write `.github/workflows/ci.yml` with the jobs your profile needs (see [Profiles](#profiles)). The
   reusable workflows' headers show how to call each one.
2. Fix what `conventions check` reports, and commit.
3. After the pull request merges, run `conventions repo-settings --apply`. The required checks are named
   after the jobs, so protection has to follow the new names.
4. In `renovate.json`, extend the shared preset: `{"extends": ["github>vEXOULZ/conventions//renovate/default"]}`.

## `.conventions.toml`

```toml
version = "v1.0.0"          # the release this repo follows; every workflow `uses: …@` must match it
profile = "python-service"  # see Profiles
flow = "trunk"              # "trunk": work merges into main. "dev": work integrates on dev, main is production
extra_checks = []           # required checks beyond the profile's, e.g. a repo-specific CI job
extra_workflows = []        # workflow files beyond ci.yml and publish.yml
```

## Profiles

Every repo's `ci.yml` calls `conventions-check.yml` as job `conventions`. The other jobs depend on the
profile. Job ids are fixed because GitHub names a reusable workflow's checks `<job id> / <job name>`,
which keeps the required check names the same in every repo.

| Profile | Jobs in `ci.yml` (and `publish.yml`) | Required checks |
|---|---|---|
| `python-service` | `conventions`, `ci` → `python-ci.yml`, `image` → `publish-image.yml` | `conventions / branch-name`, `conventions / check`, `ci / lint`, `ci / test`, `image / build` |
| `python-lib` | `conventions`, `ci` → `python-ci.yml` | `conventions / branch-name`, `conventions / check`, `ci / lint`, `ci / test` |
| `node-lib` | `conventions`, `ci` → `node-ci.yml` | `conventions / branch-name`, `conventions / check`, `ci / lint`, `ci / test`, `ci / build` |
| `site` | as `node-lib`, plus `publish` → `publish-site.yml` in `publish.yml` | as `node-lib` |
| `docs` | `conventions` | `conventions / branch-name`, `conventions / check` |

`conventions required-checks` prints the list for a repo.

## What `conventions check` enforces

- Every synced file and managed block matches the pinned version. Line endings don't count.
- `CLAUDE.md` starts with `@.conventions/CLAUDE.md`.
- The hooks are executable in git.
- Workflows are only `ci.yml` and `publish.yml` (plus `extra_workflows`), with the profile's jobs, each
  pinned to the same version as `.conventions.toml`.
- Compose files are only `compose.yaml` and `compose.dev.yaml`, at the root. One `Dockerfile`, at the
  root. Nothing in `.githooks/` except `.githooks/local/`.
- **Python:**
  - `.python-version` is 3.13, and `uv.lock` exists.
  - `requires-python >= 3.13`.
  - ruff extends `.conventions/ruff.toml` without overriding it.
  - mypy is `strict`. mypy can't extend a shared file, so this checks the settings instead.
- **Node:** `package-lock.json` exists, and `engines.node` names 22.
- **With `--public`** (CI adds it in public repos): no private IP addresses, home directories or server
  paths.
  - More patterns, such as machine names, come from the `CONVENTIONS_PRIVATE_PATTERNS` repository
    secret, one regular expression per line, so the patterns themselves stay private.
  - A line that legitimately needs one carries `conventions:allow-infra`.

## Releasing

1. Change things on a branch here. CI runs this repo's own check, from the checkout, against itself.
2. Bump `version` in `pyproject.toml` and `__version__`, then merge.
3. Tag the merge commit `vX.Y.Z` and push the tag.
4. Renovate opens a PR in each repo that bumps the pin and the `uses:` refs together. That PR fails
   `conventions / check` until someone runs `conventions sync` on its branch and pushes the result. The
   failure is intended: it is how the new files reach the repo.

Semver: a change that makes a passing repo fail is a major version, a new optional input or rule a
repo can opt into is a minor, and a fix is a patch.

## Developing

```sh
uv sync --all-extras
uv run pytest
uv run ruff check && uv run ruff format --check && uv run mypy
uv run conventions check --public
```
