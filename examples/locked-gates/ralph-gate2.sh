#!/usr/bin/env bash
set -euo pipefail
[[ "$(cat done.txt 2>/dev/null)" == "VERIFIED" ]]
printf ok > "$AUTOSHIFT_GATE_OUT/gate2.ok"
