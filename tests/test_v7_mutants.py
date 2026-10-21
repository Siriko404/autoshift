"""Source mutants for the v7 trust fixes. Each mutant is applied to a mirror copy, the unmutated test must be green first,
then the mutated tree must turn it red."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
T='tests/test_v7_trust.py'
cases=[
 ('autoshift/runner.py',"if a['verdict']!='APPROVE':status='FAIL';missing.append('<auditor-rejected>')","pass",T),
 ('autoshift/runner.py',"os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK","os.O_RDONLY|os.O_NONBLOCK",T),
 ('autoshift/runner.py',"os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK","os.O_RDONLY|os.O_NOFOLLOW",T),
 ('autoshift/runner.py',"if pin and pin_digest(spec,package)!=pin:","if False:",T),
 ('autoshift/runner.py',"(n['kind']=='agent' and rc and INFRA_TEXT.search(stderr[-2000:]+stdout[-2000:]))","False",T),
 ('autoshift/runner.py',"return roots or [work]","return [work]",T),
 ('autoshift/scheduler.py',"if n['kind']=='gate' and result['status']=='FAIL' and not handled and not signature.startswith('infra:'):","if n['kind']=='gate' and result['status']=='FAIL' and not handled:",T),
 ('autoshift/scheduler.py',"mine=writable_roots(n,self.repo)","mine=[Path('/nonexistent-lane')]",T),
 ('autoshift/scheduler.py',"'ask-exhausted:'+node+':'+str(tries),node,\n                          {'question':'Task exhausted attempts '+node})\n        elif tiers and repeat","'ask-exhausted:'+node,node,\n                          {'question':'Task exhausted attempts '+node})\n        elif tiers and repeat",T),
 ('autoshift/scheduler.py',"if tries<n.get('max_attempts',3):","if tries<n.get('max_attempts',3) and False:",T),
 ('autoshift/scheduler.py',"                except BaseException:pass  # nothing durable can be written; recovery marks the node UNCERTAIN\n","                except BaseException:raise\n",T),
 ('autoshift/scheduler.py',"elif have!=digest:raise ValueError('trusted gate %s changed since it was pinned; review it and use revise'%pin_node)","elif have!=digest:pass",T),
 ('autoshift/graph.py',"for tail in tails[anchor]:g['edges'].append(dict(edge, **{'from': tail}))","for tail in tails[anchor][:1]:g['edges'].append(dict(edge, **{'from': tail}))",T),
 ('autoshift/graph.py',"anchor = rule.get('after') or first_gate(source)","anchor = rule.get('after') or source",T),
 ('autoshift/cli.py',"print('a gate has no effect to accept: its verdict must be re-earned, use --rerun');return 2","pass",T),
 ('autoshift/cli.py',"print('an UNCERTAIN node may run again only through: reconcile NODE --rerun');return 2","pass",T),
 ('autoshift/cli.py',"'retry':a.retry,'kind'","'retry':a.retry or 'retry' in a.value.casefold(),'kind'",T),
]
B='tests/test_v7_bwrap.py'
bwrap_cases=[
 ('autoshift/runner.py',"return [str(sandbox),'--dir',str(work),'--chdir',str(work),","return [str(sandbox),'--dir',str(work),",B),
 ('autoshift/runner.py',"mounts.extend(['--ro',str(target)])","mounts.extend(['--rw',str(target)])",B),
 ('autoshift/runner.py',"*(['--ro',str(res)] if res and not res.is_relative_to(root) else [])","",B),
 ('autoshift/runner.py',"extra=['--chdir',str(work),'--ro',str(handoff),'--env','AUTOSHIFT_HANDOFF']","extra=['--chdir',str(work),'--env','AUTOSHIFT_HANDOFF']",B),
 ('autoshift/runner.py',"if vdir:extra+=['--rw',str(vdir),'--env','AUTOSHIFT_VERDICT']","pass",B),
]
if shutil.which('bwrap'):cases+=bwrap_cases
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','tests','examples','adapters','bin','measurements'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 env={**os.environ,'PYTHONPATH':str(mirror)}
 base=subprocess.run([sys.executable,T],cwd=mirror,env=env,capture_output=True,text=True,timeout=120)
 assert base.returncode==0,'BASELINE_RED '+base.stderr[-600:]
 if shutil.which('bwrap'):
  bb=subprocess.run([sys.executable,B],cwd=mirror,env=env,capture_output=True,text=True,timeout=120)
  assert bb.returncode==0,'BASELINE_RED '+B+' '+(bb.stderr or bb.stdout)[-600:]
 for filename,needle,mutation,test in cases:
  path=mirror/filename;raw=path.read_text()
  assert raw.count(needle)==1,('NEEDLE',filename,needle,raw.count(needle))
  path.write_text(raw.replace(needle,mutation))
  try:code=subprocess.run([sys.executable,test],cwd=mirror,env=env,capture_output=True,text=True,timeout=40).returncode
  except subprocess.TimeoutExpired:code=-1   # a hang (for example a blocking FIFO open) also turns the test red
  path.write_text(raw)
  assert code!=0,'SOURCE_MUTANT_SURVIVED '+filename+' '+needle
 again=subprocess.run([sys.executable,T],cwd=mirror,env=env,capture_output=True,text=True,timeout=120)
 assert again.returncode==0,'BASELINE_RED_AFTER '+again.stderr[-400:]
print('V7_MUTANTS_OK',len(cases),'/',len(cases))
