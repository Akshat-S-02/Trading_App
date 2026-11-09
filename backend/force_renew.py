import asyncio
import os
import sys
from dotenv import load_dotenv

# Add parent dir to path so we can import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.token_renewal import _renew_via_pin_totp, _rewrite_env_key
from app.config import config

async def force_renew():
    load_dotenv()
    print("Forcing token renewal via PIN + TOTP...")
    
    # Ensure config has latest from .env
    config.DHAN_PIN = os.getenv("DHAN_PIN")
    config.DHAN_TOTP_SECRET = os.getenv("DHAN_TOTP_SECRET")
    config.CLIENT_ID = os.getenv("CLIENT_ID")
    
    new_token = await _renew_via_pin_totp()
    if new_token:
        print("Success! New token obtained.")
        config.ACCESS_TOKEN = new_token
        _rewrite_env_key("ACCESS_TOKEN", new_token)
        print("Updated .env and config.")
        
        # Test it with a tiny request
        import requests
        headers = {
            "client-id": config.CLIENT_ID,
            "access-token": new_token,
        }
        resp = requests.get("https://api.dhan.co/v2/fundlimit", headers=headers)
        print(f"Test Request Status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
    else:
        print("Renewal failed.")

if __name__ == "__main__":
    asyncio.run(force_renew())
