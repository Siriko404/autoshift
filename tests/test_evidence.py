import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.evidence import collect,verdict
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'good').write_text('verified');e,m=collect(p,['good','lost']);assert len(e)==1 and m==['lost']
 assert verdict(0,[])=='PASS'
 assert verdict(0,m)=='FAIL', 'missing artifact mutant survived'
 assert verdict(1,[])=='FAIL', 'false rc mutant survived'
 assert verdict(0,[],timed_out=True)=='FAIL', 'timeout mutant survived'
 (p/'evil').symlink_to('/etc/passwd');assert collect(p,['evil'])[1]==['evil']
print('EVIDENCE_OK')
