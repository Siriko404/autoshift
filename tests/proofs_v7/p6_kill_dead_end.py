#!/usr/bin/env python3
"""P6: crash of the driver while a node runs.
 (a) The runner child lives in its own session (runner.py start_new_session=True); when only the driver dies
     (OOM kill, closed terminal, SIGKILL) the child keeps running and completes its effect unseen.
 (b) On restart the node is parked BLOCKED (UNCERTAIN + ASK) although its effect is complete.
 (c) No command can unblock it: answer --outcome PASS is refused for non-ask nodes, other answers change nothing,
     there is no retry command; every later run leaves it BLOCKED and its dependents waiting forever.
Usage: python3 -I p6_kill_dead_end.py <path-to-pinned-v4>
Uses bin/autoshift as a real separate driver process; code nodes only; mktemp scratch; no network.
"""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path

V4 = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(V4))
from autoshift.ledger import Journal

work = Path(tempfile.mkdtemp(prefix='p6-')); repo = work / 'repo'; repo.mkdir(); print('scratch', work)
g = {'name': 'crash', 'wip': 1, 'nodes': [
    {'id': 'effect', 'kind': 'code', 'cmd': ['python3', '-c', "import time;time.sleep(1.5);open('effect.txt','w').write('done')"],
     'artifacts': ['effect.txt'], 'timeout': 30},
    {'id': 'next', 'kind': 'code', 'cmd': ['python3', '-c', "open('next.txt','w').write('n')"], 'artifacts': ['next.txt']}],
    'edges': [{'from': 'effect', 'to': 'next'}]}
gf = work / 'g.json'; gf.write_text(json.dumps(g))
base = [str(V4 / 'bin/autoshift'), '--graph', str(gf), '--repo', str(repo), '--state', str(work / 'state')]
def cli(*a):
    p = subprocess.run(base + list(a), capture_output=True, text=True, timeout=60)
    return p.returncode, (p.stdout.strip() or p.stderr.strip())[-100:]
drv = subprocess.Popen(base + ['run'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ev = work / 'state/events.jsonl'
for _ in range(200):
    if ev.exists() and b'"type":"START"' in ev.read_bytes(): break
    time.sleep(0.02)
time.sleep(0.2)
os.kill(drv.pid, signal.SIGKILL); drv.wait()
print('(a) driver killed after START; effect.txt exists right now?', (repo / 'effect.txt').exists())
time.sleep(2.5)
print('(a) 2.5 s later, effect.txt exists?', (repo / 'effect.txt').exists(), '(orphaned runner child finished the effect)')
print('(b) restart run:', cli('run'))
st = Journal(work / 'state').state
print('(b) statuses:', {k: v['status'] for k, v in st['nodes'].items()}, '| open asks:', [k for k, v in st['asks'].items() if v['answer'] is None])
print('(c) answer effect --outcome PASS:', cli('answer', 'effect', 'I checked: effect is complete', '--outcome', 'PASS'))
print('(c) answer effect --outcome FAIL:', cli('answer', 'effect', 'please retry', '--outcome', 'FAIL'))
print('(c) run again:', cli('run'))
print('(c) run again:', cli('run'))
st = Journal(work / 'state').state
print('(c) final statuses:', {k: v['status'] for k, v in st['nodes'].items()}, '| next.txt exists?', (repo / 'next.txt').exists())
print('(c) available subcommands: init run status events replay stop resume view signal answer (no retry/reconcile)')
print('    status line for effect:', [l for l in cli('status')[1].splitlines()][-1:] )
assert st['nodes']['effect']['status'] == 'BLOCKED' and 'next' not in st['nodes'] and (repo / 'effect.txt').exists()
print('P6 REPRODUCED')
