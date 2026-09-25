"""Minimal OpenWebUI sign-in client (used for LOGIN — LDAP if OWUI has LDAP enabled).
Mirrors kb-admin's openwebui.signin: HTTP 200 -> user dict (with role); non-200 -> None;
network errors raise so the caller can tell 'unreachable' from 'bad credentials'."""
import httpx

from . import config

TIMEOUT = 30.0


def signin(email: str, password: str):
    with httpx.Client(timeout=TIMEOUT) as cli:
        r = cli.post(
            f"{config.OPEN_WEBUI_URL}/api/v1/auths/signin",
            json={"email": email, "password": password},
        )
    if r.status_code == 200:
        return r.json()
    return None
