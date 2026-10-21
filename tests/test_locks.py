import multiprocessing,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.locks import Locks

def expired(d,queue):
    queue.put(Locks(d).change('claim','dead',['scratch/**']))

def holder(d,queue):
    k=Locks(d);queue.put(k.change('claim','B',['src/core/**']));time.sleep(.15)

with tempfile.TemporaryDirectory() as d:
 l=Locks(d);assert l.change('claim','A',['src/**'])
 ctx=multiprocessing.get_context('fork')  # Linux 3.14 defaults to forkserver; explicit fork avoids recursive import
 q=ctx.Queue();p=ctx.Process(target=holder,args=(d,q));p.start()
 assert q.get(timeout=2) is False, 'overlap mutant survived';p.join()
 assert l.change('claim','C',['docs/**'])
 l.change('release','A');assert l.change('claim','D',['src/core/**'])
 # dead process lock reaped automatically on next claim
 assert l.change('claim','B',['src/**']) is False
 dead=ctx.Process(target=expired,args=(d,q));dead.start()
 assert q.get(timeout=2) is True;dead.join()
 assert l.change('claim','revived',['scratch/file.txt']), 'dead owner lock survived'
print('LOCKS_OK')
