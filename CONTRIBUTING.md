# Contributing to Peregrine

Thanks for your interest. Peregrine is developed primarily at
[git.opensourcesolarpunk.com](https://git.opensourcesolarpunk.com/pyr0ball/peregrine).
GitHub and Codeberg are push mirrors — issues and PRs are welcome on either platform.

---

## License

Peregrine is licensed under **[BSL 1.1](./LICENSE-BSL)** — Business Source License.

What this means for you:

| Use case | Allowed? |
|----------|----------|
| Personal self-hosting, non-commercial | ✅ Free |
| Contributing code, fixing bugs, writing docs | ✅ Free |
| Commercial SaaS / hosted service | 🔒 Requires a paid license |
| After 4 years from each release date | ✅ Converts to MIT |

**By submitting a pull request you agree that your contribution is licensed under the
project's BSL 1.1 terms.** The PR template includes this as a checkbox.

---

## Dev Setup

See [`docs/getting-started/installation.md`](docs/getting-started/installation.md) for
full instructions.

**Quick start (Docker — recommended):**

```bash
git clone https://git.opensourcesolarpunk.com/pyr0ball/peregrine.git
cd peregrine
./setup.sh        # installs deps, activates git hooks
./manage.sh start
```

**Conda (no Docker):**

```bash
conda run -n job-seeker pip install -r requirements.txt
streamlit run app/app.py
```

---

## Commit Format

Hooks enforce [Conventional Commits](https://www.conventionalcommits.org/):

```
type: short description
type(scope): short description
```

Valid types: `feat` `fix` `docs` `chore` `test` `refactor` `perf` `ci` `build`

The hook will tell you exactly what went wrong if your message is rejected.

---

## Pull Request Process

1. Fork and branch from `main`
2. Write tests first (we use `pytest`)
3. Run `pytest tests/ -v` — all tests must pass
4. Open a PR on GitHub or Codeberg
5. PRs are reviewed and cherry-picked to Forgejo (the canonical repo) — you don't need a Forgejo account

---

## Reporting Issues

Use the issue templates:

- **Bug** — steps to reproduce, version, OS, Docker or conda, logs
- **Feature** — problem statement, proposed solution, which tier it belongs to

**Security issues:** Do **not** open a public issue. Email `security@circuitforge.tech`.
See [SECURITY.md](./SECURITY.md).
