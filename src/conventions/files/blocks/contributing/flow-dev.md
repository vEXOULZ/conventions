### Release flow: dev → main

Work integrates on `dev`, and `main` is what production runs. The `pre-commit` hook refuses a commit
made on `main`, `master`, `dev` or `develop`.

- Feature and bugfix branches start from `dev`, and their pull requests target `dev`.
- A release is a pull request into `main`, and it has to raise the version (`conventions / version`).
  Start one from the **Actions → release → Run workflow** button: it works out the next version from
  the Conventional Commits since the last tag (`feat` is a minor, `!` or `BREAKING CHANGE` a major,
  anything else a patch; choose a bump to override), writes it on a `release/X-Y-Z` branch and opens
  "Release vX.Y.Z" into `main`.
- Merging the release pull request tags the merge commit `vX.Y.Z`, publishes the GitHub release, and
  opens the pull request that brings `main` back into `dev`. Merge that one too.
- A `hotfix/*` branch starts from `main`, raises the version (`conventions version set X.Y.Z`) and
  merges into `main`; it is released the same way, and `main` then merges back into `dev` so `dev`
  never loses it.
- The `conventions / branch-name` check refuses any other pull request into `main`.

```bash
git switch dev && git pull && git switch -c feature/what-you-are-doing
```

Concluding a merge that hit conflicts is a commit on the branch merged into, and the hook lets that one
through: the rule is about where work starts, not where it lands. `git commit --no-verify` skips the
hook entirely. It exists for the day you need it, not for the day you are in a hurry.

