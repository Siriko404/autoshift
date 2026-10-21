"""Conservative path pattern claims, atomic via flock, reap dead owners. K7 [§6 S27,S56]."""
import fcntl
import json
import os
from pathlib import Path
from .graph import overlaps


def alive(pid, birth):
    try:
        raw = Path('/proc/%s/stat'%pid).read_text()
        return raw.rsplit(')',1)[1].split()[19] == str(birth)
    except (OSError, IndexError): return False


def starttime(pid):
    return Path('/proc/%s/stat'%pid).read_text().rsplit(')',1)[1].split()[19]


class Locks:
    def __init__(self, root):
        self.root = Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path = self.root/'locks.json';self.guard = self.root/'locks.guard'

    def change(self, action, owner, patterns=()):
        with self.guard.open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try: reg=json.loads(self.path.read_text())
            except (OSError,ValueError): reg={}
            reg={k:v for k,v in reg.items() if alive(v['pid'],v['birth'])}
            ok = True
            if action == 'claim':
                ok = not any(overlaps(a,b) for k,v in reg.items() if k != owner
                             for a in patterns for b in v['paths'])
                if ok:reg[owner]={'pid':os.getpid(),'birth':starttime(os.getpid()),'paths':list(patterns)}
            elif action == 'release':reg.pop(owner,None)
            else: raise ValueError('bad lock action')
            tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(reg,sort_keys=True));os.replace(tmp,self.path)
            fcntl.flock(f, fcntl.LOCK_UN)
            return ok
