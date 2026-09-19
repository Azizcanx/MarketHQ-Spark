# AZIZBUSINESS PRODUCTION API

**Date:** 2026-09-17

---

## J8 API Extensions

### Authentication

**POST /api/auth/login**
Body: `{"token": "your-token"}`
Response: `{"status": "ok", "token": "...", "role": "research"}`

Tokens from `AZIZ_API_TOKENS` env var (comma-separated).
Default: `dev-token`

### Rate Limiting

- 60 requests per minute per IP+path
- HTTP 429 on exceed
- Sliding window

### Alerts

**GET /api/alerts** — List alerts (auth required)
**POST /api/alerts/{id}/ack** — Acknowledge alert (auth required)

Alert types: drift, opportunity, claim, agent, research
Severities: info, warning, critical

### SSE Events

**GET /api/sse/events** — Server-Sent Events stream

Events:
- research_started
- research_completed
- opportunity_detected
- opportunity_invalidated
- agent_status_changed
- claim_updated
- drift_detected
- intelligence_state_updated
- human_review_required
- alert
- ping

### Security Headers

- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- X-Response-Time: <ms>

### Extended Health

**GET /api/hq/health**
```json
{
  "status": "ok",
  "api": "azizbusiness-hq",
  "sse": "available",
  "alerts": 5,
  "unread_alerts": 2,
  "db_type": "sqlite"
}
```

## API Contract

All endpoints return:
```json
{"status": "ok", "data": {...}}
```

Errors:
```json
{"error": "...", "detail": "...", "path": "/api/..."}
```

## Research-Only Boundary

- No broker connection
- No order placement
- No trading signals
- No auto-deployment
- Human approval required
- All actions audited