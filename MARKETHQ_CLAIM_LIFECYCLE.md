# MARKETHQ CLAIM LIFECYCLE

**Date:** 2026-09-16
**Phase:** H

---

## Claim Status Flow

```
UNTESTED
  ↓ (sufficient evidence)
TESTED
  ↓ (strong evidence, n≥30)
SUPPORTED
  ↓ (new evidence contradicts)
REJECTED

or

TESTED
  ↓ (inconsistent across windows)
UNSTABLE
```

## Rules

1. Claims start UNTESTED
2. Status changes require explicit validation
3. Version tracking: each status change creates new version
4. Old versions preserved (never overwrite)
5. Every claim carries: evidence, sample, windows, limitations
6. Claims are OBSERVATIONS, not truths
7. No claim = future performance guarantee

## Claim Validation Requirements

For SUPPORTED status:
- n ≥ 30 per bucket
- Temporal validation (multiple windows)
- No lookahead
- Effect size documented
- Confidence interval computed

For TESTED status:
- n ≥ 15
- At least 2 validation windows

For UNSTABLE:
- Mixed evidence across windows
- n ≥ 10

For REJECTED:
- Strong counter-evidence
- n ≥ 10

## Anti-Patterns

- Never promote claim without validation
- Never treat claim as truth
- Never ignore contradictory evidence
- Never use single correlation as SUPPORTED
- Never ignore sample size