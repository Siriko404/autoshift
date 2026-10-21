#!/usr/bin/env python3
"""P5: what happens after a FAIL.
 (a) Shipped G2: gate1 fails, pass2 runs, but pass2's handoff carries NO failure evidence from gate1
     (previous == {}; the gate's error text is nowhere in it), although its goal says "Review failure evidence".
 (b) The designed FAIL edge still raises an owner ask ("ask-exhausted:gate1") and the run reports failed>0.
 (c) Dead end: when a node exhausts its attempts, its PASS-dependents are SKIPPED at once; answering the ask
     changes nothing and a new run does not revive them.
Usage: python3 -I p5_failure_path.py <path-to-pinned-v4>
Stub agents, stub sandbox, test quota readings; mktemp scratch; no network.
"""
import contextlib, io, json, sys, tempfile
from pathlib import Path

V4 = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(V4))
from autoshift.graph import load, validate
from autoshift.scheduler import Engine
from autoshift import cli
import os
# ---- v7 SETUP: test switches for the stub quota and the stub sandbox ----
os.environ['AUTOSHIFT_TEST_STATIC_QUOTA'] = '1'
os.environ['AUTOSHIFT_TEST_SANDBOX'] = '1'

work = Path(tempfile.mkdtemp(prefix='p5-')); print('scratch', work)
# ---- (a)+(b) shipped G2; pass1 does nothing, pass2 writes done.txt ----
repo = work / 'g2'; repo.mkdir()
stub = repo / 'stub.py'
stub.write_text("import json,sys\nfrom pathlib import Path\nh=json.loads(Path(sys.argv[1]).read_text())\n"
                "if h['goal'].startswith('Review'): Path('done.txt').write_text('x')\nprint(json.dumps({'claims':[]}))\n")
g2 = load(V4 / 'examples/g2-ralph.json'); g2['quota'] = {'claude': {'usage_pct': 0, 'limit_pct': 80}}
for n in g2['nodes']:
    if n['kind'] == 'agent': n['sandbox'] = [str(V4 / 'tests/stub-sandbox.sh')]
# ---- v7 SETUP: the gates' original assertion commands, as locked scripts outside the repo; the .ok file goes to the gate output dir ----
locked = work / 'locked-gates'; locked.mkdir()
for node in g2['nodes']:
    if node['kind'] == 'gate':
        (locked / (node['id'] + '.sh')).write_text('#!/bin/sh\nset -e\npython3 -c ' + repr(node['cmd'][-1]) + '\ncp ' + node['id'] + '.ok "$AUTOSHIFT_GATE_OUT/' + node['id'] + '.ok"\n')
        node['trusted_gate'] = {'root': str(locked), 'entry': node['id'] + '.sh', 'code_paths': ['done.txt']}
eng = Engine(g2, repo, work / 'state-g2', {'claude': ['python3', str(stub)]})
r = eng.run()
print('(a) statuses', {k: v['status'] for k, v in eng.j.state['nodes'].items()})
h = json.loads((work / 'state-g2/handoffs/pass2-1.json').read_text())
print('(a) pass2 handoff goal:', repr(h['goal']), '| previous:', h['previous'])
err = (work / 'state-g2/raw/gate1-1.stderr').read_text().strip().splitlines()[-1]
print('(a) gate1 stderr last line:', err, '| present in pass2 handoff?', 'AssertionError' in json.dumps(h))
print('(b) asks raised:', [e['key'] for e in eng.j.events if e['type'] == 'ASK'], '| summary failed =', r['failed'], 'pending =', r['pending'])

# ---- (c) exhausted node: dependents skipped, answer cannot revive ----
repo2 = work / 'dead'; repo2.mkdir()
gd = validate({'name': 'dead-end', 'nodes': [
    {'id': 'build', 'kind': 'code', 'cmd': ['python3', '-c', 'raise SystemExit(1)'], 'artifacts': ['b.txt']},
    {'id': 'deploy', 'kind': 'code', 'cmd': ['python3', '-c', "open('d.txt','w').write('d')"], 'artifacts': ['d.txt']}],
    'edges': [{'from': 'build', 'to': 'deploy'}]})
gfile = repo2 / 'g.json'; gfile.write_text(json.dumps(gd))
base = ['--graph', str(gfile), '--repo', str(repo2), '--state', str(work / 'state-dead')]
def call(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): rc = cli.main(base + list(args))
    return rc, buf.getvalue().strip()[-120:]
print('(c) run 1:', call('run'))
print('(c) answer build --outcome PASS:', call('answer', 'build', 'retry it please', '--outcome', 'PASS'))
print('(c) answer build (default BLOCKED):', call('answer', 'build', 'retry it please'))
print('(c) run 2:', call('run'))
from autoshift.ledger import Journal
st = Journal(work / 'state-dead').state['nodes']
print('(c) final statuses:', {k: v['status'] for k, v in st.items()})
assert h['previous'] == {} and st['deploy']['status'] == 'SKIP' and st['build']['status'] == 'FAIL'
print('P5 REPRODUCED')
