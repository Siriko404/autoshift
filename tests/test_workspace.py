"""Each run works in its own git copy; the owner's files change only when every step passed and merge is on."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
os.environ['AUTOSHIFT_TEST_SANDBOX']='1';os.environ['AUTOSHIFT_TEST_STATIC_QUOTA']='1'
from autoshift.scheduler import Engine
from autoshift.workspace import run
def git(r,*a):return subprocess.run(['git','-C',str(r),*a],check=True,capture_output=True,text=True).stdout.strip()
def graph(merge):
    return {'nodes':[{'id':'write','kind':'agent','role':'worker','goal':'write src/hello.txt',
                      'tiers':[{'provider':'claude','model':'haiku'}],'sandbox':[str(P/'tests/stub-sandbox.sh')],'max_attempts':1},
                     {'id':'check','kind':'gate','cmd':['false'],'artifacts':['.autoshift-gate-output/hello.ok'],
                      'trusted_gate':{'root':'@package','entry':'examples/hello/check.sh','code_paths':['src']}}],
            'edges':[{'from':'write','to':'check','on':['PASS']}],'wip':1,'merge_on_pass':merge,
            'quota':{'claude':{'usage_pct':0,'limit_pct':80}}}
with tempfile.TemporaryDirectory() as d:
    t=Path(d);fake=t/'agent.py'
    fake.write_text("import os;from pathlib import Path;Path('src/hello.txt').write_text(os.environ['TEXT']+'\\n');print('{}')\n")
    over={'claude':[sys.executable,str(fake)]}
    def repo(name):
        r=t/name;(r/'src').mkdir(parents=True);(r/'src/.keep').write_text('')
        git(r,'init','-q','-b','main');git(r,'add','.');git(r,'-c','user.name=t','-c','user.email=t@t','commit','-qm','base')
        return r
    # 1. The check fails: the owner's repo is untouched, the work stays on its branch.
    os.environ['TEXT']='goodbye';r=repo('r1');head=git(r,'rev-parse','HEAD')
    res,msg=run(graph(True),r,t/'s1',Engine,over)
    assert res['failed']>0 and msg.startswith('NOT MERGED'),msg
    assert not (r/'src/hello.txt').exists() and git(r,'rev-parse','HEAD')==head,'failed work reached the owner'
    assert git(r,'show','autoshift/s1:src/hello.txt')=='goodbye','failed work must stay on its branch'
    # 2. All pass but merge is off: still untouched.
    os.environ['TEXT']='hello from autoshift';r=repo('r2');head=git(r,'rev-parse','HEAD')
    res,msg=run(graph(False),r,t/'s2',Engine,over)
    assert res['failed']==0 and 'not merged' in msg and not (r/'src/hello.txt').exists() and git(r,'rev-parse','HEAD')==head,msg
    # 3. All pass and merge is on: the owner's branch gets the change.
    r=repo('r3');res,msg=run(graph(True),r,t/'s3',Engine,over)
    assert msg=='ALL PASSED and merged into your branch',msg
    assert (r/'src/hello.txt').read_text()=='hello from autoshift\n'
    # 4. The owner's branch moved during the run: no merge.
    from autoshift.workspace import prepare
    r=repo('r4');prepare(r,t/'s4');(r/'other.txt').write_text('x');git(r,'add','.');git(r,'-c','user.name=t','-c','user.email=t@t','commit','-qm','owner')
    res,msg=run(graph(True),r,t/'s4',Engine,over)
    assert 'moved' in msg and not (r/'src/hello.txt').exists(),msg
    # 5. Uncommitted owner changes and a subfolder --repo are refused before anything runs.
    r=repo('r5');(r/'src/dirty.txt').write_text('x')
    for bad_repo,state in ((r,t/'s5'),(repo('r6')/'src',t/'s6')):
        try:run(graph(True),bad_repo,state,Engine,over)
        except ValueError:pass
        else:raise AssertionError('refusal expected for '+str(bad_repo))
    assert not (t/'s5-work').exists() and not (t/'s6-work').exists()
print('WORKSPACE_OK')
