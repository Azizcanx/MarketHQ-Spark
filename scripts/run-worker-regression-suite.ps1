$ErrorActionPreference = "Stop"

$tests = @(
  ".\frontend\components\workers\implementation-intent-tests.ts",
  ".\frontend\components\workers\autonomous-worker-policy-tests.ts",
  ".\frontend\components\workers\patch-intake-hardening-tests.ts",
  ".\frontend\components\workers\worker-runtime-tests.ts",
  ".\frontend\components\workers\autonomous-worker-orchestrator-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-controller-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-coordinator-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-coordinator-v2-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-lock-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-runner-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-recovery-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-scheduler-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-plan-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-guard-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-lease-tests.ts"
)

foreach ($test in $tests) {
  Write-Host "RUN $test"
  node --experimental-transform-types $test
  if ($LASTEXITCODE -ne 0) { throw "TEST FAILED: $test" }
}

Write-Host "WORKER REGRESSION SUITE PASS"
