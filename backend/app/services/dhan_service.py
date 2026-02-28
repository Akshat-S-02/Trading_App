# # import requests
# # import time
# # import difflib
# # import os
# # import pandas as pd
# # import re

# # # === Live Dhan Credentials ===
# # # ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"


# # # Put your credentials here (or load from env vars)
# # CLIENT_ID = "1109121898"   # <-- replace if needed
# # ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJwX2lwIjoiIiwic19pcCI6IiIsImlzcyI6ImRoYW4iLCJwYXJ0bmVySWQiOiIiLCJleHAiOjE3NjI3NzgxMzUsImlhdCI6MTc2MjY5MTczNSwidG9rZW5Db25zdW1lclR5cGUiOiJTRUxGIiwid2ViaG9va1VybCI6Imh0dHA6Ly8xMjcuMC4wLjE6ODAwMC9kaGFuL2NhbGxiYWNrIiwiZGhhbkNsaWVudElkIjoiMTEwOTEyMTg5OCJ9.HCZKDfs3x15YIZVEU6Ql4cMArJsP5eRpTTKhWmEBPY1yDlifF3jte1IMbKVY5QjLRXxeFZKXaToCQwn1EkRe3Q"
# # # Use sandbox BASE_URL while developing (switch to https://api.dhan.co for production)
# # BASE_URL = "https://api.dhan.co"  # for prod
# # # BASE_URL = "https://sandbox.dhan.co"  # uncomment for sandbox

# # # ==================== CONFIG ====================

# # # CLIENT_ID = "1109121898"
# # # ACCESS_TOKEN = "<YOUR_ACCESS_TOKEN>"  # Replace
# # # BASE_URL = "https://api.dhan.co"  # Use sandbox.dhan.co if testing

# # HEADERS = {
# #     "client-id": CLIENT_ID,
# #     "access-token": ACCESS_TOKEN,
# #     "Content-Type": "application/json",
# #     "Accept": "application/json"
# # }

# # # Cache for instruments (loaded once)
# # INSTRUMENT_CACHE = []

# # # ==================== HELPER FUNCS ====================

# # def _log(msg: str):
# #     print(msg)



# # INSTRUMENT_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
# # LOCAL_INSTRUMENT_PATH = os.path.join(os.path.dirname(__file__), "../data/instruments.csv")

# # # def download_instruments_csv():
# # #     """Download the Dhan instrument master CSV if not already present"""
# # #     os.makedirs(os.path.dirname(LOCAL_INSTRUMENT_PATH), exist_ok=True)  # ✅ ensure /data folder exists
# # #     print("⬇️  Downloading Dhan instrument master CSV...")
# # #     resp = requests.get(INSTRUMENT_CSV_URL, timeout=30)
# # #     resp.raise_for_status()
# # #     with open(LOCAL_INSTRUMENT_PATH, "wb") as f:
# # #         f.write(resp.content)
# # #     print("✅ Downloaded instrument master CSV.")

# # def download_instruments_csv(exchange="NSE_EQ"):
# #     """Download Dhan instrument master for a specific exchange (e.g., NSE_EQ, BSE_EQ)."""
# #     url = f"https://api.dhan.co/v2/instruments/{exchange}"
# #     headers = {
# #         "client-id": CLIENT_ID,
# #         "access-token": ACCESS_TOKEN,
# #     }
# #     print(f"⬇️  Downloading Dhan instrument master for {exchange}...")
# #     resp = requests.get(url, headers=headers, timeout=30)

# #     if resp.status_code == 200:
# #         os.makedirs(DATA_DIR, exist_ok=True)
# #         with open(LOCAL_INSTRUMENT_PATH, "wb") as f:
# #             f.write(resp.content)
# #         print(f"✅ Downloaded instrument master CSV for {exchange}.")
# #     else:
# #         print(f"❌ Failed to load instruments: {resp.status_code} -> {resp.text}")


# # def load_instruments(force_reload=False):
# #     global INSTRUMENT_CACHE
# #     if INSTRUMENT_CACHE and not force_reload:
# #         return INSTRUMENT_CACHE

# #     if not os.path.exists(LOCAL_INSTRUMENT_PATH) or force_reload:
# #         download_instruments_csv()

# #     df = pd.read_csv(LOCAL_INSTRUMENT_PATH)
# #     INSTRUMENT_CACHE = df.to_dict(orient="records")
# #     print(f"✅ Loaded {len(INSTRUMENT_CACHE)} instruments from CSV.")
# #     return INSTRUMENT_CACHE


# # def find_best_instrument(query: str):
# #     """
# #     Fuzzy match user input (like 'LIC', 'REL', 'TRIDEN') to Dhan instrument master.
# #     Prefers NSE_EQ segment.
# #     """
# #     if not INSTRUMENT_CACHE:
# #         load_instruments()

# #     query = query.upper().strip()
# #     best_match = None
# #     best_score = 0.0

# #     for inst in INSTRUMENT_CACHE:
# #         symbol = inst.get("symbol", "").upper()
# #         name = inst.get("securityName", "").upper()
# #         exch = inst.get("exchangeSegment", "")
# #         instrument = inst.get("instrument", "")
# #         if not symbol or not instrument:
# #             continue

# #         # prefer NSE_EQ segment
# #         if exch != "NSE_EQ":
# #             continue

# #         # compute fuzzy similarity
# #         score = difflib.SequenceMatcher(None, query, symbol).ratio()
# #         if score > best_score:
# #             best_match = instrument
# #             best_score = score

# #         # if exact or very close match found
# #         if query == symbol or score > 0.95:
# #             return instrument

# #     if best_match:
# #         _log(f"🔍 Fuzzy matched '{query}' → '{best_match}' (score={best_score:.2f})")
# #         return best_match

# #     _log(f"⚠️ No fuzzy match found for '{query}'")
# #     return None




# # def normalize_symbol(s):
# #     """Normalize stock name for fuzzy comparison"""
# #     return re.sub(r'[^A-Z0-9]', '', str(s).upper())

# # def find_instrument(symbol: str, exchange="NSE"):
# #     """Find the Dhan trading instrument symbol for a given stock (fuzzy smart match)."""
# #     symbol_norm = normalize_symbol(symbol)
# #     instruments = load_instruments()

# #     candidates = []
# #     for inst in instruments:
# #         name = normalize_symbol(inst.get("SM_SYMBOL_NAME", ""))
# #         trading_symbol = normalize_symbol(inst.get("SEM_TRADING_SYMBOL", ""))
# #         exch = str(inst.get("SEM_EXM_EXCH_ID", "")).strip().upper()
# #         instr_type = str(inst.get("SEM_EXCH_INSTRUMENT_TYPE", "")).strip().upper()

# #         # only consider equities for NSE
# #         if exch == exchange and "EQ" in instr_type:
# #             if symbol_norm == name or symbol_norm == trading_symbol:
# #                 # strong match
# #                 trading_symbol_real = str(inst.get("SEM_TRADING_SYMBOL", "")).strip()
# #                 return f"{exchange}_EQ:{trading_symbol_real}"
# #             elif symbol_norm in name or symbol_norm in trading_symbol:
# #                 candidates.append(inst)

# #     # fallback to the first partial match if any
# #     if candidates:
# #         inst = candidates[0]
# #         trading_symbol_real = str(inst.get("SEM_TRADING_SYMBOL", "")).strip()
# #         return f"{exchange}_EQ:{trading_symbol_real}"

# #     print(f"⚠️ No instrument found for {symbol}")
# #     return None


# # def get_ltp_for(instruments):
# #     """
# #     Request LTP for one or more valid instruments.
# #     """
# #     url = f"{BASE_URL}/v2/marketfeed/ltp"
# #     payload = {"symbols": instruments}
# #     try:
# #         resp = requests.post(url, json=payload, headers=HEADERS, timeout=10)
# #         _log(f"LTP API {resp.status_code} -> {resp.text[:200]}")
# #         if resp.status_code == 200:
# #             data = resp.json().get("data", [])
# #             if isinstance(data, list) and len(data) > 0:
# #                 result = {}
# #                 for item in data:
# #                     sym = item.get("symbol", "")
# #                     ltp = float(item.get("LTP", 0.0))
# #                     result[sym] = {"symbol": sym, "price": ltp, "raw": item}
# #                 return result
# #         else:
# #             _log(f"⚠️ Bad response: {resp.text}")
# #     except Exception as e:
# #         _log(f"❌ Error in get_ltp_for: {e}")

# #     return {}


# # def get_live_price(symbol: str):
# #     """
# #     Main public function: fuzzy-match symbol -> instrument -> LTP.
# #     """
# #     try:
# #         instrument = find_best_instrument(symbol)
# #         if not instrument:
# #             return {"symbol": symbol, "price": 0.0, "error": "Symbol not found in Dhan master"}

# #         data = get_ltp_for([instrument])
# #         if instrument in data:
# #             return {"symbol": symbol, "instrument": instrument, "price": data[instrument]["price"]}
# #         else:
# #             return {"symbol": symbol, "instrument": instrument, "price": 0.0, "error": "No LTP in response"}
# #     except Exception as e:
# #         _log(f"❌ Exception in get_live_price({symbol}): {e}")
# #         return {"symbol": symbol, "price": 0.0, "error": str(e)}


# # # --- Optional placeholders to keep imports consistent ---

# # def place_order(symbol: str, qty: int, order_type: str = "buy"):
# #     _log(f"🧩 Simulated {order_type.upper()} order for {qty}x {symbol}")
# #     return {"status": "simulated", "symbol": symbol, "qty": qty, "order_type": order_type}


# # def get_portfolio():
# #     _log("🔍 Returning mock portfolio (placeholder)")
# #     return {
# #         "holdings": [
# #             {"symbol": "RELIANCE", "quantity": 10, "avg_price": 2450.0, "current_price": 2500.0},
# #             {"symbol": "HDFCBANK", "quantity": 5, "avg_price": 1510.0, "current_price": 1525.0},
# #         ]
# #     }


# import pandas as pd
# import os
# import requests
# from app.config import config
# # from app.websocket.market_ws import sid_to_symbol
# # from app.core.instruments import get_security_id
# from app.core.instruments import symbol_to_sid




# # ---------------------------
# # Load Instrument Master CSV
# # ---------------------------

# CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api-scrip-master.csv")


# # Global dataframe storage
# df = None

# # def load_instruments():
# #     global df

# #     print("📦 Loading Dhan instrument master list...")

# #     try:
# #         df = pd.read_csv(CSV_PATH)

# #         # Normalize columns
# #         df.columns = [c.strip().lower() for c in df.columns]

# #         # Ensure required columns exist
# #         required = ["sem_trading_symbol", "sm_symbol_name"]
# #         for col in required:
# #             if col not in df.columns:
# #                 raise ValueError(f"Missing column in CSV: {col}")

# #         reliance = df[(df["sem_trading_symbol"] == "RELIANCE")]
# #         print("test ",reliance)
# #         # Clean values
# #         df["sem_trading_symbol"] = df["sem_trading_symbol"].astype(str).str.upper().str.strip()
# #         df["sm_symbol_name"] = df["sm_symbol_name"].astype(str).str.upper().str.strip()

# #         # print(df.head())
        

# #         print(f"✅ Loaded {len(df)} instruments.")

# #     except Exception as e:
# #         print("❌ Failed to load CSV:", e)
# #         df = pd.DataFrame()


# # def load_instruments():
# #     global df

# #     print("📦 Loading Dhan instrument master list...")

# #     try:
# #         # Load CSV first
# #         df = pd.read_csv(CSV_PATH)

# #         # Normalize columns to lowercase
# #         df.columns = [c.strip().lower() for c in df.columns]

# #         # Clean & uppercase values
# #         df["sem_trading_symbol"] = df["sem_trading_symbol"].astype(str).str.upper().str.strip()
# #         df["sm_symbol_name"] = df["sm_symbol_name"].astype(str).str.upper().str.strip()

# #         # DEBUG: find reliance
# #         reliance = df[
# #             (df["sem_trading_symbol"] == "RELIANCE") |
# #             (df["sm_symbol_name"].str.contains("RELIANCE", na=False))
# #         ]
# #         print("🔍 RELIANCE rows found:\n", reliance)

# #         # --------------------------------------
# #         #  Build sid_to_symbol MAP ***AFTER df loaded ***
# #         # --------------------------------------
# #         sid_to_symbol.clear()
# #         for _, row in df.iterrows():
# #             try:
# #                 sid = int(row["sem_smst_security_id"])
# #                 symbol = str(row["sem_trading_symbol"]).strip().upper()
# #                 sid_to_symbol[sid] = symbol
# #             except:
# #                 continue

# #         print(f"🔗 Mapped {len(sid_to_symbol)} SecurityIds → Symbols")
# #         print(f"✅ Loaded {len(df)} instruments.")

# #     except Exception as e:
# #         print("❌ Failed to load CSV:", e)
# #         df = pd.DataFrame()


# # load_instruments()


# # # ---------------------------
# # # Instrument Finder
# # # ---------------------------

# def find_instrument(symbol: str) -> dict | None:
#     """
#     Find instrument using your CSV.
#     Supports input:
#         RELIANCE
#         NSE_EQ:RELIANCE
#         reliance
#     """
#     if df is None or df.empty:
#         print("⚠ CSV not loaded.")
#         return None

#     if not symbol:
#         return None

#     s = symbol.strip().upper()

#     # Remove exchange prefix: NSE_EQ:RELIANCE → RELIANCE
#     if ":" in s:
#         s = s.split(":", 1)[1]

#     # 1) Exact trading symbol match
#     row = df[df['sem_trading_symbol'] == s]
#     if not row.empty:
#         return row.iloc[0].to_dict()

#     # 2) Match by SM_SYMBOL_NAME (more stable)
#     row = df[df['sm_symbol_name'] == s]
#     if not row.empty:
#         return row.iloc[0].to_dict()

#     print("⚠ Instrument not found:", symbol)
#     return None


# # ---------------------------
# # LTP via REST API (no websocket)
# # ---------------------------

# def get_ltp(symbol: str) -> float:
#     """
#     Fetch LTP using Dhan Quotes API.
#     Works WITHOUT WebSocket plan.
#     """
#     try:
#         url = f"{config.DHAN_REST_BASE}/v2/marketfeed/quotes"

#         payload = {
#             "symbols": [f"NSE_EQ:{symbol.upper()}"]
#         }

#         headers = {
#             "client-id": config.DHAN_CLIENT_ID,
#             "access-token": config.DHAN_API_SECRET,  # Using secret token style
#             "Content-Type": "application/json"
#         }

#         resp = requests.post(url, json=payload, headers=headers, timeout=10)

#         data = resp.json()

#         if data.get("status") != "success":
#             return 0.0

#         quotes = data.get("data", {})
#         for k, v in quotes.items():
#             if "LTP" in v:
#                 return float(v["LTP"])

#         return 0.0

#     except Exception as e:
#         print("❌ LTP fetch error:", e)
#         return 0.0

# def get_live_price(symbol: str) -> dict:
#     """
#     Backward-compatible wrapper returning structured price data
#     for WebSocket and REST consumers.
#     """
#     try:
#         inst = find_instrument(symbol)
#         if not inst:
#             return {
#                 "symbol": symbol,
#                 "price": 0.0,
#                 "error": "Instrument not found"
#             }

#         trading_symbol = inst.get("sem_trading_symbol", symbol.upper())
#         ltp = get_ltp(trading_symbol)

#         return {
#             "symbol": trading_symbol,
#             "price": ltp,
#             "success": True
#         }

#     except Exception as e:
#         return {
#             "symbol": symbol,
#             "price": 0.0,
#             "error": str(e)
#         }

# async def refresh_access_token():
#     # call Dhan token endpoint & update config.ACCESS_TOKEN (or write to env)
#     # MUST be async or return immediately
#     pass


# # def get_security_id(symbol: str) -> str | None:
# #     global df
# #     if df is None or df.empty:
# #         print("⚠ CSV not loaded.")
# #         return None

# #     s = symbol.strip().upper()

# #     # Search in trading symbol if present
# #     rows = df[df["sem_trading_symbol"].str.upper() == s]

# #     # If RELIANCE is considered "RELIANCE INDUSTRIES LTD"
# #     if rows.empty:
# #         rows = df[df["sm_symbol_name"].str.contains(s, case=False, na=False)]

# #     if rows.empty:
# #         print("⚠ No rows found for", symbol)
# #         return None

# #     # Prefer NSE equity row
# #     nse_eq = rows[
# #         (rows["sem_exm_exch_id"] == "NSE") &
# #         (rows["sem_exch_instrument_type"].str.upper().isin(["EQUITY", "EQ", "ES"]))
# #     ]

# #     if not nse_eq.empty:
# #         return str(nse_eq.iloc[0]["sem_smst_security_id"])

# #     # fallback: BSE
# #     bse_eq = rows[
# #         (rows["sem_exm_exch_id"] == "BSE") &
# #         (rows["sem_exch_instrument_type"].str.upper().isin(["EQUITY", "EQ", "ES"]))
# #     ]

# #     if not bse_eq.empty:
# #         return str(bse_eq.iloc[0]["sem_smst_security_id"])

# #     print("⚠ No valid SecurityId for", symbol)
# #     return None


# # def get_security_id_multi(symbols: list[str]) -> list[dict]:
# #     """
# #     Returns a list of dicts:
# #     [
# #         {"ExchangeSegment": "NSE_EQ", "SecurityId": "2885"},
# #         ...
# #     ]
# #     """
# #     out = []

# #     for sym in symbols:
# #         s = sym.strip().upper()

# #         row = df[
# #             (df["sem_trading_symbol"] == s) &
# #             (df["sem_exm_exch_id"] == "NSE") &
# #             (df["sem_exch_instrument_type"] == "ES")  # equities
# #         ]

# #         if row.empty:
# #             print(f"⚠ No SecurityId for: {sym}")
# #             continue

# #         sec_id = str(row.iloc[0]["sem_smst_security_id"])
# #         out.append({"ExchangeSegment": "NSE_EQ", "SecurityId": sec_id})

# #     return out


import pandas as pd
import os
import time
import requests
from app.config import config
from app.core.instruments import symbol_to_sid, sid_to_symbol



# ---------------------------
# Load Instrument Master CSV
# ---------------------------

CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "api-scrip-master.csv"
)

df = None


def load_instruments():
    """Load master CSV only once (already handled in app.core.instruments)."""
    global df
    if df is not None:
        return df

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Instrument CSV missing at {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    df.columns = [c.strip().lower() for c in df.columns]

    # Normalize text fields
    df["sem_trading_symbol"] = df["sem_trading_symbol"].astype(str).str.upper().str.strip()
    df["sm_symbol_name"] = df["sm_symbol_name"].astype(str).str.upper().str.strip()

    print(f"📦 dhan_service loaded {len(df)} instruments")
    return df


def search_instruments(query: str, limit: int = 20) -> list[dict]:
    """
    Search instruments by symbol or name.
    Returns list of dicts.
    """
    global df
    load_instruments()
    
    if not query:
        return []
    
    q = query.strip().upper()
    
    # Filter: matches symbol OR name
    # Prefer NSE EQ
    mask = (
        (df["sem_trading_symbol"].str.contains(q, na=False)) | 
        (df["sm_symbol_name"].str.contains(q, na=False))
    ) & (df["sem_exm_exch_id"] == "NSE") & (df["sem_series"] == "EQ")
    
    # Sort by exact match first? 
    # For now just take top N
    results = df[mask].head(limit)
    
    out = []
    for _, row in results.iterrows():
        out.append({
            "symbol": row["sem_trading_symbol"],
            "name": row["sm_symbol_name"],
            "exchange": row["sem_exm_exch_id"],
            "security_id": row["sem_smst_security_id"]
        })
        
    return out


# ---------------------------
# Instrument Finder
# ---------------------------

def find_instrument(symbol: str) -> dict | None:
    """
    Look up full instrument row from the CSV.
    Supports:
       RELIANCE
       NSE_EQ:RELIANCE
       reliance
    """
    global df
    load_instruments()

    if not symbol:
        return None

    s = symbol.strip().upper()

    # Remove exchange prefix
    if ":" in s:
        s = s.split(":", 1)[1]

    # Remove .NS suffix if present (Frontend sends .NS)
    if s.endswith(".NS"):
        s = s[:-3]

    # 1) Exact match on trading symbol
    row = df[df["sem_trading_symbol"] == s]
    if not row.empty:
        return row.iloc[0].to_dict()

    # 2) Match full security name
    row = df[df["sm_symbol_name"] == s]
    if not row.empty:
        return row.iloc[0].to_dict()

    # 3) Partial match fallback
    row = df[df["sm_symbol_name"].str.contains(s, case=False, na=False)]
    if not row.empty:
        return row.iloc[0].to_dict()

    print(f"⚠ Instrument not found: {symbol}")
    return None


# ---------------------------
# REST API — Fetch LTP (no WebSocket required)
# ---------------------------

# Per-symbol REST cooldown: don't call Dhan REST more than once per 10s per symbol
_last_rest_call: dict[str, float] = {}
REST_COOLDOWN_S = 10.0


def get_ltp(symbol: str) -> float:
    """
    Fetch LTP for a single symbol via Dhan REST `/v2/marketfeed/ltp`.

    Protections:
      - 10-second per-symbol cooldown (avoids 429s on rapid polls).
      - Gracefully returns 0.0 when market is closed (empty NSE_EQ is normal
        outside 09:15–15:30 IST — not an error).
    """
    now = time.time()
    if now - _last_rest_call.get(symbol, 0) < REST_COOLDOWN_S:
        return 0.0   # still in cooldown — caller should use WebSocket cache
    _last_rest_call[symbol] = now

    try:
        base = config.DHAN_REST_BASE.rstrip("/")
        url  = f"{base}/v2/marketfeed/ltp"

        load_instruments()
        inst = find_instrument(symbol)
        if not inst:
            return 0.0

        sid = int(inst.get("sem_smst_security_id", 0))
        if sid == 0:
            return 0.0

        payload = {"NSE_EQ": [sid]}
        headers = {
            "client-id":    config.CLIENT_ID,
            "access-token": config.ACCESS_TOKEN,
            "Content-Type": "application/json",
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=10)

        if resp.status_code == 429:
            print(f"⚠️  Dhan REST rate-limited (429) for {symbol}. Backing off.")
            _last_rest_call[symbol] = now + 30   # extra 30s penalty
            return 0.0

        if resp.status_code != 200:
            print(f"❌ LTP REST HTTP {resp.status_code} for {symbol}: {resp.text[:200]}")
            return 0.0

        data = resp.json()
        nse_data = data.get("data", {}).get("NSE_EQ", {})
        for _, info in nse_data.items():
            price = info.get("last_price") or info.get("LTP")
            if price is not None:
                return float(price)

        # Empty NSE_EQ is normal when market is closed — no log spam
        return 0.0

    except Exception as e:
        print(f"❌ LTP REST error for {symbol}: {e}")
        return 0.0


def get_ltp_batch(symbols: list[str]) -> dict[str, float]:
    """
    Fetch LTP for multiple symbols in a SINGLE Dhan REST call.
    Returns {symbol: price} dict. Symbols with no data get price 0.0.
    Use this instead of calling get_ltp() in a loop.
    """
    load_instruments()
    sid_to_sym: dict[int, str] = {}

    for sym in symbols:
        inst = find_instrument(sym)
        if not inst:
            continue
        sid = int(inst.get("sem_smst_security_id", 0))
        if sid:
            sid_to_sym[sid] = sym.upper()

    if not sid_to_sym:
        return {s: 0.0 for s in symbols}

    try:
        base    = config.DHAN_REST_BASE.rstrip("/")
        url     = f"{base}/v2/marketfeed/ltp"
        payload = {"NSE_EQ": list(sid_to_sym.keys())}
        headers = {
            "client-id":    config.CLIENT_ID,
            "access-token": config.ACCESS_TOKEN,
            "Content-Type": "application/json",
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code == 429:
            print("⚠️  Dhan REST rate-limited (429) on batch LTP. Backing off.")
            return {s: 0.0 for s in symbols}

        if resp.status_code != 200:
            print(f"❌ Batch LTP REST HTTP {resp.status_code}: {resp.text[:200]}")
            return {s: 0.0 for s in symbols}

        data      = resp.json()
        nse_data  = data.get("data", {}).get("NSE_EQ", {})
        result    = {s: 0.0 for s in symbols}

        for sid_str, info in nse_data.items():
            try:
                sid   = int(sid_str)
                sym   = sid_to_sym.get(sid)
                price = info.get("last_price") or info.get("LTP")
                if sym and price is not None:
                    result[sym] = float(price)
            except Exception:
                continue

        return result

    except Exception as e:
        print(f"❌ Batch LTP REST error: {e}")
        return {s: 0.0 for s in symbols}





# ---------------------------
# Main public method
# ---------------------------

def get_live_price(symbol: str) -> dict:
    """
    Return latest price using REST (not WebSocket).
    Used by app routes.
    """
    try:
        inst = find_instrument(symbol)
        if not inst:
            return {
                "symbol": symbol,
                "price": 0.0,
                "error": "Instrument not found"
            }

        trading_symbol = inst.get("sem_trading_symbol", symbol.upper())
        ltp = get_ltp(trading_symbol)

        return {
            "symbol": trading_symbol,
            "price": ltp,
            "success": True
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "price": 0.0,
            "error": str(e)
        }


# ---------------------------
# Optional placeholder
# ---------------------------

async def refresh_access_token():
    """Stub: implement when enabling auto token renewal."""
    pass
