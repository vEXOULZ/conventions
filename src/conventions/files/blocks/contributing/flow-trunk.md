### Release flow: trunk

**`main` is merge-only.** The `pre-commit` hook refuses a commit made on `main`, `master`, `dev` or
`develop`. Work on a branch and merge it into `main` through a pull request:

```bash
git switch -c feature/what-you-are-doing
```

Concluding a merge that hit conflicts is a commit on `main`, and the hook lets that one through: the
rule is about where work starts, not where it lands. `git commit --no-verify` skips the hook entirely.
It exists for the day you need it, not for the day you are in a hurry.

