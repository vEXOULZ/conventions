## Checks

Every pull request runs:

- **`conventions / branch-name`:** the branch name, and in a `flow = "dev"` repo whether it may merge
  into its base.
- **`conventions / check`:** the synced files match the version pinned in `.conventions.toml`, and the
  repo follows the conventions for its profile. A public repo is also checked for private
  infrastructure (addresses, server paths).
- **`ci / …`:** the repo's lint, tests and build, from the reusable workflows in
  [vEXOULZ/conventions](https://github.com/vEXOULZ/conventions).

They are required checks on `main`. The repo's settings, protection included, are set by
`conventions repo-settings --apply`.

## Shared conventions

This section, `.conventions/`, `.gitattributes` and the other synced files come from
[vEXOULZ/conventions](https://github.com/vEXOULZ/conventions), at the version pinned in
`.conventions.toml`. Don't edit them here: change them there, release, and bump the pin (Renovate opens
that pull request). After a bump, rewrite the copies and commit them:

```bash
uvx --from "git+https://github.com/vEXOULZ/conventions@$(sed -n 's/^version *= *"\(.*\)"/\1/p' .conventions.toml)" conventions sync
```
