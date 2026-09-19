$ErrorActionPreference = "Stop"

$projectRoot = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$file = Join-Path $projectRoot "frontend\app\api\agents\orchestrator\route.ts"

if (-not (Test-Path $file)) {
    throw "Orchestrator route bulunamadi: $file"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = "$file.MARKETHQ_RESEARCH_LOOP_MODE_$stamp.bak"

Copy-Item $file $backup -Force

$text = Get-Content $file -Raw

# ============================================================
# 1) OrchestratorResponse interface
# ============================================================

$interfaceMatch = [regex]::Match(
    $text,
    'interface\s+OrchestratorResponse\s*\{(?<body>[\s\S]*?)\}'
)

if (-not $interfaceMatch.Success) {
    throw "OrchestratorResponse interface bulunamadi."
}

$interfaceBody = $interfaceMatch.Groups["body"].Value

if ($interfaceBody -notmatch 'mode\s*:\s*"RESEARCH_ONLY"') {

    if ($interfaceBody -match 'status\s*:\s*OrchestratorStatus\s*;') {

        $newInterfaceBody = [regex]::Replace(
            $interfaceBody,
            '(status\s*:\s*OrchestratorStatus\s*;)',
            '$1' + "`r`n  mode: `"RESEARCH_ONLY`";",
            1
        )

        $newInterface =
            $interfaceMatch.Value.Replace(
                $interfaceBody,
                $newInterfaceBody
            )

        $text =
            $text.Remove(
                $interfaceMatch.Index,
                $interfaceMatch.Length
            ).Insert(
                $interfaceMatch.Index,
                $newInterface
            )

        Write-Host "OrchestratorResponse mode eklendi."
    }
    else {
        throw "OrchestratorResponse status alani bulunamadi."
    }
}
else {
    Write-Host "OrchestratorResponse mode zaten mevcut."
}

# ============================================================
# 2) buildFinalResponse return objesi
# ============================================================

$functionMatch = [regex]::Match(
    $text,
    'function\s+buildFinalResponse\s*\([\s\S]*?(?=\n\})'
)

if (-not $functionMatch.Success) {
    throw "buildFinalResponse bulunamadi."
}

$functionText = $functionMatch.Value

if ($functionText -notmatch 'return\s*\{[\s\S]*?mode\s*:\s*"RESEARCH_ONLY"') {

    $returnMatch = [regex]::Match(
        $functionText,
        'return\s*\{\s*success\s*:[\s\S]*?\n\s*runId,\s*'
    )

    if (-not $returnMatch.Success) {
        throw "buildFinalResponse return blogu bulunamadi."
    }

    $replacement =
        $returnMatch.Value +
        "`r`n    mode: `"RESEARCH_ONLY`","

    $newFunctionText =
        $functionText.Remove(
            $returnMatch.Index,
            $returnMatch.Length
        ).Insert(
            $returnMatch.Index,
            $replacement
        )

    $text =
        $text.Remove(
            $functionMatch.Index,
            $functionMatch.Length
        ).Insert(
            $functionMatch.Index,
            $newFunctionText
        )

    Write-Host "buildFinalResponse mode eklendi."
}
else {
    Write-Host "buildFinalResponse mode zaten mevcut."
}

Set-Content $file $text -Encoding UTF8

# ============================================================
# 3) Verification
# ============================================================

$verify = Get-Content $file -Raw

$interfacePass = [regex]::IsMatch(
    $verify,
    'interface\s+OrchestratorResponse\s*\{[\s\S]*?mode\s*:\s*"RESEARCH_ONLY"'
)

$functionPass = [regex]::IsMatch(
    $verify,
    'function\s+buildFinalResponse[\s\S]*?return\s*\{[\s\S]*?mode\s*:\s*"RESEARCH_ONLY"'
)

Write-Host ""
Write-Host "===== RESEARCH LOOP MODE CONTRACT CHECK ====="

Write-Host (
    "OrchestratorResponse mode       " +
    $(if ($interfacePass) { "PASS" } else { "FAIL" })
)

Write-Host (
    "buildFinalResponse mode         " +
    $(if ($functionPass) { "PASS" } else { "FAIL" })
)

Write-Host "BACKUP: $backup"

if (-not ($interfacePass -and $functionPass)) {
    throw "RESEARCH LOOP MODE CONTRACT FAIL"
}

Write-Host ""
Write-Host "RESEARCH LOOP MODE CONTRACT PASS"
