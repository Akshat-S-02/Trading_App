"""Manual Dhan token renewal via PIN + TOTP:  .venv/bin/python force_renew.py"""
import asyncio
import os
import sys

import httpx

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config import config  # reads backend/.env
from app.services.token_renewal import _renew_via_pin_totp, _rewrite_env_key


async def force_renew():
    print("Forcing token renewal via PIN + TOTP...")
    new_token = await _renew_via_pin_totp()
    if not new_token:
        print("Renewal failed.")
        return
    config.ACCESS_TOKEN = new_token
    _rewrite_env_key("ACCESS_TOKEN", new_token)
    print("Success. Updated .env (restart trader-api so it picks the token up).")

    resp = httpx.get("https://api.dhan.co/v2/fundlimit",
                     headers={"client-id": config.CLIENT_ID, "access-token": new_token})
    print(f"Test request status: {resp.status_code}\n{resp.text[:200]}")


if __name__ == "__main__":
    asyncio.run(force_renew())
