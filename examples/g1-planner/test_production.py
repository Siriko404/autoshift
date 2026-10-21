"""G1 full fake-provider / trusted real gate / actual scratch git worktrees and merges."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from production import Production,validate_plan
from autoshift.ledger import Journal
from autoshift.graph import load
PACKAGE=Path(__file__).resolve().parents[2]
os.environ['AUTOSHIFT_TEST_SANDBOX']='1'

def g(path,*a):
    return subprocess.run(['git','-C',str(path),*a],check=True,capture_output=True,text=True).stdout.strip()

with tempfile.TemporaryDirectory() as d:
    t=Path(d);repo=t/'main';repo.mkdir();(repo/'src').mkdir();(repo/'src/base.txt').write_text('BASE\n')
    g(repo,'init','-q','-b','main');g(repo,'add','.');g(repo,'-c','user.name=Test','-c','user.email=t@t','commit','-qm','base')
    trusted=t/'oracle';trusted.mkdir();(trusted/'acceptance').mkdir()
    (trusted/'gate.sh').write_text((PACKAGE/'examples/locked-gates/g1-project-gate.sh').read_text())
    (trusted/'acceptance/feature.sh').write_text('''#!/bin/bash
set -euo pipefail
test -f "$1/src/$AUTOSHIFT_TASK_ID.txt"
grep -qx OK "$1/src/$AUTOSHIFT_TASK_ID.txt"
''')
    fake=t/'provider.py';fake.write_text('''import json,os,sys
from pathlib import Path
name=Path(sys.argv[1]).name
if name.startswith('g1planner-'):
    run=int(name.split('-')[1].split('.')[0])
    tasks=[{'id':i,'goal':'Create '+i,'lane':'dev','paths':['src/'+i+'.txt'],'class':('plugin' if i=='p1' else 'tooling'),'acceptance':'feature'} for i in ('t1','t2','p1')] if run==1 else []
    if os.environ.get('AUTOSHIFT_TEST_TWO')=='1':tasks=[x for x in tasks if x['id']!='p1']
    Path('plan.json').write_text(json.dumps({'tasks':tasks}))
elif name.startswith('worker.'):
    task=name.split('-')[0].split('.')[1]
    (Path('src')/(task+'.txt')).write_text('OK\\n')
elif name.startswith('audit'):
    Path(os.environ['AUTOSHIFT_VERDICT']).write_text(json.dumps({'verdict':'APPROVE','reason':'independent fake test'}))
print('{}')
''')
    settings={'planner':{'goal':'write plan.json','tiers':[{'provider':'claude','model':'haiku'}]},
        'task_template':{'worker':{'tiers':[{'provider':'claude','model':'haiku'}]},
           'trusted_gate':{'root':str(trusted),'entry':'gate.sh','code_paths':['src']},
           'acceptance':{'feature':'acceptance/feature.sh'},'allowed_paths':['src/**'],'protected_paths':{'plugin':['src/p1.txt'],'wide':['src/core/**']},
           'audits':{'plugin':[{'tiers':[{'provider':'claude','model':'sonnet'}]},{'tiers':[{'provider':'claude','model':'sonnet'}]}]}},
        'queue_min':2,'poll_seconds':.1,'stop':{'completed':3,'max_plans':3}}
    graph={'production':settings,'quota':{'claude':{'usage_pct':0,'limit_pct':80}},'nodes':[{'id':'standin','kind':'wake'}],'edges':[]}
    gpath=t/'graph.json';gpath.write_text(json.dumps(graph));graph=load(gpath)
    assert len(validate_plan({'tasks':[{'id':'a','goal':'x','lane':'l','paths':['src/a.txt'],'class':'tests','acceptance':'feature'}]},settings))==1
    for extra in ('cmd','gate','trusted_gate','audits'):
        try:validate_plan({'tasks':[{'id':'a','goal':'x','lane':'l','paths':['src/a.txt'],'class':'tests','acceptance':'feature',extra:'DO_BYPASS'}]},settings)
        except ValueError:pass
        else:raise AssertionError('planner injected '+extra)
    state=t/'state';overrides={'claude':[sys.executable,str(fake)]}
    e=Production(graph,repo,state,overrides)
    result=e.run(max_ticks=5)
    assert (repo/'src/t1.txt').read_text()=='OK\n',e.j.state['tasks']
    assert (repo/'src/t2.txt').read_text()=='OK\n',e.j.state['tasks']
    assert not (repo/'src/p1.txt').exists(),'plugin merged without approval'
    assert e.j.state['tasks']['p1']['status']=='WAIT_APPROVAL',e.j.state['tasks']
    assert [x['id'] for p in e.j.state['plans'] for x in p['tasks']]==['t1','t2','p1']
    assert any(w['kind']=='queue_low' for w in e.j.state['wakes'])
    assert len(e.j.state['plans'])>1,'planner did not rerun after low queue'
    assert len([x for x in e.j.events if x['type']=='MERGE'])==2
    approved=e.j.state['tasks']['p1']['details'];(state/'approvals').mkdir()
    (state/'approvals/p1.json').write_text(json.dumps({'task':'p1','base':approved['base'],'patch_sha256':'a'*64,'approve':True}))
    e.resume_approvals();assert not (repo/'src/p1.txt').exists(),'wrong digest authorized merge'
    (state/'approvals/p1.json').write_text(json.dumps({'task':'p1','base':approved['base'],'patch_sha256':approved['patch_sha256'],'approve':True}))
    e.resume_approvals();assert (repo/'src/p1.txt').read_text()=='OK\n'
    assert e.j.state['tasks']['p1']['status']=='MERGED'
    assert any(w['kind']=='ask_answered' for w in e.j.state['wakes'])
    assert e.j.diff()==[],'replay diff is not empty'
    assert all(not Path(x['worktree']).is_relative_to(repo) for x in e.j.state['tasks'].values())
    assert len(list((t/'state-worktrees').iterdir()))==3
    # The stop condition is explicit, not an unbounded driver loop.
    assert Production(graph,repo,state,overrides).run()['stopped']
    # Explicit human answer re-arms the planner even when the current queue is not low.
    e2=Production(graph,repo,t/'state2',overrides)
    assert e2.plan()
    assert len(e2.pending())==3
    from run import main
    e2.j.append('ASK','ask:owner_check','owner_check',{'question':'Owner answer needed'})
    assert main(['--graph',str(gpath),'--repo',str(repo),'--state',str(t/'state2'),
                 'answer','owner_check','reviewed','--outcome','BLOCKED'])==0
    e2.run(follow=True,max_ticks=1)
    assert len(e2.j.state['plans'])>=2,'planner did not re-run on human answer'
    assert any(w['kind']=='ask_answered' for w in e2.j.state['wakes'])
    # Exact two-task plan: neither static fanout extras nor a guessed third task runs.
    repo3=t/'two-main';repo3.mkdir();(repo3/'src').mkdir()
    (repo3/'src/base.txt').write_text('BASE\n')
    g(repo3,'init','-q','-b','main');g(repo3,'add','.')
    g(repo3,'-c','user.name=Test','-c','user.email=t@t','commit','-qm','base')
    settings3=json.loads(json.dumps(settings));settings3['stop']['completed']=2
    graph3={'production':settings3,'quota':{'claude':{'usage_pct':0,'limit_pct':80}},
            'nodes':[{'id':'standin','kind':'wake'}],'edges':[]}
    os.environ['AUTOSHIFT_TEST_TWO']='1'
    try:
        e3=Production(graph3,repo3,t/'two-state',overrides)
        completed=e3.run(max_ticks=7)
        assert completed['merged']==2 and completed['stopped'],completed
        assert sorted(e3.j.state['tasks'])==['t1','t2']
        assert len([x for x in e3.j.events if x['type']=='MERGE'])==2
        assert e3.j.diff()==[]
    finally:os.environ.pop('AUTOSHIFT_TEST_TWO',None)
    print('V8_PRODUCTION_OK two_tasks plan_replay locked_gate actual_git_merge plugin_approval wake_stop')
