from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.tick_store import get_tick

router = APIRouter()

@router.websocket("/ws/ltp")
async def ltp_socket(websocket: WebSocket):
    await websocket.accept()

    symbol = websocket.query_params.get("symbol").upper()

    try:
        while True:
            tick = get_tick(symbol)
            if tick:
                await websocket.send_json(tick)
            await asyncio.sleep(0.3)

    except WebSocketDisconnect:
        print("WS client disconnected")
