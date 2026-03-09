# Backend Startup Topology

This document is the canonical reference for what processes to start and in what order.

---

## Mandatory Processes

Both of these must be running for the system to function. Running only the API means
orders will be created in the DB but **will never reach Dhan** — they stay `NEW` until
the outbox worker claims them.

### 1. API Server

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Starts:
- All REST/WebSocket routes
- Dhan market-feed WebSocket (live tick stream)
- Dhan access-token auto-renewal loop (daily at ~08:15 IST)
- Default user creation on first boot

### 2. Outbox Worker ← Canonical execution path

```bash
cd backend
python app/workers/outbox_worker.py
```

Or as a module (from the project root, one level above `backend/`):

```bash
python -m app.workers.outbox_worker
```

This is the **only path** that places orders at Dhan.
It polls `outbox_events` every 1 second, uses `FOR UPDATE SKIP LOCKED`
(safe for multiple parallel workers), and retries with exponential backoff
up to 3 times before marking `FAILED_FATAL`.

---

## Optional / Dev Processes

These are not required for normal operation.

### Reconciliation (on demand, at startup after a crash)

```bash
cd backend
python test_cold_boot.py
```

Runs once. Syncs DB positions against live broker positions. Use after any unclean shutdown.

### Outbox resilience tests

```bash
cd backend
python test_outbox_resilience.py
```

Verifies worker crash-recovery and retry mechanics. Requires PostgreSQL and Redis.

### Research / Backtesting

```bash
cd backend
python run_mae_mfe_universe.py
```

Standalone — does not require the API or the outbox worker.

---

## WebSocket Routes

| Route | Source | Consumer |
|---|---|---|
| `ws://host/ws/market` | Dhan live feed → in-process dict | Flutter app (primary) |
| `ws://host/ws/ltp?symbol=X` | Dhan live feed → Redis (`tick:X`) | Single-symbol polling clients |

Both routes now read from the same underlying tick data.
`/ws/market` is the primary Flutter route.
`/ws/ltp` is a secondary single-symbol endpoint.

> **Note (Bucket B):** `ws.py` and `ws_routes.py` both define `/ws/ltp`. After the
> asyncio fix lands, the route registered last in `main.py` wins. Clean this up in
> the next sprint by deleting `ws_routes.py` entirely and keeping only `ws.py`.

---

## Known Limits (to fix in Bucket B)

- `PortfolioMetrics.last_margin_sync` is never written → stale-margin guard is always skipped (silent)
- Manual trade route (`POST /api/trade/place`) bypasses `ExecutionEngine` — sandbox only
- Duplicate `GET /api/portfolio` and `GET /api/trades` endpoints exist in both `trade.py` and `admin.py`
