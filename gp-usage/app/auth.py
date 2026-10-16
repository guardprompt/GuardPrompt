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


def login(email: str, password: str, client_ip: str, viewers: set | None = None):
    """Resolve the gp-usage role for a valid OpenWebUI login:
       admin  = OWUI role==admin OR email in GP_USAGE_ADMIN_EMAILS (full: view + edit)
       viewer = email in the gp_usage_access allowlist (read-only)
       else   = refused (valid credentials but no dashboard access).
    `viewers` is the current allowlist (fetched by the caller, which has the async DB)."""
    key = f"{client_ip}:{email}".lower()
    if _too_many(key):
        raise HTTPException(status_code=429, detail="Per daug bandymų. Pabandykite vėliau.")
    viewers = viewers or set()

    user = None
    if config.AUTH_MODE == "dev":
        em = email.lower()
        if em in config.ADMIN_FALLBACK_EMAILS:
            user = {"email": email, "name": email, "role": "admin"}
        elif em in viewers:
            user = {"email": email, "name": email, "role": "viewer"}
    else:
        try:
            res = openwebui.signin(email, password)
        except Exception:
            raise HTTPException(status_code=503, detail="OpenWebUI nepasiekiamas — patikrink ar servisas veikia.")
        if res:                                   # credentials valid
            em = (res.get("email") or email).strip().lower()
            role = None
            if res.get("role") == "admin" or em in config.ADMIN_EMAILS:
                role = "admin"
            elif em in viewers:
                role = "viewer"
            if role:
                user = {"id": res.get("id"), "email": res.get("email"),
                        "name": res.get("name"), "role": role}
            else:
                # Credentials are VALID but this account is neither admin nor a listed
                # viewer. Distinct message + log so the admin sees exactly which email
                # (as OpenWebUI knows it) to add in the "Prieiga" panel.
                _record_attempt(key)
                print(f"[gp-usage] login denied — valid OWUI user but no access: "
                      f"email={em!r} owui_role={res.get('role')!r}; "
                      f"add this exact email in Prieiga to grant view access", flush=True)
                raise HTTPException(status_code=403,
                    detail=f"Prisijungta ({em}), bet ši paskyra neturi prieigos prie ataskaitos. "
                           f"Paprašyk administratoriaus pridėti šį el. paštą „Prieiga“ skiltyje.")
        else:
            print(f"[gp-usage] login failed — bad OWUI credentials for {email!r}", flush=True)

    if not user:
        _record_attempt(key)
        raise HTTPException(status_code=401, detail="Neteisingas el. paštas arba slaptažodis.")
    return user


def make_cookie(user: dict) -> str:
    return _serializer.dumps({"email": user.get("email"), "name": user.get("name"), "role": user.get("role")})


def _session(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Neprisijungta")
    try:
        return _serializer.loads(token, max_age=config.SESSION_TTL)
    except BadSignature:
        raise HTTPException(status_code=401, detail="Sesija negalioja/pasibaigė")


def require_view(request: Request) -> dict:
    """Read access: admin OR viewer."""
    data = _session(request)
    if data.get("role") not in ("admin", "viewer"):
        raise HTTPException(status_code=403, detail="Neturite prieigos")
    return data


def require_admin(request: Request) -> dict:
    """Write access: admin only."""
    data = _session(request)
    if data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Tik administratoriui (peržiūros teisė be redagavimo)")
    return data
