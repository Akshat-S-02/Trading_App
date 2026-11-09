
import requests
import json
import time
import asyncio
import websockets
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"

def test_removed_routes():
    print("\n🔍 Testing Removed Routes (Should return 404)...")
    
    routes_to_test = [
        "/ws/ltp", # Should NOT return 404 as WebSocket, but as GET it might depending on FastAPI
        "/api/market/portfolio",
        "/api/market/order",
        "/api/market/ticks/RELIANCE",
        "/api/trade/portfolio",
        "/api/trade/trades"
    ]
    
    for route in routes_to_test:
        resp = requests.get(f"{BASE_URL}{route}")
        if resp.status_code == 404:
            print(f"✅ {route} -> 404 (Correct)")
        else:
            print(f"❌ {route} -> {resp.status_code} (Expected 404)")

def test_sandbox_route():
    print("\n🔍 Testing Sandbox Manual Trade Route...")
    
    # We don't have a valid JWT easily here without a more complex setup, 
    # but we can at least check if the route exists and returns 401/403 instead of 404.
    
    payload = {
        "symbol": "RELIANCE",
        "qty": 1,
        "side": "BUY"
    }
    
    resp = requests.post(f"{BASE_URL}/sandbox/api/trade/place", json=payload)
    if resp.status_code in [401, 403]:
        print(f"✅ /sandbox/api/trade/place exists (Returned {resp.status_code} as expected without Auth)")
    elif resp.status_code == 404:
        print(f"❌ /sandbox/api/trade/place -> 404 (FAILED)")
    else:
        print(f"❓ /sandbox/api/trade/place -> {resp.status_code}")

async def test_websocket_ltp():
    print("\n🔍 Testing Consolidated WebSocket /ws/ltp...")
    
    # Try connecting to the compatibility endpoint
    uri = f"{WS_URL}/ws/ltp?symbol=RELIANCE"
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to /ws/ltp")
            # Wait for first message
            task = asyncio.create_task(websocket.recv())
            done, pending = await asyncio.wait([task], timeout=5)
            
            if done:
                msg = list(done)[0].result()
                data = json.loads(msg)
                print(f"✅ Received data: {data}")
                if data.get("symbol") == "RELIANCE":
                    print("✅ Symbol match correct")
            else:
                print("⚠️ Timeout waiting for tick (Market might be closed or no ticks in Redis)")
                # This is okay as long as connection was allowed
            
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")

def test_canonical_endpoints():
    print("\n🔍 Testing Canonical Endpoints...")
    
    endpoints = [
        "/api/portfolio",
        "/api/trades"
    ]
    
    for ep in endpoints:
        resp = requests.get(f"{BASE_URL}{ep}")
        if resp.status_code in [401, 403]:
            print(f"✅ {ep} exists (Returned {resp.status_code})")
        else:
            print(f"❌ {ep} returned {resp.status_code}")

if __name__ == "__main__":
    # Note: Backend must be running for these to pass!
    print("🚀 Starting Bucket B Smoke Test...")
    test_removed_routes()
    test_sandbox_route()
    test_canonical_endpoints()
    
    # WS test requires asyncio
    try:
        asyncio.run(test_websocket_ltp())
    except Exception as e:
        print(f"⚠️ WS Test skipped or failed: {e}")
    
    print("\n🏁 Smoke Test Finished.")
