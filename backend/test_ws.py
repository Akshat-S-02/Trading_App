import asyncio
import websockets
import os
import json
from dotenv import load_dotenv

load_dotenv()

async def test_conn():
    client_id = os.getenv("CLIENT_ID")
    token = os.getenv("ACCESS_TOKEN")
    base = "wss://api-feed.dhan.co"
    url = f"{base}?version=2&token={token}&clientId={client_id}&authType=2"
    
    print(f"Connecting to {url.split('token=')[0]}token=...&{url.split('&token=')[1].split('&', 1)[1] if '&token=' in url else ''}...")
    try:
        # Use asyncio.wait_for for connect timeout instead of connect(timeout=)
        ws_conn = websockets.connect(url)
        async with asyncio.wait_for(ws_conn, timeout=10) as ws:
            print("Connected!")
            # Send a subscription for RELIANCE (2885)
            sub = {
                "RequestCode": 15,
                "InstrumentCount": 1,
                "InstrumentList": [{"ExchangeSegment": "NSE_EQ", "SecurityId": "2885"}]
            }
            await ws.send(json.dumps(sub))
            print("Sent subscription")
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"Received: {len(msg)} bytes")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())
