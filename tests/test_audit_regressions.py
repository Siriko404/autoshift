"""Independent call-2 behavioral oracles; must fail on unpatched v1."""
import json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate
from autoshift.ledger import Journal
from autoshift.runner import execute
from autoshift.scheduler import Engine, status

with tempfile.TemporaryDirectory() as d:
 root=Path(d)/'repo';root.mkdir()
 # K6: a START following RETRY must retain failure history so repeat signatures escalate.
 graph=validate({'nodes':[{'id':'a','kind':'agent','tiers':['cheap','strong'],
        'sandbox':['true'],'max_attempts':4}]})
 eng=Engine(graph,root,root.parent/'hist')
 j=eng.j
 for k in (1,2):
  j.append('START','start:a:'+str(k),'a',{'attempt':k,'tier':'cheap'})
  j.append('RESULT','result:a:'+str(k),'a',{'status':'FAIL','signature':'17:broken','rc':17,'artifacts':[]})
  eng.next_retry('a',graph['nodes'][0])
 assert j.state['nodes']['a']['tier']=='strong', 'duplicate failures must escalate'
 assert len(j.state['nodes']['a']['history'])==2,'journal dropped retry history'
 assert j.diff()==[]
 # K6: max_attempts is a total ceiling, even if escalation condition is met.
 capped=validate({'nodes':[{'id':'b','kind':'agent','tiers':['cheap','strong'],'max_attempts':2}]})
 en=Engine(capped,root,root.parent/'ceiling')
 for k in (1,2):
  en.j.append('START','start:b:'+str(k),'b',{'attempt':k,'tier':'cheap'})
  en.j.append('RESULT','result:b:'+str(k),'b',{'status':'FAIL','signature':'same'})
  en.next_retry('b',capped['nodes'][0])
 assert any(e['type']=='ASK' for e in en.j.events)
 assert en.j.state['nodes']['b']['status'] != 'RETRY'
 # K4: prior stale gate evidence must not certify a new execution.
 (root/'gate.ok').write_text('stale')
 res=execute({'id':'stale','kind':'gate','cmd':['python3','-c','pass'],
              'artifacts':['gate.ok']},1,None,root,root.parent/'gate-state')
 assert res['status']=='FAIL' and '<stale:gate.ok>' in res['missing'],res
 # Rewriting an identical gate marker is valid new evidence, not a false stale positive.
 res2=execute({'id':'fresh','kind':'gate','cmd':['python3','-c',
    'from pathlib import Path;Path("gate.ok").write_text("stale")'],
    'artifacts':['gate.ok']},1,None,root,root.parent/'fresh-state')
 assert res2['status']=='PASS',res2
 # K8: STOP and START linearize through same journal lock.
 stop=Journal(root.parent/'stopping'); stop.append('STOP','stop:one')
 assert stop.append('START','start:after-stop','late',{'attempt':1},require_running=True) is False
 assert 'late' not in stop.state['nodes']
 # K13: fail-only predecessor does not make PASS successor ready.
 bg=validate({'nodes':[{'id':'bad','kind':'code','cmd':['false']},
                        {'id':'later','kind':'code','cmd':['true']}],
              'edges':[{'from':'bad','to':'later','on':['PASS']}]})
 jv=Journal(root.parent/'view');jv.append('START','start:bad','bad',{'attempt':1})
 jv.append('RESULT','result:bad','bad',{'status':'FAIL','signature':'1'})
 assert 'later [tentative]' in status(bg,jv),'incorrect optimistic READY'
 # K14: explicit HUMAN outcome, not arbitrary free-text, controls ask node.
 askg=validate({'nodes':[{'id':'permit','kind':'ask','goal':'May we continue?'},
                         {'id':'next','kind':'code','cmd':['python3','-c','pass']}],
               'edges':[{'from':'permit','to':'next'}]})
 ga=root/'ask.json';ga.write_text(json.dumps(askg));st=root.parent/'ask-state'
 exe=[sys.executable,'-m','autoshift','--graph',str(ga),'--repo',str(root),'--state',str(st)]
 first=subprocess.run(exe+['run'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=12)
 assert first.returncode==3,first
 declined=subprocess.run(exe+['answer','permit','no'],capture_output=True,text=True,timeout=12)
 assert declined.returncode==0
 assert Journal(st).state['nodes']['permit']['status']=='BLOCKED'
 approved=subprocess.run(exe+['answer','permit','yes','--outcome','PASS'],capture_output=True,text=True,timeout=12)
 assert approved.returncode==0,approved.stderr
 assert Journal(st).state['nodes']['permit']['status']=='PASS'
 second=subprocess.run(exe+['run'],capture_output=True,text=True,timeout=12)
 assert second.returncode==0,second.stderr
 assert Journal(st).state['nodes']['next']['status']=='PASS'
print('AUDIT_REGRESSIONS_OK')
