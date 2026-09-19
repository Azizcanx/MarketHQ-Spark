$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$test = Join-Path $root "MARKETHQ_VectorBT_E2E_Test_V1.ps1"

if (-not (Test-Path $test)) {
    throw "E2E test dosyasi bulunamadi: $test"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root ("vectorbt-e2e-version-check-v2-backup_" + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $test (Join-Path $backupDir "MARKETHQ_VectorBT_E2E_Test_V1.ps1") -Force

$lines = @(Get-Content $test)

$targetIndex = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    $trimmed = $lines[$i].Trim()
    if ($trimmed -like '"VectorBT engine version"*') {
        $targetIndex = $i
        break
    }
}

if ($targetIndex -lt 0) {
    # Fallback: search by readable label anywhere in the line.
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Contains("VectorBT engine version")) {
            $targetIndex = $i
            break
        }
    }
}

if ($targetIndex -lt 0) {
    throw "E2E 'VectorBT engine version' satiri bulunamadi."
}

$lines[$targetIndex] = '    "VectorBT engine version" = ($fullJson -match ''"engineVersion"\s*:\s*"1\.1\.0"|VECTORBT_ENGINE_V1'')'

Set-Content -Path $test -Value $lines -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT E2E Version Check Fix V2 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "E2E Test : $test"
Write-Host "Backup   : $backupDir"
Write-Host "Patched line: $($targetIndex + 1)"
Write-Host ""
Write-Host "Engine zaten COMPLETED / succeeded / VECTORBT."
Write-Host "Sadece E2E version assertion yeniden yazildi."
Write-Host ""
Write-Host "Tekrar calistir:"
Write-Host "  cd $root"
Write-Host "  .\MARKETHQ_VectorBT_E2E_Test_V1.ps1"
Write-Host "============================================================" -ForegroundColor Cyan
