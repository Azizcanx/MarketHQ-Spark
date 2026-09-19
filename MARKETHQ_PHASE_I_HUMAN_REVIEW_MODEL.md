# MARKETHQ PHASE I — HUMAN REVIEW MODEL

**Date:** 2026-09-16
**Phase:** I

---

## Review Statuses

| Status | Meaning |
|--------|---------|
| UNREVIEWED | Not yet reviewed |
| REVIEWED | Reviewed, no action needed |
| ACCEPTED_FOR_RESEARCH | Accepted as research artifact |
| REJECTED | Rejected, with reason |
| NEEDS_MORE_DATA | Needs additional data |

## What Human Review Is NOT

Human review is NOT trade approval.
It is research artifact review.

ACCEPTED_FOR_RESEARCH means:
"This research result is accepted as a research artifact / candidate for continued investigation."

It does NOT mean:
- Trade approved
- Trade recommended
- Execution approved
- Profitable
- Guaranteed

## What Reviewers Can Inspect

- Opportunity
- Setup
- Evidence
- Conflicting evidence
- Uncertainty flags
- Historical evidence
- Validation
- Claims
- Reliability context
- Data availability
- Failure patterns
- Counterexamples
- Agent provenance

## Review Actions

1. Accept for research
2. Reject with reason
3. Request more data
4. Request re-validation
5. Flag for follow-up

## Review Provenance

Every review decision is recorded with:
- Reviewer ID
- Timestamp
- Notes
- Requested data
- Rejection reason
- Artifact lineage

## Review Queue

The HQ Decision Surface shows:
- UNREVIEWED items first
- NEEDS_MORE_DATA items next
- REVIEWED items
- ACCEPTED_FOR_RESEARCH items
- REJECTED items

## Review Safety

- No automatic promotion based on review
- Review is research-only, not trading
- Review decisions are versioned
- Review history is auditable
- Review cannot override data gating

## Example Review

```
Artifact: Setup S123
Reviewer: analyst_1
Status: NEEDS_MORE_DATA
Reason: "Volume data unavailable, cannot assess liquidity support"
Requested: volume_data for THYAO.IS 1h
```