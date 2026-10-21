#!/usr/bin/env bash
# G1 owner-installed immutable gate entry. Acceptance is an owner-mapped, pinned path.
set -uo pipefail
: "${AUTOSHIFT_GATE_OUT:?}" "${AUTOSHIFT_TASK_WORKTREE:?}" "${AUTOSHIFT_TASK_ID:?}" "${AUTOSHIFT_ACCEPTANCE:?}"
mkdir -p "$AUTOSHIFT_GATE_OUT"
out="$AUTOSHIFT_GATE_OUT/$AUTOSHIFT_TASK_ID.GATE.md"
case "$AUTOSHIFT_TASK_ID" in *[!a-zA-Z0-9_.-]*|'') exit 2;; esac
printf '# Gate %s\n\n| step | exit | result |\n|---|---|---|\n' "$AUTOSHIFT_TASK_ID" >"$out"
if [ ! -f "$AUTOSHIFT_ACCEPTANCE" ]; then rc=125
else
  # The trusted acceptance script is run with worktree code as data, not a worker-authored script.
  bash "$AUTOSHIFT_ACCEPTANCE" "$AUTOSHIFT_TASK_WORKTREE" >"$AUTOSHIFT_GATE_OUT/$AUTOSHIFT_TASK_ID.acceptance.log" 2>&1
  rc=$?
fi
if [ "$rc" -eq 0 ]; then printf '| acceptance | 0 | PASS |\n' >>"$out"
else printf '| acceptance | %s | FAIL |\n' "$rc" >>"$out"; fi
exit "$rc"
