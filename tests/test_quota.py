import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.quota import reading
assert not reading({},'claude')['admitted']
assert reading({'claude':{'usage_pct':70,'limit_pct':80}},'claude')['admitted']
assert not reading({'claude':{'usage_pct':80,'limit_pct':80}},'claude')['admitted'], 'quota boundary mutant survived'
assert not reading({'claude':{'cmd':['python3','-c','print(\"{}\")']}},'claude')['admitted']
print('QUOTA_OK')
