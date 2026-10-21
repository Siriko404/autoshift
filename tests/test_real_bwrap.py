"""Real namespace isolation smoke; no stub counts as verification."""
import shutil,subprocess,sys,tempfile
from pathlib import Path
base=Path(__file__).resolve().parents[1]
if not shutil.which('bwrap'):
 print('SKIP_NEEDS_BWRAP')
 raise SystemExit(77)
with tempfile.TemporaryDirectory() as d:
 result=subprocess.run(['bash',str(base/'adapters/sandbox.sh'),'--ro',d,'--net','0','--',
                        'sh','-c','test "$AUTOSHIFT_SANDBOX" = 1 && ! touch denied'],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,(result.stderr,result.returncode)
print('REAL_BWRAP_OK')
# The trusted gate really executes under a read-only view of code under test.
# Run with the test stub flag unset: this check must never accept the stub.
import os
sys.path.insert(0,str(base))
from autoshift.graph import validate
from autoshift.scheduler import Engine
with tempfile.TemporaryDirectory() as d:
 t=Path(d);repo=t/'repo';repo.mkdir()
 (repo/'source.py').write_text('ORIGINAL\n')
 locked=t/'trusted';locked.mkdir()
 (locked/'verify.sh').write_text('''#!/bin/bash
set -e
if touch source.py 2>/dev/null; then echo 'GATE_WORKTREE_WRITABLE' >&2; exit 9; fi
printf 'ok' > "$AUTOSHIFT_GATE_OUT/readonly.ok"
''')
 graph=validate({'nodes':[{'id':'readonly','kind':'gate','cmd':['false'],
    'artifacts':['.autoshift-gate-output/readonly.ok'],
    'trusted_gate':{'root':str(locked),'entry':'verify.sh','code_paths':['source.py']}}]})
 old=os.environ.pop('AUTOSHIFT_TEST_SANDBOX',None)
 try:
  e=Engine(graph,repo,t/'state');result=e.run()
 finally:
  if old is not None:os.environ['AUTOSHIFT_TEST_SANDBOX']=old
 assert result['passed']==1,(result,e.j.state['nodes'])
 assert (repo/'source.py').read_text()=='ORIGINAL\n'
 assert not (repo/'.autoshift-gate-output').exists()
 assert (t/'state/.autoshift-gate-output/readonly.ok').read_text()=='ok'
print('REAL_GATE_READONLY_OK')
