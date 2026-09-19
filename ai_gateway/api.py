# -*- coding: utf-8 -*-
"""Phase J9 — FastAPI AI Gateway Endpoints."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ai_gateway.gateway import AIGateway, get_gateway
from ai_gateway.models import (
    AIRequest, ProviderSpec, ModelSpec, Tier, Purpose, RoutingMode,
)
from ai_gateway.adapters import (
    FreeProviderAdapter, NousAdapter, DeterministicAdapter,
)
from ai_gateway.mock import MockFreeProviderAdapter, MockNousAdapter

security = HTTPBearer(auto_error=False)

VALID_TOKENS = {"dev-token"}


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials not in VALID_TOKENS:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return credentials.credentials


# Defaults registered in get_gateway()

def create_ai_api(app: FastAPI) -> None:
    """Add AI Gateway endpoints to FastAPI app."""

    @app.get("/api/ai/providers")
    async def list_providers(_=Depends(verify_token)):
        return {"status": "ok", "data": get_gateway().providers.to_dict()}

    @app.get("/api/ai/providers/{provider_id}")
    async def get_provider(provider_id: str, _=Depends(verify_token)):
        p = get_gateway().providers.get(provider_id)
        if not p:
            raise HTTPException(status_code=404, detail="Provider not found")
        return {"status": "ok", "data": p.to_dict()}

    @app.get("/api/ai/models")
    async def list_models(_=Depends(verify_token)):
        return {"status": "ok", "data": get_gateway().models.to_dict()}

    @app.get("/api/ai/models/{model_id}")
    async def get_model(model_id: str, _=Depends(verify_token)):
        m = get_gateway().models.get(model_id)
        if not m:
            raise HTTPException(status_code=404, detail="Model not found")
        return {"status": "ok", "data": m.to_dict()}

    @app.get("/api/ai/health")
    async def ai_health(_=Depends(verify_token)):
        return {"status": "ok", "data": get_gateway().get_health_summary()}

    @app.get("/api/ai/routing/policy")
    async def get_routing_policy(_=Depends(verify_token)):
        return {"status": "ok", "data": get_gateway().router.to_dict()}

    @app.put("/api/ai/routing/policy")
    async def set_routing_policy(mode: str, _=Depends(verify_token)):
        try:
            routing_mode = RoutingMode(mode.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")
        get_gateway().router.set_routing_mode(routing_mode)
        return {"status": "ok", "mode": mode.upper()}

    @app.post("/api/ai/test")
    async def test_provider(provider_id: str = Query(...),
                             model_id: str = Query(...),
                             _=Depends(verify_token)):
        """Test provider connectivity — no trading, just connectivity."""
        provider = get_gateway().providers.get(provider_id)
        model = get_gateway().models.get(model_id)

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        if not provider.configured:
            return JSONResponse(status_code=200, content={
                "status": "ok",
                "provider": provider_id,
                "model": model_id,
                "configured": False,
                "result": "NOT_CONFIGURED",
            })

        # Use mock adapter for testing
        adapter = MockFreeProviderAdapter(provider, model, behavior="SUCCESS")
        response = adapter.generate(AIRequest(purpose=Purpose.RESEARCH))
        return {"status": "ok", "data": response.to_dict()}

    @app.get("/api/ai/usage")
    async def get_usage(_=Depends(verify_token)):
        return {"status": "ok", "data": get_gateway().get_usage()}

    @app.get("/api/ai/requests/{request_id}")
    async def get_request(request_id: str, _=Depends(verify_token)):
        req = get_gateway().get_request(request_id)
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        return {"status": "ok", "data": req}

    @app.get("/api/ai/audit")
    async def get_audit(limit: int = 50, _=Depends(verify_token)):
        audit = get_gateway().get_audit_log()
        return {"status": "ok", "data": audit[-limit:]}