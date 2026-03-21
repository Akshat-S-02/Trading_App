# # app/config.py
# import os
# from pydantic import BaseSettings

# class Settings(BaseSettings):
#     DHAN_CLIENT_ID: str = "1109121898"
#     DHAN_CLIENT_SECRET: str = "ae999d52-bd8e-46dc-8558-6666e23c2237"
#     DHAN_ACCESS_TOKEN: str  # if provided; otherwise implement refresh flow
#     DHAN_API_KEY: str = "9fffa3e6"
#     DHAN_WS_URL: str = "wss://stream.dhan.co/market"   # change to actual
#     DHAN_REST_BASE: str = "https://api.dhan.co/"
#     APP_HOST: str = "0.0.0.0"
#     APP_PORT: int = 8000

#     class Config:
#         env_file = ".env"

# settings = Settings()
# # api key - 9fffa3e6
# # client id - 1109121898
# # api-secret - ae999d52-bd8e-46dc-8558-6666e23c2237

# """
# Put credentials here or set them as environment variables.
# Don't commit secrets to source control in a real project.
# """

# import os

# # Dhan credentials - prefer to export these as env vars and not commit in repo
# DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "1109121898")
# DHAN_API_KEY = os.getenv("DHAN_API_KEY", "9fffa3e6")
# DHAN_API_SECRET = os.getenv("DHAN_API_SECRET", "ae999d52-bd8e-46dc-8558-6666e23c2237")
# # If you have an access token already you can place it here; otherwise some endpoints accept client-id+api-key
# DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")

# # Toggle whether /trade posts to real Dhan order API.
# USE_DHAN_TRADING = os.getenv("USE_DHAN_TRADING", "false").lower() in ("1", "true", "yes")
# # Which Dhan host to hit (sandbox vs production)
# DHAN_API_BASE = os.getenv("DHAN_API_BASE", "https://api.dhan.co/v2")

# New data 

# from pathlib import Path
# import os
# from dotenv import load_dotenv


# ROOT = Path(__file__).parent
# load_dotenv(ROOT / "../.env")


# # Dhan credentials (set these in .env for security)
# API_KEY = os.getenv("DHAN_API_KEY", "9fffa3e6")
# API_SECRET = os.getenv("DHAN_API_SECRET", "ae999d52-bd8e-46dc-8558-6666e23c2237")
# CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "1109121898")
# ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")


# # Which base URLs to use
# DATA_BASE = os.getenv("DHAN_DATA_BASE", "https://api.dhan.co")
# MARKETFEED_BASE = os.getenv("DHAN_MARKETFEED_BASE", "https://api-feed.dhan.co")


# # Instrument CSV path
# INSTRUMENT_CSV = os.getenv("INSTRUMENT_CSV", str(ROOT / "../api-scrip-master.csv"))


# # App settings
# STATIC_IP = os.getenv("MY_STATIC_IP", "")


# # Debug
# DEBUG = os.getenv("DEBUG", "1") == "1"

# import os
# from pydantic import BaseSettings

# class Settings(BaseSettings):
#     DHAN_API_KEY: str = os.getenv("DHAN_API_KEY")
#     DHAN_API_SECRET: str = os.getenv("DHAN_API_SECRET")

#     DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID")
#     DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")

#     DHAN_WS_URL: str = os.getenv("DHAN_WS_URL", "wss://stream.dhan.co/market")
#     DHAN_REST_BASE: str = os.getenv("DHAN_REST_BASE", "https://api.dhan.co")

# config = Settings()

from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=False,          # allow in-memory mutation for token rotation
    )

    API_KEY: str
    API_SECRET: str
    CLIENT_ID: str
    ACCESS_TOKEN: str
    DHAN_WS_URL: str = "wss://stream.dhan.co/market"
    DHAN_REST_BASE: str = "https://api.dhan.co"
    DATABASE_URL: str = "postgresql://postgres:Akshat%401311@localhost:5432/trading_sandbox"
    # Auth — APP_PASSWORD and JWT_SECRET have NO defaults: they MUST be set in .env.
    # If either is missing, pydantic will raise a ValidationError on startup.
    APP_USERNAME: str = "admin"
    APP_PASSWORD: str           # required — set in .env
    JWT_SECRET: str             # required — set in .env (use a long random string, ≥32 chars)

    # Dhan auto-login credentials (for PIN+TOTP token generation)
    # Required for fully-automated token renewal. Set in .env:
    #   DHAN_PIN=123456          (your 6-digit Dhan login PIN)
    #   DHAN_TOTP_SECRET=XXXXX   (base32 secret from your authenticator app)
    DHAN_PIN: str = ""
    DHAN_TOTP_SECRET: str = ""

    # ── Execution Mode ─────────────────────────────────────────
    # "sandbox" = UI only, no execution
    # "paper"   = route to PaperBroker (realistic fills with slippage)
    # "live"    = route to Dhan REST API
    EXECUTION_MODE: str = "paper"

    # ── Paper Broker Config ────────────────────────────────────
    PAPER_FILL_DELAY_MS_MIN: int = 100     # min simulated fill latency
    PAPER_FILL_DELAY_MS_MAX: int = 500     # max simulated fill latency
    PAPER_SLIPPAGE_TICKS: int = 2          # 1 tick = ₹0.05

    # ── Watchdog ───────────────────────────────────────────────
    WATCHDOG_DEBUG_MODE: bool = False      # Bypass market hours check for tests


config = Settings()

