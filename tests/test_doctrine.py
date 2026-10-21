import json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.doctrine import (shorten,paired,redact,prepare_fields,digest_previous,
                                usage_from,lint,NEGATIONS,spans)
from autoshift.graph import validate,load
from autoshift.scheduler import Engine
from autoshift.ledger import Journal
from autoshift.runner import execute
from autoshift.view import read_only
base=Path(__file__).resolve().parents[1]
# Negative control: all exact syntax, numbers, error string and five negations survive.
s='The code must not, never, no, only, except `a b`, /tmp/file, `python3 -c "hi"`, 3.14.7.\n```sh\necho the code\n```'
t=shorten(s)
assert NEGATIONS.findall(s)==NEGATIONS.findall(t)
assert [p for freeze,p in spans(s) if freeze]==[p for freeze,p in spans(t) if freeze]
assert lint(t,'ultra') and lint('The security warning is clear.','lite')
assert paired('Please just test the code','Please test code',True,True)['decision']=='KEEP'
assert paired('Run gate','Run gate with extra steps',True,True)['decision']=='REVERT'
assert paired('Run gate','Run',True,False)['decision']=='REVERT'
assert usage_from('claude','{"usage":{"input_tokens":7,"output_tokens":12},"total_cost_usd":0.03}')['cost_usd']==0.03
assert usage_from('claude','bad')['state']=='UNKNOWN'
for bad_cost in ('-1','1e13','"0.03"','true','null'):
    got=usage_from('claude','{"total_cost_usd":%s}'%bad_cost)
    assert got['cost_usd'] is None and got['state']=='UNKNOWN',(bad_cost,got)
assert usage_from('codex','{"usage":{"input_tokens":"0"}}')['state']=='UNKNOWN'
assert redact('password=topsecret123')=='[REDACTED]'
with tempfile.TemporaryDirectory() as d:
 root=Path(d)/'repo';root.mkdir(); state=root/'state'
 details={'work_pattern':'Run focused gate. Stop at acceptance.',
          'output_contract':'Evidence only. Never falsify PASS.',
          'goal':'Please just test the code; never drop `TOKEN`.', 'next_action':'Run tests',
          'base_sha':'aabbcc','files':['a.py'],'evidence_paths':[],
          'decisions':[],'previous':{}}
 receipts=prepare_fields(details,state)
 assert all('injected_bytes' in r for k,r in receipts.items() if k!='rule_policy')
 assert details['goal']=='Please just test the code; never drop `TOKEN`.' and details['output_contract']=='Evidence only. Never falsify PASS.'
 assert receipts['rule_policy']['rules']['work_pattern']['decision']=='OMIT'
 assert receipts['rule_policy']['rules']['output_contract']['decision']=='INCLUDE'
 raw=state/receipts['goal']['source_handle']
 assert raw.read_bytes()==b'Please just test the code; never drop `TOKEN`.'
 digest=digest_previous({'status':'FAIL','claims':['PELICAN'],'stdout_tail':'A'*5000},state)
 assert 'stdout_tail' not in digest and 'PELICAN' in str(digest)
 assert (state/digest['source_handle']).exists()
 n={'id':'secret','kind':'code','cmd':[sys.executable,'-c',
    'print(\'{"claims":["token=topsecret123"],"usage":{"input_tokens":8}}\')'],
    'artifacts':[]}
 outcome=execute(n,1,None,root,state)
 assert 'topsecret123' not in json.dumps(outcome)
 assert b'topsecret123' in (state/outcome['raw_handles']['stdout']).read_bytes()
 assert (state/outcome['raw_handles']['stdout']).stat().st_mode&0o777==0o600
 binary=execute({'id':'bytes','kind':'code','cmd':[sys.executable,'-c',
     'import sys;sys.stdout.buffer.write(bytes([255,13,10]))']},1,None,root,state)
 assert (state/binary['raw_handles']['stdout']).read_bytes()==bytes([255,13,10])
 g=validate({'nodes':[{'id':'test','kind':'agent','tiers':[{'provider':'claude','model':'worker'}],
     'reasoning':'high','determinism':'judgment'}]})
 assert g['nodes'][0]['reasoning']=='high'
 for kind,bad in [('agent','deterministic'),('gate','judgment')]:
  node={'id':'wrong','kind':kind,'determinism':bad,'tiers':[{'provider':'claude','model':'haiku'}],
        'cmd':['true']}
  try:validate({'nodes':[node]});raise AssertionError('determinism mutant survived')
  except ValueError:pass
 g3=load(base/'examples/g3-pipeline.json')
 en=Engine(g3,root,root.parent/'journal');assert en.run()['passed']==4
 assert len(en.j.state['feedback'])>=1 and en.j.diff()==[]
 assert en.summary()['efficacy_by_level_agent']['low|UNKNOWN/UNKNOWN']['passes']>=1
 from autoshift.graph import validate as validate_graph
 eg=validate_graph({'nodes':[{'id':'flaky','kind':'agent','tiers':['cheap','strong'],'max_attempts':4}]})
 re=Engine(eg,root,root.parent/'retry-feedback')
 re.j.append('START','first','flaky',{'attempt':1,'tier':'cheap'})
 re.j.append('RESULT','fail1','flaky',{'status':'FAIL','rc':1,'signature':'same'})
 re.j.append('RETRY','retry1','flaky',{'tier':'cheap'})
 re.j.append('START','second','flaky',{'attempt':2,'tier':'cheap'})
 re.j.append('RESULT','fail2','flaky',{'status':'FAIL','rc':1,'signature':'same'})
 re.next_retry('flaky',eg['nodes'][0])
 assert re.j.state['nodes']['flaky']['tier']=='strong'
 assert any(f['source']=='retry_signature' and f['observation']['repeat'] for f in re.j.state['feedback'])
 assert read_only(root.parent/'journal')==en.j.state
 assert en.summary()['usage']['test']['state']=='UNKNOWN' or 'test' in en.summary()['usage']
print('DOCTRINE_OK')
