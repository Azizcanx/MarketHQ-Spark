# AZIZBUSINESS HQ DECISION SURFACE

**Date:** 2026-09-17

---

## Overview

The HQ Decision Surface is the AI research command center for AzizBusiness.

Brand: AzizBusiness HQ

UI feels like an AI research command center, NOT a traditional trading dashboard.

## Required Surfaces (§14)

### 1. HQ Overview
Shows:
- Current market state
- Active research
- Detected opportunities
- Important changes
- Research health
- Agent health
- Reliability
- Uncertainty
- Pending human review

### 2. Opportunity Center
Each opportunity shows:
- What
- Why
- Evidence
- Conflicts
- Regime
- Timeframe
- Historical context
- Research confidence
- Uncertainty
- Lifecycle

### 3. Research Runs
Shows:
- Active
- Completed
- Failed
- Blocked
- Waiting
- Duration
- Agents
- Evidence
- Output

### 4. Agent Board
Shows:
- Agent identity
- Capabilities
- Health
- Reliability
- Recent work
- Failures
- Current task

### 5. Claims
Shows:
- Claim
- Evidence
- Status
- Sample
- Stability
- Counterexamples
- Last validation

### 6. Intelligence Timeline
Chronological:
observation → change → opportunity → research → critique → validation → learning

### 7. Human Review
Distinguishes:
- REVIEW_REQUIRED
- APPROVED
- REJECTED
- DEFERRED

Human review must never silently alter research history.

## API Contract (§16)

### /hq/overview
Returns HQ overview with market state, research health, reliability, uncertainty.

### /hq/situation
Returns full situation report.

### /research/runs
Returns list of all research runs.

### /research/runs/{id}
Returns specific research run details.

### /agents
Returns list of all agents with reliability profiles.

### /agents/{id}
Returns specific agent reliability profile.

### /opportunities
Returns detected opportunities.

### /opportunities/{id}
Returns specific opportunity details.

### /setups
Returns research-backed setups.

### /claims
Returns all claims with validation status.

### /memory
Returns research memory entries.

### /drift
Returns current drift state.

### /reliability
Returns agent reliability summary.

### /human-review
Returns human review queue and decisions.

## Situation Report (§15)

Example output:

```
AZIZBUSINESS HQ — CURRENT SITUATION

Market:
  Observation: {trend: UPTREND, volatility: 0.15}
  Data Quality: GOOD
  Uncertainty: 0.30

Regime:
  Active: TRENDING
  Changes: 1

Important Changes:
  - Regime shift: RANGE → TRENDING (2026-09-17)

Detected Opportunities:
  - THYAO.IS trend continuation (confidence: 0.75)

Strong Evidence:
  - Claim C-1: THYAO trend up (SUPPORTED, n=50)

Conflicting Evidence:
  - Claim C-2: THYAO mean reversion (UNSTABLE, n=10)

Historical Context:
  - Similar setup in Aug 2026: +3% in 5 days

Agent Reliability:
  - trend_agent: 0.85
  - breakout_agent: 0.60

Research Running:
  - RUN-XXX: regime analysis

Uncertainty: 0.30
Recommended Next Research: regime transition analysis

---
This is a RESEARCH REPORT. Not trading advice.
No BUY/SELL/ENTER NOW/GUARANTEED statements.
```

## Brand Guidelines

- AzizBusiness
- AzizBusiness HQ
- AI research command center aesthetic
- Dark theme
- Same-tab navigation
- Agent OS aesthetic

## What This Is NOT

- NOT a trading dashboard
- NO BUY/SELL/ENTER NOW
- NO GUARANTEED statements
- NO trade execution UI
- NOT an auto-trading system