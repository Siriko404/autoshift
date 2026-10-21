"""G1 driver. Plan content is untrusted data; owner template is policy. One writer, serial tasks.

All transitions and wake IDs are durable. Never let an agent see the journal, approvals,
main checkout writable, or the common Git directory. Example flow, not kernel code.
"""
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import sys
from pathlib import Path
# Example flow, not kernel code: it lives in examples/g1-planner and uses the kernel as a library.
PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE))
from autoshift.ledger import Journal, canonical, write_atomic
from autoshift.runner import execute, pin_digest
from autoshift.quota import reading
from autoshift.doctrine import redact

IDENT = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.-]{0,63}$')
CLASSES = {'tests', 'tooling', 'plugin', 'wide'}
PLAN_KEYS = {'tasks'}
TASK_KEYS = {'id', 'goal', 'lane', 'paths', 'class', 'acceptance'}


def validate_settings(s):
    if not isinstance(s, dict) or set(s) != {'planner', 'task_template', 'queue_min', 'poll_seconds', 'stop'}:
        raise ValueError('G1 requires owner planner, task_template, queue_min, poll_seconds and stop')
    if not isinstance(s['queue_min'], int) or not 1 <= s['queue_min'] <= 64:
        raise ValueError('queue_min outside 1..64')
    if not isinstance(s['poll_seconds'], (int, float)) or not .1 <= s['poll_seconds'] <= 120:
        raise ValueError('poll_seconds outside .1..120')
    if set(s['stop']) != {'completed', 'max_plans'} or type(s['stop']['completed']) is not int or s['stop']['completed'] < 1 or type(s['stop']['max_plans']) is not int or s['stop']['max_plans'] < 1:
        raise ValueError('invalid stop conditions')
    p=s['planner'];t=s['task_template']
    if not isinstance(p, dict) or not p.get('tiers') or not isinstance(p.get('goal'),str):raise ValueError('planner requires goal and tiers')
    if not isinstance(t,dict) or not t.get('worker',{}).get('tiers') or not t.get('trusted_gate'):
        raise ValueError('task template requires owner worker and trusted gate')
    gate=t['trusted_gate'];root=gate.get('root','')
    if root!='@package' and (not isinstance(root,str) or not Path(root).is_absolute()):
        raise ValueError('owner trusted gate root must be absolute or @package')
    if not isinstance(gate.get('entry'),str) or not gate['entry'] or Path(gate['entry']).is_absolute() or '..' in Path(gate['entry']).parts:
        raise ValueError('invalid trusted gate entry')
    for k in ('code_paths','pin','args'):
        if not isinstance(gate.get(k,[]),list) or not all(isinstance(x,str) for x in gate.get(k,[])):
            raise ValueError('invalid trusted gate '+k)
    for x in gate.get('code_paths',[]):
        if Path(x).is_absolute() or '..' in Path(x).parts or x=='.' or any(p in ('tests','test','tools','harness','gate','.git') for p in Path(x).parts):
            raise ValueError('gate input is not code-only')
    if not isinstance(t.get('acceptance'),dict) or not t['acceptance']:
        raise ValueError('owner acceptance references required')
    for name,path in t['acceptance'].items():
        if not IDENT.fullmatch(name) or not isinstance(path,str) or Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('invalid acceptance reference')
    for kind in ('worker','planner'):
        n=t['worker'] if kind=='worker' else p
        if not isinstance(n['tiers'],list) or not all(isinstance(x,dict) and isinstance(x.get('provider'),str) and isinstance(x.get('model'),str) for x in n['tiers']):
            raise ValueError('invalid provider tiers')
    if not isinstance(t.get('allowed_paths'),list) or not t['allowed_paths'] or not all(isinstance(x,str) and x for x in t['allowed_paths']):
        raise ValueError('owner allowed_paths are required')
    if not isinstance(t.get('protected_paths',{}),dict):raise ValueError('owner protected_paths must be an object')
    for k,v in t.get('protected_paths',{}).items():
        if k not in ('plugin','wide') or not isinstance(v,list) or not all(isinstance(x,str) for x in v):
            raise ValueError('bad protected class configuration')
    for klass,audits in t.get('audits',{}).items():
        if klass not in CLASSES or not isinstance(audits,list) or not all(isinstance(a,dict) and a.get('tiers') for a in audits):
            raise ValueError('invalid class audits')
    return s


def validate_plan(plan, settings, known=()):
    if not isinstance(plan,dict) or set(plan)!=PLAN_KEYS or not isinstance(plan['tasks'],list):
        raise ValueError('planner may output only {tasks:[...]}')
    seen=set(known);out=[]
    for task in plan['tasks']:
        if not isinstance(task,dict) or set(task)!=TASK_KEYS:
            raise ValueError('planner task has forbidden/missing fields (never gates or commands)')
        if not IDENT.fullmatch(str(task['id'])) or task['id'] in seen:raise ValueError('duplicate/bad task id')
        seen.add(task['id'])
        if not isinstance(task['goal'],str) or not 1 <= len(task['goal']) <= 8192:raise ValueError('bad goal')
        if not IDENT.fullmatch(str(task['lane'])) or task['class'] not in CLASSES:raise ValueError('bad lane/class')
        paths=task['paths']
        if not isinstance(paths,list) or not paths or len(paths)>100:raise ValueError('missing task paths')
        for path in paths:
            if (not isinstance(path,str) or path.startswith('/') or '..' in Path(path).parts or
                    any(part in ('.git','tests','test','harness','gate') for part in Path(path).parts)):
                raise ValueError('path outside permissible code/tooling changes')
            if not any(fnmatch.fnmatchcase(path,scope) for scope in settings['task_template']['allowed_paths']):
                raise ValueError('path not authorized by owner template')
        # Risk class is owner-derived lower bound, not a planner-controlled way to auto-merge.
        protected=settings['task_template'].get('protected_paths',{})
        if any(any(fnmatch.fnmatchcase(path,mask) for mask in protected.get('plugin',[])) for path in paths):
            if task['class']!='plugin':raise ValueError('plugin path requires plugin approval class')
        elif any(any(fnmatch.fnmatchcase(path,mask) for mask in protected.get('wide',[])) for path in paths):
            if task['class']!='wide':raise ValueError('wide path requires wide approval class')
        if task['acceptance'] not in settings['task_template']['acceptance']:
            raise ValueError('unknown acceptance test reference')
        out.append(task)
    return out


def git(repo,*args,check=True):
    p=subprocess.run(['git','-C',str(repo),'-c','core.hooksPath=/dev/null',*args],capture_output=True,text=True)
    if check and p.returncode:raise RuntimeError('git '+args[0]+' rc '+str(p.returncode)+': '+p.stderr[-500:])
    return p.stdout.strip()


def sandbox(provider, path, readonly_git=False, audit=False):
    package=PACKAGE
    if os.environ.get('AUTOSHIFT_TEST_SANDBOX')=='1':
        return [str(package/'tests/stub-sandbox.sh')]
    flags=['@package/adapters/sandbox.sh','--provider',provider,'--ro' if audit else '--rw','.','--net','1']
    if readonly_git:flags+=['--ro',str(Path(path)/'.git')]
    return flags


class Production:
    def __init__(self, graph, repo, state, overrides=None):
        self.cfg=validate_settings(graph['production']);self.repo=Path(repo).resolve();self.dir=Path(state).resolve()
        if self.dir.is_relative_to(self.repo):raise ValueError('journal cannot be under repository')
        if not (self.repo/'.git').exists():raise ValueError('G1 requires a git repository')
        self.j=Journal(self.dir);self.overrides=overrides or {};self.quota=graph.get('quota',{})
        self.package=PACKAGE
        self.tpl=self.cfg['task_template']
        self.root=self.package if self.tpl['trusted_gate']['root']=='@package' else Path(self.tpl['trusted_gate']['root']).resolve()
        if self.root.is_relative_to(self.repo) or self.root.is_relative_to(self.dir):
            raise ValueError('trusted gate must be outside project and state')
        raw=canonical(graph);digest=hashlib.sha256(raw).hexdigest()
        if self.j.state['graph_sha256'] not in (None,digest):raise ValueError('graph revision refused; use revise')
        if not self.j.state['graph_sha256']:self.j.append('GRAPH','graph:initial',data={'sha256':digest,'reason':'production G1'})
        # Pin all trusted acceptance tests, validators and the gate before the planner writes a task.
        gate=self.tpl['trusted_gate'];self.gate_hash=pin_digest(gate,self.package)
        for p in self.tpl['acceptance'].values():
            f=(self.root/p).resolve()
            if not f.is_file() or not f.is_relative_to(self.root):raise ValueError('acceptance outside trusted root: '+p)
        digest=hashlib.sha256(canonical([self.gate_hash,[(k,hashlib.sha256((self.root/v).read_bytes()).hexdigest()) for k,v in sorted(self.tpl['acceptance'].items())]])).hexdigest()
        self.acceptance_hash=digest
        have=self.j.state['pins'].get('G1.acceptance')
        if have is not None and have!=digest:raise ValueError('trusted gate/acceptance changed; owner revision required')
        if have is None:self.j.append('PIN','pin:G1.acceptance:'+digest,'G1.acceptance',{'sha256':digest})
        git(self.repo,'rev-parse','HEAD')
        if git(self.repo,'status','--porcelain'):raise ValueError('G1 main checkout must be clean')

    def admit(self,provider,task):
        q=reading(self.quota,provider)
        self.j.append('QUOTA','g1:quota:'+task+':'+str(len(self.j.events)+1),data=q)
        if not q['admitted']:
            self.j.append('STOP','g1:quota-stop:'+task+':'+str(len(self.j.events)+1),data={'reason':'quota reading blocked','provider':provider})
            return False
        return True

    def record(self,task,stage,status,details=None):
        key='task:'+task+':'+stage+':'+status
        self.j.append('TASK',key,task,{'stage':stage,'status':status,**(details or {})})

    def notify(self,kind,detail=None):
        # Stable identity from the source event, not from wall-clock or model claims.
        predecessor=self.j.events[-1]['hash'] if self.j.events else '0'
        key='wake:'+kind+':'+predecessor[:24]
        self.j.append('WAKE',key,data={'kind':kind,'caused_by':predecessor,'detail':detail or ''})

    def plan(self):
        phase=len(self.j.state.get('plans',[]))+1
        pdir=self.dir/'planner-work';pdir.mkdir(exist_ok=True)
        (pdir/'plan.json').unlink(missing_ok=True)
        p=self.cfg['planner'];tier=p['tiers'][0]
        n={'id':'g1planner','kind':'agent','role':'planner','goal':p['goal'], 'tiers':p['tiers'],
           'sandbox':sandbox(tier['provider'],pdir),'artifacts':['plan.json'],'timeout':p.get('timeout',300)}
        if not self.admit(tier['provider'],'planner:'+str(phase)):return False
        self.j.append('START','planner:start:'+str(phase),'g1planner',{'attempt':phase,'tier':tier})
        result=execute(n,phase,tier,pdir,self.dir,overrides=self.overrides)
        self.j.append('RESULT','planner:result:'+str(phase),'g1planner',redact(dict(result,attempt=phase)))
        if result['status']!='PASS':
            self.j.append('ASK','planner:ask:'+str(phase),'g1planner',{'question':'Planner failed: inspect transcript'})
            return False
        path=pdir/'plan.json'
        try:
            if path.stat().st_size>1024*1024:raise ValueError('plan too large')
            content=json.loads(path.read_text())
            tasks=validate_plan(content,self.cfg,self.j.state.get('tasks',{}))
        except (OSError,ValueError,UnicodeError,TypeError) as exc:
            self.j.append('FEEDBACK','planner:invalid:'+str(phase),data={'source':'plan_validator','error':str(exc)[:500]})
            self.j.append('ASK','planner:invalid-ask:'+str(phase),'g1planner',{'question':'Rejected invalid plan; owner review'})
            return False
        raw=canonical(content);sha=hashlib.sha256(raw).hexdigest()
        # Store exact revision bytes read-only under journal root; replay uses journalled full task data.
        write_atomic(self.dir/('plan-%04d.json'%phase),raw+b'\n')
        self.j.append('PLAN','plan:rev:'+str(phase),data={'revision':phase,'sha256':sha,'tasks':tasks,'trigger_seq':self.j.events[-1]['seq']})
        return True

    def worktree(self,task):
        tid=task['id'];path=self.dir.parent/(self.dir.name+'-worktrees')/tid
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.is_relative_to(self.repo):raise ValueError('worktree inside main forbidden')
        if path.exists():
            # On crash, never silently reuse a possibly modified/partly run worktree.
            raise RuntimeError('worktree already exists; operator reconciliation required')
        base=git(self.repo,'rev-parse','HEAD')
        git(self.repo,'worktree','add','--detach',str(path),base)
        self.record(tid,'WORKTREE','PASS',{'base':base,'path':str(path)})
        return path,base

    def changes(self,wt,task):
        # Only code within declared paths is admitted. No symlink, submodule, or .git mutation.
        extra=git(wt,'ls-files','--others','--exclude-standard').splitlines()
        for f in extra:
            path=(wt/f)
            if path.is_symlink() or not path.is_file():raise ValueError('untracked symlink or non-file')
            git(wt,'add','-N','--',f)
        names=git(wt,'diff','--name-only','HEAD','--').splitlines()
        if not names:raise ValueError('worker produced no change')
        for name in names:
            path=wt/name
            if name=='.git' or any(x in ('tests','test','gate','harness') for x in Path(name).parts):
                raise ValueError('untrusted test/gate modification')
            if not any(fnmatch.fnmatchcase(name,pattern) for pattern in task['paths']):
                raise ValueError('change outside task paths: '+name)
            if path.is_symlink():raise ValueError('symlink edit forbidden')
        raw=subprocess.run(['git','-C',str(wt),'diff','--no-ext-diff','--binary','HEAD','--'],capture_output=True,check=True).stdout
        if not raw:raise ValueError('empty diff')
        return raw,hashlib.sha256(raw).hexdigest(),names

    def agent(self,role,tid,wt,base,settings,attempt=1,extra=''):
        tier=settings['tiers'][min(attempt-1,len(settings['tiers'])-1)]
        node={'id':role+'.'+tid,'kind':'agent','role':'audit' if role.startswith('audit') else role,'goal':extra,'base_sha':base,
              'tiers':settings['tiers'],'sandbox':sandbox(tier['provider'],wt,True,role.startswith('audit')),
              'timeout':settings.get('timeout',900),'max_attempts':len(settings['tiers'])}
        # Audit writes verdict outside worktree, and runner injects verdict directory only for audit role.
        if not self.admit(tier['provider'],role+':'+tid+':'+str(attempt)):
            return {'status':'BLOCKED','signature':'quota-denied'}
        self.j.append('START','g1:'+role+':'+tid+':'+str(attempt),node['id'],{'attempt':attempt,'tier':tier})
        r=execute(node,attempt,tier,wt,self.dir,overrides=self.overrides)
        self.j.append('RESULT','g1:result:'+role+':'+tid+':'+str(attempt),node['id'],redact(dict(r,attempt=attempt)))
        return r

    def task(self,task):
        tid=task['id'];stage=self.j.state.get('tasks',{}).get(tid,{})
        if stage.get('status') in ('MERGED','WAIT_APPROVAL','FAIL','BLOCKED'):return
        try:
            wt,base=self.worktree(task)
            worker=self.tpl['worker']
            for attempt in range(1,len(worker['tiers'])+1):
                result=self.agent('worker',tid,wt,base,worker,attempt,task['goal'])
                if result['status']=='PASS':break
                if attempt==len(worker['tiers']):
                    self.record(tid,'WORKER','FAIL',{'signature':result.get('signature')})
                    self.notify('strongest_failure',tid);return
            self.record(tid,'WORKER','PASS')
            patch,digest,names=self.changes(wt,task)
            self.record(tid,'PREPARE','PASS',{'paths':names,'patch_sha256':digest})
            self.gate(wt,task)
            self.record(tid,'GATE','PASS',{'patch_sha256':digest})
            for ix,auditor in enumerate(self.tpl.get('audits',{}).get(task['class'],[]),1):
                result=self.agent('audit'+str(ix),tid,wt,base,auditor,1,'Independently review: '+task['goal'])
                if result['status']!='PASS':raise ValueError('independent audit failed '+str(ix))
                self.record(tid,'AUDIT'+str(ix),'PASS')
            self.merge_check(wt,base,task,digest)
            self.record(tid,'MERGE_CHECK','PASS',{'patch_sha256':digest})
            if task['class'] in ('plugin','wide') and not self.approved(tid,base,digest):
                self.record(tid,'WAIT_APPROVAL','WAIT',{'base':base,'patch_sha256':digest})
                self.j.append('ASK','approval:'+tid,tid,{'question':'Owner approval file required for '+task['class']+' merge'})
                return
            self.merge(wt,base,tid,patch,digest)
        except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
            self.record(tid,'FAILED','FAIL',{'error':str(exc)[:600]})
            self.notify('strongest_failure',tid)

    def check_trusted(self):
        gate=self.tpl['trusted_gate']
        current=pin_digest(gate,self.package)
        tests=[(k,hashlib.sha256((self.root/v).read_bytes()).hexdigest())
               for k,v in sorted(self.tpl['acceptance'].items())]
        return (current==self.gate_hash and
                hashlib.sha256(canonical([current,tests])).hexdigest()==self.acceptance_hash)

    def gate(self,wt,task):
        # Fail closed if any owner-held test changed after pinning.
        if not self.check_trusted():
            raise ValueError('trusted gate bytes changed')
        tid=task['id'];spec=self.tpl['trusted_gate'];gateout=self.dir/'.autoshift-gate-output'
        gateout.mkdir(exist_ok=True)
        artifact='.autoshift-gate-output/'+tid+'.GATE.md'
        n={'id':'g1gate.'+tid,'kind':'gate','cmd':['false'],'trusted_gate':spec,
           'artifacts':[artifact],'timeout':self.tpl.get('gate_timeout',2400),
           'task_id':tid,'acceptance_path':str((self.root/self.tpl['acceptance'][task['acceptance']]).resolve())}
        # Gate sees only code_under_test and trusted root, never worker-written tests or project gate.
        self.j.append('START','g1:gate:start:'+tid,n['id'],{'attempt':1,'tier':None})
        r=execute(n,1,None,wt,self.dir,pin=self.gate_hash)
        self.j.append('RESULT','g1:gate:'+tid,'g1gate.'+tid,redact(dict(r,attempt=1)))
        if r['status']!='PASS':raise ValueError('trusted gate failed: '+str(r.get('signature')))

    def merge_check(self,wt,base,task,digest):
        raw,new_sha,names=self.changes(wt,task)
        if digest!=new_sha:raise ValueError('worktree changed after gate')
        if git(self.repo,'rev-parse','HEAD')!=base:raise ValueError('main moved after worktree pin')
        if git(self.repo,'status','--porcelain'):raise ValueError('main dirty at merge check')
        p=subprocess.run(['git','-C',str(self.repo),'apply','--check','--binary','-'],input=raw,capture_output=True)
        if p.returncode:raise ValueError('hash-locked patch does not apply: '+p.stderr.decode(errors='replace')[-300:])
        self.j.append('MERGE_CHECK','merge-check:'+task['id'],task['id'],{'base':base,'patch_sha256':digest,'paths':names})

    def approved(self,tid,base,digest):
        path=self.dir/'approvals'/(tid+'.json')
        try:
            if path.is_symlink() or path.stat().st_size>4096:return False
            doc=json.loads(path.read_text())
            return doc=={'task':tid,'base':base,'patch_sha256':digest,'approve':True}
        except (ValueError,OSError):return False

    def merge(self,wt,base,tid,patch,digest):
        if hashlib.sha256(patch).hexdigest()!=digest:raise ValueError('patch hash mismatch')
        if not self.check_trusted():
            raise ValueError('trusted gate or acceptance changed before merge')
        if git(self.repo,'rev-parse','HEAD')!=base or git(self.repo,'status','--porcelain'):
            raise ValueError('main changed before merge')
        current,now,_=self.changes(wt,self.j.state['tasks'][tid]['task'])
        if now!=digest or current!=patch:raise ValueError('patch mutated after check')
        p=subprocess.run(['git','-C',str(self.repo),'apply','--index','--binary','-'],input=patch,capture_output=True)
        if p.returncode:raise ValueError('apply blocked: '+p.stderr.decode(errors='replace')[-250:])
        try:
            git(self.repo,'-c','user.name=AutoShift','-c','user.email=autoshift@localhost','commit','-m','AutoShift: '+tid)
        except Exception:
            git(self.repo,'reset','--hard',base)
            raise
        head=git(self.repo,'rev-parse','HEAD')
        self.j.append('MERGE','merge:'+tid,tid,{'base':base,'patch_sha256':digest,'head':head})
        self.record(tid,'MERGED','MERGED',{'head':head})
        self.notify('milestone',tid)

    def pending(self):
        return [t for t in self.j.state.get('tasks',{}).values() if t['status']=='QUEUED']

    def resume_approvals(self):
        for tid,s in list(self.j.state.get('tasks',{}).items()):
            if s['status']!='WAIT_APPROVAL':continue
            details=s['details'];base=details['base'];digest=details['patch_sha256']
            if not self.approved(tid,base,digest):continue
            wt=Path(s['worktree'])
            try:
                patch,now,_=self.changes(wt,s['task'])
                if now!=digest:raise ValueError('approval no longer matches worktree')
                self.merge_check(wt,base,s['task'],digest)
                self.merge(wt,base,tid,patch,digest)
                self.j.append('ANSWER','approval:answered:'+tid,tid,{'answer':'approval-file-validated','outcome':'PASS'})
                self.notify('ask_answered',tid)
            except (ValueError,OSError,RuntimeError) as exc:self.record(tid,'FAILED','FAIL',{'error':str(exc)})

    def run(self,follow=False,max_ticks=None):
        # One driver lock is taken by cli. Bounded polling, no busy-loop, no hidden background processes.
        last_seq=0;ticks=0
        while True:
            self.j.refresh()
            if self.j.state['stopped']:break
            if len([t for t in self.j.state.get('tasks',{}).values() if t['status']=='MERGED'])>=self.cfg['stop']['completed']:
                self.j.append('STOP','g1:completed',data={'reason':'completed target'});break
            self.resume_approvals()
            queue=self.pending()
            plans=self.j.state.get('plans',[])
            pending_wake=any(e['type']=='WAKE' and e['seq']> (plans[-1].get('trigger_seq',0) if plans else 0)
                             for e in self.j.events)
            low=len(queue)<self.cfg['queue_min']
            if len(plans)<self.cfg['stop']['max_plans'] and (low or pending_wake):
                # Planner is re-armed on queue-low AND on external wake even if queue is full.
                token=(low,len(queue),pending_wake)
                if token!=getattr(self,'_last_low',None):
                    self._last_low=token
                    if low:self.notify('queue_low',str(len(queue)))
                    self.plan();queue=self.pending()
            if queue:self.task(queue[0]['task'])
            else:
                if not follow:break
                if len(self.j.state.get('plans',[]))>=self.cfg['stop']['max_plans']:
                    self.j.append('STOP','g1:max-plans',data={'reason':'maximum plan revisions reached'});break
                time.sleep(self.cfg['poll_seconds'])
            ticks+=1
            if max_ticks is not None and ticks>=max_ticks:break
            if not follow and not self.pending():break
        merged=sum(t['status']=='MERGED' for t in self.j.state.get('tasks',{}).values())
        if merged>=self.cfg['stop']['completed'] and not self.j.state['stopped']:
            self.j.append('STOP','g1:completed',data={'reason':'completed target'})
        waiting=sum(t['status']=='WAIT_APPROVAL' for t in self.j.state.get('tasks',{}).values())
        stopped_for_goal=merged>=self.cfg['stop']['completed']
        open_failure=any(e['type']=='ASK' and e.get('node')=='g1planner' and
                         self.j.state['asks'].get('g1planner',{}).get('answer') is None for e in self.j.events)
        failures=sum(t['status']=='FAIL' for t in self.j.state.get('tasks',{}).values())
        if open_failure or self.j.state['stopped'] and not stopped_for_goal:failures+=1
        return {'merged':merged,'pending':len(self.pending())+waiting,'stopped':self.j.state['stopped'],
                'failed':failures}
