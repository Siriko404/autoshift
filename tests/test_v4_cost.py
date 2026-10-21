"""Cost gate must kill unconditional policy injection or universal omission mutants."""
import json,sys,tempfile,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.doctrine import prepare_fields,WORK_PATTERNS,OUTPUT_CONTRACT
from autoshift.runner import execute
base=Path(__file__).resolve().parents[1]
fixtures=json.loads((base/'measurements/fixtures.json').read_text())
kept=0;omitted=0
for item in fixtures:
 with tempfile.TemporaryDirectory() as d:
  details={'goal':item['text'],'base_sha':'hash','next_action':item['text'],
    'work_pattern':WORK_PATTERNS['lean-build'],'output_contract':OUTPUT_CONTRACT}
  r=prepare_fields(details,d,agent_call=True)['rule_policy']
  assert details['output_contract']==OUTPUT_CONTRACT, item['name']
  for key in ('work_pattern','output_contract'):
   decision=r['rules'][key]['decision']
   assert details[key]==(OUTPUT_CONTRACT if key=='output_contract' else ('' if decision=='OMIT' else WORK_PATTERNS['lean-build']))
   kept+=(decision=='INCLUDE');omitted+=(decision=='OMIT')
with tempfile.TemporaryDirectory() as d:
 long='Please just really carefully revise the code. '*60
 details={'goal':long,'base_sha':'hash','next_action':long,
          'work_pattern':WORK_PATTERNS['lean-build'],'output_contract':OUTPUT_CONTRACT}
 assert prepare_fields(details,d,agent_call=False)['rule_policy']['rules']['output_contract']['decision']=='INCLUDE'
with tempfile.TemporaryDirectory() as d:
 root=Path(d);n={'id':'probe','kind':'agent','tiers':[{'provider':'claude','model':'haiku'}],
                    'goal':'Please just read carefully.','artifacts':[]}
 old=os.environ.pop('AUTOSHIFT_TEST_SANDBOX',None)
 try:result=execute(n,1,n['tiers'][0],root,root/'state')
 finally:
  if old is not None:os.environ['AUTOSHIFT_TEST_SANDBOX']=old
 # BLOCKED for missing sandbox is intentional. Handoff exists before dispatch.
 assert result['status']=='BLOCKED' and result['signature'].startswith('sandbox-required')
 handoff=json.loads(Path(result['handoff']).read_text())
 receipt_path=root/'state/receipts/probe-1.json'
 assert receipt_path.exists() and receipt_path.stat().st_mode&0o777==0o600
 assert 'text_receipts' not in handoff and 'rule_policy' not in handoff
 assert handoff['output_contract']==OUTPUT_CONTRACT
assert kept>=1 and omitted>=1,(kept,omitted)
print('V4_COST_OK include',kept,'omit',omitted)
