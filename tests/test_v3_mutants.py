"""Actual v3 source mutations in isolated mirrors. Red means test rejected bug."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
mutants=[
 ('doctrine.py',"return SECRET.sub('[REDACTED]', value)","return value",'redaction','tests/test_doctrine_guards.py'),
 ('doctrine.py',"keep=bool(original_quality and candidate_quality and after['bytes']+overhead < before['bytes']+overhead)",
  'keep=True','paired-cost','tests/test_doctrine.py'),
 ('graph.py',"if n['determinism'] != expected:raise ValueError('node kind contradicts determinism')",
  'if False:raise ValueError(\'node kind contradicts determinism\')','ownership','tests/test_doctrine_guards.py'),
 ('runner.py',"'stdout_tail':redact(stdout[-500:])","'stdout_tail':stdout[-500:]",'secret-tail','tests/test_doctrine_guards.py'),
 ('ledger.py',"elif kind == 'FEEDBACK':s['feedback'].append(d)","elif kind == 'FEEDBACK':pass",'feedback','tests/test_doctrine_guards.py'),
 ('runner.py',"receipts=prepare_fields(details,state,agent_call=n['kind']=='agent')","receipts={}",
  'receipt','tests/test_doctrine_guards.py'),
 ('scheduler.py',"repeat=self.j.state['feedback'][-1]['observation']['repeat']",
  'repeat=False','feedback-routing','tests/test_doctrine.py'),
 ('scheduler.py',"self.feedback('kill_recovery',node,{'attempt':s['attempt']},'human effect check required')",
  'pass','kill-feedback','tests/test_feedback_coverage.py'),
 ('scheduler.py',"self.feedback('quota_stop',node,adm,'quota admission false')",
  'pass','quota-feedback','tests/test_feedback_coverage.py'),
 ('scheduler.py',"if n.get('role')=='audit':self.feedback('audit_finding',node,{'status':result['status']},'audit node gate outcome')",
  "if n.get('role')=='audit':pass",'audit-feedback','tests/test_feedback_coverage.py'),
 ('scheduler.py',"if n['kind']=='gate':self.feedback('gate_result',node,{'status':result['status'],'rc':result['rc']},'rc and artifact verifier')",
  "if n['kind']=='gate':pass",'gate-feedback','tests/test_feedback_coverage.py'),
 ('cli.py',"j.append('FEEDBACK','feedback:owner_answer:'",
  "if False:j.append('FEEDBACK','feedback:owner_answer:'",'owner-feedback','tests/test_feedback_coverage.py'),
 ('view.py',"dot(*r['arrow'],'▼','edge')","pass",'viewer-frame','tests/test_v4_graph.py')]
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','adapters','examples','bin','tests','docs','measurements'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 for file,needle,mutation,name,test in mutants:
  path=mirror/'autoshift'/file
  raw=path.read_text();assert raw.count(needle)==1,(name,raw.count(needle))
  baseline=subprocess.run([sys.executable,test],cwd=mirror,capture_output=True,text=True,timeout=40,
                          env={**os.environ,'PYTHONPATH':str(mirror)})
  assert baseline.returncode==0,'BASELINE_RED '+name+' '+baseline.stderr[-400:]
  path.write_text(raw.replace(needle,mutation))
  p=subprocess.run([sys.executable,test],cwd=mirror,stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,text=True,timeout=20,env={**os.environ,'PYTHONPATH':str(mirror)})
  assert p.returncode!=0, 'SURVIVED '+name
  path.write_text(raw)
print('V3_MUTANTS_OK',len(mutants),'/',len(mutants))
