$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$frontend = Join-Path $root "frontend"
$generator = Join-Path $frontend "components\agents\experiment-generator-agent.ts"
$orchestrator = Join-Path $frontend "app\api\agents\orchestrator\route.ts"

if (-not (Test-Path $frontend)) { throw "MarketHQ rootunda frontend bulunamadi." }
if (-not (Test-Path $generator)) { throw "experiment-generator-agent.ts bulunamadi." }
if (-not (Test-Path $orchestrator)) { throw "orchestrator route.ts bulunamadi." }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("vectorbt-parameter-propagation-v1_2-backup_" + $stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item $generator (Join-Path $backup "experiment-generator-agent.ts") -Force
Copy-Item $orchestrator (Join-Path $backup "route.ts") -Force

# ============================================================
# 1) Generator: read imported parameters from context.input
#    without relying on the exact normalizeParameters formatting.
# ============================================================
$g = Get-Content $generator -Raw

if ($g -notmatch 'const\s+importedStrategyDefinition\s*=') {

    # Insert immediately before the experiment object.
    $experimentPattern = '(?m)^\s*const\s+experiment\s*:\s*ExperimentDefinition\s*=\s*\{'

    $m = [regex]::Match($g, $experimentPattern)

    if (-not $m.Success) {
        throw "Generator const experiment: ExperimentDefinition anchor bulunamadi."
    }

    $injection = @'
  const generatorInput =
    isRecord(context.input)
      ? context.input
      : {};

  const importedStrategyDefinition =
    isRecord(generatorInput.strategyDefinition)
      ? generatorInput.strategyDefinition
      : isRecord(generatorInput.importedStrategy)
        ? generatorInput.importedStrategy
        : isRecord(generatorInput.strategyImport)
          ? generatorInput.strategyImport
          : {};

  const importedParameters =
    isRecord(importedStrategyDefinition.parameters)
      ? importedStrategyDefinition.parameters
      : {};

'@

    $g =
        $g.Substring(0, $m.Index) +
        $injection +
        $g.Substring($m.Index)

    # Replace ONLY the strategy.parameters field belonging to the experiment.
    # Search from "strategy: {" to its first parameters field.
    $strategyPattern = '(?s)(strategy:\s*\{\s*.*?)(\bparameters\s*,)(\s*\})'

    $sm = [regex]::Match($g, $strategyPattern)

    if (-not $sm.Success) {
        throw "Generator experiment.strategy.parameters anchor bulunamadi."
    }

    $replacement =
        $sm.Groups[1].Value +
        'parameters: Object.keys(parameters).length > 0 ? parameters : importedParameters,' +
        $sm.Groups[3].Value

    $g =
        $g.Substring(0, $sm.Index) +
        $replacement +
        $g.Substring($sm.Index + $sm.Length)

    Set-Content -Path $generator -Value $g -Encoding UTF8
    Write-Host "Generator imported parameter fallback eklendi." -ForegroundColor Green
}
else {
    Write-Host "Generator imported parameter fallback zaten mevcut; tekrar patchlenmedi." -ForegroundColor Yellow
}

# ============================================================
# 2) Orchestrator: preserve top-level strategyDefinition.
# ============================================================
$o = Get-Content $orchestrator -Raw

if ($o -notmatch 'input\.strategyDefinition\s*=\s*body\.strategyDefinition') {

    # Find the buildContext input declaration in a formatting-tolerant way.
    $patterns = @(
        '(?s)const\s+input\s*=\s*isRecord\(body\.input\)\s*\?\s*body\.input\s*:\s*\{\}\s*;',
        '(?s)const\s+input\s*:\s*JsonRecord\s*=\s*isRecord\(body\.input\)\s*\?\s*\{\s*\.\.\.body\.input\s*\}\s*:\s*\{\}\s*;',
        '(?s)const\s+input\s*:\s*JsonRecord\s*=\s*isRecord\(body\.input\)\s*\?\s*body\.input\s*:\s*\{\}\s*;'
    )

    $cm = $null
    foreach ($pattern in $patterns) {
        $candidate = [regex]::Match($o, $pattern)
        if ($candidate.Success) {
            $cm = $candidate
            break
        }
    }

    if (-not $cm -or -not $cm.Success) {
        throw "Orchestrator buildContext input anchor bulunamadi."
    }

    $inputBlock = $cm.Value

    # Normalize to a mutable copy of body.input, then preserve engine + strategy.
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

    $o =
        $o.Substring(0, $cm.Index) +
        $newInput +
        $o.Substring($cm.Index + $cm.Length)

    Set-Content -Path $orchestrator -Value $o -Encoding UTF8
    Write-Host "Orchestrator strategyDefinition aktarimi garanti edildi." -ForegroundColor Green
}
else {
    Write-Host "Orchestrator strategyDefinition aktarimi zaten mevcut; tekrar patchlenmedi." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT Parameter Propagation Fix V1.2 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Generator    : $generator"
Write-Host "Orchestrator : $orchestrator"
Write-Host "Backup       : $backup"
Write-Host ""
Write-Host "Beklenen canonical parameters:"
Write-Host "  sma_fast=20"
Write-Host "  sma_slow=100"
Write-Host "  rsi_period=14"
Write-Host "  rsi_entry=50"
Write-Host ""
Write-Host "Not: Patch normalizeParameters satir formatina bagli degil."
Write-Host ""
Write-Host "Sonraki:"
Write-Host "  cd frontend"
Write-Host "  npm run build"
Write-Host "  cd .."
Write-Host "  .\MARKETHQ_VectorBT_E2E_Test_V1.ps1"
Write-Host "============================================================" -ForegroundColor Cyan
