# -*- coding: utf-8 -*-
"""Startup warm-up: force every lazily-loaded local model into memory BEFORE the
front door (guardproxy) lets regular users in.

Writes a readiness marker (`/state/ready`) that guardproxy's nginx checks — until
it exists, users get a friendly "warming up" page instead of a cold first request.

Design:
  - Clear the marker first (a stale one from a previous run must not open the gate).
  - Warm the REQUIRED targets (gliner, docling, LM Studio) with retries; these
    block readiness.
  - Warm the BEST-EFFORT targets (open-webui embeddings); a failure only logs.
  - Fail-open: after MAX_TOTAL_SECONDS write the marker anyway, so a genuinely
    broken service can never leave the whole site stuck on the warming page.

External services (OpenRouter chat LLM) are not warmed — nothing loads locally for
them. Voice STT is the LOCAL gp-transcribe engine and IS warmed (see below).
"""
import base64
import io
import os
import sys
import time

import requests

MARKER = os.getenv("WARMUP_MARKER", "/state/ready")
MAX_TOTAL_SECONDS = int(os.getenv("WARMUP_MAX_SECONDS", "300"))
RETRY_SLEEP = int(os.getenv("WARMUP_RETRY_SLEEP", "5"))

GLINER_URL = os.getenv("GLINER_URL", "http://gliner:8000")
DOCLING_URL = os.getenv("DOCLING_URL", "http://docling-serve:8001")
GP_TRANSCRIBE_URL = os.getenv("GP_TRANSCRIBE_URL", "http://gp-transcribe:8000")
def _model_base_url() -> str:
    """Base URL of the local chat/vision model host.

    The deployment sets LM_STUDIO_URL (the same variable docling uses) to a FULL
    endpoint — `http://ollama:11434/v1/chat/completions` on Ubuntu,
    `http://host.docker.internal:1234/v1/chat/completions` on Windows. We need the
    base, so strip anything from `/v1` onward. LMSTUDIO_URL still wins if set
    explicitly, so an operator can override just the warm-up target.
    """
    base = os.getenv("LMSTUDIO_URL", "").strip()
    if base:
        return base.rstrip("/")
    full = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234").strip()
    i = full.find("/v1")
    return (full[:i] if i != -1 else full).rstrip("/")


LMSTUDIO_URL = _model_base_url()
LM_MODEL = os.getenv("LM_MODEL", "google/gemma-3-4b")
OPENWEBUI_URL = os.getenv("OPENWEBUI_URL", "http://open-webui-dk:8080")
OPENWEBUI_KEY = os.getenv("OPEN_WEBUI_API_KEY", "")

# 200x100 PNG with text — big enough for img2pdf (>=3 units) so it reaches
# docling's OCR/model pipeline (a 1x1 PNG fails in img2pdf before the model loads).
_WARM_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAMgAAABkCAIAAABM5OhcAAAD2klEQVR4nO3dPUhybRjA8ePbA2YROfT0AdFQuEVhU0oiDRVBSA0agaE5RQRBQ1s0RYRQQ0HhYEMNDUHU0BARFAQFUZO0NFSnJcEgJ6WP6x3kjXiEZznvZRD/33TOfd+ecw9/DqLDsYmIAfzf/vnuDeBnIiyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyoICyosBrW1dVVb29vd3d3T0+PaZqpVGptba0w5XQ6/1hcPIIfS6xpb283TVNEdnZ2QqHQ16nq6uo/FheP4Key+sRKp9O5XM4wjEAgMDk5aRQ9lp6engKBgM/ni0ajhRG32317e2sYRjabdblcIuJ0OmOxWEtLy/r6ejgcbm5uXl5eNgwjlUp1dXW1trYWTldWVtxud0dHx+HhocVtQ53FMDc2Nurr62Ox2PHxcWHk87FUOAiHw1tbWyKyu7trt9tFZHFxMR6Pi8j29vbMzIyI2O328/Pz+/t7m812cXFxd3fX0NAgIuPj46enp5lMpnD6+/fvbDZ7c3MzOjpqcdvQZjUsEXl+fk4mk21tbXNzc1IUVmNjYy6XE5HX19eKigoReXh48Pl8IjIyMnJ9fS0iDofj7e1NROx2+/v7++dns9lsIpGYmZmprKwUkUgkMjg4eHh4aH3P0GYprHQ6fXZ29nlcV1cnRWHV1tYWwsrn8w6HozDl9/sfHx89Hs/XlcUHfX19iUTCNM2qqqrC+MnJydDQUDQatbJtlICl71g2my0UCpmmaRhGJpNpamoqXuP1evf29gzD2N3dlf/ejTg8PDw9Pd3f3//3619eXoZCoVwul8/nX15e/H6/x+PZ3Nw8ODiwsm2UwC8rH66pqUkkEsFg0OFwlJWVJZPJr7Mul2thYWFpaSkSiayurnq9XrvdXpgKBoNTU1Pz8/N/v/7ExITX621vb3c6neXl5QMDA52dnR8fH7Ozs1a2jRKwyXe8YdU0zbGxsaOjo9LfGqXxDb+87+/vBwKBeDxe+lujZL7niYUfj/8KoYKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoIKwoOJfZxpSbsaVXCEAAAAASUVORK5CYII="
)


def log(msg):
    print(f"[warmup] {msg}", flush=True)


def warm_gliner():
    r = requests.post(f"{GLINER_URL}/analyze",
                      json={"text": "Šildymas Jonas Petraitis.", "labels": ["person"]},
                      timeout=180)
    r.raise_for_status()
    return "gliner NER model loaded"


def warm_docling():
    r = requests.post(f"{DOCLING_URL}/convert",
                      files={"file": ("warm.png", io.BytesIO(_WARM_PNG), "image/png")},
                      timeout=300)
    # A 5xx means the convert pipeline itself failed (model not really up) — retry.
    # 2xx/4xx means docling processed the request and its models are loaded.
    if r.status_code >= 500:
        r.raise_for_status()
    return f"docling reached (HTTP {r.status_code}) — models loaded"


def warm_lmstudio():
    # Optional local chat/vision host: LM Studio (Windows) or the in-stack ollama
    # (Ubuntu, profile-gated). Probe with a SHORT connect timeout first — when
    # nothing listens this fails in milliseconds instead of stalling the run.
    try:
        requests.get(f"{LMSTUDIO_URL}/v1/models", timeout=(2, 5))
    except requests.exceptions.RequestException:
        return (f"skipped — no local model host at {LMSTUDIO_URL} "
                f"(normal on Ubuntu: chat uses OpenRouter, vision uses the ollama profile)")
    r = requests.post(f"{LMSTUDIO_URL}/v1/chat/completions",
                      json={"model": LM_MODEL,
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 1, "stream": False},
                      timeout=300)
    r.raise_for_status()
    return f"local chat model '{LM_MODEL}' loaded"


def warm_gp_transcribe():
    # The meeting-transcription engine loads the Lithuanian ASR model (svogunas CT2)
    # into GPU memory at container startup; /health flips to 200 only once it is
    # resident. We wait for that so the first real transcription isn't cold. /health
    # is exempt from the license gate, so this works regardless of license state (an
    # inactive license disables transcription itself, not the model load).
    r = requests.get(f"{GP_TRANSCRIBE_URL}/health", timeout=180)
    r.raise_for_status()
    j = r.json()
    if j.get("status") != "ok":
        raise RuntimeError(f"gp-transcribe not ok: {j}")
    return f"gp-transcribe ASR model loaded ({j.get('model', '?')})"


def _ow_headers():
    return {"Authorization": f"Bearer {OPENWEBUI_KEY}"}


def warm_embedding_model():
    # Force the RAG embedding model (e.g. BAAI/bge-m3, ~2 GB) resident. The
    # embedding-config *update* handler calls get_ef() → loads the model into
    # app.state.ef. So we GET the current config and POST it back UNCHANGED: a
    # no-op round-trip that instantiates the model. Data-independent — works on a
    # fresh install with zero documents (unlike embedding a query against a
    # collection, which needs indexed data to exercise anything).
    if not OPENWEBUI_KEY:
        return "skipped (no OPEN_WEBUI_API_KEY)"
    h = _ow_headers()
    cur = requests.get(f"{OPENWEBUI_URL}/api/v1/retrieval/embedding", headers=h, timeout=30)
    cur.raise_for_status()
    c = cur.json()
    # /embedding/update reads every field directly (not "if None keep"), so echo
    # them all back verbatim.
    body = {
        "RAG_EMBEDDING_ENGINE": c.get("RAG_EMBEDDING_ENGINE", ""),
        "RAG_EMBEDDING_MODEL": c.get("RAG_EMBEDDING_MODEL", ""),
        "RAG_EMBEDDING_BATCH_SIZE": c.get("RAG_EMBEDDING_BATCH_SIZE", 1),
        "ENABLE_ASYNC_EMBEDDING": c.get("ENABLE_ASYNC_EMBEDDING", True),
        "RAG_EMBEDDING_CONCURRENT_REQUESTS": c.get("RAG_EMBEDDING_CONCURRENT_REQUESTS", 0),
        "openai_config": c.get("openai_config"),
        "ollama_config": c.get("ollama_config"),
        "azure_openai_config": c.get("azure_openai_config"),
    }
    r = requests.post(f"{OPENWEBUI_URL}/api/v1/retrieval/embedding/update",
                      json=body, headers=h, timeout=600)
    r.raise_for_status()
    return f"embedding model '{body['RAG_EMBEDDING_MODEL']}' loaded"


def warm_reranker():
    # Force the reranking cross-encoder (e.g. BAAI/bge-reranker-v2-m3) resident.
    # The retrieval-config update handler calls get_rf() whenever hybrid search is
    # enabled → loads the reranker into app.state.rf. Post a MINIMAL body (this
    # handler keeps any field left None), so we only echo the reranker identity +
    # the hybrid flag and touch nothing else.
    if not OPENWEBUI_KEY:
        return "skipped (no OPEN_WEBUI_API_KEY)"
    h = _ow_headers()
    cur = requests.get(f"{OPENWEBUI_URL}/api/v1/retrieval/config", headers=h, timeout=30)
    cur.raise_for_status()
    c = cur.json()
    if not c.get("ENABLE_RAG_HYBRID_SEARCH") or not c.get("RAG_RERANKING_MODEL"):
        return "skipped (hybrid search / reranker not configured)"
    body = {
        "RAG_RERANKING_ENGINE": c.get("RAG_RERANKING_ENGINE", ""),
        "RAG_RERANKING_MODEL": c.get("RAG_RERANKING_MODEL", ""),
        "ENABLE_RAG_HYBRID_SEARCH": True,
    }
    r = requests.post(f"{OPENWEBUI_URL}/api/v1/retrieval/config/update",
                      json=body, headers=h, timeout=600)
    r.raise_for_status()
    return f"reranker '{body['RAG_RERANKING_MODEL']}' loaded"


# The local chat/vision model host is OPTIONAL and platform-specific: LM Studio is
# a Windows-side app, while Ubuntu uses the in-stack `ollama` service, which is
# profile-gated and therefore not running by default. Keeping it REQUIRED made the
# gate hold every Ubuntu deployment on the "warming up" page for the full
# WARMUP_MAX_SECONDS (5 min) with a wall of "Connection refused", because nothing
# listens on host.docker.internal:1234 there. It is best-effort now: if the host
# is reachable we warm it, otherwise we note it and move on. The chat LLM itself
# is external (OpenRouter) — nothing local has to load for chat to work.
REQUIRED = [("gliner", warm_gliner), ("docling", warm_docling),
            ("gp-transcribe", warm_gp_transcribe)]
BEST_EFFORT = [("local-chat-model", warm_lmstudio),
               ("embedding-model", warm_embedding_model), ("reranker", warm_reranker)]


def main():
    # A stale marker from a previous boot must not open the gate early.
    try:
        os.remove(MARKER)
        log("cleared stale marker")
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(MARKER), exist_ok=True)

    deadline = time.time() + MAX_TOTAL_SECONDS
    done = set()
    while time.time() < deadline:
        for name, fn in REQUIRED:
            if name in done:
                continue
            try:
                log(f"warming {name} …")
                log(f"  ✓ {fn()}")
                done.add(name)
            except Exception as e:
                log(f"  … {name} not ready yet: {e}")
        if len(done) == len(REQUIRED):
            break
        time.sleep(RETRY_SLEEP)

    if len(done) != len(REQUIRED):
        log(f"TIMEOUT after {MAX_TOTAL_SECONDS}s — opening the gate anyway "
            f"(warmed: {sorted(done)}). First request to a cold service may be slow.")

    for name, fn in BEST_EFFORT:
        try:
            log(f"warming {name} (best-effort) …")
            log(f"  ✓ {fn()}")
        except Exception as e:
            log(f"  … {name} best-effort failed: {e}")

    with open(MARKER, "w") as f:
        f.write(str(int(time.time())))
    log(f"READY — marker written at {MARKER}. Gate open.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Never leave the site permanently gated because warmup itself crashed.
        log(f"FATAL {e} — opening gate as a safety fallback")
        try:
            os.makedirs(os.path.dirname(MARKER), exist_ok=True)
            open(MARKER, "w").write("fallback")
        except Exception:
            pass
        sys.exit(0)
