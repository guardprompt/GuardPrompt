"""Preliminary per-model prices from OpenRouter's public /models endpoint (no key needed).

OpenRouter returns pricing.prompt / pricing.completion as USD *per token* (strings). We
cache the map, refresh once/day, and expose a EUR/token price for a gp_audit model name.
gp_audit stores whatever model string the proxy sent (e.g. "claude-sonnet-4-5", "gpt-4.1"),
which may not equal the OpenRouter id ("anthropic/claude-3.7-sonnet"), so the match is
fuzzy (normalise both, then longest-substring). Missing -> 0.0 (flagged in the UI)."""
import asyncio
import re
import time

import httpx

from . import config

_STATE = {"prices": {}, "updated": 0.0, "ok": False}  # id -> {"prompt":usd,"completion":usd}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


async def refresh() -> bool:
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.get(config.OPENROUTER_MODELS_URL)
            r.raise_for_status()
            data = r.json().get("data", [])
    except Exception as e:
        print(f"[gp-usage] price refresh failed: {e!r}", flush=True)
        return False
    prices = {}
    for m in data:
        pid = m.get("id") or ""
        pr = m.get("pricing") or {}
        try:
            prices[pid] = {"prompt": float(pr.get("prompt", 0) or 0),
                           "completion": float(pr.get("completion", 0) or 0)}
        except (TypeError, ValueError):
            continue
    if prices:
        _STATE.update(prices={**prices}, updated=time.time(), ok=True)
        print(f"[gp-usage] prices: {len(prices)} models from OpenRouter", flush=True)
        return True
    return False


async def loop():
    while True:
        await refresh()
        await asyncio.sleep(max(3600, config.PRICE_TTL))


_MATCH_CACHE: dict[str, float] = {}


def eur_per_token(model: str) -> float:
    """EUR per token (prompt price) for a gp_audit model name. 0.0 if unknown."""
    if model in _MATCH_CACHE:
        return _MATCH_CACHE[model]
    prices = _STATE["prices"]
    usd = 0.0
    if prices:
        exact = prices.get(model)
        if exact:
            usd = exact["prompt"]
        else:
            nm = _norm(model)
            best = None
            for pid, pv in prices.items():
                pn = _norm(pid)
                # match when either normalised id contains the other (drops vendor prefix,
                # version punctuation) — pick the longest such id for specificity.
                if nm and (nm in pn or pn.endswith(nm) or nm in pn.split("/")[-1] or _norm(pid.split("/")[-1]) == nm):
                    if best is None or len(pn) > len(_norm(best)):
                        best = pid
            if best:
                usd = prices[best]["prompt"]
    val = usd * config.USD_EUR
    _MATCH_CACHE[model] = val
    return val


def status() -> dict:
    return {"ok": _STATE["ok"], "updated": _STATE["updated"], "count": len(_STATE["prices"])}
