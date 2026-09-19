$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$generator = Join-Path $root "frontend\components\agents\experiment-generator-agent.ts"

if (-not (Test-Path $generator)) {
    throw "experiment-generator-agent.ts bulunamadi: $generator"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("vectorbt-parameter-propagation-backup_" + $stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item $generator (Join-Path $backup "experiment-generator-agent.ts") -Force

$source = Get-Content $generator -Raw

$old = @'
  const parameters =
    normalizeParameters(
      strategyOutput
    );
'@

$new = @'
  const generatedParameters =
    normalizeParameters(
      strategyOutput
    );

  const input =
    isRecord(context.input)
      ? context.input
      : {};

  const importedStrategyDefinition =
    isRecord(input.strategyDefinition)
      ? input.strategyDefinition
      : isRecord(input.importedStrategy)
        ? input.importedStrategy
        : isRecord(input.strategyImport)
          ? input.strategyImport
          : {};

  const importedParameters =
    isRecord(
      importedStrategyDefinition.parameters
    )
      ? importedStrategyDefinition.parameters
      : {};

  const parameters =
    Object.keys(generatedParameters).length > 0
      ? generatedParameters
      : importedParameters;
'@

if (-not $source.Contains($old)) {
    throw "Generator parameter anchor bulunamadi."
}

if (-not $source.Contains("const importedParameters =")) {
    $source = $source.Replace($old, $new)
    Set-Content -Path $generator -Value $source -Encoding UTF8
}
else {
    Write-Host "Parameter propagation patch zaten mevcut; tekrar uygulanmadi." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT Parameter Propagation Fix V1 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Generator : $generator"
Write-Host "Backup    : $backup"
Write-Host ""
Write-Host "Strategy Agent parameters bos gelirse:"
Write-Host "context.input.strategyDefinition.parameters"
Write-Host "fallback olarak canonical Experiment'a aktarilacak."
Write-Host ""
Write-Host "Beklenen:"
Write-Host "sma_fast=20"
Write-Host "sma_slow=100"
Write-Host "rsi_period=14"
Write-Host "rsi_entry=50"
Write-Host ""
Write-Host "Sonraki:"
Write-Host "  cd frontend"
Write-Host "  npm run build"
Write-Host "============================================================" -ForegroundColor Cyan

