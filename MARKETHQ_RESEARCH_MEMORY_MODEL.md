# MARKETHQ RESEARCH MEMORY MODEL

**Date:** 2026-09-16
**Phase:** H

---

## Memory Types

| Type | Description |
|------|-------------|
| OBSERVATION | Raw observation from data |
| PATTERN | Repeated pattern across cases |
| FAILURE | Setup failure pattern |
| SUCCESS_PATTERN | Setup success pattern |
| CLAIM | Research claim |
| COUNTEREXAMPLE | Case contradicting a claim |
| DATA_QUALITY | Data quality issue |
| REGIME_PATTERN | Regime-specific pattern |
| STRATEGY_PATTERN | Strategy-specific pattern |

## Memory Entry

Every memory entry carries:
- status (UNTESTED/TESTED/SUPPORTED/UNSTABLE/REJECTED)
- evidence (list of evidence sources)
- sample_size
- validation_windows
- reliability score
- regime, asset, timeframe context

## Memory ≠ Truth

Memory is NOT a truth database.
Every entry is an observation that may be wrong.
Status reflects evidence quality, not certainty.

## Retrieval

Similarity engine finds similar historical setups.
Failure memory finds similar failure patterns.
Claim engine finds supporting/contradicting evidence.

All retrieval is evidence-based, not truth-based.