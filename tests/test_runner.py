import json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.runner import execute
base=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 root=Path(d);state=root/'state'
 scenarios=[
   ('no-git',['git','rev-parse','HEAD'],['ok'],False),
   ('pipefail',['bash','-o','pipefail','-c','false | cat; exit ${PIPESTATUS[0]}'],['ok'],False),
   ('missing',['python3','-c','print("ALL TESTS PASSED")'],['nonexistent'],False),
   ('timeout',['python3','-c','import time;time.sleep(2)'],['ok'],True)
 ]
 for i,(name,cmd,art,timeout) in enumerate(scenarios):
   n={'id':name,'kind':'gate','cmd':cmd,'artifacts':art,'timeout':.03 if timeout else 2}
   r=execute(n,1,None,root,state)
   assert r['status'] in ('FAIL','BLOCKED'),name+' mutant survived: '+str(r)
 # Simulated file system exhaustion: journal/runner must not fake successful transition.
 from autoshift import ledger
 old=ledger.os.fsync
 try:
   def full(fd):raise OSError(28,'No space left on device')
   ledger.os.fsync=full
   try:ledger.write_atomic(root/'full','ok'.encode());raise AssertionError('ENOSPC mutant survived')
   except OSError as e:assert e.errno==28
 finally:ledger.os.fsync=old
print('RUNNER_OK')
