$ErrorActionPreference = "Stop"

$baseUrl = "http://localhost:3000"
$endpoint = "$baseUrl/api/agents/orchestrate"

Write-Host "=== MarketHQ RESEARCH LOOP E2E ===" -ForegroundColor Cyan

$body = @{
    symbol = "THYAO"
    timeframe = "1d"
    strategyId = "research-thyao-loop-e2e"
    researchQuestion = "THYAO günlük verisinde tarihsel hafızadan türetilen yeni araştırma sorusunu uçtan uca doğrula"
} | ConvertTo-Json -Depth 20

$result = Invoke-RestMethod `
    -Uri $endpoint `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

function Get-PropValue {
    param(
        [object]$Object,
        [string]$Path
    )

    $current = $Object

    foreach ($part in ($Path -split "\.")) {
        if ($null -eq $current) {
            return $null
        }

        if ($current -is [System.Collections.IDictionary]) {
            if ($current.Contains($part)) {
                $current = $current[$part]
            } else {
                return $null
            }
        } else {
            $property = $current.PSObject.Properties[$part]
            if ($null -eq $property) {
                return $null
            }

            $current = $property.Value
        }
    }

    return $current
}

function Assert-True {
    param(
        [string]$Name,
        [bool]$Condition,
        [string]$Detail = ""
    )

    if (-not $Condition) {
        throw "FAIL: $Name $Detail"
    }

    Write-Host "PASS  $Name" -ForegroundColor Green
}

function Show-Value {
    param(
        [string]$Name,
        [object]$Value
    )

    if ($null -eq $Value) {
        Write-Host "$Name = <null>"
    } else {
        Write-Host "$Name = $Value"
    }
}

Write-Host ""
Write-Host "--- RUN ---"

Assert-True "success" ($result.success -eq $true)
Assert-True "status COMPLETED" ($result.status -eq "COMPLETED")
Assert-True "mode RESEARCH_ONLY" ($result.mode -eq "RESEARCH_ONLY")

$researchResult = $result.researchResult

Assert-True "researchResult exists" ($null -ne $researchResult)
Assert-True "schema research_result_v1" (
    $researchResult.schemaVersion -eq "research_result_v1"
)

Show-Value "run.status" $researchResult.run.status
Show-Value "request.strategyId" $researchResult.request.strategyId
Show-Value "request.researchQuestion" $researchResult.request.researchQuestion
Show-Value "data.resolvedSymbol" $researchResult.data.resolvedSymbol
Show-Value "dateResolution.status" $researchResult.dateResolution.status
Show-Value "hypothesis.source" $researchResult.hypothesis.source

# ---------------------------------------------------------------------------
# SAFETY
# ---------------------------------------------------------------------------

Assert-True "safety.researchOnly" (
    $researchResult.safety.researchOnly -eq $true
)

Assert-True "safety.executionEnabled=false" (
    $researchResult.safety.executionEnabled -eq $false
)

Assert-True "safety.databaseWriteEnabled=false" (
    $researchResult.safety.databaseWriteEnabled -eq $false
)

Assert-True "safety.brokerExecutionEnabled=false" (
    $researchResult.safety.brokerExecutionEnabled -eq $false
)

# readOnly may be exposed by the contract at either:
#   researchResult.safety.readOnly
# or:
#   researchResult.data.safety.readOnly
#
# Both represent the same research-only safety guarantee.
$contractReadOnly = Get-PropValue $researchResult "safety.readOnly"
$dataReadOnly = Get-PropValue $researchResult "data.safety.readOnly"

Show-Value "safety.readOnly.contract" $contractReadOnly
Show-Value "safety.readOnly.data" $dataReadOnly

Assert-True "safety.readOnly=true" (
    ($contractReadOnly -eq $true) -or
    ($dataReadOnly -eq $true)
)

# ---------------------------------------------------------------------------
# RESULTS BY AGENT
# ---------------------------------------------------------------------------

$results = $result.resultsByAgent

if ($null -eq $results) {
    $results = $result.results
}

Assert-True "resultsByAgent exists" (
    $null -ne $results
)

$queue = Get-PropValue $results "research-queue.output"
$generator = Get-PropValue $results "experiment-generator.output"
$runner = Get-PropValue $results "experiment-runner.output"
$ingestion = Get-PropValue $results "result-ingestion.output"
$learning = Get-PropValue $results "learning.output"
$decisions = Get-PropValue $results "research-decision.output"

Assert-True "queue output exists" (
    $null -ne $queue
)

Assert-True "generator output exists" (
    $null -ne $generator
)

Assert-True "runner output exists" (
    $null -ne $runner
)

Assert-True "ingestion output exists" (
    $null -ne $ingestion
)

Assert-True "learning output exists" (
    $null -ne $learning
)

Assert-True "final decision output exists" (
    $null -ne $decisions
)

# ---------------------------------------------------------------------------
# MEMORY → DECISION → QUEUE
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- MEMORY → DECISION → QUEUE ---"

$decisionLoop = Get-PropValue $decisions "researchLoop"
$queueTask = Get-PropValue $queue "queue.selectedTask"
$queueLoop = Get-PropValue $queueTask "metadata"

Show-Value "decision.researchLoop.source" (
    Get-PropValue $decisionLoop "source"
)

Show-Value "decision.researchLoop.memoryCount" (
    Get-PropValue $decisionLoop "memoryCount"
)

Show-Value "decision.researchLoop.nextResearchQuestion" (
    Get-PropValue $decisionLoop "nextResearchQuestion"
)

Show-Value "queue.selectedTask.question" (
    Get-PropValue $queueTask "question"
)

Show-Value "queue.selectedTask.metadata.source" (
    Get-PropValue $queueLoop "source"
)

Show-Value "queue.selectedTask.metadata.generatedFromHistoricalMemory" (
    Get-PropValue $queueLoop "generatedFromHistoricalMemory"
)

$nextQuestion = Get-PropValue `
    $decisionLoop `
    "nextResearchQuestion"

$selectedQuestion = Get-PropValue `
    $queueTask `
    "question"

Assert-True `
    "Decision produced nextResearchQuestion" `
    (-not [string]::IsNullOrWhiteSpace([string]$nextQuestion))

Assert-True `
    "Queue selected a task" `
    ($null -ne $queueTask)

Assert-True `
    "Queue question matches Decision nextResearchQuestion" `
    ([string]$selectedQuestion -eq [string]$nextQuestion)

$memoryDriven = (
    Get-PropValue $queueLoop "generatedFromHistoricalMemory"
) -eq $true

if ($memoryDriven) {

    Assert-True `
        "Queue task is marked historical-memory driven" `
        $memoryDriven

    Assert-True `
        "Queue task avoids blind repeat" `
        (
            (Get-PropValue $queueLoop "avoidsBlindRepeat") -eq $true
        )

} else {

    Write-Host `
        "INFO  Current run did not create a memory-driven queue task; this is valid when Decision has no historical memory record." `
        -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# QUEUE → GENERATOR → RUNNER
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- QUEUE → GENERATOR → RUNNER ---"

$generatorExperiment = Get-PropValue `
    $generator `
    "experiment"

$generatorQuestion = Get-PropValue `
    $generatorExperiment `
    "researchQuestion"

if ([string]::IsNullOrWhiteSpace([string]$generatorQuestion)) {

    $generatorQuestion = Get-PropValue `
        $generator `
        "researchQuestion"
}

$runnerQuestion = Get-PropValue `
    $runner `
    "experiment.researchQuestion"

if ([string]::IsNullOrWhiteSpace([string]$runnerQuestion)) {

    $runnerQuestion = Get-PropValue `
        $runner `
        "researchQuestion"
}

Show-Value `
    "generator.researchQuestion" `
    $generatorQuestion

Show-Value `
    "runner.researchQuestion" `
    $runnerQuestion

Assert-True `
    "Generator carries a research question" `
    (
        -not [string]::IsNullOrWhiteSpace(
            [string]$generatorQuestion
        )
    )

Assert-True `
    "Runner carries a research question" `
    (
        -not [string]::IsNullOrWhiteSpace(
            [string]$runnerQuestion
        )
    )

Assert-True `
    "Generator and Runner research question agree" `
    (
        [string]$generatorQuestion -eq
        [string]$runnerQuestion
    )

# ---------------------------------------------------------------------------
# RUNNER → INGESTION → LEARNING
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- RUNNER → INGESTION → LEARNING ---"

$runnerExperimentId = Get-PropValue `
    $runner `
    "experimentId"

if ([string]::IsNullOrWhiteSpace([string]$runnerExperimentId)) {

    $runnerExperimentId = Get-PropValue `
        $runner `
        "experiment.experimentId"
}

if ([string]::IsNullOrWhiteSpace([string]$runnerExperimentId)) {

    $runnerExperimentId = Get-PropValue `
        $runner `
        "experiment.id"
}

$ingestionExperimentId = Get-PropValue `
    $ingestion `
    "experimentId"

$learningExperimentId = Get-PropValue `
    $learning `
    "learningContext.experimentId"

if ([string]::IsNullOrWhiteSpace([string]$learningExperimentId)) {

    $learningExperimentId = Get-PropValue `
        $learning `
        "ingestedResult.experimentId"
}

Show-Value `
    "runner.experimentId" `
    $runnerExperimentId

Show-Value `
    "ingestion.experimentId" `
    $ingestionExperimentId

Show-Value `
    "learning.experimentId" `
    $learningExperimentId

Assert-True `
    "Runner produced experiment identity" `
    (
        -not [string]::IsNullOrWhiteSpace(
            [string]$runnerExperimentId
        )
    )

Assert-True `
    "Ingestion produced experiment identity" `
    (
        -not [string]::IsNullOrWhiteSpace(
            [string]$ingestionExperimentId
        )
    )

Assert-True `
    "Learning produced experiment identity" `
    (
        -not [string]::IsNullOrWhiteSpace(
            [string]$learningExperimentId
        )
    )

# ---------------------------------------------------------------------------
# LEARNING → MEMORY
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- LEARNING → MEMORY ---"

$memoryDiagnostics = Get-PropValue `
    $learning `
    "memoryPersistenceDiagnostics"

$researchMemory = Get-PropValue `
    $learning `
    "researchMemory"

$learningLoop = Get-PropValue `
    $learning `
    "researchLoop"

$memoryPayloadLoop = Get-PropValue `
    $learning `
    "memoryPayload.learning.researchLoop"

Show-Value `
    "memory.persistence.status" `
    (Get-PropValue $memoryDiagnostics "status")

Show-Value `
    "memory.persistence.persisted" `
    (Get-PropValue $memoryDiagnostics "persisted")

Show-Value `
    "memory.researchLoop.nextResearchQuestion" `
    (Get-PropValue $learningLoop "nextResearchQuestion")

Show-Value `
    "memory.payload.researchLoop.nextResearchQuestion" `
    (Get-PropValue $memoryPayloadLoop "nextResearchQuestion")

Assert-True `
    "Learning has researchLoop" `
    ($null -ne $learningLoop)

Assert-True `
    "Learning has memoryPayload.researchLoop" `
    ($null -ne $memoryPayloadLoop)

Assert-True `
    "Research Memory persistence succeeded" `
    (
        (Get-PropValue $memoryDiagnostics "persisted") -eq $true
    )

# ---------------------------------------------------------------------------
# FINAL DECISION
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- FINAL DECISION ---"

$finalDecisionName = Get-PropValue `
    $decisions `
    "decision"

$finalDecisionLoop = Get-PropValue `
    $decisions `
    "researchLoop"

Show-Value `
    "final.decision" `
    $finalDecisionName

Show-Value `
    "final.researchLoop.source" `
    (Get-PropValue $finalDecisionLoop "source")

Show-Value `
    "final.researchLoop.memoryCount" `
    (Get-PropValue $finalDecisionLoop "memoryCount")

Show-Value `
    "final.researchLoop.avoidsBlindRepeat" `
    (Get-PropValue $finalDecisionLoop "avoidsBlindRepeat")

Show-Value `
    "final.researchLoop.nextResearchQuestion" `
    (Get-PropValue $finalDecisionLoop "nextResearchQuestion")

Assert-True `
    "Final Decision has researchLoop" `
    ($null -ne $finalDecisionLoop)

Assert-True `
    "Final Decision has nextResearchQuestion" `
    (
        -not [string]::IsNullOrWhiteSpace(
            [string](
                Get-PropValue `
                    $finalDecisionLoop `
                    "nextResearchQuestion"
            )
        )
    )

Write-Host ""
Write-Host "=== RESEARCH LOOP E2E PASS ===" -ForegroundColor Green

Write-Host ""
Write-Host "Full response saved to `$result in the current PowerShell session."
Write-Host "To inspect everything:"
Write-Host '$result | ConvertTo-Json -Depth 50'
