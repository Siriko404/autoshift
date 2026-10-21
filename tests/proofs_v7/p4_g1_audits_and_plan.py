#!/usr/bin/env python3
"""P4: shipped G1 graph with stub agents.
 (a) an auditor that REJECTS the change (prose) but exits 0 is recorded PASS; downstream continues;
 (b) the planner's plan.json is never read: the fanout runs its fixed items whatever the plan says;
 (c) what an auditor is given: its handoff has no diff, no spec, no worker evidence;
 (d) where G1 ends with the shipped merge_check placeholder.
Usage: python3 -I p4_g1_audits_and_plan.py <path-to-pinned-v4>
Project commands (prepare, gate) are replaced by stubs that write their artifact, exactly as tests/test_scheduler.py
does; merge_check is left as shipped. Sandbox -> tests/stub-sandbox.sh; quota -> test readings. No network.
"""
import json, sys, tempfile
from pathlib import Path

V4 = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(V4))
from autoshift.graph import load
from autoshift.scheduler import Engine
import os
# ---- v7 SETUP: test switches for the stub quota and the stub sandbox (the script replaces every agent sandbox by the stub) ----
os.environ['AUTOSHIFT_TEST_STATIC_QUOTA'] = '1'
os.environ['AUTOSHIFT_TEST_SANDBOX'] = '1'

work = Path(tempfile.mkdtemp(prefix='p4-')); repo = work / 'repo'; repo.mkdir()
print('scratch', work)
honest = repo / 'stub_claude.py'
honest.write_text(
    "import json,sys\nfrom pathlib import Path\nh=json.loads(Path(sys.argv[1]).read_text())\n"
    "if 'plan file' in h['goal']:\n"
    "    Path('plan.json').write_text(json.dumps({'current':[{'id':'only-task','lane':'docs'}],'tentative':[]}))\n"
    "print(json.dumps({'claims':['done']}))\n")
rejecter = repo / 'stub_codex_auditor.py'
rejecter.write_text("import json\nprint(json.dumps({'claims':['REJECT: plugin change breaks the protocol; do not merge']}))\n")
g = load(V4 / 'examples/g1-production.json')
g['quota'] = {p: {'usage_pct': 0, 'limit_pct': 80} for p in ('claude', 'codex')}
for n in g['nodes']:
    if n['kind'] == 'agent':
        n['sandbox'] = [str(V4 / 'tests/stub-sandbox.sh')]
        if n['id'] == 'planner':
            pass
        else:
            n['artifacts'] = []
    if n['id'] in ('prepare', 'gate'):
        n['cmd'] = ['python3', '-c', 'from pathlib import Path;Path(%r).write_text("ok")' % n['artifacts'][0]]
# ---- v7 SETUP: G1's shipped gate is intentionally unwired; give it a locked stand-in that writes gate.ok ----
trusted = work / 'trusted-g1'; trusted.mkdir()
(trusted / 'gate.sh').write_text('#!/bin/sh\nprintf ok > gate.ok\n')
for node in g['nodes']:
    if node['id'] == 'gate': node['trusted_gate'] = {'root': str(trusted), 'entry': 'gate.sh'}
eng = Engine(g, repo, work / 'state', {'claude': ['python3', str(honest)], 'codex': ['python3', str(rejecter)]})
r = eng.run()
st = eng.j.state['nodes']
print('plan.json written by planner:', (repo / 'plan.json').read_text())
print('fanout children that ran:', sorted(k for k in st if k.startswith('workers.item')  and '.audit.' not in k))
for k in sorted(st):
    if '.audit.' in k:
        print('auditor', k, '->', st[k]['status'], '| claims:', st[k]['evidence']['claims'])
print('downstream:', {k: st.get(k, {}).get('status') for k in ('join_workers', 'prepare', 'gate', 'merge_check', 'merge')})
h = json.loads((work / 'state/handoffs/workers.item0.audit.plugin.1-1.json').read_text())
print('auditor handoff keys:', sorted(h), '| goal:', repr(h['goal']), '| files:', h['files'], '| previous:', h['previous'])
print('open asks:', [k for k, v in eng.j.state['asks'].items() if v['answer'] is None])
print('summary failed/pending:', r['failed'], r['pending'])
assert st['workers.item0.audit.plugin.1']['status'] == 'PASS'
print('P4 REPRODUCED')
