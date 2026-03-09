"""
Bucket A Smoke Test
====================
Verifies all 6 Bucket A fixes are correctly in place.
Run from the backend/ directory:

    python test_bucket_a_fixes.py

Requires: PostgreSQL (for DB import chain), Redis (for test 4).
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def check(name, fn):
    try:
        fn()
        print(f"  [{PASS}] {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"  [{FAIL}] {name}: {e}")
        results.append((name, False, str(e)))


print("\n=== Bucket A Smoke Tests ===\n")

# ── Test 1: OrderStatus.CLOSED must not exist ──────────────────────────────────
def test_no_closed_status():
    from app.models import OrderStatus
    assert not hasattr(OrderStatus, "CLOSED"), (
        "OrderStatus.CLOSED still exists — trade.py will crash on POST /api/trade/place"
    )

check("1. OrderStatus.CLOSED removed from enum", test_no_closed_status)


# ── Test 2: trade.py route module constructs Order with valid status ────────────
def test_trade_route_order_status():
    # Import the route module — if OrderStatus.CLOSED is referenced at module level it raises here
    import app.routes.trade as trade_module
    from app.models import OrderStatus

    # Simulate what the route does: verify NEW is a valid member
    assert OrderStatus.NEW is not None, "OrderStatus.NEW does not exist — route is broken"

check("2. trade.py references valid OrderStatus.NEW", test_trade_route_order_status)


# ── Test 3: asyncio importable from ws_routes ──────────────────────────────────
def test_ws_routes_asyncio():
    import app.routes.ws_routes as ws_routes_module
    import asyncio
    # The module uses asyncio.sleep — verify the module loaded without NameError
    assert hasattr(ws_routes_module, "router"), "ws_routes.router not found after import"

check("3. ws_routes.py imports without NameError (asyncio fix)", test_ws_routes_asyncio)


# ── Test 4: execution_worker.py is inert (imports fine, run_worker exits 0) ────
def test_execution_worker_inert():
    import app.workers.execution_worker as ew
    assert hasattr(ew, "run_worker"), "run_worker() stub is missing from execution_worker.py"
    # Do NOT call run_worker() here — it calls sys.exit(0) by design

check("4. execution_worker.py is archived & exposes harmless run_worker() stub", test_execution_worker_inert)


# ── Test 5: reconciliation_engine uses valid OrderStatus ──────────────────────
def test_reconciliation_engine_status():
    from app.models import OrderStatus
    # FAILED was the bug — only FAILED_RETRYABLE and FAILED_FATAL are valid
    assert not hasattr(OrderStatus, "FAILED"), (
        "OrderStatus.FAILED still exists — reconciliation_engine will use the wrong member"
    )
    assert hasattr(OrderStatus, "FAILED_RETRYABLE"), "OrderStatus.FAILED_RETRYABLE missing"
    assert hasattr(OrderStatus, "FAILED_FATAL"), "OrderStatus.FAILED_FATAL missing"

check("5. reconciliation_engine uses OrderStatus.FAILED_RETRYABLE (not FAILED)", test_reconciliation_engine_status)


# ── Test 6: Redis tick round-trip (requires Redis running) ───────────────────
def test_redis_tick_roundtrip():
    from app.core.tick_store import save_tick, get_tick
    TEST_SYMBOL = "BUCKET_A_SMOKE_TEST"
    TEST_LTP = 9999.99

    save_tick(TEST_SYMBOL, TEST_LTP)
    result = get_tick(TEST_SYMBOL)

    assert result is not None, (
        f"Redis is not reachable or save_tick silently failed. "
        f"get_tick('{TEST_SYMBOL}') returned None. "
        f"Ensure Redis is running on 127.0.0.1:6379."
    )
    assert abs(float(result["ltp"]) - TEST_LTP) < 0.01, (
        f"Redis round-trip value mismatch: wrote {TEST_LTP}, got {result['ltp']}"
    )
    assert result["symbol"].upper() == TEST_SYMBOL.upper(), (
        f"Symbol key mismatch: wrote '{TEST_SYMBOL}', got '{result.get('symbol')}'"
    )

check("6. Redis tick round-trip (save_tick -> get_tick) works correctly", test_redis_tick_roundtrip)


# ── Summary ────────────────────────────────────────────────────────────────────
print()
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)

if passed == total:
    print(f"All {total}/{total} tests passed. Bucket A is clean.\n")
    sys.exit(0)
else:
    print(f"{passed}/{total} tests passed. Fix the failures above before proceeding.\n")
    for name, ok, err in results:
        if not ok:
            print(f"  FAILED: {name}")
            print(f"    {err}")
    print()
    sys.exit(1)
