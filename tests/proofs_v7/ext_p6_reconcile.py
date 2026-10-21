#!/usr/bin/env python3
"""EXTENSION (new, not a copy of an original proof): after the driver crash of P6, `reconcile` settles the node.
Usage: python3 -I ext_p6_reconcile.py <tree>
Scenario 1: reconcile --rerun -> the effect is done and `next` runs. Scenario 2: reconcile --accept -> the node counts as
PASS without re-running and `next` runs. Both journalled; replay clean."""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
T = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(T))
from autoshift.ledger import Journal
def scenario(mode):
    work = Path(tempfile.mkdtemp(prefix='ext-p6-' + mode + '-')); repo = work / 'repo'; repo.mkdir(); print(mode, 'scratch', work)
    g = {'name': 'crash', 'wip': 1, 'nodes': [
        {'id': 'effect', 'kind': 'code', 'cmd': ['python3', '-c', "import time;time.sleep(1.5);open('effect.txt','w').write('done')"],
         'artifacts': ['effect.txt'], 'timeout': 30},
        {'id': 'next', 'kind': 'code', 'cmd': ['python3', '-c', "open('next.txt','w').write('n')"], 'artifacts': ['next.txt']}],
        'edges': [{'from': 'effect', 'to': 'next'}]}
    gf = work / 'g.json'; gf.write_text(json.dumps(g))
    base = [str(T / 'bin/autoshift'), '--graph', str(gf), '--repo', str(repo), '--state', str(work / 'state')]
    def cli(*a):
        p = subprocess.run(base + list(a), capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout.strip() or p.stderr.strip())[-60:]
    drv = subprocess.Popen(base + ['run'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ev = work / 'state/events.jsonl'
    for _ in range(200):
        if ev.exists() and b'"type":"START"' in ev.read_bytes(): break
        time.sleep(0.02)
    time.sleep(0.2); os.kill(drv.pid, signal.SIGKILL); drv.wait(); time.sleep(2.0)
    print(mode, 'restart run:', cli('run')[0], {k: v['status'] for k, v in Journal(work / 'state').state['nodes'].items()})
    assert Journal(work / 'state').state['nodes']['effect']['status'] == 'BLOCKED'
    print(mode, 'reconcile:', cli('reconcile', 'effect', '--' + mode))
    print(mode, 'run:', cli('run'))
    st = {k: v['status'] for k, v in Journal(work / 'state').state['nodes'].items()}
    print(mode, 'final statuses:', st, '| effect.txt:', (repo / 'effect.txt').exists(), '| next.txt:', (repo / 'next.txt').exists())
    assert st == {'effect': 'PASS', 'next': 'PASS'} and (repo / 'next.txt').exists()
    assert (repo / 'effect.txt').exists() == (mode == 'rerun')
    assert Journal(work / 'state').diff() == [] and any(e['type'] == 'RECONCILE' for e in Journal(work / 'state').events)
scenario('rerun'); scenario('accept')
print('EXT P6 RECONCILE OK')
