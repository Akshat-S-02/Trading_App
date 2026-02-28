import os
import pandas as pd

# CSV location inside app/
# Assuming this file is at backend/app/core/instruments.py
# CSV is at backend/app/api-scrip-master.csv
BASE_DIR = os.path.dirname(os.path.dirname(__file__)) # backend/app
CSV_PATH = os.path.join(BASE_DIR, "api-scrip-master.csv")

# Exported globals
df = None
symbol_to_sid = {}
sid_to_symbol = {}
top_5000_sids = []


# ---------------------------------------------------------
# Utility: Build list of top 5000 NSE Equity instruments
# ---------------------------------------------------------
def get_top_5000_nse_equities(df_local: pd.DataFrame) -> list:
    try:
        # NSE + Equity filter
        # Note: adjust column names if your CSV is different
        cond = (
            (df_local["sem_exm_exch_id"].str.upper() == "NSE") &
            (df_local["sem_instrument_name"].str.upper() == "EQUITY")
        )

        # Only EQ series if available
        if "sem_series" in df_local.columns:
            cond &= df_local["sem_series"].str.upper().eq("EQ")

        sub = df_local[cond].copy()

        # Sort by volume if available
        for col in ["volume", "vol", "trade_volume", "sem_total_volume"]: # Added common volume col names
            if col in sub.columns:
                sub[col] = pd.to_numeric(sub[col], errors="coerce").fillna(0)
                sub = sub.sort_values(col, ascending=False)
                break

        sids = []
        for v in sub["sem_smst_security_id"].dropna().unique():
            try:
                sids.append(int(v))
            except:
                continue
            if len(sids) >= 5000:
                break

        print(f"🔥 Selected top NSE_EQ instruments = {len(sids)}")
        return sids

    except Exception as e:
        print("❌ Error computing top NSE_EQ list:", e)
        return []


# ---------------------------------------------------------
# MAIN LOADER CALLED BY main.py
# ---------------------------------------------------------
def load_instruments():
    global df, symbol_to_sid, sid_to_symbol, top_5000_sids

    print(f"📦 Loading Dhan instrument master list from {CSV_PATH}...")

    try:
        if not os.path.exists(CSV_PATH):
            print(f"❌ CSV not found at {CSV_PATH}")
            return

        df = pd.read_csv(CSV_PATH, low_memory=False) # low_memory=False to avoid DtypeWarning

        # Normalize header names
        df.columns = [c.strip().lower() for c in df.columns]

        # Clean key columns (ensure they exist first)
        for col in ["sem_trading_symbol", "sm_symbol_name", "sem_exm_exch_id", "sem_series"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.upper().str.strip()

        # Build maps
        symbol_to_sid = {}
        sid_to_symbol = {}

        # Iterate via vectorization or simple loop. Loop is fine for <100k rows at startup.
        # But for speed, let's just use what was working, but protected.
        
        # Filter relevant rows for mapping (e.g. NSE EQ) to keep dict size manageable?
        # Or just map everything. Let's map everything where 'sem_smst_security_id' is valid.
        
        if "sem_smst_security_id" in df.columns and "sem_trading_symbol" in df.columns:
             # Fast dict creation
             # We want to PRIORITIZE NSE EQ.
             # Strategy: 
             # 1. Create a mask for NSE EQ
             # 2. Iterate NSE EQ first and populate map
             # 3. Iterate others and populate if not exists (or just skip others if we only want NSE)
             
             # Let's map EVERYTHING to sid_to_symbol (for reverse lookup)
             # But for symbol_to_sid (lookup), we strictly want NSE EQ if available.
             
             # 1. Sort DF so NSE EQ comes first? or just filter.
             # Filtering is safer.
             
             # Helper to process a subset
             def process_subset(subset, force_override=False):
                 for _, row in subset.iterrows():
                     try:
                         sid = int(row["sem_smst_security_id"])
                         sym = str(row["sem_trading_symbol"]).strip()
                         
                         # Always update reverse map
                         sid_to_symbol[sid] = sym
                         
                         # Update forward map
                         if force_override or sym not in symbol_to_sid:
                             symbol_to_sid[sym] = sid
                     except:
                         pass

             # Split into NSE_EQ and Others
             is_nse = (df["sem_exm_exch_id"] == "NSE")
             is_eq = (df["sem_instrument_name"] == "EQUITY")
             if "sem_series" in df.columns:
                 is_eq &= (df["sem_series"] == "EQ")
            
             nse_eq_df = df[is_nse & is_eq]
             other_df = df[~(is_nse & is_eq)]
             
             print(f"📊 Mapping: Found {len(nse_eq_df)} NSE_EQ rows and {len(other_df)} others.")
             
             # Process NSE EQ first (overriding anything that might theoretically be there, though map is empty)
             process_subset(nse_eq_df, force_override=True)
             
             # Process others (only if not already mapped) - optional, but good for fallback
             # process_subset(other_df, force_override=False) 
             # ACTUALLY: For this app, we PROBABLY only want NSE EQ to avoid mixing BSE SIDs with NSE subscriptions
             # So let's skip 'other_df' for symbol_to_sid, but keep it for sid_to_symbol if we receive data?
             # No, if we receive data for a SID we didn't map, we can't look it up easily if we don't map it.
             # Let's map others to sid_to_symbol but NOT symbol_to_sid to prevent accidental BSE subscription.
             
             for _, row in other_df.iterrows():
                 try:
                     sid = int(row["sem_smst_security_id"])
                     sym = str(row["sem_trading_symbol"]).strip()
                     # Only add if NOT already mapped (NSE_EQ takes priority)
                     if sid not in sid_to_symbol:
                         sid_to_symbol[sid] = sym
                     # Do NOT add to symbol_to_sid to avoid BSE SIDs
                 except: 
                     pass

        # Use NSE EQ for stricter symbol->sid mapping if possible
        # (Optional refinement: overwrite symbol_to_sid with NSE EQ specific ones)

        # Build top 5000 list
        top_5000_sids = get_top_5000_nse_equities(df)

        print(f"🔗 Mapped {len(symbol_to_sid)} symbols")
        print(f"🔗 sid_to_symbol has {len(sid_to_symbol)} entries")
        # Print sample mappings for the 5 stocks we're using
        test_sids = [2885, 11536, 1333, 1594, 4963]
        for sid in test_sids:
            print(f"   SID {sid} -> {sid_to_symbol.get(sid, 'NOT FOUND')}")

        print(f"✅ Loaded {len(df)} instruments.")

    except Exception as e:
        print("❌ Failed to load instrument CSV:", e)
        # traceback.print_exc()
        df = pd.DataFrame()


# ---------------------------------------------------------
# Public APIs
# ---------------------------------------------------------
def get_all_instruments():
    """Return the whole DataFrame."""
    return df

def get_security_id(symbol: str):
    """Return NSE_EQ SecurityId for a single symbol."""
    if not symbol: return None
    symbol = symbol.upper().strip()
    if symbol.endswith(".NS"):
        symbol = symbol[:-3]
    return symbol_to_sid.get(symbol)

def get_security_id_multi(symbols: list[str]):
    """Return dict mapping symbol → NSE_EQ SecurityId."""
    result = {}
    for sym in symbols:
        sid = get_security_id(sym)
        if sid:
            result[sym.upper().strip()] = str(sid)
    return result

def resolve_symbol_from_sid(sid: int):
    """Resolve SecurityId back to symbol."""
    return sid_to_symbol.get(int(sid))
