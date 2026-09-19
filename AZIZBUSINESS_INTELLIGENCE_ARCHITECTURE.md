# AZIZBUSINESS INTELLIGENCE ARCHITECTURE

**Date:** 2026-09-17

---

## Overview

AzizBusiness intelligence architecture — a production-grade research intelligence system.

NOT an auto-trading system. Research-only boundary preserved.

## Architecture Layers

### L1: Data Layer
- Market data (yfinance): THYAO.IS, AAPL, EURUSD=X, BTC-USD
- Database: market_hq.db (13.5MB SQLite)
- Observation bundles: MarketObservation, ObservationBundle

### L2: Intelligence Layer
- IntelligenceStateJ6: Full system state
- ChangeDetectionEngine: Regime/volatility/momentum/trend/liquidity detection
- DistributionDriftEngine: Quality/regime/setup/strategy/outcome/RR/volatility/evidence drift
- TemporalDecay: Evidence weighting with time decay
- CounterexampleEngine: Active search against hypotheses
- ClaimValidationPipeline: Structured claim lifecycle
- SearchableMemory: Full-text search over research memory
- IntelligenceHealthMonitor: System health tracking

### L3: Research Layer
- AutonomousResearchLoop: OBSERVE → DETECT → PRIORITIZE → PLAN → EXECUTE
  → CRITIC → SYNTHESIZE → VALIDATE → LEARN → REPORT → WAIT → OBSERVE
- ResearchOrchestrator: Team-based research coordination
- ResearchPlanner: Adaptive research planning
- AdaptiveTeamSelector: Team composition
- ResearchPriorityEngine: Priority scoring with explanations
- DataQualityGate: Data quality validation

### L4: Agent Layer
- AgentRegistry: Agent registration and discovery
- AgentRuntime V2: Agent execution with routing
- AgentRouter: Runtime selection and fallback
- ProviderAdapter: Provider abstraction (deterministic + mock)
- DeterministicRuntime: Local deterministic execution
- ParallelExecutor: Deterministic parallel execution
- TaskRouter: Capability-based task routing

### L5: HQ Decision Surface (J6)
- HQDecisionSurface: All API surfaces
  - /hq/overview, /hq/situation
  - /research/runs, /research/runs/{id}
  - /agents, /agents/{id}
  - /opportunities, /opportunities/{id}
  - /setups, /claims, /memory
  - /drift, /reliability, /human-review
- Situation Report: Research report, NOT trading advice
- Human Review: REVIEW_REQUIRED/APPROVED/REJECTED/DEFERRED

### L6: Reliability & Validation Layer (J6)
- AgentReliabilityProfile: Per-agent reliability tracking
- ReliabilityTracker: Reliability management
- ClaimValidationPipeline: Claim lifecycle with audit trail
- DriftState: System drift tracking
- IntelligenceStateJ6: Full J6 intelligence state

## State Machine

Intelligence States:
INITIALIZING → OBSERVING → STABLE / CHANGE_DETECTED / ERROR / PAUSED / STALE
OBSERVING → STABLE / CHANGE_DETECTED / ERROR / PAUSED / STALE
STABLE → OBSERVING / CHANGE_DETECTED / RESEARCHING / HUMAN_REVIEW / PAUSED / STALE
CHANGE_DETECTED → RESEARCHING / OBSERVING / HUMAN_REVIEW / PAUSED
RESEARCHING → VALIDATING / LEARNING / HUMAN_REVIEW / OBSERVING / PAUSED / ERROR
VALIDATING → LEARNING / RESEARCHING / HUMAN_REVIEW / PAUSED / ERROR
LEARNING → STABLE / OBSERVING / HUMAN_REVIEW / PAUSED / ERROR
HUMAN_REVIEW → RESEARCHING / LEARNING / STABLE / OBSERVING / PAUSED
PAUSED → OBSERVING / INITIALIZING / RESEARCHING
ERROR → INITIALIZING / OBSERVING / PAUSED
STALE → OBSERVING / RESEARCHING / PAUSED

## Data Flow

Market Observation → Opportunity Detection → Setup Candidate
→ Research-Backed Setup → Historical Validation → Outcome
→ Evidence → Claim → Research Memory → Future Research

Every object traceable backward and forward. No orphaned research results.

## Safety Boundary

- No broker connection
- No order placement
- No real-money execution
- No auto-trading
- No auto-strategy deployment
- No auto weight promotion
- Human approval required for all decisions
- Research-only boundary enforced