$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$OrchestrateUrl = "http://localhost:3000/api/agents/orchestrate"

Write-Host ""
Write-Host "=== MARKET HQ RESEARCH SPRINT V1 ===" -ForegroundColor Cyan
Write-Host ""

Set-Location $ProjectRoot

$requiredFiles = @(
    "frontend\app\api\agents\orchestrate\route.ts",
    "frontend\components\agents\experiment-runner-agent.ts",
    "frontend\components\agents\result-ingestion-agent.ts",
    "frontend\components\agents\learning-agent.ts",
    "frontend\components\agents\research-decision-agent.ts",
    "frontend\components\agents\paper-trading-agent.ts"
)

foreach ($relative in $requiredFiles) {
    $full = Join-Path $ProjectRoot $relative
    if (Test-Path $full) {
        Write-Host "[OK] $relative" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] $relative" -ForegroundColor Red
        throw "Required file missing: $relative"
    }
}

Write-Host ""
Write-Host "[INFO] Turbopack spawn patch skipped; warnings are non-blocking." -ForegroundColor Yellow
Write-Host ""

# -------------------------
# BUILD
# -------------------------
Write-Host "=== BUILD ===" -ForegroundColor Cyan
Set-Location $FrontendRoot

npm run build
if ($LASTEXITCODE -ne 0) {
    throw "npm run build failed with exit code $LASTEXITCODE"
}

Write-Host "[PASS] Build completed." -ForegroundColor Green
Write-Host ""

# -------------------------
# E2E RESEARCH TEST
# -------------------------
Write-Host "=== E2E RESEARCH TEST ===" -ForegroundColor Cyan

try {
    $body = @{
        symbol = "THYAO"
        timeframe = "1d"
        strategyId = "research-thyao-e2e-final"
        researchQuestion = "THYAO günlük verisinde trend takip sinyali araştır"
    } | ConvertTo-Json -Depth 20

    $result = Invoke-RestMethod `
        -Uri $OrchestrateUrl `
        -Method Post `
        -ContentType "application/json" `
        -Body $body
}
catch {
    Write-Host "[FAIL] Orchestrator request failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}

if ($null -eq $result) {
    throw "Orchestrator returned an empty response."
}

$rr = $result.researchResult

if ($null -eq $rr) {
    throw "researchResult is missing from orchestrator response."
}

function Get-FirstValue {
    param(
        [object]$Object,
        [string[]]$Names
    )

    if ($null -eq $Object) { return $null }

    foreach ($name in $Names) {
        $prop = $Object.PSObject.Properties[$name]
        if ($null -ne $prop -and $null -ne $prop.Value) {
            return $prop.Value
        }
    }

    return $null
}

function Find-StringArrayContaining {
    param(
        [object]$Object,
        [string[]]$Needles
    )

    $found = New-Object System.Collections.Generic.List[string]

    function Walk {
        param([object]$Node)

        if ($null -eq $Node) { return }

        if ($Node -is [System.Collections.IEnumerable] -and
            -not ($Node -is [string]) -and
            -not ($Node -is [System.Collections.IDictionary])) {

            $strings = @($Node | Where-Object { $_ -is [string] })
            if ($strings.Count -gt 0) {
                foreach ($needle in $Needles) {
                    if ($strings -contains $needle) {
                        [void]$found.Add($needle)
                    }
                }
            }

            foreach ($item in $Node) {
                if ($null -ne $item -and
                    -not ($item -is [string])) {
                    Walk $item
                }
            }
            return
        }

        if ($Node -is [System.Collections.IDictionary]) {
            foreach ($key in $Node.Keys) {
                Walk $Node[$key]
            }
            return
        }

        if ($Node.PSObject -and $Node.PSObject.Properties.Count -gt 0) {
            foreach ($prop in $Node.PSObject.Properties) {
                if ($null -ne $prop.Value -and
                    -not ($prop.Value -is [string])) {
                    Walk $prop.Value
                }
            }
        }
    }

    Walk $Object
    return @($found | Select-Object -Unique)
}

# Contract fields can differ between nested run/execution representations.
# Read the known contract fields first, then fall back to recursive lookup.
$run = $rr.run
$execution = $rr.execution
$data = $rr.data

$resolvedSymbol = Get-FirstValue $data @("resolvedSymbol", "resolved_symbol", "symbol")
$dataSource = Get-FirstValue $data @("source", "dataSource", "provider")
$dataBars = Get-FirstValue $data @("rowCount", "bars", "barCount", "dataBars", "rows")

$dateResolution = $rr.dateResolution
$dateStatus = Get-FirstValue $dateResolution @("status", "state")

$hypothesis = $rr.hypothesis
$hypothesisSource = Get-FirstValue $hypothesis @("source")

$runStatus = Get-FirstValue $run @("status", "runStatus")
if ($null -eq $runStatus) {
    $runStatus = $result.status
}

$executionCandidates = @(
    $run,
    $execution,
    $result
)

$requiredStages = @(
    "experiment-generator",
    "experiment-runner",
    "result-ingestion",
    "learning",
    "research-decision"
)

$stageSearchObject = [PSCustomObject]@{
    run = $run
    execution = $execution
    result = $result
}

$foundStages = Find-StringArrayContaining $stageSearchObject $requiredStages

Write-Host ""
Write-Host ("success       : " + $result.success)
Write-Host ("status        : " + $result.status)
Write-Host ("mode          : " + $result.mode)
Write-Host ("schemaVersion : " + $rr.schemaVersion)
Write-Host ("runId         : " + (Get-FirstValue $run @("runId", "id")))
Write-Host ("symbol        : " + $rr.request.symbol)
Write-Host ("timeframe     : " + $rr.request.timeframe)
Write-Host ("question      : " + $rr.request.researchQuestion)
Write-Host ("resolvedSymbol: " + $resolvedSymbol)
Write-Host ("dataSource    : " + $dataSource)
Write-Host ("dataBars      : " + $dataBars)
Write-Host ("dateResolver  : " + $dateStatus)
Write-Host ("hypothesis    : " + $hypothesisSource)
Write-Host ""

# Basic E2E contract assertions.
if ($result.success -ne $true) {
    throw "Orchestrator returned success != true."
}

if ($result.status -ne "COMPLETED") {
    throw "Orchestrator status is not COMPLETED: $($result.status)"
}

if ($result.mode -ne "RESEARCH_ONLY") {
    throw "Unexpected execution mode: $($result.mode)"
}

if ($rr.schemaVersion -ne "research_result_v1") {
    throw "Unexpected Research Result Contract schema: $($rr.schemaVersion)"
}

if ($dateStatus -ne "READY") {
    throw "Date Resolver is not READY: $dateStatus"
}

if ($hypothesisSource -notin @("strategy", "brain")) {
    throw "Hypothesis source is not valid: $hypothesisSource"
}

$contractSections = @(
    @{ Name = "request"; Value = $rr.request },
    @{ Name = "data"; Value = $rr.data },
    @{ Name = "dateResolution"; Value = $rr.dateResolution },
    @{ Name = "hypothesis"; Value = $rr.hypothesis },
    @{ Name = "experiment"; Value = $rr.experiment },
    @{ Name = "execution"; Value = $rr.execution },
    @{ Name = "validation"; Value = $rr.validation },
    @{ Name = "evidence"; Value = $rr.evidence },
    @{ Name = "learning"; Value = $rr.learning },
    @{ Name = "decision"; Value = $rr.decision }
)

foreach ($section in $contractSections) {
    if ($null -ne $section.Value) {
        Write-Host "[OK] Contract section: $($section.Name)" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] Contract section missing: $($section.Name)" -ForegroundColor Red
        throw "Research Result Contract section missing: $($section.Name)"
    }
}

# Verify required pipeline stage names are actually represented somewhere
# in the returned execution/result structures. This avoids assuming a single
# property path such as researchResult.run.executionOrder.
foreach ($stage in $requiredStages) {
    if ($foundStages -contains $stage) {
        Write-Host "[OK] E2E stage present: $stage" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] E2E stage not represented in response: $stage" -ForegroundColor Red
        throw "Required E2E stage is not represented in the orchestrator response: $stage"
    }
}

# Research-only safety guard.
$safetyObjects = @()
if ($null -ne $result.safety) { $safetyObjects += $result.safety }
if ($null -ne $rr.safety) { $safetyObjects += $rr.safety }

foreach ($safety in $safetyObjects) {
    if ($safety.executionEnabled -eq $true) {
        throw "SAFETY FAILURE: executionEnabled=true"
    }
    if ($safety.databaseWriteEnabled -eq $true) {
        throw "SAFETY FAILURE: databaseWriteEnabled=true"
    }
    if ($safety.brokerExecutionEnabled -eq $true) {
        throw "SAFETY FAILURE: brokerExecutionEnabled=true"
    }
}

if ($runStatus -and $runStatus -ne "COMPLETED") {
    throw "Research run status is not COMPLETED: $runStatus"
}

Write-Host ""
Write-Host "=== RESEARCH SPRINT PASS ===" -ForegroundColor Green
Write-Host "Build + single E2E research pipeline + contract + safety checks passed." -ForegroundColor Green
Write-Host ""

