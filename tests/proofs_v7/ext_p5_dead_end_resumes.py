#!/usr/bin/env python3
"""EXTENSION (new, not a copy of an original proof): the P5 dead end must RESUME after an answer.
Usage: python3 -I ext_p5_dead_end_resumes.py <tree>
Graph build -> deploy. build fails on its first run and succeeds on its second. While the ask is open deploy must WAIT
(not SKIP); free text must not retry; `answer --retry` must re-run build; deploy then runs; exit code 0."""
import contextlib, io, json, sys, tempfile
from pathlib import Path
T = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(T))
from autoshift import cli
from autoshift.ledger import Journal
work = Path(tempfile.mkdtemp(prefix='ext-p5-')); print('scratch', work)
repo = work / 'repo'; repo.mkdir()
g = {'name': 'dead-end', 'nodes': [
    {'id': 'build', 'kind': 'code', 'cmd': ['python3', '-c',
        "import os,sys;ok=os.path.exists('marker');open('marker','w').write('x');sys.exit(0 if ok else 1)"],
     'artifacts': ['marker']},
    {'id': 'deploy', 'kind': 'code', 'cmd': ['python3', '-c', "open('d.txt','w').write('d')"], 'artifacts': ['d.txt']}],
    'edges': [{'from': 'build', 'to': 'deploy'}]}
gfile = work / 'g.json'; gfile.write_text(json.dumps(g))
base = ['--graph', str(gfile), '--repo', str(repo), '--state', str(work / 'state')]
def call(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): rc = cli.main(base + list(a))
    return rc, buf.getvalue().strip()[-60:]
def nodes(): return {k: v['status'] for k, v in Journal(work / 'state').state['nodes'].items()}
def open_asks(): return [k for k, v in Journal(work / 'state').state['asks'].items() if v['answer'] is None]
print('run 1:', call('run')[0], nodes(), 'open asks', open_asks())
assert nodes() == {'build': 'FAIL'} and open_asks() == ['build'], 'deploy must WAIT (absent), not SKIP, while the ask is open'
print('answer with free text only:', call('answer', 'build', 'please retry it'))
print('after free text:', nodes())
assert nodes()['build'] != 'RETRY', 'free text must not start a retry'
print('answer --retry:', call('answer', 'build', 'retry now', '--retry'))
print('run 2:', call('run')[0], nodes(), 'open asks', open_asks())
assert nodes() == {'build': 'PASS', 'deploy': 'PASS'} and open_asks() == [] and (repo / 'd.txt').exists()
assert Journal(work / 'state').diff() == []
print('EXT P5 RESUMES')
