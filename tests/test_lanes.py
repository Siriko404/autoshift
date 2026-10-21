"""K7 independent lanes rendezvous; same-lane START cannot precede prior RESULT."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate
from autoshift.scheduler import Engine
with tempfile.TemporaryDirectory() as d:
 root=Path(d)/'repo';root.mkdir()
 def waiter(own,other):
  return ['python3','-c',"from pathlib import Path;import time,sys;"+
   f"Path('{own}.ready').write_text('yes');"+
   f"deadline=time.monotonic()+4;other=Path('{other}.ready');"+
   "\nwhile not other.exists() and time.monotonic()<deadline:time.sleep(.01)\n"+
   "sys.exit(0 if other.exists() else 2)"]
 p=validate({'wip':2,'nodes':[{'id':'a','kind':'code','lane':'west','cmd':waiter('a','b')},
                             {'id':'b','kind':'code','lane':'east','cmd':waiter('b','a')}]})
 eng=Engine(p,root,root.parent/'parallel-state');r=eng.run()
 assert r['passed']==2,(r,eng.j.events)
 serial=validate({'wip':2,'nodes':[
  {'id':'first','kind':'code','lane':'same','cmd':['python3','-c',
      "from pathlib import Path;import time;time.sleep(.18);Path('first.done').write_text('ok')"]},
  {'id':'second','kind':'code','lane':'same','cmd':['python3','-c',
      "from pathlib import Path;assert Path('first.done').read_text()=='ok'"]}]})
 s=Engine(serial,root,root.parent/'serial-state');r=s.run();assert r['passed']==2,r
 ev=s.j.events
 start_b=next(x['seq'] for x in ev if x['type']=='START' and x['node']=='second')
 result_a=next(x['seq'] for x in ev if x['type']=='RESULT' and x['node']=='first')
 assert start_b>result_a,'same-lane interleaved'
print('LANES_OK')
