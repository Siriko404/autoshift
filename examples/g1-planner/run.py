#!/usr/bin/env python3
"""Runs the example planner flow (production.py) on the kernel. Not part of the kernel.

  python3 examples/g1-planner/run.py --graph G --repo R --state S run [--follow]
  python3 examples/g1-planner/run.py --graph G --repo R --state S status
  python3 examples/g1-planner/run.py --graph G --repo R --state S answer NODE TEXT [--outcome ...]
Every other command is the kernel's own: bin/autoshift.
"""
import argparse
import fcntl
import json
import sys
import uuid
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from production import Production, PACKAGE  # noqa: E402
from autoshift.graph import load  # noqa: E402
from autoshift.ledger import Journal  # noqa: E402
from autoshift import cli as kernel_cli  # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog='g1-planner')
    p.add_argument('--graph', required=True)
    p.add_argument('--repo', default='.')
    p.add_argument('--state', required=True)
    p.add_argument('cmd')
    p.add_argument('rest', nargs=argparse.REMAINDER)
    a = p.parse_args(argv)
    g = load(a.graph)
    root = Path(a.state)
    if a.cmd == 'run':
        follow = '--follow' in a.rest
        root.mkdir(parents=True, exist_ok=True)
        with (root / 'driver.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print('BLOCKED: another driver is active'); return 3
            result = Production(g, a.repo, root).run(follow=follow)
            print(json.dumps(result, sort_keys=True))
            return 0 if result['failed'] == 0 and result['pending'] == 0 else 3
    if a.cmd == 'status':
        j = Journal(root, read_only=True)
        tasks = j.state.get('tasks', {})
        print('G1 PLANNER  stopped=' + str(j.state['stopped']) + ' plans=' + str(len(j.state.get('plans', []))))
        for tid, t in tasks.items():
            print('  ' + tid + ' [' + t['status'] + '] ' + t['stage'] + ' class=' + t['task']['class'] +
                  ' lane=' + t['task']['lane'])
        print('QUEUE: ' + ', '.join(k for k, t in tasks.items() if t['status'] == 'QUEUED'))
        print('ASKS: ' + ', '.join(k for k, t in j.state['asks'].items() if t['answer'] is None))
        return 0
    rc = kernel_cli.main(argv)
    if a.cmd == 'answer' and rc == 0:
        # An answered ask wakes the planner.
        Journal(root).append('WAKE', 'wake:answer:' + a.rest[0] + ':' + uuid.uuid4().hex,
                             data={'kind': 'ask_answered', 'detail': a.rest[0]})
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
