"""Portable doctrine guards. Copy THIS file to v2/tests to show red before v3.
No imported kernel module is needed until each guard executes, so failures are visible.
"""
import json,os,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
checks={}
def test(name,source):
 p=subprocess.run([sys.executable,'-c',source],cwd=root,text=True,capture_output=True,
                  env={**os.environ,'PYTHONPATH':str(root)},timeout=12)
 checks[name]={'passed':p.returncode==0,'rc':p.returncode,'error':p.stderr[-180:].replace('\n',' ')}
test('D1 lint must reject invalid compression levels', '''
from autoshift.doctrine import lint
assert lint('No fillers.', 'unknown-level') is False
assert lint('No fillers.', 'lite') is True
''')
test('D1 compression must keep every safety negation', '''
import re
import autoshift.doctrine as dt
text='Do not delete the backup; only read it.'
assert dt.shorten(text)=='Do not delete backup; only read it.'
# Make the filler step try to drop a negation. The guard must refuse the candidate.
dt.FILLER=re.compile(r'\\b(?:not|only)\\b',re.I)
assert dt.shorten(text)==text,dt.shorten(text)
''')
test('D1 cost receipts', '''
from pathlib import Path
from autoshift.runner import execute
import tempfile
with tempfile.TemporaryDirectory() as d:
 x=execute({'id':'n','kind':'code','cmd':['python3','-c','print(0)']},1,None,d,Path(d)/'state')
 assert x['text_receipts']['goal']['injected_bytes'] >= 0
''')
test('D2 contradictory node', '''
from autoshift.graph import validate
try:validate({'nodes':[{'id':'bad','kind':'code','determinism':'judgment','cmd':['true']}]})
except ValueError:pass
else:raise AssertionError('kind/determinism mismatch accepted')
''')
test('D3 unknown usage', '''
from autoshift.runner import execute
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory() as d:
 r=execute({'id':'one','kind':'code','cmd':['python3','-c','print(123)']},1,None,d,Path(d)/'state')
 assert r['usage']['state']=='UNKNOWN'
''')
test('D3 redaction', '''
from autoshift.runner import execute
from pathlib import Path
import tempfile,json
with tempfile.TemporaryDirectory() as d:
 r=execute({'id':'one','kind':'code','cmd':['python3','-c','print("token=topsecret123")']},1,None,d,Path(d)/'state')
 assert 'topsecret123' not in json.dumps(r)
''')
test('D3 feedback', '''
from autoshift.graph import validate
from autoshift.scheduler import Engine
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as d:
 g=validate({'nodes':[{'id':'gate','kind':'gate','cmd':['python3','-c','from pathlib import Path;Path("ok").write_text("ok")'],'artifacts':['ok']}]})
 p=Path(d)/'repo';p.mkdir();e=Engine(g,p,Path(d)/'state');e.run()
 assert any(x['source']=='gate_result' for x in e.j.state['feedback'])
''')
test('D4 viewer command', '''
import subprocess,sys,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as d:
 p=subprocess.run([sys.executable,'-m','autoshift','--graph','examples/g3-pipeline.json','--state',d,'view','--width','46'],capture_output=True,text=True)
 assert p.returncode==0 and '▼' in p.stdout and '┌' in p.stdout
 assert not list(Path(d).iterdir())
''')
test('D1 injected work pattern', '''
from autoshift.runner import execute
from pathlib import Path
import tempfile,json
with tempfile.TemporaryDirectory() as d:
 r=execute({'id':'one','kind':'code','cmd':['python3','-c','print(123)']},1,None,d,Path(d)/'state')
 h=json.loads(Path(r['handoff']).read_text())
 assert 'work_pattern' in h and 'output_contract' in h
''')
test('D1 owner auto clarity', '''
from autoshift.doctrine import owner_message
assert owner_message('Warning: irreversible deletion. Do not proceed.',irreversible=True)=='Warning: irreversible deletion. Do not proceed.'
''')
test('D2 explicit G1 classification', '''
import json
from pathlib import Path
g=json.loads(Path('examples/g1-production.json').read_text())
assert all('determinism' in x and 'reasoning' in x for x in g['nodes'])
''')
for name,x in checks.items():print(('GREEN' if x['passed'] else 'RED'),name,x['error'])
if not all(x['passed'] for x in checks.values()):raise SystemExit(1)
print('DOCTRINE_GUARDS_OK',len(checks))
