#!/usr/bin/env python3
import json,sys
from pathlib import Path
handoff,out,model=sys.argv[1:4]
h=json.loads(Path(handoff).read_text())
prev=h.get('previous') or {}
if 'PELICAN' in h['goal']:
    if h['attempt']==1:
        print(json.dumps({'claims':['PELICAN: first attempt keeps the phrase']}))
        sys.exit(17)
    assert 'PELICAN' in json.dumps(prev), 'no handoff carry over'
    Path(out).write_text('PELICAN FOUND')
    print(json.dumps({'claims':['PELICAN recovered']}))
else:
    Path(out).write_text('completed')
    print(json.dumps({'claims':['ALL TESTS PASSED (untrusted)']}))
