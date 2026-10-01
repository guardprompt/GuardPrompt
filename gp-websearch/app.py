"""gp-websearch — adapter that exposes OpenWebUI's "External" web-search API and fulfils it
via OpenRouter's built-in web search (Exa/Parallel). Lets any OWUI model use the on-demand
web-search toggle, backed by the existing OpenRouter account — no separate search API key,
no searxng, no dedicated online model.

OWUI (External engine) --POST /search {query,count}--> here --OpenRouter web plugin-->
      annotations(url_citation) --> [{link,title,snippet}] --> OWUI injects as context.
"""
import os

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
# Cheap model just to carry the web plugin; its text answer is ignored — we only read citations.
MODEL = os.environ.get("WEBSEARCH_MODEL", "google/gemini-3.5-flash-lite")
ENGINE = os.environ.get("WEBSEARCH_ENGINE", "exa")  # exa | parallel | auto
# Shared secret OWUI sends as "Authorization: Bearer <key>". Empty = no auth check.
AUTH_KEY = os.environ.get("WEBSEARCH_AUTH_KEY", "")
TIMEOUT = float(os.environ.get("WEBSEARCH_TIMEOUT", "30"))

app = FastAPI(title="gp-websearch")


class SearchIn(BaseModel):
    query: str
    count: int = 5


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "engine": ENGINE, "key": bool(OPENROUTER_API_KEY)}


@app.post("/search")
async def search(body: SearchIn, authorization: str = Header(default="")):
    if AUTH_KEY and authorization != f"Bearer {AUTH_KEY}":
        raise HTTPException(status_code=401, detail="unauthorized")
    if not OPENROUTER_API_KEY:
        # OWUI expects an array; empty means "no results" (fail-soft, no crash).
        return []
    n = max(1, min(int(body.count or 5), 10))
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": (body.query or "").strip()[:2000]}],
        "max_tokens": 16,  # we don't use the answer, only the web citations
        "plugins": [{"id": "web", "max_results": n, "engine": ENGINE}],
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
            r = await cli.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
    except Exception:
        return []
    if r.status_code != 200:
        return []

    msg = ((r.json().get("choices") or [{}])[0] or {}).get("message") or {}
    results, seen = [], set()
    for a in (msg.get("annotations") or []):
        if a.get("type") != "url_citation":
            continue
        c = a.get("url_citation") or a  # OpenAI schema nests under url_citation; tolerate flat too
        url = c.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "link": url,
            "title": (c.get("title") or url)[:300],
            "snippet": (c.get("content") or "")[:600],
        })
        if len(results) >= n:
            break
    return results
