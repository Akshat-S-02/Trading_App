"""
Dhan market feed WebSocket client, and the /ws/market proxy the app connects to.
- Subscribes NSE_EQ symbols in chunks of 100 (Quote mode, so candles get volume).
- Parses Dhan's binary packets; writes each tick to Redis (tick_store.save_tick)
  and the in-process latest_ticks, and queues it for the paper strategy runner.
- Reconnects with backoff; a watchdog forces a reconnect when the feed goes silent
  in market hours, and missed 5-min candles are replayed after a reconnect.
"""

import asyncio
import json
import ssl
import struct
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import certifi
import websockets
from fastapi import APIRouter, HTTPException, WebSocket
from websockets import InvalidStatusCode

from app.auth import decode_token
from app.config import config
from app.core import instruments as core_instruments
from app.core.alerts import async_dispatch_alert
from app.core.instruments import get_security_id_multi
from app.core.tick_store import latest_ticks, save_tick
from research.utils.market_calendar import _IST, is_in_session, is_trading_day

router = APIRouter()

MAX_RECONNECT_DELAY = 60.0   # seconds
BASE_RECONNECT_DELAY = 1.0   # seconds
HEARTBEAT_TIMEOUT = 60.0     # seconds without any packet -> reconnect
BINARY_TICK_TIMEOUT = 10.0   # seconds without a valid binary tick -> reconnect
CHUNK_SIZE = 100             # Dhan limit per subscribe request
CHUNK_PAUSE = 0.05           # seconds between chunk sends
# 17 = Quote mode: carries cumulative day volume (15 = Ticker has none, which
# left every candle with volume=0 and broke volume-based strategies)
SUBSCRIBE_REQUEST_CODE = 17

# Runtime state (admin /health and the watchdog test read these)
_subscribe_symbols: List[str] = []
_running = False
_ws: Optional[websockets.WebSocketClientProtocol] = None
_reconnect_count = 0
last_ws_msg_time = time.time()
last_binary_tick_time = time.time()
stale_feed_active = False
_outage_alerted = False      # one alert per outage; cleared when a real tick arrives
_redis_warn_last = 0.0       # Redis write failures warn at most once a minute

# Bounded queue decouples strategy work from the WS read loop
tick_queue = asyncio.Queue(maxsize=5000)

# Last cumulative day volume per security id, for per-tick volume deltas
_last_cum_volume: Dict[int, int] = {}


def volume_delta(sid: int, cum_volume: Optional[int]) -> int:
    """
    Dhan's cumulative day volume -> volume traded since the last tick. The first
    packet for a sid only sets the baseline (so the whole day's volume isn't
    dumped into one candle); a drop (new session) resets it.
    """
    if cum_volume is None or cum_volume < 0:
        return 0
    prev = _last_cum_volume.get(sid)
    _last_cum_volume[sid] = cum_volume
    if prev is None or cum_volume < prev:
        return 0
    return cum_volume - prev


def build_ws_url() -> str:
    base = config.DHAN_WS_URL or "wss://api-feed.dhan.co"
    return f"{base}?version=2&token={config.ACCESS_TOKEN}&clientId={config.CLIENT_ID}&authType=2"


async def subscribe_sids(ws, sids: List[int]):
    for i in range(0, len(sids), CHUNK_SIZE):
        chunk = sids[i:i + CHUNK_SIZE]
        msg = {
            "RequestCode": SUBSCRIBE_REQUEST_CODE,
            "InstrumentCount": len(chunk),
            "InstrumentList": [{"ExchangeSegment": "NSE_EQ", "SecurityId": str(sid)} for sid in chunk],
        }
        try:
            await ws.send(json.dumps(msg))
            await asyncio.sleep(CHUNK_PAUSE)
        except Exception as e:
            print(f"⚠️ Error subscribing chunk: {e}")
            break


def parse_binary_message(b: bytes):
    """Dhan binary packet -> dict with security_id, ltp, time (+cum_volume), or None."""
    try:
        if not b or len(b) < 8:
            return None
        code = b[0]
        security_id = struct.unpack("<i", b[4:8])[0]
        ltp = struct.unpack("<f", b[8:12])[0] if len(b) >= 12 else None

        if code == 2 and len(b) >= 16:   # Ticker: LTP f32, LTT i32
            return {"type": "ticker", "security_id": security_id, "ltp": ltp,
                    "time": struct.unpack("<i", b[12:16])[0]}
        if code == 6 and len(b) >= 16:   # Prev close
            return {"type": "prev_close", "security_id": security_id, "prev_close": ltp}
        # Quote (4) and Full (8): LTP f32 [8:12], LTQ i16 [12:14], LTT i32 [14:18],
        # ATP f32 [18:22], cumulative day volume i32 [22:26]
        if (code == 4 and len(b) >= 50) or (code == 8 and len(b) >= 18):
            parsed = {"type": "quote" if code == 4 else "full", "security_id": security_id,
                      "ltp": ltp, "time": struct.unpack("<i", b[14:18])[0]}
            if len(b) >= 26:
                parsed["cum_volume"] = struct.unpack("<i", b[22:26])[0]
            return parsed
        return None
    except Exception:
        return None


async def ws_watchdog():
    global stale_feed_active, _outage_alerted
    while _running:
        await asyncio.sleep(1)
        now = time.time()
        # Dhan is silent outside market hours; checking then just reconnects all night.
        now_ist = datetime.now(_IST)
        is_market_open = config.WATCHDOG_DEBUG_MODE or (
            is_trading_day(now_ist.date()) and is_in_session(now_ist))

        is_connection_stale = is_market_open and now - last_ws_msg_time > HEARTBEAT_TIMEOUT
        is_binary_stale = is_market_open and now - last_binary_tick_time > BINARY_TICK_TIMEOUT
        if not (_ws and (is_connection_stale or is_binary_stale) and not stale_feed_active):
            continue

        reason = "HEARTBEAT_TIMEOUT" if is_connection_stale else "BINARY_TICK_SILENCE"
        limit = HEARTBEAT_TIMEOUT if is_connection_stale else BINARY_TICK_TIMEOUT
        print(f"🚨 STALE_FEED BREAKER TRIPPED: {reason} (> {limit}s). Forcing reconnect.", flush=True)
        stale_feed_active = True
        if not _outage_alerted:
            _outage_alerted = True
            asyncio.create_task(async_dispatch_alert(
                level="CRITICAL",
                title=f"STALE_FEED: {reason}",
                message=f"No data received from Dhan in {limit} seconds. Reconnecting; "
                        f"no further alert until data comes back."))
        try:
            await _ws.close()   # the reconnect loop takes it from here
        except Exception:
            pass


async def heal_historical_gap():
    """
    After a reconnect, fetch the 5-min candles missed since the runner's last
    bucket from Dhan REST and replay them in time order to restore strategy state.
    """
    from app.engines.paper_strategy_runner import MOMENTUM5_UNIVERSE, get_runner
    from research.services.historical_data_service import fetch_intraday

    now_ist = datetime.now(_IST)
    if not is_in_session(now_ist):
        print("Market closed. No gap healing needed.")
        return
    session_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)

    runner = get_runner()
    last_bucket = runner._aggregator.last_bucket
    fetch_from = session_start if last_bucket is None or last_bucket < session_start \
        else last_bucket + timedelta(minutes=5)
    fetch_to = now_ist.replace(minute=now_ist.minute // 5 * 5, second=0, microsecond=0)
    if fetch_from >= fetch_to:
        print("✅ No complete 5-min candles missed. Resuming...")
        return

    print(f"Healing gap {fetch_from:%H:%M} -> {fetch_to:%H:%M} IST")
    candles = []
    for sym, sid in get_security_id_multi(MOMENTUM5_UNIVERSE).items():
        try:
            # blocking REST call: run in a thread to keep the WS loop alive
            candles += await asyncio.to_thread(fetch_intraday, str(sid), sym, 5, fetch_from, fetch_to)
        except Exception as e:
            print(f"WARN Failed to fetch healing candles for {sym}: {e}")

    candles.sort(key=lambda c: c["timestamp"])   # chronological across all symbols
    for c in candles:
        runner.feed_historical_candle(c["symbol"], c)
    print(f"OK replayed {len(candles)} candles.")


def _on_tick(parsed: dict):
    global _redis_warn_last
    sid, ltp = parsed["security_id"], float(parsed["ltp"])
    sym = core_instruments.sid_to_symbol.get(sid, str(sid)).upper()
    latest_ticks[sid] = {"symbol": sym, "ltp": ltp, "time": parsed["time"]}
    try:
        save_tick(sym, ltp)
    except Exception as e:
        if time.time() - _redis_warn_last > 60:
            print(f"⚠ tick_store Redis write failed (suppressing for 60s): {e}")
            _redis_warn_last = time.time()
    try:
        tick_queue.put_nowait((sym, ltp, volume_delta(sid, parsed.get("cum_volume")), None))
    except asyncio.QueueFull:
        print(f"⚠️ CRITICAL: Tick Queue Full! Dropping tick for {sym}")


async def _connect_and_listen():
    global _running, _ws, last_ws_msg_time, last_binary_tick_time, stale_feed_active
    global _reconnect_count, _outage_alerted
    backoff = BASE_RECONNECT_DELAY
    _running = True
    asyncio.create_task(ws_watchdog())
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    while _running:
        print(f"WS Connecting to Dhan: {config.DHAN_WS_URL}...")   # no token in logs
        disconnect_duration = time.time() - last_ws_msg_time
        try:
            _reconnect_count += 1
            async with websockets.connect(build_ws_url(), ping_interval=20, ping_timeout=10,
                                          ssl=ssl_context) as ws:
                _ws = ws
                # Fresh grace period; otherwise the watchdog sees the old timestamp
                # and closes this connection during gap healing, before we subscribe.
                last_ws_msg_time = last_binary_tick_time = time.time()
                print("✅ Dhan WebSocket Connected", flush=True)

                # Heal after a watchdog trip, a >15 s gap, or the process's first connect
                if stale_feed_active or disconnect_duration > 15 or _reconnect_count == 1:
                    await heal_historical_gap()
                stale_feed_active = False

                print(f"📋 Subscribing to {len(_subscribe_symbols)} symbols")
                sids = {int(sid) for sid in get_security_id_multi(_subscribe_symbols).values()}
                await subscribe_sids(ws, list(sids))
                last_ws_msg_time = last_binary_tick_time = time.time()

                async for msg in ws:
                    last_ws_msg_time = time.time()
                    if not isinstance(msg, (bytes, bytearray)):
                        print(f"Dhan WS text message: {str(msg)[:300]}", flush=True)
                        continue
                    # Code 50 = Dhan disconnect packet; bytes 8-9 carry the reason code
                    if len(msg) >= 10 and msg[0] == 50:
                        reason_code = struct.unpack("<h", bytes(msg[8:10]))[0]
                        print(f"⛔ Dhan sent disconnect packet, reason code {reason_code}", flush=True)
                        continue
                    parsed = parse_binary_message(bytes(msg))
                    if parsed and parsed.get("ltp") is not None:
                        last_binary_tick_time = time.time()
                        backoff = BASE_RECONNECT_DELAY   # only real data proves the feed works
                        _outage_alerted = False
                        if not stale_feed_active:        # mid-healing: don't feed out of order
                            _on_tick(parsed)

                # Dhan closed the socket cleanly: say why, and back off so we don't hit 429
                print(f"🔌 Dhan closed the feed: code={ws.close_code} reason={ws.close_reason!r}", flush=True)
        except InvalidStatusCode as e:
            print(f"⚠️ Dhan WS Error: server rejected WebSocket connection: HTTP {e.status_code}")
            if e.status_code == 429:
                backoff = max(backoff, 5.0)
        except Exception as e:
            print(f"⚠️ Dhan WS Error: {e}")
        finally:
            _ws = None

        await asyncio.sleep(backoff + 1)
        backoff = min(MAX_RECONNECT_DELAY, backoff * 1.5)


async def fetch_initial_data():
    """REST LTP snapshot so the app shows prices before the first tick (or when closed)."""
    from app.services.dhan_service import get_ltp_batch
    prices = await asyncio.to_thread(get_ltp_batch, _subscribe_symbols.copy())
    sids = get_security_id_multi(list(prices))
    for sym, price in prices.items():
        if price and sym in sids:
            latest_ticks[int(sids[sym])] = {"symbol": sym, "ltp": price, "time": 0}
    print(f"🌍 Initial snapshot loaded for {sum(1 for p in prices.values() if p)} instruments.")


async def _tick_processor():
    """Feeds queued ticks to the strategy runner one at a time, in a worker thread."""
    from app.engines.paper_strategy_runner import get_runner
    while _running:
        try:
            sym, ltp, vol, tick_time = await tick_queue.get()
            try:
                q_size = tick_queue.qsize()
                if q_size > 100 and q_size % 100 == 0:
                    print(f"⚠️ Tick Processor Lagging. Queue depth: {q_size}")
                await asyncio.to_thread(get_runner().feed_tick, sym, ltp, vol, tick_time)
            finally:
                tick_queue.task_done()
        except Exception as e:
            print(f"⚠️ Tick Processor Global Error: {e}")
            await asyncio.sleep(1)


async def start_ws_background_task():
    asyncio.create_task(_connect_and_listen())
    asyncio.create_task(_tick_processor())
    asyncio.create_task(fetch_initial_data())


def subscribe_symbols(symbols: List[str]) -> List[str]:
    """Add symbols to the list subscribed on every (re)connect; returns the new ones."""
    new = [s for s in dict.fromkeys(symbols) if s not in _subscribe_symbols]
    _subscribe_symbols.extend(new)
    return new


async def subscribe_dynamic_symbols(symbols: List[str]):
    """subscribe_symbols, plus subscribe right away if the feed is connected."""
    new = subscribe_symbols(symbols)
    if new and _ws:
        try:
            sids = [int(sid) for sid in get_security_id_multi(new).values()]
            print(f"⚡ Dynamic Subscribe: {new} -> {sids}")
            await subscribe_sids(_ws, sids)
        except Exception as e:
            print(f"⚠️ Error in dynamic subscribe: {e}")


# The app connects here (?token=JWT); every cached tick is pushed every 500 ms.
@router.websocket("/ws/market")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    try:
        decode_token(token or "")
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            # ~20-25 watchlist symbols; fine to send them all each time.
            if latest_ticks:
                await websocket.send_text(json.dumps(
                    [{"symbol": d["symbol"], "LTP": d["ltp"]} for d in list(latest_ticks.values())]))
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f"❌ Flutter Client Disconnected: {e}")
