> 🌐 **Language / Kalba:** **English** · [Lietuvių](API.lt.md)

# GuardPrompt — Anonymization API

Send text, get the same text back with personal and sensitive data replaced by
placeholders (`[PERSON]`, `[HEALTH]`, `[IBAN]`, …). Everything runs on your own
hardware: the text never leaves the machine.

Use this to anonymize data from your own applications — before archiving,
before sending to an external service, or before any other processing.

- **What gets masked and why:** [COMPLIANCE.md](COMPLIANCE.md) (GDPR Art. 9/10, EU AI Act)
- **How it fits the platform:** [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Two APIs, two jobs

GuardPrompt exposes two independent programmatic entry points. Pick by what you need:

| | **Anonymization API** (this doc, below) | **Anonymizing chat API** ([↓ through OpenWebUI](#chat-api-through-openwebui-openai-compatible)) |
|---|---|---|
| Purpose | Mask text / documents | Run an LLM (OpenRouter) with PII stripped first |
| Endpoint | `http://…:8005/api/v1/anonymize` | `http://…/api/chat/completions` (OpenAI-compatible) |
| Auth | `ANON_API_KEYS` | OpenWebUI API key |
| Returns | Masked text | LLM answer — the input was masked before the model saw it |
| Reversible? | No — one-way | No — one-way. Need the real values back in the reply? Use the reversible Claude gateway: [GP-CLAUDE-PROXY.md](GP-CLAUDE-PROXY.md) |

The rest of this page documents the **Anonymization API**; the chat API is at the
[end](#chat-api-through-openwebui-openai-compatible).

---

## Base URL

| Where you call from | URL |
|---|---|
| Another container in the stack | `http://anonymizer:8005` |
| The Docker host | `http://localhost:8005` |

> ⚠️ Port 8005 is published on **all interfaces** (`0.0.0.0`). Anything that can
> reach the host can reach this API, so **set an API key** (below). If you do not
> need external access, restrict the port in `docker-compose.yml`
> (`"127.0.0.1:8005:8005"`) or with a firewall.

## Authentication

Send the key from `ANON_API_KEYS` (`.env`) as a Bearer token:

```
Authorization: Bearer <key>
```

`X-API-Key: <key>` also works. `install.ps1` / `install.sh` generate a key
automatically; it is printed once at the end of the install.

If `ANON_API_KEYS` is **empty the API needs no key** and is open to anyone who
can reach the port. `ANON_API_KEYS` may hold several comma-separated keys, so
each client can get its own and be revoked without disturbing the rest.

| Response | Meaning |
|---|---|
| `401` | Key missing or wrong |
| `400` | Malformed request (bad JSON, empty text) |
| `200` | Success |

---

## `POST /api/v1/anonymize`

The main endpoint. JSON in, JSON out.

**Request**

```json
{
  "text": "Jonas Vaitkevičius serga vėžio liga. Tel. +37060012345.",
  "do_anonymize": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | Text to anonymize |
| `do_anonymize` | bool | no (default `true`) | `false` returns a "skipped" notice instead of the text — it never echoes raw input |

**Response**

```json
{ "text": "[PERSON] serga [HEALTH]. Tel. [PHONE]." }
```

### curl

```bash
curl -X POST http://localhost:8005/api/v1/anonymize \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"Jonas Vaitkevičius serga vėžio liga."}'
```

### Python

```python
import requests

r = requests.post(
    "http://localhost:8005/api/v1/anonymize",
    headers={"Authorization": f"Bearer {ANON_API_KEY}"},
    json={"text": "Jonas Vaitkevičius serga vėžio liga."},
    timeout=30,
)
r.raise_for_status()
print(r.json()["text"])      # [PERSON] serga [HEALTH].
```

> **Lithuanian text and JSON encoding.** Send UTF-8 and let your HTTP library
> build the JSON (`json=` in `requests`, `JSON.stringify` in JS). Both `"vėžio"`
> and the `ė`-escaped form are handled — the service decodes the JSON before
> anonymizing. Do **not** hand-build a JSON string and post it as `text/plain`:
> that path treats the whole envelope as prose.

### Other accepted formats

The same handler also takes plain text and file uploads. Useful for shell
scripts; new integrations should use JSON.

```bash
# raw body
curl -X POST http://localhost:8005/api/v1/anonymize \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -H "Content-Type: text/plain" \
  --data-binary "Jonas Vaitkevičius serga vėžio liga."

# file upload (returns JSON with an "anon_text" field)
curl -X POST http://localhost:8005/api/v1/anonymize \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -F "file=@notes.txt"
```

### `POST /api/anonimize` (alias)

The original path, kept for backwards compatibility — note the Lithuanian
spelling (`anonimize`). Identical behaviour. Prefer `/api/v1/anonymize` in new
code; `/api/anonimize` will not be removed.

---

## `PUT /process` — documents

Extracts and anonymizes a document (PDF, DOCX, XLSX, PPTX, images, …). This is
the endpoint OpenWebUI uses as its *external document loader*; you can call it
directly too. Non-text formats are routed through Docling for extraction first.

Send the raw file bytes as the body, with the filename in a header:

```bash
curl -X PUT http://localhost:8005/process \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -H "X-Filename: report.pdf" \
  -H "Content-Type: application/pdf" \
  --data-binary @report.pdf
```

**Response** — a list of pages/blocks:

```json
[
  {
    "page_content": "[PERSON] serga [HEALTH].",
    "metadata": {
      "filename": "report.pdf",
      "mime_type": "application/pdf",
      "processed_by": "guardprompt-docling"
    }
  }
]
```

---

## Utility endpoints

These need **no** API key — registration must work before a key exists.

| Endpoint | Purpose |
|---|---|
| `GET /` | Health check → `{"status":"ok"}` |
| `GET /api/reginfo` | Host ID + IP for licence registration ([LICENSING_INFO.md](LICENSING_INFO.md)) |
| `GET /metrics` | Prometheus metrics — anon requests/status, mask duration, `fail_closed{license,gliner}`, injection-detected. Scraped by the Zabbix monitoring plane ([MONITORING.md](MONITORING.md)) |

`POST /api/webcrawle` (crawl a site into a knowledge base) **does** require a key.

> **Observability.** `gliner` (`:8500/metrics`) and the Claude proxy
> (`gp-claude-proxy:8006/metrics`) expose the same Prometheus format, giving
> uniform latency, throughput, `model_on_gpu` and fail-closed signals across the
> whole anonymization path — see [MONITORING.md](MONITORING.md).

---

## Behaviour you must plan for

The API is **fail-closed**: when it cannot guarantee anonymization it refuses to
return text rather than returning text that might leak. Handle these as errors,
not as content — they arrive with HTTP `200`:

| Returned text | Cause |
|---|---|
| `[PROCESSING DISABLED: LICENSE IS NOT VALID]` | Licence missing/expired — see [LICENSING_INFO.md](LICENSING_INFO.md) |
| `[PROCESSING DISABLED: ANONYMIZATION SERVICE UNAVAILABLE]` | The `gliner` NER service is down, so GDPR Art. 9/10 categories cannot be detected. `ANON_REQUIRE_GLINER=false` in `.env` allows a degraded run instead |

**Timeouts.** A short text is fast, but a large document is not: `gliner` NER is
**GPU-accelerated with dynamic batching** (~70 req/s), but Docling extraction is
heavy. Allow at least 30 s for `/api/v1/anonymize` and considerably more for
`/process`.

**Startup.** The service validates its licence asynchronously a few seconds
after boot. A call made in that window gets `LICENSE IS NOT VALID` even with a
valid licence — poll `GET /` and retry rather than treating the first response as
final.

**Diacritics matter.** Detection is tuned for real Lithuanian text. `vėžio` is
recognised as health data; `vezio` may not be. Do not strip diacritics before
sending.

**Idempotent.** Re-anonymizing already-masked text is safe — placeholders are
protected and will not be re-tagged.

## Configuration

What gets masked is controlled by the `ANON_*` flags in `.env` (see
`.env.example` — every flag is documented there). Terms that must stay visible go
into `ANON_ALLOW_WORDS` / `ANON_ALLOW_DOMAINS`; the allow list has the highest
priority.

---

## Chat API through OpenWebUI (OpenAI-compatible)

The second entry point. For developers and tools that want to **call an LLM with
anonymization applied automatically**: the request goes through OpenWebUI, the
GuardPrompt filter masks it, and only then reaches OpenRouter. Real personal data
never leaves the machine in the outbound LLM call.

This is the *same* anonymizer the chat UI uses — a global `pipelines: ["*"]`
filter — exposed over OpenWebUI's standard OpenAI-compatible API, so any OpenAI
SDK works unchanged. It is not a separate service to run.

- **Base URL:** the same host/domain as the OpenWebUI web app, plus `/api`
  (e.g. `https://chat.example.com/api`).
- **Auth:** an **OpenWebUI API key** — *not* `ANON_API_KEYS`. Each user creates
  one under *Settings → Account → API Keys*; give each developer their own so
  access is revocable per person.
- **Models:** any model OpenWebUI serves — list them with `GET /api/models`, use
  the OpenRouter ids (e.g. `openai/gpt-5.6-luna`).

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://chat.example.com/api",   # OpenWebUI — NOT openrouter.ai
    api_key="<your OpenWebUI API key>",
)
resp = client.chat.completions.create(
    model="openai/gpt-5.6-luna",               # any OpenRouter model
    messages=[{"role": "user",
               "content": "Jonas Petraitis, a.k. 38901011234 — draft a reply."}],
)
print(resp.choices[0].message.content)
```

OpenRouter receives `[PERSON], [ID] — draft a reply.` — the name and personal
code are masked **before** the request leaves the machine.

### curl

```bash
curl -X POST https://chat.example.com/api/chat/completions \
  -H "Authorization: Bearer <OpenWebUI API key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-5.6-luna","messages":[{"role":"user","content":"..."}]}'
```

### One-way, not reversible

This path **masks** (like the text API above): the LLM only ever sees
`[PERSON]`, so its answer also refers to `[PERSON]` — the real values are never
restored. If a client needs the real data back in the response (reversible
pseudonymization), use the Anthropic/Claude gateway instead —
[GP-CLAUDE-PROXY.md](GP-CLAUDE-PROXY.md).

> **Fail-closed**, like the rest of the platform: if the anonymizer is
> unavailable the message is blocked rather than sent raw (configurable on the
> pipeline filter).

> Responses may carry invisible zero-width marker characters the pipeline adds
> (`​‌⁣`). They are harmless — not a leak — but strip them if a
> downstream system is picky.
