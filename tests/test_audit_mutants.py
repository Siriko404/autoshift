"""Call-2 targeted source mutations: each must turn the added regression test red."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
mutants=[
 ('graph.py',"and any(overlaps(p, q) for p in match for q in n.get('paths', []))",
  "and False",'path-risk-audit'),
 ('ledger.py',"'history':previous.get('history', [])","'history':[]",'retry-history'),
 ('ledger.py',"if require_running and self.state['stopped']:","if False and require_running and self.state['stopped']:",'stop-admission'),
 ('runner.py',"if old_hashes.get(item['path']) == item['sha256'] and not fresh:","if False:",'gate-freshness'),
 ('scheduler.py',"if tries >= n.get('max_attempts',len(tiers)*2 if tiers else 1):","if False:",'retry-ceiling'),
 ('scheduler.py',"and self.j.state['asks'][e['from']]['answer'] is None)", "and False)",'ask-dependency'),
 ('view.py',"in e.get('on',['PASS']) for e in deps)", "in TERMINAL for e in deps)",'status-readiness'),
 ('ledger.py',"s['nodes'][n]['status'] = ('RETRY' if d.get('retry') else d.get('outcome','BLOCKED'))", "s['nodes'][n]['status'] = 'BLOCKED'",'explicit-human-outcome'),
]
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','tests','examples','bin','adapters'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 for file,needle,replacement,name in mutants:
  path=mirror/'autoshift'/file
  raw=path.read_text();assert raw.count(needle)==1,(name,raw.count(needle))
  target_test='tests/test_graph.py' if name=='path-risk-audit' else 'tests/test_audit_regressions.py'
  baseline=subprocess.run([sys.executable,target_test],cwd=mirror,capture_output=True,text=True,timeout=40,
                          env={**os.environ,'PYTHONPATH':str(mirror)})
  assert baseline.returncode==0,'BASELINE_RED '+name+' '+baseline.stderr[-400:]
  path.write_text(raw.replace(needle,replacement))
  p=subprocess.run([sys.executable,
         'tests/test_graph.py' if name=='path-risk-audit' else 'tests/test_audit_regressions.py'],cwd=mirror,
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=40,
                   env={**os.environ,'PYTHONPATH':str(mirror)})
  assert p.returncode!=0,'SURVIVED '+name
  path.write_text(raw)
print('AUDIT_MUTANTS_OK 8/8')
