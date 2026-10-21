"""Non-kernel package and manifest mutations must be detectable by static checks."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 mirror=Path(d)
 for folder in ('autoshift','tests','examples','bin','adapters','docs','skills'):
  shutil.copytree(root/folder,mirror/folder,ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copy2(root/'README.md',mirror/'README.md')
 changes=[
  ('K1 extra dependency',lambda: (mirror/'autoshift/__init__.py').write_text('import not_a_stdlib_dependency\n')),
  ('K2 missing graph',lambda: (mirror/'examples/g1-production.json').write_text('{"nodes":[]}')),
  ('K14 check skill weakened',lambda: (mirror/'skills/autoshift-check/SKILL.md').write_text('Never show any result.')),
  ('K15 missing reference',lambda: (mirror/'docs/GRAPH.md').unlink()),
  ('K16 missing command',lambda: (mirror/'bin/autoshift').unlink()),
 ]
 for name,mutate in changes:
  path={'K1':mirror/'autoshift/__init__.py','K2':mirror/'examples/g1-production.json',
        'K14':mirror/'skills/autoshift-check/SKILL.md','K15':mirror/'docs/GRAPH.md',
        'K16':mirror/'bin/autoshift'}[name.split()[0]]
  before=path.read_bytes();mode=path.stat().st_mode
  baseline=subprocess.run([sys.executable,'tests/test_integrity.py'],cwd=mirror,
          capture_output=True,text=True,timeout=15,env={**os.environ,'PYTHONPATH':str(mirror)})
  assert baseline.returncode==0,'BASELINE_RED '+name+' '+baseline.stderr[-400:]
  mutate()
  r=subprocess.run([sys.executable,'tests/test_integrity.py'],cwd=mirror,
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=9,
          env={**os.environ,'PYTHONPATH':str(mirror)})
  assert r.returncode != 0,'CONTRACT MUTANT SURVIVED '+name
  path.write_bytes(before);path.chmod(mode)
print('CONTRACT_MUTANTS_OK 5/5')
