<p align="center">🌐 <b>English</b> · <a href="GP-OPENAI-PROXY.lt.md">Lietuvių</a></p>

# GuardPrompt OpenAI proxy (`gp-openai-proxy`)

An **OpenAI-compatible** gateway to **OpenRouter** with **reversible** anonymization —
for developer tools that speak the OpenAI `/v1/chat/completions` protocol (Oracle SQL
Developer / SQLcl, VS Code + Continue, or any OpenAI client). It lets, for example,
PL/SQL developers use a frontier LLM without a single sensitive value leaving in the
clear.

It is a **separate service** from the Claude gateway ([GP-CLAUDE-PROXY.md](GP-CLAUDE-PROXY.md)):
Claude Code / VS Code developers keep using `gp-claude-proxy` on port 8006 unchanged;
OpenAI-protocol clients use `gp-openai-proxy` on port 8013.

## What it does

```
client  ──►  mask (reversible, per-owner vault)  ──►  OpenRouter  ──►  restore  ──►  client
```

1. Receives an OpenAI chat request.
2. **Pins the model** to `OPENROUTER_MODEL` — whatever model the caller sends is
   ignored, so no one can pick an arbitrary or expensive model.
3. **Reversibly pseudonymizes** every message: sensitive **values** become `GP_…`
   tokens (names, personal codes, emails, IBANs, GDPR Art. 9/10 categories, secrets,
   …) while ordinary identifiers (table/column names, keywords) are left intact.
4. Forwards to OpenRouter using the OpenRouter API key **read from OpenWebUI's own
   config** (one key to rotate, not two).
5. **Restores** the real values in the response (both non-streaming and SSE stream),
   so the answer references the developer's actual identifiers — not `GP_…`.
6. Writes a **who-sent-what audit row** (already anonymized) to `gp_audit` (GDPR Art. 30).

Masking is **fail-closed**: if the anonymizer/NER is unreachable, the request is
blocked rather than sent unmasked.

Why reversible (vs the one-way OpenWebUI filter): for code, a masked table or column
name that never comes back would make the answer useless. Here the vault restores it.

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| POST | `/v1/chat/completions` | OpenAI chat, streaming and non-streaming |
| GET | `/v1/models` | Advertises the single pinned model |
| GET | `/health` | `{"status":"ok","model":"<pinned>"}` |

Auth: `Authorization: Bearer <key>` where the key is one of `GP_OAI_PROXY_KEYS`
(empty ⇒ open — rely on network isolation).

## Configuration (`.env`)

| Variable | Meaning |
|----------|---------|
| `OPENROUTER_MODEL` | **Pinned** upstream model (the only one used). Required, e.g. `qwen/qwen-2.5-coder-32b-instruct`. |
| `OPENROUTER_BASE_URL` | OpenAI-compatible base. Default `https://openrouter.ai/api/v1`. |
| `OPENROUTER_API_KEY` | Optional explicit key. **Empty ⇒ read from OpenWebUI** (the `openrouter` connection). |
| `GP_OAI_PROXY_KEYS` | Bearer keys the client tools present (comma-separated). Empty ⇒ open. |
| `GP_TOKEN_SECRET` | Token-derivation secret (shared with the Claude proxy; owner-scoped, so vaults stay separate). |
| `GP_DB_URL` | Postgres vault DSN (token → real value). Same DB as the Claude proxy. |
| `GP_FAIL_CLOSED` | `true` (default) ⇒ block on masking failure. |
| `GP_AUDIT_ENABLED` | `true` (default) ⇒ persist the anonymized new turn to `gp_audit`. |

The OpenRouter key comes from OpenWebUI's config table (`openai.api_base_urls` /
`openai.api_keys`, matched by `OPENROUTER_KEY_MATCH`, default `openrouter`) — so set
the OpenRouter connection **once in OpenWebUI** (Admin → Settings → Connections).

## Network & security

The port is bound to `0.0.0.0` (LAN-reachable) so IDE clients can connect directly.
Because it **carries credentials and reaches the plaintext vault**, protect it:

- set `GP_OAI_PROXY_KEYS` and give each developer a key (offboarding revokes one key);
- **firewall** port 8013 to trusted developer subnets only;
- the vault (`gp_vault`) holds the real values — restrict the DB role and rely on the
  TTL prune (`GP_VAULT_TTL_DAYS`, default 30).

## Client setup

Any OpenAI-compatible client that allows a custom base URL works. The model field is
**ignored** (pinned server-side), so put anything.

| Setting | Value |
|---------|-------|
| Base URL | `http://<host>:8013/v1` |
| API key | one of `GP_OAI_PROXY_KEYS` |
| Model | anything (pinned by `OPENROUTER_MODEL`) |

**VS Code + Continue** (`~/.continue/config.json`) — the tested path:

```json
{
  "models": [{
    "title": "GuardPrompt (OpenRouter)",
    "provider": "openai",
    "apiBase": "http://YOUR_HOST:8013/v1",
    "apiKey": "YOUR_GP_OAI_PROXY_KEY",
    "model": "pinned"
  }]
}
```

**Oracle SQL Developer / SQLcl:** use SQLcl 24.3+ (or an IDE AI plugin) that accepts a
custom OpenAI base URL + key. Classic SQL Developer without such a setting cannot point
at an arbitrary OpenAI endpoint — in that case use VS Code + Continue, or OpenWebUI in
the browser.

## Deploy

Ships pyarmor-obfuscated (in the `publish.ps1` list). On the server:

```bash
# 1. set the model + client keys in .env
#    OPENROUTER_MODEL=qwen/qwen-2.5-coder-32b-instruct
#    GP_OAI_PROXY_KEYS=<generated key(s)>
# 2. build + start (safe on a shared host — no -v / --remove-orphans)
docker compose up -d --build gp-openai-proxy
```

Make sure the **OpenRouter connection exists in OpenWebUI** (so the key can be read),
or set `OPENROUTER_API_KEY` explicitly.

## Verify

```bash
# health + pinned model
curl -s http://localhost:8013/health

# a chat (add -H "Authorization: Bearer <key>" if GP_OAI_PROXY_KEYS is set)
curl -s http://localhost:8013/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"What does SELECT ename FROM emp WHERE ename='"'"'Jonas Petraitis'"'"'; do?"}]}'
```

Confirm the request went to OpenRouter **masked** (the audit stores the anonymized
turn):

```bash
docker exec postgres psql -U <user> -d <db> \
  -c "SELECT ts, model, left(content,150) FROM gp_audit ORDER BY ts DESC LIMIT 3;"
```

The `content` must show `GP_…` tokens (not the real name) — proof it masked before
egress; the client, meanwhile, sees the real values restored.

## Relation to the other paths

| | `gp-openai-proxy` | OpenWebUI `/api/chat/completions` | `gp-claude-proxy` |
|---|---|---|---|
| Protocol | OpenAI → OpenRouter | OpenAI (OWUI) | Anthropic → Anthropic |
| Anonymization | **reversible** (vault) | one-way filter | reversible (vault) |
| Model | **env-pinned** | via OWUI access control | Claude models |
| For | SQL Developer / OpenAI tools | browser / ad-hoc | Claude Code / VS Code |
