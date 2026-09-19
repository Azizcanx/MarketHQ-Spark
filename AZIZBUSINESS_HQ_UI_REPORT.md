# AZIZBUSINESS HQ UI REPORT

**Date:** 2026-09-17

---

## Current State

### Existing Frontend (Next.js)

Mevcut Next.js frontend:
- `frontend/app/research-result/page.tsx`
- `frontend/app/quant/page.tsx`
- `frontend/app/intelligence/page.tsx`
- `frontend/app/ops/page.tsx`
- `frontend/app/brain/page.tsx`
- `frontend/app/api/` — API routes for agents, setup, ops, automation

### Brand

AzizBusiness / AzizBusiness HQ

### UI Aesthetic

Research command center, NOT trading terminal.
Dark theme, same-tab navigation, agent OS style.

## J7 API Integration

FastAPI endpoints ready for frontend integration:
- GET /api/hq/overview
- GET /api/hq/situation
- GET /api/hq/situation-report
- GET /api/agents
- GET /api/opportunities
- GET /api/claims
- GET /api/drift
- GET /api/reliability
- GET /api/human-review
- POST /api/human-review
- POST /api/research/priority
- POST /api/research/start

## Dashboard Surfaces (§14)

### 1. HQ Overview
Market state, research health, reliability, uncertainty

### 2. Opportunity Center
What, why, evidence, conflicts, regime, timeframe

### 3. Research Runs
Active, completed, failed, blocked, waiting

### 4. Agent Board
Identity, capabilities, health, reliability, recent work

### 5. Claims
Claim, evidence, status, sample, stability, counterexamples

### 6. Intelligence Timeline
Observation → change → opportunity → research → critique → validation → learning

### 7. Human Review
REVIEW_REQUIRED, APPROVED, REJECTED, DEFERRED

## What's NOT in Scope for J7

- Full Next.js dashboard rewrite (J8)
- WebSocket real-time updates (J8)
- Authentication (J8)
- Rate limiting (J8)
- Alerting system (J8)

## Next Steps (J8)

1. Connect Next.js frontend to FastAPI
2. Add real-time polling/SSE
3. Upgrade dashboard UI to HQ surfaces
4. Add authentication
5. Add alerting

## Safety

- No BUY/SELL/ENTER NOW in UI
- No trading terminal aesthetic
- Research report clearly labeled
- Uncertainty always shown
- Human review required for decisions