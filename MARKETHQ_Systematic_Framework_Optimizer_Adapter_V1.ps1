$ErrorActionPreference = "Stop"

$root = "C:\Users\Ersin\PycharmProjects\MarketHQ"
$toolsRoot = Join-Path $root "external_tools"
$upstreamRoot = Join-Path $toolsRoot "systematic-trading-framework"
$zipPath = Join-Path $toolsRoot "systematic-trading-framework-main.zip"
$adapterPath = Join-Path $root "agents\systematic_trading_optimizer_adapter_v1.py"

if (-not (Test-Path $root)) {
    throw "MarketHQ root bulunamadi: $root"
}

# IMPORTANT:
# This script intentionally does NOT require Git.
# It downloads the public upstream repository archive with PowerShell.

New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $root "agents") -Force | Out-Null

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "MarketHQ - Systematic Trading Framework Adapter V1 FIXED" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$repoZipUrl = "https://github.com/dikibagast/systematic-trading-framework/archive/refs/heads/main.zip"

# ---------------------------------------------------------------------------
# 1) Get upstream source without Git.
# ---------------------------------------------------------------------------
if (-not (Test-Path $upstreamRoot)) {
    Write-Host "Upstream framework indiriliyor (Git gerektirmez)..." -ForegroundColor Yellow

    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }

    Invoke-WebRequest `
        -Uri $repoZipUrl `
        -OutFile $zipPath `
        -UseBasicParsing

    $extractRoot = Join-Path $toolsRoot "_extract_systematic_trading"
    if (Test-Path $extractRoot) {
        Remove-Item $extractRoot -Recurse -Force
    }

    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

    $topLevel = Get-ChildItem $extractRoot -Directory | Select-Object -First 1

    if (-not $topLevel) {
        throw "Upstream ZIP icinden klasor bulunamadi."
    }

    Move-Item `
        -Path $topLevel.FullName `
        -Destination $upstreamRoot `
        -Force

    Remove-Item $extractRoot -Recurse -Force
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
}
else {
    Write-Host "Upstream framework zaten mevcut; indirme tekrar yapilmadi." -ForegroundColor Yellow
}

$optimizerPath = Join-Path $upstreamRoot "engine\optimizer.py"
$licensePath = Join-Path $upstreamRoot "LICENSE"
$requirementsPath = Join-Path $upstreamRoot "requirements.txt"

if (-not (Test-Path $optimizerPath)) {
    throw "Upstream optimizer.py bulunamadi: $optimizerPath"
}

if (-not (Test-Path $licensePath)) {
    throw "Upstream LICENSE bulunamadi: $licensePath"
}

Write-Host "Upstream optimizer bulundu." -ForegroundColor Green
Write-Host "  $optimizerPath" -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# 2) Thin adapter.
#
# We reuse the upstream implementation instead of recreating its algorithms.
# MarketHQ remains the owner of:
#   - experiment contract
#   - backtest execution
#   - research safety
#   - validation / decision
# ---------------------------------------------------------------------------
$adapter = @'
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[1]

UPSTREAM_ROOT = (
    PROJECT_ROOT
    / "external_tools"
    / "systematic-trading-framework"
)

UPSTREAM_OPTIMIZER = (
    UPSTREAM_ROOT
    / "engine"
    / "optimizer.py"
)


def _load_upstream_optimizer():
    """Load the upstream optimizer without copying its implementation."""
    if not UPSTREAM_OPTIMIZER.exists():
        raise FileNotFoundError(
            f"Upstream optimizer not found: {UPSTREAM_OPTIMIZER}"
        )

    upstream_root_str = str(UPSTREAM_ROOT)
    if upstream_root_str not in sys.path:
        sys.path.insert(0, upstream_root_str)

    spec = importlib.util.spec_from_file_location(
        "markethq_upstream_optimizer",
        UPSTREAM_OPTIMIZER,
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            "Could not load upstream optimizer module."
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_parameter_candidates(
    param_space: Dict[str, List[Any]],
    method: str = "grid",
    n_random: int = 100,
) -> List[Dict[str, Any]]:
    """Reuse upstream grid/random search candidate generation."""
    optimizer = _load_upstream_optimizer()

    if method == "grid":
        return optimizer._generate_grid_combinations(param_space)

    if method == "random":
        return optimizer._generate_random_combinations(
            param_space,
            n_random,
        )

    raise ValueError(
        f"Unsupported method: {method}. Use 'grid' or 'random'."
    )


def optimize_params(
    strategy_class: Any,
    param_space: Dict[str, List[Any]],
    train_data: pl.DataFrame,
    method: str = "grid",
    objective: str = "sharpe",
    n_random: int = 100,
    config: Dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Reuse the upstream multiprocessing optimizer."""
    optimizer = _load_upstream_optimizer()

    return optimizer.optimize_params(
        strategy_class=strategy_class,
        param_space=param_space,
        train_data=train_data,
        method=method,
        objective=objective,
        n_random=n_random,
        config=config,
    )


def select_parameter_plateau(
    results: pl.DataFrame,
    param_space: Dict[str, List[Any]],
    objective: str = "sharpe",
    min_threshold: float = 0.0,
    adaptive_threshold: bool = True,
    percentile: float = 50.0,
) -> Dict[str, Any]:
    """Reuse upstream Island Volume Selection / plateau detection."""
    optimizer = _load_upstream_optimizer()

    return optimizer.select_params_by_island_volume(
        results=results,
        param_space=param_space,
        objective=objective,
        min_threshold=min_threshold,
        adaptive_threshold=adaptive_threshold,
        percentile=percentile,
    )


def adapter_info() -> Dict[str, Any]:
    """Return MarketHQ adapter metadata."""
    return {
        "adapter": "MARKETHQ_SYSTEMATIC_OPTIMIZER_ADAPTER_V1",
        "upstream": "dikibagast/systematic-trading-framework",
        "upstream_optimizer": str(UPSTREAM_OPTIMIZER),
        "reused_capabilities": [
            "grid_parameter_generation",
            "random_parameter_generation",
            "multiprocessing_parameter_optimization",
            "island_volume_selection",
        ],
        "marketHQ_owns_backtest": True,
        "marketHQ_owns_validation": True,
        "researchOnly": True,
        "executionEnabled": False,
        "brokerExecutionEnabled": False,
        "databaseWriteEnabled": False,
    }
'@

Set-Content `
    -Path $adapterPath `
    -Value $adapter `
    -Encoding UTF8

# ---------------------------------------------------------------------------
# 3) Validate Python syntax.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Adapter syntax kontrolu..." -ForegroundColor Yellow

Push-Location $root
try {
    python -m py_compile ".\agents\systematic_trading_optimizer_adapter_v1.py"

    if ($LASTEXITCODE -ne 0) {
        throw "Adapter py_compile basarisiz."
    }
}
finally {
    Pop-Location
}

Write-Host "py_compile PASS." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4) Runtime test.
# ---------------------------------------------------------------------------
$testCode = @'
from agents.systematic_trading_optimizer_adapter_v1 import (
    adapter_info,
    generate_parameter_candidates,
)

space = {
    "sma_fast": [10, 20, 30],
    "sma_slow": [50, 100],
}

candidates = generate_parameter_candidates(
    space,
    method="grid",
)

print("ADAPTER_INFO")
print(adapter_info())
print("GRID_COUNT", len(candidates))
print("FIRST", candidates[0] if candidates else None)
print("LAST", candidates[-1] if candidates else None)

assert len(candidates) == 6, (
    f"Expected 6 grid candidates, got {len(candidates)}"
)
'@

$testScript = Join-Path $root "temp_systematic_optimizer_adapter_test.py"
Set-Content -Path $testScript -Value $testCode -Encoding UTF8

Write-Host ""
Write-Host "Hazir upstream optimizer runtime testi..." -ForegroundColor Yellow

Push-Location $root
try {
    python $testScript

    if ($LASTEXITCODE -ne 0) {
        throw "Upstream optimizer adapter runtime testi basarisiz."
    }
}
finally {
    Pop-Location
    Remove-Item $testScript -Force -ErrorAction SilentlyContinue
}

Write-Host "Runtime test PASS." -ForegroundColor Green

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Systematic Trading Framework Adapter V1 BASARIYLA HAZIR." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Upstream : $upstreamRoot"
Write-Host "Adapter  : $adapterPath"
Write-Host ""
Write-Host "Git gerekmiyor."
Write-Host "MarketHQ backtest motoru degistirilmedi."
Write-Host ""
Write-Host "Yeniden kullanilan hazir yetenekler:"
Write-Host "  - Grid parameter generation"
Write-Host "  - Random parameter generation"
Write-Host "  - Multiprocessing optimization"
Write-Host "  - Island Volume Selection"
Write-Host ""
Write-Host "Sonraki adim:"
Write-Host "  Adapter'i Experiment Runner + VectorBT sweep'e baglamak."
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan

