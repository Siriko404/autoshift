"""Real source mutations with green baseline; no in-memory self-certifying predicates."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cases=[
 ("return SECRET.sub('[REDACTED]', value)","return value",'test_doctrine.py'),
 ("and candidate_quality and after['bytes']+overhead < before['bytes']+overhead)","and candidate_quality and False)",'test_doctrine.py'),
 ("if level not in ('ultra','lite'):return False",'if True:return True','test_doctrine_guards.py'),
 ("if NEGATIONS.findall(text) != NEGATIONS.findall(candidate):return text",'if False:return text','test_doctrine_guards.py'),
 ("if type(cost) in (float,int) and cost>=0 and cost<1e12:","if True:",'test_doctrine.py'),
]
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','tests','examples','bin','adapters','measurements','docs'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 target=mirror/'autoshift/doctrine.py'
 for needle,mutation,test in cases:
  raw=target.read_text();assert raw.count(needle)==1,(needle,raw.count(needle))
  command=[sys.executable,'tests/'+test]
  base=subprocess.run(command,cwd=mirror,env={**os.environ,'PYTHONPATH':str(mirror)},capture_output=True,text=True,timeout=45)
  assert base.returncode==0,'BASELINE_RED '+test+' '+base.stderr[-400:]
  target.write_text(raw.replace(needle,mutation))
  red=subprocess.run(command,cwd=mirror,env={**os.environ,'PYTHONPATH':str(mirror)},capture_output=True,text=True,timeout=45)
  assert red.returncode!=0,'SOURCE_MUTANT_SURVIVED '+needle
  target.write_text(raw)
print('DOCTRINE_SOURCE_MUTANTS_OK 5/5')
