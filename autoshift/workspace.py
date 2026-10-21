"""Each run works in its own git copy; the owner's checkout changes only when every step passed.

The copy is a git worktree on branch autoshift/<state name>, next to the state directory, made from the owner's
committed HEAD. Agents and checks see only the copy. At the end the copy's changes are committed on that branch.
The owner's branch is fast-forwarded only if every step passed, the graph says "merge_on_pass": true, and the
owner's branch has not moved and has no uncommitted changes. Otherwise nothing of the owner's changes.
"""
import json
import subprocess
from pathlib import Path
from .ledger import write_atomic


def git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null', *args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError('git ' + args[0] + ' failed: ' + p.stderr.strip()[-300:])
    return p.stdout.strip()


def git_top(repo):
    p = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    return Path(p.stdout.strip()).resolve() if p.returncode == 0 else None


def prepare(repo, state):
    repo, state = Path(repo).resolve(), Path(state).resolve()
    record = state / 'workspace.json'
    if record.exists():
        return json.loads(record.read_text())
    if git(repo, 'status', '--porcelain'):
        raise ValueError('the repo has uncommitted changes: commit or stash them first')
    base = git(repo, 'rev-parse', 'HEAD')
    path = state.parent / (state.name + '-work')
    if path.is_relative_to(repo):
        raise ValueError('the work copy would be inside the repo: put --state outside it')
    branch = 'autoshift/' + state.name
    git(repo, 'worktree', 'add', '-q', '-b', branch, str(path), base)
    ws = {'repo': str(repo), 'path': str(path), 'branch': branch, 'base': base}
    state.mkdir(parents=True, exist_ok=True)
    write_atomic(record, (json.dumps(ws, sort_keys=True) + '\n').encode())
    return ws


def finish(ws, result, merge):
    path = ws['path']
    if git(path, 'status', '--porcelain'):
        git(path, 'add', '-A')
        git(path, '-c', 'user.name=AutoShift', '-c', 'user.email=autoshift@localhost', 'commit', '-q', '-m',
            'AutoShift run on ' + ws['branch'])
    if result.get('failed') != 0 or result.get('pending') != 0:
        return 'NOT MERGED: a step failed or waits. Your files are unchanged; the work is on branch ' + ws['branch']
    if not merge:
        return 'ALL PASSED, not merged (merge_on_pass is off). The work is on branch ' + ws['branch']
    repo = ws['repo']
    if git(repo, 'rev-parse', 'HEAD') != ws['base'] or git(repo, 'status', '--porcelain'):
        return 'ALL PASSED, not merged: your branch moved or has uncommitted changes. The work is on branch ' + ws['branch']
    git(repo, 'merge', '--ff-only', '-q', ws['branch'])
    return 'ALL PASSED and merged into your branch'


def run(graph, repo, state, engine_class, overrides=None):
    """Runs the graph in its own copy when --repo is a git repository's top folder."""
    top = git_top(repo)
    if top is None:
        engine = engine_class(graph, repo, state, overrides) if overrides else engine_class(graph, repo, state)
        return engine.run(), 'NOTE: --repo is not a git repository, so steps ran in it directly'
    if top != Path(repo).resolve():
        raise ValueError('point --repo at the top folder of the git repository: ' + str(top))
    ws = prepare(repo, state)
    engine = engine_class(graph, ws['path'], state, overrides) if overrides else engine_class(graph, ws['path'], state)
    result = engine.run()
    return result, finish(ws, result, graph.get('merge_on_pass') is True)
