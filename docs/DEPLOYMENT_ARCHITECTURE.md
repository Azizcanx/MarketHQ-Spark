# MarketHQ Production Deployment Architecture

## Current service boundary

MarketHQ currently has two runtime pieces:

1. **Next.js frontend** under `frontend/`.
2. **Python read-only market-data backend** exposed locally on port `8010` by the existing dashboard backend/runtime.

The Next.js application already supports a configurable backend origin through `MARKETHQ_BACKEND_URL`. When that variable is not set, several server-side paths fall back to `http://127.0.0.1:8010` for local development.

The Python runtime dependencies used by the repository's research/backtest/dashboard paths are now declared in the root `requirements.txt` so a deployment environment has an explicit install contract.

## Production requirement

A production deployment must provide a reachable backend service for the Next.js server. Do not deploy the frontend as an isolated static/serverless application while leaving `MARKETHQ_BACKEND_URL` pointed at `127.0.0.1:8010`; that address refers to the frontend runtime itself in a hosted environment and will not reach a separately hosted backend.

The production topology should therefore be:

```text
Browser
   |
   v
Next.js / frontend
   |
   | MARKETHQ_BACKEND_URL
   v
MarketHQ Python read-only backend :8010
```

The backend remains research-only: no broker execution, no order placement, and no write-enabled trading path should be introduced by deployment configuration.

## Autonomous operations topology

Autonomous operations are a separate control path:

```text
External scheduler (opt-in)
          |
          | HTTPS + x-markethq-automation-secret
          v
POST /api/automation/cycle
          |
          v
Bounded research cycle
          |
          +--> Research -> Decision -> Worker/Cursor
          |                    -> Validation -> Evidence
          |                    -> Feedback -> Next Cycle
          |
          v
Durable worker/cycle state
```

The scheduler remains disabled by default. The cycle endpoint also remains research-only, with live execution, broker execution, main-repository mutation, automatic PR creation, and automatic merge disabled.

## Production environment variables

### Next.js application

Required when autonomous operations are intended to be reachable:

- `MARKETHQ_BACKEND_URL` — HTTPS or internal service URL for the deployed Python backend.
- `MARKETHQ_AUTOMATION_URL` — public HTTPS origin of the deployed Next.js application.
- `MARKETHQ_AUTOMATION_SECRET` — long random secret shared with the external scheduler.
- `MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER=false` — keep disabled until deployment checks are complete.
- `MARKETHQ_CURSOR_WORKER_ENABLE=false` — keep disabled until real Cursor CLI/auth preflight succeeds.
- `MARKETHQ_WORKER_DB_PATH` — optional path to persistent storage for worker/cycle SQLite state.

The autonomous mode stored in SQLite also defaults to disabled.

### External scheduler

The repository workflow is intentionally opt-in and requires:

- repository variable `MARKETHQ_AUTONOMOUS_SCHEDULER_ENABLED=true`
- repository secret `MARKETHQ_AUTOMATION_URL`
- repository secret `MARKETHQ_AUTOMATION_SECRET`

The workflow must exist on the repository's default branch before GitHub's scheduled trigger can execute it.

## Persistent storage

The worker/cycle SQLite database must live on storage that survives application restarts and redeployments. Ephemeral serverless filesystems are not a valid production persistence strategy for autonomous cycle state.

If the hosting platform cannot provide persistent writable storage to the Next.js runtime, keep the autonomous scheduler disabled until the state store is moved to an appropriate persistent service.

## Activation order

1. Deploy frontend and backend independently or on a platform that supports both services.
2. Install Python dependencies from the root `requirements.txt` and verify the backend starts in read-only mode.
3. Set `MARKETHQ_BACKEND_URL` and verify read-only backend health/data routes.
4. Open the Workers page and verify scheduler/readiness telemetry.
5. Verify the worker SQLite database is persistent.
6. Verify real Cursor CLI installation, authentication, isolated worktree creation, and preflight.
7. Configure the automation URL and secret.
8. Keep the scheduler and autonomous mode disabled while validating the above.
9. Explicitly enable only the research-only autonomous scheduler after validation.
10. Keep trading/execution, broker execution, main-repo mutation, automatic PR, and automatic merge disabled.

## Current repository boundary

There is currently no committed provider-specific deployment manifest in the repository. Do not assume Vercel, Railway, Render, Docker, or another hosting provider. Provider-specific deployment work should only be added once the actual hosting target is selected.
