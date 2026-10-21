"""File-store-only, deterministic DAG drawing. No viewer ever opens a Journal writer."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from .graph import load
from .ledger import Journal, canonical, reducer

STATUS_GLYPH={'PASS':'✓','FAIL':'✕','BLOCKED':'?','RUNNING':'●','RETRY':'↻',
              'SKIP':'−','READY':'○','tentative':'·'}
PALETTE={'PASS':'\x1b[32m','FAIL':'\x1b[31m','BLOCKED':'\x1b[33m',
         'RUNNING':'\x1b[36m','RETRY':'\x1b[35m','SKIP':'\x1b[90m',
         'READY':'\x1b[37m','tentative':'\x1b[90m','edge':'\x1b[90m',
         'heading':'\x1b[1;36m'}
RESET='\x1b[0m'


def read_only(state):
    """Check hash-chain and parse complete lines in memory; never repair on disk."""
    path=Path(state)/'events.jsonl'
    if not path.exists():return reducer([])
    events=[];prior='0'*64
    for line in path.read_bytes().split(b'\n'):
        if not line:continue
        try:e=json.loads(line)
        except ValueError:break  # concurrent writer's uncommitted final line
        if e.get('seq')!=len(events)+1 or e.get('previous')!=prior:
            raise ValueError('journal continuity failure')
        if e.get('hash')!=hashlib.sha256(canonical({k:v for k,v in e.items() if k!='hash'})).hexdigest():
            raise ValueError('journal hash mismatch')
        events.append(e);prior=e['hash']
    return reducer(events)


def state_of(node,graph,state):
    previous=state['nodes'].get(node)
    if previous:return previous['status']
    deps=[e for e in graph['edges'] if e['to']==node]
    if not deps:return 'READY'
    if all(e['from'] in state['nodes'] and state['nodes'][e['from']]['status']
           in e.get('on',['PASS']) for e in deps):return 'READY'
    return 'tentative'


def layers(graph):
    """Stable longest-path DAG rank: fanout siblings occupy the same rank."""
    depths={n['id']:0 for n in graph['nodes']}
    for _ in graph['nodes']:
        for e in graph['edges']:
            depths[e['to']]=max(depths[e['to']],depths[e['from']]+1)
    return [[n for n in graph['nodes'] if depths[n['id']]==d]
            for d in sorted(set(depths.values()))]


def safe_label(value):
    """Untrusted graph labels cannot move a terminal cursor or exceed cell widths."""
    return ''.join(ch if ' ' <= ch <= '~' else '?' for ch in str(value))


def wrap_words(value,width):
    import textwrap
    return textwrap.wrap(safe_label(value),width=max(3,width),break_long_words=True,
                         break_on_hyphens=False) or ['']


def node_text(n,state,width):
    s=state_of(n['id'],state['graph'],state['journal'])
    agent=n.get('agent','')
    tiers=n.get('tiers',[])
    if tiers and n['kind']=='agent':
        a=tiers[0]
        agent=(str(a.get('provider','?'))+'/'+str(a.get('model','?'))) if isinstance(a,dict) else str(a)
    category=('agent '+str(agent or 'owner-choice')+' / '+n.get('reasoning','med')) if n['kind']=='agent' else n['kind']+' / code'
    lines=wrap_words(n['id'],width)
    lines+=wrap_words(category,width)
    lines+=['%s %s' % (STATUS_GLYPH.get(s,'?'),s)]
    return lines,s


def layout(graph,state,width):
    """Return actual, testable box positions and port-to-port paths."""
    width=max(36,int(width))
    boxw=min(34,(width-12)//2)
    # Split overloaded ranks, without imposing an order on sibling dependencies.
    ranks=[r[i:i+2] for r in layers(graph) for i in range(0,len(r),2)]
    info={'graph':graph,'journal':state}
    boxes={};y=3
    for rank in ranks:
        longest=0
        for col,node in enumerate(rank):
            left=((width-boxw)//2 if len(rank)==1 else 6+col*(boxw+2))
            lines,s=node_text(node,info,boxw-4)
            longest=max(longest,len(lines))
            boxes[node['id']]={'x':left,'y':y,'w':boxw,'lines':lines,'status':s,'node':node}
        height=longest+2
        for node in rank:boxes[node['id']]['h']=height
        y+=height+5
    routes=[]
    for i,edge in enumerate(graph['edges']):
        src=boxes[edge['from']];dst=boxes[edge['to']]
        sx=src['x']+src['w']//2;tx=dst['x']+dst['w']//2
        sy=src['y']+src['h']-1;ty=dst['y']
        if ty<=sy:raise ValueError('graph layout requires DAG')
        # Long arcs travel in a dedicated clear left gutter, never through nodes.
        skipped=any(b['y']>sy and b['y']<ty for b in boxes.values())
        lane=(2+(i%3)) if skipped else tx
        start=sy+1;end=ty-1
        path=[(sx,sy),(sx,start)]
        if lane!=sx:path.append((lane,start))
        if end!=start:path.append((lane,end))
        if tx!=lane:path.append((tx,end))
        path.append((tx,ty-1))
        routes.append({'from':edge['from'],'to':edge['to'],
                       'on':tuple(edge.get('on',['PASS'])),'path':path,
                       'start':(sx,sy),'arrow':(tx,ty-1)})
    return boxes,routes,y


def _draw(graph,state,width):
    boxes,routes,height=layout(graph,state,width)
    rows=[[' ']*width for _ in range(height+1)]
    styles=[[None]*width for _ in rows]
    connections={}
    def dot(x,y,ch,style=None):
        if 0<=x<width and 0<=y<len(rows):
            rows[y][x]=ch
            if style:styles[y][x]=style
    def label(x,y,text,style=None):
        for i,ch in enumerate(text[:max(0,width-x)]):dot(x+i,y,ch,style)
    label(0,0,'AUTOSHIFT / '+safe_label(graph.get('name','unnamed'))[:width-12],'heading')
    label(0,1,'STOPPED' if state['stopped'] else 'ACTIVE','heading')
    for r in routes:
        path=r['path']
        for (x1,y1),(x2,y2) in zip(path,path[1:]):
            if x1!=x2 and y1!=y2:raise AssertionError('non-orthogonal edge')
            if x1==x2:
                rng=[(x1,v) for v in range(min(y1,y2),max(y1,y2)+1)]
            else:
                rng=[(v,y1) for v in range(min(x1,x2),max(x1,x2)+1)]
            for a,b in zip(rng,rng[1:]):
                connections.setdefault(a,set()).add(b)
                connections.setdefault(b,set()).add(a)
    for (x,y),neighbors in connections.items():
        up=(x,y-1) in neighbors;down=(x,y+1) in neighbors
        left=(x-1,y) in neighbors;right=(x+1,y) in neighbors
        glyph={(0,0,1,1):'─',(1,1,0,0):'│',(0,1,0,1):'┌',
               (0,1,1,0):'┐',(1,0,0,1):'└',(1,0,1,0):'┘',
               (1,1,1,0):'┤',(1,1,0,1):'├',(0,1,1,1):'┬',
               (1,0,1,1):'┴',(1,1,1,1):'┼'}.get((up,down,left,right),'│' if up or down else '─')
        dot(x,y,glyph,'edge')
    for r in routes:
        dot(*r['arrow'],'▼','edge')
        if r['on']!=('PASS',):
            mark='F' if r['on']==('FAIL',) else 'B' if r['on']==('BLOCKED',) else 'S' if r['on']==('SKIP',) else '*'
            dot(r['arrow'][0]+2,r['arrow'][1],mark,'edge')
    for b in boxes.values():
        x,y,w,h=b['x'],b['y'],b['w'],b['h']
        dot(x,y,'┌','edge');dot(x+w-1,y,'┐','edge')
        dot(x,y+h-1,'└','edge');dot(x+w-1,y+h-1,'┘','edge')
        for t in range(x+1,x+w-1):dot(t,y,'─','edge');dot(t,y+h-1,'─','edge')
        for t in range(y+1,y+h-1):dot(x,t,'│','edge');dot(x+w-1,t,'│','edge')
        for k,line in enumerate(b['lines']):label(x+2,y+k+1,line,b['status'])
        if any(r['from']==b['node']['id'] for r in routes):dot(x+w//2,y+h-1,'┴','edge')
        if any(r['to']==b['node']['id'] for r in routes):dot(x+w//2,y,'┬','edge')
    legend='● RUNNING  ✓ PASS  ✕ FAIL  ? BLOCKED  ↻ RETRY  ○ READY  · WAIT  ▼ DIRECTION  F FAIL-edge  B BLOCKED-edge  S SKIP-edge  * mixed-edge'
    bottom=max(b['y']+b['h'] for b in boxes.values())+2 if boxes else 3
    # Legend is trusted kernel text; preserve semantic Unicode glyphs.
    import textwrap
    for i,line in enumerate(textwrap.wrap(legend,width=width,break_long_words=True,break_on_hyphens=False)):
        if bottom+i<len(rows):label(0,bottom+i,line,'edge')
    pending=[k for k,v in sorted(state['asks'].items()) if v['answer'] is None]
    if pending:
        for i,line in enumerate(wrap_words('ASK '+','.join(pending),width)):
            if bottom+3+i<len(rows):label(0,bottom+3+i,line,'BLOCKED')
    # Trim line ends, retain internal gutters. Colorized form is the same geometry.
    return rows,styles,boxes,routes


def frame(graph,state,width=80,color=False):
    width=max(36,int(width))
    rows,styles,_,_=_draw(graph,state,width)
    output=[]
    for chars,paint in zip(rows,styles):
        end=len(''.join(chars).rstrip())
        active=None;line=''
        for ch,style in zip(chars[:end],paint[:end]):
            desired=PALETTE.get(style) if color else None
            if desired!=active:
                if active:line+=RESET
                if desired:line+=desired
                active=desired
            line+=ch
        if active:line+=RESET
        output.append(line)
    return '\n'.join(output).rstrip()+'\n'


def main(argv=None):
    p=argparse.ArgumentParser(prog='autoshift view')
    p.add_argument('--graph',required=True);p.add_argument('--state',required=True)
    p.add_argument('--width',type=int);p.add_argument('--live',action='store_true')
    p.add_argument('--interval',type=float,default=.4)
    palette=p.add_mutually_exclusive_group();palette.add_argument('--color',action='store_true')
    palette.add_argument('--no-color',action='store_true')
    a=p.parse_args(argv);g=load(a.graph)
    if a.live and not sys.stdout.isatty():
        print('live requires an attached terminal',file=sys.stderr);return 2
    use_color=(a.color or (sys.stdout.isatty() and not a.no_color and 'NO_COLOR' not in os.environ))
    while True:
        size=a.width or shutil.get_terminal_size((80,24)).columns
        rendered=frame(g,read_only(a.state),size,color=use_color)
        if not a.live:sys.stdout.write(rendered);return 0
        sys.stdout.write('\x1b[H\x1b[2J'+rendered);sys.stdout.flush()
        time.sleep(max(.1,a.interval))

if __name__=='__main__':raise SystemExit(main())
