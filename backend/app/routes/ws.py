# from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# from app.core.tick_store import get_tick
# import asyncio
# # import WebSocketDisconnect

# router = APIRouter()

# # @router.websocket("/ws/ltp")
# # async def ws_ltp(websocket: WebSocket, symbol: str):
# #     await websocket.accept()

# #     symbol = symbol.upper()

# #     while True:
# #         tick = get_tick(symbol)
# #         await websocket.send_json(tick or {"symbol": symbol, "error": "no tick"})
# #         await asyncio.sleep(1)

# @router.websocket("/ws/ltp")
# async def ws_ltp(websocket: WebSocket, symbol: str):
#     await websocket.accept()

#     try:
#         while True:
#             tick = get_cached_ltp(symbol)
#             if tick:
#                 await websocket.send_json(tick)
#             await asyncio.sleep(1)
#     except WebSocketDisconnect:
#         print("Client disconnected")

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from app.core.tick_store import get_tick  # make sure this import is correct

router = APIRouter()

@router.websocket("/ws/ltp")
async def ws_ltp(ws: WebSocket, symbol: str):
    await ws.accept()

    symbol = symbol.upper().strip()
    print(f"⚡ WS Connected for {symbol}")

    placeholder_sent = False

    try:
        while True:
            tick = get_tick(symbol)
            print("WS LOOP tick for", symbol, "=>", tick)  # <--- DEBUG

            if tick:
                # tick should be a dict: {"symbol": "...", "ltp": ..., "timestamp": ...}
                await ws.send_json({
                    "symbol": tick.get("symbol", symbol),
                    "ltp": tick.get("ltp"),
                    "timestamp": tick.get("timestamp"),
                    "source": "websocket",
                })
                placeholder_sent = False
            else:
                # only send placeholder once, not spam
                if not placeholder_sent:
                    await ws.send_json({
                        "symbol": symbol,
                        "ltp": None,
                        "source": "waiting",
                    })
                    placeholder_sent = True

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        print(f"❌ WS disconnected for {symbol}")
