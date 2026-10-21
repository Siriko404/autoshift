"""C14: simulated full disk. RLIMIT_FSIZE makes every write past N bytes fail with EFBIG (like ENOSPC for the journal).
Whatever N is, a restart must replay clean, never invent a PASS, and `reconcile` must be able to finish the run."""
import json,os,resource,subprocess,sys,tempfile
from pathlib import Path
base=Path(__file__).resolve().parents[1]
BIN=str(base/'bin/autoshift')
env={**os.environ,'AUTOSHIFT_TEST_SANDBOX':'1'}


def limited(n):
    def apply():resource.setrlimit(resource.RLIMIT_FSIZE,(n,n))
    return apply


uncertain_seen=0;crashed=0
with tempfile.TemporaryDirectory() as d:
    t=Path(d)
    graph={'wip':2,'nodes':[{'id':x,'kind':'code','lane':x,'cmd':['python3','-c',"import time;time.sleep(.5);open('%s.ok','w').write('1')"%x],
                             'artifacts':[x+'.ok']} for x in ('a','b')]}
    gf=t/'g.json';gf.write_text(json.dumps(graph))
    for i,limit in enumerate(range(5200,9800,650)):
        repo=t/('repo%d'%i);repo.mkdir();state=t/('state%d'%i)
        args=[BIN,'--graph',str(gf),'--repo',str(repo),'--state',str(state)]
        first=subprocess.run(args+['run'],env=env,capture_output=True,text=True,timeout=60,preexec_fn=limited(limit))
        crashed+=first.returncode not in(0,3)
        again=subprocess.run(args+['run'],env=env,capture_output=True,text=True,timeout=60)
        assert subprocess.run(args+['replay'],env=env,capture_output=True,text=True,timeout=30).stdout.strip()=='REPLAY_OK',(limit,)
        sys.path.insert(0,str(base))
        from autoshift.ledger import Journal
        nodes=Journal(state).state['nodes']
        for node,s in nodes.items():
            if s['status']=='PASS':assert (repo/(node+'.ok')).exists(),('PASS without its artifact',limit,node)
        for node,s in list(nodes.items()):
            if s['status']=='BLOCKED' and str(s.get('reason','')).startswith('driver died'):
                uncertain_seen+=1
                r=subprocess.run(args+['reconcile',node,'--rerun'],env=env,capture_output=True,text=True,timeout=30);assert r.returncode==0,r.stderr
        final=subprocess.run(args+['run'],env=env,capture_output=True,text=True,timeout=60)
        j=Journal(state)
        assert final.returncode==0 and all(v['status']=='PASS' for v in j.state['nodes'].values()) and len(j.state['nodes'])==2,(limit,final.stdout[-300:],j.state['nodes'])
        assert j.diff()==[] and (repo/'a.ok').exists() and (repo/'b.ok').exists()
assert crashed>=3 and uncertain_seen>=1,('the sweep never hit a full disk',crashed,uncertain_seen)
print('V7_ENOSPC_OK crashed=%d uncertain_then_reconciled=%d'%(crashed,uncertain_seen))
