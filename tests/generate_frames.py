"""Create deterministic public acceptance snapshots. Does not contact providers."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import load
from autoshift.ledger import Journal
from autoshift.view import frame,read_only
base=Path(__file__).resolve().parents[1]
for name in ('g1-production','g2-ralph','g3-pipeline'):
 graph=load(base/'examples'/(name+'.json'))
 for phase in ('idle','running','failed','asked','stopped'):
  with tempfile.TemporaryDirectory() as d:
   j=Journal(d);node=graph['nodes'][0]['id']
   if phase in ('running','failed','asked'):
    j.append('START','start:1',node,{'attempt':1,'tier':None})
   if phase in ('failed','asked'):
    j.append('RESULT','result:1',node,{'status':'FAIL','rc':1,'signature':'boom'})
   if phase=='asked':j.append('ASK','ask:1',node,{'question':'Need approval'})
   if phase=='stopped':j.append('STOP','stop:1')
   for width in (46,92):
    prefix=base/'tests/frames'/(name+'-'+phase+'-'+str(width))
    prefix.with_suffix('.txt').write_text(frame(graph,read_only(d),width))
    (base/'tests/frames'/(prefix.name+'-color.ansi')).write_text(
        frame(graph,read_only(d),width,color=True))
print('GENERATED_FRAMES_OK')
