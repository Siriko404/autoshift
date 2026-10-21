#!/usr/bin/env bash
# Removes only the links install.sh made (links that point into this folder). Run state is kept.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
for t in "$HOME/.local/bin/autoshift" "$HOME/.local/bin/autoshift-config" "$HOME"/.claude/skills/autoshift*; do
  [ -L "$t" ] && case "$(readlink -f "$t")" in "$HERE"/*) rm "$t"; echo "removed $t";; esac
done
echo "kept ~/.local/state/autoshift (worker sign-ins); delete it yourself if you want"
