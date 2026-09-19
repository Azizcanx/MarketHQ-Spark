# AZIZBUSINESS API ARCHITECTURE

**Date:** 2026-09-17

---

## Overview

FastAPI REST API for AzizBusiness HQ.

Research-only boundary enforced. No trading. No broker.

## Endpoints

### Health
- `GET /api/health` — Health check

### HQ
- `GET /api/hq/overview` — Market state, research health, reliability, uncertainty
- `GET /api/hq/situation` — Full situation data
- `GET /api/hq/situation-report` — Text situation report (research only)

### Research Runs
- `GET /api/research/runs?limit=50` — List runs
- `GET /api/research/runs/{run_id}` — Specific run
- `POST /api/research/start` — Start new research run

### Agents
- `GET /api/agents` — List agents with reliability
- `GET /api/agents/{agent_id}` — Agent reliability profile

### Opportunities
- `GET /api/opportunities` — List opportunities
- `GET /api/opportunities/{opp_id}` — Specific opportunity

### Setups
- `GET /api/setups` — List setups
- `GET /api/setups/{setup_id}` — Specific setup

### Claims
- `GET /api/claims?status=UNTESTED` — List claims (filter by status)
- `GET /api/claims/{claim_id}` — Specific claim

### Memory
- `GET /api/memory?limit=50` — Research memory

### Drift
- `GET /api/drift` — Current drift state

### Reliability
- `GET /api/reliability` — Agent reliability summary

### Human Review
- `GET /api/human-review` — Review queue
- `POST /api/human-review` — Add review decision

### Research Priority
- `POST /api/research/priority` — Set priority with explanation

## Response Format

All endpoints return JSON:
```json
{
  "status": "ok",
  "data": { ... }
}
```

Error format:
```json
{
  "error": "not_found",
  "detail": "Run ABC123 not found"
}
```

## Error Codes

- 200 — Success
- 400 — Bad request
- 404 — Not found
- 422 — Validation error
- 500 — Internal server error

## Swagger/OpenAPI

Auto-generated at `http://localhost:8000/docs`

## Security

- Research-only boundary
- No trading endpoints
- No broker connection
- Human review required for decisions
- All actions audited

## Rate Limiting

Not implemented yet (J8).

## Authentication

Not implemented yet (J8).

## CORS

Configurable for frontend integration (J8).