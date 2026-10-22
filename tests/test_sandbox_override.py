"""A step's own `sandbox` list may start only with the package sandbox. Text elsewhere in the list must not pass."""
import os,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
os.environ.pop('AUTOSHIFT_TEST_SANDBOX',None)
from autoshift.runner import _sandbox_for
PKG=str(P/'adapters/sandbox.sh')
with tempfile.TemporaryDirectory() as d:
    root=Path(d)/'repo';root.mkdir();state=Path(d)/'state';state.mkdir()
    def node(sb):return {'id':'a','kind':'agent','sandbox':sb}
    ok=_sandbox_for(node(['@package/adapters/sandbox.sh','--rw','.']),root,root,state)
    assert ok[0]==PKG and ok[1:]==['--rw','.'],ok
    assert _sandbox_for(node([PKG,'--net','1']),root,root,state)[0]==PKG
    for bad in (['/bin/sh','-c','id','sandbox.sh'],['/bin/sh','-c','echo sandbox.sh'],['env','sandbox.sh'],[],
                '@package/adapters/sandbox.sh',['/tmp/evil/adapters/sandbox.sh','--rw','.']):
        try:_sandbox_for(node(bad),root,root,state)
        except ValueError:continue
        raise AssertionError('unsandboxed command accepted: '+repr(bad))
print('SANDBOX_OVERRIDE_OK')
