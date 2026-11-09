"""
app/services/dhan_service.py

Dhan REST calls: instrument search, LTP snapshots, live order placement and
order lookup. Symbols resolve through app.core.instruments, whose forward map
is NSE_EQ only — the master CSV lists BSE rows first, so a raw CSV lookup would
send BSE security ids to NSE_EQ endpoints.
"""

import time

import requests

from app.config import config
from app.core import instruments


def _headers() -> dict:
    from app.services.token_renewal import current_access_token
    return {
        "client-id": config.CLIENT_ID,
        "access-token": current_access_token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base() -> str:
    return config.DHAN_REST_BASE.rstrip("/")


def _nse_sid(symbol: str) -> int | None:
    """NSE_EQ security id for a bare or '.NS' symbol; loads the master CSV on first use
    (the OutboxWorker process never runs the API startup that loads it)."""
    if not instruments.symbol_to_sid:
        instruments.load_instruments()
    sid = instruments.get_security_id(symbol)
    return int(sid) if sid else None


def _on_401():
    from app.services.token_renewal import handle_401_unauthorized
    handle_401_unauthorized()


# ── Instrument search ─────────────────────────────────────────────────────────

def search_instruments(query: str, limit: int = 20) -> list[dict]:
    """Substring search over NSE equities by trading symbol or company name."""
    q = (query or "").strip().upper()
    if not q:
        return []
    if instruments.df is None or instruments.df.empty:
        instruments.load_instruments()
    df = instruments.df
    if df is None or df.empty:
        return []
    nse_eq = df[(df["sem_exm_exch_id"] == "NSE") & (df["sem_series"] == "EQ")]
    # regex=False: user text like "M&M" or "(" is literal, not a pattern
    mask = (nse_eq["sem_trading_symbol"].str.contains(q, regex=False, na=False)
            | nse_eq["sm_symbol_name"].str.contains(q, regex=False, na=False))
    return [
        {
            "symbol": row["sem_trading_symbol"],
            "name": row["sm_symbol_name"],
            "exchange": row["sem_exm_exch_id"],
            "security_id": row["sem_smst_security_id"],
        }
        for _, row in nse_eq[mask].head(limit).iterrows()
    ]


# ── LTP snapshots (REST) ──────────────────────────────────────────────────────

_last_rest_call: dict[str, float] = {}
REST_COOLDOWN_S = 10.0


def get_ltp(symbol: str) -> float:
    """Single-symbol REST LTP with a 10 s per-symbol cooldown. 0.0 when unknown,
    in cooldown, rate-limited, or the market is closed."""
    now = time.time()
    if now - _last_rest_call.get(symbol, 0) < REST_COOLDOWN_S:
        return 0.0
    _last_rest_call[symbol] = now
    return get_ltp_batch([symbol]).get(symbol.upper(), 0.0)


def get_ltp_batch(symbols: list[str]) -> dict[str, float]:
    """LTP for many symbols in one Dhan call. Unknown / missing symbols get 0.0."""
    result = {s.upper(): 0.0 for s in symbols}
    sid_to_sym = {}
    for sym in symbols:
        sid = _nse_sid(sym)
        if sid:
            sid_to_sym[sid] = sym.upper()
    if not sid_to_sym:
        return result

    try:
        resp = requests.post(f"{_base()}/v2/marketfeed/ltp", json={"NSE_EQ": list(sid_to_sym)},
                             headers=_headers(), timeout=15)
        if resp.status_code == 401:
            _on_401()
            return result
        if resp.status_code != 200:
            print(f"❌ LTP REST HTTP {resp.status_code}: {resp.text[:200]}")
            return result
        for sid_str, info in resp.json().get("data", {}).get("NSE_EQ", {}).items():
            sym = sid_to_sym.get(int(sid_str))
            price = info.get("last_price") or info.get("LTP")
            if sym and price is not None:
                result[sym] = float(price)
    except Exception as e:
        print(f"❌ LTP REST error: {e}")
    return result


# ── Live orders ───────────────────────────────────────────────────────────────

def place_order(symbol: str, qty: int, direction: str, price: float = 0.0,
                order_type: str = "MARKET", correlation_id: str = None) -> dict:
    """
    POST /v2/orders. Returns one of:
      {"status": "success", "order_id": ...}
      {"status": "error", "error": ...}    — Dhan answered and refused
      {"status": "unknown", "error": ...}  — no answer (timeout / connection);
          the order MAY exist at Dhan, so the caller must look it up by
          correlation_id before sending again.
    """
    sid = _nse_sid(symbol)
    if not sid:
        return {"status": "error", "error": f"No NSE_EQ instrument for {symbol}"}

    payload = {
        "dhanClientId": config.CLIENT_ID,
        "correlationId": correlation_id or f"SIG_{int(time.time() * 1000)}",
        "transactionType": "BUY" if direction == "LONG" else "SELL",
        "exchangeSegment": "NSE_EQ",
        "productType": "INTRADAY",
        "orderType": order_type,
        "validity": "DAY",
        "tradingSymbol": symbol.upper(),
        "securityId": str(sid),
        "quantity": qty,
        "disclosedQuantity": 0,
        "price": price if order_type == "LIMIT" else 0.0,
        "triggerPrice": 0.0,
        "afterMarketOrder": False,
    }

    try:
        resp = requests.post(f"{_base()}/v2/orders", json=payload, headers=_headers(), timeout=10)
    except (requests.Timeout, requests.ConnectionError) as e:
        return {"status": "unknown", "error": f"No response from Dhan: {e}"}

    if resp.status_code == 401:
        _on_401()
        return {"status": "error", "error": "Unauthorized (401). Token expired."}
    try:
        data = resp.json()
    except ValueError:
        return {"status": "unknown", "error": f"Unreadable Dhan response HTTP {resp.status_code}"}
    if resp.status_code == 200 and data.get("orderStatus") != "REJECTED":
        return {"status": "success", "order_id": data.get("orderId"), "raw_response": data}
    return {"status": "error", "error": data.get("errorDescription") or data.get("remarks") or str(data)}


def find_order_by_correlation(correlation_id: str) -> dict | None:
    """
    GET /v2/orders/external/{correlation-id}. Returns the newest non-rejected
    order with that tag, None if Dhan has none. Raises on network / HTTP
    failure so the caller never mistakes "couldn't ask" for "not placed".
    """
    resp = requests.get(f"{_base()}/v2/orders/external/{correlation_id}", headers=_headers(), timeout=10)
    if resp.status_code == 404:
        return None
    if resp.status_code == 401:
        _on_401()
    resp.raise_for_status()
    data = resp.json()
    orders = data if isinstance(data, list) else [data]
    live = [o for o in orders if o and o.get("orderId") and o.get("orderStatus") != "REJECTED"]
    return live[-1] if live else None
