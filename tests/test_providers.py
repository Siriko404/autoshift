import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.providers import command
for p in ('claude','codex','opencode','agy'):
 c=command(p,'model-x','h.json','out.json');assert isinstance(c,list) and 'model-x' in c
assert command('agy','m','h','o')[0]=='python3', 'agy glue mutant survived'
try:command('fictional','m','h','o');raise AssertionError('unknown provider mutant survived')
except ValueError:pass
print('PROVIDERS_OK')
