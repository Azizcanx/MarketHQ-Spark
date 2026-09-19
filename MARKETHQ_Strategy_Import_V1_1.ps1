$ErrorActionPreference = "Stop"

# MarketHQ Strategy Import V1.2
# Purpose:
#   Wire the V1.1 imported strategy into the canonical Experiment Generator
#   strategy contract consumed by Experiment Runner / backtest pipeline.
#
# Research-only:
#   This patch treats imported strategy definitions as DATA.
#   It does not execute imported code, enable broker execution, or write DB data.

$root = (Get-Location).Path
$frontend = Join-Path $root "frontend"
$generator = Join-Path $frontend "components\agents\experiment-generator-agent.ts"

if (-not (Test-Path $frontend)) {
    throw "MarketHQ rootunda degilsin."
}

if (-not (Test-Path $generator)) {
    throw "experiment-generator-agent.ts bulunamadi."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root "strategy-import-v1_2-backup_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $generator (Join-Path $backupDir "experiment-generator-agent.ts") -Force

$content = Get-Content $generator -Raw

# ---------------------------------------------------------------------------
# 1) Add importedStrategy reference immediately after strategyOutput extraction.
# ---------------------------------------------------------------------------
$anchor1 = @'
  const strategyOutput =
    extractStrategyOutput(
      context
    );
'@

$insert1 = @'
  const strategyOutput =
    extractStrategyOutput(
      context
    );

  // V1.2: imported strategy becomes the preferred canonical strategy source.
  // The imported definition is data only; no imported code is executed.
  const importedStrategy =
    isRecord(strategyOutput.importedStrategy)
      ? strategyOutput.importedStrategy
      : null;
'@

if ($content.Contains($insert1)) {
    Write-Host "V1.2 import block already present; continuing."
} elseif ($content.Contains($anchor1)) {
    $content = $content.Replace($anchor1, $insert1)
} else {
    throw "V1.2 anchor #1 bulunamadi: strategyOutput extraction blogu."
}

# ---------------------------------------------------------------------------
# 2) Strategy ID: imported strategy first, then existing context/output.
# ---------------------------------------------------------------------------
$old2 = @'
  const strategyId =
    context.strategyId ||
    toStringValue(
      strategyOutput.strategyId
    ) ||
    "UNKNOWN_STRATEGY";
'@

$new2 = @'
  const strategyId =
    toStringValue(
      importedStrategy?.strategyId
    ) ||
    context.strategyId ||
    toStringValue(
      strategyOutput.strategyId
    ) ||
    "UNKNOWN_STRATEGY";
'@

if ($content.Contains($new2)) {
    Write-Host "V1.2 strategyId block already present."
} elseif ($content.Contains($old2)) {
    $content = $content.Replace($old2, $new2)
} else {
    throw "V1.2 anchor #2 bulunamadi: strategyId blogu."
}

# ---------------------------------------------------------------------------
# 3) Strategy name: imported strategy first, then existing resolver.
# ---------------------------------------------------------------------------
$old3 = @'
  const strategyName =
    buildStrategyName(
      strategyOutput,
      context
    );
'@

$new3 = @'
  const strategyName =
    toStringValue(
      importedStrategy?.name
    ) ||
    buildStrategyName(
      strategyOutput,
      context
    );
'@

if ($content.Contains($new3)) {
    Write-Host "V1.2 strategyName block already present."
} elseif ($content.Contains($old3)) {
    $content = $content.Replace($old3, $new3)
} else {
    throw "V1.2 anchor #3 bulunamadi: strategyName blogu."
}

# ---------------------------------------------------------------------------
# 4) Rule definition: imported value first; convert structured JSON safely.
# ---------------------------------------------------------------------------
$old4 = @'
  const ruleDefinition =
    buildRuleDefinition(
      strategyOutput
    );
'@

$new4 = @'
  const importedRuleDefinition =
    typeof importedStrategy?.ruleDefinition ===
    "string"
      ? importedStrategy.ruleDefinition
      : importedStrategy?.ruleDefinition !==
          undefined
        ? JSON.stringify(
            importedStrategy.ruleDefinition
          ) ?? ""
        : "";

  const ruleDefinition =
    importedRuleDefinition ||
    buildRuleDefinition(
      strategyOutput
    );
'@

if ($content.Contains($new4)) {
    Write-Host "V1.2 ruleDefinition block already present."
} elseif ($content.Contains($old4)) {
    $content = $content.Replace($old4, $new4)
} else {
    throw "V1.2 anchor #4 bulunamadi: ruleDefinition blogu."
}

# ---------------------------------------------------------------------------
# 5) Parameters: imported parameters first; fallback preserves current flow.
# ---------------------------------------------------------------------------
$old5 = @'
  const parameters =
    normalizeParameters(
      strategyOutput
    );
'@

$new5 = @'
  const parameters =
    importedStrategy &&
    isRecord(
      importedStrategy.parameters
    )
      ? importedStrategy.parameters
      : normalizeParameters(
          strategyOutput
        );
'@

if ($content.Contains($new5)) {
    Write-Host "V1.2 parameters block already present."
} elseif ($content.Contains($old5)) {
    $content = $content.Replace($old5, $new5)
} else {
    throw "V1.2 anchor #5 bulunamadi: parameters blogu."
}

Set-Content -Path $generator -Value $content -Encoding UTF8

Write-Host ""
Write-Host "============================================================"
Write-Host "MarketHQ Strategy Import V1.2 kuruldu."
Write-Host "============================================================"
Write-Host "Generator : $generator"
Write-Host "Backup    : $backupDir"
Write-Host ""
Write-Host "V1.2 davranisi:"
Write-Host "  importedStrategy.strategyId  -> canonical strategyId"
Write-Host "  importedStrategy.name        -> canonical strategy name"
Write-Host "  importedStrategy.ruleDefinition -> canonical ruleDefinition"
Write-Host "  importedStrategy.parameters  -> canonical parameters"
Write-Host ""
Write-Host "Fallback: V1.1 import yoksa mevcut Strategy Agent akisi aynen kullanilir."
Write-Host "Research-only. Imported strategy code CALISTIRILMAZ."
Write-Host ""
Write-Host "Test:"
Write-Host "  cd frontend"
Write-Host "  npm run build"

