$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$generator = Join-Path $root "frontend\components\agents\experiment-generator-agent.ts"
$orchestrator = Join-Path $root "frontend\app\api\agents\orchestrator\route.ts"

if (-not (Test-Path $generator)) { throw "experiment-generator-agent.ts bulunamadi: $generator" }
if (-not (Test-Path $orchestrator)) { throw "orchestrator route bulunamadi: $orchestrator" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("vectorbt-e2e-wiring-backup_" + $stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item $generator (Join-Path $backup "experiment-generator-agent.ts") -Force
Copy-Item $orchestrator (Join-Path $backup "orchestrator-route.ts") -Force

# ------------------------------------------------------------
# 1) Experiment Generator
# ------------------------------------------------------------
$lines = @(Get-Content $generator)

# A) Interface field
$hasField = $false
foreach ($line in $lines) {
    if ($line.Trim() -eq 'researchEngine: "CURRENT" | "VECTORBT";') {
        $hasField = $true
        break
    }
}

if (-not $hasField) {
    $statusIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq "status: ExperimentStatus;") {
            $statusIndex = $i
            break
        }
    }
    if ($statusIndex -lt 0) { throw "Generator interface status satiri bulunamadi." }

    $newLines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $newLines.Add($lines[$i])
        if ($i -eq $statusIndex) {
            $newLines.Add('  researchEngine: "CURRENT" | "VECTORBT";')
        }
    }
    $lines = @($newLines)
}

# B) Read requested engine from context.input
$hasRequested = $false
foreach ($line in $lines) {
    if ($line.Trim() -eq "const requestedResearchEngine =") {
        $hasRequested = $true
        break
    }
}

if (-not $hasRequested) {
    $resolverIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq "const dateResolverOutput =") {
            $resolverIndex = $i
            break
        }
    }
    if ($resolverIndex -lt 0) { throw "Generator dateResolverOutput baslangici bulunamadi." }

    $resolverEnd = -1
    for ($i = $resolverIndex; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq ");") {
            $resolverEnd = $i
            break
        }
    }
    if ($resolverEnd -lt 0) { throw "Generator dateResolverOutput sonu bulunamadi." }

    $insert = @(
        "",
        "  const requestedResearchEngine =",
        "    toStringValue(",
        "      isRecord(context.input)",
        "        ? context.input.researchEngine",
        "        : null",
        "    ).toUpperCase();",
        "",
        '  const researchEngine: "CURRENT" | "VECTORBT" =',
        '    requestedResearchEngine === "VECTORBT"',
        '      ? "VECTORBT"',
        '      : "CURRENT";',
        ""
    )

    $newLines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $newLines.Add($lines[$i])
        if ($i -eq $resolverEnd) {
            foreach ($x in $insert) { $newLines.Add($x) }
        }
    }
    $lines = @($newLines)
}

# C) Put researchEngine into canonical experiment
$hasExperimentField = $false
foreach ($line in $lines) {
    if ($line.Trim() -eq "researchEngine,") {
        $hasExperimentField = $true
        break
    }
}

if (-not $hasExperimentField) {
    $experimentIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq "ExperimentDefinition = {") {
            $experimentIndex = $i
            break
        }
    }
    if ($experimentIndex -lt 0) { throw "Generator ExperimentDefinition nesnesi bulunamadi." }

    $blockedLineIndex = -1
    for ($i = $experimentIndex; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq ': "BLOCKED",') {
            $blockedLineIndex = $i
            break
        }
    }
    if ($blockedLineIndex -lt 0) { throw "Generator experiment BLOCKED satiri bulunamadi." }

    $newLines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $newLines.Add($lines[$i])
        if ($i -eq $blockedLineIndex) {
            $newLines.Add("")
            $newLines.Add("      researchEngine,")
        }
    }
    $lines = @($newLines)
}

Set-Content -Path $generator -Value $lines -Encoding UTF8

# ------------------------------------------------------------
# 2) Orchestrator compact Runner response
# ------------------------------------------------------------
$olines = @(Get-Content $orchestrator)

$hasEngineOutput = $false
foreach ($line in $olines) {
    if ($line.Trim() -eq "engine: researchExecutionEngine,") {
        $hasEngineOutput = $true
        break
    }
}

if (-not $hasEngineOutput) {
    $runnerLine = -1
    for ($i = 0; $i -lt $olines.Count; $i++) {
        if ($olines[$i].Trim() -eq "const researchExecution = output.researchExecution;") {
            $runnerLine = $i
            break
        }
    }
    if ($runnerLine -lt 0) { throw "Orchestrator researchExecution satiri bulunamadi." }

    $engineBlock = @(
        "",
        "      const executionResult =",
        "        isRecord(researchExecution.result)",
        "          ? researchExecution.result",
        "          : {};",
        "",
        "      const executionMeta =",
        "        isRecord(executionResult.execution)",
        "          ? executionResult.execution",
        "          : {};",
        "",
        "      const researchExecutionEngine =",
        '        typeof executionMeta.researchEngine === "string"',
        "          ? executionMeta.researchEngine",
        "          : null;",
        ""
    )

    $newOLines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $olines.Count; $i++) {
        $newOLines.Add($olines[$i])
        if ($i -eq $runnerLine) {
            foreach ($x in $engineBlock) { $newOLines.Add($x) }
        }
    }
    $olines = @($newOLines)

    $succeededLine = -1
    for ($i = $runnerLine; $i -lt $olines.Count; $i++) {
        if ($olines[$i].Trim() -eq "succeeded: researchExecution.succeeded ?? false,") {
            $succeededLine = $i
            break
        }
    }
    if ($succeededLine -lt 0) { throw "Orchestrator compact succeeded satiri bulunamadi." }

    $newOLines = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $olines.Count; $i++) {
        $newOLines.Add($olines[$i])
        if ($i -eq $succeededLine) {
            $newOLines.Add("        engine: researchExecutionEngine,")
        }
    }
    $olines = @($newOLines)
}

Set-Content -Path $orchestrator -Value $olines -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT E2E Wiring Fix V1.1 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Generator   : $generator"
Write-Host "Orchestrator: $orchestrator"
Write-Host "Backup      : $backup"
Write-Host ""
Write-Host "researchEngine request -> Experiment -> Adapter -> response"
Write-Host "hatti baglandi."
Write-Host ""
Write-Host "Sonraki: frontend npm run build"
Write-Host "============================================================" -ForegroundColor Cyan

