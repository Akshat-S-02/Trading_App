"""
research/data/instrument_repository.py

Registry of NIFTY 50 instruments with their Dhan security_id values.
security_id is the canonical key used in all API calls and candle lookups.
symbol is the human-readable name used for display and lookups by name.

Security IDs sourced from api-scrip-master.csv (NSE EQ segment).
"""

from __future__ import annotations
from typing import Optional


# ---------------------------------------------------------------------------
# NIFTY 50 Instruments
# Verified security_id values from Dhan's api-scrip-master.csv (NSE_EQ, EQUITY)
# ---------------------------------------------------------------------------

_NIFTY50 = [
    {"symbol": "RELIANCE",     "security_id": "2885",  "name": "Reliance Industries Ltd"},
    {"symbol": "TCS",          "security_id": "11536", "name": "Tata Consultancy Services Ltd"},
    {"symbol": "HDFCBANK",     "security_id": "1333",  "name": "HDFC Bank Ltd"},
    {"symbol": "BHARTIARTL",   "security_id": "10604", "name": "Bharti Airtel Ltd"},
    {"symbol": "ICICIBANK",    "security_id": "4963",  "name": "ICICI Bank Ltd"},
    {"symbol": "INFOSYS",      "security_id": "1594",  "name": "Infosys Ltd"},
    {"symbol": "SBIN",         "security_id": "3045",  "name": "State Bank of India"},
    {"symbol": "HINDUNILVR",   "security_id": "1394",  "name": "Hindustan Unilever Ltd"},
    {"symbol": "ITC",          "security_id": "1660",  "name": "ITC Ltd"},
    {"symbol": "LT",           "security_id": "11483", "name": "Larsen & Toubro Ltd"},
    {"symbol": "KOTAKBANK",    "security_id": "1922",  "name": "Kotak Mahindra Bank Ltd"},
    {"symbol": "BAJFINANCE",   "security_id": "317",   "name": "Bajaj Finance Ltd"},
    {"symbol": "AXISBANK",     "security_id": "5900",  "name": "Axis Bank Ltd"},
    {"symbol": "ASIANPAINT",   "security_id": "236",   "name": "Asian Paints Ltd"},
    {"symbol": "MARUTI",       "security_id": "10999", "name": "Maruti Suzuki India Ltd"},
    {"symbol": "SUNPHARMA",    "security_id": "3351",  "name": "Sun Pharmaceutical Industries Ltd"},
    {"symbol": "TITAN",        "security_id": "3506",  "name": "Titan Company Ltd"},
    {"symbol": "ULTRACEMCO",   "security_id": "11532", "name": "UltraTech Cement Ltd"},
    {"symbol": "WIPRO",        "security_id": "3787",  "name": "Wipro Ltd"},
    {"symbol": "NTPC",         "security_id": "11630", "name": "NTPC Ltd"},
    {"symbol": "HCLTECH",      "security_id": "7229",  "name": "HCL Technologies Ltd"},
    {"symbol": "BAJAJFINSV",   "security_id": "16675", "name": "Bajaj Finserv Ltd"},
    {"symbol": "ADANIENT",     "security_id": "25",    "name": "Adani Enterprises Ltd"},
    {"symbol": "ONGC",         "security_id": "2475",  "name": "Oil & Natural Gas Corporation Ltd"},
    {"symbol": "TATAMOTORS",   "security_id": "3432",  "name": "Tata Motors Ltd"},
    {"symbol": "TATASTEEL",    "security_id": "3499",  "name": "Tata Steel Ltd"},
    {"symbol": "JSWSTEEL",     "security_id": "11723", "name": "JSW Steel Ltd"},
    {"symbol": "POWERGRID",    "security_id": "14977", "name": "Power Grid Corporation of India Ltd"},
    {"symbol": "COALINDIA",    "security_id": "20374", "name": "Coal India Ltd"},
    {"symbol": "INDUSINDBK",   "security_id": "5258",  "name": "IndusInd Bank Ltd"},
    {"symbol": "GRASIM",       "security_id": "1232",  "name": "Grasim Industries Ltd"},
    {"symbol": "TECHM",        "security_id": "13538", "name": "Tech Mahindra Ltd"},
    {"symbol": "HDFCLIFE",     "security_id": "119",   "name": "HDFC Life Insurance Company Ltd"},
    {"symbol": "SBILIFE",      "security_id": "21808", "name": "SBI Life Insurance Company Ltd"},
    {"symbol": "ADANIPORTS",   "security_id": "15083", "name": "Adani Ports and Special Economic Zone Ltd"},
    {"symbol": "DRREDDY",      "security_id": "881",   "name": "Dr. Reddy's Laboratories Ltd"},
    {"symbol": "CIPLA",        "security_id": "694",   "name": "Cipla Ltd"},
    {"symbol": "EICHERMOT",    "security_id": "910",   "name": "Eicher Motors Ltd"},
    {"symbol": "TATACONSUM",   "security_id": "3432",  "name": "Tata Consumer Products Ltd"},
    {"symbol": "HINDALCO",     "security_id": "1363",  "name": "Hindalco Industries Ltd"},
    {"symbol": "APOLLOHOSP",   "security_id": "157",   "name": "Apollo Hospitals Enterprise Ltd"},
    {"symbol": "BPCL",         "security_id": "526",   "name": "Bharat Petroleum Corporation Ltd"},
    {"symbol": "HEROMOTOCO",   "security_id": "1348",  "name": "Hero MotoCorp Ltd"},
    {"symbol": "BAJAJ-AUTO",   "security_id": "16669", "name": "Bajaj Auto Ltd"},
    {"symbol": "SHRIRAMFIN",   "security_id": "4306",  "name": "Shriram Finance Ltd"},
    {"symbol": "NESTLEIND",    "security_id": "17963", "name": "Nestlé India Ltd"},
    {"symbol": "BRITANNIA",    "security_id": "547",   "name": "Britannia Industries Ltd"},
    {"symbol": "M&M",          "security_id": "2031",  "name": "Mahindra & Mahindra Ltd"},
    {"symbol": "DIVISLAB",     "security_id": "10940", "name": "Divi's Laboratories Ltd"},
    {"symbol": "BEL",          "security_id": "383",   "name": "Bharat Electronics Ltd"},
]

# Index by symbol and security_id for O(1) lookup
_BY_SYMBOL      = {inst["symbol"]: inst for inst in _NIFTY50}
_BY_SECURITY_ID = {inst["security_id"]: inst for inst in _NIFTY50}

# Common aliases not in official symbol list
_ALIASES = {
    "INFY":   _BY_SYMBOL["INFOSYS"],   # Dhan uses INFOSYS; retail often says INFY
    "BAJAJ":  _BY_SYMBOL["BAJAJ-AUTO"],
}


def get_nifty50_instruments() -> list[dict]:
    """
    Return the full NIFTY 50 instrument list.
    Each dict has: symbol, security_id, name, exchange_segment, instrument.
    """
    return [
        {**inst, "exchange_segment": "NSE_EQ", "instrument": "EQUITY"}
        for inst in _NIFTY50
    ]


def get_instrument(symbol: str) -> Optional[dict]:
    """
    Look up a single instrument by symbol (e.g. 'RELIANCE').
    Returns None if not in the NIFTY 50 universe.
    """
    clean = symbol.upper().replace(".NS", "")
    inst  = _BY_SYMBOL.get(clean) or _ALIASES.get(clean)
    if not inst:
        return None
    return {**inst, "exchange_segment": "NSE_EQ", "instrument": "EQUITY"}


def get_instrument_by_id(security_id: str) -> Optional[dict]:
    """Look up by security_id."""
    inst = _BY_SECURITY_ID.get(security_id)
    if not inst:
        return None
    return {**inst, "exchange_segment": "NSE_EQ", "instrument": "EQUITY"}


def get_symbols() -> list[str]:
    """Return just the symbol list."""
    return [inst["symbol"] for inst in _NIFTY50]
