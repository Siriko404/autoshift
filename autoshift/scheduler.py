"""Single-process deterministic dispatch, lane WIP, escalation and fail-closed recovery.
K2 K3 K5 K6 K7 K8 K10 [field §1,§3,§6,§7,§10 S35 S44 S56].
"""
import concurrent.futures
import hashlib
import os
import json
import signal
import time
from pathlib import Path
from .graph import byid
from .ledger import Journal,canonical
from .locks import Locks
from .quota import reading
from .runner import execute,terminate_children,writable_roots,pin_digest
from .doctrine import redact,owner_message

TERMINAL={'PASS','FAIL','BLOCKED','SKIP'}


def pinned_spec(n):
    """The pinned script of a locked gate (`trusted_gate`) or of a host step (`host`), else None."""
    return n.get('trusted_gate') if n['kind']=='gate' else n.get('host') if n['kind']=='code' else None


def gate_pins(graph):
    package=Path(__file__).resolve().parents[1]
    return {n['id']:pin_digest(pinned_spec(n),package) for n in graph['nodes'] if pinned_spec(n)}


class Engine:
    def __init__(self, graph, repo, state, overrides=None):
        self.g=graph;self.nodes=byid(graph);self.repo=Path(repo).resolve();self.dir=Path(state).resolve()
        # A hash chain is not authentication: never let an agent touch its journal.
        if self.dir.is_relative_to(self.repo):
            raise ValueError('unsafe state: journal must be outside --repo')
        for n in graph['nodes']:
            sandbox=n.get('sandbox') or []
            for ix,word in enumerate(sandbox):
                if word=='--rw' and ix+1<len(sandbox):
                    bind=((self.repo/n.get('cwd','.')).resolve()/sandbox[ix+1]).resolve()
                    if self.dir.is_relative_to(bind):
                        raise ValueError('unsafe state: journal under writable agent bind')
                    if n['kind']=='agent' and (self.repo/'.git').exists() and (self.repo/'.git').resolve().is_relative_to(bind):
                        raise ValueError('unsafe agent: writable bind includes .git')
        # No writable agent bind may cover a source of locked gate scripts.
        for gate in (x for x in graph['nodes'] if pinned_spec(x)):
            spec=pinned_spec(gate)
            trusted=(Path(__file__).resolve().parents[1] if spec['root']=='@package' else Path(spec['root']).resolve())
            if trusted.is_relative_to(self.repo):
                raise ValueError('unsafe gate: trusted source under writable worktree')
            for agent in (x for x in graph['nodes'] if x['kind']=='agent'):
                for i,word in enumerate(agent.get('sandbox',[])):
                    if word=='--rw' and i+1<len(agent['sandbox']):
                        dest=((self.repo/agent.get('cwd','.')).resolve()/agent['sandbox'][i+1]).resolve()
                        if trusted.is_relative_to(dest):raise ValueError('unsafe gate: trusted source writable by agent')
        self.j=Journal(self.dir);self.lock=Locks(self.dir);self.overrides=overrides or {}
        self.graph_hash=hashlib.sha256(canonical(graph)).hexdigest()
        pinned=self.j.state['graph_sha256']
        if pinned and pinned!=self.graph_hash:
            raise ValueError('graph revision refused: journalled graph sha256 differs; use revise')
        if not pinned:
            self.j.append('GRAPH','graph:initial',data={'sha256':self.graph_hash,'reason':'initial graph'})
        self.parents={n:[] for n in self.nodes}
        for e in graph['edges']:self.parents[e['to']].append(e)
        # Trusted gate content (entry, pinned acceptance tests) is journalled before any worker can run.
        for pin_node,digest in gate_pins(graph).items():
            have=self.j.state['pins'].get(pin_node)
            if have is None:self.j.append('PIN','pin:%s:%s'%(pin_node,digest),pin_node,{'sha256':digest})
            elif have!=digest:raise ValueError('trusted gate %s changed since it was pinned; review it and use revise'%pin_node)

    def recover(self):
        # External commands are not transactionally replayable. Log uncertainty;
        # never run a possibly executed command twice after a crash.
        for node,s in list(self.j.state['nodes'].items()):
            if s['status']=='RUNNING':
                self.j.append('UNCERTAIN','uncertain:%s:%s'%(node,s['attempt']),node,
                              {'reason':'driver died in-flight; verify effects and manually reconcile'})
                self.feedback('kill_recovery',node,{'attempt':s['attempt']},'human effect check required')
                self.j.append('ASK','ask-uncertain:%s:%s'%(node,s['attempt']),node,
                              {'question':'Verify effects and manually reconcile '+node})

    def feedback(self,source,node,observation,mechanical):
        prior=len(self.j.state.get('feedback',[]))+1
        self.j.append('FEEDBACK','feedback:'+source+':'+str(node)+':'+str(prior),node,
                      {'source':source,'node':node,'observation':redact(observation),'mechanical_check':mechanical})

    def dependencies(self, node):
        incoming=self.parents[node]
        if not incoming:return 'READY'
        status=self.j.state['nodes']
        if any(e['from'] not in status or status[e['from']]['status'] not in TERMINAL
               or (e['from'] in self.j.state['asks']
                   and self.j.state['asks'][e['from']]['answer'] is None) for e in incoming):
            return 'WAIT'
        if all(status[e['from']]['status'] in e.get('on',['PASS']) for e in incoming):return 'READY'
        return 'SKIP'

    def candidates(self):
        for node,n in self.nodes.items():
            existing=self.j.state['nodes'].get(node)
            if existing and existing['status'] != 'RETRY':continue
            if n['kind']=='wake':
                on=n.get('on',['start'])
                if 'start' not in on and not set(on)&set(self.j.state['signals']):continue
            d=self.dependencies(node)
            if d=='SKIP':self.j.append('SKIP','skip:'+node,node);continue
            if d=='READY':yield node,n

    def tier(self,n,prev):
        tiers=n.get('tiers',[])
        if not tiers:return None
        if prev and prev.get('tier') is not None:return prev['tier']
        return tiers[0]

    def next_retry(self,node,n):
        st=self.j.state['nodes'][node];history=st.get('history',[])
        if st['status'] == 'PASS':return
        if n['kind'] == 'ask':
            self.j.append('ASK','ask:'+node,node,{'question':n.get('goal','Human response required')})
            return
        # An explicit FAIL/BLOCKED edge handles that outcome; it is not exhaustion.
        if any(e['from']==node and st['status'] in e.get('on',['PASS']) for e in self.g['edges']):return
        tries=st['attempt'];tier=st.get('tier')
        tiers=n.get('tiers',[]); idx=tiers.index(tier) if tier in tiers else 0
        signature=st.get('failure_signature','')
        if signature.startswith('infra:'):
            self.feedback('infrastructure',node,{'signature':signature},'reader/runner problem: no model escalation')
            # Back off and retry the SAME tier; a provider outage must not buy a stronger model.
            if tries<n.get('max_attempts',3):
                time.sleep(min(.2*tries,1))
                self.j.append('RETRY','retry:infra:'+node+':'+str(tries),node,{'tier':tier})
            else:self.j.append('ASK','ask-infra:'+node+':'+str(tries),node,{'question':'Infrastructure failure; repair before retry '+node})
            return
        repeat=(len(history)>=2 and history[-1]['signature'] is not None
                and history[-1]['signature']==history[-2]['signature'])
        self.feedback('retry_signature',node,{'repeat':repeat,'attempt':tries,'tier':tier},
                      'equal consecutive failure signatures trigger configured escalation')
        repeat=self.j.state['feedback'][-1]['observation']['repeat']
        if tries >= n.get('max_attempts',len(tiers)*2 if tiers else 1):
            self.j.append('ASK','ask-exhausted:'+node+':'+str(tries),node,
                          {'question':'Task exhausted attempts '+node})
        elif tiers and repeat and idx<len(tiers)-1:
            ntier=tiers[idx+1]
            self.j.append('RETRY','retry:'+node+':'+str(tries),node,{'tier':ntier})
        elif tries < n.get('max_attempts',len(tiers)*2 if tiers else 1):
            if tiers and idx == len(tiers)-1 and repeat:
                self.j.append('ASK','ask-exhausted:'+node+':'+str(tries),node,
                              {'question':'Strongest tier repeatedly failed '+node})
            else:self.j.append('RETRY','retry:'+node+':'+str(tries),node,{'tier':tier})
        else:self.j.append('ASK','ask-exhausted:'+node+':'+str(tries),node,
                           {'question':'Task exhausted attempts '+node})

    def _run(self,node,n,attempt,tier,previous):
        return execute(n,attempt,tier,self.repo,self.dir,previous,self.overrides,self.j.state['pins'].get(node))

    def run(self, recover=True):
        if recover:self.recover()
        occupied={};futures={}
        executor=concurrent.futures.ThreadPoolExecutor(max_workers=self.g['wip'])
        try:
            while True:
                self.j.refresh()
                if self.j.state['stopped']:break
                for node,n in list(self.candidates()):
                    self.j.refresh()  # STOP from another process must halt this dispatch batch
                    if self.j.state['stopped']:break
                    if len(futures)>=self.g['wip']:break
                    lane=n.get('lane','default')
                    if lane in occupied:continue
                    # Concurrent worker lanes may never share a writable tree: compare the resolved
                    # --rw binds (or the whole cwd when there is no bind list), not just the cwd names.
                    def overlap(x,y):return x==y or x.is_relative_to(y) or y.is_relative_to(x)
                    mine=writable_roots(n,self.repo)
                    if n['kind']=='agent' and any(
                            old['kind']=='agent' and any(overlap(x,y) for x in mine for y in writable_roots(old,self.repo))
                            for _,old,_,_ in futures.values()):continue
                    if not self.lock.change('claim',node,n.get('paths',[])):continue
                    prev=self.j.state['nodes'].get(node,{})
                    attempt=prev.get('attempt',0)+1
                    tier=self.tier(n,prev)
                    provider=(tier.get('provider') if isinstance(tier,dict) else n.get('provider','claude')) if n['kind']=='agent' else 'code'
                    adm=reading(self.g.get('quota',{}),provider)
                    self.j.append('QUOTA','quota:%s:%s'%(node,attempt),data=adm)
                    if not adm['admitted']:
                        self.feedback('quota_stop',node,adm,'quota admission false')
                        self.lock.change('release',node)
                        if adm.get('state')=='READER_ERROR':
                            self.j.append('ASK','ask-quota-reader:'+node,node,{'question':'Quota reader failed; repair adapter then resume'})
                        else:self.j.append('STOP','quota-stop:'+node+':'+str(attempt),data={'reason':'quota exceeded'})
                        break
                    started=self.j.append('START','start:'+node+':'+str(attempt),node,
                                  {'attempt':attempt,'tier':tier,'handoff':str(self.dir/'handoffs')},
                                  require_running=True)
                    if not started:
                        self.lock.change('release',node)
                        break
                    # The START is durable before any effect. Restart cannot blindly retry.
                    previous=prev.get('evidence')
                    if prev.get('retry_feedback'):
                        previous={'status':'FAIL','prior_gates':[prev['retry_feedback']]}
                    if not previous:
                        failures=[]
                        for edge in self.parents[node]:
                            parent=self.j.state['nodes'].get(edge['from'],{})
                            if parent.get('status')=='FAIL':
                                failures.append(parent.get('evidence',{}))
                        if failures:previous={'status':'FAIL','prior_gates':[
                            {'signature':p.get('signature'),'stderr_tail':p.get('stderr_tail'),
                             'stdout_tail':p.get('stdout_tail'),'missing':p.get('missing')} for p in failures]}
                    futures[executor.submit(self._run,node,n,attempt,tier,previous)] = (node,n,lane,attempt)
                    occupied[lane]=node
                if not futures:
                    if self.j.state['stopped']:break
                    # Any unresolved asks, blocked nodes or wake events require explicit intervention.
                    break
                done,_=concurrent.futures.wait(futures,timeout=0.05,
                                                  return_when=concurrent.futures.FIRST_COMPLETED)
                for f in done:
                    node,n,lane,attempt=futures[f]
                    try:result=f.result()
                    except BaseException as exc:
                        result={'status':'BLOCKED','rc':None,'artifacts':[],'claims':[],
                                'signature':'runner-exception','error':repr(exc)}
                    result.update(node=node,attempt=attempt)
                    result=redact(result)
                    self.j.append('RESULT','result:'+node+':'+str(attempt),node,result)
                    del futures[f]  # Keep this future recoverable until its RESULT is durable.
                    if n['kind']=='gate':self.feedback('gate_result',node,{'status':result['status'],'rc':result['rc']},'rc and artifact verifier')
                    if n.get('role')=='audit':self.feedback('audit_finding',node,{'status':result['status']},'audit node gate outcome')
                    self.lock.change('release',node)
                    occupied.pop(lane,None)
                    if result['status']!='PASS':
                        signature=result.get('signature','')
                        handled=any(x['from']==node and 'FAIL' in x.get('on',['PASS']) for x in self.g['edges'])
                        group=None
                        if n['kind']=='gate' and result['status']=='FAIL' and not handled and not signature.startswith('infra:'):
                            # A quality failure of the gate re-runs its worker with the gate's error (C19).
                            # Infrastructure failures (signature infra:*) only re-run the gate, after backoff (C20).
                            for e in self.parents[node]:
                                pn=self.nodes[e['from']];ps=self.j.state['nodes'].get(e['from'],{})
                                if pn['kind']=='agent' and pn.get('role')=='worker' and ps.get('attempt',0)<pn.get('max_attempts',1):
                                    group=(e['from'],pn,ps);break
                        if group:
                            parent,pn,ps=group
                            # Escalation follows the GATE's failure signature: the same failure twice buys the next tier.
                            history=self.j.state['nodes'][node].get('history',[])
                            repeat=len(history)>=2 and history[-2].get('signature')==signature
                            tier=ps.get('tier');tiers=pn.get('tiers',[])
                            if repeat and tier in tiers and tiers.index(tier)+1<len(tiers):tier=tiers[tiers.index(tier)+1]
                            self.feedback('retry_signature',node,{'signature':signature,'repeat':repeat},'worker+gate failure signature')
                            self.j.append('RETRY','retry:worker-gate:'+parent+':'+str(ps.get('attempt',attempt)),parent,
                                          {'tier':tier,'gate_error':result.get('stderr_tail',''),'gate_signature':signature})
                            self.j.append('RETRY','retry:paired-gate:'+node+':'+str(attempt),node)
                        else:self.next_retry(node,n)
        finally:
            # A scheduler exception must not discard the results of children that were already started and
            # finish during shutdown. Every drained result is journalled on its own: one failed append (for
            # example a full disk) must not hide the others, and the original exception is never replaced.
            executor.shutdown(wait=True,cancel_futures=False)
            for future,(node,n,lane,attempt) in list(futures.items()):
                try:
                    try:result=future.result()
                    except BaseException as exc:
                        result={'status':'BLOCKED','rc':None,'artifacts':[],'claims':[],
                                'signature':'runner-exception','error':repr(exc)}
                    self.j.append('RESULT','result:'+node+':'+str(attempt),node,redact(dict(result,node=node,attempt=attempt)))
                except BaseException:pass  # nothing durable can be written; recovery marks the node UNCERTAIN
                try:self.lock.change('release',node)
                except BaseException:pass
                futures.pop(future,None)
        return self.summary()

    def summary(self):
        nodes=self.j.state['nodes']
        evidence={k:v.get('evidence',{}) for k,v in nodes.items()}
        outcome_groups={}
        for nid,state in nodes.items():
            t=state.get('tier') or {}
            name=str(t.get('provider','UNKNOWN'))+'/'+str(t.get('model','UNKNOWN')) if isinstance(t,dict) else str(t)
            weight=self.nodes.get(nid,{}).get('reasoning','low')
            label=weight+'|'+name
            metric=outcome_groups.setdefault(label,{'nodes':0,'passes':0,'failures':0,'attempts':0})
            metric['nodes']+=1;metric['passes']+=state['status']=='PASS'
            metric['failures']+=state['status'] in ('FAIL','BLOCKED')
            metric['attempts']+=state.get('attempt',0)
        return {'efficacy_by_level_agent':outcome_groups,
                'evidence_basis':'journal result status/attempt; no claim-based performance', 'usage':{k:e.get('usage',{'state':'UNKNOWN'}) for k,e in evidence.items()},
                'efficacy':{k:{'status':v['status'],'agent':str(v.get('tier')),'attempts':v.get('attempt',0)}
                            for k,v in nodes.items()},
                'passed':sum(v['status']=='PASS' for v in nodes.values()),
                'failed':sum(v['status'] in ('FAIL','BLOCKED') and not any(e['from']==nid and v['status'] in e.get('on',['PASS']) for e in self.g['edges']) for nid,v in nodes.items()),
                'stopped':self.j.state['stopped'], 'total':len(self.nodes),
                'pending':len(self.nodes)-sum(v['status'] in TERMINAL for v in nodes.values())}


def status(g,j):
    nodes=byid(g);st=j.state;group={}
    for nid,n in nodes.items():group.setdefault(n.get('lane','default'),[]).append((nid,n))
    lines=['AUTOSHIFT  supervisor: '+str(g.get('name','unnamed')),
           '  stopped: '+str(st['stopped'])+'  quota: '+json.dumps(st['quota'],sort_keys=True)]
    from .view import state_of
    for lane,items in group.items():
        lines.append('  lane '+lane)
        for name,n in items:
            s=st['nodes'].get(name)
            incoming=[e for e in g['edges'] if e['to']==name]
            d=state_of(name,g,st)
            lines.append('    '+name+' ['+(s['status'] if s else d)+'] '+n['kind'] + ((' reason='+str(s.get('reason') or st['asks'].get(name,{}).get('question') or s.get('evidence',{}).get('signature',''))) if s and s['status'] in ('BLOCKED','FAIL') else ''))
    for nid,n in nodes.items():
        usage=st['nodes'].get(nid,{}).get('evidence',{}).get('usage',{'state':'UNKNOWN'})
        if nid in st['nodes']:lines.append('  usage '+nid+': '+json.dumps(usage,sort_keys=True))
    lines.append('  asks: '+', '.join(k for k,v in st['asks'].items() if v['answer'] is None))
    for nid,n in nodes.items():
        if nid in st['asks'] and st['asks'][nid]['answer'] is None and (n.get('irreversible') or n.get('security_warning')):
            lines.append('  '+owner_message('Warning: This operation may change protected or sensitive data. Confirm its exact scope before approval.',
                                               security=True,irreversible=True))
    lines.append('  last events:')
    lines.extend('    #'+str(e['seq'])+' '+e['type']+' '+str(e['node'] or '') for e in st['events'][-5:])
    return redact('\n'.join(lines[:45]))
