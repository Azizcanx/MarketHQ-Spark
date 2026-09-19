$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$runner = Join-Path $root "agents\research_execution_adapter_v1.py"
$vbt = Join-Path $root "agents\vectorbt_engine_v1.py"
$optimizer = Join-Path $root "agents\systematic_trading_optimizer_adapter_v1.py"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ - Systematic Optimizer -> VectorBT Bridge ROBUST" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

foreach ($p in @($runner,$vbt,$optimizer)) {
    if (-not (Test-Path $p)) {
        throw "Dosya bulunamadi: $p"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root ("systematic-vbt-robust-backup_" + $stamp)
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item $runner (Join-Path $backup "research_execution_adapter_v1.py") -Force
Copy-Item $vbt (Join-Path $backup "vectorbt_engine_v1.py") -Force

$r = Get-Content $runner -Raw
$v = Get-Content $vbt -Raw

# ---------------------------------------------------------------------------
# RUNNER: already-installed bridge pieces are preserved. Only add missing
# explicit candidate forwarding.
# ---------------------------------------------------------------------------
if (-not $r.Contains("parameter_candidates=parameter_candidates")) {
    $pattern = '(?s)(return\s+run_vectorbt_backtest\(\s*.*?parameter_sweep\s*=\s*parameter_sweep,\s*)(\))'
    $newR = [regex]::Replace($r, $pattern, {
        param($m)
        $m.Groups[1].Value +
        "            parameter_candidates=parameter_candidates," + "`r`n" +
        "        " + $m.Groups[2].Value
    }, 1)

    if ($newR -eq $r) {
        throw "Runner VectorBT dispatcher call bulunamadi."
    }
    $r = $newR
    Write-Host "Runner -> VectorBT explicit candidate forwarding eklendi." -ForegroundColor Green
}
else {
    Write-Host "Runner -> VectorBT explicit candidate forwarding zaten mevcut." -ForegroundColor Yellow
}

if (-not $r.Contains("parameter_candidates=optimizer_candidates")) {
    $pattern = '(?s)(run_selected_backtest\(\s*data\s*=\s*independent_data,.*?parameter_sweep\s*=\s*parameter_sweep,\s*)(\))'
    $newR = [regex]::Replace($r, $pattern, {
        param($m)
        $m.Groups[1].Value +
        "        parameter_candidates=optimizer_candidates," + "`r`n" +
        "    " + $m.Groups[2].Value
    }, 1)

    if ($newR -eq $r) {
        throw "Runner main optimizer candidate call bulunamadi."
    }
    $r = $newR
    Write-Host "Runner main optimizer candidate aktarimi eklendi." -ForegroundColor Green
}
else {
    Write-Host "Runner main optimizer candidate aktarimi zaten mevcut." -ForegroundColor Yellow
}

Set-Content -Path $runner -Value $r -Encoding UTF8

# ---------------------------------------------------------------------------
# VECTORBT ENGINE
#
# The current MarketHQ VectorBT file uses normalize_sweep(), not
# _candidate_parameters(). The earlier bridge failed because it assumed the
# wrong function name. This patch supports BOTH shapes.
# ---------------------------------------------------------------------------

$v = Get-Content $vbt -Raw

# ---- Case A: _candidate_parameters architecture ---------------------------
if ($v.Contains("def _candidate_parameters(")) {

    if (-not $v.Contains("parameter_candidates: list[dict[str, Any]] | None = None")) {
        $pattern = '(?s)(def _candidate_parameters\(\s+.*?)(\)\s*->\s*list\[dict\[str,\s*Any\]\]:)'
        $newV = [regex]::Replace($v, $pattern, {
            param($m)
            $head = $m.Groups[1].Value
            $head + "    parameter_candidates: list[dict[str, Any]] | None = None," + "`r`n" + $m.Groups[2].Value
        }, 1)

        if ($newV -eq $v) {
            throw "_candidate_parameters mevcut ama signature patch edilemedi."
        }
        $v = $newV
        Write-Host "VectorBT _candidate_parameters explicit candidate argumani eklendi." -ForegroundColor Green
    }
    else {
        Write-Host "VectorBT _candidate_parameters explicit candidate argumani zaten mevcut." -ForegroundColor Yellow
    }

    if (-not $v.Contains("if parameter_candidates:")) {
        $pattern = '(?s)(def _candidate_parameters\(.*?\n)(\s*if not sweep:)'
        $insert = @'
$1    if parameter_candidates:
        normalized_candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for raw_candidate in parameter_candidates:
            if not isinstance(raw_candidate, dict):
                continue

            candidate = dict(base)
            candidate.update(raw_candidate)

            marker = json.dumps(
                candidate,
                sort_keys=True,
                default=str,
            )

            if marker not in seen:
                seen.add(marker)
                normalized_candidates.append(candidate)

        if normalized_candidates:
            return normalized_candidates

$2
'@
        $newV = [regex]::Replace($v, $pattern, $insert, 1)
        if ($newV -eq $v) {
            throw "VectorBT _candidate_parameters explicit candidate body eklenemedi."
        }
        $v = $newV
        Write-Host "VectorBT explicit candidate body eklendi." -ForegroundColor Green
    }
    else {
        Write-Host "VectorBT explicit candidate body zaten mevcut." -ForegroundColor Yellow
    }

    $callPattern = '(?s)candidates\s*=\s*_candidate_parameters\(\s*base,\s*parameter_sweep,\s*\)'
    if ([regex]::IsMatch($v, $callPattern)) {
        $v = [regex]::Replace($v, $callPattern, @"
candidates = _candidate_parameters(
        base,
        parameter_sweep,
        parameter_candidates,
    )
"@, 1)
        Write-Host "VectorBT _candidate_parameters forwarding tamamlandi." -ForegroundColor Green
    }

}
# ---- Case B: normalize_sweep architecture ---------------------------------
elseif ($v.Contains("def normalize_sweep(")) {

    if (-not $v.Contains("parameter_candidates")) {
        $pattern = '(?s)(def normalize_sweep\(\s*base:\s*dict\[str,\s*Any\],\s*sweep:\s*dict\[str,\s*Any\]\s*\|\s*None,\s*)(\)\s*->\s*list\[dict\[str,\s*Any\]\]:)'
        $newV = [regex]::Replace($v, $pattern, {
            param($m)
            $m.Groups[1].Value +
            "    parameter_candidates: list[dict[str, Any]] | None = None," + "`r`n" +
            $m.Groups[2].Value
        }, 1)

        if ($newV -eq $v) {
            throw "normalize_sweep signature patch edilemedi."
        }
        $v = $newV
        Write-Host "VectorBT normalize_sweep explicit candidate argumani eklendi." -ForegroundColor Green
    }
    else {
        Write-Host "VectorBT normalize_sweep explicit candidate desteği zaten var." -ForegroundColor Yellow
    }

    if (-not $v.Contains("if parameter_candidates:")) {
        $pattern = '(?s)(def normalize_sweep\(.*?\n)(\s*if not sweep:)'
        $insert = @'
$1    if parameter_candidates:
        normalized_candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for raw_candidate in parameter_candidates:
            if not isinstance(raw_candidate, dict):
                continue

            candidate = dict(base)
            candidate.update(raw_candidate)

            marker = json.dumps(
                candidate,
                sort_keys=True,
                default=str,
            )

            if marker not in seen:
                seen.add(marker)
                normalized_candidates.append(candidate)

        if normalized_candidates:
            return normalized_candidates

$2
'@
        $newV = [regex]::Replace($v, $pattern, $insert, 1)
        if ($newV -eq $v) {
            throw "normalize_sweep explicit candidate body eklenemedi."
        }
        $v = $newV
        Write-Host "normalize_sweep explicit candidate body eklendi." -ForegroundColor Green
    }
    else {
        Write-Host "normalize_sweep explicit candidate body zaten mevcut." -ForegroundColor Yellow
    }

    # The engine has historically used both run_vectorbt_backtest() and run().
    # Patch whichever call site exists.
    $callPattern = '(?s)candidates\s*=\s*normalize_sweep\(\s*base(?:_params)?\s*,\s*sweep\s*\)'
    if ([regex]::IsMatch($v, $callPattern)) {
        $v = [regex]::Replace($v, $callPattern, {
            param($m)
            $text = $m.Value
            $text -replace '\)\s*$', ",`r`n        parameter_candidates,`r`n    )"
        }, 1)
        Write-Host "VectorBT normalize_sweep forwarding tamamlandi." -ForegroundColor Green
    }
}
else {
    throw "VectorBT candidate generator bulunamadi: neither _candidate_parameters nor normalize_sweep exists."
}

# ---- Public function / payload plumbing -----------------------------------
# Add explicit parameter_candidates to run_vectorbt_backtest() when that
# function exists. Formatting-independent.
if ($v.Contains("def run_vectorbt_backtest(") -and
    -not $v.Contains("parameter_candidates: list[dict[str, Any]] | None = None")) {

    $pattern = '(?s)(def run_vectorbt_backtest\(.*?parameter_sweep:\s*dict\[str,\s*Any\]\s*\|\s*None\s*=\s*None,\s*)(\))'
    $newV = [regex]::Replace($v, $pattern, {
        param($m)
        $m.Groups[1].Value +
        "    parameter_candidates: list[dict[str, Any]] | None = None," + "`r`n" +
        $m.Groups[2].Value
    }, 1)

    if ($newV -eq $v) {
        throw "run_vectorbt_backtest public signature bulunamadi."
    }

    $v = $newV
    Write-Host "run_vectorbt_backtest explicit candidate argumani eklendi." -ForegroundColor Green
}

# If run_vectorbt_backtest was previously patched, make sure the call uses it.
if ($v.Contains("def run_vectorbt_backtest(") -and
    -not $v.Contains("parameter_candidates,") ) {

    $pattern = '(?s)candidates\s*=\s*(?:_candidate_parameters|normalize_sweep)\(\s*base(?:_params)?\s*,\s*parameter_sweep\s*\)'
    if ([regex]::IsMatch($v, $pattern)) {
        $v = [regex]::Replace($v, $pattern, {
            param($m)
            $m.Value -replace '\)\s*$', ",`r`n        parameter_candidates,`r`n    )"
        }, 1)
    }
}

# Result metadata.
$metaOld = @"
        "parameterSweep": {
            "requested": bool(parameter_sweep),
            "candidateCount": len(candidates),
            "completedCount": len(results),
            "failedCount": len(errors),
        },
"@

$metaNew = @"
        "parameterSweep": {
            "requested": bool(parameter_sweep) or bool(parameter_candidates),
            "source": (
                "SYSTEMATIC_TRADING_FRAMEWORK"
                if parameter_candidates
                else "VECTORBT_NATIVE"
            ),
            "candidateCount": len(candidates),
            "completedCount": len(results),
            "failedCount": len(errors),
        },
"@

if ($v.Contains($metaOld)) {
    $v = $v.Replace($metaOld, $metaNew)
    Write-Host "VectorBT parameterSweep metadata guncellendi." -ForegroundColor Green
}
else {
    Write-Host "VectorBT metadata blogu format olarak farkli; metadata patch atlandi." -ForegroundColor Yellow
}

Set-Content -Path $vbt -Value $v -Encoding UTF8

# ---------------------------------------------------------------------------
# VERIFY WITH PYTHON
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Python syntax kontrolu..." -ForegroundColor Yellow

Push-Location $root
try {
    python -m py_compile ".\agents\systematic_trading_optimizer_adapter_v1.py"
    if ($LASTEXITCODE -ne 0) { throw "Systematic optimizer adapter py_compile FAIL." }

    python -m py_compile ".\agents\research_execution_adapter_v1.py"
    if ($LASTEXITCODE -ne 0) { throw "Research execution adapter py_compile FAIL." }

    python -m py_compile ".\agents\vectorbt_engine_v1.py"
    if ($LASTEXITCODE -ne 0) { throw "VectorBT engine py_compile FAIL." }

    @'
from agents.systematic_trading_optimizer_adapter_v1 import generate_parameter_candidates

space = {
    "sma_fast": [10, 20, 30],
    "sma_slow": [50, 100],
}

candidates = generate_parameter_candidates(space, method="grid")

print("SYSTEMATIC_GRID_CANDIDATES", len(candidates))
print("FIRST", candidates[0] if candidates else None)
print("LAST", candidates[-1] if candidates else None)

assert len(candidates) == 6
assert all(isinstance(x, dict) for x in candidates)
print("BRIDGE_UPSTREAM_TEST", "PASS")
'@ | Set-Content ".\temp_systematic_vbt_bridge_test.py" -Encoding UTF8

    python ".\temp_systematic_vbt_bridge_test.py"
    if ($LASTEXITCODE -ne 0) { throw "Upstream optimizer unit test FAIL." }
}
finally {
    Remove-Item ".\temp_systematic_vbt_bridge_test.py" -Force -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "SYSTEMATIC OPTIMIZER -> VECTORBT BRIDGE ROBUST HAZIR" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backup : $backup"
Write-Host ""
Write-Host "Kontrol edilen mimari:"
Write-Host "  Systematic Trading Framework -> candidate list"
Write-Host "  candidate list -> MarketHQ VectorBT"
Write-Host "  MarketHQ backtest/validation sahibi"
Write-Host "  research-only korunuyor"
Write-Host ""
Write-Host "SONRA:"
Write-Host "  cd frontend"
Write-Host "  npm run build"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

