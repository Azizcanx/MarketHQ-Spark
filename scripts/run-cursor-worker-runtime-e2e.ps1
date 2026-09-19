$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$env:MARKETHQ_CURSOR_WORKER_ENABLE = "true"
$env:MARKETHQ_CURSOR_WORKER_ALLOW_DIRTY_MAIN_REPO = "true"
$env:MARKETHQ_REPO_ROOT = (Get-Location).Path

$loaderPath = (Resolve-Path ".\scripts\node-ts-extension-loader.mjs").Path
$loaderUrl = "file:///" + $loaderPath.Replace("\", "/")

node --experimental-strip-types --experimental-transform-types --experimental-loader "$loaderUrl" .\scripts\run-cursor-worker-runtime-e2e.mjs
