"""gp-usage config. Auth mirrors kb-admin (OpenWebUI sign-in = LDAP if OWUI has LDAP)."""
import json
import os

# Optional friendly-name map for identities that carry no email — Claude Code clients
# authenticate with an account_uuid (no email), so the dashboard would otherwise show
# "Claude · <uuid>". Fill GP_USAGE_USER_MAP with {"<account_uuid>": "vardas@regitra.lt"}
# (device_id or the raw id also work as keys) to show real people. JSON object; bad
# JSON -> empty map (never crashes).
try:
    USER_MAP = json.loads(os.getenv("GP_USAGE_USER_MAP", "{}") or "{}")
    if not isinstance(USER_MAP, dict):
        USER_MAP = {}
except Exception:
    USER_MAP = {}

# --- auth (same knobs as kb-admin) ---
AUTH_MODE = os.environ.get("AUTH_MODE", "openwebui").lower()

SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
if SESSION_SECRET.strip().lower() in ("", "change-me", "change-me-in-env"):
    raise RuntimeError(
        "SESSION_SECRET is unset or a placeholder — refusing to start. Set a strong "
        "random SESSION_SECRET (the installer generates one).")
SESSION_TTL = int(os.environ.get("SESSION_TTL", "3600"))

LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW = int(os.environ.get("LOGIN_WINDOW", "300"))
ADMIN_FALLBACK_EMAILS = [
    e.strip().lower() for e in os.environ.get("ADMIN_FALLBACK_EMAILS", "").split(",") if e.strip()
]

OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "http://open-webui-dk:8080").rstrip("/")

# --- data ---
# Same Postgres the proxies write gp_audit to. Read-only usage here (SELECT only).
DB_URL = os.environ.get("GP_DB_URL", "")

# --- pricing (OpenRouter, preliminary) ---
OPENROUTER_MODELS_URL = os.environ.get("OPENROUTER_MODELS_URL", "https://openrouter.ai/api/v1/models")
PRICE_TTL = int(os.environ.get("GP_USAGE_PRICE_TTL", "86400"))          # refresh once/day
USD_EUR = float(os.environ.get("GP_USAGE_USD_EUR", "0.92"))            # preliminary FX
BYTES_PER_TOKEN = float(os.environ.get("GP_USAGE_BYTES_PER_TOKEN", "4"))  # rough token estimate

# retention hint shown in the UI (audit prune lives in the proxies)
MAX_DAYS = int(os.environ.get("GP_USAGE_MAX_DAYS", "90"))

# Timezone for day-bucketing (ts is timestamptz/UTC; group by LOCAL calendar day so the
# chart matches how people read dates). Client also renders local days.
TZ = os.environ.get("GP_USAGE_TZ", "Europe/Vilnius")
