$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$orchestrator = Join-Path $root "frontend\app\api\agents\orchestrator\route.ts"

if (-not (Test-Path $orchestrator)) {
    throw "orchestrator route bulunamadi: $orchestrator"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("vectorbt-request-context-backup_" + $stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item $orchestrator (Join-Path $backup "orchestrator-route.ts") -Force

$lines = @(Get-Content $orchestrator)

# Find the exact buildContext input declaration.
$inputLine = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -eq "const input = isRecord(body.input)") {
        $inputLine = $i
        break
    }
}

if ($inputLine -lt 0) {
    throw "buildContext input blogu baslangici bulunamadi."
}

# The current source is:
#   const input = isRecord(body.input)
#     ? body.input
#     : {};
#
# Find the first ": {};" after that declaration.
$inputEnd = -1
for ($i = $inputLine + 1; $i -lt [Math]::Min($lines.Count, $inputLine + 10); $i++) {
    if ($lines[$i].Trim() -eq ": {};") {
        $inputEnd = $i
        break
    }
}

if ($inputEnd -lt 0) {
    throw "buildContext input blogu sonu bulunamadi. Beklenen satir ': {};'."
}

# Prevent double patching.
$alreadyPatched = $false
for ($i = $inputLine; $i -lt [Math]::Min($lines.Count, $inputEnd + 12); $i++) {
    if ($lines[$i].Contains("body.researchEngine")) {
        $alreadyPatched = $true
        break
    }
}

if (-not $alreadyPatched) {
    $replacement = @(
        '  const input: JsonRecord = isRecord(body.input)',
        '    ? { ...body.input }',
        '    : {};',
        '',
        '  if (typeof body.researchEngine === "string") {',
        '    input.researchEngine = body.researchEngine;',
        '  }'
    )

    $newLines = New-Object System.Collections.Generic.List[string]

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($i -eq $inputLine) {
            foreach ($x in $replacement) {
                $newLines.Add($x)
            }
            $i = $inputEnd
        } else {
            $newLines.Add($lines[$i])
        }
    }

    $lines = @($newLines)
}

Set-Content -Path $orchestrator -Value $lines -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ VectorBT Request Context Fix V1.1 tamamlandi." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Orchestrator: $orchestrator"
Write-Host "Backup      : $backup"
Write-Host ""
Write-Host "Top-level request.researchEngine -> AgentContext.input.researchEngine"
Write-Host "baglantisi kuruldu."
Write-Host ""
Write-Host "Sonraki:"
Write-Host "  1) cd frontend"
Write-Host "  2) npm run build"
Write-Host "  3) VectorBT E2E testini tekrar calistir."
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
