#!/usr/bin/env bash
# Sync main and the release tags to the GitHub and Codeberg mirrors by hand.
#
# This replaced the CI mirror workflow, which failed on every tag (peregrine#246). Run it after
# merging to main or cutting a release:
#
#   scripts/sync-mirrors.sh            push main and tags to both mirrors
#   scripts/sync-mirrors.sh --dry-run  show what would be pushed, change nothing
#
# Safe by design: it never uses --mirror and never deletes a branch or tag on a mirror, and a
# tag that already exists with different content is rejected rather than overwritten. If a mirror
# rejects one ref the others still go through, and the exit status says whether anything failed.
#
# Tokens are read from files and handed to git through an askpass helper, so they never appear in
# a command line, the environment listing, a remote URL or the output:
#   ~/.config/github/token     GitHub token (packages are not needed, repo write is)
#   ~/.config/codeberg/token   Codeberg token
set -euo pipefail

REPO="${SYNC_REPO:-peregrine}"
DRY_RUN=""
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN="--dry-run"

cd "$(git rev-parse --show-toplevel)"

# Public fetch, so the pushed commit is exactly what Forgejo has (not whatever branch is checked out).
git fetch --quiet origin main --tags

askpass="$(mktemp)"
trap 'rm -f "$askpass"' EXIT
cat >"$askpass" <<'EOF'
#!/bin/sh
case "$1" in
  *sername*) printf '%s\n' "$SYNC_USER" ;;
  *) cat "$SYNC_TOKEN_FILE" ;;
esac
EOF
chmod 700 "$askpass"

failed=0
sync_one() {
    local name="$1" url="$2" user="$3" token_file="$4"
    if [[ ! -r "$token_file" ]]; then
        echo "[$name] skipped: cannot read $token_file" >&2
        failed=1
        return
    fi
    echo "[$name] pushing main and tags to $url ${DRY_RUN:+(dry run)}"
    if GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 SYNC_USER="$user" SYNC_TOKEN_FILE="$token_file" \
        git push $DRY_RUN "$url" refs/remotes/origin/main:refs/heads/main --tags; then
        echo "[$name] ok"
    else
        echo "[$name] FAILED, see the git output above" >&2
        failed=1
    fi
}

sync_one github   "https://github.com/CircuitForgeLLC/${REPO}.git" x-access-token "$HOME/.config/github/token"
sync_one codeberg "https://codeberg.org/CircuitForge/${REPO}.git"  pyr0ball       "$HOME/.config/codeberg/token"

exit "$failed"
