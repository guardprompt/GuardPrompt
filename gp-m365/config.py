"""gp-m365 configuration. Everything is env-driven; the placeholders below are safe
defaults so the scaffold imports and boots WITHOUT the Entra app existing yet. Fill the
ENTRA_* values in .env once the delegated add-in app is registered (README).

Design rule baked in here: this service NEVER stores fetched M365 content. The only
persisted state is the reversible pseudonym Vault (shared with gp-openai-proxy, TTL-pruned)
so tokens map back for the user — no personal document text is ever written to disk/DB.
"""
import os


def _b(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# --- Entra / Microsoft Graph (PLACEHOLDERS — fill after registering the delegated app) ---
ENTRA_TENANT_ID = os.getenv("M365_TENANT_ID", "REPLACE_WITH_TENANT_ID")
ENTRA_CLIENT_ID = os.getenv("M365_CLIENT_ID", "REPLACE_WITH_CLIENT_ID")
# The OBO middle-tier secret. NEVER hard-code — read from .env only. Empty = the service
# starts but /answer fails closed with a clear "not configured" error (see app.py).
ENTRA_CLIENT_SECRET = os.getenv("M365_CLIENT_SECRET", "")
# Scope the add-in's SSO token is issued for (Expose an API → access_as_user).
API_SCOPE = os.getenv("M365_API_SCOPE", "access_as_user")
GRAPH_BASE = os.getenv("M365_GRAPH_BASE", "https://graph.microsoft.com/v1.0").rstrip("/")
AAD_AUTHORITY = os.getenv("M365_AUTHORITY", "https://login.microsoftonline.com")

# Delegated Graph scopes requested in the OBO exchange (least-privilege; must match the
# app registration's granted delegated permissions).
GRAPH_SCOPES = os.getenv(
    "M365_GRAPH_SCOPES",
    "User.Read Mail.Read Files.Read.All Sites.Read.All",
).split()

# DEV/TEST ONLY: paste a Graph access token (e.g. from Graph Explorer signed into the test
# tenant) to bypass the OBO exchange and test the search→fetch→anon→rerank→LLM pipeline
# WITHOUT the add-in SSO wired. NEVER set in production — it's a static user token. When
# set, /answer uses it directly instead of exchanging the SSO assertion.
DEV_GRAPH_TOKEN = os.getenv("GP_M365_DEV_GRAPH_TOKEN", "")

# --- Reused internal services (NO new models — call what already runs) -------------------
# NER: gliner's /analyze returns {entities:[{type,text,start,end,score}]}. gp-m365 turns
# those spans into REVERSIBLE GP_ tokens itself (keeps a per-request map to restore real
# values for the user) — gliner's own `redacted` field is non-reversible so we don't use it.
NER_URL = os.getenv("GP_NER_URL", "http://gliner:8000/analyze")
# Injection screening for UNTRUSTED fetched M365 docs: gliner /injection returns flagged
# {spans} (offsets into the original) which we replace with [PROTECTION] before the LLM.
INJECTION_URL = os.getenv("GP_INJECTION_URL", "http://gliner:8000/injection")
# Reranker (optional): pick the few fragments that matter so the LLM sees a few hundred
# tokens, not whole docs. Empty => skip reranking and take the first MAX_FRAGMENTS chunks
# (still cheap). Point at the deployed bge-reranker endpoint when available.
RERANKER_URL = os.getenv("GP_RERANKER_URL", "")
# Final answer LLM — go through OWUI so gp-pipeline governance still applies. The service
# passes ALREADY-ANONYMIZED text, so nothing raw reaches the external model.
LLM_URL = os.getenv("GP_M365_LLM_URL", "http://open-webui-dk:8080/api/chat/completions")
LLM_MODEL = os.getenv("GP_M365_MODEL", "regitra-browser")

# --- Cost / resource guards (the "taupytų" knobs) --------------------------------------
# Cheap RAG is the DEFAULT: one search, one LLM call. The agentic multi-round loop is a
# capped fallback for genuinely multi-hop questions only.
MAX_ITERS = int(os.getenv("GP_M365_MAX_ITERS", "2"))          # hard ceiling on agent rounds
TOP_DOCS = int(os.getenv("GP_M365_TOP_DOCS", "5"))            # max documents fetched
SEARCH_HITS = int(os.getenv("GP_M365_SEARCH_HITS", "15"))    # Graph search candidates
MAX_FRAGMENTS = int(os.getenv("GP_M365_MAX_FRAGMENTS", "6"))  # reranked chunks to the LLM
MAX_FRAGMENT_CHARS = int(os.getenv("GP_M365_MAX_FRAGMENT_CHARS", "1200"))
MAX_DOC_BYTES = int(os.getenv("GP_M365_MAX_DOC_BYTES", str(2 * 1024 * 1024)))  # skip huge files
# Bounded concurrency so N users can't melt the shared GPU / blow the LLM budget.
MAX_CONCURRENCY = int(os.getenv("GP_M365_CONCURRENCY", "4"))
# Per-user daily LLM-call budget (cheap floor against a runaway client / loop).
USER_DAILY_CALLS = int(os.getenv("GP_M365_USER_DAILY_CALLS", "300"))

# --- Timeouts (nothing runs away) -------------------------------------------------------
HTTP_TIMEOUT = float(os.getenv("GP_M365_HTTP_TIMEOUT", "30"))
LLM_TIMEOUT = float(os.getenv("GP_M365_LLM_TIMEOUT", "120"))

# --- Session / cleanup (the "tvarkytųsi" knobs) ----------------------------------------
# In-memory per-request state (Graph token cache, reversible map handles) is evicted after
# this TTL so memory stays bounded even if a client never comes back.
SESSION_TTL_SEC = int(os.getenv("GP_M365_SESSION_TTL_SEC", "1800"))
# Fail-closed switch: if anonymization is unavailable, REFUSE (never send raw to the LLM).
FAIL_CLOSED = _b("GP_M365_FAIL_CLOSED", "true")

PORT = int(os.getenv("GP_M365_PORT", "8015"))   # 8014 is taken by gp-websearch


def entra_configured() -> bool:
    """True only when the delegated app is actually wired — /answer checks this and fails
    closed with a friendly message instead of making a doomed Graph call."""
    return (
        ENTRA_CLIENT_SECRET
        and "REPLACE_WITH" not in ENTRA_TENANT_ID
        and "REPLACE_WITH" not in ENTRA_CLIENT_ID
    )
