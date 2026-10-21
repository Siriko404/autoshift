#!/usr/bin/env bash
# Runs a steps file (default: hello.json) once on a brand-new scratch git repo and prints the result.
#   examples/hello/run.sh [STEPS FILE]
# Needs a Claude worker sign-in (adapters/sandbox.sh --login claude) and a usage reader (adapters/claude_quota.py).
# No usage reader? Choose that explicitly:  AUTOSHIFT_UNMETERED=1 examples/hello/run.sh
set -uo pipefail
PKG=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
WORK=$(mktemp -d "${AUTOSHIFT_SCRATCH:-${TMPDIR:-/tmp}}/autoshift-demo-XXXX")
GRAPH=$(readlink -f "${1:-$PKG/examples/hello/hello.json}")
mkdir -p "$WORK/repo/src/a" "$WORK/repo/src/b" && cd "$WORK/repo" && git init -q -b main \
  && for d in src src/a src/b; do echo keep > $d/.keep; done && git add . \
  && git -c user.name=demo -c user.email=demo@localhost commit -qm base
cd "$PKG"
if [ "${AUTOSHIFT_UNMETERED:-0}" = 1 ]; then
  bin/autoshift-config apply "$GRAPH" "$WORK/graph.json" claude.unmetered=true >/dev/null || exit 2
  echo "note: running Claude with NO usage stop (AUTOSHIFT_UNMETERED=1)"
else
  bin/autoshift-config apply "$GRAPH" "$WORK/graph.json" >/dev/null || exit 2
  if ! python3 adapters/claude_quota.py >/dev/null 2>"$WORK/reader.err"; then
    cat "$WORK/reader.err"
    echo "The kernel will not start Claude steps without a usage reader. Install one (docs/ADAPTERS.md)"
    echo "or choose to run without a usage stop:  AUTOSHIFT_UNMETERED=1 $0 ${1:-}"
    exit 2
  fi
fi
AS=(bin/autoshift --graph "$WORK/graph.json" --repo "$WORK/repo" --state "$WORK/state")
"${AS[@]}" init >/dev/null
"${AS[@]}" run; rc=$?
echo "run rc=$rc   work dir: $WORK"
"${AS[@]}" status
exit $rc
