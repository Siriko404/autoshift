import copy,json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import load,validate
from autoshift.scheduler import Engine,status
base=Path(__file__).resolve().parents[1]
wrapper=[str(base/'tests/stub-sandbox.sh')]
def quotas(g):
 g['quota']={p:{'usage_pct':0,'limit_pct':80} for p in ('claude','codex','opencode','agy')}
 return g
providers={'claude':['python3',str(base/'tests/stub-agent.py')],
           'codex':['python3',str(base/'tests/stub-agent.py')],
           'opencode':['python3',str(base/'tests/stub-agent.py')],
           'agy':['python3',str(base/'tests/stub-agent.py')]}
with tempfile.TemporaryDirectory() as d:
 root=Path(d)/'repo';root.mkdir();g=load(base/'examples/g3-pipeline.json')
 en=Engine(g,root,root.parent/'state');assert en.run()['passed']==4
 assert en.j.diff()==[];assert 'lane' in status(g,en.j)
 # G2: two passes defined entirely by data; stubbed fresh agent, gate passes after stub-created sentinel
 g2=quotas(load(base/'examples/g2-ralph.json'))
 for n in g2['nodes']:
  if n['kind']=='agent':n['sandbox']=wrapper;n['artifacts']=[]
  if n['kind']=='gate':n['cmd']=['python3','-c','from pathlib import Path;Path("'+n['artifacts'][0]+'").write_text("ok")']
 en2=Engine(g2,root,root.parent/'g2-state',providers)
 assert en2.run()['passed']>=2
 # G1 entirely graph-based: patch project commands to sandbox-free stub code
 g1=quotas(load(base/'examples/g1-production.json'))
 for n in g1['nodes']:
  if n['kind']=='agent':
   n['sandbox']=wrapper;n['artifacts']=[]
  if n['kind']=='gate' or n['kind']=='code':
   n['cmd']=['python3','-c','from pathlib import Path;Path('+repr(n['artifacts'][0])+').write_text("ok")']
 en1=Engine(g1,root,root.parent/'g1-state',providers)
 r=en1.run();assert r['passed']>=5 and en1.j.state['nodes']['gate']['status']=='FAIL' and 'merge' not in en1.j.state['nodes'], r  # unwired G1 cannot merge
 assert len([n for n in g1['nodes'] if '.audit.plugin.' in n['id']])==2
 # stopped means no dispatch; cannot silently resume
 gs=validate({'nodes':[{'id':'one','kind':'code','cmd':['python3','-c','raise SystemExit(0)']} ]})
 eng=Engine(gs,root,root.parent/'stop');eng.j.append('STOP','stop:1')
 assert eng.run()['passed']==0 and eng.j.state['nodes']=={},'stop mutant survived'
 eng.j.append('RESUME','resume:1');assert eng.run()['passed']==1
 # failure escalates after two identical signatures, then strongest parks and asks
 ga=quotas(validate({'nodes':[{'id':'bad','kind':'agent','goal':'PELICAN','tiers':[
     {'provider':'claude','model':'cheap'},{'provider':'claude','model':'strong'}],
     'sandbox':wrapper,'artifacts':['never'],'max_attempts':4}]}))
 eng=Engine(ga,root,root.parent/'escalate',providers)
 assert eng.run()['failed']==1
 assert any(e['type']=='ASK' for e in eng.j.events), 'exhaustion mutant survived'
 # PELICAN: second fresh process can only find fact in prior handoff; artifacts omitted
 gp=quotas(validate({'nodes':[{'id':'bird','kind':'agent','goal':'PELICAN',
     'tiers':[{'provider':'claude','model':'cheap'}], 'max_attempts':2,'sandbox':wrapper}]}))
 eng=Engine(gp,root,root.parent/'pelican',providers);assert eng.run()['passed']==1
 assert eng.j.state['nodes']['bird']['attempt']==2
 # agent lies about test passing; missing artifact remains FAIL
 gl=quotas(validate({'nodes':[{'id':'liar','kind':'agent','goal':'test',
 'tiers':[{'provider':'claude','model':'cheap'}], 'max_attempts':1,'sandbox':wrapper,
 'artifacts':['never-created.txt']}]}))
 eng=Engine(gl,root,root.parent/'liar',providers);assert eng.run()['failed']==1
 assert eng.j.state['nodes']['liar']['evidence']['claims'][0].startswith('ALL TESTS PASSED')
print('SCHEDULER_OK')
