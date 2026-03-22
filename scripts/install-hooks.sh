#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SCRIPT_SRC="$REPO_ROOT/scripts/pre-push.sh"
HOOK_DEST="$HOOKS_DIR/pre-push"

ln -sf "$SCRIPT_SRC" "$HOOK_DEST"
chmod +x "$SCRIPT_SRC"

echo "Installed pre-push hook: $HOOK_DEST -> $SCRIPT_SRC"
