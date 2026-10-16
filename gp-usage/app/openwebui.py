"""Minimal OpenWebUI sign-in client (used for LOGIN).

OpenWebUI has TWO sign-in endpoints and they validate different credential stores:
  * /api/v1/auths/signin  -> LOCAL accounts only (email + the local password hash).
  * /api/v1/auths/ldap    -> LDAP/Active Directory (the `user` field + AD password).
A user who logs into OpenWebUI via AD has NO local password, so /signin rejects their
AD password ("bad credentials") even though it is correct. We therefore try /signin
first (local admins) and fall back to /ldap (AD users). Both return the same user json
(id, email, name, role) on success; we hand that back so the caller can match the
email against its allowlist. 200 -> user dict; neither works -> None; network errors
raise so the caller can tell 'unreachable' from 'bad credentials'."""
import httpx

from . import config

TIMEOUT = 30.0


def signin(identifier: str, password: str):
    """`identifier` is whatever the person typed in the login form — their OpenWebUI
    email (local) or their AD username/email (LDAP). We try local first, then LDAP."""
    unreachable = None
    s_local = s_ldap = None
    with httpx.Client(timeout=TIMEOUT) as cli:
        # 1) local account (email + password)
        try:
            r = cli.post(f"{config.OPEN_WEBUI_URL}/api/v1/auths/signin",
                         json={"email": identifier, "password": password})
            s_local = r.status_code
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError as e:
            unreachable = e
        # 2) LDAP / Active Directory (OpenWebUI validates against AD here). The `user`
        #    field is the LDAP login value (email or sAMAccountName, per OWUI's
        #    LDAP_ATTRIBUTE_FOR_USERNAME); the response still carries the real email.
        try:
            r = cli.post(f"{config.OPEN_WEBUI_URL}/api/v1/auths/ldap",
                         json={"user": identifier, "password": password})
            s_ldap = r.status_code
            if r.status_code == 200:
                return r.json()
            # surface WHY ldap refused (OWUI returns a JSON {"detail": "..."} body)
            try:
                _d = r.text[:200]
            except Exception:
                _d = ""
            print(f"[gp-usage] OWUI auth: signin={s_local} ldap={s_ldap} ldap_body={_d!r}", flush=True)
        except httpx.HTTPError as e:
            unreachable = e
    if unreachable is not None:
        raise unreachable          # let the caller report 'OpenWebUI unreachable' (503)
    print(f"[gp-usage] OWUI auth: signin={s_local} ldap={s_ldap} (both refused)", flush=True)
    return None
