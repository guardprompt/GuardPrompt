"""Lightweight license gate for gp-transcribe — mirrors the anonymizer's licensing:
same license server, same machine key, same confirmation-token algorithm
(sha256("<key>|DKprojektai|<YYYY-MM-DD>")). If the license is invalid the engine
refuses to transcribe. Network / server failures fall back to GRACE so a flaky
license server never takes production down; only an EXPLICIT rejection denies.

The result is cached for GP_LICENSE_TTL seconds (default 30 min) so we hit the
license server at most twice an hour, not on every request.
"""
import os
import time
import hashlib

import requests

MACHINE_KEY_PATH = os.environ.get("MACHINE_KEY_PATH", "/app/machine_key.txt")
LICENSING_URL = (os.environ.get("LICENSING_URL_ENV", "") or "").rstrip("/")
CLIENT = os.environ.get("GP_LICENSE_CLIENT", "DKprojektai")
TTL = int(os.environ.get("GP_LICENSE_TTL", "1800"))
# GRACE=true (default): unreachable/misconfigured server -> allow (never hard-down
# on infra hiccups). Only an explicit server "rejected" denies. Set false to fail
# closed (deny whenever the license cannot be positively confirmed).
GRACE = os.environ.get("GP_LICENSE_GRACE", "true").lower() in ("1", "true", "yes")

_state = {"ok": True, "checked": 0.0, "reason": "startup"}


def _machine_key():
    try:
        with open(MACHINE_KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _expected(key, date_str):
    return hashlib.sha256(("%s|%s|%s" % (key, CLIENT, date_str)).encode("utf-8")).hexdigest()


def _verify():
    key = _machine_key()
    if not key or not LICENSING_URL:
        return (GRACE, "no key/URL")
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        r = requests.get(LICENSING_URL + "/dk_anon_regcheck.php",
                         params={"key": key, "date": date_str}, timeout=30)
    except Exception:
        return (True if GRACE else _state["ok"], "server unreachable")
    if r.status_code != 200:
        return (True if GRACE else False, "server HTTP %s" % r.status_code)
    try:
        d = r.json()
    except Exception:
        return (True if GRACE else False, "bad response")
    if d.get("status") == "OK" and d.get("confirmation_token") == _expected(key, date_str):
        return (True, "approved")
    return (False, "rejected")            # explicit rejection ALWAYS denies (even in grace)


def is_licensed():
    now = time.time()
    if now - _state["checked"] > TTL:
        ok, reason = _verify()
        _state["ok"], _state["reason"], _state["checked"] = ok, reason, now
        print("[gp-transcribe] license: %s (%s)" % ("OK" if ok else "DENIED", reason), flush=True)
    return _state["ok"]


def status():
    return {"licensed": _state["ok"], "reason": _state["reason"], "checked": _state["checked"]}
