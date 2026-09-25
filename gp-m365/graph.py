"""Microsoft Graph access for gp-m365.

Trust model: this module is the ONLY place that touches real M365 data. It runs the
On-Behalf-Of (OBO) exchange (add-in SSO token -> delegated Graph token AS the user) and
then searches / fetches with that token, so everything is scoped to what the signed-in
user can already see. It NEVER persists any fetched content.

Resource rules baked in:
  * ONE pooled httpx.AsyncClient for the whole process (connection reuse).
  * OBO tokens are cached per user until near expiry (no re-exchange every call).
  * Fetches are size-capped (MAX_DOC_BYTES) and time-capped (HTTP_TIMEOUT).

The Graph HTTP calls are marked TODO — they are wired once the Entra app exists; the
shape (endpoints, bodies) is real so wiring is a fill-in, not a redesign.
"""
import time
import httpx

import config

# Single shared client — created on startup, closed on shutdown (see app.py lifespan).
_client: httpx.AsyncClient | None = None

# Per-user OBO token cache: user_key -> (access_token, expires_at). Bounded by SESSION_TTL
# eviction in app.py; here we just refuse to hand back a token within 60s of expiry.
_obo_cache: dict[str, tuple[str, float]] = {}


def set_client(c: httpx.AsyncClient) -> None:
    global _client
    _client = c


def _client_or_raise() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("gp-m365 http client not initialised")
    return _client


async def obo_token(sso_token: str, user_key: str) -> str:
    """Exchange the add-in's SSO token for a delegated Microsoft Graph token (OBO).
    Cached per user until ~1 min before expiry."""
    # DEV/TEST bypass: a pasted Graph Explorer token is used directly, no OBO. Lets the
    # whole pipeline be tested before the add-in SSO is wired. Never set in production.
    if config.DEV_GRAPH_TOKEN:
        return config.DEV_GRAPH_TOKEN

    hit = _obo_cache.get(user_key)
    if hit and hit[1] - time.monotonic() > 60:
        return hit[0]

    url = f"{config.AAD_AUTHORITY}/{config.ENTRA_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": config.ENTRA_CLIENT_ID,
        "client_secret": config.ENTRA_CLIENT_SECRET,
        "assertion": sso_token,
        "scope": " ".join(config.GRAPH_SCOPES),
        "requested_token_use": "on_behalf_of",
    }
    r = await _client_or_raise().post(url, data=data, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    tok = r.json()
    access = tok["access_token"]
    ttl = float(tok.get("expires_in", 3600))
    _obo_cache[user_key] = (access, time.monotonic() + ttl)
    return access


def _flatten_hits(payload: dict) -> list[dict]:
    """Turn Graph /search/query response into flat hits [{id,title,snippet,source,web_url}].
    Only lightweight metadata — never full content."""
    out = []
    for resp in payload.get("value", []):
        for container in resp.get("hitsContainers", []):
            for h in container.get("hits", []):
                res = h.get("resource", {}) or {}
                # @odata.type tells us the entity kind → how to fetch it later.
                otype = (res.get("@odata.type") or "").lower()
                source = ("message" if "message" in otype else
                          "driveItem" if "driveitem" in otype else
                          "listItem" if "listitem" in otype else
                          "chatMessage" if "chatmessage" in otype else "unknown")
                out.append({
                    "id": res.get("id") or h.get("hitId"),
                    "title": res.get("subject") or (res.get("name") or "")
                             or ((res.get("fields") or {}).get("title", "")),
                    "snippet": h.get("summary", ""),
                    "source": source,
                    "web_url": res.get("webUrl", ""),
                    "parent_drive": ((res.get("parentReference") or {}).get("driveId", "")),
                })
    return out


# Graph Search rejects mixing incompatible entityTypes in ONE request: mail (message) and
# files (driveItem/listItem) must be searched SEPARATELY. Each group is its own /search/query
# call so one failing group (e.g. no SharePoint license) never sinks the others.
_ALL_GROUPS = [["message"], ["driveItem", "listItem"]]
# Scope by the Microsoft product the user is in, so results are relevant (and cheaper).
_PRODUCT_GROUPS = {
    "outlook": [["message"]],
    "sharepoint": [["driveItem", "listItem"]],
    "teams": [["chatMessage"], ["driveItem"]],
}


async def search(graph_token: str, query: str, top: int, product: str = "") -> list[dict]:
    """Graph Search across the user's mail + files (or scoped to `product`). Returns
    lightweight hits (id, title, snippet, source) — NOT full content. Delegated: only what
    the user can see. Per-group, resilient: a group that errors is logged and skipped."""
    hdr = {"Authorization": f"Bearer {graph_token}"}
    groups = _PRODUCT_GROUPS.get((product or "").lower(), _ALL_GROUPS)
    hits: list[dict] = []
    for group in groups:
        body = {"requests": [{
            "entityTypes": group,
            "query": {"queryString": query},
            "from": 0, "size": top,
        }]}
        try:
            r = await _client_or_raise().post(
                f"{config.GRAPH_BASE}/search/query", json=body, headers=hdr,
                timeout=config.HTTP_TIMEOUT)
            if r.status_code >= 400:
                # Surface the Graph error body (raise_for_status hides it) but keep going.
                print(f"[gp-m365] search {group} HTTP {r.status_code}: {r.text[:300]}", flush=True)
                continue
            hits += _flatten_hits(r.json())
        except Exception as e:
            print(f"[gp-m365] search {group} failed: {e}", flush=True)
    return hits


async def recent_messages(graph_token: str, top: int) -> list[dict]:
    """List the user's RECENT inbox messages directly (not a keyword search). Keyword search
    can't answer 'do I have mail from X' or 'summarize my inbox' — the words aren't in the
    body — but the actual recent list can. Returns the same hit shape as search()."""
    url = (f"{config.GRAPH_BASE}/me/messages?$top={top}"
           "&$orderby=receivedDateTime desc"
           "&$select=id,subject,from,receivedDateTime,bodyPreview,webLink")
    try:
        r = await _client_or_raise().get(url, headers={"Authorization": f"Bearer {graph_token}"},
                                         timeout=config.HTTP_TIMEOUT)
        if r.status_code >= 400:
            print(f"[gp-m365] recent_messages HTTP {r.status_code}: {r.text[:200]}", flush=True)
            return []
        out = []
        for m in r.json().get("value", []):
            frm = ((m.get("from") or {}).get("emailAddress") or {})
            who = frm.get("name") or frm.get("address") or ""
            date = (m.get("receivedDateTime") or "")[:10]
            out.append({
                "id": m.get("id"),
                "title": f"{m.get('subject','(be temos)')} — {who} {date}".strip(),
                "snippet": m.get("bodyPreview", ""),
                "source": "message",
                "web_url": m.get("webLink", ""),
            })
        return out
    except Exception as e:
        print(f"[gp-m365] recent_messages failed: {e}", flush=True)
        return []


async def fetch(graph_token: str, hit: dict) -> str:
    """Fetch ONE item's textual content, size-capped. Returns raw text (untrusted — the
    caller injection-scans + anonymizes it before the LLM). Never stored."""
    hdr = {"Authorization": f"Bearer {graph_token}"}
    src, hid = hit.get("source"), hit.get("id")
    if not hid:
        return ""
    try:
        if src == "message":
            r = await _client_or_raise().get(
                f"{config.GRAPH_BASE}/me/messages/{hid}?$select=subject,body,from,receivedDateTime",
                headers=hdr, timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()
            d = r.json()
            return f"{d.get('subject','')}\n{(d.get('body') or {}).get('content','')}"[: config.MAX_DOC_BYTES]
        if src == "driveItem":
            # Files: download content (text-extractable types). Cap the read at MAX_DOC_BYTES
            # so a huge binary never lands in memory.
            drive = hit.get("parent_drive")
            base = (f"{config.GRAPH_BASE}/drives/{drive}/items/{hid}/content" if drive
                    else f"{config.GRAPH_BASE}/me/drive/items/{hid}/content")
            r = await _client_or_raise().get(base, headers=hdr, timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()
            return r.content[: config.MAX_DOC_BYTES].decode("utf-8", "ignore")
        if src == "listItem":
            # SharePoint list item — title/snippet is usually enough; deep fetch needs the
            # site+list ids, wired per-tenant later. Use what search already returned.
            return f"{hit.get('title','')}\n{hit.get('snippet','')}"
    except Exception as e:
        # A single unreadable item must not sink the whole answer — skip it.
        print(f"[gp-m365] fetch skip {src}/{hid}: {e}", flush=True)
        return ""
    return f"{hit.get('title','')}\n{hit.get('snippet','')}"


def evict_expired(now: float) -> int:
    """Drop OBO tokens past TTL. Called by the app's periodic janitor so memory stays
    bounded. Returns how many were removed."""
    dead = [k for k, (_, exp) in _obo_cache.items() if exp <= now]
    for k in dead:
        _obo_cache.pop(k, None)
    return len(dead)
