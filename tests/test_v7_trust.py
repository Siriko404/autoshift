"""v7 trust regressions (stub sandbox, no bwrap needed): C06 C07 C10 C14 C15 C20 and the per-attempt ask key.
Every block fails if the fix it names is removed."""
import contextlib,io,json,os,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate
from autoshift.scheduler import Engine
from autoshift.ledger import Journal
from autoshift import cli
base=Path(__file__).resolve().parents[1]
STUB=str(base/'tests/stub-sandbox.sh')
Q={'claude':{'usage_pct':0,'limit_pct':80}}


def cli_call(graph_file,repo,state,*args):
    out=io.StringIO()
    with contextlib.redirect_stdout(out):rc=cli.main(['--graph',str(graph_file),'--repo',str(repo),'--state',str(state),*args])
    return rc,out.getvalue().strip()


with tempfile.TemporaryDirectory() as d:
    t=Path(d)
    ok_gate=t/'trusted-ok';ok_gate.mkdir()
    (ok_gate/'gate.sh').write_text('#!/bin/bash\nprintf ok > "$AUTOSHIFT_GATE_OUT/gate.ok"\n')
    worker_py=t/'worker.py';worker_py.write_text('print("{}")\n')

    def audit_graph(workers=1):
        ws=[{'id':'w%d'%i,'kind':'agent','role':'worker','lane':'w%d'%i,'cwd':'w%d'%i,'paths':['src/plugins/p%d/**'%i],
             'tiers':[{'provider':'claude','model':'stub'}],'sandbox':[STUB],'max_attempts':1} for i in range(workers)]
        return validate({'wip':2,'quota':Q,'nodes':ws+[
            {'id':'gate','kind':'gate','cmd':['false'],'artifacts':['.autoshift-gate-output/gate.ok'],
             'trusted_gate':{'root':str(ok_gate),'entry':'gate.sh'}},
            {'id':'merge','kind':'code','cmd':['python3','-c',"open('merged.txt','w').write('m')"],'artifacts':['merged.txt']}],
            'edges':[{'from':w['id'],'to':'gate'} for w in ws]+[{'from':'gate','to':'merge'}],
            'audit_policy':[{'id':'plug','patterns':['src/plugins/**'],
                             'auditors':[{'goal':'audit','tiers':[{'provider':'claude','model':'stub'}],'sandbox':[STUB]}]}]})

    def launcher_for(tag,auditor_body):
        # One provider command: auditors (they get AUTOSHIFT_VERDICT) run auditor_body, workers do nothing.
        script=t/(tag+'-aud.py')
        script.write_text('import json,os,sys\nfrom pathlib import Path\nh=json.loads(Path(sys.argv[1]).read_text())\nv=os.environ["AUTOSHIFT_VERDICT"]\n'+auditor_body)
        launcher=t/(tag+'-launch.py')
        launcher.write_text('import os,subprocess,sys\nsys.exit(subprocess.call([sys.executable,%r if "AUTOSHIFT_VERDICT" in os.environ else %r]+sys.argv[1:]))\n'%(str(script),str(worker_py)))
        return {'claude':[sys.executable,str(launcher)]}

    def run_audit(tag,body,workers=1,graph=None,repo=None):
        repo=repo or t/('repo-'+tag)
        repo.mkdir(exist_ok=True)
        for i in range(workers):(repo/('w%d'%i)).mkdir(exist_ok=True)
        e=Engine(graph or audit_graph(workers),repo,t/('state-'+tag),launcher_for(tag,body));e.run()
        return e,repo

    def auditors(e):return sorted(k for k in e.j.state['nodes'] if '.audit.' in k)

    # C07: REJECT in the verdict file stops the merge path, runs after the gate, and is kept in audits/.
    e,repo=run_audit('reject','Path(v).write_text(json.dumps({"verdict":"REJECT","reason":"unsafe"}))\nprint("APPROVE: looks good")\n')
    nodes=e.j.state['nodes'];aud=auditors(e)[0]
    assert nodes['gate']['status']=='PASS' and nodes[aud]['status']=='FAIL',nodes
    assert 'merge' not in nodes and not (repo/'merged.txt').exists(),'REJECT did not stop the merge path'
    assert json.loads((t/'state-reject/audits'/(aud+'-1.json')).read_text())['verdict']=='REJECT'
    seq={(x['type'],x['node']):x['seq'] for x in e.j.events if x['type'] in('START','RESULT')}
    assert seq[('RESULT','gate')]<seq[('START',aud)],'auditor must run after the gate'
    # C07: APPROVE in the verdict file lets the merge path continue.
    e,repo=run_audit('approve','Path(v).write_text(json.dumps({"verdict":"APPROVE","reason":"ok"}))\n')
    assert e.j.state['nodes']['merge']['status']=='PASS' and (repo/'merged.txt').exists()
    # C07: prose on stdout with a clean exit, or APPROVE with a failed process, or a bad decision, or a symlink: all FAIL.
    outside=t/'approve-elsewhere.json';outside.write_text(json.dumps({"verdict":"APPROVE"}))
    for tag,body,missing in (('prose','print(json.dumps({"verdict":"APPROVE","claims":["APPROVE"]}))\n','<missing-audit-verdict>'),
                             ('rc1','Path(v).write_text(json.dumps({"verdict":"APPROVE"}))\nsys.exit(3)\n',None),
                             ('maybe','Path(v).write_text(json.dumps({"verdict":"MAYBE"}))\n','<missing-audit-verdict>'),
                             ('link','os.symlink(%r,v)\n'%str(outside),'<missing-audit-verdict>'),
                             ('fifo','os.mkfifo(v)\n','<missing-audit-verdict>')):
        e,repo=run_audit(tag,body);aud=auditors(e)[0]
        assert e.j.state['nodes'][aud]['status']=='FAIL' and 'merge' not in e.j.state['nodes'],(tag,e.j.state['nodes'][aud])
        if missing:assert missing in e.j.state['nodes'][aud]['evidence']['missing'],tag
    # C07: with two audited workers behind one gate, BOTH chains gate the merge (the second used to dangle).
    g2=audit_graph(2)
    assert sorted(x['from'] for x in g2['edges'] if x['to']=='merge')==['w0.audit.plug.1','w1.audit.plug.1'],g2['edges']
    first=t/'first-auditor-seen'
    e,repo=run_audit('two','try:\n    os.close(os.open(%r,os.O_CREAT|os.O_EXCL))\n    verdict="APPROVE"\nexcept FileExistsError:\n    verdict="REJECT"\nPath(v).write_text(json.dumps({"verdict":verdict}))\n'%str(first),workers=2,graph=g2)
    assert sorted(e.j.state['nodes'][a]['status'] for a in auditors(e))==['FAIL','PASS'] and 'merge' not in e.j.state['nodes'],e.j.state['nodes']
    # C07: the auditor's handoff carries the real diff and the spec.
    repo=t/'repo-diff';(repo/'w0').mkdir(parents=True)
    genv={**os.environ,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null','GIT_AUTHOR_NAME':'r','GIT_AUTHOR_EMAIL':'r@x','GIT_COMMITTER_NAME':'r','GIT_COMMITTER_EMAIL':'r@x'}
    subprocess.run(['git','init','-q','-b','main'],cwd=repo,check=True,env=genv)
    (repo/'feature.py').write_text('VALUE = 1\n');(repo/'SPEC.md').write_text('SPEC_MARKER requirement text\n')
    subprocess.run(['git','add','-A'],cwd=repo,check=True,env=genv);subprocess.run(['git','commit','-qm','base'],cwd=repo,check=True,env=genv)
    (repo/'feature.py').write_text('VALUE = 2  # CHANGED_MARKER\n')
    g=audit_graph(1)
    for n in g['nodes']:
        if n.get('role')=='audit':n['spec_path']='SPEC.md'
    dump=t/'contract.json'
    run_audit('diff','Path(v).write_text(json.dumps({"verdict":"APPROVE"}))\nPath(%r).write_text(json.dumps(h["audit_contract"]))\n'%str(dump),graph=g,repo=repo)
    contract=json.loads(dump.read_text())
    assert 'CHANGED_MARKER' in contract['diff'] and 'SPEC_MARKER' in contract['spec'],contract
    assert contract['verdict_file'].endswith('audit.json') and 'APPROVE|REJECT' in contract['schema']

    # C15: lanes with different cwd but one shared --rw bind never run together; disjoint binds still do.
    repo=t/'repo-shared'
    for x in ('a','b','shared'):(repo/x).mkdir(parents=True)
    for x in ('a','b'):(repo/x/'own').mkdir()
    slow=t/'slow.py';slow.write_text('import time\ntime.sleep(.25)\nprint("{}")\n')
    def lanes(tag,bind):
        nodes=[{'id':x,'kind':'agent','role':'worker','lane':x,'cwd':x,'tiers':[{'provider':'claude','model':'stub'}],
                'sandbox':[STUB,'--rw',bind],'max_attempts':1} for x in ('a','b')]
        e=Engine(validate({'wip':2,'quota':Q,'nodes':nodes}),repo,t/('state-'+tag),{'claude':[sys.executable,str(slow)]})
        assert e.run()['passed']==2
        return {(x['type'],x['node']):x['seq'] for x in e.j.events if x['type'] in('START','RESULT')}
    st=lanes('shared','../shared')
    first,second=sorted(('a','b'),key=lambda k:st[('START',k)])
    assert st[('START',second)]>st[('RESULT',first)],'lanes sharing one writable bind ran together'
    st=lanes('own','own')
    assert st[('START','b')]<st[('RESULT','a')] and st[('START','a')]<st[('RESULT','b')],'disjoint lanes were serialized'

    # C20: gate infrastructure failure (rc 127) backs off and retries the GATE only; the worker is neither re-run nor escalated.
    infra=t/'trusted-infra';infra.mkdir()
    (infra/'gate.sh').write_text('#!/bin/bash\necho "bwrap: not found" >&2\nexit 127\n')
    repo=t/'repo-infra';repo.mkdir()
    cnt=t/'worker-count';cnt.write_text('')
    counting=t/'counting.py';counting.write_text('open(%r,"a").write("x")\nprint("{}")\n'%str(cnt))
    g=validate({'wip':1,'quota':Q,'nodes':[
        {'id':'worker','kind':'agent','role':'worker','tiers':[{'provider':'claude','model':'weak'},{'provider':'claude','model':'strong'}],
         'sandbox':[STUB],'max_attempts':4},
        {'id':'gate','kind':'gate','cmd':['false'],'artifacts':['.autoshift-gate-output/x'],'trusted_gate':{'root':str(infra),'entry':'gate.sh'}}],
        'edges':[{'from':'worker','to':'gate'}]})
    e=Engine(g,repo,t/'state-infra',{'claude':[sys.executable,str(counting)]});e.run()
    assert cnt.read_text()=='x',('worker was re-run for a gate infrastructure error',cnt.read_text())
    assert e.j.state['nodes']['worker']['tier']['model']=='weak'
    assert e.j.state['nodes']['gate']['attempt']==3,e.j.state['nodes']['gate']
    assert any(f['source']=='infrastructure' for f in e.j.state['feedback'])
    assert [k for k,v in e.j.state['asks'].items() if v['answer'] is None]==['gate']
    assert not [x for x in e.j.events if x['type']=='RETRY' and x['node']=='worker']
    # C20: an agent that only reports a provider outage is retried on the SAME tier; a real failure escalates.
    for text,final in (('429 Too Many Requests: rate limit exceeded','weak'),('boom: assertion failed','strong')):
        repo=t/('repo-out-'+final);repo.mkdir()
        bad=t/('bad-%s.py'%final);bad.write_text('import sys\nsys.stderr.write(%r)\nsys.exit(1)\n'%text)
        g=validate({'wip':1,'quota':Q,'nodes':[{'id':'w','kind':'agent','role':'worker','sandbox':[STUB],'max_attempts':4,
              'tiers':[{'provider':'claude','model':'weak'},{'provider':'claude','model':'strong'}]}]})
        e=Engine(g,repo,t/('state-out-'+final),{'claude':[sys.executable,str(bad)]});e.run()
        assert e.j.state['nodes']['w']['tier']['model']==final,(text,e.j.state['nodes']['w']['tier'])
        assert e.j.state['nodes']['w']['evidence']['signature'].startswith('infra:')==(final=='weak')

    # C14: when the scheduler raises, every other finished child is still journalled, one by one.
    repo=t/'repo-drain';repo.mkdir()
    g=validate({'wip':3,'nodes':[{'id':x,'kind':'code','lane':x,'cmd':['python3','-c',"import time;time.sleep(.15);open('%s.ok','w').write('1')"%x],
                                 'artifacts':[x+'.ok']} for x in ('one','two','three')]})
    e=Engine(g,repo,t/'state-drain')
    real_append=e.j.append
    def flaky(kind,key,*a,**k):
        if key=='result:one:1':raise OSError(28,'No space left on device')   # the first finished child cannot be recorded
        return real_append(kind,key,*a,**k)
    e.j.append=flaky
    try:e.run();raise AssertionError('disk error swallowed')
    except OSError as exc:assert exc.errno==28,exc   # the original error is not replaced by a later one
    j=Journal(t/'state-drain')
    done={k for k,v in j.state['nodes'].items() if v['status']=='PASS'}
    assert {'two','three'}<=done and 'one' not in done,j.state['nodes']
    e2=Engine(g,repo,t/'state-drain');e2.recover()
    assert e2.j.state['nodes']['one']['status']=='BLOCKED' and 'driver died' in e2.j.state['nodes']['one']['reason']

    # C10: UNCERTAIN nodes are settled only by reconcile; a gate cannot be accepted; free text does not retry.
    repo=t/'repo-rec';repo.mkdir()
    gf=t/'rec.json'
    graph={'nodes':[{'id':'effect','kind':'code','cmd':['python3','-c',"open('effect.txt','w').write('1')"],'artifacts':['effect.txt']},
                    {'id':'check','kind':'gate','cmd':['python3','-c','pass'],'artifacts':['x']}]}
    gf.write_text(json.dumps(graph));state=t/'state-rec'
    vg=validate(graph);first_engine=Engine(vg,repo,state)
    for node in ('effect','check'):first_engine.j.append('START','start:%s:1'%node,node,{'attempt':1,'tier':None})
    Engine(vg,repo,state).recover()
    assert cli_call(gf,repo,state,'reconcile','check','--accept')[0]==2,'a gate verdict was accepted by hand'
    assert cli_call(gf,repo,state,'answer','effect','please retry','--outcome','BLOCKED','--retry')[0]==2
    assert cli_call(gf,repo,state,'answer','effect','I checked: no retry needed, effect complete')[0]==0
    assert Journal(state).state['nodes']['effect']['status']=='BLOCKED','free text moved an UNCERTAIN node'
    assert cli_call(gf,repo,state,'reconcile','effect','--accept')==(0,'RECONCILED')
    assert Journal(state).state['nodes']['effect']['status']=='PASS'
    assert cli_call(gf,repo,state,'reconcile','check','--rerun')==(0,'RECONCILED')
    assert Journal(state).state['nodes']['check']['status']=='RETRY' and Journal(state).diff()==[]

    # P5 residual: a second exhaustion re-opens the ask instead of dropping a duplicate key; text alone never retries.
    repo=t/'repo-ask';repo.mkdir()
    dead={'nodes':[{'id':'build','kind':'code','cmd':['false'],'max_attempts':1},{'id':'later','kind':'code','cmd':['true']}],'edges':[{'from':'build','to':'later'}]}
    gf=t/'dead.json';gf.write_text(json.dumps(dead));state=t/'state-ask'
    for i in range(2):
        assert cli_call(gf,repo,state,'run')[0]==3
        j=Journal(state)
        assert j.state['asks']['build']['answer'] is None and 'later' not in j.state['nodes'],(i,j.state['asks'])
        if i==0:
            assert cli_call(gf,repo,state,'answer','build','please retry')[0]==0
            assert Journal(state).state['nodes']['build']['status']=='BLOCKED','free text started a retry'
            assert cli_call(gf,repo,state,'answer','build','again','--retry')[0]==0
    assert len([x for x in Journal(state).events if x['type']=='ASK'])==2

    # C06: gate content is pinned in the journal before any worker runs; acceptance tests live outside the worker tree.
    trusted=t/'trusted-acc';(trusted/'acceptance').mkdir(parents=True)
    (trusted/'gate.sh').write_text('#!/bin/bash\nset -e\npython3 "$(dirname "$0")/$1"\nprintf ok > "$AUTOSHIFT_GATE_OUT/gate.ok"\n')
    (trusted/'acceptance/test_feature.py').write_text('from pathlib import Path\nassert Path("feature.txt").read_text()=="good",Path("feature.txt").read_text()\n')
    repo=t/'repo-pin';repo.mkdir()
    fw=t/'feature_writer.py'
    fw.write_text('from pathlib import Path\nPath("feature.txt").write_text("bad")\nPath("test_feature.py").write_text("assert True")  # worker-authored vacuous test\nprint("{}")\n')
    pgraph=validate({'wip':1,'quota':Q,'nodes':[
        {'id':'worker','kind':'agent','role':'worker','tiers':[{'provider':'claude','model':'m'}],'sandbox':[STUB],'max_attempts':1},
        {'id':'gate','kind':'gate','cmd':['false'],'artifacts':['.autoshift-gate-output/gate.ok'],
         'trusted_gate':{'root':str(trusted),'entry':'gate.sh','args':['acceptance/test_feature.py'],'code_paths':['feature.txt']}}],
        'edges':[{'from':'worker','to':'gate'}]})
    for bad in ({'pin':'acceptance'},{'pin':['../x']},{'pin':['/etc']},{'args':[1]}):
        try:validate({'nodes':[{'id':'g','kind':'gate','cmd':['x'],'artifacts':['a'],'trusted_gate':{'root':str(trusted),'entry':'gate.sh',**bad}}]});raise AssertionError(bad)
        except ValueError:pass
    e=Engine(pgraph,repo,t/'state-pin',{'claude':[sys.executable,str(fw)]})
    assert len([x for x in e.j.events if x['type']=='PIN'])==1
    e.run()
    ev=e.j.state['nodes']['gate']
    assert ev['status']=='FAIL','worker-written vacuous test replaced the trusted acceptance test'
    assert 'AssertionError' in ev['evidence']['stderr_tail'] and 'bad' in ev['evidence']['stderr_tail'],ev['evidence']['stderr_tail']
    assert min(x['seq'] for x in e.j.events if x['type']=='PIN')<min(x['seq'] for x in e.j.events if x['type']=='START')
    (trusted/'acceptance/test_feature.py').write_text('assert True\n')   # the acceptance test is weakened afterwards
    try:Engine(pgraph,repo,t/'state-pin');raise AssertionError('changed gate content accepted')
    except ValueError as exc:assert 'changed since it was pinned' in str(exc),exc
    pf=t/'pin.json';pf.write_text(json.dumps(pgraph))
    assert cli_call(pf,repo,t/'state-pin','revise','--reason','acceptance test change reviewed')==(0,'GRAPH_REVISED')
    Engine(pgraph,repo,t/'state-pin')   # after an explicit revision the new content is pinned
    assert len(Journal(t/'state-pin').state['pins'])==1
    e=Engine(pgraph,repo,t/'state-pin2',{'claude':[sys.executable,str(fw)]})
    (trusted/'acceptance/test_feature.py').write_text('assert False\n')   # changed between pin and gate run
    e.run()
    ev=e.j.state['nodes']['gate']['evidence']
    assert e.j.state['nodes']['gate']['status']=='BLOCKED' and ev['signature']=='trusted-gate-changed',ev
print('V7_TRUST_OK C06 C07 C10 C14 C15 C20 ask-key')
