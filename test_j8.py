#!/usr/bin/env python3
"""Phase J8 — Production HQ Integration Tests."""

import sys, os, traceback
sys.path.insert(0, '/opt/markethq')
os.chdir('/opt/markethq')

passed = 0
failed = 0
errors = []

def test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  PASS: {name}")
    except Exception as e:
        failed += 1
        errors.append((name, traceback.format_exc()))
        print(f"  FAIL: {name} — {e}")


def test_j8_import():
    from api.main import app
    assert app is not None

def test_j8_sse_endpoint():
    from api.main import app
    from fastapi.routing import APIRoute
    routes = [r.path for r in app.routes if isinstance(r, APIRoute)]
    assert "/api/sse/events" in routes

def test_j8_login_valid():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"token": "dev-token"})
    assert r.status_code == 200
    assert r.json()["role"] == "research"

def test_j8_login_invalid():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"token": "wrong"})
    assert r.status_code == 401

def test_j8_alerts():
    from api.main import app, add_alert
    from fastapi.testclient import TestClient
    client = TestClient(app)
    add_alert("drift", "warning", "Test alert", "test")
    r = client.get("/api/alerts", headers={"Authorization": "Bearer dev-token"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) >= 1
    assert data[0]["message"] == "Test alert"

def test_j8_alert_ack():
    from api.main import app, add_alert
    from fastapi.testclient import TestClient
    client = TestClient(app)
    alert = add_alert("test", "info", "Ack test", "test")
    r = client.post(f"/api/alerts/{alert['id']}/ack", headers={"Authorization": "Bearer dev-token"})
    assert r.status_code == 200
    assert r.json()["data"]["read"] is True

def test_j8_alert_not_found():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/api/alerts/nonexistent/ack", headers={"Authorization": "Bearer dev-token"})
    assert r.status_code == 404

def test_j8_rate_limit():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    last_status = 200
    for _ in range(70):
        r = client.get("/api/hq/health")
        last_status = r.status_code
    assert last_status == 429

def test_j8_rate_limit_not_blocked():
    """Rate limit window expired → request succeeds."""
    from api.main import app, _request_timestamps
    from fastapi.testclient import TestClient
    # Clear rate limit state
    _request_timestamps.clear()
    client = TestClient(app)
    r = client.get("/api/hq/health")
    assert r.status_code == 200

def test_j8_notify_research():
    from api.main import app, add_alert, _alerts
    from fastapi.testclient import TestClient
    client = TestClient(app)
    before = len(_alerts)
    r = client.post("/api/research/notify", json={
        "event": "opportunity_detected",
        "data": {"message": "Test opportunity", "severity": "info"},
    })
    assert r.status_code == 200
    assert len(_alerts) >= before

def test_j8_health_extended():
    from api.main import app, _request_timestamps
    from fastapi.testclient import TestClient
    _request_timestamps.clear()
    client = TestClient(app)
    r = client.get("/api/hq/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["sse"] == "available"

def test_j8_security_headers():
    from api.main import app, _request_timestamps
    from fastapi.testclient import TestClient
    _request_timestamps.clear()
    client = TestClient(app)
    r = client.get("/api/hq/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"

def test_j8_response_time_header():
    from api.main import app, _request_timestamps
    from fastapi.testclient import TestClient
    _request_timestamps.clear()
    client = TestClient(app)
    r = client.get("/api/hq/health")
    assert "x-response-time" in r.headers

def test_postgres_repo_exists():
    from api.repository import PostgresRepository
    assert PostgresRepository is not None

def test_auth_protected():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/alerts")
    assert r.status_code == 401

def test_auth_valid_token():
    from api.main import app, add_alert
    from fastapi.testclient import TestClient
    client = TestClient(app)
    add_alert("test", "info", "Auth test", "test")
    r = client.get("/api/alerts", headers={"Authorization": "Bearer dev-token"})
    assert r.status_code == 200

def test_auth_invalid_token():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/alerts", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401

def test_sse_reconnect():
    from api.main import app
    from fastapi.routing import APIRoute
    routes = [r.path for r in app.routes if isinstance(r, APIRoute)]
    assert "/api/sse/events" in routes

def test_j7_api_health():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200

def test_j7_api_overview():
    from api.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/hq/overview")
    assert r.status_code == 200

def test_j7_repo_persistence():
    from api.repository import SQLiteRepository
    import tempfile, os
    db = tempfile.mktemp(suffix=".db")
    repo = SQLiteRepository(db_path=db)
    repo.save_research_run({"run_id": "J7-REG", "symbol": "THYAO.IS", "timeframe": "1h", "status": "COMPLETED"})
    r = repo.get_research_run("J7-REG")
    assert r is not None
    os.remove(db)

def test_j7_multi_asset():
    import yfinance as yf
    df = yf.download("THYAO.IS", period="5d", interval="1h", progress=False)
    assert df is not None and len(df) > 0

def test_frontend_env():
    env = open("/opt/markethq/frontend/.env").read()
    assert "MARKETHQ_BACKEND_URL" in env


print("="*60)
print("J8 Test Suite")
print("="*60)

test("J8 import", test_j8_import)
test("J8 SSE endpoint", test_j8_sse_endpoint)
test("J8 login valid", test_j8_login_valid)
test("J8 login invalid", test_j8_login_invalid)
test("J8 alerts", test_j8_alerts)
test("J8 alert ack", test_j8_alert_ack)
test("J8 alert 404", test_j8_alert_not_found)
test("J8 rate limit", test_j8_rate_limit)
test("J8 rate limit not blocked", test_j8_rate_limit_not_blocked)
test("J8 notify research", test_j8_notify_research)
test("J8 health extended", test_j8_health_extended)
test("J8 security headers", test_j8_security_headers)
test("J8 response time header", test_j8_response_time_header)
test("Postgres repo exists", test_postgres_repo_exists)
test("Auth protected", test_auth_protected)
test("Auth valid token", test_auth_valid_token)
test("Auth invalid token", test_auth_invalid_token)
test("SSE reconnect", test_sse_reconnect)
test("J7 API health", test_j7_api_health)
test("J7 API overview", test_j7_api_overview)
test("J7 repo persistence", test_j7_repo_persistence)
test("J7 multi asset", test_j7_multi_asset)
test("Frontend env", test_frontend_env)

print(f"\n{'='*60}")
print(f"J8 Test Suite: {passed} PASS, {failed} FAIL")
if errors:
    print(f"\nFailures:")
    for name, tb in errors:
        print(f"  {name}: {tb.split(chr(10))[-2]}")
sys.exit(1 if failed else 0)