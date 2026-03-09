"""
ARCHIVED — Redis Stream Execution Worker
=========================================
This worker has been intentionally retired in favour of the DB Outbox pattern.

WHY OUTBOX WINS OVER REDIS STREAMS FOR ORDER EXECUTION
-------------------------------------------------------
The Redis Stream approach has a fundamental crash safety gap:

    1. Signal arrives on the stream.
    2. ExecutionEngine writes Order to DB and calls Dhan API.
    3. Server dies before XACK is sent.

On restart, Redis replays the message — but the Order is already in the DB
and may already be at the broker. You now have a duplicate-order risk with
no programmatic protection unless you rebuild Redis consumer group state.

The DB Outbox pattern eliminates this:

    1. Signal arrives.
    2. ExecutionEngine writes Order + OutboxEvent in a single atomic transaction.
    3. Server can die at any point. On restart, the OutboxEvent is still PENDING
       in PostgreSQL. The worker picks it up, checks idempotency via signal_hash,
       and resumes safely — no duplicate orders, no lost events, no manual XACK recovery.

WHAT TO RUN INSTEAD
-------------------
    python backend/app/workers/outbox_worker.py

Or as a module:
    python -m app.workers.outbox_worker

The outbox_worker.py polls the `outbox_events` table every 1 second,
uses FOR UPDATE SKIP LOCKED for horizontal scale safety, and has built-in
exponential backoff retry (up to 3 attempts before FAILED_FATAL).

This file is kept (not deleted) to preserve architectural decision history.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExecutionWorker")


def run_worker():
    """
    Inert stub. Preserved so legacy imports do not raise ImportError.
    Directs operators to the correct outbox worker.
    """
    logger.warning(
        "\n"
        "=" * 70 + "\n"
        "RETIRED WORKER: Redis Stream ExecutionWorker is no longer active.\n"
        "\n"
        "The canonical order execution path is the DB Outbox Worker.\n"
        "Run this instead:\n"
        "\n"
        "    python backend/app/workers/outbox_worker.py\n"
        "\n"
        "See the module docstring in this file for the architectural rationale.\n"
        + "=" * 70
    )
    sys.exit(0)


if __name__ == "__main__":
    run_worker()
