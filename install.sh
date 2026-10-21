#!/usr/bin/env bash
# Puts `autoshift` and `autoshift-config` on PATH (~/.local/bin) and the skills into ~/.claude/skills.
# An existing different file or link is never replaced unless you pass --force.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
FORCE=0; [ "${1:-}" = --force ] && FORCE=1
command -v bwrap >/dev/null || echo "note: bubblewrap (bwrap) is not installed; agents cannot run without it"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' || { echo "Python 3.12 or newer is required"; exit 1; }
link() {  # link SOURCE TARGET
  if [ -e "$2" ] || [ -L "$2" ]; then
    if [ "$(readlink -f "$2")" = "$(readlink -f "$1")" ]; then return; fi
    if [ "$FORCE" = 0 ]; then echo "skipped $2 (exists; rerun with --force to replace)"; return; fi
    rm -f "$2"
  fi
  ln -s "$1" "$2"; echo "linked $2"
}
mkdir -p "$HOME/.local/bin" "$HOME/.claude/skills"
link "$HERE/bin/autoshift" "$HOME/.local/bin/autoshift"
link "$HERE/bin/autoshift-config" "$HOME/.local/bin/autoshift-config"
for s in "$HERE"/skills/*/; do link "${s%/}" "$HOME/.claude/skills/$(basename "$s")"; done
echo "done. Next: autoshift --home; then sign in a worker: $HERE/adapters/sandbox.sh --login claude"
