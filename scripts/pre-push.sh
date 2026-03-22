#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PREFIX="[pre-push]"

# Read stdin: lines of "<local ref> <local sha1> <remote ref> <remote sha1>"
CHANGED_FILES=""

while read -r local_ref local_sha remote_ref remote_sha; do
    ZEROS="0000000000000000000000000000000000000000"

    if [[ "$remote_sha" == "$ZEROS" ]]; then
        # New branch — diff against parent commit
        FILES="$(git diff --name-only HEAD~1..HEAD 2>/dev/null || git diff --name-only HEAD 2>/dev/null || true)"
    else
        FILES="$(git diff --name-only "${remote_sha}..${local_sha}" 2>/dev/null || true)"
    fi

    if [[ -n "$FILES" ]]; then
        CHANGED_FILES="${CHANGED_FILES}${FILES}"$'\n'
    fi
done

# Trim trailing whitespace/newlines
CHANGED_FILES="$(echo "$CHANGED_FILES" | sed '/^[[:space:]]*$/d')"

if [[ -z "$CHANGED_FILES" ]]; then
    echo "$PREFIX No changed files detected, skipping screenshot check."
    exit 0
fi

# Check if claude is available
if ! command -v claude &>/dev/null; then
    echo "$PREFIX Warning: 'claude' not found in PATH, skipping UI change detection."
    exit 0
fi

echo "$PREFIX Asking Claude if UI was changed..."

CLAUDE_RESPONSE="$(echo "$CHANGED_FILES" | claude --print "These files were changed in a git push. Does this change affect the visual UI of a web application (HTML, CSS, JavaScript templates, or anything that changes what the user sees in a browser)? Answer with only YES or NO." 2>/dev/null || true)"

# Trim whitespace and uppercase
CLAUDE_ANSWER="$(echo "$CLAUDE_RESPONSE" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"

if [[ "$CLAUDE_ANSWER" != "YES" ]]; then
    echo "$PREFIX No UI changes detected (Claude answered: '$CLAUDE_RESPONSE'), skipping screenshots."
    exit 0
fi

echo "$PREFIX UI changes detected — regenerating screenshots..."

if ! python scripts/screenshot.py; then
    echo "$PREFIX Warning: screenshot.py failed. Skipping screenshot update."
    exit 0
fi

git add docs/screenshots/ 2>/dev/null || true

STAGED_SCREENSHOTS="$(git diff --cached --name-only docs/screenshots/ 2>/dev/null || true)"

if [[ -z "$STAGED_SCREENSHOTS" ]]; then
    echo "$PREFIX Screenshots unchanged, continuing push."
    exit 0
fi

git commit -m "Update screenshots"
echo "$PREFIX Screenshots updated. Please run 'git push' again to include them."
exit 1
