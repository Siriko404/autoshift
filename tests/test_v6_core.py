"""v6 regressions: independent agent lanes, durable crash exception drain, read-only journal and gate retry."""
import json,os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate
from autoshift.scheduler import Engine
from autoshift.ledger import Journal
from autoshift import cli
base=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 t=Path(d);repo=t/'repo';repo.mkdir()
 # A blocked evidence handler must drain and journal all completed futures.
 g=validate({'wip':2,'nodes':[{'id':x,'kind':'gate', 'cmd':['python3','-c',
        "from pathlib import Path;import time;time.sleep(.12);Path('"+x+".ok').write_text('ok')"],
        'artifacts':[x+'.ok'],'lane':x} for x in ('left','right')]})
 e=Engine(g,repo,t/'drain')
 def broken_feedback(*args,**kwargs):raise RuntimeError('injected mid-run scheduler exception')
 e.feedback=broken_feedback
 try:e.run();raise AssertionError('injected exception was swallowed')
 except RuntimeError as exc:assert 'injected' in str(exc)
 j=Journal(t/'drain')
 assert set(j.state['nodes'])=={'left','right'},j.state['nodes']
 assert all(v['status']=='PASS' for v in j.state['nodes'].values()),j.state['nodes']
 assert j.diff()==[]
 # A reader never creates or repairs journal state as a side effect.
 (t/'drain/state.json').unlink()
 r=Journal(t/'drain',read_only=True)
 assert len(r.events)>0 and not (t/'drain/state.json').exists()
 oldstate=t/'drain/state.json'
 # Two agent lanes deliberately use disjoint writable cwd roots.
 for name in ('west','east'):(repo/name).mkdir()
 writer=t/'writer.py'
 writer.write_text('import os,time;from pathlib import Path\nPath("identity").write_text(os.getcwd());time.sleep(.3);print("{}")\n')
 nodes=[]
 for name in ('west','east'):
  nodes.append({'id':name,'kind':'agent','role':'worker','lane':name,'cwd':name,
    'tiers':[{'provider':'claude','model':'stub'}],
    'sandbox':[str(base/'tests/stub-sandbox.sh')], 'max_attempts':1})
 parallel=validate({'wip':2,'nodes':nodes,'quota':{'claude':{'usage_pct':0,'limit_pct':80}}})
 e=Engine(parallel,repo,t/'parallel',{'claude':['python3',str(writer)]})
 assert e.run()['passed']==2
 assert (repo/'west/identity').read_text()!= (repo/'east/identity').read_text()
 starts={x['node']:x['seq'] for x in e.j.events if x['type']=='START'}
 results={x['node']:x['seq'] for x in e.j.events if x['type']=='RESULT'}
 assert starts['west']<results['east'] and starts['east']<results['west'], (starts,results)
 # Worker + gate are a retry group; quality error is carried and escalated.
 trusted=t/'trusted';trusted.mkdir()
 (trusted/'oracle.sh').write_text('''#!/bin/bash
set -e
[ "$(cat verified.txt 2>/dev/null)" = good ] || { echo 'QUALITY_ERROR_42' >&2; exit 1; }
printf yes > "$AUTOSHIFT_GATE_OUT/good.ok"
''')
 worker=t/'retry_worker.py'
 worker.write_text('''import json,sys
from pathlib import Path
h=json.loads(Path(sys.argv[1]).read_text())
if h['attempt']>1:
 assert 'QUALITY_ERROR_42' in json.dumps(h['previous']),h['previous']
if h['attempt']>2:Path('verified.txt').write_text('good')
print('{}')
''')
 rgraph=validate({'wip':1,'nodes':[
  {'id':'worker','kind':'agent','role':'worker','lane':'work','goal':'make verifier pass',
   'tiers':[{'provider':'claude','model':'weak'},{'provider':'claude','model':'strong'}],
   'max_attempts':3,'sandbox':[str(base/'tests/stub-sandbox.sh')]},
  {'id':'gate','kind':'gate','lane':'gate','cmd':['false'],
   'artifacts':['.autoshift-gate-output/good.ok'],
   'trusted_gate':{'root':str(trusted),'entry':'oracle.sh','code_paths':['verified.txt']}}],
  'edges':[{'from':'worker','to':'gate'}],
  'quota':{'claude':{'usage_pct':0,'limit_pct':80}}})
 re=Engine(rgraph,repo,t/'retry',{'claude':['python3',str(worker)]})
 rr=re.run()
 assert rr['failed']==0 and rr['passed']==2,rr
 assert re.j.state['nodes']['worker']['attempt']==3
 assert re.j.state['nodes']['worker']['tier']['model']=='strong'
 assert not [x for x in re.j.events if x['type']=='ASK']
 hh=json.loads((t/'retry/handoffs/worker-3.json').read_text())
 assert 'QUALITY_ERROR_42' in json.dumps(hh['previous'])
print('V6_CORE_OK drain read_only disjoint_concurrent_lanes paired_gate_feedback')
