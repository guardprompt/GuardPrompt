"""
Open Terminal role-aware proxy.

Sits between OpenWebUI and the open-terminal sandbox. OpenWebUI authenticates
every terminal request as a specific user and forwards that identity:
  * HTTP  -> header  X-User-Id: <user id>
  * WS    -> query   ?user_id=<user id>
Those values are set by OpenWebUI server-side from the authenticated session —
a chat user cannot forge them, and open-terminal is only reachable through this
proxy (loopback + in-network, key held here), so the identity is trustworthy.

Policy: only OpenWebUI ADMINS may run privileged / install-class commands.
  * non-admin HTTP /execute (and /execute/{id}/input): command is inspected;
    if it matches BLOCK_REGEX (sudo, apt, pip install, npm install, ...) -> 403
    with a message the model relays to the user.
  * non-admin WebSocket (the interactive terminal panel) -> refused, because a
    live shell cannot be command-filtered reliably. Non-admins work through the
    AI (/execute), which IS filtered.
  * admins -> everything passes through unchanged.

NOTE: command-string filtering is a blocklist and a determined user can evade it
(python -m pip, base64+exec, curl|sh, ...). It stops casual/accidental misuse;
for a hard guarantee pair it with the egress firewall (block-all) on the sandbox.
"""

import asyncio
import json
import os
import re
import shlex
import time

import asyncpg
import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response

UPSTREAM = os.getenv("OT_UPSTREAM", "http://open-terminal:8000").rstrip("/")
DB_DSN = os.getenv("OT_DB_DSN", "")
ROLE_TTL = int(os.getenv("OT_ROLE_TTL", "60"))

# run_command synchronous mode. Upstream open-terminal's POST /execute returns
# immediately with status="running" and empty output, forcing the model to poll
# GET /execute/{id}/status repeatedly. Each poll is a separate LLM tool-call
# round-trip; on Gemini 3 (Flash/Lite) those extra round-trips push the
# conversation past the point where the model still emits a valid
# thought_signature, and the provider then rejects the request with
# 400 "Corrupted thought signature". By blocking here until the process finishes
# and returning the FINAL status payload (full output + exit_code) as the
# run_command response, one command costs ONE tool call instead of 3+, which
# keeps multi-step work under that cutoff — and is faster for every model.
# Long-running commands (servers) that don't finish within OT_EXEC_SYNC_MAX fall
# back to the original behaviour: the "running" payload is returned and the model
# may still poll get_process_status.
EXEC_SYNC = os.getenv("OT_EXEC_SYNC", "1") not in ("0", "false", "False", "")
EXEC_SYNC_MAX = float(os.getenv("OT_EXEC_SYNC_MAX", "120"))
EXEC_POLL = float(os.getenv("OT_EXEC_POLL", "0.4"))

# Per-session working directory. OpenWebUI's file browser POSTs the directory
# the user navigates to (GET/POST <url>/files/cwd, keyed by X-Session-Id), and
# OWUI reads it back to tell the model "current working directory is: X".
# Upstream open-terminal does NOT implement /files/cwd, so the whole feature is
# dead: the user's browsed folder never reaches the model and every run_command
# executes in the server default (/home/user). We implement it here AND inject
# the tracked cwd into run_command so files actually land where the user is.
HOME_DIR = os.getenv("OT_HOME", "/home/user")
_cwd_by_session: dict[str, str] = {}


def _safe_cwd(path: str | None) -> str | None:
    """Normalise and confine a cwd to HOME_DIR (no escaping the sandbox home)."""
    if not isinstance(path, str) or not path.strip():
        return None
    p = os.path.normpath(path.strip())
    if p == HOME_DIR or p.startswith(HOME_DIR + "/"):
        return p
    return None

# Image generation: the sandbox helper (gpdeck.gen_image) POSTs a prompt here;
# this proxy holds NO secret of its own — it reads the OpenRouter base_url + key
# straight from OpenWebUI's `config` table (openai.api_base_urls / openai.api_keys,
# the entry whose base url contains openrouter.ai). So the API key lives in exactly
# one place (the OWUI DB) and NEVER reaches the sandbox, where any user could read it.
IMAGE_MODEL = os.getenv("OT_IMAGE_MODEL", "google/gemini-3.1-flash-image")
IMAGE_TIMEOUT = float(os.getenv("OT_IMAGE_TIMEOUT", "120"))
_or_creds_cache: tuple[str, str, float] | None = None
_OR_TTL = 300

# Commands only admins may run. Case-insensitive. Override via OT_BLOCK_REGEX.
DEFAULT_BLOCK = (
    r"(?:^|[\s;|&`$(){}<>])"                      # start or a shell separator
    r"(?:"
    r"sudo|su|doas"                               # any privilege escalation
    r"|apt|apt-get|aptitude|dpkg|snap|apk|add-apt-repository"
    r"|pip[0-9.]*\s+install|pipx\s+install"
    r"|python[0-9.]*\s+-m\s+pip\s+install"
    r"|uv\s+(?:pip\s+)?install|uv\s+add"
    r"|conda\s+install|mamba\s+install"
    r"|npm\s+(?:install|i|add)|pnpm\s+(?:install|i|add)|yarn\s+add"
    r"|gem\s+install|cargo\s+install|go\s+install"
    r")\b"
)
# `or` (not getenv default) so an empty env value falls back instead of
# compiling an empty pattern that would match — and block — everything.
BLOCK_RE = re.compile(os.getenv("OT_BLOCK_REGEX") or DEFAULT_BLOCK, re.IGNORECASE)

# Paths whose JSON body carries a shell command to inspect.
FILTER_PREFIXES = ("/execute",)

# Returned INSTEAD OF running a blocked command: the session is NOT rejected —
# the command is replaced by an echo of this message, so open-terminal returns
# it as normal output and the model relays it to the user.
BLOCK_MSG = (
    "Siam vartotojui nesuteikta teise diegti programas ar vykdyti "
    "privilegijuotas (sudo) komandas - tai gali tik administratorius. "
    "Naudokite jau idiegtas bibliotekas arba kreipkites i administratoriu. "
    "(This user is not permitted to install software or run privileged/sudo "
    "commands; only an administrator can.)"
)

# Hop-by-hop headers not to forward.
_STRIP = {
    "host", "content-length", "connection", "keep-alive",
    "transfer-encoding", "upgrade",
}

# openapi_url/docs/redoc disabled so FastAPI does NOT serve its own schema at
# /openapi.json. OpenWebUI fetches <connection.url>/openapi.json to discover the
# terminal's tools (run_command, list_files, ...); if FastAPI answered with its
# OWN schema (just /_healthz + the generic catch-all) OpenWebUI would register
# garbage tools and the model's run_command call would come back
# 'Tool "run_command" not found'. With these disabled, /openapi.json falls
# through to the catch-all below and is proxied to the real open-terminal.
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
_pool: asyncpg.Pool | None = None
_role_cache: dict[str, tuple[str | None, float]] = {}


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=4)
    return _pool


async def _role_of(user_id: str | None) -> str | None:
    """Return the OpenWebUI role ('admin'/'user'/...) for a user id, cached."""
    if not user_id:
        return None
    now = time.time()
    hit = _role_cache.get(user_id)
    if hit and now - hit[1] < ROLE_TTL:
        return hit[0]
    role = None
    try:
        pool = await _get_pool()
        async with pool.acquire() as con:
            row = await con.fetchrow('SELECT role FROM "user" WHERE id = $1', user_id)
        role = row["role"] if row else None
    except Exception:
        # Fail closed: if we cannot verify the role, treat as non-admin.
        role = None
    _role_cache[user_id] = (role, now)
    return role


def _extract_command(body: bytes) -> str | None:
    if not body:
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("command", "input", "cmd"):
        val = data.get(key)
        if isinstance(val, str):
            return val
    return None


@app.get("/_healthz")
async def healthz():
    return {"ok": True}


@app.get("/files/cwd")
async def get_cwd(request: Request):
    """Return the tracked working directory for this chat session (X-Session-Id).

    OpenWebUI reads this to tell the model where it is; the file browser reads it
    to show the current folder. Falls back to HOME_DIR when nothing is tracked.
    """
    sid = request.headers.get("x-session-id") or ""
    return {"cwd": _cwd_by_session.get(sid) or HOME_DIR, "home": HOME_DIR}


@app.post("/files/cwd")
async def set_cwd(request: Request):
    """Set the working directory for this chat session (the folder the user
    navigated to in the file browser). Confined to HOME_DIR."""
    sid = request.headers.get("x-session-id") or ""
    try:
        data = json.loads(await request.body() or b"{}")
    except Exception:
        data = {}
    p = _safe_cwd(data.get("path"))
    if p is None:
        return JSONResponse({"error": "invalid path", "home": HOME_DIR}, status_code=400)
    if sid:
        _cwd_by_session[sid] = p
    return {"cwd": p, "home": HOME_DIR}


async def _openrouter_creds() -> tuple[str, str]:
    """(base_url, api_key) for OpenRouter, read from OpenWebUI's config table.

    Returns ('', '') if not configured. Cached for _OR_TTL seconds.
    """
    global _or_creds_cache
    now = time.time()
    if _or_creds_cache and now - _or_creds_cache[2] < _OR_TTL:
        return _or_creds_cache[0], _or_creds_cache[1]
    base, key = "", ""
    try:
        pool = await _get_pool()
        async with pool.acquire() as con:
            urls_row = await con.fetchval(
                "SELECT value FROM config WHERE key = 'openai.api_base_urls'"
            )
            keys_row = await con.fetchval(
                "SELECT value FROM config WHERE key = 'openai.api_keys'"
            )
        urls = json.loads(urls_row) if isinstance(urls_row, str) else (urls_row or [])
        keys = json.loads(keys_row) if isinstance(keys_row, str) else (keys_row or [])
        for i, u in enumerate(urls):
            if isinstance(u, str) and "openrouter.ai" in u:
                base = u.rstrip("/")
                key = keys[i] if i < len(keys) and isinstance(keys[i], str) else ""
                break
    except Exception:
        base, key = "", ""
    _or_creds_cache = (base, key, now)
    return base, key


@app.post("/genimage")
async def genimage(request: Request):
    """Generate an image via the OpenRouter Gemini image model.

    Body: {"prompt": "...", "model"?: "...", "size"?: "1024x1024"}
    Returns: {"b64": "<base64 png>", "mime": "image/png"}
    Any authenticated OWUI user may call this (image generation is not a
    privileged action); the sandbox reaches it in-network without the key.
    """
    try:
        data = json.loads(await request.body() or b"{}")
    except Exception:
        return JSONResponse({"error": "invalid json body"}, status_code=400)
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "missing prompt"}, status_code=400)
    # SECURITY: pin to the configured image model; ignore any client-supplied
    # "model". This endpoint is keyless and reachable in-network, so honouring an
    # arbitrary model would let anyone invoke an expensive OpenRouter model on the
    # operator's key (cost abuse).
    model = IMAGE_MODEL

    base, key = await _openrouter_creds()
    if not base or not key:
        return JSONResponse(
            {"error": "OpenRouter not configured in OpenWebUI (openai.api_keys)"},
            status_code=503,
        )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=IMAGE_TIMEOUT) as cx:
            r = await cx.post(f"{base}/chat/completions", json=payload, headers=headers)
    except Exception as e:
        return JSONResponse({"error": f"upstream request failed: {e}"}, status_code=502)
    if r.status_code != 200:
        return JSONResponse(
            {"error": f"image model returned {r.status_code}", "detail": r.text[:500]},
            status_code=502,
        )
    try:
        msg = r.json()["choices"][0]["message"]
        imgs = msg.get("images") or []
        url = imgs[0]["image_url"]["url"] if imgs else None
    except Exception:
        url = None
    if not url or "base64," not in url:
        return JSONResponse(
            {"error": "no image in model response"}, status_code=502
        )
    header, b64 = url.split("base64,", 1)
    mime = "image/png"
    if header.startswith("data:") and ";" in header:
        mime = header[5:].split(";", 1)[0] or mime
    return {"b64": b64, "mime": mime}


@app.websocket("/{path:path}")
async def ws_proxy(client: WebSocket, path: str):
    # WS carries identity in the query (?user_id=...). Only admins get a live
    # shell. A non-admin is not hard-rejected: accept, write the policy message
    # into the terminal, then close cleanly so the panel shows why.
    user_id = client.query_params.get("user_id")
    role = await _role_of(user_id)
    if role != "admin":
        try:
            await client.accept()
            await client.send_text("\r\n" + BLOCK_MSG + "\r\n")
        except Exception:
            pass
        finally:
            try:
                await client.close(code=1000)
            except Exception:
                pass
        return

    await client.accept()
    qs = client.url.query
    up_url = UPSTREAM.replace("http://", "ws://").replace("https://", "wss://")
    up_url = f"{up_url}/{path}" + (f"?{qs}" if qs else "")
    fwd_headers = [
        (k, v) for k, v in client.headers.items()
        if k.lower() not in _STRIP and k.lower() != "sec-websocket-key"
        and not k.lower().startswith("sec-websocket")
    ]
    try:
        async with websockets.connect(
            up_url, additional_headers=fwd_headers, max_size=None
        ) as upstream:
            async def c2u():
                try:
                    while True:
                        msg = await client.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if (t := msg.get("text")) is not None:
                            await upstream.send(t)
                        elif (b := msg.get("bytes")) is not None:
                            await upstream.send(b)
                except Exception:
                    pass

            async def u2c():
                try:
                    async for msg in upstream:
                        if isinstance(msg, bytes):
                            await client.send_bytes(msg)
                        else:
                            await client.send_text(msg)
                except Exception:
                    pass

            done, pending = await asyncio.wait(
                {asyncio.create_task(c2u()), asyncio.create_task(u2c())},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
    except Exception:
        pass
    finally:
        try:
            await client.close()
        except Exception:
            pass


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def http_proxy(request: Request, path: str):
    body = await request.body()
    full_path = "/" + path

    # Enforce the command policy for non-admins on the execution endpoints.
    # Instead of rejecting the request, rewrite the offending command to an
    # `echo` of the policy message: open-terminal runs it and returns the message
    # as normal command output, which the model relays back to the user — the
    # session is not broken, the user is simply told they lack the permission.
    if request.method == "POST" and full_path.startswith(FILTER_PREFIXES):
        role = await _role_of(request.headers.get("x-user-id"))
        if role != "admin":
            data = None
            if body:
                try:
                    data = json.loads(body)
                except Exception:
                    data = None
            # FAIL-CLOSED: only pass through unchanged if we could parse the body AND
            # every command-bearing field is policy-clean. Anything we can't vet
            # (non-JSON / form-encoded / aliased or nested field) is BLOCKED, not
            # forwarded unchecked — the old code only filtered when isinstance(dict),
            # so a non-dict body slipped past the whole policy.
            allow = isinstance(data, dict)
            if isinstance(data, dict):
                for key in ("command", "input", "cmd"):
                    val = data.get(key)
                    if isinstance(val, str) and BLOCK_RE.search(val):
                        allow = False
                        break
            if not allow:
                if isinstance(data, dict):
                    for key in ("command", "input", "cmd"):
                        if isinstance(data.get(key), str):
                            data[key] = "echo " + shlex.quote(BLOCK_MSG)
                    body = json.dumps(data).encode()
                else:
                    body = json.dumps(
                        {"command": "echo " + shlex.quote(BLOCK_MSG)}).encode()

    # Inject the session's tracked cwd into run_command when the model didn't
    # set one, so commands execute in the folder the user navigated to in the
    # file browser (not the /home/user default) — files land where the user is.
    is_run = request.method == "POST" and full_path == "/execute"
    if is_run:
        sid = request.headers.get("x-session-id") or ""
        tracked = _cwd_by_session.get(sid)
        if tracked and body:
            try:
                data = json.loads(body)
            except Exception:
                data = None
            if isinstance(data, dict) and not data.get("cwd"):
                data["cwd"] = tracked
                body = json.dumps(data).encode()

    url = f"{UPSTREAM}{full_path}"
    fwd_headers = {k: v for k, v in request.headers.items() if k.lower() not in _STRIP}
    async with httpx.AsyncClient(timeout=None) as cx:
        upstream = await cx.request(
            request.method, url, params=request.query_params,
            content=body, headers=fwd_headers,
        )
        # run_command -> block until the process finishes (or EXEC_SYNC_MAX),
        # returning the full output in this single response so the model never
        # has to poll get_process_status. See EXEC_SYNC note above.
        if EXEC_SYNC and is_run and upstream.status_code == 200:
            try:
                data = upstream.json()
            except Exception:
                data = None
            if isinstance(data, dict) and data.get("id") and data.get("status") == "running":
                pid = data["id"]
                deadline = time.time() + EXEC_SYNC_MAX
                last = data
                while time.time() < deadline:
                    await asyncio.sleep(EXEC_POLL)
                    try:
                        st = await cx.get(
                            f"{UPSTREAM}/execute/{pid}/status", headers=fwd_headers
                        )
                    except Exception:
                        break
                    if st.status_code != 200:
                        break
                    try:
                        last = st.json()
                    except Exception:
                        break
                    if last.get("status") != "running":
                        break
                return JSONResponse(last, status_code=200)
    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in _STRIP and k.lower() != "content-encoding"
    }
    return Response(
        content=upstream.content, status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )
