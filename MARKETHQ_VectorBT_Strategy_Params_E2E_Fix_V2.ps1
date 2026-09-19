$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$generatorPath = Join-Path $root "frontend\components\agents\experiment-generator-agent.ts"
$e2ePath = Join-Path $root "MARKETHQ_VectorBT_E2E_Test_V1.ps1"

Write-Host "MarketHQ - VectorBT Params Propagation FIX V10"
Write-Host "============================================================"

if (-not (Test-Path $generatorPath)) {
    throw "Generator dosyasi bulunamadi: $generatorPath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root ("vectorbt-params-propagation-v6-backup_" + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $generatorPath (Join-Path $backupDir "experiment-generator-agent.ts") -Force
if (Test-Path $e2ePath) {
    Copy-Item $e2ePath (Join-Path $backupDir "MARKETHQ_VectorBT_E2E_Test_V1.ps1") -Force
}

$content = Get-Content $generatorPath -Raw

function Get-TokenCount([string]$text, [string]$token) {
    return ([regex]::Matches($text, [regex]::Escape($token))).Count
}

Write-Host ""
Write-Host "BEFORE duplicate declaration counts:"
Write-Host ("  generatorInput              : " + (Get-TokenCount $content "const generatorInput ="))
Write-Host ("  importedStrategyDefinition  : " + (Get-TokenCount $content "const importedStrategyDefinition ="))
Write-Host ("  importedParameters          : " + (Get-TokenCount $content "const importedParameters ="))
Write-Host ("  generatedParameters         : " + (Get-TokenCount $content "const generatedParameters ="))
Write-Host ""

# ------------------------------------------------------------------
# 1) Remove all previously injected parameter-propagation declaration
#    groups. We rebuild one canonical group below, so duplicate const
#    declarations cannot survive.
# ------------------------------------------------------------------
$blockPattern = '(?ms)^[ \t]*const generatorInput =.*?^[ \t]*const importedParameters =.*?^[ \t]*: \{\};\r?\n'
$blockMatches = [regex]::Matches($content, $blockPattern)

if ($blockMatches.Count -gt 0) {
    $content = [regex]::Replace($content, $blockPattern, "", 1)
    Write-Host "Eski generatorInput/importedStrategyDefinition/importedParameters blogu temizlendi."
} else {
    Write-Host "Birlesik eski parameter blogu bulunmadi; tekil deklarasyonlar ayrıca temizlenecek."
}

# Remove any remaining standalone declarations that may have been left
# by previous V4/V5 patch attempts.
$standalonePatterns = @(
    '(?ms)^[ \t]*const generatorInput =\r?\n[ \t]*isRecord\(context\.input\).*?^[ \t]*: \{\};\r?\n',
    '(?ms)^[ \t]*const importedStrategyDefinition =\r?\n[ \t]*isRecord\(generatorInput\.strategyDefinition\).*?^[ \t]*: \{\};\r?\n',
    '(?ms)^[ \t]*const importedParameters =\r?\n[ \t]*isRecord\(importedStrategyDefinition\.parameters\).*?^[ \t]*: \{\};\r?\n'
)

foreach ($pattern in $standalonePatterns) {
    $content = [regex]::Replace($content, $pattern, "")
}

# ------------------------------------------------------------------
# 2) Remove any prior generatedParameters declaration so we create
#    exactly one canonical declaration.
# ------------------------------------------------------------------
# Remove every previous generatedParameters declaration with a
# line-based scan. This is formatting-agnostic and handles one-line
# and multiline declarations safely.
$lines = [System.Collections.Generic.List[string]](Get-Content $generatorPath)
$cleanLines = [System.Collections.Generic.List[string]]::new()
$skipGenerated = $false

foreach ($line in $lines) {
    $trimmed = $line.Trim()

    if (-not $skipGenerated -and $trimmed -match '^const generatedParameters\s*=') {
        if ($trimmed -notmatch ';\s*$') {
            $skipGenerated = $true
        }
        continue
    }

    if ($skipGenerated) {
        if ($trimmed -match ';\s*$') {
            $skipGenerated = $false
        }
        continue
    }

    $cleanLines.Add($line)
}

$content = [string]::Join([Environment]::NewLine, $cleanLines) + [Environment]::NewLine

# ------------------------------------------------------------------
# 3) Find the current effective parameters declaration. Replace it with
#    a canonical block using generatedParameters -> importedParameters.
# ------------------------------------------------------------------
$paramPattern = '(?ms)^[ \t]*const parameters =\r?\n.*?(?=^[ \t]*const [A-Za-z0-9_]+\s*=|^[ \t]*return\s+\{|^[ \t]*const experiment\s*=)'
$paramMatch = [regex]::Match($content, $paramPattern)

if (-not $paramMatch.Success) {
    $oneLineParamPattern = '(?m)^[ \t]*const parameters = [^\r\n;]+;\r?\n'
    $paramMatch = [regex]::Match($content, $oneLineParamPattern)
}

if (-not $paramMatch.Success) {
    throw "Generator icinde effective 'const parameters =' blogu bulunamadi."
}

$remainingGenerated = ([regex]::Matches($content, '(?m)^\s*const generatedParameters\s*=')).Count
if ($remainingGenerated -ne 0) {
    throw ("Eski generatedParameters deklarasyonlari temizlenemedi. Kalan: " + $remainingGenerated)
}

$canonical = @'
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

  const generatedParameters =
    normalizeParameters(strategyOutput);

  const parameters =
    Object.keys(generatedParameters).length > 0
      ? generatedParameters
      : importedParameters;

'@

$content = $content.Remove($paramMatch.Index, $paramMatch.Length)
$content = $content.Insert($paramMatch.Index, $canonical)

# ------------------------------------------------------------------
# 4) If the effective block already exists elsewhere after the cleanup,
#    fail early rather than creating a compile-breaking duplicate.
# ------------------------------------------------------------------
$generatorInputCount = Get-TokenCount $content "const generatorInput ="
$importedStrategyCount = Get-TokenCount $content "const importedStrategyDefinition ="
$importedParamsCount = Get-TokenCount $content "const importedParameters ="
$generatedParamsCount = Get-TokenCount $content "const generatedParameters ="
$parametersCount = Get-TokenCount $content "const parameters ="

Write-Host "AFTER canonical declaration counts:"
Write-Host ("  generatorInput              : " + $generatorInputCount)
Write-Host ("  importedStrategyDefinition  : " + $importedStrategyCount)
Write-Host ("  importedParameters          : " + $importedParamsCount)
Write-Host ("  generatedParameters         : " + $generatedParamsCount)
Write-Host ("  parameters                  : " + $parametersCount)

if ($generatorInputCount -ne 1 -or
    $importedStrategyCount -ne 1 -or
    $importedParamsCount -ne 1 -or
    $generatedParamsCount -ne 1 -or
    $parametersCount -lt 1) {
    throw "Canonical parameter propagation declaration counts beklenenden farkli."
}

Set-Content -Path $generatorPath -Value $content -Encoding UTF8
Write-Host "Generator canonical parameter propagation V6 yazildi."

# ------------------------------------------------------------------
# 5) Static contract checks.
# ------------------------------------------------------------------
$check = Get-Content $generatorPath -Raw

$checks = [ordered]@{
    "generatedParameters" = $check -match "const generatedParameters =\s*normalizeParameters\(strategyOutput\)"
    "importedParameters" = $check -match "const importedParameters ="
    "strategyDefinition read" = $check -match "generatorInput\.strategyDefinition"
    "effective fallback" = $check -match "Object\.keys\(generatedParameters\)\.length > 0[\s\S]*?generatedParameters[\s\S]*?importedParameters"
    "single generatorInput" = ((Get-TokenCount $check "const generatorInput =") -eq 1)
    "single importedParameters" = ((Get-TokenCount $check "const importedParameters =") -eq 1)
}

Write-Host ""
Write-Host "---------------- CONTRACT KONTROLU ----------------"
foreach ($key in $checks.Keys) {
    $result = if ($checks[$key]) { "PASS" } else { "FAIL" }
    "{0,-32} {1}" -f $key, $result
}

if ($checks.Values -contains $false) {
    throw "V6 contract kontrolu FAIL."
}

# E2E must retain the 6-candidate sweep requested by the bridge.
if (Test-Path $e2ePath) {
    $e2e = Get-Content $e2ePath -Raw
    $hasSweep = $e2e -match "parameterSweep" -and
                $e2e -match "sma_fast" -and
                $e2e -match "sma_slow"
    if ($hasSweep) {
        Write-Host "E2E parameterSweep                 PASS"
    } else {
        Write-Host "E2E parameterSweep                 FAIL"
        throw "E2E parameterSweep evidence not found."
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "VECTORBT PARAM PROPAGATION FIX V10 HAZIR"
Write-Host "============================================================"
Write-Host ""
Write-Host ("Backup : " + $backupDir)
Write-Host ""
Write-Host "SIMDI:"
Write-Host "  cd C:\Users\Ersin\PycharmProjects\MarketHQ\frontend"
Write-Host "  npm run build"
Write-Host ""
Write-Host "BUILD PASS OLURSA:"
Write-Host "  cd C:\Users\Ersin\PycharmProjects\MarketHQ"
Write-Host "  .\MARKETHQ_VectorBT_E2E_Test_V1.ps1"
Write-Host ""
Write-Host "Beklenen:"
Write-Host "  VectorBT engine reported       PASS"
Write-Host "  status                         COMPLETED"
Write-Host "  engine                         VECTORBT"
Write-Host "  candidateCount                6"
Write-Host ""

