import json,os,pty,signal,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import load
from autoshift.ledger import Journal
from autoshift.scheduler import status
from autoshift.view import frame,read_only,state_of,layout
base=Path(__file__).resolve().parents[1]
frames=base/'tests/frames'
for n in ('g1-production','g2-ralph','g3-pipeline'):
 g=load(base/'examples'/(n+'.json'))
 for phase in ('idle','running','failed','asked','stopped'):
  with tempfile.TemporaryDirectory() as d:
   j=Journal(d)
   node=g['nodes'][0]['id']
   if phase in ('running','failed','asked'):
    j.append('START','start:1',node,{'attempt':1,'tier':None})
   if phase=='failed' or phase=='asked':
    j.append('RESULT','result:1',node,{'status':'FAIL','rc':1,'signature':'boom'})
   if phase=='asked':j.append('ASK','ask:1',node,{'question':'Need approval'})
   if phase=='stopped':j.append('STOP','stop:1')
   for width in (46,92):
    rendered=frame(g,read_only(d),width)
    path=frames/(n+'-'+phase+'-'+str(width)+'.txt')
    assert path.exists() and path.read_text()==rendered,str(path)
    assert max(map(len,rendered.splitlines()))<=width, (n,phase,width)
    boxes,routes,_=layout(g,read_only(d),width)
    assert len(boxes)==len(g['nodes']) and len(routes)==len(g['edges'])
    assert rendered.count('▼')>=len(set(r['arrow'] for r in routes))
    coloured=frames/(n+'-'+phase+'-'+str(width)+'-color.ansi')
    assert coloured.exists() and coloured.read_text()==frame(g,read_only(d),width,color=True)
    for nn in g['nodes']:
     assert state_of(nn['id'],g,j.state) in status(g,j)
   if phase=='running':
    old=frame(g,read_only(d),92)
    j.append('RESULT','result:2',node,{'status':'PASS','rc':0})
    assert frame(g,read_only(d),92)!=old
    assert read_only(d)['nodes'][node]['status']=='PASS'
    assert j.diff()==[]
# A viewer never writes in an empty directory, even at first frame.
with tempfile.TemporaryDirectory() as d:
 g=load(base/'examples/g3-pipeline.json')
 assert '┌' in frame(g,read_only(d),50)
 assert not list(Path(d).iterdir())
# One command prints a complete frame without tty and without writing state.
with tempfile.TemporaryDirectory() as d:
 g=base/'examples/g3-pipeline.json';args=[sys.executable,'-m','autoshift',
     '--graph',str(g),'--repo',d,'--state',d+'/journal','view','--width','46']
 p=subprocess.run(args,cwd=base,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 assert p.returncode==0 and '▼' in p.stdout and 'prepare' in p.stdout
 assert not Path(d,'journal').exists()
 colour=subprocess.run(args+['--color'],cwd=base,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 mono=subprocess.run(args+['--no-color'],cwd=base,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 assert colour.returncode==0 and '\x1b[' in colour.stdout and '▼' in colour.stdout
 assert mono.returncode==0 and '\x1b[' not in mono.stdout and mono.stdout==p.stdout
 # Live viewer kill with PTY mid-run must not stop driver.
 slow=Path(d,'slow.json')
 slow.write_text(json.dumps({'nodes':[{'id':'slow','kind':'code','cmd':[sys.executable,'-c',
    'import time;time.sleep(1.5);open("done","w").write("yes")'],'artifacts':['done']}]}))
 work_repo=Path(d)/'work';work_repo.mkdir()
 driver=subprocess.Popen([sys.executable,'-m','autoshift','--graph',str(slow),'--repo',str(work_repo),
     '--state',d+'/journal','run'],cwd=base,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 master,slave=pty.openpty()
 viewer=subprocess.Popen([sys.executable,'-m','autoshift','--graph',str(slow),'--repo',str(work_repo),
    '--state',d+'/journal','view','--live','--width','46'],cwd=base,stdin=slave,
    stdout=slave,stderr=slave,start_new_session=True)
 os.close(slave);time.sleep(.3);viewer.kill();viewer.wait(timeout=4);os.close(master)
 out,err=driver.communicate(timeout=12)
 assert driver.returncode==0,(out,err)
 j=Journal(d+'/journal')
 assert j.diff()==[] and j.state['nodes']['slow']['status']=='PASS'
 assert not j.state['stopped']
print('VIEW_OK')
