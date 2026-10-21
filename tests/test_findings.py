"""Independent per-finding executable repro cases; accept one case ID or run all.

Each case is designed to FAIL on unpatched v1 and PASS on v2.
"""
import json,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import validate
from autoshift.ledger import Journal
from autoshift.runner import execute
from autoshift.scheduler import Engine,status
from autoshift import cli


def history(root):
 g=validate({'nodes':[{'id':'n','kind':'agent','tiers':['cheap','strong'],'max_attempts':4}]})
 e=Engine(g,root,root.parent/'st')
 for i in (1,2):
  e.j.append('START','s'+str(i),'n',{'attempt':i,'tier':'cheap'})
  e.j.append('RESULT','r'+str(i),'n',{'status':'FAIL','signature':'same'})
  e.next_retry('n',g['nodes'][0])
 assert e.j.state['nodes']['n']['tier']=='strong'
 assert len(e.j.state['nodes']['n']['history'])==2


def ceiling(root):
 g=validate({'nodes':[{'id':'n','kind':'agent','tiers':['cheap','strong'],'max_attempts':2}]})
 e=Engine(g,root,root.parent/'st')
 e.j.append('START','s2','n',{'attempt':2,'tier':'cheap'})
 e.j.append('RESULT','r2','n',{'status':'FAIL','signature':'same'})
 # Inject a prior identical failure into the next_retry input (isolated transition).
 e.j.state['nodes']['n']['history']=[{'signature':'same'},{'signature':'same'}]
 e.next_retry('n',g['nodes'][0])
 assert e.j.state['nodes']['n']['status']!='RETRY'
 assert any(x['type']=='ASK' for x in e.j.events)


def stale(root):
 (root/'gate.ok').write_text('previous')
 r=execute({'id':'g','kind':'gate','cmd':['python3','-c','pass'],
            'artifacts':['gate.ok']},1,None,root,root.parent/'st')
 assert r['status']=='FAIL' and '<stale:gate.ok>' in r['missing']


def stop(root):
 j=Journal(root.parent/'st');j.append('STOP','stop')
 assert j.append('START','start','n',{'attempt':1},require_running=True) is False
 assert j.state['nodes']=={}


def readiness(root):
 g=validate({'nodes':[{'id':'a','kind':'code','cmd':['false']},
                      {'id':'b','kind':'code','cmd':['true']}],
             'edges':[{'from':'a','to':'b','on':['PASS']}]})
 j=Journal(root.parent/'st');j.append('START','start','a',{'attempt':1})
 j.append('RESULT','result','a',{'status':'FAIL'})
 assert 'b [tentative]' in status(g,j)


def uniqueness(root):
 g=root/'g.json';g.write_text(json.dumps({'nodes':[{'id':'a','kind':'code','cmd':['true']}]}))
 class DummyJournal:
  events=[]
  keys=[]
  def __init__(self,root):pass
  def append(self,kind,key,*args,**kwargs):self.keys.append(key)
 with patch.object(cli,'Journal',DummyJournal):
  for i in range(2):
   assert cli.main(['--graph',str(g),'--state',str(root.parent/'st'),'stop'])==0
 assert len(set(DummyJournal.keys))==2, 'distinct STOP commands need distinct identities'


def approval(root):
 g=validate({'nodes':[{'id':'permit','kind':'ask'},
                      {'id':'after','kind':'code','cmd':['python3','-c','pass']}],
             'edges':[{'from':'permit','to':'after'}]})
 graph=root/'g.json';graph.write_text(json.dumps(g))
 binroot=Path(__file__).resolve().parents[1]
 args=[sys.executable,'-m','autoshift','--graph',str(graph),'--repo',str(root),'--state',str(root.parent/'st')]
 first=subprocess.run(args+['run'],cwd=binroot,capture_output=True,text=True,timeout=12)
 assert first.returncode==3
 ans=subprocess.run(args+['answer','permit','approved','--outcome','PASS'],cwd=binroot,
                    capture_output=True,text=True,timeout=12)
 assert ans.returncode==0,ans.stderr
 last=subprocess.run(args+['run'],cwd=binroot,capture_output=True,text=True,timeout=12)
 assert last.returncode==0,last.stderr
 assert Journal(root.parent/'st').state['nodes']['after']['status']=='PASS'

CASES={'history':history,'ceiling':ceiling,'stale':stale,'stop':stop,
       'readiness':readiness,'uniqueness':uniqueness,'approval':approval}
requested=sys.argv[1:] or list(CASES)
assert all(c in CASES for c in requested)
for name in requested:
 with tempfile.TemporaryDirectory() as d:
  repo=Path(d)/'repo';repo.mkdir();CASES[name](repo)
print('FINDINGS_OK '+','.join(requested))
