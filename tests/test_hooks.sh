#!/usr/bin/env bash
set -euo pipefail
HOOK=".githooks/pre-commit"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; exit 1; }

# Helper: run hook against a fake staged file list
run_hook_with() {
    local staged_file="$1"
    local staged_content="${2:-}"
    local tmpdir
    tmpdir=$(mktemp -d)

    # Create shim that reports our file as staged
    cat > "$tmpdir/git" <<SHIM
#!/usr/bin/env bash
if [[ "\$*" == *"diff-index"* ]]; then
    echo "$staged_file"
elif [[ "\$*" == *"diff"*"--cached"* ]]; then
    echo "$staged_content"
else
    command git "\$@"
fi
SHIM
    chmod +x "$tmpdir/git"
    PATH="$tmpdir:$PATH" bash "$HOOK" 2>&1
    local status=$?
    rm -rf "$tmpdir"
    return $status
}

echo "Test 1: blocks config/user.yaml"
run_hook_with "config/user.yaml" && fail "should have blocked" || pass "blocked user.yaml"

echo "Test 2: blocks .env"
run_hook_with ".env" && fail "should have blocked" || pass "blocked .env"

echo "Test 3: blocks content with OpenAI key pattern"
run_hook_with "app/app.py" "+sk-abcdefghijklmnopqrstuvwxyz123456" && \
    fail "should have blocked key pattern" || pass "blocked key pattern"

echo "Test 4: allows safe file"
run_hook_with "app/app.py" "import streamlit" && pass "allowed safe file" || \
    fail "should have allowed safe file"

echo "All pre-commit hook tests passed."
