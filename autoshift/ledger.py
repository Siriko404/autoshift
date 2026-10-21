"""Append-only, hash-chained journal and atomic materialization. K3 K9 [§10 S44 S56]."""
import fcntl
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path


def canonical(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(',',':')).encode()


def reducer(events):
    s = {'nodes': {}, 'stopped': False, 'quota': {}, 'signals': [], 'asks': {}, 'events': [], 'keys': [], 'feedback': [], 'graph_sha256': None, 'revisions': [], 'pins': {}, 'plans': [], 'tasks': {}, 'wakes': []}
    seen = set()
    for e in events:
        if e['key'] in seen:
            continue
        seen.add(e['key'])
        kind, n, d = e['type'],e.get('node'),e.get('data', {})
        if kind == 'GRAPH':
            if d.get('prior'):
                s['nodes']={};s['asks']={};s['pins']={}  # explicit revision invalidates earlier graph node verdicts and gate pins
            s['graph_sha256'] = d['sha256'];s['revisions'].append(d)
        elif kind == 'PIN':s['pins'][n]=d['sha256']
        elif kind == 'PLAN':
            s['plans'].append(d)
            for task in d['tasks']:
                s['tasks'][task['id']]={'task':task,'status':'QUEUED','stage':'QUEUED','details':{},'worktree':None}
        elif kind == 'TASK':
            if n in s['tasks']:
                st=s['tasks'][n];st.update(stage=d['stage'],details=d,status=('MERGED' if d['stage']=='MERGED' else 'WAIT_APPROVAL' if d['stage']=='WAIT_APPROVAL' else 'FAIL' if d['status']=='FAIL' else st['status']))
                if d['stage']=='WORKTREE':st['worktree']=d['path']
        elif kind == 'WAKE':s['wakes'].append(d)
        elif kind == 'START':
            previous = s['nodes'].get(n, {})
            s['nodes'][n] = {'status':'RUNNING','attempt':d['attempt'],'tier':d.get('tier'),
                             'handoff': d.get('handoff'), 'history':previous.get('history', []),
                             'previous_evidence':previous.get('evidence')}
        elif kind == 'RESULT':
            s['nodes'][n].update({'status':d['status'],'evidence':d,'failure_signature':d.get('signature')})
            s['nodes'][n].setdefault('history', []).append({'signature':d.get('signature'),'tier':s['nodes'][n].get('tier'), 'status':d['status']})
        elif kind == 'RETRY':
            s['nodes'][n]['status'] = 'RETRY'
            s['nodes'][n]['tier'] = d.get('tier')
            if d.get('gate_error') is not None:s['nodes'][n]['retry_feedback'] = {'signature':d.get('gate_signature'), 'stderr_tail':d['gate_error']}
        elif kind == 'SKIP':
            s['nodes'][n] = {'status':'SKIP'}
        elif kind == 'RECONCILE':
            if n in s['nodes']:
                s['nodes'][n]['status'] = 'PASS' if d['action']=='accept' else 'RETRY'
                s['nodes'][n]['reason'] = 'reconciled:'+d['action']
            if n in s['asks'] and s['asks'][n]['answer'] is None:s['asks'][n]['answer']='reconciled:'+d['action']
        elif kind == 'UNCERTAIN':
            s['nodes'][n]['status'] = 'BLOCKED'
            s['nodes'][n]['reason'] = d.get('reason','lost runner; manual reconcile')
        elif kind == 'STOP': s['stopped'] = True
        elif kind == 'RESUME': s['stopped'] = False
        elif kind == 'QUOTA': s['quota'] = d
        elif kind == 'SIGNAL': s['signals'].append(d['name'])
        elif kind == 'ASK': s['asks'][n] = {'question': d.get('question',''), 'answer': None}
        elif kind == 'FEEDBACK':s['feedback'].append(d)
        elif kind == 'ANSWER':
            s['asks'][n]['answer'] = d['answer']
            if n in s['nodes']:
                s['nodes'][n]['status'] = ('RETRY' if d.get('retry') else d.get('outcome','BLOCKED'))
        s['events'].append({'seq':e['seq'],'type':kind,'node':n})
    s['keys'] = sorted(seen)
    return s


def write_atomic(path, raw):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.state-')
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(name): os.unlink(name)


class Journal:
    def __init__(self, directory, read_only=False):
        self.root = Path(directory)
        if not read_only:self.root.mkdir(parents=True, exist_ok=True)
        self.file = self.root/'events.jsonl'; self.snapshot = self.root/'state.json'
        self.mu = threading.RLock()
        self.events = self.read()
        self.state = reducer(self.events)
        if not read_only and not self.snapshot.exists():
            with (self.root/'journal.guard').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                self.events=self.read(); self.state=reducer(self.events)
                if not self.snapshot.exists():self.materialize()

    def read(self, repair=False):
        if not self.file.exists(): return []
        events, prev = [], '0'*64
        raw = self.file.read_bytes()
        for line in raw.split(b'\n'):
            if not line: continue
            try: e = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                if line != raw.split(b'\n')[-1]:
                    raise ValueError('corrupt journal in middle')
                break  # incomplete final append; only a complete fsync event commits
            if e['seq'] != len(events)+1 or e['previous'] != prev:
                raise ValueError('journal continuity failure')
            digest = hashlib.sha256(canonical({k:v for k,v in e.items() if k != 'hash'})).hexdigest()
            if e['hash'] != digest:
                raise ValueError('journal hash mismatch')
            events.append(e); prev=e['hash']
        if repair and raw and not raw.endswith(b'\n'):
            # Truncate only an incomplete final write; preserve complete valid entries.
            with self.file.open('r+b') as f:
                last = raw.rfind(b'\n')
                if events and len(events) == len([x for x in raw.split(b'\n') if x]):
                    f.seek(0, os.SEEK_END); f.write(b'\n')
                else:
                    f.truncate(last + 1)
                f.flush(); os.fsync(f.fileno())
        return events

    def refresh(self):
        with self.mu:
            latest=self.read()
            if len(latest) != len(self.events):
                self.events=latest;self.state=reducer(self.events)

    def materialize(self):
        write_atomic(self.snapshot, canonical(self.state)+b'\n')

    def append(self, kind, key, node=None, data=None, require_running=False):
        with self.mu, (self.root/'journal.guard').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self.events=self.read(repair=True);self.state=reducer(self.events)  # under journal.guard
            if require_running and self.state['stopped']:
                return False
            if key in self.state['keys']:
                return False
            e = {'seq':len(self.events)+1, 'previous':self.events[-1]['hash'] if self.events else '0'*64,
                 'type':kind,'key':key,'node':node,'data':data or {}}
            e['hash'] = hashlib.sha256(canonical(e)).hexdigest()
            with self.file.open('ab') as f:
                f.write(canonical(e)+b'\n');f.flush();os.fsync(f.fileno())
            self.events.append(e);self.state = reducer(self.events);self.materialize()
            return True

    def diff(self):
        with self.mu:
            expected = reducer(self.read())
            try: actual = json.loads(self.snapshot.read_text())
            except (OSError, ValueError): return ['state missing or invalid']
            return [] if expected == actual else ['snapshot differs from replay']
