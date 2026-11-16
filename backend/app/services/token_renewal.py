"""
app/services/token_renewal.py

Dhan ACCESS_TOKEN renewal (httpx calls to Dhan).

Renewal strategy (in priority order):
  1. PIN + TOTP  → POST auth.dhan.co/app/generateAccessToken
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
import os
import re
import sys
import time
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import httpx
from dotenv import dotenv_values

from app.config import config

_IST = ZoneInfo("Asia/Kolkata")
MARKET_START = dt_time(8, 45)             # an expiry in this window is renewed
MARKET_END = dt_time(17, 0)               # at 08:15 the same morning instead
PRE_MARKET_RENEWAL = dict(hour=8, minute=15, second=0, microsecond=0)
PRE_EXPIRY_BUFFER_S = 3600                # otherwise renew 1 hour before expiry
DHAN_RENEW_URL = "https://api.dhan.co/v2/RenewToken"
_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

_next_renewal_at: float | None = None     # epoch of the next scheduled renewal


def _fmt_epoch_ist(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, _IST).strftime("%Y-%m-%d %H:%M:%S")


def _token_exp(token: str) -> float | None:
    """The JWT's exp claim (no signature check: we only schedule by it)."""
    try:
        _, payload, _ = token.split(".")
        return float(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"])
    except Exception:
        return None


def _expires_in_market_hours(exp_ts: float) -> bool:
    t = datetime.fromtimestamp(exp_ts, _IST).time().replace(second=0, microsecond=0)
    return MARKET_START <= t <= MARKET_END


def _compute_next_renewal(exp_ts: float) -> float:
    """When to renew a token expiring at exp_ts; never sooner than 60 s from now."""
    if _expires_in_market_hours(exp_ts):
        renewal_ts = datetime.fromtimestamp(exp_ts, _IST).replace(**PRE_MARKET_RENEWAL).timestamp()
    else:
        renewal_ts = exp_ts - PRE_EXPIRY_BUFFER_S
    return max(renewal_ts, time.time() + 60.0)


def _seconds_until_next_renewal() -> float:
    if _next_renewal_at is not None:
        return max(_next_renewal_at - time.time(), 60.0)
    exp = _token_exp(config.ACCESS_TOKEN)
    return max(_compute_next_renewal(exp) - time.time(), 60.0) if exp else 300.0


def initialize_renewal_schedule() -> None:
    global _next_renewal_at
    exp = _token_exp(config.ACCESS_TOKEN)
    if exp is None:
        print("⚠️  token_renewal: cannot read expiry from ACCESS_TOKEN.", file=sys.stderr)
        return
    _next_renewal_at = _compute_next_renewal(exp)
    reason = "market-hours expiry -> 8:15 AM IST" if _expires_in_market_hours(exp) else "1h before expiry"
    print(f"DATE  Token expiry:  {_fmt_epoch_ist(exp)} IST\n"
          f"TIME  Next renewal: {_fmt_epoch_ist(_next_renewal_at)} IST  ({reason})", flush=True)


# ── .env persistence ──────────────────────────────────────────────────────────

def _rewrite_env_key(key: str, value: str) -> None:
    """Set one key=value line in .env (appended if missing)."""
    # A line break in value would write extra keys (EXECUTION_MODE=live, ...) into .env
    if any(ch in value for ch in "\r\n\x00"):
        raise ValueError(f"refusing to write control characters into {key}")
    try:
        with open(_ENV_PATH) as f:
            lines = f.readlines()
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        new_line = f"{key}={value}\n"
        if any(pattern.match(line) for line in lines):
            lines = [new_line if pattern.match(line) else line for line in lines]
        else:
            lines.append(new_line)
        with open(_ENV_PATH, "w") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"⚠️  token_renewal: could not persist to .env: {e}", file=sys.stderr)


def _token_from(data: dict) -> str | None:
    return data.get("accessToken") or data.get("access_token") or (data.get("data") or {}).get("accessToken")


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

        data = resp.json()
        new_token = _token_from(data)
        if new_token:
            print("KEY PIN+TOTP login succeeded. New token obtained.", flush=True)
        else:
            print(f"WARN PIN+TOTP: unexpected response: {str(data)[:300]}", file=sys.stderr)
        return new_token

    except Exception as e:
        print(f"ERR PIN+TOTP renewal failed: {e}", file=sys.stderr)
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
                DHAN_RENEW_URL,
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

        return _token_from(resp.json())

    except Exception as e:
        print(f"⚠️  RenewToken exception: {e}", file=sys.stderr)
        return None


# ── Main renewal entry point ──────────────────────────────────────────────────

async def _do_renewal() -> bool:
    """
    Attempt token renewal using the best available method (PIN+TOTP first,
    then RenewToken fallback). Updates config, .env, and internal state.
    """
    global _next_renewal_at

    # ── Method 1: PIN + TOTP (preferred — works even when token is expired) ───
    new_token = await _renew_via_pin_totp()

    # ── Method 2: RenewToken fallback ─────────────────────────────────────────
    if not new_token:
        print("ℹ️  Falling back to RenewToken API …", flush=True)
        new_token = await _renew_via_renew_token()

    if not new_token:
        print("❌  Both PIN+TOTP and RenewToken failed.", file=sys.stderr, flush=True)
        return False

    # ── Success — hot-swap and recompute schedule ─────────────────────────────
    config.ACCESS_TOKEN = new_token
    _rewrite_env_key("ACCESS_TOKEN", new_token)

    new_exp = _token_exp(new_token)
    if new_exp:
        _next_renewal_at = _compute_next_renewal(new_exp)
        print(f"✅ Token renewed.\n"
              f"   Expiry:       {_fmt_epoch_ist(new_exp)} IST\n"
              f"   Next renewal: {_fmt_epoch_ist(_next_renewal_at)} IST", flush=True)
    return True


# ── External Health Check API ─────────────────────────────────────────────────

_env_mtime: float | None = None
_rejected_token: str | None = None      # token Dhan answered 401 for
_wake: asyncio.Event | None = None      # set to cut the renewal loop's sleep short
_loop: asyncio.AbstractEventLoop | None = None


def current_access_token() -> str:
    """
    The freshest ACCESS_TOKEN. Renewal runs in the API process and writes .env;
    the OutboxWorker is a separate process, so re-read .env whenever it changes
    instead of trusting the token loaded at process start.
    """
    global _env_mtime
    try:
        mtime = os.path.getmtime(_ENV_PATH)
        if mtime != _env_mtime:
            _env_mtime = mtime
            token = dotenv_values(_ENV_PATH).get("ACCESS_TOKEN")
            if token:
                config.ACCESS_TOKEN = token
    except OSError:
        pass
    return config.ACCESS_TOKEN


def handle_401_unauthorized():
    """
    Called by HTTP clients when Dhan returns HTTP 401 (from any thread).
    Marks the current token as rejected so is_token_valid() turns False, and
    wakes the renewal loop (API process only) to renew right away.
    """
    global _next_renewal_at, _rejected_token
    _rejected_token = config.ACCESS_TOKEN
    _next_renewal_at = time.time()
    if _loop is not None and _wake is not None:
        _loop.call_soon_threadsafe(_wake.set)
    print("🚨 Token flagged as UNAUTHORIZED (401). Pausing execution.", flush=True)


def is_token_valid() -> bool:
    """True if the current token has not expired and Dhan has not rejected it."""
    token = current_access_token()
    exp = _token_exp(token)
    return bool(token) and exp is not None and exp > time.time() and token != _rejected_token


# ── Background loop ───────────────────────────────────────────────────────────

async def token_renewal_loop() -> None:
    print("⏰  Token renewal scheduler starting …", flush=True)

    if config.DHAN_PIN and config.DHAN_TOTP_SECRET:
        print("✅  Auto-renewal mode: PIN + TOTP (fully automated)", flush=True)
    else:
        print("⚠️  Auto-renewal mode: RenewToken only (set DHAN_PIN + DHAN_TOTP_SECRET "
              "in .env for full automation that works even when token expires)",
              file=sys.stderr, flush=True)

    global _wake, _loop
    _loop = asyncio.get_running_loop()
    _wake = asyncio.Event()

    initialize_renewal_schedule()

    while True:
        wait_s   = _seconds_until_next_renewal()
        wake_ist = _fmt_epoch_ist(time.time() + wait_s)
        print(f"⏰  Sleeping {wait_s/3600:.1f} h → next renewal at {wake_ist} IST.", flush=True)
        try:
            await asyncio.wait_for(_wake.wait(), timeout=wait_s)
            print("⏰  Woken early by a 401 — renewing now.", flush=True)
        except asyncio.TimeoutError:
            pass
        _wake.clear()

        for attempt in range(1, 4):
            print(f"🔄  Token renewal attempt {attempt}/3 …", flush=True)
            if await _do_renewal():
                break
            if attempt < 3:
                print("   Retrying in 5 minutes …", flush=True)
                await asyncio.sleep(300)
        else:
            print("❌  All 3 renewal attempts failed. "
                  "Run force_renew.py, or put a fresh ACCESS_TOKEN in .env and restart.",
                  file=sys.stderr, flush=True)

        await asyncio.sleep(120)
