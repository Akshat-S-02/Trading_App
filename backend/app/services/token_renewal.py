"""
app/services/token_renewal.py

Smart Dhan ACCESS_TOKEN renewal using the official dhanhq SDK.

Renewal strategy (in priority order):
  1. PIN + TOTP  → dhanhq.DhanLogin.generate_token(pin, totp)
       Generates a BRAND NEW token — works even if the current one is expired.
       Requires DHAN_PIN and DHAN_TOTP_SECRET in .env.

  2. RenewToken fallback → POST /v2/RenewToken
       Extends the CURRENT active token for another 24h.
       Only works while the token is still active.
       Used automatically if DHAN_PIN / DHAN_TOTP_SECRET are not configured.

Renewal timing rules:
  - If token expiry is during market hours (8:45 AM – 5:00 PM IST):
      → renew at 8:15 AM IST that same day (before market opens)
  - Otherwise:
      → renew 1 hour before expiry

After each successful renewal the new token's expiry is decoded and the
schedule recomputed automatically.
"""

import asyncio
import base64
import json
import sys
import time
from datetime import datetime, timezone, timedelta

import httpx

from app.config import config

# ── Constants ─────────────────────────────────────────────────────────────────

MARKET_START_H, MARKET_START_M = 8, 45     # 8:45 AM IST
MARKET_END_H,   MARKET_END_M   = 17, 0     # 5:00 PM IST
PRE_MARKET_RENEWAL_H = 8                   # renew at 08:15 if exp is in market hours
PRE_MARKET_RENEWAL_M = 15
PRE_EXPIRY_BUFFER_S  = 3600               # 1 hour before expiry (non-market case)

IST_OFFSET_S   = 5 * 3600 + 30 * 60      # 19800 seconds
DHAN_RENEW_URL = "https://api.dhan.co/v2/RenewToken"

# ── Module-level state (read by admin.py for /api/admin/token-status) ─────────

_stored_exp_ts: float | None   = None   # current token expiry epoch
_next_renewal_at: float | None = None   # computed next renewal epoch

last_renewal_at: float | None  = None
last_renewal_ok: bool          = False
last_renewal_error: str | None = None


# ── IST datetime arithmetic (no pytz needed) ──────────────────────────────────

def _ist_components(epoch: float):
    dt = datetime.utcfromtimestamp(epoch + IST_OFFSET_S)
    return dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second


def _ist_to_epoch(year, month, day, hour, minute, second=0) -> float:
    import calendar
    naive = datetime(year, month, day, hour, minute, second)
    return float(calendar.timegm(naive.timetuple()) - IST_OFFSET_S)


def _fmt_epoch_ist(epoch: float) -> str:
    y, mo, d, h, mi, s = _ist_components(epoch)
    return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"


# ── JWT decode ────────────────────────────────────────────────────────────────

def _token_exp(token: str) -> float | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        padding = 4 - len(parts[1]) % 4
        padded  = parts[1] + ("=" * (padding % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return float(payload["exp"])
    except Exception:
        return None


# ── Renewal scheduling ────────────────────────────────────────────────────────

def _compute_next_renewal(exp_ts: float) -> float:
    """
    Given a token's expiry epoch, return when to schedule the next renewal.
      - Expiry during market hours → renew at 8:15 AM IST same day
      - Expiry outside market hours → renew 1 hour before expiry
      - If computed renewal already past → renew in 60 s
    """
    y, mo, d, h, mi, _ = _ist_components(exp_ts)
    exp_min = h * 60 + mi
    market_start = MARKET_START_H * 60 + MARKET_START_M  # 525
    market_end   = MARKET_END_H   * 60 + MARKET_END_M    # 1020

    if market_start <= exp_min <= market_end:
        renewal_ts = _ist_to_epoch(y, mo, d, PRE_MARKET_RENEWAL_H, PRE_MARKET_RENEWAL_M)
    else:
        renewal_ts = exp_ts - PRE_EXPIRY_BUFFER_S

    now = time.time()
    return max(renewal_ts, now + 60.0)


def _seconds_until_next_renewal() -> float:
    if _next_renewal_at is not None:
        return max(_next_renewal_at - time.time(), 60.0)
    exp = _token_exp(config.ACCESS_TOKEN)
    if exp:
        return max(_compute_next_renewal(exp) - time.time(), 60.0)
    return 300.0


def initialize_renewal_schedule() -> None:
    global _stored_exp_ts, _next_renewal_at
    exp = _token_exp(config.ACCESS_TOKEN)
    if exp is None:
        print("⚠️  token_renewal: cannot read expiry from ACCESS_TOKEN.", file=sys.stderr)
        return
    _stored_exp_ts   = exp
    _next_renewal_at = _compute_next_renewal(exp)
    exp_ist    = _fmt_epoch_ist(exp)
    renew_ist  = _fmt_epoch_ist(_next_renewal_at)
    y, mo, d, h, mi, _ = _ist_components(exp)
    exp_min    = h * 60 + mi
    in_market  = (MARKET_START_H*60+MARKET_START_M) <= exp_min <= (MARKET_END_H*60+MARKET_END_M)
    reason     = "market-hours expiry → 8:15 AM IST" if in_market else "1h before expiry"
    print(f"📅  Token expiry:  {exp_ist} IST\n"
          f"⏰  Next renewal: {renew_ist} IST  ({reason})", flush=True)


# ── .env persistence ──────────────────────────────────────────────────────────

def _rewrite_env_key(key: str, value: str) -> None:
    import os, re
    env_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    )
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
        pattern  = re.compile(rf"^\s*{re.escape(key)}\s*=")
        replaced = False
        new_lines = []
        for line in lines:
            if pattern.match(line):
                new_lines.append(f"{key}={value}\n")
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"{key}={value}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"⚠️  token_renewal: could not persist to .env: {e}", file=sys.stderr)


# ── Renewal methods ───────────────────────────────────────────────────────────

async def _renew_via_pin_totp() -> str | None:
    """
    Generate a brand-new Dhan access token using PIN + TOTP.
    Calls POST https://auth.dhan.co/app/generateAccessToken directly.
    Works even if the current token is EXPIRED.
    Returns the new token string, or None on failure.
    """
    pin         = config.DHAN_PIN
    totp_secret = config.DHAN_TOTP_SECRET
    client_id   = config.CLIENT_ID

    if not pin or not totp_secret:
        return None  # not configured — fall through to RenewToken

    try:
        import pyotp
        totp = pyotp.TOTP(totp_secret).now()

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://auth.dhan.co/app/generateAccessToken",
                # Dhan expects query params, NOT a JSON body (confirmed from GitHub source)
                params={
                    "dhanClientId": client_id,
                    "pin":          pin,
                    "totp":         totp,
                },
            )

        if resp.status_code != 200:
            print(f"⚠️  PIN+TOTP HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
            return None

        data      = resp.json()
        new_token = (
            data.get("accessToken")
            or data.get("access_token")
            or (data.get("data") or {}).get("accessToken")
        )
        if new_token:
            print("🔑 PIN+TOTP login succeeded. New token obtained.", flush=True)
        else:
            print(f"⚠️  PIN+TOTP: unexpected response: {str(data)[:300]}", file=sys.stderr)
        return new_token

    except Exception as e:
        print(f"⚠️  PIN+TOTP renewal failed: {e}", file=sys.stderr)
        return None


async def _renew_via_renew_token() -> str | None:
    """
    Extend the CURRENT active token via POST /v2/RenewToken.
    Only works while the existing token is still active.
    Returns the new token string, or None on failure.
    """
    current_token = config.ACCESS_TOKEN
    client_id     = config.CLIENT_ID

    exp = _token_exp(current_token)
    if exp is not None and exp <= time.time():
        print("⛔ RenewToken skipped: current token already expired. "
              "Set DHAN_PIN + DHAN_TOTP_SECRET in .env for fully-automated renewal.",
              file=sys.stderr)
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.dhan.co/v2/RenewToken",
                headers={
                    "access-token": current_token,
                    "client-id":    client_id,
                    "Content-Type": "application/json",
                },
                json={"dhanClientId": client_id},
            )

        if resp.status_code != 200:
            print(f"⚠️  RenewToken HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return None

        data = resp.json()
        return (
            data.get("accessToken")
            or data.get("access_token")
            or (data.get("data") or {}).get("accessToken")
        )

    except Exception as e:
        print(f"⚠️  RenewToken exception: {e}", file=sys.stderr)
        return None




# ── Main renewal entry point ──────────────────────────────────────────────────

async def _do_renewal() -> bool:
    """
    Attempt token renewal using the best available method (PIN+TOTP first,
    then RenewToken fallback). Updates config, .env, and internal state.
    """
    global last_renewal_at, last_renewal_ok, last_renewal_error
    global _stored_exp_ts, _next_renewal_at

    # ── Method 1: PIN + TOTP (preferred — works even when token is expired) ───
    new_token = await _renew_via_pin_totp()

    # ── Method 2: RenewToken fallback ─────────────────────────────────────────
    if not new_token:
        print("ℹ️  Falling back to RenewToken API …", flush=True)
        new_token = await _renew_via_renew_token()

    if not new_token:
        last_renewal_at    = time.time()
        last_renewal_ok    = False
        last_renewal_error = "Both PIN+TOTP and RenewToken methods failed"
        return False

    # ── Success — hot-swap and recompute schedule ─────────────────────────────
    config.ACCESS_TOKEN = new_token
    _rewrite_env_key("ACCESS_TOKEN", new_token)

    new_exp = _token_exp(new_token)
    if new_exp:
        _stored_exp_ts   = new_exp
        _next_renewal_at = _compute_next_renewal(new_exp)
        print(f"✅ Token renewed.\n"
              f"   Expiry:       {_fmt_epoch_ist(new_exp)} IST\n"
              f"   Next renewal: {_fmt_epoch_ist(_next_renewal_at)} IST", flush=True)

    last_renewal_at    = time.time()
    last_renewal_ok    = True
    last_renewal_error = None
    return True


# ── External Health Check API ─────────────────────────────────────────────────

def handle_401_unauthorized():
    """
    Called by HTTP clients when Dhan returns HTTP 401.
    Flags the token as invalid so the ExecutionEngine pauses immediately,
    and forces the background loop to renew ASAP.
    """
    global last_renewal_ok, _next_renewal_at
    last_renewal_ok = False
    _next_renewal_at = time.time() - 10.0 # Force immediate loop wake
    print("🚨 Token flagged as UNAUTHORIZED (401). Pausing execution.", flush=True)

def is_token_valid() -> bool:
    """Returns True if the system believes the token is currently active."""
    return last_renewal_ok


# ── Background loop ───────────────────────────────────────────────────────────

async def token_renewal_loop() -> None:
    print("⏰  Token renewal scheduler starting …", flush=True)

    if config.DHAN_PIN and config.DHAN_TOTP_SECRET:
        print("✅  Auto-renewal mode: PIN + TOTP (fully automated)", flush=True)
    else:
        print("⚠️  Auto-renewal mode: RenewToken only (set DHAN_PIN + DHAN_TOTP_SECRET "
              "in .env for full automation that works even when token expires)",
              file=sys.stderr, flush=True)

    initialize_renewal_schedule()

    while True:
        wait_s   = _seconds_until_next_renewal()
        wake_ist = _fmt_epoch_ist(time.time() + wait_s)
        print(f"⏰  Sleeping {wait_s/3600:.1f} h → next renewal at {wake_ist} IST.", flush=True)
        await asyncio.sleep(wait_s)

        for attempt in range(1, 4):
            print(f"🔄  Token renewal attempt {attempt}/3 …", flush=True)
            success = await _do_renewal()
            if success:
                break
            if attempt < 3:
                print("   Retrying in 5 minutes …", flush=True)
                await asyncio.sleep(300)
        else:
            print("❌  All 3 renewal attempts failed. "
                  "Use the Admin screen to rotate the token manually.",
                  file=sys.stderr, flush=True)

        await asyncio.sleep(120)
