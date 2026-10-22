"""A host step runs the owner's pinned script outside the sandbox (for tools that bring their own sandbox, e.g. a browser)."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
os.environ['AUTOSHIFT_TEST_SANDBOX']='1';os.environ['AUTOSHIFT_TEST_STATIC_QUOTA']='1'
from autoshift.graph import validate
from autoshift.scheduler import Engine
from autoshift.workspace import run
def git(r,*a):return subprocess.run(['git','-C',str(r),*a],check=True,capture_output=True,text=True).stdout.strip()
def graph(root,args=()):
    return {'nodes':[{'id':'feed','kind':'code','artifacts':['out/made.txt'],'timeout':60,
                      'host':{'root':str(root),'entry':'feed.sh','args':list(args)}},
                     {'id':'check','kind':'gate','cmd':['false'],'artifacts':['.autoshift-gate-output/ok'],
                      'trusted_gate':{'root':'@package','entry':'examples/hello/check.sh','code_paths':['out']}}],
            'edges':[{'from':'feed','to':'check','on':['PASS']}],'wip':1,'merge_on_pass':False}
with tempfile.TemporaryDirectory() as d:
    t=Path(d);trusted=t/'trusted';trusted.mkdir();mark=t/'ran-on-host.txt'
    # The script proves it is NOT in the sandbox (the sandbox sets AUTOSHIFT_SANDBOX=1) and works in the run's copy.
    (trusted/'feed.sh').write_text('set -e\nmkdir -p out\nprintf "%s" "${AUTOSHIFT_SANDBOX:-none}" > '+str(mark)+'\nprintf "made by $1" > out/made.txt\n')
    r=t/'repo';(r/'src').mkdir(parents=True);(r/'src/.keep').write_text('')
    git(r,'init','-q','-b','main');git(r,'add','.');git(r,'-c','user.name=t','-c','user.email=t@t','commit','-qm','base')
    g=graph(trusted,['host-arg'])
    g['nodes'][1]['trusted_gate']['code_paths']=['src']   # the check only needs something to exist; success is judged on feed
    res,msg=run(g,r,t/'s1',Engine,{})
    st=json.loads((t/'s1/state.json').read_text()) if (t/'s1/state.json').exists() else {}
    assert mark.read_text()=='none','host step must run outside the sandbox'
    assert git(r,'show','autoshift/s1:out/made.txt')=='made by host-arg','host step output must land in the run copy'
    assert not (r/'out').exists(),'host step must not write the owner repo'
    # A changed script after it was pinned is refused (the pin is journalled on first start).
    Engine(graph(trusted),r,t/'s2')
    (trusted/'feed.sh').write_text('echo tampered\n')
    try:Engine(graph(trusted),r,t/'s2')
    except ValueError as e:assert 'changed since it was pinned' in str(e),e
    else:raise AssertionError('a changed host script ran')
    # A failing host script fails the step.
    bad=t/'bad';bad.mkdir();(bad/'feed.sh').write_text('exit 7\n')
    res,msg=run(graph(bad),r,t/'s4',Engine,{})
    assert res['failed']>0 and msg.startswith('NOT MERGED'),msg
    # The pinned script must not live under the run's writable copy.
    (r/'tools').mkdir();(r/'tools/feed.sh').write_text('true\n')
    try:Engine(graph(r/'tools'),r,t/'s3')
    except ValueError as e:assert 'trusted source under writable worktree' in str(e),e
    else:raise AssertionError('host script inside the worktree accepted')
    # Validation: host belongs on a code step only, needs an absolute root, and takes no sandbox.
    for node in ({'id':'a','kind':'agent','tiers':[{'provider':'claude','model':'m'}],'host':{'root':str(trusted),'entry':'feed.sh'}},
                 {'id':'a','kind':'code','cmd':['true'],'sandbox':['x'],'host':{'root':str(trusted),'entry':'feed.sh'}},
                 {'id':'a','kind':'code','host':{'root':'relative/dir','entry':'feed.sh'}},
                 {'id':'a','kind':'code','host':{'root':str(trusted),'entry':'../feed.sh'}},
                 {'id':'a','kind':'code','host':'feed.sh'}):
        try:validate({'nodes':[node],'edges':[]})
        except ValueError:pass
        else:raise AssertionError('bad host step accepted: '+repr(node))
print('HOST_OK')
