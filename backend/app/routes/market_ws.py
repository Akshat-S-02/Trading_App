# # app/routes/market_ws.py
# from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# import asyncio
# from app.services.dhan_service import start_dhan_stream, stop_dhan_stream

# router = APIRouter()

# clients = set()

# async def on_dhan_tick(msg):
#     # Broadcast to all active WebSocket clients
#     for ws in list(clients):
#         try:
#             await ws.send_json(msg)
#         except Exception:
#             clients.discard(ws)

# @router.websocket("/ws/market")
# async def ws_market(websocket: WebSocket):
#     await websocket.accept()
#     clients.add(websocket)
#     print("📲 Flutter client connected")

#     await start_dhan_stream(on_dhan_tick)

#     try:
#         while True:
#             await websocket.receive_text()  # keep alive
#     except WebSocketDisconnect:
#         clients.discard(websocket)
#         stop_dhan_stream(on_dhan_tick)
#         print("❌ Flutter client disconnected")
