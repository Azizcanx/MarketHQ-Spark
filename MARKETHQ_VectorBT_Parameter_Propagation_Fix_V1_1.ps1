$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$frontend = Join-Path $root "frontend"
$generator = Join-Path $frontend "components\agents\experiment-generator-agent.ts"
$orchestrator = Join-Path $frontend "app\api\agents\orchestrator\route.ts"

if (-not (Test-Path $frontend)) { throw "MarketHQ rootunda frontend bulunamadi." }
if (-not (Test-Path $generator)) { throw "experiment-generator-agent.ts bulunamadi." }
if (-not (Test-Path $orchestrator)) { throw "orchestrator route.ts bulunamadi." }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("vectorbt-parameter-propagation-v1_1-backup_" + $stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item $generator (Join-Path $backup "experiment-generator-agent.ts") -Force
Copy-Item $orchestrator (Join-Path $backup "route.ts") -Force

# ---------------------------------------------------------------------------
# 1) Experiment Generator
# ---------------------------------------------------------------------------
$source = Get-Content $generator -Raw

if ($source -notmatch 'importedParameters\s*=') {

    # The live file formatting has changed across Generator versions.
    # Match the whole normalizeParameters call by whitespace, not exact lines.
    $pattern = '(?s)\bconst\s+parameters\s*=\s*normalizeParameters\s*\(\s*strategyOutput\s*\)\s*;'

    $match = [regex]::Match($source, $pattern)

    if (-not $match.Success) {
        # Fallback: find normalizeParameters(strategyOutput) and replace only
        # the surrounding const parameters assignment.
        $pattern2 = '(?s)const\s+parameters\s*=\s*normalizeParameters\s*\(\s*strategyOutput\s*\)\s*;'
        $match = [regex]::Match($source, $pattern2)
    }

    if (-not $match.Success) {
        throw "Generator normalizeParameters(strategyOutput) anchor bulunamadi."
    }

    $replacement = @'
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

    $source =
        $source.Substring(0, $match.Index) +
        $replacement +
        $source.Substring($match.Index + $match.Length)

    Set-Content -Path $generator -Value $source -Encoding UTF8
    Write-Host "Generator parameter fallback eklendi." -ForegroundColor Green
}
else {
    Write-Host "Generator parameter fallback zaten mevcut; tekrar patchlenmedi." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 2) Orchestrator: top-level strategyDefinition -> context.input
# ---------------------------------------------------------------------------
$orch = Get-Content $orchestrator -Raw

if ($orch -notmatch 'input\.strategyDefinition\s*=\s*body\.strategyDefinition') {

    $contextPattern = '(?s)const\s+input(?::\s*JsonRecord)?\s*=\s*isRecord\(body\.input\)\s*\?\s*body\.input\s*:\s*\{\};'

    $cm = [regex]::Match($orch, $contextPattern)

    if (-not $cm.Success) {
        # Current patched versions may use the spread form.
        $contextPattern2 = '(?s)const\s+input\s*:\s*JsonRecord\s*=\s*isRecord\(body\.input\)\s*\?\s*\{\s*\.\.\.body\.input\s*\}\s*:\s*\{\};'
        $cm = [regex]::Match($orch, $contextPattern2)
    }

    if (-not $cm.Success) {
        throw "Orchestrator context input anchor bulunamadi."
    }

    $oldInput = $cm.Value

    if ($oldInput -match '\.\.\.body\.input') {
        $newInput = $oldInput + @'

    if (isRecord(body.strategyDefinition)) {
      input.strategyDefinition = body.strategyDefinition;
    }
'@
    }
    else {
        $newInput = @'
const input: JsonRecord =
    isRecord(body.input)
      ? { ...body.input }
      : {};

  if (typeof body.researchEngine === "string") {
    input.researchEngine = body.researchEngine;
  }

  if (isRecord(body.strategyDefinition)) {
    input.strategyDefinition = body.strategyDefinition;
  }
'@
    }

    $orch =
        $orch.Substring(0, $cm.Index) +
        $newInput +
        $orch.Substring($cm.Index + $cm.Length)

    Set-Content -Path $orchestrator -Value $orch -Encoding UTF8
    Write-Host "Orchestrator strategyDefinition context aktarimi eklendi." -ForegroundColor Green
}
else {
    Write-Host "Orchestrator strategyDefinition aktarimi zaten mevcut; tekrar patchlenmedi." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT Parameter Propagation Fix V1.1 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Generator    : $generator"
Write-Host "Orchestrator : $orchestrator"
Write-Host "Backup       : $backup"
Write-Host ""
Write-Host "Beklenen Experiment.strategy.parameters:"
Write-Host "  sma_fast=20"
Write-Host "  sma_slow=100"
Write-Host "  rsi_period=14"
Write-Host "  rsi_entry=50"
Write-Host ""
Write-Host "Sonraki:"
Write-Host "  cd frontend"
Write-Host "  npm run build"
Write-Host ""
Write-Host "Build PASS olursa E2E:"
Write-Host "  cd .."
Write-Host "  .\MARKETHQ_VectorBT_E2E_Test_V1.ps1"
Write-Host "============================================================" -ForegroundColor Cyan
