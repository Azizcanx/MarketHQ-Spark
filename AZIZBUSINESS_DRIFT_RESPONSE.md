# AZIZBUSINESS DRIFT RESPONSE

**Date:** 2026-09-17

---

## Overview

Drift response integrates data drift, market drift, model drift, and research drift
into research planning.

Drift influences research priority — NOT automatic trading decisions.

## Drift Types

### DATA_DRIFT
Data distribution has changed significantly.
Example: Feature distributions shifted.
Response: Block dependent research until data quality is restored.

### MARKET_DRIFT
Market regime has changed.
Example: TRENDING → RANGE transition.
Response: Prioritize regime research.

### MODEL_DRIFT
Model predictions have degraded.
Example: Accuracy dropped below threshold.
Response: Trigger model retraining/review.

### RESEARCH_DRIFT
Research quality has declined.
Example: Claim stability falling.
Response: Revalidate claims, increase evidence requirements.

## Drift Detection

The DistributionDriftEngine detects:

- Quality drift: Data quality distribution changes
- Regime drift: Market regime distribution changes
- Setup drift: Setup configuration distribution changes
- Strategy family drift: Strategy family distribution changes
- Outcome drift: Win/loss distribution changes
- RR drift: Risk/reward ratio distribution changes
- Volatility drift: Volatility distribution changes
- Evidence drift: Evidence quality distribution changes

## Drift Response Rules

### Regime Distribution Changes
IF regime distribution changes significantly
→ PRIORITIZE regime research

### Agent Reliability Changes
IF agent reliability changes significantly
→ TRIGGER reliability review

### Claim Stability Falls
IF claim stability falls below threshold
→ REVALIDATE claim

### Data Quality Falls
IF data quality falls below threshold
→ BLOCK dependent research

## Drift State

The DriftState tracks:
- regime_drift_detected
- regime_drift_magnitude
- regime_drift_severity
- data_drift_detected
- data_drift_magnitude
- model_drift_detected
- research_drift_detected
- last_checked
- affected_symbols
- affected_timeframes

## Integration with Research Priority

Drift influences research priority:

```
WHY THIS RESEARCH?
  - high uncertainty
  - recent regime transition / drift detected
  - sufficient data
  - previous failures
  - claim instability
```

## Examples

### Example 1: Regime Drift

```
Drift detected: TRENDING → RANGE (magnitude: 0.30, severity: SIGNIFICANT)
→ Priority: Regime transition research
→ Action: Analyze RANGE regime setups
→ Evidence needed: 50+ setups in RANGE
→ Human review: Required for regime change confirmation
```

### Example 2: Data Drift

```
Drift detected: Data quality degraded (good: 80% → 50%)
→ Priority: Data quality investigation
→ Action: Validate data sources
→ Evidence needed: Source comparison
→ Block dependent research until resolved
```

### Example 3: Agent Reliability Drift

```
Drift detected: Agent reliability dropped (0.85 → 0.45)
→ Priority: Agent reliability review
→ Action: Review agent outputs
→ Evidence needed: Recent execution comparison
→ Human review: Required if reliability < 0.3
```

## Safety Boundary

Drift response NEVER:
- Automatically changes trading decisions
- Places trades
- Modifies weights without human approval
- Overrides human review

Drift response ONLY:
- Influences research priority
- Triggers reliability review
- Blocks dependent research if data quality poor
- Requests human review for significant changes

## Integration with HQ

Drift state is exposed via:
- /drift — current drift state
- /hq/overview — drift state in overview
- /hq/situation — drift context in situation report
- /agents/{id} — agent drift flag in reliability profile

## Monitoring

Drift is monitored continuously:
- Regime distribution changes
- Data quality changes
- Model performance changes
- Research quality changes

Alerts generated for:
- Significant regime transitions
- Data quality degradation
- Agent reliability drift
- Claim stability falls