"""V5 security regressions: P1, P2, P4, P5, Q2-Q4, trust and handoff semantics."""
import contextlib,io,json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate,load
from autoshift.scheduler import Engine,status
from autoshift.ledger import Journal
from autoshift.quota import reading
from autoshift.runner import execute
from autoshift import cli
base=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 t=Path(d);repo=t/'repo';repo.mkdir();state=t/'secure-state'
 # P2: state cannot be under --repo, even when an attacker has a stub shell.
 g=validate({'nodes':[{'id':'n','kind':'code','cmd':['true']}]})
 try: Engine(g,repo,repo/'.autoshift-state');raise AssertionError('P2 forged journal admitted')
 except ValueError as e:assert 'journal must be outside' in str(e)
 # P1: unverifiable in-repo gate and writable git metadata are forbidden.
 base_graph={'nodes':[{'id':'w','kind':'agent','tiers':['stub'], 'sandbox':[str(base/'tests/stub-sandbox.sh')]},
                       {'id':'g','kind':'gate','cmd':['bash','tools/gate.sh'],'artifacts':['gate.ok']}],
             'edges':[{'from':'w','to':'g'}]}
 try:validate(base_graph);raise AssertionError('P1 worker-authored gate accepted')
 except ValueError as e:assert 'untrusted gate' in str(e)
 (repo/'.git').mkdir()  # Exercise the writable-Git guard on an actual .git tree.
 unsafe=validate({'nodes':[{'id':'a','kind':'agent','tiers':['stub'],
                 'sandbox':[str(base/'adapters/sandbox.sh'),'--rw','.','--net','0']}]})
 try:Engine(unsafe,repo,state);raise AssertionError('agent could write .git')
 except ValueError as e:assert 'writable bind includes .git' in str(e)
 # R9: graph must be journal-pinned; caller cannot silently swap a live graph.
 en=Engine(g,repo,t/'graph-state');assert en.run()['passed']==1
 changed=validate({'nodes':[{'id':'next','kind':'code','cmd':['true']}]})
 try:Engine(changed,repo,t/'graph-state');raise AssertionError('Q4 accepted mutated graph')
 except ValueError as e:assert 'graph revision refused' in str(e)
 gf=t/'changed.json';gf.write_text(json.dumps(changed))
 with contextlib.redirect_stdout(io.StringIO()):
  assert cli.main(['--graph',str(gf),'--repo',str(repo),'--state',str(t/'graph-state'),'revise','--reason','reviewed-v2'])==0
 assert Engine(changed,repo,t/'graph-state').run()['passed']==1
 assert len(Journal(t/'graph-state').state['revisions'])==2
 # Q2: static quota disabled outside explicit test fixture mode.
 old=os.environ.pop('AUTOSHIFT_TEST_STATIC_QUOTA',None)
 try:
  r=reading({'claude':{'usage_pct':10,'limit_pct':80}},'claude')
  assert not r['admitted'] and r['state']=='READER_ERROR'
 finally:
  if old is not None:os.environ['AUTOSHIFT_TEST_STATIC_QUOTA']=old
 # Q3: exact goal, contract, and output taint survive compression.
 goal='Please just review THE WHOLE TASK and never modify any locked gate scripts.'
 rn=execute({'id':'exact','kind':'agent','goal':goal,'tiers':['a'],
           'sandbox':[str(base/'tests/stub-sandbox.sh')]},1,'a',repo,t/'handoff-state')
 h=json.loads((t/'handoff-state/handoffs/exact-1.json').read_text())
 assert h['goal']==goal and 'Never assert gate PASS' in h['output_contract']
 # P4: audit must return affirmative structured verdict, not approval by CLI exit.
 auditor=t/'auditor.py';auditor.write_text('import json;print(json.dumps({"claims":["REJECT this change"]}))\n')
 ga=validate({'nodes':[{'id':'auditor','kind':'agent','role':'audit',
       'tiers':[{'provider':'claude','model':'stub'}], 'sandbox':[str(base/'tests/stub-sandbox.sh')]}],
       'quota':{'claude':{'usage_pct':0,'limit_pct':80}}})
 an=Engine(ga,repo,t/'audit-state',{'claude':['python3',str(auditor)]})
 ar=an.run();assert an.j.state['nodes']['auditor']['status']=='FAIL' and ar['failed']==1
 g1=load(base/'examples/g1-production.json')
 assert any(e['from']=='gate' and '.audit.' in e['to'] for e in g1['edges']), 'audits need post-gate placement'
 # P5/R6: known FAIL edge is handled and its stderr reaches downstream handoff.
 worker=t/'second.py';worker.write_text('import json,sys;from pathlib import Path\nh=json.loads(Path(sys.argv[1]).read_text());assert "AssertionError" in json.dumps(h["previous"]);print("{}")\n')
 trusted=t/'trusted';trusted.mkdir();(trusted/'fail.sh').write_text('#!/usr/bin/env bash\necho AssertionError >&2\nexit 1\n')
 fp=validate({'nodes':[{'id':'first','kind':'gate','cmd':['python3','-c','raise AssertionError("oracle says no")'], 'artifacts':['unused'],'trusted_gate':{'root':str(trusted),'entry':'fail.sh'}},
                       {'id':'next','kind':'agent','tiers':[{'provider':'claude','model':'stub'}],
                        'sandbox':[str(base/'tests/stub-sandbox.sh')], 'goal':'Review failure evidence'}],
             'edges':[{'from':'first','to':'next','on':['FAIL']}],
             'quota':{'claude':{'usage_pct':0,'limit_pct':80}}})
 eng=Engine(fp,repo,t/'fail-state',{'claude':['python3',str(worker)]})
 r=eng.run();assert eng.j.state['nodes']['first']['status']=='FAIL' and eng.j.state['nodes']['next']['status']=='PASS',r
 assert not [e for e in eng.j.events if e['type']=='ASK'] and r['failed']==0
 hh=json.loads((t/'fail-state/handoffs/next-1.json').read_text())
 assert 'AssertionError' in json.dumps(hh.get('previous',{}))
 # Pending asks hold dependent work; explicit answer can retry exhausted node.
 dead=validate({'nodes':[{'id':'build','kind':'code','cmd':['false'],'max_attempts':1},
                         {'id':'later','kind':'code','cmd':['true']}],
                 'edges':[{'from':'build','to':'later'}]})
 be=Engine(dead,repo,t/'ask-state');be.run()
 assert be.j.state['nodes']['build']['status']=='FAIL' and 'later' not in be.j.state['nodes']
 assert 'build' in be.j.state['asks'] and be.j.state['asks']['build']['answer'] is None
 gg=t/'dead.json';gg.write_text(json.dumps(dead))
 with contextlib.redirect_stdout(io.StringIO()):
  assert cli.main(['--graph',str(gg),'--repo',str(repo),'--state',str(t/'ask-state'),'answer','build','retry please','--retry'])==0
 assert be.j.refresh() is None
 assert be.j.state['nodes']['build']['status']=='RETRY'
print('V5_SECURITY_OK P1 P2 P4 P5 Q2 Q3 Q4')
