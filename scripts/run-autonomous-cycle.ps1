$ErrorActionPreference = "Stop"

Write-Host "MarketHQ autonomous cycle entrypoint"
Write-Host "This entrypoint is intentionally bounded and does not enable the worker by itself."
Write-Host "Use MARKETHQ_AUTONOMOUS_WORKER_ENABLE=true only after reviewing the target task and safety gates."
Write-Host "For the real Cursor runtime E2E, use .\scripts\run-cursor-worker-runtime-e2e.ps1"
