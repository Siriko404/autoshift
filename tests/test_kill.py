"""50 driver+runner SIGKILL interruptions; conservative no replay of uncertain effects."""
import json,os,random,signal,subprocess,sys,tempfile,time
from pathlib import Path
base=Path(__file__).resolve().parents[1]
random.seed(43133)
with tempfile.TemporaryDirectory() as d:
 for i in range(50):
  root=Path(d)/str(i);root.mkdir()
  code="import time;from pathlib import Path;time.sleep(.1);p=Path('count');p.write_text(str(int(p.read_text())+1 if p.exists() else 1))"
  graph={'name':'crash','wip':1,'nodes':[{'id':'effect','kind':'code','cmd':['python3','-c',code],
                                                'artifacts':['count'],'timeout':3}]}
  g=root/'g.json';g.write_text(json.dumps(graph));state=root.parent/('state-'+str(i))
  cmd=[str(base/'bin/autoshift'),'--graph',str(g),'--repo',str(root),'--state',str(state),'run']
  p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  time.sleep(.01+random.random()*.10)
  # Find children before terminating; SIGKILL cannot invoke the driver's cleanup handler.
  children=[]
  for task in (Path('/proc')/str(p.pid)/'task').glob('*') if (Path('/proc')/str(p.pid)/'task').exists() else []:
   try:children += [int(x) for x in (task/'children').read_text().split()]
   except OSError:pass
  for pid in children:
   try:os.killpg(pid,signal.SIGKILL)
   except (ProcessLookupError,PermissionError):pass
  try:os.kill(p.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  p.communicate(timeout=4)
  result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=4)
  assert result.returncode in (0,3),result.stderr
  from sys import path
  sys.path.insert(0,str(base))
  from autoshift.ledger import Journal
  j=Journal(state);assert j.diff()==[],(i,j.diff())
  assert len(j.state['nodes'])==1,(i,j.state)
  assert j.state['nodes']['effect']['status'] in ('PASS','BLOCKED'),i
  if j.state['nodes']['effect']['status']=='BLOCKED':
   assert j.state['nodes']['effect'].get('reason','').startswith('driver died'),i
  c=root/'count'
  assert not c.exists() or c.read_text()=='1', 'double-effect mutant survived at iteration '+str(i)
print('KILL_OK')
