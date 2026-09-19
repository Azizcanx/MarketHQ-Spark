# MARKETHQ — RESEARCH-BACKED SETUP MODEL

## ResearchBackedSetup

Research-backed setup candidate derived from an Opportunity.
NOT a trade recommendation. Entry/invalidation/target are CANDIDATES.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| setup_id | str | Unique ID (UUID-based) |
| opportunity_id | str | Parent opportunity |
| symbol | str | Trading symbol |
| timeframe | str | Timeframe |
| detected_at | str | ISO timestamp |
| direction | Direction | LONG/SHORT/NEUTRAL/UNKNOWN |
| regime | str | Market regime |
| setup_type | str | Setup type signature |
| strategy_family | str | Strategy family |
| thesis | str | Research thesis |
| entry_zone_low | float | Entry zone low |
| entry_zone_high | float | Entry zone high |
| entry_reference | float | Entry reference price |
| entry_method | str | How entry was computed |
| entry_confirmation | list[str] | Confirmation signals |
| entry_status | str | AVAILABLE/UNAVAILABLE/PARTIAL |
| invalidation_price | float | Invalidation level |
| invalidation_type | str | ATR/structure/combined/unavailable |
| invalidation_reason | str | Why invalidation at this level |
| invalidation_distance_atr | float | Distance in ATR multiples |
| target_1/2/3 | float | Target levels |
| target_method | str | How targets were computed |
| stop_distance | float | Risk distance |
| target_distance_1/2/3 | float | Reward distances |
| rr_to_t1/2/3 | float | Risk/reward ratios |
| supporting_evidence | list[dict] | Supporting agent evidence |
| conflicting_evidence | list[dict] | Conflicting agent evidence |
| historical_evidence | dict | Historical stats |
| structure_evidence | dict | Structure context |
| regime_evidence | dict | Regime context |
| momentum_evidence | dict | Momentum context |
| liquidity_evidence | dict | Liquidity context |
| volatility_evidence | dict | Volatility context |
| uncertainty_flags | list[UncertaintyFlag] | Uncertainty flags |
| overall_uncertainty | float | 0-1 uncertainty measure |
| quality_reference | str | Quality engine reference |
| confidence | float | Research confidence (NOT win probability) |
| uncertainty | float | 1 - confidence |
| data_availability | float | 0-1 data availability |
| source_agents | list[dict] | Per-agent traceability |
| evidence_traces | list[EvidenceTrace] | Assertion → source traces |
| feature_snapshot_id | str | FeatureSnapshot reference |
| created_at | str | Creation timestamp |
| expires_at | str | Expiry timestamp |
| status | SetupStatus | Lifecycle status |
| why_panel | dict | WHY panel data |

### SetupStatus

- CANDIDATE — Initial candidate
- UNDER_REVIEW — Conflicts or data limitations
- CONFIRMED_RESEARCH_SETUP — Research criteria met (NOT trade confirmed)
- INVALIDATED — Thesis no longer valid
- EXPIRED — Context changed
- ARCHIVED — Historical record

## UncertaintyFlag

| Field | Description |
|-------|-------------|
| type | UncertaintyType enum |
| description | Human-readable description |
| severity | low/medium/high/critical |
| feature | Which feature is affected |

## EvidenceTrace

| Field | Description |
|-------|-------------|
| assertion | What is being asserted |
| source_agent | Which agent produced it |
| agent_run_id | Agent run reference |
| feature_snapshot_id | FeatureSnapshot reference |
| timestamp | When evidence was captured |
| evidence_feature | Which feature supports this |
| evidence_value | Feature value |
| evidence_direction | Direction of evidence |

## Critical Distinctions

- **Setup confidence ≠ Win probability**
- **CONFIRMED_RESEARCH_SETUP ≠ Trade confirmed**
- **CANDIDATE ≠ Trade recommendation**
- **UNTESTED ≠ Invalid**
- **Quality V4 score ≠ Setup confidence**
- **RR is geometric measure ≠ Quality score**
- **No broker, no orders, no trading, no real money**
- **No fake data, no lookahead, no overclaim**
