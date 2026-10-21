"""v7 real-bwrap regressions: C02 C03 C04 (locked gate sees only code under test), C01/C27 (worker cannot reach the
journal or validators), C07 (auditor sandbox: read-only repo, writable verdict directory only).
The test-only stub is switched OFF here; a stub can never satisfy this file."""
import hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
base=Path(__file__).resolve().parents[1]
if not shutil.which('bwrap'):
    print('SKIP_NEEDS_BWRAP');raise SystemExit(77)
sys.path.insert(0,str(base))
from autoshift.graph import validate
from autoshift.scheduler import Engine
os.environ.pop('AUTOSHIFT_TEST_SANDBOX',None)
os.environ['AUTOSHIFT_TEST_STATIC_QUOTA']='1'
SB=str(base/'adapters/sandbox.sh')
Q={'claude':{'usage_pct':0,'limit_pct':80}}


def tree_hash(root):
    h=hashlib.sha256()
    for p in sorted(Path(root).rglob('*')):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():h.update(p.read_bytes())
    return h.hexdigest()


with tempfile.TemporaryDirectory() as d:
    t=Path(d)
    # ---- C02/C03: a project-style gate. Validators come from the trusted root; the worker's copies are invisible.
    repo=t/'repo';(repo/'tests').mkdir(parents=True);(repo/'tools').mkdir();(repo/'harness').mkdir();(repo/'.git').mkdir()
    (repo/'calc.py').write_text('def add(a, b):\n    return a - b   # bug\n')
    (repo/'tests/test_calc.py').write_text('print("POISONED tests pass")\n')
    (repo/'tools/gate.sh').write_text('touch "$AUTOSHIFT_GATE_OUT/gate.ok"\n')
    (repo/'harness/test_x.sh').write_text('exit 0\n')
    trusted=t/'trusted';(trusted/'oracle').mkdir(parents=True)
    (trusted/'oracle/test_calc.py').write_text('import sys\nsys.path.insert(0,".")\nfrom calc import add\nassert add(2, 2) == 4, "add(2,2) != 4"\n')
    (trusted/'gate.sh').write_text('''#!/bin/bash
set -u
for p in tests tools harness .git; do [ ! -e "$p" ] || { echo "VALIDATOR_VISIBLE $p" >&2; exit 9; }; done
if touch calc.py 2>/dev/null; then echo CODE_WRITABLE >&2; exit 9; fi
if (echo x > "$(dirname "$0")/planted") 2>/dev/null; then echo TRUSTED_ROOT_WRITABLE >&2; exit 9; fi
python3 "$(dirname "$0")/oracle/test_calc.py" || exit 1
printf ok > "$AUTOSHIFT_GATE_OUT/gate.ok"
''')
    def gate_graph():
        return validate({'nodes':[{'id':'gate','kind':'gate','cmd':['bash','tools/gate.sh'],'artifacts':['.autoshift-gate-output/gate.ok'],
            'trusted_gate':{'root':str(trusted),'entry':'gate.sh','code_paths':['calc.py']}}]})
    before=tree_hash(repo)
    e=Engine(gate_graph(),repo,t/'state-bug');r=e.run()
    ev=e.j.state['nodes']['gate']['evidence']
    assert e.j.state['nodes']['gate']['status']=='FAIL' and ev['rc']==1 and 'add(2,2) != 4' in ev['stderr_tail'],ev
    assert not (t/'state-bug/.autoshift-gate-output/gate.ok').exists()
    assert tree_hash(repo)==before and not (repo/'.autoshift-gate-output').exists() and not (trusted/'planted').exists()
    (repo/'calc.py').write_text('def add(a, b):\n    return a + b\n')
    before=tree_hash(repo)
    e=Engine(gate_graph(),repo,t/'state-fixed');r=e.run()
    assert r['passed']==1 and tree_hash(repo)==before,(r,e.j.state['nodes']['gate'].get('evidence'))
    print('V7_GATE_VALIDATORS_LOCKED_OK')

    # ---- C01/C27/C15: a worker in the real sandbox writes only its declared bind and cannot reach state or validators.
    repo=t/'repo2';(repo/'src').mkdir(parents=True);(repo/'tools').mkdir()
    (repo/'tools/gate.sh').write_text('ORIGINAL\n')
    attack=t/'attack.py'
    attack.write_text('''import json,os,sys
from pathlib import Path
res={}
def attempt(name,path):
    try:Path(path).write_text("owned");res[name]="WROTE"
    except OSError as e:res[name]=type(e).__name__
attempt("declared",Path("src/ok.txt"))
attempt("gate_script",%r)
attempt("journal",%r)
attempt("state_dir_new",%r)
attempt("parent_escape","../escaped.txt")
res["home_entries"]=len(os.listdir(os.path.expanduser("~")))
Path("src/result.json").write_text(json.dumps(res))
print("{}")
''' % (str(repo/'tools/gate.sh'),str(t/'state-w/events.jsonl'),str(t/'state-w/forged'),))
    wg=validate({'quota':Q,'nodes':[{'id':'worker','kind':'agent','role':'worker','tiers':[{'provider':'claude','model':'m'}],'max_attempts':1,
        'sandbox':[SB,'--rw','src','--ro',str(attack),'--net','0']}]})
    e=Engine(wg,repo,t/'state-w',{'claude':[sys.executable,str(attack)]});e.run()
    assert e.j.state['nodes']['worker']['status']=='PASS',e.j.state['nodes']['worker'].get('evidence')
    res=json.loads((repo/'src/result.json').read_text())
    assert res['declared']=='WROTE' and (repo/'src/ok.txt').read_text()=='owned',res
    # Writes to paths that are not binds may land in the sandbox's private tmpfs; only the HOST state counts.
    assert res['gate_script']=='FileNotFoundError',res   # tools/ does not even exist in the worker's view
    assert (repo/'tools/gate.sh').read_text()=='ORIGINAL\n' and not (t/'state-w/forged').exists()
    assert not (t/'escaped.txt').exists() and not (repo/'escaped.txt').exists() and sorted(p.name for p in repo.iterdir())==['src','tools']
    assert b'owned' not in (t/'state-w/events.jsonl').read_bytes() and e.j.diff()==[] and res['home_entries']==0,res
    assert sorted(p.name for p in (repo/'src').iterdir())==['ok.txt','result.json']
    print('V7_WORKER_BOUNDS_OK',json.dumps(res,sort_keys=True))

    # ---- C07: auditor in the real sandbox: repo read-only, handoff readable, verdict directory writable, code reads the file.
    repo=t/'repo3';repo.mkdir();(repo/'f.txt').write_text('x')
    aud=t/'auditor.py'
    aud.write_text('''import json,os
from pathlib import Path
h=json.loads(Path(os.environ["AUTOSHIFT_HANDOFF"]).read_text())
try:Path("planted.txt").write_text("x");ro=False
except OSError:ro=True
Path(os.environ["AUTOSHIFT_VERDICT"]).write_text(json.dumps({"verdict":os.environ.get("DECISION","REJECT"),"reason":"ro=%s keys=%s"%(ro,sorted(h["audit_contract"]))}))
print("APPROVE: prose that must be ignored")
''')
    for decision,expected in (('REJECT','FAIL'),('APPROVE','PASS')):
        os.environ['DECISION']=decision
        ag=validate({'quota':Q,'nodes':[{'id':'auditor','kind':'agent','role':'audit','tiers':[{'provider':'claude','model':'m'}],
            'sandbox':[SB,'--ro','.','--ro',str(aud),'--net','0','--env','DECISION']}]})
        e=Engine(ag,repo,t/('state-a-'+decision),{'claude':[sys.executable,str(aud)]});e.run()
        node=e.j.state['nodes']['auditor']
        assert node['status']==expected,(decision,node.get('evidence'))
        saved=json.loads((t/('state-a-'+decision)/'audits/auditor-1.json').read_text())
        assert saved['verdict']==decision and 'ro=True' in saved['reason'] and 'verdict_file' in saved['reason'],saved
        assert not (repo/'planted.txt').exists()
    print('V7_AUDITOR_SANDBOX_OK')
print('V7_BWRAP_OK')
