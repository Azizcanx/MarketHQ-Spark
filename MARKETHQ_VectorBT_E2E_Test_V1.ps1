$ErrorActionPreference = "Stop"

$projectRoot = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$endpoint = "http://localhost:3000/api/agents/orchestrate"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT E2E Test V1" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $projectRoot)) {
    throw "MarketHQ project root bulunamadi: $projectRoot"
}

Write-Host "Request gonderiliyor..." -ForegroundColor Yellow

$strategy = [ordered]@{
    schemaVersion = "MARKETHQ_STRATEGY_V1"
    strategyId = "STR-DEMO001"
    name = "Example Imported Trend Strategy"
    ruleDefinition = [ordered]@{
        entry = @(
            "SMA(20) > SMA(100)"
            "RSI(14) > 50"
        )
        exit = @(
            "SMA(20) < SMA(100)"
        )
    }
    parameters = [ordered]@{
        sma_fast = 20
        sma_slow = 100
        rsi_period = 14
        rsi_entry = 50
    }
    signalConfig = [ordered]@{
        entry_mode = "LONG_ONLY"
        confirmation = "AND"
    }
    riskConfig = [ordered]@{
        stop_atr_multiple = 1.5
        target_atr_multiple = 3.0
    }
    supportedMarkets = @("BIST")
    supportedTimeframes = @("1d")
    source = [ordered]@{
        type = "external_strategy"
        name = "demo"
    }
    provenance = [ordered]@{
        importVersion = "1"
        notes = "Example only; not a verified strategy."
    }
}

$body = [ordered]@{
    strategyId = "STR-DEMO001"
    symbol = "THYAO"
    timeframe = "1d"
    researchEngine = "VECTORBT"
    researchQuestion = "VectorBT E2E entegrasyon testi - THYAO"
    strategyDefinition = $strategy
    parameterSweep = [ordered]@{
        sma_fast = @(10, 20, 30)
        sma_slow = @(50, 100)
    }
    parameterSearchMethod = "grid"
    parameterSearchCount = 6
}

$payload = $body | ConvertTo-Json -Depth 20

try {
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri $endpoint `
        -ContentType "application/json" `
        -Body $payload
}
catch {
    Write-Host ""
    Write-Host "API istegi basarisiz." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    throw
}

Write-Host "E2E sonucu alindi." -ForegroundColor Green
Write-Host ""

function Find-FirstRecord {
    param([object]$Node)

    if ($null -eq $Node) {
        return $null
    }

    if ($Node -is [System.Collections.IDictionary]) {
        if ($Node.Contains("researchExecution") -and $Node.researchExecution) {
            return $Node.researchExecution
        }

        foreach ($value in $Node.Values) {
            $found = Find-FirstRecord $value
            if ($found) {
                return $found
            }
        }
    }
    elseif ($Node -is [System.Management.Automation.PSCustomObject]) {
        $props = $Node.PSObject.Properties

        $researchExecution = $props |
            Where-Object { $_.Name -eq "researchExecution" } |
            Select-Object -First 1

        if ($researchExecution -and $researchExecution.Value) {
            return $researchExecution.Value
        }

        foreach ($prop in $props) {
            $found = Find-FirstRecord $prop.Value
            if ($found) {
                return $found
            }
        }
    }
    elseif ($Node -is [System.Collections.IEnumerable] -and -not ($Node -is [string])) {
        foreach ($item in $Node) {
            $found = Find-FirstRecord $item
            if ($found) {
                return $found
            }
        }
    }

    return $null
}

$execution = Find-FirstRecord $response

Write-Host "---------------- KANIT KONTROLU ----------------" -ForegroundColor Yellow
Write-Host ""

$fullJson = $response | ConvertTo-Json -Depth 80

$engineVersion = $null
$versionMatch = [regex]::Match($fullJson, '"engineVersion"\s*:\s*"([^"]+)"')
if ($versionMatch.Success) {
    $engineVersion = $versionMatch.Groups[1].Value
}
if ($engineVersion) {
    Write-Host ("VectorBT engineVersion : {0}" -f $engineVersion) -ForegroundColor Cyan
}
else {
    Write-Host "VectorBT engineVersion : bulunamadi" -ForegroundColor DarkYellow
}

$checks = [ordered]@{
    "VECTORBT route requested" = ($fullJson -match '"VECTORBT"')
    "VectorBT engine reported" = ($fullJson -match '"engine"\s*:\s*"VECTORBT"')
    "execution researchEngine" = ($fullJson -match '"researchEngine"\s*:\s*"VECTORBT"')
    "VectorBT engine version" = ($fullJson -match '"engineVersion"\s*:\s*"[^"]+"')
    "Systematic optimizer source" = ($fullJson -match '"source"\s*:\s*"SYSTEMATIC_TRADING_FRAMEWORK"')
    "Parameter sweep requested" = ($fullJson -match '"requested"\s*:\s*true')
    "Multiple candidates" = ($fullJson -match '"candidateCount"\s*:\s*([2-9]|[1-9][0-9]+)')
    "research-only true" = ($fullJson -match '"researchOnly"\s*:\s*true')
    "broker execution false" = ($fullJson -match '"brokerExecutionEnabled"\s*:\s*false')
    "database write false" = ($fullJson -match '"databaseWriteEnabled"\s*:\s*false')
}

foreach ($item in $checks.GetEnumerator()) {
    $mark = if ($item.Value) { "PASS" } else { "FAIL" }
    $color = if ($item.Value) { "Green" } else { "Red" }

    Write-Host (
        ("{0,-30} {1}" -f $item.Key, $mark)
    ) -ForegroundColor $color
}

Write-Host ""
Write-Host "---------------- KISA RESULT ----------------" -ForegroundColor Yellow

if ($execution) {
    Write-Host ($execution | ConvertTo-Json -Depth 40)
}
else {
    Write-Host "researchExecution objesi otomatik bulunamadi; full JSON dosyaya yaziliyor." -ForegroundColor DarkYellow
}

$outPath = Join-Path $projectRoot "vectorbt-e2e-result.json"

$response |
    ConvertTo-Json -Depth 80 |
    Set-Content $outPath -Encoding UTF8

Write-Host ""
Write-Host "Full result: $outPath" -ForegroundColor Cyan
Write-Host ""

$passed = @(
    $checks.Values |
    Where-Object { $_ -eq $true }
).Count

$total = $checks.Count

if ($passed -eq $total) {
    Write-Host "VECTORBT E2E KANITI: PASS" -ForegroundColor Green
}
else {
    Write-Host "VECTORBT E2E KANITI: INCOMPLETE ($passed/$total)" -ForegroundColor Yellow
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""




