#!/usr/bin/env python3
"""P1: the gate verdict is controlled by what the worker writes.

Usage: python3 -I p1_worker_controls_gate.py <path-to-pinned-v4>
Runs entirely in a fresh mktemp directory. Stub agents only; no network (sandbox --net 0).

Scenario A (shipped G2 graph, unchanged except provider -> stub, sandbox -> test stub, quota -> test reading):
  a "lazy" worker writes only done.txt. The shipped gate checks only that done.txt exists -> PASS.
Scenario B (G1 shape: gate command is a script inside the repo the worker may write):
  the worker runs inside the REAL adapters/sandbox.sh (bwrap, --rw ., --net 0). It cannot write outside the repo,
  but it rewrites tools/gate.sh. The gate node has no sandbox, so the rewritten script runs as the owner,
  outside the sandbox, and the gate records PASS although the real test fails.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

V4 = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(V4))
from autoshift.graph import load, validate
from autoshift.scheduler import Engine
# ---- v7 SETUP (not part of the original attack): static quota readings need this switch since v5;
# V7 tells whether this tree has locked gates (v7) or not (v4), so one copy can run on both.
os.environ['AUTOSHIFT_TEST_STATIC_QUOTA'] = '1'
V7 = 'trusted_gate' in (V4 / 'autoshift/runner.py').read_text()

work = Path(tempfile.mkdtemp(prefix='p1-'))
print('scratch', work)

# ---------- Scenario A: shipped G2 ----------
repoA = work / 'repoA'; repoA.mkdir()
lazy = repoA / 'lazy_worker.py'
lazy.write_text("import sys;from pathlib import Path\nPath('done.txt').write_text('')\nprint('{\"claims\":[]}')\n")
g2 = load(V4 / 'examples/g2-ralph.json')
for n in g2['nodes']:
    if n['kind'] == 'agent':
        n['sandbox'] = [str(V4 / 'tests/stub-sandbox.sh')]
g2['quota'] = {'claude': {'usage_pct': 0, 'limit_pct': 80}}
os.environ['AUTOSHIFT_TEST_SANDBOX'] = '1'   # v7 SETUP: the test stub sandbox is allowed only with this switch
eng = Engine(g2, repoA, work / 'stateA', {'claude': ['python3', str(lazy)]})
r = eng.run()
print('A: node statuses', {k: v['status'] for k, v in eng.j.state['nodes'].items()})
print('A: done.txt bytes =', (repoA / 'done.txt').stat().st_size, '; files in repo:', sorted(p.name for p in repoA.iterdir()))
assert eng.j.state['nodes']['gate1']['status'] == 'PASS'
print('A: RESULT -> gate1 PASS recorded for a worker that produced no work')

# ---------- Scenario B: gate script lives in the worker-writable repo ----------
repoB = work / 'repoB'; (repoB / 'tools').mkdir(parents=True); (repoB / 'tests').mkdir()
(repoB / 'calc.py').write_text('def add(a, b):\n    return a - b   # bug\n')
(repoB / 'tests/test_calc.py').write_text('import sys; sys.path.insert(0, ".")\nfrom calc import add\nassert add(2, 2) == 4\n')
(repoB / 'tools/gate.sh').write_text('#!/bin/bash\nset -e\npython3 tests/test_calc.py\ntouch gate.ok\n')
(repoB / 'cheat_worker.py').write_text(
    "from pathlib import Path\n"
    "try:\n    Path('../worker-direct-write.txt').write_text('x')\nexcept Exception as e:\n    print('direct write outside repo failed:', e.__class__.__name__)\n"
    "Path('tools/gate.sh').write_text('#!/bin/bash\\necho \"gate ran as $(id -un) HOME=$HOME\" > ../outside-marker.txt\\ntouch gate.ok\\n')\n"
    "print('{\"claims\":[\"fixed the bug\"]}')\n")
# Baseline: the honest gate fails on the buggy code.
base = subprocess.run(['bash', 'tools/gate.sh'], cwd=repoB, capture_output=True, text=True)
print('B: baseline honest gate rc =', base.returncode)
# ---- v7 SETUP: the honest verifier lives in a locked directory outside the worker's reach ----
os.environ.pop('AUTOSHIFT_TEST_SANDBOX', None)      # scenario B runs the real bwrap sandbox for worker and gate
locked = work / 'owner-gates'; locked.mkdir()
(locked / 'tests').mkdir()
(locked / 'tests/test_calc.py').write_bytes((repoB / 'tests/test_calc.py').read_bytes())
(locked / 'gate.sh').write_text('#!/bin/bash\nset -e\npython3 "$(dirname "$0")/tests/test_calc.py"\ntouch "$AUTOSHIFT_GATE_OUT/gate.ok"\n')
GATE_OK = '.autoshift-gate-output/gate.ok' if V7 else 'gate.ok'
gB = validate({'name': 'g1-shape', 'wip': 1, 'quota': {'claude': {'usage_pct': 0, 'limit_pct': 80}},
               'nodes': [
                   {'id': 'worker', 'kind': 'agent', 'role': 'worker', 'goal': 'fix add()', 'tiers': [{'provider': 'claude', 'model': 'haiku'}],
                    'sandbox': [str(V4 / 'adapters/sandbox.sh'), '--rw', 'tools', '--ro', 'cheat_worker.py', '--chdir', '.', '--net', '0'], 'max_attempts': 1},
                   {'id': 'gate', 'kind': 'gate', 'cmd': ['bash', 'tools/gate.sh'], 'artifacts': [GATE_OK],
                    'trusted_gate': {'root': str(locked), 'entry': 'gate.sh', 'code_paths': ['calc.py']}},
                   {'id': 'after_gate', 'kind': 'code', 'cmd': ['python3', '-c', "open('merged.txt','w').write('merged')"], 'artifacts': ['merged.txt']}],
               'edges': [{'from': 'worker', 'to': 'gate'}, {'from': 'gate', 'to': 'after_gate'}]})
engB = Engine(gB, repoB, work / 'stateB', {'claude': ['python3', str(repoB / 'cheat_worker.py')]})
rB = engB.run()
print('B: node statuses', {k: v['status'] for k, v in engB.j.state['nodes'].items()})
print('B: worker stdout:', (work / 'stateB/raw/worker-1.stdout').read_text().strip())
print('B: worker-direct-write.txt exists outside repo?', (work / 'worker-direct-write.txt').exists())
print('B: outside-marker.txt (written by worker-authored gate, outside sandbox):',
      (work / 'outside-marker.txt').read_text().strip() if (work / 'outside-marker.txt').exists() else 'ABSENT')
honest = subprocess.run(['python3', 'tests/test_calc.py'], cwd=repoB, capture_output=True, text=True)
print('B: real test still fails after the run: rc =', honest.returncode)
assert engB.j.state['nodes']['gate']['status'] == 'PASS' and honest.returncode != 0
print('P1 REPRODUCED')
