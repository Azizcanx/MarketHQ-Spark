# AZIZBUSINESS CLAIM VALIDATION

**Date:** 2026-09-17

---

## Overview

Every important research claim must have:

- claim_id
- statement (text)
- source
- evidence
- sample size
- time period
- symbols
- timeframes
- confidence/calibration information
- validation status
- first_seen (first_observed)
- last_tested (last_validated)
- expiry/decay
- contradictory evidence
- counterexamples

## Allowed States

- UNTESTED — claim exists, no evidence yet
- TESTED — evidence collected, not yet validated
- SUPPORTED — sufficient evidence supports claim
- UNSTABLE — evidence conflicts or sample too small
- REJECTED — evidence contradicts claim
- EXPIRED — claim outdated, needs revalidation

## Validation Rules

### No Automatic Promotion to SUPPORTED

A claim CANNOT be promoted to SUPPORTED without:
1. At least one evidence reference
2. No contradictory evidence
3. Sufficient sample size (configurable)
4. Recent validation (not expired)

### Contradictory Evidence Handling

When contradictory evidence is added:
1. Claim status moves to UNSTABLE (if was SUPPORTED)
2. Contradictory evidence is logged
3. Counterexample search is triggered
4. Human review may be required

### Counterexample-First Research

For every strong claim:
1. Search historical counterexamples
2. Look for failures in same regime
3. Look for low-quality winners
4. Look for high-quality losers
5. Look for regime transition failures

## Claim Lifecycle

```
UNTESTED → TESTED → SUPPORTED
              ↓           ↓
           UNSTABLE ←── REJECTED
              ↓
           EXPIRED
```

## Claim Validation Pipeline API

```python
from claim_validation_pipeline import ClaimValidationPipeline

pipeline = ClaimValidationPipeline()

# Create claim
claim = pipeline.create_claim(
    claim_id="C-1",
    text="THYAO trend up",
    source="trend_agent",
    symbols=["THYAO.IS"],
    timeframes=["1h"],
    confidence=0.75,
)

# Add evidence
pipeline.add_evidence("C-1", "E-001")

# Add contradictory evidence
pipeline.add_contradictory_evidence("C-1", "E-002")

# Add counterexample
pipeline.add_counterexample("C-1", "CE-001")

# Update status (only with evidence, no contradictions)
pipeline.update_status("C-1", ClaimStatus.TESTED)

# Cannot promote to SUPPORTED without evidence
pipeline.update_status("C-1", ClaimStatus.SUPPORTED)  # ValueError

# Cannot promote with contradictory evidence
pipeline.update_status("C-1", ClaimStatus.SUPPORTED)  # ValueError
```

## Validation History

Every status change is logged:
- Timestamp
- Action (CREATED, EVIDENCE_ADDED, CONTRADICTORY_EVIDENCE, COUNTEREXAMPLE, STATUS_CHANGE)
- Detail

This provides a complete audit trail for every claim.

## Integration with HQ

Claims are exposed via:
- /claims — all claims with status summary
- /claims/{id} — specific claim with full validation history
- /hq/situation — strong evidence and conflicting evidence

## Data Limitations

- Claims require real evidence — no synthetic data
- Sample size must be realistic
- Time period must be specified
- Symbols and timeframes must be explicit
- If data unavailable: UNAVAILABLE