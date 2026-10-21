"""Source mutants: branches in edge drawing and cost adoption rejected."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cases=[
 ('autoshift/view.py',"dot(*r['arrow'],'▼','edge')","pass",'tests/test_v4_graph.py'),
 ('autoshift/view.py',"textwrap.wrap(legend,width=width,break_long_words=True,break_on_hyphens=False)","wrap_words(legend,width)",'tests/test_v4_graph.py'),
 ('autoshift/view.py',"use_color=(a.color or (sys.stdout.isatty() and not a.no_color and 'NO_COLOR' not in os.environ))", "use_color=False",'tests/test_view.py'),
 ('autoshift/doctrine.py',"keep=bool(cost>0 and (key=='output_contract' or (agent_call and serialized_bytes(candidate)<baseline_bytes)))","keep=True",'tests/test_v4_cost.py'),
 ('autoshift/view.py',"return ''.join(ch if ' ' <= ch <= '~' else '?' for ch in str(value))","return str(value)",'tests/test_v4_graph.py'),
 ('autoshift/doctrine.py',"keep=bool(cost>0 and (key=='output_contract' or (agent_call and serialized_bytes(candidate)<baseline_bytes)))","keep=False",'tests/test_v4_cost.py'),
]
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','examples','tests','measurements'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 for filename,needle,replacement,test in cases:
  path=mirror/filename;raw=path.read_text();assert raw.count(needle)==1,filename
  baseline=subprocess.run([sys.executable,test],cwd=mirror,capture_output=True,text=True,timeout=40,
                          env={**os.environ,'PYTHONPATH':str(mirror)})
  assert baseline.returncode==0,'BASELINE_RED '+test+' '+baseline.stderr[-400:]
  path.write_text(raw.replace(needle,replacement))
  p=subprocess.run([sys.executable,test],cwd=mirror,capture_output=True,text=True,
                   env={**os.environ,'PYTHONPATH':str(mirror)},timeout=30)
  assert p.returncode!=0,('SURVIVED',filename,replacement)
  path.write_text(raw)
print('V4_MUTANTS_OK',len(cases),'/',len(cases))
