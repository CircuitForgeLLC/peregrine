# Public Mirror Strategy — Design

**Date:** 2026-03-02
**Scope:** Peregrine (initial); pattern applies to all future CircuitForge products
**Status:** Approved — ready for implementation planning

---

## Summary

Publish Peregrine to GitHub and Codeberg as push-mirrored community hubs. Full BSL 1.1
codebase, no MIT carve-outs. Git hooks enforcing safety + commit format committed to the
repo so every clone gets them automatically. Issue templates and a CONTRIBUTING.md make
the project approachable for external contributors. FossHub added when a Windows installer
exists.

---

## License

**Whole repo: BSL 1.1.** No MIT exception — including `scrapers/`. The original rationale
for making scrapers MIT (community maintenance) is equally served by BSL 1.1: contributors
can fix broken scrapers, submit PRs, and run the tool at home for free. Making scrapers MIT
would allow competitors to lift CF-authored scraper code into a competing commercial product
without a license, which is not in CircuitForge's interest.

The `LICENSE` file at repo root covers the full codebase. No `LICENSE-MIT` file needed.
CONTRIBUTING.md explains what BSL means practically for contributors.

BSL converts to MIT after 4 years per the standard BSL 1.1 terms.

---

## Mirror Sync

Forgejo has built-in **push mirror** support (Settings → Mirror → Push mirrors). Every push
to the primary Forgejo repo auto-replicates within seconds — no CI/CD overhead, no cron job.

Two mirrors:
- `github.com/CircuitForge/peregrine`
- `codeberg.org/CircuitForge/peregrine`

Both under the `CircuitForge` org (consistent branding; not the personal `pyr0ball` account).
GitHub and Codeberg orgs to be created if not already present.

---

## README Canonical-Source Banner

A prominent notice near the top of the README:

```
> **Primary development** happens at [git.opensourcesolarpunk.com](https://git.opensourcesolarpunk.com/pyr0ball/peregrine).
> GitHub and Codeberg are push mirrors. Issues and PRs are welcome on either platform.
```

---

## CONTRIBUTING.md

Sections:

1. **License** — BSL 1.1 overview. What it means: self-hosting for personal non-commercial
   use is free; commercial SaaS use requires a paid license; converts to MIT after 4 years.
   Link to full `LICENSE`.

2. **CLA** — One-sentence acknowledgment in bold:
   *"By submitting a pull request you agree that your contribution is licensed under the
   project's BSL 1.1 terms."* No separate CLA file or signature process — the PR template
   repeats this as a checkbox.

3. **Dev setup** — Docker path (recommended) and conda path, pointing to
   `docs/getting-started/installation.md`.

4. **PR process** — GH and Codeberg PRs are reviewed and cherry-picked to Forgejo; Forgejo
   is the canonical merge target. Contributors do not need a Forgejo account.

5. **Commit format** — `type: description` (or `type(scope): description`). Valid types:
   `feat fix docs chore test refactor perf ci build`. Hooks enforce this — if your commit is
   rejected, the hook message tells you exactly why.

6. **Issue guidance** — link to templates; note that security issues go to
   `security@circuitforge.tech`, not GitHub Issues.

---

## Git Hooks (`.githooks/`)

Committed to the repo. Activated by `setup.sh` via:

```sh
git config core.hooksPath .githooks
```

`setup.sh` already runs on first clone; hook activation is added there so no contributor
has to think about it.

### `pre-commit`

Blocks the commit if any staged file matches:

**Exact path blocklist:**
- `config/user.yaml`
- `config/server.yaml`
- `config/llm.yaml`
- `config/notion.yaml`
- `config/adzuna.yaml`
- `config/label_tool.yaml`
- `.env`
- `demo/data/*.db`
- `data/*.db`
- `data/*.jsonl`

**Content scan** (regex on staged diff):
- `sk-[A-Za-z0-9]{20,}` — OpenAI-style keys
- `Bearer [A-Za-z0-9\-_]{20,}` — generic bearer tokens
- `api_key:\s*["\']?[A-Za-z0-9\-_]{16,}` — YAML key fields with values

On match: prints the offending file/pattern, aborts with a clear message and hint to use
`git restore --staged <file>` or add to `.gitignore`.

### `commit-msg`

Reads `$1` (the commit message temp file). Rejects if:
- Message is empty or whitespace-only
- First line does not match `^(feat|fix|docs|chore|test|refactor|perf|ci|build)(\(.+\))?: .+`

On rejection: prints the required format and lists valid types. Does not touch the message
(no auto-rewriting).

---

## Issue Templates

Location: `.github/ISSUE_TEMPLATE/` (GitHub) and `.gitea/ISSUE_TEMPLATE/` (Codeberg/Forgejo).

### Bug Report (`bug_report.md`)

Fields:
- Peregrine version (output of `./manage.sh status`)
- OS and runtime (Docker / conda-direct)
- Steps to reproduce
- Expected behaviour
- Actual behaviour (with log snippets)
- Relevant config (redact keys)

### Feature Request (`feature_request.md`)

Fields:
- Problem statement ("I want to do X but currently...")
- Proposed solution
- Alternatives considered
- Which tier this might belong to (free / paid / premium / ultra)
- Willingness to contribute a PR

### PR Template (`.github/pull_request_template.md`)

Fields:
- Summary of changes
- Related issue(s)
- Type of change (feat / fix / docs / ...)
- Testing done
- **CLA checkbox:** `[ ] I agree my contribution is licensed under the project's BSL 1.1 terms.`

### Security (`SECURITY.md`)

Single page: do not open a GitHub Issue for security vulnerabilities. Email
`security@circuitforge.tech`. Response target: 72 hours.

---

## GitHub-Specific Extras

**CI (GitHub Actions)** — `.github/workflows/ci.yml`:
- Trigger: push and PR to `main`
- Steps: checkout → set up Python 3.11 → install deps from `requirements.txt` →
  `pytest tests/ -v`
- Free for public repos; gives contributors a green checkmark without needing local conda

**Repo topics:** `job-search`, `ai-assistant`, `privacy`, `streamlit`, `python`,
`open-core`, `neurodivergent`, `accessibility`, `bsl`

**Releases:** Mirror Forgejo tags. Release notes auto-generated from conventional commit
subjects grouped by type.

---

## FossHub (Future — Windows RC prerequisite)

When a signed Windows installer (`.msi` or `.exe`) is ready:

1. Submit via FossHub publisher portal (`https://www.fosshub.com/contribute.html`)
2. Requirements: stable versioned release, no bundled software, no adware
3. FossHub gives a trusted, antivirus-clean download URL — important for an app running on
   users' personal machines
4. Link FossHub download from README and from `circuitforge.tech` downloads section

No action needed until Windows RC exists.

---

## File Map

```
peregrine/
├── .githooks/
│   ├── pre-commit          # sensitive file + key pattern blocker
│   └── commit-msg          # conventional commit format enforcer
├── .github/
│   ├── workflows/
│   │   └── ci.yml          # pytest on push/PR
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── pull_request_template.md
├── .gitea/
│   └── ISSUE_TEMPLATE/     # mirrors .github/ISSUE_TEMPLATE/ for Forgejo/Codeberg
├── CONTRIBUTING.md
└── SECURITY.md
```

---

## Out of Scope

- Forgejo mirror configuration (done via Forgejo web UI, not committed to repo)
- GitHub/Codeberg org creation (manual one-time step)
- Windows installer build pipeline (separate future effort)
- `circuitforge-core` extraction (deferred until second product)
