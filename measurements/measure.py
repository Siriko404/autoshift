"""Reproducible paired input-length decisions (UTF-8 bytes, not model tokens)."""
import json
import sys
import tempfile
from pathlib import Path
base=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(base))
from autoshift.doctrine import prepare_fields,measure,WORK_PATTERNS,OUTPUT_CONTRACT
rows=[]
for item in json.loads((Path(__file__).parent/'fixtures.json').read_text()):
    with tempfile.TemporaryDirectory() as d:
        source=item['text'];details={'goal':source,'base_sha':'hash','next_action':source,
                'work_pattern':WORK_PATTERNS['lean-build'],'output_contract':OUTPUT_CONTRACT}
        before=details.copy();receipts=prepare_fields(details,d,agent_call=True)
        policy=receipts['rule_policy']
        rows.append({'fixture':item['name'],'level_used':'ultra (agent-call policy)','source_fixture_level':item['level'],
            'original_bytes':sum(measure(before[k])['bytes'] for k in ('goal','base_sha','next_action')),
            'candidate_bytes':policy['total_candidate_bytes'],
            'net_delta_bytes_vs_no_rules':policy['net_delta_bytes'],
            'work_pattern':policy['rules']['work_pattern'],
            'output_contract':policy['rules']['output_contract'],
            'method':'UTF-8 bytes of same text fields, uncompressed/no-rules vs compressed/gated; NOT model tokens',
            'quality':'protected spans and negations unchanged; not live-agent equivalence'})
print(json.dumps(rows,indent=2,sort_keys=True))
