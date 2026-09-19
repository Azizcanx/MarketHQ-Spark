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
