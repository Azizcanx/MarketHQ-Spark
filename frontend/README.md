# MarketHQ Frontend

Next.js frontend and API layer for MarketHQ.

## Getting Started

Run the development server:

```bash
npm run dev
```

Open `http://localhost:3000` in your browser.

Production build:

```bash
npm ci
npm run build
npm run start
```

## Autonomous Operations

The autonomous operations layer is **research-only** in this phase. The worker/Cursor path is isolated and bounded; live trading, broker execution, main-repository mutation, automatic PR creation, and automatic merge remain disabled.

### Environment

Copy `.env.example` to the deployment environment and configure only the values required by the deployment. Never commit secrets.

- `MARKETHQ_AUTOMATION_URL` — public HTTPS origin used by the external scheduler to call `/api/automation/cycle`.
- `MARKETHQ_AUTOMATION_SECRET` — shared secret required by the cycle endpoint when configured.
- `MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER` — server-side scheduler gate; keep `false` until production readiness is verified.
- `MARKETHQ_CURSOR_WORKER_ENABLE` — Cursor worker gate; keep `false` until real Cursor CLI/auth preflight is verified in the target environment.
- `MARKETHQ_WORKER_DB_PATH` — optional SQLite path. In production, use persistent storage; do not commit the database.

Persistent autonomous mode is stored separately and defaults to disabled. The external GitHub Actions scheduler is also opt-in and requires the repository variable `MARKETHQ_AUTONOMOUS_SCHEDULER_ENABLED=true` plus the secrets `MARKETHQ_AUTOMATION_URL` and `MARKETHQ_AUTOMATION_SECRET`.

### Safe activation order

1. Deploy the Next.js app with all autonomous controls disabled.
2. Verify the Workers page and `/api/automation/cycle` GET readiness telemetry.
3. Verify the target environment has persistent storage for the SQLite worker runtime database.
4. Verify real Cursor CLI availability/authentication through the worker preflight; CI's deterministic Cursor fixture is not proof of real CLI availability.
5. Configure the automation URL and secret in the scheduler environment.
6. Only after the above checks pass, explicitly enable the intended research-only scheduler/mode controls.
7. Keep trading/execution and automatic PR/merge capabilities disabled.

### External scheduler

`.github/workflows/markethq-autonomous-cycle.yml` provides a 15-minute GitHub Actions trigger plus manual dispatch. It is intentionally gated by `MARKETHQ_AUTONOMOUS_SCHEDULER_ENABLED` and secret configuration. The workflow must exist on the repository's default branch before the scheduled trigger can run as a normal repository schedule.

The cycle endpoint itself is bounded (`maxIterations` is capped) and protected by the automation secret when configured. A failed or unsafe worker path stops/reviews the cycle rather than enabling execution.

### Current readiness boundary

The autonomous operations code is ready for deployment preparation, but no production hosting target, public URL, deployment credentials, or production secrets are assumed by the repository. Do not invent or commit those values. Until a real deployment is configured, the scheduled workflow remains opt-in and inactive.

## Learn More

- Next.js documentation: https://nextjs.org/docs
- Next.js deployment guide: https://nextjs.org/docs/app/building-your-application/deploying
