$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$test = Join-Path $root "MARKETHQ_VectorBT_E2E_Test_V1.ps1"

if (-not (Test-Path $test)) {
    throw "E2E test dosyasi bulunamadi: $test"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root ("vectorbt-e2e-version-check-backup_" + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $test (Join-Path $backupDir "MARKETHQ_VectorBT_E2E_Test_V1.ps1") -Force

$source = Get-Content $test -Raw

$old = '    "VectorBT engine version" = ($fullJson -match ''VECTORBT_ENGINE_V1|VECTORBT.*"engineVersion"'')'

$new = '    "VectorBT engine version" = ($fullJson -match ''"engineVersion"\s*:\s*"1\.1\.0"|VECTORBT_ENGINE_V1'')'

if ($source.Contains($old)) {
    $source = $source.Replace($old, $new)
    Set-Content -Path $test -Value $source -Encoding UTF8
    Write-Host "VectorBT engine version kontrolu 1.1.0 kontratina guncellendi." -ForegroundColor Green
}
elseif ($source -match '"VectorBT engine version".*engineVersion') {
    Write-Host "VectorBT engine version kontrolu zaten guncel; tekrar patchlenmedi." -ForegroundColor Yellow
}
else {
    throw "E2E version check anchor bulunamadi."
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT E2E Version Check Fix V1 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "E2E Test : $test"
Write-Host "Backup   : $backupDir"
Write-Host ""
Write-Host "Bu bir engine bugfix degil; E2E testinin version regex kontrolu duzeltildi."
Write-Host "Engine calismasi zaten COMPLETED / succeeded / VECTORBT."
Write-Host ""
Write-Host "Tekrar calistir:"
Write-Host "  cd $root"
Write-Host "  .\MARKETHQ_VectorBT_E2E_Test_V1.ps1"
Write-Host "============================================================" -ForegroundColor Cyan
