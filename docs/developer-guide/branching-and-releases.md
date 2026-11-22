# Branching and Releases

How work moves from an idea to a released version of Peregrine. The short version: nothing goes straight into `main`.

```
feature branch  →  develop  →  freeze/vX.Y.Z  →  main  →  tag vX.Y.Z
```

---

## The branches

| Branch | What it is | How it changes |
|--------|-----------|----------------|
| `main` | Released code. Every release tag is cut from here. | Pull requests only, from a freeze branch or a hotfix |
| `develop` | Where finished work comes together and is tested | Pull requests only, from feature branches |
| `freeze/vX.Y.Z` | A release candidate, cut from `develop` and tested as a whole | Pull requests with fixes for that release only |
| `feat/…`, `fix/…`, `docs/…` | One change, for one ticket | The author |

A pull request (PR) is a request to merge a branch. Direct pushes to `main` and `develop` are blocked, and a PR can only merge once CI (continuous integration, the tests that run on the server) passes.

---

## Day to day

1. **Start from a ticket.** Open a Forgejo issue and list its tasks. Comment on it when you start, when the plan changes, and when the PR is open.
2. **Branch from `develop`.** Put the ticket number in the name (the commit hook can then link the ticket for you):

    ```bash
    git fetch origin
    git switch -c feat/123-short-name origin/develop
    ```

3. **Commit each logical change.** One task is one commit, in the conventional format described in [Contributing](contributing.md). Commit as often as you like. Committing is not merging.
4. **Run the tests locally** before you push (see [Testing](testing.md)). CI confirms the result, it is not where you find out.
5. **Get a review before you push.** Someone who did not write the change (a teammate, or a fresh reviewer agent) reads the diff against `develop`. Fix what it finds in one batch of commits.
6. **Push once, then open a PR into `develop`.** Say what changed, why, and how you tested it. Add the review as a comment.
7. **Merge when it is ready:** the review is recorded, CI is green on the latest commit, and there are no conflicts. **Merge one PR at a time.** Wait for CI on `develop` to finish before merging the next, because a second push cancels the first run and the first merge then shows as a failure.

Things not to do: merge a PR as soon as you open it, merge after every commit, merge two PRs back to back, force-push, or push straight to `main` or `develop`.

---

## Cutting a release

1. **Cut a freeze branch** when `develop` holds what you want to ship and its CI is green:

    ```bash
    git fetch origin
    git switch -c freeze/v1.2.0 origin/develop
    git push -u origin freeze/v1.2.0
    ```

2. **Test it as a whole.** CI runs on every PR into the freeze branch. Also build a candidate and try it on a test instance. Fix problems with PRs into the freeze branch, not into `develop`.
3. **Open a PR from the freeze branch into `main`.** Merge it with a **merge commit, never a squash**, so the history stays intact.
4. **Tag the release** (`v1.2.0`) on that merge commit on `main`. The tag starts the release workflow, which builds and publishes the images and creates the Forgejo release with notes from the commit messages.
5. **Merge `main` back into `develop`** with a PR, so fixes made on the freeze branch are not lost.
6. **Sync the public mirrors** on GitHub and Codeberg with `scripts/sync-mirrors.sh` (run it with `--dry-run` first).

---

## Hotfixes

When `main` is broken or a security fix cannot wait for the next release: branch from `main` (`fix/123-name`), test and review as usual, and open one PR into `main`. Tag a patch release (`v1.2.1`) after it merges, then merge `main` into `develop` so the fix is in both.

---

## What is enforced and what is a habit

Enforced by the server:

- No direct pushes to `main` or `develop`.
- Both need the CI checks `CI / Backend (Python)` and `CI / Frontend (Vue)` to pass before a PR merges.

CI runs once for a PR into `main`, `develop` or a freeze branch, and again when `develop` or `main` themselves change. It does not also run on every push to a work branch.

Everything else on this page, including reviewing before you push and merging one PR at a time, is a habit the whole team keeps.
