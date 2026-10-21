"""A check sees only the environment variables its trusted_gate declares in env, plus the kernel's own."""
import os,sys,tempfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
os.environ.pop('AUTOSHIFT_TEST_SANDBOX',None)
from autoshift.runner import _sandbox_for
from autoshift.graph import validate
with tempfile.TemporaryDirectory() as d:
    root=Path(d)/'repo';(root/'src').mkdir(parents=True);state=Path(d)/'state';state.mkdir()
    def gate(env):return {'id':'g','kind':'gate','cmd':['false'],'artifacts':['.autoshift-gate-output/x'],
                          'trusted_gate':{'root':'@package','entry':'examples/hello/check.sh','code_paths':['src'],**({'env':env} if env is not None else {})}}
    args=_sandbox_for(gate(['MY_TOOL_HOME']),root,root,state)
    pairs={args[i+1] for i,x in enumerate(args) if x=='--env'}
    assert 'MY_TOOL_HOME' in pairs and 'AUTOSHIFT_GATE_OUT' in pairs
    args=_sandbox_for(gate(None),root,root,state)
    assert not any(x.startswith('IGI') or x=='AUTOSHIFT_IGI_SANDBOX' for x in args),'no project-specific names in the kernel'
    for bad in (['lower'],['A B'],'NOT_A_LIST'):
        try:validate({'nodes':[gate(bad)],'edges':[]})
        except ValueError:pass
        else:raise AssertionError('bad env accepted: '+repr(bad))
print('GATE_ENV_OK')
