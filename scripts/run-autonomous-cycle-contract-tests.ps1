$ErrorActionPreference = "Stop"

$tests = @(
  ".\frontend\components\workers\autonomous-cycle-guard-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-lease-tests.ts",
  ".\frontend\components\workers\autonomous-cycle-plan-tests.ts"
)

foreach ($test in $tests) {
  Write-Host "RUN $test"
  node --experimental-transform-types $test
  if ($LASTEXITCODE -ne 0) { throw "TEST FAILED: $test" }
}

Write-Host "AUTONOMOUS CYCLE CONTRACT TESTS PASS"
