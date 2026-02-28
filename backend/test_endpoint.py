
import asyncio
import httpx
import os
import sys

# Mock config
DHAN_CLIENT_ID = "1109121898"
DHAN_ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiMjQwNjo3NDAwOjFjMzphMTBjOjZkZDc6OWYxMTo5YTE4OjUyNTUiLCJzX2lwIjoiNDkuMjA2LjE0LjIyOSIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NzA2NjMwMTcsImlhdCI6MTc3MDU3NjYxNywidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHBzOi8vd2ViaG9vay5zaXRlLzNkMDVlMTU4LTBlZGEtNGFiYi04MDQ5LTg4ZGE2ZGNlNTEzMCIsImRoYW5DbGllbnRJZCI6IjExMDkxMjE4OTgifQ.31KV_1OIzB9v0r6L_SUu-ONQo7fk5QMYlG1FUUvVzr7zj-ikP40Uw-qBKXTm-8sgEgSOgY4iN6lPPvj8g78Vvg"
BASE = "https://api.dhan.co"

HEADERS = {
    "client-id": DHAN_CLIENT_ID,
    "access-token": DHAN_ACCESS_TOKEN,
    "Content-Type": "application/json"
}

TESTS = [
    {
        "name": "/quote with symbols",
        "url": "/v2/marketfeed/quote",
        "payload": {"symbols": ["NSE_EQ:RELIANCE", "NSE_EQ:TCS"]}
    },
    {
        "name": "/ltp with symbols",
        "url": "/v2/marketfeed/ltp",
        "payload": {"symbols": ["NSE_EQ:RELIANCE", "NSE_EQ:TCS"]}
    },
    {
        "name": "/ltp with instruments (PascalCase)",
        "url": "/v2/marketfeed/ltp",
        "payload": {"instruments": [{"ExchangeSegment": "NSE_EQ", "SecurityId": "2885"}]}
    },
    {
        "name": "/ltp with instruments (camelCase)",
        "url": "/v2/marketfeed/ltp",
        "payload": {"instruments": [{"exchangeSegment": "NSE_EQ", "securityId": "2885"}]}
    },
     {
        "name": "/quote with instruments (camelCase)",
        "url": "/v2/marketfeed/quote",
        "payload": {"instruments": [{"exchangeSegment": "NSE_EQ", "securityId": "2885"}]}
    }
]

async def run_tests():
    async with httpx.AsyncClient() as client:
        for t in TESTS:
            print(f"\n--- Testing {t['name']} ---")
            url = BASE + t['url']
            print(f"URL: {url}")
            print(f"Payload: {t['payload']}")
            try:
                resp = await client.post(url, json=t['payload'], headers=HEADERS, timeout=5.0)
                print(f"Status: {resp.status_code}")
                try:
                    data = resp.json()
                    print(f"Response: {str(data)[:200]}")
                except:
                    print(f"Response Text: {resp.text[:200]}")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except ImportError:
        # Fallback if asyncio.run not available or other issue
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_tests())
