## Set up the hooks once per clone

```bash
git config core.hooksPath .conventions/githooks
```

Git does not carry hooks in a clone, so this is the one step nothing can do for you (`conventions sync`
does it as a side effect). Without it, the branch rules below are only enforced in CI, which is a slower
way to hear about a typo. A repo's own extra checks live in `.githooks/local/pre-commit`, which the
shared hook runs after its own.

## Branches

Branch names follow [Conventional Branch](https://conventional-branch.github.io/): `<type>/<description>`,
where the description is lowercase letters, digits and single hyphens.

| Type | For |
|------|-----|
| `feature/` | a new capability, e.g. `feature/part-mapping` |
| `bugfix/` | a fix, e.g. `bugfix/issue-42-restricted-seek` |
| `hotfix/` | a fix that can't wait for the usual path, e.g. `hotfix/broken-deploy` |
| `release/` | preparing a version, e.g. `release/1-2-0` |
| `chore/` | dependencies, tooling, docs, anything with no behaviour change, e.g. `chore/bump-vite` |

A ticket number is just another word in the description.
`.conventions/githooks/check-branch-name.sh <name>` says whether a name passes, and CI runs the same
script (the `conventions / branch-name` check) against the branch a pull request comes from.

