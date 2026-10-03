### Release flow: dev → main

Work integrates on `dev`, and `main` is what production runs. The `pre-commit` hook refuses a commit
made on `main`, `master`, `dev` or `develop`.

- Feature and bugfix branches start from `dev`, and their pull requests target `dev`.
- A release is a pull request from `dev` (or a `release/*` branch) into `main`, then a `vX.Y.Z` tag on
  `main`.
- A `hotfix/*` branch starts from `main` and merges into `main`; `main` then merges back into `dev` so
  `dev` never loses it.
- The `conventions / branch-name` check refuses any other pull request into `main`.

```bash
git switch dev && git pull && git switch -c feature/what-you-are-doing
```

Concluding a merge that hit conflicts is a commit on the branch merged into, and the hook lets that one
through: the rule is about where work starts, not where it lands. `git commit --no-verify` skips the
hook entirely. It exists for the day you need it, not for the day you are in a hurry.

