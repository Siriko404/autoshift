"""Nine source-code mutations: each must make its matching baseline test FAIL."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
mutants=[
 ('graph.py',"if n['id'] in ids:","if False:",'test_graph.py'),
 ('ledger.py',"if e['hash'] != digest:","if False:",'test_ledger.py'),
 ('locks.py',"if k != owner", "if False",'test_locks.py'),
 ('quota.py',"d['usage_pct'] < spec.get('limit_pct',80)","d['usage_pct'] <= spec.get('limit_pct',80)",'test_quota.py'),
 ('evidence.py',"if rc != 0 or missing:","if False:",'test_evidence.py'),
 ('providers.py',"if provider == 'agy':", "if False:",'test_providers.py'),
 ('runner.py',"status=verdict(rc,missing,timed_out)","status='PASS'",'test_runner.py'),
 ('scheduler.py',"if not self.lock.change('claim',node,n.get('paths',[])):continue", "if True:continue",'test_scheduler.py'),
 ('cli.py',"if a.node not in j.state['asks']:","if False:",'test_cli.py')
]
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','tests','examples','bin','adapters'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 for file,needle,replacement,test in mutants:
  target=mirror/'autoshift'/file
  raw=target.read_text()
  assert raw.count(needle)>=1,(file,raw.count(needle))
  baseline=subprocess.run(['python3',str(mirror/'tests'/test)],cwd=mirror,
              capture_output=True,text=True,timeout=40,env={**os.environ,'PYTHONPATH':str(mirror)})
  assert baseline.returncode==0,'BASELINE_RED '+test+' '+baseline.stderr[-400:]
  target.write_text(raw.replace(needle,replacement))
  result=subprocess.run(['python3',str(mirror/'tests'/test)],cwd=mirror,
                        capture_output=True,text=True,timeout=30,
                        env={**os.environ,'PYTHONPATH':str(mirror)})
  assert result.returncode != 0,'SOURCE MUTANT SURVIVED '+file
  target.write_text(raw)
print('MUTANTS_OK 9/9')
