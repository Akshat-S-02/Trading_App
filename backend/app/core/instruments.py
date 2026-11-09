"""
app/core/instruments.py

Loads Dhan's instrument master CSV once and builds:
  symbol_to_sid : trading symbol -> NSE_EQ security id   (NSE equities ONLY)
  sid_to_symbol : security id -> trading symbol          (NSE_EQ first, others as fallback)
The CSV lists BSE rows before NSE, so the forward map must never fall back to
other segments: an NSE_EQ request with a BSE id hits the wrong instrument.
"""
import os

import pandas as pd

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api-scrip-master.csv")

df = None
symbol_to_sid: dict[str, int] = {}
sid_to_symbol: dict[int, str] = {}


def load_instruments():
    global df, symbol_to_sid, sid_to_symbol
    if not os.path.exists(CSV_PATH):
        print(f"❌ Instrument CSV not found at {CSV_PATH}")
        df = pd.DataFrame()
        return

    df = pd.read_csv(CSV_PATH, low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    for col in ["sem_trading_symbol", "sm_symbol_name", "sem_exm_exch_id", "sem_series", "sem_instrument_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper().str.strip()

    df["sem_smst_security_id"] = pd.to_numeric(df["sem_smst_security_id"], errors="coerce")
    valid = df.dropna(subset=["sem_smst_security_id"])
    is_nse_eq = ((valid["sem_exm_exch_id"] == "NSE")
                 & (valid["sem_instrument_name"] == "EQUITY")
                 & (valid["sem_series"] == "EQ"))
    nse_eq, others = valid[is_nse_eq], valid[~is_nse_eq]

    def pairs(frame):
        return zip(frame["sem_smst_security_id"].astype(int), frame["sem_trading_symbol"])

    # Reverse map: other segments first so NSE_EQ entries overwrite on id clashes
    sid_to_symbol = {sid: sym for sid, sym in pairs(others)}
    sid_to_symbol.update({sid: sym for sid, sym in pairs(nse_eq)})
    symbol_to_sid = {sym: sid for sid, sym in pairs(nse_eq)}

    print(f"✅ Loaded {len(df)} instruments; {len(symbol_to_sid)} NSE_EQ symbols mapped.")


def get_all_instruments():
    return df


def get_security_id(symbol: str):
    """NSE_EQ security id for 'RELIANCE' or 'RELIANCE.NS'; None if not an NSE equity."""
    if not symbol:
        return None
    symbol = symbol.upper().strip()
    if symbol.endswith(".NS"):
        symbol = symbol[:-3]
    return symbol_to_sid.get(symbol)


def get_security_id_multi(symbols: list[str]):
    """{SYMBOL: 'sid'} for the symbols that are NSE equities."""
    result = {}
    for sym in symbols:
        sid = get_security_id(sym)
        if sid:
            result[sym.upper().strip()] = str(sid)
    return result


def resolve_symbol_from_sid(sid: int):
    return sid_to_symbol.get(int(sid))
