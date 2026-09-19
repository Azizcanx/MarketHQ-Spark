$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($env:MARKETHQ_CURSOR_WORKER_ENABLE -ne "true") {
  $env:MARKETHQ_CURSOR_WORKER_ENABLE = "true"
}

node --experimental-strip-types .\scripts\run-cursor-worker-fixture.mjs
