"""Fresh agent and deterministic gate/code process execution. K4 K5 K9 K11 [§5,§9 S22,S25]."""
import ctypes
import hashlib
import json
import os
import re
import shutil
import signal
from stat import S_ISREG
import subprocess
import threading
from pathlib import Path
from .evidence import collect,verdict
from .ledger import write_atomic
from .providers import command
from .doctrine import redact, prepare_fields, digest_previous, usage_from, WORK_PATTERNS, OUTPUT_CONTRACT

_RUNNING=set();_MU=threading.Lock()
# Provider-side outages look like ordinary failures (rc 1). They are infrastructure, not model quality.
INFRA_TEXT=re.compile(r'(?i)rate.?limit|too many requests|\b429\b|overloaded|\b50[234]\b|quota|credit balance|not logged in|please log ?in|login required|unauthori[sz]ed|authentication|ECONNRESET|temporar(?:y|ily) unavailable')


def writable_roots(n, root):
    """Resolved directories an agent node can write: its --rw binds, or the whole cwd if it has no bind list."""
    work=(Path(root)/n.get('cwd','.')).resolve();sandbox=n.get('sandbox') or []
    roots=[(work/sandbox[i+1]).resolve() for i,x in enumerate(sandbox[:-1]) if x=='--rw']
    return roots or [work]


def pin_digest(spec, package):
    """sha256 over the files a trusted gate is made of. Journalled before any worker runs (C06)."""
    source=package if spec['root']=='@package' else Path(spec['root']).resolve()
    wanted=[spec['entry'],*spec.get('pin',[])] if spec['root']=='@package' else ['.']
    h=hashlib.sha256();count=0
    for rel in sorted(wanted):
        top=(source/rel).resolve()
        if not top.is_relative_to(source) or not top.exists():raise ValueError('trusted gate pin path missing: '+rel)
        for f in sorted([top] if top.is_file() else (x for x in top.rglob('*') if x.is_file() and '__pycache__' not in x.parts)):
            count+=1
            if count>5000:raise ValueError('trusted gate pin too large')
            h.update(str(f.relative_to(source)).encode()+b'\0'+hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def terminate_children():
    with _MU:
        for p in list(_RUNNING):
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass


def _die_with_parent():
    # Parent death is a SIGKILL too: a Python signal handler cannot help.
    parent = os.getppid()
    libc=ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid()!=parent:
        os._exit(127)


def _sandbox_for(n, root, work, state):
    custom=n.get('sandbox')
    if custom and 'stub-sandbox.sh' in str(custom):
        if os.environ.get('AUTOSHIFT_TEST_SANDBOX') != '1':
            raise ValueError('test-only sandbox may not run outside regression suite')
        return custom
    if custom and n['kind']=='gate':
        raise ValueError('gate sandbox is kernel-owned; remove custom sandbox')
    if custom:
        # Only the package's own sandbox may be the program that runs. Arguments after it are its options.
        # (Matching the text 'sandbox.sh' anywhere in the list let any command run outside the sandbox.)
        package_sandbox=str(Path(__file__).resolve().parents[1]/'adapters/sandbox.sh')
        if isinstance(custom,list) and custom and custom[0] in ('@package/adapters/sandbox.sh',package_sandbox):
            return [package_sandbox if x=='@package/adapters/sandbox.sh' else x for x in custom]
        raise ValueError('unknown sandbox executable')
    if os.environ.get('AUTOSHIFT_TEST_SANDBOX')=='1':
        return [str(Path(__file__).resolve().parents[1]/'tests/stub-sandbox.sh')]
    sandbox=Path(__file__).resolve().parents[1]/'adapters/sandbox.sh'
    if n['kind']=='gate':
        out=Path(state)/'.autoshift-gate-output'
        out.mkdir(parents=True,exist_ok=True)
        t=n.get('trusted_gate') or {}
        res=Path(__file__).resolve().parents[1] if t.get('root')=='@package' else Path(t['root']).resolve() if t.get('root') else None
        code_paths=t.get('code_paths',[])
        if any(not isinstance(x,str) or Path(x).is_absolute() or '..' in Path(x).parts or x=='.' for x in code_paths):
            raise ValueError('unsafe gate code_paths')
        mounts=[]
        for x in code_paths:
            target=(root/x).resolve()
            if not target.is_relative_to(root) or not target.exists():
                raise ValueError('gate code input absent or outside repo: '+str(x))
            mounts.extend(['--ro',str(target)])
        # Only explicitly designated CODE UNDER TEST is visible. No worker tests,
        # scripts, .git, hooks, or arbitrary checkout files can be executed.
        return [str(sandbox),'--dir',str(work),'--chdir',str(work),*(['--ro',str(res)] if res and not res.is_relative_to(root) else []),*mounts,'--rw',str(out),'--env','AUTOSHIFT_GATE_OUT','--env','AUTOSHIFT_TASK_WORKTREE','--env','AUTOSHIFT_TASK_ID','--env','AUTOSHIFT_ACCEPTANCE',*[x for name in t.get('env',[]) for x in ('--env',name)],'--net','0']
    if n['kind']=='code':
        return [str(sandbox),'--rw',str(root),'--net','0']
    raise ValueError('agent sandbox required')


def execute(n, attempt, tier, root, state, previous=None, overrides=None, pin=None):
    root=Path(root).resolve();work=(root/n.get('cwd','.')).resolve()
    if not work.is_relative_to(root) or not work.is_dir():
        return {'status':'BLOCKED','rc':None,'artifacts':[],'missing':[],'claims':[],'signature':'unsafe-cwd'}
    handoff_dir=Path(state)/'handoffs';handoff_dir.mkdir(parents=True,exist_ok=True)
    handoff=handoff_dir/('%s-%s.json'%(n['id'],attempt))
    details={'goal':n.get('goal',''),'base_sha':n.get('base_sha','unknown'),
             'files':n.get('files',[]),'evidence_paths':n.get('artifacts',[]),
             'decisions':n.get('decisions',[]),'next_action':n.get('next_action',n.get('goal','')),
             'attempt':attempt,'previous':digest_previous(previous, state),
             'work_pattern':WORK_PATTERNS.get(n.get('work_pattern','lean-build'),WORK_PATTERNS['lean-build']),
             'output_contract':OUTPUT_CONTRACT}
    receipts=prepare_fields(details,state,agent_call=n['kind']=='agent')
    # Store measurements apart from the agent input: receipt prose cannot earn
    # a place inside its own measured envelope (D1; Caveman Honest Numbers).
    receipt_dir=Path(state)/'receipts';receipt_dir.mkdir(parents=True,exist_ok=True)
    receipt_file=receipt_dir/('%s-%s.json'%(n['id'],attempt))
    write_atomic(receipt_file,json.dumps(receipts,sort_keys=True).encode()+b'\n')
    receipt_file.chmod(0o600)
    write_atomic(handoff,json.dumps(details,sort_keys=True).encode()+b'\n')
    outfile=handoff_dir/('%s-%s.out'%(n['id'],attempt))
    if n['kind'] in ('join','wake','fanout'):
        return {'status':'PASS','rc':0,'artifacts':[],'missing':[],'claims':[], 'handoff':str(handoff)}
    if n['kind'] == 'ask':
        return {'status':'BLOCKED','rc':None,'artifacts':[],'missing':[],'claims':[], 'signature':'human-answer-needed','handoff':str(handoff)}
    vdir=None
    if n.get('role')=='audit':
        # Independent review gets actual bytes, never worker-authored verdict prose.
        # The verdict is a file the auditor writes into a fresh per-attempt directory; code reads that file.
        vdir=Path(state)/'verdicts'/('%s-%s'%(n['id'],attempt))
        shutil.rmtree(vdir,ignore_errors=True);vdir.mkdir(parents=True);vdir.chmod(0o700)
        spec=n.get('spec_path','')
        specfile=(root/spec).resolve() if spec else None
        if specfile and specfile.is_file() and specfile.is_relative_to(root):
            spec_content=specfile.read_text(errors='replace')[:65536]
        else:spec_content=n.get('goal','')
        try:
            change=subprocess.run(['git','diff','--no-ext-diff','--binary','HEAD','--'],
                    cwd=root,capture_output=True,text=True,timeout=15)
            patch=change.stdout[:131072] if change.returncode==0 else '[git diff unavailable]'
        except (OSError,subprocess.TimeoutExpired):patch='[git diff unavailable]'
        details['audit_contract']={'schema':'audit.json: {"verdict":"APPROVE|REJECT","reason":"..."}',
               'verdict_file':str(vdir/'audit.json'),
               'diff':patch,'spec':spec_content,'spec_source':str(spec or 'goal'),
               'parent_results':details['previous']}
        write_atomic(handoff,json.dumps(details,sort_keys=True).encode()+b'\n')
    if n['kind'] == 'agent':
        provider=tier.get('provider') if isinstance(tier,dict) else n.get('provider','claude')
        model=tier.get('model') if isinstance(tier,dict) else str(tier)
        cmd=command(provider, model, handoff, outfile, overrides)
    else:
        cmd=list(n.get('cmd',[]))
        spec_key={'gate':'trusted_gate','code':'host'}.get(n['kind'])
        if spec_key and n.get(spec_key):
            spec=n[spec_key]
            package=Path(__file__).resolve().parents[1]
            source=package if spec['root']=='@package' else Path(spec['root']).resolve()
            entry=(source/spec['entry']).resolve()
            if not entry.is_file() or not entry.is_relative_to(source):
                return {'status':'BLOCKED','rc':None,'signature':'untrusted-gate-entry','missing':[], 'artifacts':[], 'claims':[]}
            if source.is_relative_to(root) or source.is_relative_to(work):
                return {'status':'BLOCKED','rc':None,'signature':'mutable-gate-root','missing':[], 'artifacts':[], 'claims':[]}
            if pin and pin_digest(spec,package)!=pin:
                return {'status':'BLOCKED','rc':None,'signature':'trusted-gate-changed','missing':[], 'artifacts':[], 'claims':[]}
            # The command vector cannot be overridden by worktree contents.
            cmd=['bash',str(entry),*spec.get('args',[])]
    host=n['kind']=='code' and bool(n.get('host'))   # owner-pinned script, runs outside the sandbox on purpose
    try:
        sandbox=[] if host else _sandbox_for(n,root,work,state)
        if n['kind']=='agent' and 'stub-sandbox.sh' not in str(sandbox):
            # Gate state and .git must not be reachable through an agent's writable bind.
            for ix,x in enumerate(sandbox):
                if x=='--rw' and ix+1<len(sandbox):
                    dest=(work/str(sandbox[ix+1])).resolve()
                    if state.resolve().is_relative_to(dest) or (root/'.git').resolve().is_relative_to(dest):
                        raise ValueError('unsafe writable agent bind includes journal or .git')
        if n['kind']=='agent' and 'stub-sandbox.sh' not in str(sandbox):
            # Agents start in their own work dir, may read their handoff, and an auditor may write only its verdict dir.
            ix=next(i for i,x in enumerate(sandbox) if 'sandbox.sh' in str(x))
            extra=['--chdir',str(work),'--ro',str(handoff),'--env','AUTOSHIFT_HANDOFF']
            if vdir:extra+=['--rw',str(vdir),'--env','AUTOSHIFT_VERDICT']
            sandbox=list(sandbox[:ix+1])+extra+list(sandbox[ix+1:])
        if sandbox:cmd=list(sandbox)+['--']+cmd
    except ValueError as e:
        return {'status':'BLOCKED','rc':None,'artifacts':[],'missing':[],'claims':[],
                'signature':'sandbox-required: '+str(e),'handoff':str(handoff)}
    # A gate must produce fresh evidence; old artifacts cannot certify a new run.
    gate_output=Path(state)/'.autoshift-gate-output'
    if n['kind']=='gate': gate_output.mkdir(parents=True,exist_ok=True)
    # Real gates can write only their state-side output directory, not --repo.
    # Test-only stub execution remains compatible with pre-v6 fixtures.
    gate_root=(Path(state) if n['kind']=='gate' and
               ('stub-sandbox.sh' not in str(sandbox) or
                all(x.startswith('.autoshift-gate-output/') for x in n.get('artifacts',[])))
               else work)
    preexisting, _ = collect(gate_root,n.get('artifacts',[])) if n['kind']=='gate' else ([],[])
    old_hashes = {e['path']:e['sha256'] for e in preexisting}
    old_stats = {}
    for item in preexisting:
        stat = (gate_root/item['path']).stat()
        old_stats[item['path']] = (stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino)
    rc=None;timed_out=False;stdout_bytes=b'';stderr_bytes=b''
    # CLI stdout/stderr are streamed to private, real files while RUNNING; the
    # /autoshift-check skill must inspect actual transcript bytes, not status prose.
    private=Path(state)/'raw';private.mkdir(parents=True,exist_ok=True)
    stdout_path=private/('%s-%s.stdout'%(n['id'],attempt))
    stderr_path=private/('%s-%s.stderr'%(n['id'],attempt))
    with stdout_path.open('wb') as outfd,stderr_path.open('wb') as errfd:
        stdout_path.chmod(0o600);stderr_path.chmod(0o600)
        try:
            proc=subprocess.Popen(cmd,cwd=work,stdout=outfd,stderr=errfd,text=False,
                                  start_new_session=True,preexec_fn=_die_with_parent,env={**os.environ,
                                    'AUTOSHIFT_HANDOFF':str(handoff),'AUTOSHIFT_GATE_OUT':str(gate_output),
                                    'AUTOSHIFT_TASK_WORKTREE':str(root),
                                    'AUTOSHIFT_TASK_ID':str(n.get('task_id',n['id'])),
                                    'AUTOSHIFT_ACCEPTANCE':str(n.get('acceptance_path','')),
                                    **({'AUTOSHIFT_VERDICT':str(vdir/'audit.json')} if vdir else {})})
            with _MU:_RUNNING.add(proc)
            try:
                rc=proc.wait(timeout=n.get('timeout',300))
            except subprocess.TimeoutExpired:
                timed_out=True;os.killpg(proc.pid,signal.SIGKILL)
                rc=proc.wait()
            finally:
                with _MU:_RUNNING.discard(proc)
        except OSError as e:errfd.write(str(e).encode('utf-8','replace'))
        outfd.flush();errfd.flush()
    stdout_bytes=stdout_path.read_bytes();stderr_bytes=stderr_path.read_bytes()
    stdout=stdout_bytes.decode('utf-8','replace');stderr=stderr_bytes.decode('utf-8','replace')
    evidence,missing=collect(gate_root if n['kind']=='gate' else work,n.get('artifacts',[]))
    if n['kind'] == 'gate':
        if not n.get('artifacts'): missing.append('<undeclared-gate-artifact>')
        for item in evidence:
            stat=(gate_root/item['path']).stat()
            fresh=(stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino) != old_stats.get(item['path'])
            if old_hashes.get(item['path']) == item['sha256'] and not fresh:
                missing.append('<stale:'+item['path']+'>')
    status=verdict(rc,missing,timed_out)
    audit_file=None
    if n.get('role')=='audit':
        # Accept only the verdict FILE the auditor left in its own directory, never stdout prose or exit status.
        try:
            fd=os.open(vdir/'audit.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as f:
                if not S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('verdict is not a regular file')
                raw=f.read(65537)
            if len(raw)>65536:raise ValueError('verdict too large')
            obj=json.loads(raw)
            if not isinstance(obj,dict):raise ValueError('not a JSON object')
            a={'verdict':obj.get('verdict'),'reason':str(obj.get('reason',''))[:1000]}
            if a['verdict'] not in ('APPROVE','REJECT'):raise ValueError('invalid decision')
            dest=Path(state)/'audits';dest.mkdir(parents=True,exist_ok=True)
            audit_file=dest/('%s-%s.json'%(n['id'],attempt))
            write_atomic(audit_file,json.dumps(a,sort_keys=True).encode()+b'\n');audit_file.chmod(0o600)
            if a['verdict']!='APPROVE':status='FAIL';missing.append('<auditor-rejected>')
        except (OSError,ValueError,AttributeError):
            status='FAIL';missing.append('<missing-audit-verdict>')
    claims=[]
    # Explicit claims are telemetry only; never use JSON output to determine status.
    if stdout:
        try:
            obj=json.loads(stdout)
            if isinstance(obj,dict): claims=obj.get('claims', []) if isinstance(obj.get('claims',[]),list) else []
        except ValueError: pass
    # Evidence output is always treated as untrusted DATA, never graph or policy input.
    # Raw stdout/stderr stay private and byte-exact, journal and handoffs are redacted.
    private=Path(state)/'raw';private.mkdir(parents=True,exist_ok=True)
    for label,content in (('stdout',stdout_bytes),('stderr',stderr_bytes)):
        file=private/('%s-%s.%s'%(n['id'],attempt,label))
        write_atomic(file,content);file.chmod(0o600)
    usage=usage_from(provider if n['kind']=='agent' else 'code',stdout)
    return {'status':status,'rc':rc,'artifacts':evidence,'missing':missing,'claims':redact(claims),
            'usage':usage,'text_receipts':receipts,
            'raw_handles':{'stdout':'raw/'+n['id']+'-'+str(attempt)+'.stdout',
                           'stderr':'raw/'+n['id']+'-'+str(attempt)+'.stderr'},
            'stdout_sha256':hashlib.sha256(stdout_bytes).hexdigest(),
            'stderr_sha256':hashlib.sha256(stderr_bytes).hexdigest(),
            'signature':('infra:' if rc in (None, 78, 125, 126, 127) or timed_out
                         or (n['kind']=='agent' and rc and INFRA_TEXT.search(stderr[-2000:]+stdout[-2000:])) else '')+str(rc)+':'+','.join(missing)+(':timeout' if timed_out else ''),
            'handoff':str(handoff),'audit_file':str(audit_file) if audit_file else None,'stdout_tail':redact(stdout[-500:]),'stderr_tail':redact(stderr[-500:])}
