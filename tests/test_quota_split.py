"""Separate weekly and five-hour stops each reading is checked against its own limit."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.quota import reading

def spec(weekly,five,extra=None):
    d={'usage_pct':max(weekly,five),'weekly_pct':weekly,'five_hour_pct':five,'at':__import__('time').time()}
    d.update(extra or {})
    return {'claude':{'cmd':[sys.executable,'-c','import json;print(json.dumps(%r))'%d],
                      'weekly_limit_pct':80,'five_hour_limit_pct':90}}
assert reading(spec(79,89),'claude')['admitted']
assert reading(spec(10,85),'claude')['admitted'],'five-hour 85 is below its own 90 stop'
assert not reading(spec(81,10),'claude')['admitted'],'weekly 81 is over the 80 stop'
assert not reading(spec(10,91),'claude')['admitted'],'five-hour 91 is over the 90 stop'
assert not reading(spec(85,85),'claude')['admitted']
missing={'claude':{'cmd':[sys.executable,'-c','import json,time;print(json.dumps({"usage_pct":5,"weekly_pct":5,"at":time.time()}))'],
                   'weekly_limit_pct':80,'five_hour_limit_pct':90}}
assert not reading(missing,'claude')['admitted'],'a missing reading must fail closed'
assert reading({'codex':{'unmetered':True}},'codex')['admitted'],'owner-chosen unmetered tool runs'
assert not reading({'codex':{'unmetered':'yes'}},'codex')['admitted'],'only an explicit true counts'
assert not reading({},'codex')['admitted'],'no setting at all still fails closed'
import os
os.chdir('/')  # '@package/' must resolve inside the package, whatever the working directory
assert reading({'claude':{'cmd':[sys.executable,'@package/tests/stub-quota.py'],'weekly_limit_pct':80,'five_hour_limit_pct':90}},'claude')['admitted']
print('QUOTA_SPLIT_OK')
