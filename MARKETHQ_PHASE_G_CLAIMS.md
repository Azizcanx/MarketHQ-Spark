# MARKETHQ PHASE G — RESEARCH CLAIMS

**Date:** 2026-09-16
**Purpose:** All research claims explicitly status-labeled

---

## Claim Status Definitions

| Status | Meaning |
|--------|---------|
| TESTED | Validated with sufficient data |
| SUPPORTED | Evidence supports claim (not guaranteed) |
| UNSTABLE | Result varies across windows |
| REJECTED | Evidence contradicts claim |
| UNTESTED | Not enough data or not tested |

---

## Claims

### Quality V4 Claims

**CLAIM-001:** "High-quality setups had higher T1 hit rate."
- Status: UNTESTED
- Sample: pending Phase G replay
- Required: n ≥ 30 per quality bucket
- Temporal validation: required

**CLAIM-002:** "Quality score correlates with realized R."
- Status: UNSTABLE
- Quality V4 is experimental
- Walk-forward stability not proven

**CLAIM-003:** "Quality buckets show monotonic outcome ordering."
- Status: UNTESTED
- Requires: quality buckets × outcome distribution

### Agent Confidence Claims

**CLAIM-004:** "Agent direction confidence correlates with outcome."
- Status: UNTESTED
- Confidence = evidence consistency, NOT probability
- Requires: confidence buckets × realized R

**CLAIM-005:** "High-confidence agents produce better setups."
- Status: UNTESTED
- Requires: agent-level attribution

### Evidence Claims

**CLAIM-006:** "Supporting evidence count predicts outcome."
- Status: UNTESTED
- Conflicting evidence may dominate

**CLAIM-007:** "Evidence consistency (confidence) > majority vote."
- Status: UNTESTED

### Setup Geometry Claims

**CLAIM-008:** "Narrow entry zones have higher T1 hit but lower entry rate."
- Status: UNTESTED
- Zone width vs. entry frequency trade-off

**CLAIM-009:** "ATR-based invalidation distance is appropriate."
- Status: UNTESTED
- Requires: invalidation distance × outcome

**CLAIM-010:** "T1/T2/T3 distances follow consistent RR pattern."
- Status: UNTESTED

### Regime Claims

**CLAIM-011:** "Regime affects setup performance."
- Status: UNTESTED
- Requires: regime × outcome matrix

**CLAIM-012:** "DOWNTREND_STRONG: SHORT setups outperform."
- Status: UNTESTED

### Strategy Family Claims

**CLAIM-013:** "Strategy family × regime interaction matters."
- Status: UNTESTED

**CLAIM-014:** "Cross-family agreement improves outcome."
- Status: UNTESTED

### Walk-Forward Claims

**CLAIM-015:** "Validation metrics are stable across windows."
- Status: UNSTABLE
- Requires: ≥3 windows

**CLAIM-016:** "Train → validation drift is measurable."
- Status: UNTESTED

### RR Claims

**CLAIM-017:** "High RR setups have higher realized R."
- Status: UNTESTED
- RR ≠ expected return

**CLAIM-018:** "RR buckets show monotonic outcome."
- Status: UNTESTED

### Failure Claims

**CLAIM-019:** "High quality + invalidation = common pattern."
- Status: UNTESTED

**CLAIM-020:** "Strong regime compatibility doesn't guarantee success."
- Status: UNTESTED

---

## Anti-Claims (Explicitly Rejected)

These are NEVER claims of MarketHQ:

- "This setup will make money"
- "Win probability = X%"
- "Quality score = future performance"
- "Backtest = future results"
- "High RR = guaranteed profit"
- "Agent confidence = probability"

---

## Usage Rules

1. Every claim gets a unique ID (CLAIM-XXX)
2. Status is explicit, never implied
3. Sample size documented with each claim
4. Temporal window documented
5. Claims are OBSERVATIONS, not TRUTHS
6. Brain gets observations with full context
7. No claim auto-promotes any strategy