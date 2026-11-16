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

### Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

In-memory SQLite, Dhan mocked; needs neither Postgres nor Redis.

### Manual token renewal

```bash
cd backend
python force_renew.py
```

There is no broker reconciliation yet: after an unclean shutdown in live mode,
compare open orders in the Dhan app with the DB by hand. (The outbox worker
requeues or closes interrupted sends on its own at startup.)

---

## WebSocket Route

`ws://host/ws/market?token=<JWT>` streams every cached tick (symbol + LTP) every
500 ms. The app is its only client. Ticks also go to Redis (`tick:<SYMBOL>`),
which the worker and paper broker read.
