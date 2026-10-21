"""P6: driver SIGKILL kills effect, and UNCERTAIN can be settled explicitly."""
import json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.ledger import Journal
base=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 t=Path(d);repo=t/'repo';repo.mkdir();state=t/'state'
 graph=t/'g.json'
 graph.write_text(json.dumps({'nodes':[
  {'id':'effect','kind':'code','cmd':['python3','-c',"import time;time.sleep(1.4);open('effect.txt','w').write('done')"], 'artifacts':['effect.txt']},
  {'id':'next','kind':'code','cmd':['python3','-c',"open('next.txt','w').write('done')"], 'artifacts':['next.txt']}],
  'edges':[{'from':'effect','to':'next'}]}))
 args=[str(base/'bin/autoshift'),'--graph',str(graph),'--repo',str(repo),'--state',str(state)]
 env={**os.environ,'AUTOSHIFT_TEST_SANDBOX':'1'}
 driver=subprocess.Popen(args+['run'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
 for _ in range(150):
  if (state/'events.jsonl').exists() and any(e.get('type')=='START' for e in Journal(state).events):break
  time.sleep(.02)
 else:raise AssertionError('no START')
 time.sleep(.2)
 os.kill(driver.pid,signal.SIGKILL);driver.wait(timeout=5)
 time.sleep(1.7)
 assert not (repo/'effect.txt').exists(),'P6 orphaned child survived SIGKILL'
 restart=subprocess.run(args+['run'],env=env,capture_output=True,text=True,timeout=10)
 assert Journal(state).state['nodes']['effect']['status']=='BLOCKED',restart.stderr
 reconcile=subprocess.run(args+['reconcile','effect','--rerun'],env=env,capture_output=True,text=True,timeout=10)
 assert reconcile.returncode==0,reconcile.stderr
 again=subprocess.run(args+['run'],env=env,capture_output=True,text=True,timeout=10)
 assert again.returncode==0,again.stderr
 assert (repo/'effect.txt').read_text()=='done' and (repo/'next.txt').read_text()=='done'
 assert Journal(state).diff()==[]
print('V5_CRASH_OK P6')
