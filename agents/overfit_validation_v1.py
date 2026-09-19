"""MarketHQ research-only overfit diagnostics.

Consumes trusted VectorBT candidate results. No second backtest engine,
broker connectivity, live execution, or database writes.
"""
from __future__ import annotations

import itertools
import math
from statistics import NormalDist
from typing import Any

import numpy as np

VALIDATION_VERSION = "1.3.0"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _distance(a: dict[str, Any], b: dict[str, Any]) -> int:
    keys = ("sma_fast", "sma_slow", "rsi_period", "rsi_entry")
    return sum(1 for key in keys if key in a and key in b and a[key] != b[key])


def parameter_plateau(results, selected, *, neighbor_distance=1, retention_threshold=0.75):
    if not results or not isinstance(selected, dict):
        return {"status": "INCONCLUSIVE", "reason": "PARAMETER_PLATEAU_INPUT_INSUFFICIENT", "neighborCount": 0, "supportRatio": None}
    selected_return = _finite((selected.get("metrics") or {}).get("net_return_percent"))
    selected_params = selected.get("parameters")
    if selected_return is None or not isinstance(selected_params, dict):
        return {"status": "INCONCLUSIVE", "reason": "SELECTED_RETURN_UNAVAILABLE", "neighborCount": 0, "supportRatio": None}

    neighbors = []
    for result in results:
        if result is selected:
            continue
        params = result.get("parameters")
        if isinstance(params, dict) and _distance(params, selected_params) <= neighbor_distance:
            neighbors.append(result)

    if not neighbors:
        return {"status": "INCONCLUSIVE", "reason": "NO_NEARBY_CANDIDATES", "neighborCount": 0, "supportRatio": None}

    threshold = selected_return * retention_threshold
    passing = usable = 0
    for result in neighbors:
        value = _finite((result.get("metrics") or {}).get("net_return_percent"))
        if value is None:
            continue
        usable += 1
        passing += int(value >= threshold)

    ratio = passing / usable if usable else None
    status = "INCONCLUSIVE" if ratio is None else ("PASS" if ratio >= 0.50 else "FAIL")
    return {"status": status, "reason": "NEIGHBOR_SUPPORT_EVALUATED", "neighborCount": len(neighbors), "usableNeighborCount": usable, "passingNeighborCount": passing, "supportRatio": ratio, "retentionThreshold": retention_threshold}


def _sharpe(returns: np.ndarray) -> float:
    if returns.size < 2:
        return 0.0
    deviation = returns.std(ddof=1)
    return 0.0 if deviation == 0 else float(returns.mean() / deviation)


def _psr(sr: float, n_obs: int, skew: float, kurtosis: float, benchmark: float) -> float:
    if n_obs < 2:
        return float("nan")
    denominator = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if denominator <= 0:
        return float("nan")
    z = (sr - benchmark) * math.sqrt(n_obs - 1.0) / math.sqrt(denominator)
    return float(NormalDist().cdf(z))


def sharpe_diagnostics(returns: Any, trial_sharpes: list[float] | None = None) -> dict[str, Any]:
    """Compute PSR/DSR only from genuine per-period portfolio returns."""
    if returns is None:
        return {"status": "INCONCLUSIVE", "reason": "RETURN_SERIES_REQUIRED", "observationUnit": None}
    values = np.asarray(returns, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return {"status": "INCONCLUSIVE", "reason": "RETURN_SERIES_TOO_SHORT", "observationUnit": "PERIOD_RETURN"}

    sr = _sharpe(values)
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    if std == 0:
        skew, kurtosis = 0.0, 3.0
    else:
        centered = values - mean
        m2 = float(np.mean(centered ** 2))
        m3 = float(np.mean(centered ** 3))
        m4 = float(np.mean(centered ** 4))
        skew = m3 / (m2 ** 1.5) if m2 > 0 else 0.0
        kurtosis = m4 / (m2 ** 2) if m2 > 0 else 3.0

    psr = _psr(sr, values.size, skew, kurtosis, 0.0)
    trials = np.asarray(trial_sharpes or [sr], dtype=float)
    trials = trials[np.isfinite(trials)]
    if trials.size == 0:
        trials = np.asarray([sr], dtype=float)

    variance = float(np.var(trials, ddof=1)) if trials.size > 1 else 0.0
    if trials.size <= 1 or variance == 0:
        expected_max = 0.0
    else:
        euler = 0.5772156649015329
        n = float(trials.size)
        normal = NormalDist()
        z1 = normal.inv_cdf(1.0 - 1.0 / n)
        z2 = normal.inv_cdf(1.0 - 1.0 / (n * math.e))
        expected_max = math.sqrt(variance) * ((1.0 - euler) * z1 + euler * z2)

    dsr = _psr(sr, values.size, skew, kurtosis, expected_max)
    return {"status": "PASS" if math.isfinite(dsr) else "INCONCLUSIVE", "reason": "RETURN_SERIES_EVALUATED", "observationUnit": "PERIOD_RETURN", "observations": int(values.size), "sharpe": sr, "skew": skew, "kurtosis": kurtosis, "psrVsZero": psr, "trialCount": int(trials.size), "trialSharpeVariance": variance, "expectedMaxSharpe": expected_max, "deflatedSharpe": dsr}


def _stationary_bootstrap(values: np.ndarray, rng: np.random.Generator, block_probability: float) -> np.ndarray:
    """Generate a stationary-bootstrap resample while preserving local dependence."""
    n = values.size
    output = np.empty(n, dtype=float)
    index = int(rng.integers(0, n))
    for i in range(n):
        if i > 0 and rng.random() < block_probability:
            index = int(rng.integers(0, n))
        elif i > 0:
            index = (index + 1) % n
        output[i] = values[index]
    return output


def permutation_test(returns: Any, *, simulations: int = 1000, seed: int = 42, block_probability: float = 0.1) -> dict[str, Any]:
    """Research-only stationary-block bootstrap null sanity test."""
    if returns is None:
        return {"status": "INCONCLUSIVE", "reason": "RETURN_SERIES_REQUIRED", "simulations": 0}
    values = np.asarray(returns, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size < 20:
        return {"status": "INCONCLUSIVE", "reason": "RETURN_SERIES_TOO_SHORT_FOR_BLOCK_BOOTSTRAP", "simulations": 0}

    observed = _sharpe(values)
    rng = np.random.default_rng(seed)
    sims = max(100, int(simulations))
    null_sharpes = [_sharpe(_stationary_bootstrap(values, rng, float(block_probability))) for _ in range(sims)]
    exceed = sum(int(value >= observed) for value in null_sharpes)
    p_value = (exceed + 1) / (sims + 1)
    return {"status": "PASS" if p_value < 0.05 else "FAIL", "reason": "STATIONARY_BLOCK_BOOTSTRAP_COMPLETED", "observationUnit": "PERIOD_RETURN", "observations": int(values.size), "simulations": sims, "observedSharpe": observed, "pValue": p_value, "seed": seed, "blockProbability": float(block_probability)}


def pbo_diagnostics(candidate_fold_sharpes: Any) -> dict[str, Any]:
    """Compute true CSCV-style PBO from a candidate-by-fold matrix.

    Each combination of half the folds is treated as in-sample and its
    complement as out-of-sample. The in-sample winner is ranked among all
    candidates on the complementary OOS folds. PBO is the fraction of valid
    splits whose OOS rank is below the median (logit <= 0).
    """
    if candidate_fold_sharpes is None:
        return {"status": "INCONCLUSIVE", "reason": "CANDIDATE_FOLD_MATRIX_REQUIRED", "foldCount": 0, "candidateCount": 0}
    matrix = np.asarray(candidate_fold_sharpes, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 4 or matrix.shape[1] < 4:
        return {"status": "INCONCLUSIVE", "reason": "CANDIDATE_FOLD_MATRIX_TOO_SMALL", "foldCount": int(matrix.shape[1]) if matrix.ndim == 2 else 0, "candidateCount": int(matrix.shape[0]) if matrix.ndim == 2 else 0}

    fold_count = int(matrix.shape[1])
    split_size = fold_count // 2
    combinations = list(itertools.combinations(range(fold_count), split_size))
    logits: list[float] = []
    valid = 0

    for is_indices in combinations:
        is_mask = np.zeros(fold_count, dtype=bool)
        is_mask[list(is_indices)] = True
        oos_mask = ~is_mask

        is_scores = np.nanmean(matrix[:, is_mask], axis=1)
        if not np.isfinite(is_scores).any():
            continue
        winner = int(np.nanargmax(is_scores))

        oos_scores = np.nanmean(matrix[:, oos_mask], axis=1)
        winner_oos = float(oos_scores[winner])
        finite_oos = oos_scores[np.isfinite(oos_scores)]
        if not math.isfinite(winner_oos) or finite_oos.size < 2:
            continue

        # Mid-rank percentile with deterministic tie handling.
        less = float(np.sum(finite_oos < winner_oos))
        equal = float(np.sum(finite_oos == winner_oos))
        rank = (less + 0.5 * equal) / float(finite_oos.size)
        rank = min(max(rank, 1e-6), 1.0 - 1e-6)
        logits.append(math.log(rank / (1.0 - rank)))
        valid += 1

    if valid == 0:
        return {"status": "INCONCLUSIVE", "reason": "NO_VALID_CSCV_SPLITS", "foldCount": fold_count, "candidateCount": matrix.shape[0], "splitCount": len(combinations)}

    logits_array = np.asarray(logits, dtype=float)
    pbo = float(np.mean(logits_array <= 0.0))
    return {
        "status": "PASS" if pbo < 0.50 else "FAIL",
        "reason": "CSCV_PBO_COMPLETED",
        "method": "COMBINATORIAL_SYMMETRIC_CROSS_VALIDATION",
        "pbo": pbo,
        "badSplitCount": int(np.sum(logits_array <= 0.0)),
        "validSplitCount": valid,
        "splitCount": len(combinations),
        "foldCount": fold_count,
        "candidateCount": int(matrix.shape[0]),
        "medianLogit": float(np.median(logits_array)),
    }


def evaluate_overfit_diagnostics(*, results, selected, return_series=None, candidate_fold_sharpes=None):
    plateau = parameter_plateau(results, selected)
    trial_sharpes = []
    for result in results:
        value = _finite((result.get("metrics") or {}).get("sharpe_ratio"))
        if value is not None:
            trial_sharpes.append(value)
    sharpe = sharpe_diagnostics(return_series, trial_sharpes)
    permutation = permutation_test(return_series)
    pbo = pbo_diagnostics(candidate_fold_sharpes)
    statuses = [plateau["status"], sharpe["status"], permutation["status"], pbo["status"]]
    overall = "FAIL" if "FAIL" in statuses else ("PASS" if all(status == "PASS" for status in statuses) else "INCONCLUSIVE")
    return {"version": VALIDATION_VERSION, "status": overall, "parameterPlateau": plateau, "sharpeDiagnostics": sharpe, "permutationTest": permutation, "pbo": pbo, "researchOnly": True, "executionEnabled": False, "brokerExecutionEnabled": False, "databaseWriteEnabled": False}
