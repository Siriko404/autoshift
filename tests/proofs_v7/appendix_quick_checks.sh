#!/bin/bash
# Short supporting checks (not among the six main proofs). Usage: bash appendix_quick_checks.sh <path-to-pinned-v4>
# Everything runs in a mktemp directory; stubs only; the sandbox check runs `command -v`, it never starts a CLI.
set -u
V4=$(readlink -f "$1"); W=$(mktemp -d); echo "scratch $W"

echo "== Q1 mutant runners never check that the target test is green first"
cp -a "$V4" "$W/mut" && cd "$W/mut" || exit 9
for t in test_graph test_ledger test_runner; do printf 'raise SystemExit(1)  # broken: checks nothing\n' > tests/$t.py; done
python3 tests/test_mutants.py; echo "rc=$?  (three target tests replaced by 'exit 1'; runner still reports all mutants killed)"
cd "$W"

echo "== Q2 a static quota number is treated as a fresh reading forever"
python3 -I -c "import sys;sys.path.insert(0,'$V4');from autoshift.quota import reading;print(reading({'claude':{'usage_pct':10,'limit_pct':80}},'claude'))"

echo "== Q3 handoff text: goal shortened; work pattern and output contract dropped"
python3 -I - "$V4" "$W" <<'PY'
import sys, json, pathlib
sys.path.insert(0, sys.argv[1]); from autoshift.runner import execute
d = pathlib.Path(sys.argv[2]) / 'q3'; d.mkdir()
goal = 'Fix the build so that the test passes and then stop; do not touch the gate or the harness, and the change must be small and a clear one'
execute({'id': 'w', 'kind': 'agent', 'goal': goal, 'tiers': ['x'], 'sandbox': ['true']}, 1, 'x', d, d / 'st')  # 'true' ignores argv: nothing launched
h = json.loads((d / 'st/handoffs/w-1.json').read_text())
print('goal sent   :', h['goal']); print('work_pattern:', repr(h['work_pattern']), '| output_contract:', repr(h['output_contract']))
PY

echo "== Q4 editing the graph between runs (a node removed) crashes the driver at summary"
python3 -I - "$V4" "$W" <<'PY'
import sys, pathlib
sys.path.insert(0, sys.argv[1]); from autoshift.graph import validate; from autoshift.scheduler import Engine
d = pathlib.Path(sys.argv[2]) / 'q4'; d.mkdir()
g1 = validate({'nodes': [{'id': 'a', 'kind': 'code', 'cmd': ['true']}, {'id': 'b', 'kind': 'code', 'cmd': ['true']}]})
print('run 1 passed =', Engine(g1, d, pathlib.Path(sys.argv[2]) / 'q4-state').run()['passed'])
g2 = validate({'nodes': [{'id': 'a', 'kind': 'code', 'cmd': ['true']}, {'id': 'c', 'kind': 'code', 'cmd': ['true']}]})
try: print(Engine(g2, d, pathlib.Path(sys.argv[2]) / 'q4-state').run())
except Exception as e: print('run 2 with edited graph raised', type(e).__name__, e)
PY

echo "== Q5 second driver on the same state is refused (non-risk check)"
mkdir -p "$W/q5"; printf '{"nodes":[{"id":"s","kind":"code","cmd":["python3","-c","import time;time.sleep(2)"]}]}' > "$W/q5/g.json"
"$V4/bin/autoshift" --graph "$W/q5/g.json" --repo "$W/q5" --state "$W/q5-state" run >/dev/null & D=$!; sleep 0.6
"$V4/bin/autoshift" --graph "$W/q5/g.json" --repo "$W/q5" --state "$W/q5-state" run; echo "second driver rc=$?"; wait $D

echo "== Q6 inside the shipped sandbox arguments (G1/G2: --rw . --net 1, here --net 0): provider CLIs and HOME"
mkdir -p "$W/q6"; bash "$V4/adapters/sandbox.sh" --rw "$W/q6" --net 0 -- sh -c 'for c in claude codex opencode agy; do command -v $c >/dev/null && echo "$c: found" || echo "$c: NOT FOUND"; done; echo "HOME=$HOME entries: $(ls -A "$HOME" | wc -l)"'
echo "sandbox rc=$?"
