"""During an active CLI subprocess, raw transcript must be visible on disk."""
import os,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.runner import execute
P=Path(__file__).resolve().parents[1]
os.environ['AUTOSHIFT_TEST_SANDBOX']='1'
with tempfile.TemporaryDirectory() as d:
    root=Path(d)/'repo';root.mkdir();state=Path(d)/'state';state.mkdir()
    agent=Path(d)/'agent.py';agent.write_text('''import sys,time
print('TRANSCRIPT_STARTED',flush=True)
time.sleep(.6)
print('TRANSCRIPT_COMPLETE',flush=True)
''')
    node={'id':'worker.testing','kind':'agent','role':'worker','goal':'transcript','tiers':[{'provider':'claude','model':'test'}],
          'sandbox':[str(P/'tests/stub-sandbox.sh')],'timeout':10}
    result={}
    def job():result.update(execute(node,1,node['tiers'][0],root,state,overrides={'claude':[sys.executable,str(agent)]}))
    t=threading.Thread(target=job);t.start()
    transcript=state/'raw/worker.testing-1.stdout'
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if transcript.exists() and 'TRANSCRIPT_STARTED' in transcript.read_text():break
        time.sleep(.02)
    else:raise AssertionError('No live running transcript')
    assert t.is_alive(),'transcript did not become visible until after worker finished'
    t.join(3)
    assert result['status']=='PASS' and 'TRANSCRIPT_COMPLETE' in transcript.read_text()
print('V8_TRANSCRIPT_OK running_stdout_stderr_are_real_files')
