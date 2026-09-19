# -*- coding: utf-8 -*-
"""Phase J7 — FastAPI REST API for AzizBusiness HQ.

Exposes all J6 intelligence surfaces via REST API:
- /api/hq/overview
- /api/hq/situation
- /api/agents, /api/agents/{id}
- /api/opportunities, /api/opportunities/{id}
- /api/setups, /api/setups/{id}
- /api/research/runs, /api/research/runs/{id}
- /api/claims
- /api/memory
- /api/drift
- /api/reliability
- /api/human-review

Research-only. No trading. No broker.
"""

from __future__ import annotations

import sys
import os
import time
import uuid
import threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime, timezone

from hq_decision_surface import HQDecisionSurface
from intelligence_state_j6 import IntelligenceStateJ6, IntelligenceState
from claim_validation_pipeline import ClaimValidationPipeline
from agent_reliability import ReliabilityTracker

app = FastAPI(
    title="AzizBusiness HQ API",
    description="AI Research Command Center API — Research Only, No Trading",
    version="7.0.0",
)

allowed_origins = [
    o.strip() for o in os.environ.get("AZIZ_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Requested-With"],
)

# Global HQ instance
hq = HQDecisionSurface()


# ─── Request/Response Models ───

class ResearchRunRequest(BaseModel):
    symbol: str = "THYAO.IS"
    timeframe: str = "1h"
    trigger: str = "manual"


class HumanReviewRequest(BaseModel):
    review_type: str
    claim_id: str
    decision: str  # REVIEW_REQUIRED, APPROVED, REJECTED, DEFERRED
    notes: str = ""


class PriorityRequest(BaseModel):
    action: str
    expected_info_value: float = 0.5
    uncertainty: float = 0.5
    impact: str = "medium"
    data_available: bool = True
    historical_instability: float = 0.0
    drift_detected: bool = False
    recurrence: float = 0.0
    failure_memory: int = 0
    claim_instability: float = 0.0
    research_cost: str = "low"


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


# ─── Startup ───

@app.on_event("startup")
async def startup():
    """Initialize HQ on startup."""
    # Ensure intelligence state is initialized
    if hq.intelligence.state == IntelligenceState.INITIALIZING:
        hq.intelligence.state = IntelligenceState.OBSERVING
        hq.intelligence.entered_at = datetime.now(timezone.utc).isoformat()


# ─── Health ───

@app.get("/api/health")
async def health():
    """Component-aware health check endpoint."""
    components: dict[str, str] = {
        "api": "HEALTHY",
        "workforce": "HEALTHY",
        "brain": "HEALTHY",
        "memory": "HEALTHY",
        "sse": "HEALTHY",
    }

    # PostgreSQL
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgresql://"):
        try:
            from repository_pg import PostgresRepository
            repo = PostgresRepository(db_url)
            chk = repo.check_connection()
            components["postgresql"] = "HEALTHY" if chk.get("connected") else "UNAVAILABLE"
            repo.close()
        except Exception:
            components["postgresql"] = "UNAVAILABLE"
    else:
        components["postgresql"] = "UNAVAILABLE"

    # AI gateway/provider availability (without expensive generation)
    try:
        from ai_gateway.gateway import get_gateway
        gw = get_gateway()
        providers = gw.providers.list_all()
        configured = [p for p in providers if getattr(p, "configured", False)]
        components["ai"] = "HEALTHY" if configured else "DEGRADED"
    except Exception:
        components["ai"] = "UNAVAILABLE"

    overall = "HEALTHY"
    if any(v == "UNAVAILABLE" for v in components.values()):
        overall = "DEGRADED"
    elif any(v == "DEGRADED" for v in components.values()):
        overall = "DEGRADED"

    return {
        "status": overall,
        "service": "azizbusiness-hq",
        "version": "7.0.0",
        "components": components,
    }


# ─── HQ Overview ───

@app.get("/api/hq/overview")
async def hq_overview():
    """HQ Overview — current market state, research health, reliability."""
    try:
        return hq.get_overview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── HQ Situation ───

@app.get("/api/hq/situation")
async def hq_situation():
    """Full situation report."""
    try:
        return hq.get_situation()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Research Runs ───

@app.get("/api/research/runs")
async def get_research_runs(limit: int = Query(50, ge=1, le=200)):
    """Get research runs with optional limit."""
    runs = hq.get_research_runs()
    return {"runs": runs[-limit:], "total": len(runs)}


@app.get("/api/research/runs/{run_id}")
async def get_research_run(run_id: str):
    """Get specific research run by ID."""
    run = hq.get_research_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


# ─── Agents ───

@app.get("/api/agents")
async def get_agents():
    """List all agents with reliability profiles."""
    return {"agents": hq.get_agents()}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get specific agent reliability profile."""
    agent = hq.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent


# ─── Opportunities ───

@app.get("/api/opportunities")
async def get_opportunities():
    """List detected opportunities."""
    return {"opportunities": hq.get_opportunities()}


@app.get("/api/opportunities/{opp_id}")
async def get_opportunity(opp_id: str):
    """Get specific opportunity."""
    opp = hq.get_opportunity(opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail=f"Opportunity {opp_id} not found")
    return opp


# ─── Setups ───

@app.get("/api/setups")
async def get_setups():
    """List research-backed setups."""
    return {"setups": hq.get_setups()}


@app.get("/api/setups/{setup_id}")
async def get_setup(setup_id: str):
    """Get specific setup."""
    setups = hq.get_setups()
    for s in setups:
        if s.get("setup_id") == setup_id or s.get("id") == setup_id:
            return s
    raise HTTPException(status_code=404, detail=f"Setup {setup_id} not found")


# ─── Claims ───

@app.get("/api/claims")
async def get_claims(status: Optional[str] = Query(None)):
    """List claims, optionally filtered by status."""
    claims_data = hq.get_claims()
    if status:
        claims_data["claims"] = {
            k: v for k, v in claims_data.get("claims", {}).items()
            if v.get("status") == status
        }
    return claims_data


@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str):
    """Get specific claim."""
    claim = hq.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "status": claim.status.value,
        "evidence": claim.evidence,
        "sample_size": claim.sample_size,
        "confidence": claim.confidence,
        "stability": claim.stability,
        "first_observed": claim.first_observed,
        "last_validated": claim.last_validated,
    }


# ─── Memory ───

@app.get("/api/memory")
async def get_memory(limit: int = Query(50, ge=1, le=200)):
    """Get research memory."""
    memory = hq.get_memory()
    return {"memory": memory[-limit:], "total": len(memory)}


# ─── Drift ───

@app.get("/api/drift")
async def get_drift():
    """Get current drift state."""
    return hq.get_drift()


# ─── Reliability ───

@app.get("/api/reliability")
async def get_reliability():
    """Get agent reliability summary."""
    return hq.get_reliability()


# ─── Human Review ───

@app.get("/api/human-review")
async def get_human_reviews():
    """Get human review queue."""
    return {"reviews": hq.get_human_review()}


@app.post("/api/human-review")
async def add_human_review(req: HumanReviewRequest):
    """Add human review decision."""
    review = hq.add_human_review(
        review_type=req.review_type,
        claim_id=req.claim_id,
        decision=req.decision,
        notes=req.notes,
    )
    return review


# ─── Research Priority ───

@app.post("/api/research/priority")
async def set_research_priority(req: PriorityRequest):
    """Set research priority with auditable explanation."""
    explanation = hq.set_research_priority(
        action=req.action,
        expected_info_value=req.expected_info_value,
        uncertainty=req.uncertainty,
        impact=req.impact,
        data_available=req.data_available,
        historical_instability=req.historical_instability,
        drift_detected=req.drift_detected,
        recurrence=req.recurrence,
        failure_memory=req.failure_memory,
        claim_instability=req.claim_instability,
        research_cost=req.research_cost,
    )
    return {"explanation": explanation}


# ─── Situation Report ───

@app.get("/api/hq/situation-report")
async def situation_report():
    """Get HQ Situation Report — research report, NOT trading advice."""
    report = hq.build_situation_report()
    return {"report": report, "type": "research_only", "no_trading_advice": True}


# ─── Start Research Run ───

@app.post("/api/research/start")
async def start_research(req: ResearchRunRequest):
    """Start a research run."""
    try:
        from autonomous_research_loop import AutonomousResearchLoop
        loop = AutonomousResearchLoop()
        report = loop.run_full_cycle(
            symbol_scope=req.symbol,
            timeframe_scope=req.timeframe,
            trigger=req.trigger,
        )
        run_id = getattr(report.run, 'run_id', 'unknown') if report.run else 'unknown'
        return {"status": "started", "run_id": run_id, "report_id": report.report_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Global Exception Handler ───

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "path": request.url.path},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": str(exc)},
    )


# ─── J8: Middleware + Security Headers + Rate Limiting ───

_SECRET_KEY = os.environ.get("AZIZ_SECRET_KEY", "dev-secret-change-in-production")
_VALID_TOKENS = set(os.environ.get("AZIZ_API_TOKENS", "dev-token").split(","))
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 60
_request_timestamps: dict[str, list[float]] = {}
_alerts: list[dict] = []
_sse_listeners: list[dict] = []
_sse_lock = threading.Lock()


@app.middleware("http")
async def j8_security_middleware(request: Request, call_next):
    start = time.time()
    # Rate limiting
    key = f"{request.client.host}:{request.url.path}" if request.client else "unknown"
    now = time.time()
    timestamps = [t for t in _request_timestamps.get(key, []) if now - t < _RATE_LIMIT_WINDOW]
    timestamps.append(now)
    _request_timestamps[key] = timestamps
    if len(timestamps) > _RATE_LIMIT_MAX:
        return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})
    response = await call_next(request)
    response.headers["X-Response-Time"] = f"{(time.time() - start) * 1000:.1f}ms"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' http://127.0.0.1:3000 http://localhost:3000; frame-ancestors 'none'; base-uri 'self'"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# ─── J8: SSE Events ───

@app.get("/api/sse/events")
async def sse_events(request: Request):
    """Server-Sent Events for real-time updates."""
    async def event_generator():
        import asyncio, queue
        q: queue.Queue = queue.Queue()
        with _sse_lock:
            _sse_listeners.append({"queue": q})
        try:
            while True:
                try:
                    msg = await asyncio.to_thread(q.get, timeout=30)
                    yield msg
                except Exception:
                    yield "event: ping\ndata: {\"type\":\"ping\"}\n\n"
        except Exception:
            pass
        finally:
            with _sse_lock:
                _sse_listeners[:] = [l for l in _sse_listeners if l["queue"] is not q]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─── J8: Auth ───

security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if credentials.credentials not in _VALID_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials


@app.post("/api/auth/login")
async def login(request: Request):
    """Simple token-based login."""
    body = await request.json()
    token = body.get("token", "")
    if token not in _VALID_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"status": "ok", "token": token, "role": "research"}


# ─── J8: Alerts ───

def add_alert(alert_type: str, severity: str, message: str, source: str = "system",
              related_id: Optional[str] = None):
    alert = {
        "id": str(uuid.uuid4())[:8],
        "type": alert_type, "severity": severity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source, "message": message,
        "related_id": related_id, "read": False,
    }
    _alerts.insert(0, alert)
    return alert


@app.get("/api/alerts")
async def list_alerts(limit: int = 50, _=Depends(verify_token)):
    return {"status": "ok", "data": _alerts[:limit]}


@app.post("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, _=Depends(verify_token)):
    for a in _alerts:
        if a["id"] == alert_id:
            a["read"] = True
            return {"status": "ok", "data": a}
    raise HTTPException(status_code=404, detail="Alert not found")


@app.post("/api/research/notify")
async def notify_research(request: Request):
    """Receive research events for SSE broadcast."""
    body = await request.json()
    alert = add_alert(
        alert_type=body.get("event", "research_update"),
        severity=body.get("data", {}).get("severity", "info"),
        message=body.get("data", {}).get("message", "Research update"),
        source=body.get("data", {}).get("source", "research"),
        related_id=body.get("data", {}).get("id"),
    )
    return {"status": "ok", "alert_id": alert["id"]}


# ─── J8: Extended Health ───

@app.get("/api/hq/health")
async def hq_health():
    """Extended health check."""
    return {
        "status": "ok", "api": "azizbusiness-hq", "sse": "available",
        "alerts": len(_alerts),
        "unread_alerts": sum(1 for a in _alerts if not a["read"]),
        "db_type": "sqlite",
    }


# ─── Workforce Router ───
from workforce.api import router as workforce_router
app.include_router(workforce_router)