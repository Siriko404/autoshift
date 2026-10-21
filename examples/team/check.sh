#!/usr/bin/env bash
# The check: both workers' files must hold exactly the agreed lines. No agent can edit this file.
set -euo pipefail
[[ "$(cat src/a/one.txt 2>/dev/null)" == "first worker done" ]]
[[ "$(cat src/b/two.txt 2>/dev/null)" == "second worker done" ]]
printf ok > "$AUTOSHIFT_GATE_OUT/team.ok"
