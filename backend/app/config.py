

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
    DATABASE_URL: str               # required — set in .env (no default: it would hold a password)
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

    # ── SEBI Static-IP Compliance ──────────────────────────────
    # From April 2026, order-placing API calls must originate from an IP
    # whitelisted with the broker. Set to true only after that whitelisting
    # is done for this host's IP. Checked at startup when EXECUTION_MODE=="live".
    DHAN_STATIC_IP_CONFIRMED: bool = False


config = Settings()

