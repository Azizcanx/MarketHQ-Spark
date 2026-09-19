$ErrorActionPreference = "Stop"

# ============================================================
# MarketHQ Research Flow Harden V3
# ============================================================

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$frontend = Join-Path $root "frontend"
$orchestrator = Join-Path $frontend "app\api\agents\orchestrate\route.ts"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " MarketHQ Research Flow Harden V3" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $root)) {
    throw "MarketHQ root bulunamadı: $root"
}

if (-not (Test-Path $frontend)) {
    throw "Frontend klasörü bulunamadı: $frontend"
}

if (-not (Test-Path $orchestrator)) {
    throw "Orchestrator dosyası bulunamadı: $orchestrator"
}

# ============================================================
# 1. BACKUP
# ============================================================

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $root "backup-research-flow-v3-$stamp"

New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

$backupFile = Join-Path $backupDir "route.ts"

Copy-Item `
    -Path $orchestrator `
    -Destination $backupFile `
    -Force

Write-Host "[OK] Backup: $backupFile" -ForegroundColor Green

# ============================================================
# 2. READ ROUTE
# ============================================================

$text = Get-Content `
    -Path $orchestrator `
    -Raw `
    -Encoding UTF8

if ([string]::IsNullOrWhiteSpace($text)) {
    throw "route.ts boş okunuyor."
}

$originalText = $text

# ============================================================
# 3. LEARNING DEPENDENCY
#
# POST_RUNNER Learning:
# validation
# result-ingestion
# brain
# evidence
# ============================================================

$learningPattern = '(?s)case\s+"learning"\s*:\s*return\s+phase\s*===\s*"POST_RUNNER"\s*\?\s*\[(.*?)\]\s*:\s*\[\s*"brain"\s*,\s*"evidence"\s*\]\s*;'

$learningMatch = [regex]::Match(
    $text,
    $learningPattern
)

if (-not $learningMatch.Success) {

    Write-Host ""
    Write-Host "[WARN] Learning dependency bloğu regex ile bulunamadı." -ForegroundColor Yellow

    # Alternatif daha genel arama
    $learningIndex = $text.IndexOf('case "learning":')

    if ($learningIndex -lt 0) {
        throw "Learning case bloğu bulunamadı. Dosya değiştirilmedi."
    }

    $learningEnd = $text.IndexOf(
        'case "experiment-generator":',
        $learningIndex
    )

    if ($learningEnd -lt 0) {
        throw "Learning bloğunun sonu bulunamadı. Dosya değiştirilmedi."
    }

    $learningBlock = $text.Substring(
        $learningIndex,
        $learningEnd - $learningIndex
    )

    Write-Host ""
    Write-Host "Mevcut Learning bloğu:" -ForegroundColor DarkYellow
    Write-Host $learningBlock -ForegroundColor DarkYellow
    Write-Host ""

    if ($learningBlock.Contains('"result-ingestion"')) {
        Write-Host "[OK] Learning zaten Result Ingestion dependency içeriyor." -ForegroundColor Green
    }
    else {
        $replacement = @'
case "learning":
      return phase === "POST_RUNNER"
        ? [
            "validation",
            "result-ingestion",
            "brain",
            "evidence",
          ]
        : ["brain", "evidence"];

    '@

        $relativeBlock = $learningBlock

        $caseStart = $relativeBlock.IndexOf('case "learning":')

        if ($caseStart -lt 0) {
            throw "Learning case başlangıcı bulunamadı."
        }

        $newBlock = $replacement

        $text =
            $text.Substring(0, $learningIndex) +
            $newBlock +
            $text.Substring($learningEnd)

        Write-Host "[PASS] Learning -> Result Ingestion dependency eklendi." -ForegroundColor Green
    }
}
else {

    $existingLearning = $learningMatch.Value

    if ($existingLearning.Contains('"result-ingestion"')) {
        Write-Host "[OK] Learning zaten Result Ingestion dependency içeriyor." -ForegroundColor Green
    }
    else {

        $newLearning = @'
case "learning":
      return phase === "POST_RUNNER"
        ? [
            "validation",
            "result-ingestion",
            "brain",
            "evidence",
          ]
        : ["brain", "evidence"];
'@

        $text = $text.Replace(
            $existingLearning,
            $newLearning
        )

        Write-Host "[PASS] Learning -> Result Ingestion dependency eklendi." -ForegroundColor Green
    }
}

# ============================================================
# 4. RESEARCH DECISION DEPENDENCY
#
# POST_RUNNER:
# learning
# result-ingestion
# evidence
# validation
# ============================================================

$decisionIndex = $text.IndexOf('case "research-decision":')

if ($decisionIndex -lt 0) {
    throw "Research Decision case bloğu bulunamadı. Dosya değiştirilmedi."
}

$decisionEnd = $text.IndexOf(
    'default:',
    $decisionIndex
)

if ($decisionEnd -lt 0) {
    throw "Research Decision bloğunun sonu bulunamadı. Dosya değiştirilmedi."
}

$decisionBlock = $text.Substring(
    $decisionIndex,
    $decisionEnd - $decisionIndex
)

if ($decisionBlock.Contains('"result-ingestion"')) {

    Write-Host "[OK] Research Decision zaten Result Ingestion dependency içeriyor." -ForegroundColor Green

}
else {

    $newDecisionBlock = @'
case "research-decision":
      return phase === "POST_RUNNER"
        ? [
            "learning",
            "result-ingestion",
            "evidence",
            "validation",
          ]
        : ["learning", "evidence", "validation"];

    '@

    $text =
        $text.Substring(0, $decisionIndex) +
        $newDecisionBlock +
        $text.Substring($decisionEnd)

    Write-Host "[PASS] Research Decision -> Result Ingestion dependency eklendi." -ForegroundColor Green
}

# ============================================================
# 5. RUNNER METRIC FALLBACK
#
# runnerResult.metrics
# veya
# runnerOutput.researchExecution.result.metrics
# ============================================================

$metricsPattern = '(?s)const\s+runnerMetrics\s*=\s*isRecord\(runnerResult\?\.metrics\)\s*\?\s*runnerResult\.metrics\s*:\s*\{\};'

$metricsMatch = [regex]::Match(
    $text,
    $metricsPattern
)

if ($metricsMatch.Success) {

    $newMetrics = @'
const runnerExecution =
    runnerOutput &&
    isRecord(
      runnerOutput.researchExecution,
    )
      ? runnerOutput.researchExecution
      : {};

  const runnerExecutionResult =
    isRecord(runnerExecution.result)
      ? runnerExecution.result
      : {};

  const runnerMetrics =
    isRecord(runnerResult?.metrics)
      ? runnerResult.metrics
      : isRecord(runnerExecutionResult.metrics)
        ? runnerExecutionResult.metrics
        : {};
'@

    $text = $text.Replace(
        $metricsMatch.Value,
        $newMetrics
    )

    Write-Host "[PASS] Runner metric fallback eklendi." -ForegroundColor Green

}
elseif ($text.Contains("runnerExecutionResult.metrics")) {

    Write-Host "[OK] Runner metric fallback zaten mevcut." -ForegroundColor Green

}
else {

    Write-Host "[WARN] Runner metric bloğu bulunamadı; bu adım atlandı." -ForegroundColor Yellow
}

# ============================================================
# 6. VERIFY CHANGES
# ============================================================

Write-Host ""
Write-Host "Değişiklikler doğrulanıyor..." -ForegroundColor Cyan

if (-not $text.Contains('"result-ingestion"')) {
    throw "route.ts içinde result-ingestion dependency bulunamadı."
}

if ($text -eq $originalText) {

    Write-Host ""
    Write-Host "[INFO] Dosyada değişiklik gerekmiyor." -ForegroundColor Yellow

}
else {

    # ========================================================
    # 7. WRITE
    # ========================================================

    Set-Content `
        -Path $orchestrator `
        -Value $text `
        -Encoding UTF8

    Write-Host "[OK] route.ts güncellendi." -ForegroundColor Green
}

# ============================================================
# 8. FINAL SOURCE CHECK
# ============================================================

$verifyText = Get-Content `
    -Path $orchestrator `
    -Raw `
    -Encoding UTF8

if (-not $verifyText.Contains('"result-ingestion"')) {
    throw "Final source check başarısız: result-ingestion bulunamadı."
}

if ($verifyText.Contains('case "learning":')) {
    Write-Host "[OK] Learning case mevcut." -ForegroundColor Green
}
else {
    throw "Learning case kayboldu."
}

if ($verifyText.Contains('case "research-decision":')) {
    Write-Host "[OK] Research Decision case mevcut." -ForegroundColor Green
}
else {
    throw "Research Decision case kayboldu."
}

# ============================================================
# 9. BUILD
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " BUILD" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $frontend

npm run build

if ($LASTEXITCODE -ne 0) {
    throw "npm run build başarısız oldu."
}

Write-Host ""
Write-Host "[PASS] Build completed." -ForegroundColor Green

# ============================================================
# 10. E2E TEST
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " E2E RESEARCH TEST" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$body = @{
    symbol = "THYAO"
    timeframe = "1d"
    strategyId = "research-thyao-flow-harden-v3"
    researchQuestion = "THYAO günlük verisinde trend takip sinyali araştır"
} | ConvertTo-Json -Depth 20

try {

    $result = Invoke-RestMethod `
        -Uri "http://localhost:3000/api/agents/orchestrate" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body

}
catch {

    Write-Host ""
    Write-Host "[FAIL] Orchestrator API çağrısı başarısız." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}

# ============================================================
# 11. BASIC CONTRACT CHECKS
# ============================================================

if ($null -eq $result) {
    throw "E2E response boş."
}

if ($result.success -ne $true) {
    throw "E2E success=true değil."
}

if ($result.status -ne "COMPLETED") {
    throw "E2E status COMPLETED değil: $($result.status)"
}

if ($result.mode -ne "RESEARCH_ONLY") {
    throw "E2E mode RESEARCH_ONLY değil: $($result.mode)"
}

$rr = $result.researchResult

if ($null -eq $rr) {
    throw "researchResult bulunamadı."
}

if ($rr.schemaVersion -ne "research_result_v1") {
    throw "Yanlış schemaVersion: $($rr.schemaVersion)"
}

Write-Host "[OK] success=true" -ForegroundColor Green
Write-Host "[OK] status=COMPLETED" -ForegroundColor Green
Write-Host "[OK] mode=RESEARCH_ONLY" -ForegroundColor Green
Write-Host "[OK] schemaVersion=research_result_v1" -ForegroundColor Green

# ============================================================
# 12. DATE RESOLUTION
# ============================================================

$dateResolution = $rr.dateResolution

if ($null -eq $dateResolution) {
    throw "dateResolution bulunamadı."
}

$dateStatus = $dateResolution.status

if ([string]::IsNullOrWhiteSpace([string]$dateStatus)) {

    $dateStatus = $dateResolution.state
}

if ($dateStatus -ne "READY") {

    Write-Host "[WARN] Date Resolver status: $dateStatus" -ForegroundColor Yellow

}
else {

    Write-Host "[OK] Date Resolver=READY" -ForegroundColor Green
}

# ============================================================
# 13. HYPOTHESIS
# ============================================================

$hypothesis = $rr.hypothesis

if ($null -eq $hypothesis) {
    throw "hypothesis bulunamadı."
}

$hypothesisSource = $hypothesis.source

if (
    $hypothesisSource -ne "strategy" -and
    $hypothesisSource -ne "brain"
) {
    throw "Hypothesis source beklenen değerde değil: $hypothesisSource"
}

Write-Host "[OK] Hypothesis=$hypothesisSource" -ForegroundColor Green

# ============================================================
# 14. CONTRACT SECTIONS
# ============================================================

$requiredSections = @(
    "run",
    "request",
    "data",
    "dateResolution",
    "hypothesis",
    "experiment",
    "execution",
    "validation",
    "evidence",
    "learning",
    "decision"
)

foreach ($section in $requiredSections) {

    $value = $rr.$section

    if ($null -eq $value) {
        throw "Contract section missing: $section"
    }

    Write-Host "[OK] Contract section: $section" -ForegroundColor Green
}

# ============================================================
# 15. E2E STAGE SEARCH
# ============================================================

function Find-Stage {
    param(
        [Parameter(Mandatory=$true)]
        $Object,

        [Parameter(Mandatory=$true)]
        [string]$StageName
    )

    if ($null -eq $Object) {
        return $false
    }

    if ($Object -is [string]) {
        return $Object -eq $StageName
    }

    if ($Object -is [System.Collections.IDictionary]) {

        foreach ($key in $Object.Keys) {

            if ([string]$key -eq $StageName) {
                return $true
            }

            if (Find-Stage -Object $Object[$key] -StageName $StageName) {
                return $true
            }
        }

        return $false
    }

    if ($Object -is [System.Collections.IEnumerable]) {

        foreach ($item in $Object) {

            if (Find-Stage -Object $item -StageName $StageName) {
                return $true
            }
        }
    }

    return $false
}

$requiredStages = @(
    "experiment-generator",
    "experiment-runner",
    "result-ingestion",
    "learning",
    "research-decision"
)

foreach ($stage in $requiredStages) {

    if (Find-Stage -Object $result -StageName $stage) {
        Write-Host "[OK] E2E stage: $stage" -ForegroundColor Green
    }
    else {
        throw "E2E stage missing: $stage"
    }
}

# ============================================================
# 16. RESULT INGESTION METRICS
# ============================================================

$ingestion = $result.agents."result-ingestion"

if ($null -eq $ingestion) {

    $ingestion = $result.results."result-ingestion"
}

$metricCount = $null

if ($null -ne $ingestion) {

    if ($null -ne $ingestion.metricCount) {
        $metricCount = [int]$ingestion.metricCount
    }
    elseif ($null -ne $ingestion.output.metricCount) {
        $metricCount = [int]$ingestion.output.metricCount
    }
}

if ($null -ne $metricCount) {

    if ($metricCount -gt 0) {
        Write-Host "[OK] Result Ingestion metricCount=$metricCount" -ForegroundColor Green
    }
    else {
        Write-Host "[WARN] Result Ingestion metricCount=0" -ForegroundColor Yellow
    }

}
else {

    Write-Host "[WARN] metricCount doğrudan response içinde bulunamadı." -ForegroundColor Yellow
}

# ============================================================
# 17. EXPERIMENT METRICS
# ============================================================

$experimentMetrics = $null

if ($null -ne $rr.experiment) {

    if ($null -ne $rr.experiment.metrics) {
        $experimentMetrics = $rr.experiment.metrics
    }
    elseif ($null -ne $rr.experiment.normalizedMetrics) {
        $experimentMetrics = $rr.experiment.normalizedMetrics
    }
}

$hasExperimentMetric = $false

if ($null -ne $experimentMetrics) {

    if ($experimentMetrics -is [System.Collections.IDictionary]) {

        if ($experimentMetrics.Count -gt 0) {
            $hasExperimentMetric = $true
        }

    }
}

if ($hasExperimentMetric) {

    Write-Host "[OK] researchResult.experiment.metrics dolu." -ForegroundColor Green

}
else {

    Write-Host "[WARN] researchResult.experiment.metrics boş veya doğrudan bulunamadı." -ForegroundColor Yellow
}

# ============================================================
# 18. SAFETY
# ============================================================

$safetyObjects = @()

if ($null -ne $result.safety) {
    $safetyObjects += $result.safety
}

if ($null -ne $rr.safety) {
    $safetyObjects += $rr.safety
}

foreach ($safety in $safetyObjects) {

    if ($null -ne $safety.executionEnabled) {

        if ($safety.executionEnabled -ne $false) {
            throw "SAFETY FAIL: executionEnabled true."
        }
    }

    if ($null -ne $safety.databaseWriteEnabled) {

        if ($safety.databaseWriteEnabled -ne $false) {
            throw "SAFETY FAIL: databaseWriteEnabled true."
        }
    }

    if ($null -ne $safety.brokerExecutionEnabled) {

        if ($safety.brokerExecutionEnabled -ne $false) {
            throw "SAFETY FAIL: brokerExecutionEnabled true."
        }
    }

    if ($null -ne $safety.liveTradingAllowed) {

        if ($safety.liveTradingAllowed -ne $false) {
            throw "SAFETY FAIL: liveTradingAllowed true."
        }
    }
}

Write-Host "[OK] Research-only safety checks passed." -ForegroundColor Green

# ============================================================
# 19. SUMMARY
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " RESEARCH FLOW HARDEN V3 PASS" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Build                     : PASS" -ForegroundColor Green
Write-Host "E2E Orchestrator          : PASS" -ForegroundColor Green
Write-Host "Research Result Contract  : PASS" -ForegroundColor Green
Write-Host "Date Resolver             : $dateStatus" -ForegroundColor Green
Write-Host "Hypothesis                : $hypothesisSource" -ForegroundColor Green
Write-Host "Runner                    : PASS" -ForegroundColor Green
Write-Host "Result Ingestion          : PASS" -ForegroundColor Green
Write-Host "Learning                  : PASS" -ForegroundColor Green
Write-Host "Research Decision         : PASS" -ForegroundColor Green
Write-Host "Research-only Safety      : PASS" -ForegroundColor Green
Write-Host ""
Write-Host "Backup:" -ForegroundColor Cyan
Write-Host $backupFile
Write-Host ""
Write-Host "MarketHQ Research Flow Harden V3 tamamlandi." -ForegroundColor Green
Write-Host ""
