"""Every directed source-to-target connector must occupy tested raster cells."""
import re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import load
from autoshift.ledger import reducer
from autoshift.view import frame,layout,_draw,state_of,safe_label
base=Path(__file__).resolve().parents[1]
assert safe_label('abc\x1b[2J\r\n')=='abc?[2J??'
assert '\x1b' not in frame({'name':'\x1b[2Jhidden','nodes':[],'edges':[]},reducer([]),46)
for name in ('g1-production','g2-ralph','g3-pipeline'):
 g=load(base/'examples'/(name+'.json'))
 for width in (46,92):
  state=reducer([]);boxes,routes,_=layout(g,state,width)
  assert len(routes)==len(g['edges'])
  assert sorted((r['from'],r['to'],r['on']) for r in routes)==sorted(
   (r['from'],r['to'],tuple(r.get('on',['PASS']))) for r in g['edges'])
  rows,styles,_,_= _draw(g,state,width)
  canvas=[''.join(r) for r in rows]
  assert len(set(boxes))==len(g['nodes'])
  for route in routes:
   src=boxes[route['from']];dst=boxes[route['to']]
   assert src['y']<dst['y'] and route['arrow'][1]==dst['y']-1
   assert canvas[route['arrow'][1]][route['arrow'][0]]=='▼',route
   assert route['start']==(src['x']+src['w']//2,src['y']+src['h']-1)
   for (x,y),(xx,yy) in zip(route['path'],route['path'][1:]):
    assert x==xx or y==yy,route
    if x==xx:coords=((x,t) for t in range(min(y,yy),max(y,yy)+1))
    else:coords=((t,y) for t in range(min(x,xx),max(x,xx)+1))
    for px,py in coords:
     assert (canvas[py][px] in '│─┌┐└┘├┤┬┴┼▼'), (name,route,(px,py),canvas[py][px])
  if name=='g2-ralph':
   fail_edge=next(r for r in routes if r['on']==('FAIL',))
   assert canvas[fail_edge['arrow'][1]][fail_edge['arrow'][0]+2]=='F'
  plain=frame(g,state,width);color=frame(g,state,width,color=True)
  assert re.sub(r'\x1b\[[0-9;]*m','',color)==plain
  assert '\x1b[1;36m' in color and '\x1b[90m' in color
  assert frame(g,state,width)==plain
  assert max(len(row) for row in plain.splitlines())<=width
  assert '● RUNNING' in plain and '✓ PASS' in plain and '▼ DIRECTION' in plain, 'missing semantic legend'
  for n in g['nodes']:
   b=boxes[n['id']]
   assert b['status']==state_of(n['id'],g,state)
 if name=='g1-production':
  assert boxes['workers.item0']['y']==boxes['workers.item1']['y']
  assert boxes['workers.item0']['x']<boxes['workers.item1']['x']
  assert boxes['join_workers']['y']>max(boxes[x]['y'] for x in ('workers.item0','workers.item1'))
print('V4_GRAPH_OK')
