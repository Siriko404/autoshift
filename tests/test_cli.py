import os,subprocess,sys,tempfile
from pathlib import Path
base=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 root=Path(d)/'repo';root.mkdir();g=base/'examples/g3-pipeline.json';state=root.parent/'state'
 args=['--graph',str(g),'--repo',str(root),'--state',str(state)]
 def call(op,*extra):
  return subprocess.run([str(base/'bin/autoshift')]+args+[op,*extra],capture_output=True,text=True,env=os.environ)
 assert call('init').returncode==0
 assert call('run').returncode==0
 assert 'REPLAY_OK' in call('replay').stdout
 assert 'supervisor' in call('status').stdout
 assert call('stop').returncode==0
 assert 'stopped: True' in call('status').stdout
 assert call('resume').returncode==0
 assert call('signal','wake-up').returncode==0
 assert call('answer','missing','x').returncode==2, 'invalid answer mutant survived'
print('CLI_OK')
