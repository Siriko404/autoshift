"""Durability for every native feedback source, and its mechanical-check field."""
import contextlib,io,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate
from autoshift.scheduler import Engine
from autoshift.ledger import Journal
from autoshift.cli import main
base=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 root=Path(d)/'repo';root.mkdir()
 # Gate outcome; agent audit role (under stubbed CLI) emits audit feedback.
 gate=validate({'nodes':[{'id':'gate','kind':'gate','artifacts':['gate.ok'],'cmd':[
     sys.executable,'-c','from pathlib import Path;Path("gate.ok").write_text("ok")']}]})
 engine=Engine(gate,root,root.parent/'gate-state');assert engine.run()['passed']==1
 assert any(f['source']=='gate_result' for f in engine.j.state['feedback'])
 # Audit node with no sandbox: runner blocks. The feedback still records the verdict.
 audit=validate({'nodes':[{'id':'audit','kind':'agent','role':'audit',
   'tiers':[{'provider':'claude','model':'stub'}],'max_attempts':1}],
   'quota':{'claude':{'usage_pct':0,'limit_pct':80}}})
 eng=Engine(audit,root,root.parent/'audit-state');eng.run()
 assert any(f['source']=='audit_finding' for f in eng.j.state['feedback'])
 # Fail-closed quota admission records why a non-code dispatch stopped.
 denied=validate({'nodes':[{'id':'worker','kind':'agent','tiers':[{'provider':'claude','model':'haiku'}]}]})
 eng=Engine(denied,root,root.parent/'quota-state');eng.run()
 assert any(f['source']=='quota_stop' for f in eng.j.state['feedback'])
 # Human answer is a durable FEEDBACK with outcome, not a model claim.
 asked=validate({'nodes':[{'id':'owner','kind':'ask','goal':'Approve manual operation'}]})
 import json
 graph_file=root/'asks.json';graph_file.write_text(json.dumps(asked))
 asks=root.parent/'ask-state';j=Journal(asks);j.append('ASK','ask:owner','owner',{'question':'Approve?'})
 with contextlib.redirect_stdout(io.StringIO()):
  assert main(['--graph',str(graph_file),'--repo',str(root),'--state',str(asks),
    'answer','owner','yes','--outcome','PASS'])==0
 j=Journal(asks)
 assert any(f['source']=='owner_answer' for f in j.state['feedback'])
 # After a crash, the unfinished effect is parked. A feedback record marks recovery.
 one=validate({'nodes':[{'id':'running','kind':'code','cmd':['true']}]})
 j=Journal(root.parent/'kill-state');j.append('START','inflight','running',{'attempt':1})
 eng=Engine(one,root,root.parent/'kill-state');eng.run()
 assert any(f['source']=='kill_recovery' for f in eng.j.state['feedback'])
 for st in (engine.j.state,Journal(root.parent/'audit-state').state,Journal(root.parent/'quota-state').state,
            Journal(asks).state,eng.j.state):
  assert all(x['mechanical_check'] and x['source'] and x['node'] for x in st['feedback'])
  assert st['feedback'] and st['feedback'][0]['source']
 for jx in (engine.j,eng.j,Journal(root.parent/'quota-state'),Journal(asks)):
  assert jx.diff()==[]
print('FEEDBACK_COVERAGE_OK')
