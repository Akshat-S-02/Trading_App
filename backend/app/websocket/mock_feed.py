import asyncio
import json
import random
import yfinance as yf
from fastapi import WebSocket, APIRouter

router = APIRouter()

connected_clients = set()

@router.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    print("📲 Client connected to Mock Feed")
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except Exception:
        print("❌ Client disconnected")
    finally:
        connected_clients.remove(websocket)

async def broadcast_mock_prices():
    """Broadcasts random prices for sandbox symbols"""
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
    print("📡 Starting Mock Price Feed...")
    
    while True:
        try:
            if not connected_clients:
                await asyncio.sleep(2)
                continue

            for symbol in symbols:
                # In a real scenario, we'd fetch or simulate realistic movement
                # For now, just a random fluctuation around a base price
                base_price = 2500.0 if "RELIANCE" in symbol else 3500.0 if "TCS" in symbol else 1500.0
                price = base_price + random.uniform(-10, 10)
                
                packet = {
                    "symbol": symbol,
                    "LTP": price
                }
                
                # Broadcast to all
                disconnected = set()
                for client in connected_clients:
                    try:
                        await client.send_text(json.dumps(packet))
                    except:
                        disconnected.add(client)
                
                for dead in disconnected:
                    connected_clients.remove(dead)
            
            await asyncio.sleep(1) # Update every second
            
        except Exception as e:
            print(f"Mock Feed Error: {e}")
            await asyncio.sleep(5)
