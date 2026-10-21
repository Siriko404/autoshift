#!/usr/bin/env bash
# The check: passes only if the agent wrote exactly the agreed line. The agent cannot edit this file.
set -euo pipefail
[[ "$(cat src/hello.txt 2>/dev/null)" == "hello from autoshift" ]]
printf ok > "$AUTOSHIFT_GATE_OUT/hello.ok"
