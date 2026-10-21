"""Runs the adapted critique proofs (tests/proofs_v7) against THIS tree. Each attack must be rejected, with the printed
statuses that show the fix's reason; the extensions must succeed. Needs real bwrap (P1-B, P2, P6)."""
import os,shutil,subprocess,sys
from pathlib import Path
base=Path(__file__).resolve().parents[1]
if not shutil.which('bwrap'):
    print('SKIP_NEEDS_BWRAP');raise SystemExit(77)
P=base/'tests/proofs_v7'
env={k:v for k,v in os.environ.items() if k not in('AUTOSHIFT_TEST_SANDBOX','AUTOSHIFT_TEST_STATIC_QUOTA')}


def run(cmd,timeout=120):
    p=subprocess.run(cmd,cwd='/tmp',env=env,capture_output=True,text=True,timeout=timeout)
    return p.returncode,p.stdout+p.stderr


def attack_rejected(name,must,forbid='REPRODUCED'):
    rc,out=run([sys.executable,'-I',str(P/name),str(base)])
    assert rc==1 and forbid not in out and any(x in out for x in('AssertionError','KeyError','ValueError')),(name,rc,out[-800:])
    for needle in must:assert needle in out,(name,needle,out[-1200:])


attack_rejected('p1_worker_controls_gate.py',["A: node statuses {'pass1': 'PASS', 'gate1': 'FAIL'"])
attack_rejected('p1b_scenario_b_only.py',["B: node statuses {'worker': 'PASS', 'gate': 'FAIL'}","outside-marker.txt (written by worker-authored gate, outside sandbox): ABSENT",
                                          "B: real test still fails after the run: rc = 1"])
attack_rejected('p2_worker_forges_journal.py',["statuses {'worker': 'FAIL'}","merged.txt exists: False"])
attack_rejected('p2b_state_inside_declared_bind.py',["unsafe state: journal must be outside --repo"])
attack_rejected('p4_g1_audits_and_plan.py',["workers.item0.audit.plugin.1 -> FAIL","'merge_check': None","'merge': None"])
attack_rejected('p5_failure_path.py',["present in pass2 handoff? True","(b) asks raised: [] | summary failed = 0 pending = 0","'deploy': 'SKIP'"])
attack_rejected('p6_kill_dead_end.py',["(a) 2.5 s later, effect.txt exists? False","(b) statuses: {'effect': 'BLOCKED'}"])
for name,ok in (('ext_p5_dead_end_resumes.py','EXT P5 RESUMES'),('ext_p6_reconcile.py','EXT P6 RECONCILE OK')):
    rc,out=run([sys.executable,'-I',str(P/name),str(base)]);assert rc==0 and ok in out,(name,out[-800:])
rc,out=run(['bash',str(P/'appendix_quick_checks.sh'),str(base)],timeout=240)
assert 'BASELINE_RED' in out and "'state': 'READER_ERROR'" in out and 'graph revision refused' in out and 'MUTANTS_OK' not in out,out[-1500:]
print('V7_PROOFS_OK p1 p1b p2 p2b p4 p5 p6 ext-p5 ext-p6 appendix')
