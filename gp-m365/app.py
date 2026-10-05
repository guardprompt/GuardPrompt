"""gp-m365 — delegated M365 grounding for the GuardPrompt Office add-in.

Flow:  add-in (SSO token + question) -> /answer -> OBO -> Graph search/fetch (as the user)
       -> injection-scan -> anonymize -> rerank -> ONE LLM call -> de-anonymize -> add-in.

Not public: bound to 127.0.0.1 in compose; the add-in reaches it through guardproxy (which
login-gates + injects the trusted user id). Holds the Entra client secret, so it is a
SEPARATE least-privilege service (isolated from the app-only SharePoint-sync credentials).

Resource lifecycle (the "tvarkytųsi" part) lives here: one pooled httpx client for the
whole process, a bounded concurrency semaphore, per-user daily budgets, and a periodic
janitor that evicts expired session/token state so memory stays flat.
"""
import time
import json
import base64
import asyncio
import contextlib

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

import config
import graph
import rag

app = FastAPI(title="gp-m365", docs_url=None, redoc_url=None)

# Bounded concurrency: at most MAX_CONCURRENCY answers in flight, so a crowd can't melt the
# shared GPU (reranker/NER) or blow the LLM budget. Excess requests wait, they don't pile on.
_sem = asyncio.Semaphore(config.MAX_CONCURRENCY)

# Per-user daily LLM-call budget. Cheap floor against a runaway client. Reset lazily by day.
_usage: dict[str, tuple[str, int]] = {}   # user -> (yyyymmdd, count)

# Lightweight counters for /metrics (no PII — counts only).
_m = {"answers": 0, "llm_calls": 0, "fail_closed": 0, "errors": 0, "budget_denied": 0}

_client: httpx.AsyncClient | None = None
_janitor: asyncio.Task | None = None


class AnswerReq(BaseModel):
    question: str
    # ONE of these provides the user's identity/Graph access:
    #  * graph_token — a delegated Graph token the caller already holds (browser extension
    #    via chrome.identity). Used DIRECTLY, no OBO. Preferred path.
    #  * sso_token — an Office add-in SSO token, exchanged via OBO. (legacy add-in path)
    sso_token: str = ""
    graph_token: str = ""
    # The current page's visible text (the MS product tab). Included as an extra source so
    # the answer covers what's ON SCREEN as well as the Graph search of history.
    page_context: str = ""
    # Which Microsoft product the user is in ("outlook" | "sharepoint" | "teams") — scopes
    # the Graph search. Empty = search mail + files.
    product: str = ""
    # Recent conversation turns [{role, content}] so 'reply to him' / 'this email' resolve.
    history: list = []


def _user_key(sso_token: str, header_user: str) -> str:
    """Stable per-user bucket for budgeting/audit. Prefer the guardproxy-injected header;
    else the SSO token's `oid` claim (stable per user, unlike a per-token hash). This does
    NOT verify the token — AAD verifies it during the OBO exchange; here it's only a key."""
    if header_user:
        return header_user
    try:
        payload = sso_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)          # pad base64url
        claims = json.loads(base64.urlsafe_b64decode(payload))
        oid = claims.get("oid") or claims.get("sub")
        if oid:
            return "oid:" + str(oid)
    except Exception:
        pass
    return "sso:" + str(hash(sso_token))


def _today() -> str:
    # Date bucket for the daily budget. time.gmtime avoids TZ drift; not security-sensitive.
    t = time.gmtime()
    return f"{t.tm_year:04d}{t.tm_mon:02d}{t.tm_mday:02d}"


def _charge_budget(user: str) -> bool:
    """True if the user is under today's budget (and increments). False -> deny."""
    day = _today()
    d, n = _usage.get(user, (day, 0))
    if d != day:
        n = 0
    if n >= config.USER_DAILY_CALLS:
        return False
    _usage[user] = (day, n + 1)
    return True


async def _janitor_loop():
    """Periodic cleanup so memory stays bounded even if clients never return: evict expired
    OBO tokens and stale daily-usage rows. Runs every SESSION_TTL/4."""
    interval = max(60, config.SESSION_TTL_SEC // 4)
    while True:
        await asyncio.sleep(interval)
        with contextlib.suppress(Exception):
            graph.evict_expired(time.monotonic())
            today = _today()
            for u in [u for u, (d, _) in _usage.items() if d != today]:
                _usage.pop(u, None)


@app.on_event("startup")
async def _startup():
    global _client, _janitor
    # ONE pooled client for the whole process (Graph + internal services). Connection reuse.
    _client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=config.MAX_CONCURRENCY * 4, max_keepalive_connections=16),
        timeout=config.HTTP_TIMEOUT,
    )
    graph.set_client(_client)
    _janitor = asyncio.create_task(_janitor_loop())


@app.on_event("shutdown")
async def _shutdown():
    # Clean teardown: stop the janitor, close the pooled client.
    if _janitor:
        _janitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _janitor
    if _client:
        await _client.aclose()


@app.get("/health")
async def health():
    return {"ok": True, "entra_configured": bool(config.entra_configured())}


@app.get("/metrics")
async def metrics():
    # Plain counters, no PII. Extend to Prometheus text if you wire it into monitoring.
    return JSONResponse(_m)


@app.post("/answer")
async def answer(req: AnswerReq, x_gp_user: str = Header(default=""), cookie: str = Header(default="")):
    # Identity for budgeting/audit: guardproxy header if present, else the oid claim of
    # whichever token was sent (graph_token for the extension path, else the SSO token).
    user_key = _user_key(req.graph_token or req.sso_token, x_gp_user)

    # Runnable when the caller passes a graph_token directly (extension path), OR the OBO
    # app is configured, OR a DEV token is set. Otherwise fail closed with a clear message.
    if not (req.graph_token or config.entra_configured() or config.DEV_GRAPH_TOKEN):
        raise HTTPException(503, "gp-m365 not configured: pass a graph_token, or register the "
                                 "delegated Entra app (M365_TENANT_ID / M365_CLIENT_ID / "
                                 "M365_CLIENT_SECRET), or set GP_M365_DEV_GRAPH_TOKEN.")
    if not _charge_budget(user_key):
        _m["budget_denied"] += 1
        raise HTTPException(429, "Dienos užklausų limitas pasiektas.")

    async with _sem:                      # bounded concurrency
        try:
            out = await rag.answer(_client, req.question, sso_token=req.sso_token,
                                   user_key=user_key, graph_token=req.graph_token,
                                   page_context=req.page_context, product=req.product,
                                   owui_cookie=cookie, history=req.history)
            _m["answers"] += 1
            _m["llm_calls"] += out.get("llm_calls", 0)
            return out
        except rag.AnonUnavailable:
            _m["fail_closed"] += 1
            # Never fall through to the LLM when anonymization is down.
            raise HTTPException(503, "Anonimizavimas neprieinamas — atsakymas neteikiamas (fail-closed).")
        except NotImplementedError as e:
            _m["errors"] += 1
            raise HTTPException(501, f"Graph dar neprijungtas: {e}")
        except Exception as e:
            _m["errors"] += 1
            import traceback
            print(f"[gp-m365] /answer failed: {e}\n{traceback.format_exc()}", flush=True)
            raise HTTPException(502, f"Klaida: {e}")
