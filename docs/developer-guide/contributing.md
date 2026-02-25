# Contributing

Thank you for your interest in contributing to Peregrine. This guide covers the development environment, code standards, test requirements, and pull request process.

!!! note "License"
    Peregrine uses a dual licence. The discovery pipeline (`scripts/discover.py`, `scripts/match.py`, `scripts/db.py`, `scripts/custom_boards/`) is MIT. All AI features, the UI, and everything else is BSL 1.1.
    Do not add `Co-Authored-By:` trailers or AI-attribution notices to commits — this is a commercial repository.

---

## Fork and Clone

```bash
git clone https://git.circuitforge.io/circuitforge/peregrine
cd peregrine
```

Create a feature branch from `main`:

```bash
git checkout -b feat/my-feature
```

---

## Dev Environment Setup

Peregrine's Python dependencies are managed with conda. The same `job-seeker` environment is used for both the legacy personal app and Peregrine.

```bash
# Create the environment from the lockfile
conda env create -f environment.yml

# Activate
conda activate job-seeker
```

Alternatively, install from `requirements.txt` into an existing Python 3.12 environment:

```bash
pip install -r requirements.txt
```

!!! warning "Keep the env lightweight"
    Do not add `torch`, `sentence-transformers`, `bitsandbytes`, `transformers`, or any other CUDA/GPU package to the main environment. These live in separate conda environments (`job-seeker-vision` for the vision service, `ogma` for fine-tuning). Adding them to the main env causes out-of-memory failures during test runs.

---

## Running Tests

```bash
conda run -n job-seeker python -m pytest tests/ -v
```

Or with the direct binary (avoids runaway process spawning):

```bash
/path/to/miniconda3/envs/job-seeker/bin/pytest tests/ -v
```

The `pytest.ini` file scopes collection to the `tests/` directory only — do not widen this.

All tests must pass before submitting a PR. See [Testing](testing.md) for patterns and conventions.

---

## Code Style

- **PEP 8** for all Python code — use `flake8` or `ruff` to check
- **Type hints preferred** on function signatures — not required but strongly encouraged
- **Docstrings** on all public functions and classes
- **No print statements** in library code (`scripts/`); use Python's `logging` module or return status in the return value. `print` is acceptable in one-off scripts and `discover.py`-style entry points.

---

## Branch Naming

| Prefix | Use for |
|--------|---------|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `refactor/` | Code reorganisation without behaviour change |
| `test/` | Test additions or corrections |
| `chore/` | Dependency updates, CI, tooling |

Example: `feat/add-greenhouse-scraper`, `fix/email-imap-timeout`, `docs/add-integration-guide`

---

## PR Checklist

Before opening a pull request:

- [ ] All tests pass: `conda run -n job-seeker python -m pytest tests/ -v`
- [ ] New behaviour is covered by at least one test
- [ ] No new dependencies added to `environment.yml` or `requirements.txt` without a clear justification in the PR description
- [ ] Documentation updated if the PR changes user-visible behaviour (update the relevant page in `docs/`)
- [ ] Config file changes are reflected in the `.example` file
- [ ] No secrets, tokens, or personal data in any committed file
- [ ] Gitignored files (`config/*.yaml`, `staging.db`, `aihawk/`, `.env`) are not committed

---

## What NOT to Do

- Do not commit `config/user.yaml`, `config/notion.yaml`, `config/email.yaml`, `config/adzuna.yaml`, or any `config/integrations/*.yaml` — all are gitignored
- Do not commit `staging.db`
- Do not add `torch`, `bitsandbytes`, `transformers`, or `sentence-transformers` to the main environment
- Do not add `Co-Authored-By:` or AI-attribution lines to commit messages
- Do not force-push to `main`

---

## Getting Help

Open an issue on the repository with the `question` label. Include:
- Your OS and Docker version
- The `inference_profile` from your `config/user.yaml`
- Relevant log output from `make logs`
