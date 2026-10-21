#!/usr/bin/env bash
# Replace with owner's project-specific tests; trusted root, never worker-writable.
set -euo pipefail
test -f "$1/src/feature.txt"
grep -qx 'OK' "$1/src/feature.txt"
