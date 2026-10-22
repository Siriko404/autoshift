#!/usr/bin/env bash
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 9
FAIL=0
SKIP_BWRAP=0
export AUTOSHIFT_TEST_STATIC_QUOTA=1 AUTOSHIFT_TEST_SANDBOX=1
for f in tests/test_graph.py tests/test_ledger.py tests/test_locks.py tests/test_lanes.py tests/test_quota.py tests/test_evidence.py tests/test_providers.py tests/test_runner.py tests/test_scheduler.py tests/test_cli.py tests/test_integrity.py tests/test_findings.py tests/test_audit_regressions.py tests/test_mutants.py tests/test_audit_mutants.py tests/test_contract_mutants.py tests/test_doctrine.py tests/test_feedback_coverage.py tests/test_doctrine_guards.py tests/test_view.py tests/test_v4_graph.py tests/test_v4_cost.py tests/test_v4_mutants.py tests/test_doctrine_mutants.py tests/test_v3_mutants.py tests/test_kill.py tests/test_v5_security.py tests/test_v5_crash.py tests/test_v6_core.py tests/test_v7_trust.py tests/test_v7_enospc.py tests/test_v7_mutants.py tests/test_real_bwrap.py tests/test_v7_bwrap.py tests/test_v7_proofs.py tests/test_v8_sandbox.py tests/test_v8_transcript.py examples/g1-planner/test_production.py tests/test_quota_split.py tests/test_config.py tests/test_workspace.py tests/test_gate_env.py tests/test_sandbox_override.py; do
  python3 "$f"
  rc=$?
  if [ "$rc" -eq 77 ]; then
    SKIP_BWRAP=$((SKIP_BWRAP + 1))
    continue
  fi
  if [ "$rc" -ne 0 ]; then
    echo "FAIL $f rc=$rc"
    FAIL=$((FAIL + 1))
  fi
done
echo "SKIP_NEEDS_BWRAP $SKIP_BWRAP"
if [ "$FAIL" -ne 0 ]; then
  echo "AUTOSHIFT_TESTS_FAIL $FAIL"
  exit 1
fi
echo AUTOSHIFT_TESTS_OK
exit 0
