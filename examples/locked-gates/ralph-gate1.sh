#!/usr/bin/env bash
set -euo pipefail
# Demonstration oracle: sentinel must contain the exact agreed text.
[[ "$(cat done.txt 2>/dev/null)" == "VERIFIED" ]]
printf ok > "$AUTOSHIFT_GATE_OUT/gate1.ok"
