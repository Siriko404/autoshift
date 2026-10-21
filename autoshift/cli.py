"""One driver CLI; journal mutations and plain status. K1 K3 K8 K13 [§10 S44]."""
import argparse
import hashlib
import fcntl
import json
import os
import uuid
from pathlib import Path
from .graph import load
from .ledger import Journal
from .scheduler import Engine,status


def main(argv=None):
    p=argparse.ArgumentParser(prog='autoshift')
    p.add_argument('--graph',default='graph.json')
    p.add_argument('--repo',default='.')
    p.add_argument('--state',default=None)
    sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('init','run','status','events','replay','stop','resume'):sub.add_parser(name)
    reconcile=sub.add_parser('reconcile');reconcile.add_argument('node');actions=reconcile.add_mutually_exclusive_group(required=True);actions.add_argument('--rerun',action='store_true');actions.add_argument('--accept',action='store_true')
    revise=sub.add_parser('revise');revise.add_argument('--reason',required=True)
    view=sub.add_parser('view');view.add_argument('--width',type=int);view.add_argument('--live',action='store_true');view.add_argument('--interval',type=float,default=.4);view.add_argument('--color',action='store_true');view.add_argument('--no-color',action='store_true')
    signal=sub.add_parser('signal');signal.add_argument('name')
    answer=sub.add_parser('answer');answer.add_argument('node');answer.add_argument('value')
    answer.add_argument('--outcome',choices=['PASS','FAIL','BLOCKED'],default='BLOCKED');answer.add_argument('--retry',action='store_true')
    a=p.parse_args(argv)
    g=load(a.graph);root=Path(a.state).expanduser() if a.state else Path.home()/'.local/state/autoshift'/hashlib.sha256(str(Path(a.repo).resolve()).encode()).hexdigest()[:18]
    if a.cmd=='view':
        from .view import main as view_main
        args=['--graph',a.graph,'--state',str(root)]
        if a.width:args+=['--width',str(a.width)]
        if a.live:args+=['--live','--interval',str(a.interval)]
        if a.color:args+=['--color']
        if a.no_color:args+=['--no-color']
        return view_main(args)
    if a.cmd not in ('status','events','replay'):root.mkdir(parents=True,exist_ok=True)
    if a.cmd=='revise':
        j=Journal(root)
        if any(v['status']=='RUNNING' for v in j.state['nodes'].values()):
            print('BLOCKED: in-flight work must finish before graph revision');return 3
        from .ledger import canonical
        new=hashlib.sha256(canonical(g)).hexdigest()
        j.append('GRAPH','graph:revision:'+uuid.uuid4().hex,data={'sha256':new,'reason':a.reason,'prior':j.state['graph_sha256']})
        print('GRAPH_REVISED');return 0
    if a.cmd=='init':
        j=Journal(root);print('AUTOSHIFT_INITIALIZED');return 0
    if a.cmd=='run':
        with (root/'driver.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:print('BLOCKED: another driver is active');return 3
            from .workspace import run as run_isolated
            result,outcome=run_isolated(g,a.repo,root,Engine)
            print(json.dumps(result,sort_keys=True))
            print(outcome)
            return 0 if result['failed']==0 and result['pending']==0 else 3
    if a.cmd in ('status','events','replay'):j=Journal(root, read_only=True)
    else:j=Journal(root)
    if a.cmd=='reconcile':
        st=j.state['nodes'].get(a.node)
        if not st or st['status']!='BLOCKED' or not st.get('reason','').startswith('driver died'):
            print('reconcile requires an UNCERTAIN node');return 2
        if a.accept and next((n['kind'] for n in g['nodes'] if n['id']==a.node),None)=='gate':
            print('a gate has no effect to accept: its verdict must be re-earned, use --rerun');return 2
        j.append('RECONCILE','reconcile:'+a.node+':'+uuid.uuid4().hex,a.node,
                 {'action':'accept' if a.accept else 'rerun','reason':'explicit operator effect verification'})
        print('RECONCILED');return 0
    if a.cmd=='status': print(status(g,j))
    elif a.cmd=='events':
        from .doctrine import redact
        for e in j.events[-20:]:print(json.dumps(redact(e),sort_keys=True))
    elif a.cmd=='replay':
        differences=j.diff();print('REPLAY_OK' if not differences else 'REPLAY_DIFF: '+str(differences))
        return 0 if not differences else 2
    elif a.cmd=='stop': j.append('STOP','stop:'+uuid.uuid4().hex);print('STOPPED')
    elif a.cmd=='resume': j.append('RESUME','resume:'+uuid.uuid4().hex);print('RESUMED')
    elif a.cmd=='signal': j.append('SIGNAL','signal:'+a.name+':'+uuid.uuid4().hex,data={'name':a.name});print('SIGNALED')
    elif a.cmd=='answer':
        if a.node not in j.state['asks']:print('no such open ask');return 2
        is_ask=any(n['id']==a.node and n['kind']=='ask' for n in g['nodes'])
        if a.outcome=='PASS' and not is_ask:
            print('only declared human ask nodes may be approved');return 2
        held=j.state['nodes'].get(a.node,{})
        if a.retry and str(held.get('reason','')).startswith('driver died'):
            print('an UNCERTAIN node may run again only through: reconcile NODE --rerun');return 2
        # Free text never triggers a transition: a retry needs the explicit --retry flag.
        j.append('ANSWER','answer:'+a.node+':'+uuid.uuid4().hex,a.node,
                 {'answer':a.value,'outcome':a.outcome,'retry':a.retry,'kind':'ask' if is_ask else 'escalation'})
        j.append('FEEDBACK','feedback:owner_answer:'+a.node+':'+uuid.uuid4().hex,a.node,
                 {'source':'owner_answer','node':a.node,'observation':{'outcome':a.outcome},
                  'mechanical_check':'declared human answer outcome'})
        print('ANSWERED')
    return 0


if __name__=='__main__':raise SystemExit(main())
