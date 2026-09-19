

$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$generatorPath = Join-Path $root "frontend\components\agents\experiment-generator-agent.ts"

Write-Host "MarketHQ - VectorBT Params Propagation FINAL REPAIR"
Write-Host "============================================================"

if (-not (Test-Path $generatorPath)) {
    throw "Generator dosyasi bulunamadi: $generatorPath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root ("vectorbt-final-repair-backup_" + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item $generatorPath (Join-Path $backupDir "experiment-generator-agent.ts") -Force

# Read the file as lines. This avoids fragile multiline regex editing.
$lines = @(Get-Content $generatorPath)

function Test-DeclarationStart {
    param(
        [string]$Line,
        [string]$Name
    )
    return ($Line.Trim() -match ("^const " + [regex]::Escape($Name) + "\s*="))
}

function Remove-DeclarationBlocks {
    param(
        [string[]]$InputLines,
        [string[]]$Names
    )

    $result = New-Object System.Collections.Generic.List[string]
    $skip = $false

    foreach ($line in $InputLines) {
        $trimmed = $line.Trim()

        if (-not $skip) {
            $matched = $false

            foreach ($name in $Names) {
                if ($trimmed -match ("^const " + [regex]::Escape($name) + "\s*=")) {
                    $matched = $true
                    break
                }
            }

            if ($matched) {
                # A declaration may be one-line or multiline.
                if ($trimmed -notmatch ";\s*$") {
                    $skip = $true
                }
                continue
            }

            $result.Add($line)
            continue
        }

        # We are inside a multiline declaration.
        if ($trimmed -match ";\s*$") {
            $skip = $false
        }
    }

    if ($skip) {
        throw "Dosya sonuna kadar uzanan yarim deklarasyon bulundu."
    }

    return ,$result.ToArray()
}

Write-Host ""
Write-Host "1) Eski parameter-propagation deklarasyonlari temizleniyor..."

$namesToRemove = @(
    "generatorInput",
    "importedStrategyDefinition",
    "importedParameters",
    "generatedParameters",
    "parameters"
)

$clean = Remove-DeclarationBlocks -InputLines $lines -Names $namesToRemove

# Reinsert one canonical block immediately before the experiment creation.
$insertIndex = -1

for ($i = 0; $i -lt $clean.Count; $i++) {
    if ($clean[$i].Trim() -match "^const experiment\s*=") {
        $insertIndex = $i
        break
    }
}

if ($insertIndex -lt 0) {
    throw "Generator icinde 'const experiment =' anchor'i bulunamadi."
}

$canonical = @(
"  const generatorInput =",
"    isRecord(context.input)",
"      ? context.input",
"      : {};",
"",
"  const importedStrategyDefinition =",
"    isRecord(generatorInput.strategyDefinition)",
"      ? generatorInput.strategyDefinition",
"      : isRecord(generatorInput.importedStrategy)",
"        ? generatorInput.importedStrategy",
"        : isRecord(generatorInput.strategyImport)",
"          ? generatorInput.strategyImport",
"          : {};",
"",
"  const importedParameters =",
"    isRecord(importedStrategyDefinition.parameters)",
"      ? importedStrategyDefinition.parameters",
"      : {};",
"",
"  const generatedParameters =",
"    normalizeParameters(strategyOutput);",
"",
"  const parameters =",
"    Object.keys(generatedParameters).length > 0",
"      ? generatedParameters",
"      : importedParameters;",
""
)

$newLines = New-Object System.Collections.Generic.List[string]

for ($i = 0; $i -lt $clean.Count; $i++) {
    if ($i -eq $insertIndex) {
        foreach ($line in $canonical) {
            $newLines.Add($line)
        }
    }
    $newLines.Add($clean[$i])
}

$content = [string]::Join([Environment]::NewLine, $newLines.ToArray()) + [Environment]::NewLine
Set-Content -Path $generatorPath -Value $content -Encoding UTF8

Write-Host "Canonical block tek sefer yerlestirildi."

# Contract verification.
$verify = Get-Content $generatorPath

function Count-Declaration {
    param(
        [string[]]$InputLines,
        [string]$Name
    )

    $count = 0
    foreach ($line in $InputLines) {
        if ($line.Trim() -match ("^const " + [regex]::Escape($Name) + "\s*=")) {
            $count++
        }
    }
    return $count
}

$generatorCount = Count-Declaration $verify "generatorInput"
$importedStrategyCount = Count-Declaration $verify "importedStrategyDefinition"
$importedParametersCount = Count-Declaration $verify "importedParameters"
$generatedParametersCount = Count-Declaration $verify "generatedParameters"
$parametersCount = Count-Declaration $verify "parameters"

Write-Host ""
Write-Host "---------------- FINAL CONTRACT ----------------"
Write-Host ("generatorInput                 : " + $generatorCount)
Write-Host ("importedStrategyDefinition     : " + $importedStrategyCount)
Write-Host ("importedParameters             : " + $importedParametersCount)
Write-Host ("generatedParameters            : " + $generatedParametersCount)
Write-Host ("parameters                     : " + $parametersCount)

$full = [string]::Join([Environment]::NewLine, $verify)

$checks = @(
    ($generatorCount -eq 1),
    ($importedStrategyCount -eq 1),
    ($importedParametersCount -eq 1),
    ($generatedParametersCount -eq 1),
    ($parametersCount -eq 1),
    ($full -match "generatorInput\.strategyDefinition"),
    ($full -match "normalizeParameters\(strategyOutput\)"),
    ($full -match "Object\.keys\(generatedParameters\)\.length -gt 0"),
    ($full -match "\? generatedParameters"),
    ($full -match ": importedParameters")
)

if ($checks -contains $false) {
    throw "FINAL parameter propagation contract FAIL."
}

Write-Host ""
Write-Host "FINAL parameter propagation contract PASS."
Write-Host ("Backup : " + $backupDir)
Write-Host ""
Write-Host "SIMDI BUILD:"
Write-Host "  cd C:\Users\Ersin\PycharmProjects\MarketHQ\frontend"
Write-Host "  npm run build"
Write-Host ""
Write-Host "BUILD PASS SONRASI E2E:"
Write-Host "  cd C:\Users\Ersin\PycharmProjects\MarketHQ"
Write-Host "  .\MARKETHQ_VectorBT_E2E_Test_V1.ps1"
Write-Host ""
Write-Host "============================================================"
Write-Host "FINAL REPAIR HAZIR"
Write-Host "============================================================"
