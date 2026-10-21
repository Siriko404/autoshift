import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.ledger import Journal
with tempfile.TemporaryDirectory() as d:
 j=Journal(d); assert j.append('STOP','once');assert not j.append('STOP','once')
 assert j.state['stopped'] and j.diff()==[]
 j.append('RESUME','new');assert not j.state['stopped']
 f=Path(d)/'events.jsonl'; original=f.read_bytes()
 f.write_bytes(original+b'{broken')
 j2=Journal(d);assert len(j2.events)==2 and j2.diff()==[]
 raw=f.read_bytes();f.write_bytes(raw.replace(b'RESUME',b'RESUNE'))
 try:Journal(d);raise AssertionError('hash mutant survived')
 except ValueError:pass
 f.write_bytes(raw)
 j2.snapshot.write_text('{}')
 assert j2.diff(), 'snapshot corruption mutant survived'
print('LEDGER_OK')
