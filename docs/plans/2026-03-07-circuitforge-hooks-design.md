# CircuitForge Hooks — Secret & PII Scanning Design

**Date:** 2026-03-07
**Scope:** All CircuitForge repos (Peregrine first; others on public release)
**Status:** Approved, ready for implementation

## Problem

A live Forgejo API token was committed in `docs/plans/2026-03-03-feedback-button-plan.md`
and required emergency history scrubbing via `git-filter-repo`. Root causes:

1. `core.hooksPath` was never configured — the existing `.githooks/pre-commit` ran on zero commits
2. The token format (`FORGEJO_API_TOKEN=<hex>`) matched none of the hook's three regexes
3. No pre-push safety net existed

## Solution

Centralised hook repo (`circuitforge-hooks`) shared across all products.
Each repo activates it with one command. The heavy lifting is delegated to
`gitleaks` — an actively-maintained binary with 150+ built-in secret patterns,
native Forgejo/Gitea token detection, and a clean allowlist system.

## Repository Structure

```
/Library/Development/CircuitForge/circuitforge-hooks/
├── hooks/
│   ├── pre-commit       # gitleaks --staged scan (fast, every commit)
│   ├── commit-msg       # conventional commits enforcement
│   └── pre-push         # gitleaks full-branch scan (safety net)
├── gitleaks.toml        # shared base config
├── install.sh           # wires core.hooksPath in the calling repo
├── tests/
│   └── test_hooks.sh    # migrated + extended from Peregrine
└── README.md
```

Forgejo remote: `git.opensourcesolarpunk.com/pyr0ball/circuitforge-hooks`

## Hook Behaviour

### pre-commit
- Runs `gitleaks protect --staged` — scans only the staged diff
- Sub-second on typical commits
- Blocks commit and prints redacted match on failure
- Merges per-repo `.gitleaks.toml` allowlist if present

### pre-push
- Runs `gitleaks git` — scans full branch history not yet on remote
- Catches anything committed with `--no-verify` or before hooks were wired
- Same config resolution as pre-commit

### commit-msg
- Enforces conventional commits format (`type(scope): subject`)
- Migrated unchanged from `peregrine/.githooks/commit-msg`

## gitleaks Config

### Shared base (`circuitforge-hooks/gitleaks.toml`)

```toml
title = "CircuitForge secret + PII scanner"

[extend]
useDefault = true   # inherit all 150+ built-in rules

[[rules]]
id = "cf-generic-env-token"
description = "Generic KEY=<token> in env-style assignment"
regex = '''(?i)(token|secret|key|password|passwd|pwd|api_key)\s*[=:]\s*['\"]?[A-Za-z0-9\-_]{20,}['\"]?'''
[rules.allowlist]
regexes = ['api_key:\s*ollama', 'api_key:\s*any']

[[rules]]
id = "cf-phone-number"
description = "US phone number in source or config"
regex = '''\b(\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b'''
[rules.allowlist]
regexes = ['555-\d{4}', '555\.\d{4}', '5550', '1234567890', '0000000000']

[[rules]]
id = "cf-personal-email"
description = "Personal email address in source/config (not .example files)"
regex = '''[a-zA-Z0-9._%+\-]+@(gmail|yahoo|icloud|hotmail|outlook|proton)\.(com|me)'''
[rules.allowlist]
paths = ['.*\.example$', '.*test.*', '.*docs/.*']

[allowlist]
description = "CircuitForge global allowlist"
paths = [
    '.*\.example$',
    'docs/reference/.*',
    'gitleaks\.toml$',
]
regexes = [
    'sk-abcdefghijklmnopqrstuvwxyz',
    'your-forgejo-api-token-here',
]
```

### Per-repo override (e.g. `peregrine/.gitleaks.toml`)

```toml
[extend]
path = "/Library/Development/CircuitForge/circuitforge-hooks/gitleaks.toml"

[allowlist]
regexes = [
    '\d{10}\.html',   # Craigslist listing IDs (10-digit, look like phone numbers)
]
```

## Activation Per Repo

Each repo's `setup.sh` or `manage.sh` calls:

```bash
bash /Library/Development/CircuitForge/circuitforge-hooks/install.sh
```

`install.sh` does exactly one thing:

```bash
git config core.hooksPath /Library/Development/CircuitForge/circuitforge-hooks/hooks
```

For Heimdall live deploys (`/devl/<repo>/`), the same line goes in the deploy
script / post-receive hook.

## Migration from Peregrine

- `peregrine/.githooks/pre-commit` → replaced by gitleaks wrapper
- `peregrine/.githooks/commit-msg` → copied verbatim to hooks repo
- `peregrine/tests/test_hooks.sh` → migrated and extended in hooks repo
- `peregrine/.githooks/` directory → kept temporarily, then removed after cutover

## Rollout Order

1. `circuitforge-hooks` repo — create, implement, test
2. `peregrine` — activate (highest priority, already public)
3. `circuitforge-license` (heimdall) — activate before any public release
4. All subsequent repos — activate as part of their public-release checklist

## Testing

`tests/test_hooks.sh` covers:

- Staged file with live-format token → blocked
- Staged file with phone number → blocked
- Staged file with personal email in source → blocked
- `.example` file with placeholders → allowed
- Craigslist URL with 10-digit ID → allowed (Peregrine allowlist)
- Valid conventional commit message → accepted
- Non-conventional commit message → rejected

## What This Does Not Cover

- Scanning existing history on new repos (run `gitleaks git` manually before
  making any repo public — add to the public-release checklist)
- CI/server-side enforcement (future: Forgejo Actions job on push to main)
- Binary files or encrypted secrets at rest
