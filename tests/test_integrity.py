"""Package, source boundary, examples, skill/doc evidence checks for K1/2/10/14/15/16."""
import ast,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from autoshift.graph import load,validate
root=Path(__file__).resolve().parents[1]
assert all((root/p).is_dir() for p in ('autoshift','adapters','examples','skills','tests','docs','bin'))
assert (root/'bin/autoshift').is_file() and (root/'bin/autoshift').stat().st_mode & 0o111
assert all((root/p).is_file() for p in ('README.md','docs/GRAPH.md','docs/ADAPTERS.md',
                  'docs/EVIDENCE.md','docs/OPERATIONS.md','docs/CHANGELOG.md'))
assert all((root/'skills'/('autoshift'+('-'+n if n else ''))/'SKILL.md').exists()
        for n in ('','setup','run','check','ask','job'))
assert 'status tree' in (root/'skills/autoshift-check/SKILL.md').read_text().lower()
files=list((root/'autoshift').glob('*.py'));lines=sum(len(f.read_text().splitlines()) for f in files)
assert len(files)>=9 and lines<3000,(len(files),lines)
for f in files:
 tree=ast.parse(f.read_text())
 for node in ast.walk(tree):
  if isinstance(node,ast.Import):
   modules=[a.name.split('.')[0] for a in node.names]
  elif isinstance(node,ast.ImportFrom) and node.level==0:
   modules=[node.module.split('.')[0]]
  else:continue
  assert all(m in sys.stdlib_module_names for m in modules),(f,modules)
for g in ('g1-production.json','g2-ralph.json','g3-pipeline.json'):
 assert load(root/'examples'/g)['nodes']
policy=validate({'nodes':[{'id':'wide','kind':'agent','role':'worker','paths':['src/core/udp.inc'],
    'tiers':['cheap']}], 'audit_policy':[{'id':'wide','patterns':['src/core/**'],
    'auditors':[{'tiers':['strong']},{'tiers':['stronger']}]}]})
assert len([n for n in policy['nodes'] if '.audit.' in n['id']])==2
print('INTEGRITY_OK')
