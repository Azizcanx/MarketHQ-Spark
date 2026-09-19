# MARKETHQ — OPPORTUNITY MODEL

## Opportunity

Research-only market opportunity record. Aggregates Phase D strategy research agent results.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| opportunity_id | str | Unique ID (UUID-based) |
| symbol | str | Trading symbol (e.g., THYAO.IS) |
| timeframe | str | Timeframe (e.g., 1h, 5m) |
| detected_at | str | ISO timestamp |
| market_context | str | Human-readable context summary |
| regime | str | Current market regime |
| direction | Direction | LONG / SHORT / NEUTRAL / UNKNOWN |
| thesis | str | Deterministic research thesis |
| status | OpportunityStatus | Lifecycle status |
| confidence | float | Evidence consistency (0-1), NOT win probability |
| uncertainty | float | 1 - confidence |
| agent_results | list[dict] | Per-agent raw results |
| supporting_evidence | list[dict] | Evidence supporting direction |
| conflicting_evidence | list[dict] | Evidence against direction |
| strategy_families | list[str] | Families involved |
| strategy_count | int | Total agents queried |
| independent_families | int | Independent (non-correlated) families |
| correlated_families | int | Correlated families |
| feature_snapshot_id | str | FeatureSnapshot cache reference |
| source_agents | list[SourceAgent] | Per-agent traceability |
| first_detected_at | str | First detection timestamp |
| last_updated_at | str | Last update timestamp |
| invalidation_reason | str | Why invalidated |
| expiry_reason | str | Why expired |
| metadata | dict | Arbitrary metadata |

### Direction

- LONG — bullish bias
- SHORT — bearish bias
- NEUTRAL — no directional bias
- UNKNOWN — insufficient/conflicting evidence

### Status Lifecycle

DETECTED → UNDER_REVIEW → VALIDATED (or INVALIDATED) → EXPIRED → ARCHIVED

## SourceAgent

Per-agent traceability within an opportunity.

| Field | Description |
|-------|-------------|
| agent_id | Agent identifier |
| agent_version | Version string |
| direction | Agent's direction |
| confidence | Agent's confidence |
| thesis | Agent's reasoning (truncated) |
| evidence_count | Number of evidence items |
| supporting_features | Features supporting direction |
| conflicting_features | Features contradicting direction |
| required_features | Features needed |
| unavailable_features | Features not available |
| strategy_family | Strategy family |
| regime | Agent's regime assessment |
| timestamp | Agent result timestamp |
| status | Agent status |

## SetupCandidate

Research-only setup candidate — NOT a trade recommendation.

| Field | Description |
|-------|-------------|
| candidate_id | Unique ID |
| opportunity_id | Parent opportunity |
| symbol | Symbol |
| timeframe | Timeframe |
| direction | Direction |
| status | CANDIDATE (not confirmed) |
| candidate_entry_zone | CANDIDATE zone (not entry) |
| invalidation_candidate | CANDIDATE invalidation |
| target_candidate | CANDIDATE target |
| supporting_evidence | Supporting evidence references |
| conflicting_evidence | Conflicting evidence references |
| historical_evidence_reference | Link to historical evidence |
| quality_reference | Quality reference |
| uncertainty | Uncertainty measure |
| regime | Regime at detection |
| detected_at | Timestamp |

## Critical Distinctions

- **Opportunity confidence** ≠ Win probability
- **VALIDATED** ≠ Trade will succeed
- **CANDIDATE** ≠ Trade recommendation
- **UNTESTED** ≠ Invalid (no historical validation yet)
- **Quality V4 score** ≠ Opportunity confidence
