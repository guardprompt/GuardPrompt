"""Auth: signed session cookie + brute-force limit + admin gate. Copied from kb-admin
(same behaviour): AUTH_MODE=openwebui validates via OpenWebUI sign-in (LDAP if OWUI has
it) and requires role==admin; AUTH_MODE=dev allowlists ADMIN_FALLBACK_EMAILS (no password)."""
import time

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config, openwebui

_serializer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="gpusage-session")
COOKIE_NAME = "gpusage_session"

_attempts: dict[str, list] = {}


def _too_many(key: str) -> bool:
    now = time.time()
    window = [t for t in _attempts.get(key, []) if now - t < config.LOGIN_WINDOW]
    _attempts[key] = window
    return len(window) >= config.LOGIN_MAX_ATTEMPTS


def _record_attempt(key: str):
    _attempts.setdefault(key, []).append(time.time())


def login(email: str, password: str, client_ip: str):
    key = f"{client_ip}:{email}".lower()
    if _too_many(key):
        raise HTTPException(status_code=429, detail="Per daug bandymų. Pabandykite vėliau.")

    user = None
    if config.AUTH_MODE == "dev":
        if email.lower() in config.ADMIN_FALLBACK_EMAILS:
            user = {"email": email, "name": email, "role": "admin"}
    else:
        try:
            res = openwebui.signin(email, password)
        except Exception:
            raise HTTPException(status_code=503, detail="OpenWebUI nepasiekiamas — patikrink ar servisas veikia.")
        if res and res.get("role") == "admin":
            user = {"id": res.get("id"), "email": res.get("email"), "name": res.get("name"), "role": "admin"}

    if not user:
        _record_attempt(key)
        raise HTTPException(status_code=401, detail="Neteisingi duomenys arba ne administratorius.")
    return user


def make_cookie(user: dict) -> str:
    return _serializer.dumps({"email": user.get("email"), "name": user.get("name"), "role": user.get("role")})


def require_admin(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Neprisijungta")
    try:
        data = _serializer.loads(token, max_age=config.SESSION_TTL)
    except BadSignature:
        raise HTTPException(status_code=401, detail="Sesija negalioja/pasibaigė")
    if data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Tik administratoriui")
    return data
