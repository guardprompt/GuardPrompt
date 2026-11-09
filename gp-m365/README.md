# gp-m365 — delegated M365 grounding (Office add-in Track C / 1B)

Server-side engine behind the add-in's **"use all my documents"** action. Searches the
signed-in user's own M365 via Microsoft Graph (delegated), anonymizes what it finds, and
answers with **one** LLM call over reranked fragments.

## Why a separate service

Three things MUST be server-side and can't live in the add-in (browser):
1. **OBO exchange** uses the Entra **client secret** — never ship to a browser.
2. **Reversible anonymization** — the trust boundary; the LLM must never see raw PII, and
   the token↔value map is held here, not in the client.
3. **Reranker / injection-scan** run on the server GPU.

It is a **separate least-privilege service** from kb-admin/brand-kit: those use an
**app-only** (client-credentials) app that reads SharePoint as a service; this one uses
**delegated + OBO** so it acts as the user and sees only what that user can. Isolated
secret, isolated blast radius.

## Cheap by design

`search (Graph, free) → fetch top docs → injection-scan → anonymize → rerank (local, free)
→ ONE LLM call on a few fragments → de-anonymize`. Free local tools do the finding/selecting;
the paid LLM sees only a handful of small, anonymized fragments (~one query ≈ ~1 cent).
The agentic multi-round loop is a **capped** fallback (`GP_M365_MAX_ITERS`), not the default.

## Never litters

- Fetched M365 content is **never stored** — on-demand only, no second copy (GDPR).
- No new Qdrant collections / DB rows for personal content.
- Reversible map reuses the existing **Vault** (TTL-pruned) — bounded, self-cleaning.
- No temp files; **no PII in logs** (counts/tokens only).

## Cleans up

- ONE pooled httpx client (startup) → closed on shutdown.
- Bounded concurrency semaphore + per-user daily budget.
- Periodic janitor evicts expired OBO tokens + stale usage rows → flat memory.
- **Fail-closed**: if anonymization is down, `/answer` returns 503 and NEVER calls the LLM.

## Status = SCAFFOLD

Boots and answers `/health` today. `/answer` returns **503 "not configured"** until the
Entra app exists and `.env` is filled. The Graph search/fetch calls in `graph.py` are
marked `TODO(wire)` — the shapes are real, wiring is fill-in.

## To finish (once the delegated Entra app is registered)

1. Set in `.env`: `M365_TENANT_ID`, `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_API_SCOPE`.
2. Wire `graph.search` / `graph.fetch` (uncomment + adjust the Graph calls).
3. Point `_anonymize` / `_injection_scan` at the shared Vault + injection endpoint.
4. Add a guardproxy `location = /_gp/m365` (login-gated, injects `X-GP-User`) → `gp-m365:8015/answer`.
5. Add an "use my documents" button in the add-in task pane that calls `/_gp/m365` with the
   Office SSO token (`OfficeRuntime.auth.getAccessToken`).

## Ports / network

Listens on `8015` on the internal `openwebui_net` only — **no published host port** (it
holds the Entra secret). Reached only through guardproxy over the docker network.
