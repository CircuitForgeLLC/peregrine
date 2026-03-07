# CircuitForge Hooks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the `circuitforge-hooks` repo with gitleaks-based secret/PII scanning, activate it in Peregrine, and retire the old hand-rolled `.githooks/pre-commit`.

**Architecture:** A standalone git repo holds three hook scripts (pre-commit, commit-msg, pre-push) and a shared `gitleaks.toml`. Each product repo activates it with `git config core.hooksPath`. Per-repo `.gitleaks.toml` files extend the base config with repo-specific allowlists.

**Tech Stack:** gitleaks (Go binary, apt install), bash, TOML config

---

### Task 1: Install gitleaks

**Files:**
- None — binary install only

**Step 1: Install gitleaks**

```bash
sudo apt-get install -y gitleaks
```

If not in apt (older Ubuntu), use the GitHub release:
```bash
GITLEAKS_VERSION=$(curl -s https://api.github.com/repos/gitleaks/gitleaks/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")
curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION#v}_linux_x64.tar.gz" | sudo tar -xz -C /usr/local/bin gitleaks
```

**Step 2: Verify**

```bash
gitleaks version
```
Expected: prints version string e.g. `v8.x.x`

---

### Task 2: Create repo and write gitleaks.toml

**Files:**
- Create: `/Library/Development/CircuitForge/circuitforge-hooks/gitleaks.toml`

**Step 1: Scaffold repo**

```bash
mkdir -p /Library/Development/CircuitForge/circuitforge-hooks/hooks
mkdir -p /Library/Development/CircuitForge/circuitforge-hooks/tests
cd /Library/Development/CircuitForge/circuitforge-hooks
git init
```

**Step 2: Write gitleaks.toml**

Create `/Library/Development/CircuitForge/circuitforge-hooks/gitleaks.toml`:

```toml
title = "CircuitForge secret + PII scanner"

[extend]
useDefault = true   # inherit all 150+ built-in gitleaks rules

# ── CircuitForge-specific secret patterns ────────────────────────────────────

[[rules]]
id = "cf-generic-env-token"
description = "Generic KEY=<token> in env-style assignment — catches FORGEJO_API_TOKEN=hex etc."
regex = '''(?i)(token|secret|key|password|passwd|pwd|api_key)\s*[=:]\s*['"]?[A-Za-z0-9\-_]{20,}['"]?'''
[rules.allowlist]
regexes = [
    'api_key:\s*ollama',
    'api_key:\s*any',
    'your-[a-z\-]+-here',
    'replace-with-',
    'xxxx',
]

# ── PII patterns ──────────────────────────────────────────────────────────────

[[rules]]
id = "cf-phone-number"
description = "US phone number committed in source or config"
regex = '''\b(\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b'''
[rules.allowlist]
regexes = [
    '555-\d{4}',
    '555\.\d{4}',
    '5550\d{4}',
    '^1234567890$',
    '0000000000',
    '1111111111',
    '2222222222',
    '9999999999',
]

[[rules]]
id = "cf-personal-email"
description = "Personal webmail address committed in source or config (not .example files)"
regex = '''[a-zA-Z0-9._%+\-]+@(gmail|yahoo|icloud|hotmail|outlook|proton)\.(com|me)'''
[rules.allowlist]
paths = [
    '.*\.example$',
    '.*test.*',
    '.*docs/.*',
    '.*\.md$',
]

# ── Global allowlist ──────────────────────────────────────────────────────────

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
    'your-[a-z\-]+-here',
]
```

**Step 3: Smoke-test config syntax**

```bash
cd /Library/Development/CircuitForge/circuitforge-hooks
gitleaks detect --config gitleaks.toml --no-git --source . 2>&1 | head -5
```
Expected: no "invalid config" errors. (May report findings in the config itself — that's fine.)

**Step 4: Commit**

```bash
cd /Library/Development/CircuitForge/circuitforge-hooks
git add gitleaks.toml
git commit -m "feat: add shared gitleaks config with CF secret + PII rules"
```

---

### Task 3: Write hook scripts

**Files:**
- Create: `hooks/pre-commit`
- Create: `hooks/commit-msg`
- Create: `hooks/pre-push`

**Step 1: Write hooks/pre-commit**

```bash
#!/usr/bin/env bash
# pre-commit — scan staged diff for secrets + PII via gitleaks
set -euo pipefail

HOOKS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_CONFIG="$HOOKS_REPO/gitleaks.toml"
REPO_ROOT="$(git rev-parse --show-toplevel)"
REPO_CONFIG="$REPO_ROOT/.gitleaks.toml"

if ! command -v gitleaks &>/dev/null; then
    echo "ERROR: gitleaks not found. Install with: sudo apt-get install gitleaks"
    echo "       or: https://github.com/gitleaks/gitleaks#installing"
    exit 1
fi

CONFIG_ARG="--config=$BASE_CONFIG"
[[ -f "$REPO_CONFIG" ]] && CONFIG_ARG="--config=$REPO_CONFIG"

if ! gitleaks protect --staged $CONFIG_ARG --redact 2>&1; then
    echo ""
    echo "Commit blocked: secrets or PII detected in staged changes."
    echo "Review above, remove the sensitive value, then re-stage and retry."
    echo "If this is a false positive, add an allowlist entry to .gitleaks.toml"
    exit 1
fi
```

**Step 2: Write hooks/commit-msg**

Copy verbatim from Peregrine:

```bash
#!/usr/bin/env bash
# commit-msg — enforces conventional commit format
set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

VALID_TYPES="feat|fix|docs|chore|test|refactor|perf|ci|build|security"
MSG_FILE="$1"
MSG=$(head -1 "$MSG_FILE")

if [[ -z "${MSG// }" ]]; then
    echo -e "${RED}Commit rejected:${NC} Commit message is empty."
    exit 1
fi

if ! echo "$MSG" | grep -qE "^($VALID_TYPES)(\(.+\))?: .+"; then
    echo -e "${RED}Commit rejected:${NC} Message does not follow conventional commit format."
    echo ""
    echo -e "  Required: ${YELLOW}type: description${NC}  or  ${YELLOW}type(scope): description${NC}"
    echo -e "  Valid types: ${YELLOW}$VALID_TYPES${NC}"
    echo ""
    echo -e "  Your message: ${YELLOW}$MSG${NC}"
    echo ""
    echo -e "  Examples:"
    echo -e "    ${YELLOW}feat: add cover letter refinement${NC}"
    echo -e "    ${YELLOW}fix(wizard): handle missing user.yaml gracefully${NC}"
    echo -e "    ${YELLOW}security: rotate leaked API token${NC}"
    exit 1
fi
exit 0
```

Note: added `security` to VALID_TYPES vs the Peregrine original.

**Step 3: Write hooks/pre-push**

```bash
#!/usr/bin/env bash
# pre-push — scan full branch history not yet on remote
# Safety net: catches anything committed with --no-verify or before hooks were wired
set -euo pipefail

HOOKS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_CONFIG="$HOOKS_REPO/gitleaks.toml"
REPO_ROOT="$(git rev-parse --show-toplevel)"
REPO_CONFIG="$REPO_ROOT/.gitleaks.toml"

if ! command -v gitleaks &>/dev/null; then
    echo "ERROR: gitleaks not found. Install with: sudo apt-get install gitleaks"
    exit 1
fi

CONFIG_ARG="--config=$BASE_CONFIG"
[[ -f "$REPO_CONFIG" ]] && CONFIG_ARG="--config=$REPO_CONFIG"

if ! gitleaks git $CONFIG_ARG --redact 2>&1; then
    echo ""
    echo "Push blocked: secrets or PII found in branch history."
    echo "Use git-filter-repo to scrub, then force-push."
    echo "See: https://github.com/newren/git-filter-repo"
    exit 1
fi
```

**Step 4: Make hooks executable**

```bash
chmod +x hooks/pre-commit hooks/commit-msg hooks/pre-push
```

**Step 5: Commit**

```bash
cd /Library/Development/CircuitForge/circuitforge-hooks
git add hooks/
git commit -m "feat: add pre-commit, commit-msg, and pre-push hook scripts"
```

---

### Task 4: Write install.sh

**Files:**
- Create: `install.sh`

**Step 1: Write install.sh**

```bash
#!/usr/bin/env bash
# install.sh — wire circuitforge-hooks into the calling git repo
# Usage: bash /Library/Development/CircuitForge/circuitforge-hooks/install.sh
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/hooks" && pwd)"

if ! git rev-parse --git-dir &>/dev/null; then
    echo "ERROR: not inside a git repo. Run from your product repo root."
    exit 1
fi

git config core.hooksPath "$HOOKS_DIR"
echo "CircuitForge hooks installed."
echo "  core.hooksPath → $HOOKS_DIR"
echo ""
echo "Verify gitleaks is available: gitleaks version"
```

**Step 2: Make executable**

```bash
chmod +x install.sh
```

**Step 3: Commit**

```bash
git add install.sh
git commit -m "feat: add install.sh for one-command hook activation"
```

---

### Task 5: Write tests

**Files:**
- Create: `tests/test_hooks.sh`

**Step 1: Write tests/test_hooks.sh**

```bash
#!/usr/bin/env bash
# tests/test_hooks.sh — integration tests for circuitforge-hooks
# Requires: gitleaks installed, bash 4+
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/hooks"
PASS_COUNT=0
FAIL_COUNT=0

pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "  FAIL: $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# Create a temp git repo for realistic staged-content tests
setup_temp_repo() {
    local dir
    dir=$(mktemp -d)
    git init "$dir" -q
    git -C "$dir" config user.email "test@example.com"
    git -C "$dir" config user.name "Test"
    git -C "$dir" config core.hooksPath "$HOOKS_DIR"
    echo "$dir"
}

run_pre_commit_in() {
    local repo="$1" file="$2" content="$3"
    echo "$content" > "$repo/$file"
    git -C "$repo" add "$file"
    bash "$HOOKS_DIR/pre-commit" 2>&1
    echo $?
}

echo ""
echo "=== pre-commit hook tests ==="

# Test 1: blocks live-format Forgejo token
echo "Test 1: blocks FORGEJO_API_TOKEN=<hex>"
REPO=$(setup_temp_repo)
echo 'FORGEJO_API_TOKEN=4ea4353b88d6388e8fafab9eb36662226f3a06b0' > "$REPO/test.env"
git -C "$REPO" add test.env
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:1"; then pass "blocked FORGEJO_API_TOKEN"; else fail "should have blocked FORGEJO_API_TOKEN"; fi
rm -rf "$REPO"

# Test 2: blocks OpenAI-style sk- key
echo "Test 2: blocks sk-<key> pattern"
REPO=$(setup_temp_repo)
echo 'api_key = "sk-abcXYZ1234567890abcXYZ1234567890"' > "$REPO/config.py"
git -C "$REPO" add config.py
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:1"; then pass "blocked sk- key"; else fail "should have blocked sk- key"; fi
rm -rf "$REPO"

# Test 3: blocks US phone number
echo "Test 3: blocks US phone number"
REPO=$(setup_temp_repo)
echo 'phone: "5107643155"' > "$REPO/config.yaml"
git -C "$REPO" add config.yaml
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:1"; then pass "blocked phone number"; else fail "should have blocked phone number"; fi
rm -rf "$REPO"

# Test 4: blocks personal email in source
echo "Test 4: blocks personal gmail address in .py file"
REPO=$(setup_temp_repo)
echo 'DEFAULT_EMAIL = "someone@gmail.com"' > "$REPO/app.py"
git -C "$REPO" add app.py
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:1"; then pass "blocked personal email"; else fail "should have blocked personal email"; fi
rm -rf "$REPO"

# Test 5: allows .example file with placeholders
echo "Test 5: allows .example file with placeholder values"
REPO=$(setup_temp_repo)
echo 'FORGEJO_API_TOKEN=your-forgejo-api-token-here' > "$REPO/config.env.example"
git -C "$REPO" add config.env.example
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:0"; then pass "allowed .example placeholder"; else fail "should have allowed .example file"; fi
rm -rf "$REPO"

# Test 6: allows ollama api_key placeholder
echo "Test 6: allows api_key: ollama (known safe placeholder)"
REPO=$(setup_temp_repo)
printf 'backends:\n  - api_key: ollama\n' > "$REPO/llm.yaml"
git -C "$REPO" add llm.yaml
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:0"; then pass "allowed ollama api_key"; else fail "should have allowed ollama api_key"; fi
rm -rf "$REPO"

# Test 7: allows safe source file
echo "Test 7: allows normal Python import"
REPO=$(setup_temp_repo)
echo 'import streamlit as st' > "$REPO/app.py"
git -C "$REPO" add app.py
RESULT=$(cd "$REPO" && bash "$HOOKS_DIR/pre-commit" 2>&1; echo "EXIT:$?")
if echo "$RESULT" | grep -q "EXIT:0"; then pass "allowed safe file"; else fail "should have allowed safe file"; fi
rm -rf "$REPO"

echo ""
echo "=== commit-msg hook tests ==="

tmpfile=$(mktemp)

echo "Test 8: accepts feat: message"
echo "feat: add gitleaks scanning" > "$tmpfile"
if bash "$HOOKS_DIR/commit-msg" "$tmpfile" &>/dev/null; then pass "accepted feat:"; else fail "rejected valid feat:"; fi

echo "Test 9: accepts security: message (new type)"
echo "security: rotate leaked API token" > "$tmpfile"
if bash "$HOOKS_DIR/commit-msg" "$tmpfile" &>/dev/null; then pass "accepted security:"; else fail "rejected valid security:"; fi

echo "Test 10: accepts fix(scope): message"
echo "fix(wizard): handle missing user.yaml" > "$tmpfile"
if bash "$HOOKS_DIR/commit-msg" "$tmpfile" &>/dev/null; then pass "accepted fix(scope):"; else fail "rejected valid fix(scope):"; fi

echo "Test 11: rejects non-conventional message"
echo "updated the thing" > "$tmpfile"
if bash "$HOOKS_DIR/commit-msg" "$tmpfile" &>/dev/null; then fail "should have rejected"; else pass "rejected non-conventional"; fi

echo "Test 12: rejects empty message"
echo "" > "$tmpfile"
if bash "$HOOKS_DIR/commit-msg" "$tmpfile" &>/dev/null; then fail "should have rejected empty"; else pass "rejected empty message"; fi

rm -f "$tmpfile"

echo ""
echo "=== Results ==="
echo "  Passed: $PASS_COUNT"
echo "  Failed: $FAIL_COUNT"
[[ $FAIL_COUNT -eq 0 ]] && echo "All tests passed." || { echo "FAILURES detected."; exit 1; }
```

**Step 2: Make executable**

```bash
chmod +x tests/test_hooks.sh
```

**Step 3: Run tests (expect failures — hooks not yet fully wired)**

```bash
cd /Library/Development/CircuitForge/circuitforge-hooks
bash tests/test_hooks.sh
```

Expected: Tests 1-4 should PASS (gitleaks catches real secrets), Tests 5-7 may fail if allowlists need tuning — note any failures for the next step.

**Step 4: Tune allowlists in gitleaks.toml if any false positives**

If Test 5 (`.example` file) or Test 6 (ollama) fail, add the relevant pattern to the `[allowlist]` or `[rules.allowlist]` sections in `gitleaks.toml` and re-run until all 12 pass.

**Step 5: Commit**

```bash
git add tests/
git commit -m "test: add integration tests for pre-commit and commit-msg hooks"
```

---

### Task 6: Write README and push to Forgejo

**Files:**
- Create: `README.md`

**Step 1: Write README.md**

```markdown
# circuitforge-hooks

Centralised git hooks for all CircuitForge repos.

## What it does

- **pre-commit** — scans staged changes for secrets and PII via gitleaks
- **commit-msg** — enforces conventional commit format
- **pre-push** — scans full branch history as a safety net before push

## Install

From any CircuitForge product repo root:

```bash
bash /Library/Development/CircuitForge/circuitforge-hooks/install.sh
```

On Heimdall live deploys (`/devl/<repo>/`), add the same line to the deploy script.

## Per-repo allowlists

Create `.gitleaks.toml` at the repo root to extend the base config:

```toml
[extend]
path = "/Library/Development/CircuitForge/circuitforge-hooks/gitleaks.toml"

[allowlist]
regexes = [
    '\d{10}\.html',   # example: Craigslist listing IDs
]
```

## Testing

```bash
bash tests/test_hooks.sh
```

## Requirements

- `gitleaks` binary: `sudo apt-get install gitleaks`
- bash 4+

## Adding a new rule

Edit `gitleaks.toml`. Follow the pattern of the existing `[[rules]]` blocks.
Add tests to `tests/test_hooks.sh` covering both the blocked and allowed cases.
```

**Step 2: Create Forgejo repo and push**

```bash
# Create repo on Forgejo
curl -s -X POST "https://git.opensourcesolarpunk.com/api/v1/user/repos" \
  -H "Authorization: token 4ea4353b88d6388e8fafab9eb36662226f3a06b0" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "circuitforge-hooks",
    "description": "Centralised git hooks for CircuitForge repos — gitleaks secret + PII scanning",
    "private": false,
    "auto_init": false
  }' | python3 -c "import json,sys; r=json.load(sys.stdin); print('Created:', r.get('html_url','ERROR:', r))"

# Add remote and push
cd /Library/Development/CircuitForge/circuitforge-hooks
git add README.md
git commit -m "docs: add README with install and usage instructions"
git remote add origin https://git.opensourcesolarpunk.com/pyr0ball/circuitforge-hooks.git
git push -u origin main
```

---

### Task 7: Activate in Peregrine

**Files:**
- Create: `peregrine/.gitleaks.toml`
- Modify: `peregrine/manage.sh` (add install.sh call)
- Delete: `peregrine/.githooks/pre-commit` (replaced by gitleaks wrapper)

**Step 1: Write peregrine/.gitleaks.toml**

```toml
# peregrine/.gitleaks.toml — per-repo allowlists extending the shared base config
[extend]
path = "/Library/Development/CircuitForge/circuitforge-hooks/gitleaks.toml"

[allowlist]
description = "Peregrine-specific allowlists"
regexes = [
    '\d{10}\.html',      # Craigslist listing IDs (10-digit paths, look like phone numbers)
    '\d{10}\/',          # LinkedIn job IDs in URLs
    'localhost:\d{4,5}', # port numbers that could trip phone pattern
]
```

**Step 2: Activate hooks in Peregrine**

```bash
cd /Library/Development/CircuitForge/peregrine
bash /Library/Development/CircuitForge/circuitforge-hooks/install.sh
```

Expected output:
```
CircuitForge hooks installed.
  core.hooksPath → /Library/Development/CircuitForge/circuitforge-hooks/hooks
```

Verify:
```bash
git config core.hooksPath
```
Expected: prints the absolute path to `circuitforge-hooks/hooks`

**Step 3: Add install.sh call to manage.sh**

In `peregrine/manage.sh`, find the section that runs setup/preflight (near the top of the `start` command handling). Add after the existing setup checks:

```bash
# Wire CircuitForge hooks (idempotent — safe to run every time)
if [[ -f "/Library/Development/CircuitForge/circuitforge-hooks/install.sh" ]]; then
    bash /Library/Development/CircuitForge/circuitforge-hooks/install.sh --quiet 2>/dev/null || true
fi
```

Also add a `--quiet` flag to `install.sh` to suppress output when called from manage.sh:

In `circuitforge-hooks/install.sh`, modify to accept `--quiet`:
```bash
QUIET=false
[[ "${1:-}" == "--quiet" ]] && QUIET=true

git config core.hooksPath "$HOOKS_DIR"
if [[ "$QUIET" == "false" ]]; then
    echo "CircuitForge hooks installed."
    echo "  core.hooksPath → $HOOKS_DIR"
fi
```

**Step 4: Retire old .githooks/pre-commit**

The old hook used hand-rolled regexes and is now superseded. Remove it:

```bash
cd /Library/Development/CircuitForge/peregrine
rm .githooks/pre-commit
```

Keep `.githooks/commit-msg` until verified the new one is working (then remove in a follow-up).

**Step 5: Smoke-test — try to commit a fake secret**

```bash
cd /Library/Development/CircuitForge/peregrine
echo 'TEST_TOKEN=abc123def456ghi789jkl012mno345' >> /tmp/leak-test.txt
git add /tmp/leak-test.txt 2>/dev/null || true
# Easier: stage it directly
echo 'BAD_TOKEN=abc123def456ghi789jkl012mno345pqr' > /tmp/test-secret.py
cp /tmp/test-secret.py .
git add test-secret.py
git commit -m "test: this should be blocked" 2>&1
```
Expected: commit blocked with gitleaks output. Clean up:
```bash
git restore --staged test-secret.py && rm test-secret.py
```

**Step 6: Commit Peregrine changes**

```bash
cd /Library/Development/CircuitForge/peregrine
git add .gitleaks.toml manage.sh
git rm .githooks/pre-commit
git commit -m "chore: activate circuitforge-hooks, add .gitleaks.toml, retire old pre-commit"
```

**Step 7: Push Peregrine**

```bash
git push origin main
```

---

### Task 8: Run full test suite and verify

**Step 1: Run the hooks test suite**

```bash
bash /Library/Development/CircuitForge/circuitforge-hooks/tests/test_hooks.sh
```
Expected: `All tests passed. Passed: 12  Failed: 0`

**Step 2: Run Peregrine tests to confirm nothing broken**

```bash
cd /Library/Development/CircuitForge/peregrine
/devl/miniconda3/envs/job-seeker/bin/pytest tests/ -v --tb=short -q 2>&1 | tail -10
```
Expected: all existing tests still pass.

**Step 3: Push hooks repo final state**

```bash
cd /Library/Development/CircuitForge/circuitforge-hooks
git push origin main
```

---

## Public-release checklist (for all future repos)

Add this to any repo's pre-public checklist:

```
[ ] Run: gitleaks git --config /Library/Development/CircuitForge/circuitforge-hooks/gitleaks.toml
    (manual full-history scan — pre-push hook only covers branch tip)
[ ] Run: bash /Library/Development/CircuitForge/circuitforge-hooks/install.sh
[ ] Add .gitleaks.toml with repo-specific allowlists
[ ] Verify: git config core.hooksPath
[ ] Make repo public on Forgejo
```
