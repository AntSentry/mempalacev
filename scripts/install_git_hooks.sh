#!/usr/bin/env bash
# Install MemPalace's git hooks by symlinking .git-hooks/* into .git/hooks/.
#
# Idempotent: re-running replaces existing symlinks but never overwrites a
# real file. If `.git/hooks/pre-commit` is a regular file (not a symlink),
# this script aborts and asks the user to remove it manually so we don't
# clobber a hand-written hook.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC_DIR="$REPO_ROOT/.git-hooks"
DEST_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$SRC_DIR" ]; then
    echo "[install_git_hooks] no .git-hooks/ directory found at $SRC_DIR" >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

for hook in "$SRC_DIR"/*; do
    [ -f "$hook" ] || continue
    name="$(basename "$hook")"
    dest="$DEST_DIR/$name"

    if [ -e "$dest" ] && [ ! -L "$dest" ]; then
        echo "[install_git_hooks] refusing to overwrite real file $dest" >&2
        echo "[install_git_hooks] remove it manually, then re-run" >&2
        exit 1
    fi

    ln -sf "$hook" "$dest"
    chmod +x "$hook"
    echo "[install_git_hooks] linked $name -> $hook"
done

echo "[install_git_hooks] done."
