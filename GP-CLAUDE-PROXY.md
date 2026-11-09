> 🌐 **Language / Kalba:** **English** · [Lietuvių](GP-CLAUDE-PROXY.lt.md)

# GuardPrompt Claude proxy — deployment

Routes your Claude Code clients — CLI, VS Code and JetBrains — through GuardPrompt
before anything reaches Anthropic (the **desktop app** too, but only in API-key
mode, not with a claude.ai subscription — see §3). Sensitive values are replaced
with reversible tokens on the way out and restored on the way back, so developers
see real code while Anthropic never does. The mapping never leaves this
infrastructure.

```
Claude Code CLI ─┐
VS Code ext ─────┤
JetBrains IDE ───┼─→ gp-claude-proxy ──→ api.anthropic.com
Desktop app * ───┘    (your machine)      (sees GP_a3298922c55a)
                            │
                    ┌───────┴───────┐
              Postgres vault     Postgres audit
            (GP_… → real value)  (who sent what, masked)

 * subscription pass-through (Mode A) works for CLI / VS Code / JetBrains;
   the desktop app can only go through the proxy in API-key mode (Mode B) — §3.
```

This is a **separate service** from the `anonymizer` container. That one serves
OpenWebUI with one-way masking for prose and is not touched here; this one only
imports its rule modules read-only.

Why organizations run it: developers keep using the best coding model on the
market, and not one customer name, credential, personal code, or line of
sensitive source ever leaves the building in the clear. GDPR, NIS2 and internal
data-handling policy stop being a reason to ban AI tooling.

---

## 1. Two credential modes — pick before you deploy

The proxy authenticates to Anthropic in one of two ways. **It is a single global
switch for the whole instance, set by whether `GP_UPSTREAM_API_KEY` is filled —
not per user.** You cannot mix both in one instance; run two instances on two
ports if you need both.

| | **Mode A — Subscription pass-through** | **Mode B — Shared API key** |
|---|---|---|
| `GP_UPSTREAM_API_KEY` | empty (default) | set to a real `sk-ant-…` |
| Who pays | each developer's own claude.ai subscription (Pro / Max / Team) | one central Anthropic **API** account, per-token billing |
| Developer needs a claude.ai login | **yes** | **no** |
| Access control to the proxy | network layer only (`GP_PROXY_KEYS` is ignored) | `GP_PROXY_KEYS` gate tokens, one per person |
| Desktop app support | **no** (see §3) | yes |
| Good for | a team that already has Pro/Team seats | people without a licence, or centralizing billing/attribution |

The Anthropic **API key** in Mode B (from
[console.anthropic.com](https://console.anthropic.com)) is a *different product*
from a Pro/Team chat subscription — it is billed per token, not a flat monthly
seat. This is the single most common point of confusion; keep it straight.

**Network reach.** The proxy binds to `127.0.0.1:8006` by default, so only the
host can reach it. For a team, publish it over your VPN or behind a reverse
proxy with TLS, and give developers that URL. Do not expose it to the internet:
anyone who reaches it can have their content pseudonymized and, more to the
point, **restored** — the vault is behind this port.

---

## 2. Configure the server

Generate the token key once and put it in `.env`. **Changing it later orphans
every existing mapping** — tokens already in a running conversation stop
resolving — so treat it as permanent. `install.ps1` / `install.sh` generate it
for you; to do it by hand:

```powershell
$b = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
"GP_TOKEN_SECRET=" + (($b | ForEach-Object { $_.ToString("x2") }) -join "")
```

```bash
# .env
GP_TOKEN_SECRET=<the value generated above>   # HMAC seed; keep stable forever

# Customer names, internal domains, project code names — the values only you
# know are sensitive. gliner will not find these; nothing but this list will.
GP_CUSTOM_WORDS=YourCustomer,internal.example.com,ProjectFalcon

# --- MODE SELECTOR ---
# Empty  -> Mode A (pass-through): developers use their own claude.ai logins.
# sk-ant -> Mode B (shared key):  proxy pays for everyone.
GP_UPSTREAM_API_KEY=

# Gate tokens — MODE B ONLY (ignored in Mode A). One per developer so
# offboarding revokes a single key; also identifies the sender for the vault
# scope and the audit log. Generate strong random values:
#   gpk_$(openssl rand -hex 20)
GP_PROXY_KEYS=
```

Start it:

```bash
docker compose up -d gp-claude-proxy
docker compose logs gp-claude-proxy | Select-String "gp-proxy"
```

A healthy start prints the rule count, `gliner=ON`, `fail_closed=True`, and the
resolved mode:

```
[gp-proxy] credential mode=SUBSCRIPTION PASS-THROUGH (client's own claude.ai login is relayed)
[gp-proxy] proxy auth=n/a (pass-through) — restrict access at the network layer
```

or, in Mode B:

```
[gp-proxy] credential mode=API KEY (proxy-held, replaces client credential)
[gp-proxy] proxy auth=ON (3 keys)
```

---

## 3. Point each surface at it

Replace `https://gp-proxy.internal.example.com` with your URL.

### Claude Code CLI

`~/.claude/settings.json` (`%USERPROFILE%\.claude\settings.json` on Windows):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gp-proxy.internal.example.com",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0"
  }
}
```

In **Mode A**, do **not** set `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY`:
either replaces the claude.ai subscription with that credential, the
subscription stops being used, and its licence is wasted. In **Mode B**, set
`ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`) to the developer's **gate token**
(`gpk_…`), *not* to any Anthropic key — the real Anthropic key lives only in the
proxy container.

### VS Code extension ("CLAUDE CODE" tab)

VS Code's own user settings (**Preferences: Open User Settings (JSON)**), not
`~/.claude/settings.json` — the extension checks credentials from this setting
before it launches, and values in the Claude settings file reach the spawned
process but not the extension's own login check:

```json
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "https://gp-proxy.internal.example.com" },
    { "name": "CLAUDE_CODE_ATTRIBUTION_HEADER", "value": "0" }
  ]
}
```

> **Not to be confused with the VS Code "CHAT" tab**, which is **GitHub
> Copilot** — a *separate* AI surface that egresses to GitHub/Microsoft and
> never touches this proxy. It is an independent, un-pseudonymized data path.
> Disable it for users who must stay on the proxy:
> `"chat.disableAIFeatures": true` in VS Code settings (or uninstall Copilot on
> the fleet).

### JetBrains IDEs (IntelliJ IDEA, PyCharm, …) — "Claude Code [Beta]" plugin

The JetBrains plugin just spawns the **Claude Code CLI** — its **Settings → Tools →
Claude Code** panel exposes only *CLI Path* / *Node Path*, **no base-URL field** —
and that CLI reads `~/.claude/settings.json`. So the proxy treats it exactly like
the CLI and **no proxy-side change is needed**. *Verified on IntelliJ IDEA 2026.2.*

Put the same `env` block as the CLI (above) in `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gp-proxy.internal.example.com",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0"
  }
}
```

Then **restart the IDE** (the base URL is read once, at agent startup — a
mid-session change does nothing). The JetBrains plugin does **not** support the
`/status` slash command (`"/status isn't available in this environment"`), so
verify with the **self-test page** below (§3a). Auth is identical to the CLI —
**Mode A**: leave
`ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` unset (claude.ai subscription);
**Mode B**: the developer's `gpk_…` gate token.

> **This edit is global** — `~/.claude/settings.json` also steers the terminal
> `claude` CLI. To route **only** the IDE through the proxy, leave that file alone
> and set the plugin's *CLI Path* to a small wrapper that exports
> `ANTHROPIC_BASE_URL` (and `CLAUDE_CODE_ATTRIBUTION_HEADER=0`) then execs the real
> `claude`.

> **If a build ignores `~/.claude`** (JetBrains YouTrack **LLM-26098**: some newer
> `com.intellij.ml.llm` ACP agents do not read `ANTHROPIC_BASE_URL` from the
> environment), put the same `env` object inside
> `%APPDATA%\JetBrains\acp-agents\installed.json` (Linux/macOS
> `~/.config/JetBrains/acp-agents/installed.json`) under `acp.registry.claude-acp`,
> then restart. That folder appears only after the plugin has bootstrapped its
> agent once.

### Desktop app — Mode B only

**The desktop app cannot do subscription pass-through.** Its gateway config
(**Help → Troubleshooting → Enable Developer Mode**, then **Developer →
Configure Third-Party Inference**) *requires* a "Credential kind", and the only
choices are **Static API key**, **Interactive sign-in (external OIDC IdP)**, or
**Helper script** — none of which is a claude.ai subscription. So the desktop
app works through this proxy only in **Mode B** (give it the `gpk_…` gate token
as the static API key), or with an OIDC/helper credential you operate.

An administrator-distributed configuration takes precedence and makes that form
read-only, which is how to roll this out to a fleet. With a gateway configured,
the desktop app runs sessions **locally only** — the environment picker offers
no SSH or Anthropic-hosted cloud environments, and Remote Control is
unavailable.

If your team is on Pro/Team seats (Mode A), route sensitive work through the CLI
or the VS Code "CLAUDE CODE" tab and leave the desktop app off the proxy.

### 3a. Verify it's working (any client — proves YOUR traffic is anonymized)

A developer can confirm their own IDE traffic actually flows through the proxy —
not merely that the proxy exists — right inside the Claude chat, with no URL and
no server access. Type a message that **starts with `GP-SELFTEST:`** followed by
anything you want to check:

```
GP-SELFTEST: Klientas Jonas Petraitis, a.k. 39001011234, tel. +37061234567
```

The proxy intercepts it, masks the text, and replies with **exactly what Anthropic
would have received** — without calling Claude at all:

```
🛡️ GuardPrompt patikra — štai KĄ GAVO Claude (anonimizuota):
Klientas GP_53ef4c1638aa, a.k. GP_03ef34205f00, tel. GP_d8317e2c016f
Užmaskuota reikšmių: 3. …tavo srautas EINA per GuardPrompt proxy…
```

**Why this is a real check:** that reply can only appear if the message actually
reached this proxy. If the base URL is misconfigured (wrong host/port), the
`GP-SELFTEST:` message goes elsewhere and you get a connection error or an ordinary
Claude answer — never this canned reply. So seeing it means your traffic **is**
routed through GuardPrompt and masked. Works in any surface (CLI, VS Code,
JetBrains) — this is the recommended check for the **JetBrains plugin**, which has
no `/status` command.

*(Admins can additionally confirm real traffic server-side: `docker logs
gp-claude-proxy` shows `POST /v1/messages -> 200 mask=…ms` and a
`GP-SELFTEST owner=… masked_spans=N` line, and `gp_vault` fills with `GP_`
token→value rows.)*

---

## 4. Two protocol details the proxy must get right

These are handled by the proxy already; you need them only to understand
failures and to keep them intact if you fork the code.

### 4a. The Claude Code system-prompt identity must survive verbatim

Subscription OAuth (Mode A) validates that each request carries the genuine
Claude Code identity line in its system prompt:

> `You are Claude Code, Anthropic's official CLI for Claude.`

An earlier version of the proxy pseudonymized *everything*, including that line
(it tokenised "Claude"/"Anthropic"). Anthropic then rejected the request — **as
a `429 rate_limit_error`, not a 401** — which looks exactly like a usage cap and
sends you chasing the wrong problem for hours. The fix, already in `bodywalk.py`:
**never mask any system block that contains the identity line.** Everything
*after* it (user text, tool results, tool-use inputs) is still masked normally.
If you rewrite `bodywalk.py`, keep the identity block byte-identical.

### 4b. `/api/hello` must forward, not 404

Claude Code probes a first-party-only endpoint (`HEAD /api/hello`) to decide
whether the base URL is Anthropic's real API. If the proxy 404s it, the client
concludes it is talking to a third-party gateway and stops sending the
subscription OAuth correctly → every `/v1/messages` then returns **401 "Invalid
bearer token"** even with a valid login. The proxy therefore has a **catch-all
route** that transparently forwards any unmatched path upstream (defined last,
so the explicit masking routes win). `api.anthropic.com/api/hello` returns
`{"message":"hello"}`.

### 4c. Why `CLAUDE_CODE_ATTRIBUTION_HEADER=0`

Claude Code prepends an attribution block as the first `system` entry.
`api.anthropic.com` strips it before processing — **but only if it arrives
byte-identical and first**. The strip is positional, and any proxy that rewrites
system text can defeat it, putting the block into the prompt-cache key.
Anthropic's own docs prescribe omitting it at the client for exactly this case;
the setting does that.

---

## 5. Audit — who sent what (optional, GDPR Art. 30)

The proxy can persist one row per request to a `gp_audit` table: the **new turn
only**, **already pseudonymized** (GP_ tokens, never raw content), plus **who
sent it** and when. This is the record an auditor asks for — proof of what left
the building and by whom — without itself becoming a second copy of the
sensitive data.

```bash
# .env
GP_AUDIT_ENABLED=true          # ON by default (GDPR Art.30); set false to disable
GP_AUDIT_TTL_DAYS=180          # rows pruned after this (default 180)
```

**Identity ("who sent it")** is resolved best-available:

1. `X-GP-User` request header — set per machine via managed config
   (`ANTHROPIC_CUSTOM_HEADERS`). **Inject it at your reverse proxy** instead of
   trusting the client, so a developer cannot spoof another's identity.
2. `metadata.user_id` from the request body (fallback).
3. The credential-hash `owner` is always stored alongside regardless.

Auditing never fails a request: a write error is logged, not raised. Content
stored is the masked text, so the audit table's own exposure is limited to
GP_ tokens plus identity/IP/timestamp/byte-count.

The reversible **vault** (`gp_vault`) is the sensitive store — it holds the
plaintext of everything ever masked. Prune it with `GP_VAULT_TTL_DAYS`
(default 30) and protect it as the crown jewels.

---

## 6. Monitoring

The proxy exposes Prometheus metrics at `GET /metrics` (request/mask latency
histograms, masked-span counts, upstream status, fail-closed counters, plus
leak-detection gauges: DB-pool in-use/idle, event-loop lag, asyncio task count,
cache size/evictions). `gliner` and `anonymizer` expose the same. The full
Zabbix template, exporters, dashboards and preventive triggers are in
**[MONITORING.md](MONITORING.md)**. The trigger `gliner_model_on_gpu=0` and the
`*_fail_closed_total>0` critical would each have caught a real incident during
build-out.

---

## 7. Verify

From a developer machine, before opening any Claude client:

```bash
curl -X POST "https://gp-proxy.internal.example.com/v1/messages" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-8","max_tokens":1,"messages":[{"role":"user","content":"."}]}'
```

In **Mode A**, a `401` here is the expected, correct answer: it proves the proxy
is reachable and forwarded the request, and that the upstream rejected it because
curl sent no subscription credential. In **Mode B**, a request with no gate token
returns `401` from the proxy itself (`"Invalid or missing gateway credential"`),
and a request with a valid `Authorization: Bearer gpk_…` is forwarded.

Then in Claude Code run `/status`. The **Anthropic base URL** line must show the
proxy address; in Mode A the **Login method** line must still name your claude.ai
account (not an API key).

To confirm masking is actually happening, watch the proxy while a developer
works, or inspect the vault directly:

```bash
docker compose logs -f gp-claude-proxy
# [gp-proxy] POST /v1/messages -> 200 mask=340ms total=4.1s cache 11/14 (79% hit)

docker exec postgres psql -U guardprompt -d guardprompt \
  -c "SELECT token, value FROM gp_vault ORDER BY value LIMIT 20;"
# real name/email/phone/IBAN/personal code -> GP_xxxxxxxxxxxx
```

Set `GP_LOG_SENT=true` to log the pseudonymized outbound `messages` to stdout so
an operator can confirm real values became GP_ tokens before they left.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every request `429 rate_limit_error`, message `"Error"`, no `anthropic-ratelimit-*` headers | The Claude Code **system-prompt identity was masked** — subscription OAuth rejects a non-genuine client as a rate limit (see §4a). Only happens if you edited `bodywalk.py` | Keep the identity block verbatim; do not tokenise it |
| `401 "Invalid bearer token"` in Mode A even with a valid login | `/api/hello` 404'd, so the client stopped sending OAuth correctly (see §4b) | Ensure the catch-all forward route is present |
| `401 "Invalid or missing gateway credential"` in Mode B | Client presented no gate token or one not in `GP_PROXY_KEYS` | Set `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` to the developer's `gpk_…` |
| Mode B request → `401 "invalid x-api-key"` with a real `request_id` | The **upstream** Anthropic API key is wrong/dummy — the gate passed and the request reached Anthropic | Put a real `sk-ant-…` in `GP_UPSTREAM_API_KEY` |
| `403` with an HTML body, and the proxy logs show **no request** | A WAF/reverse proxy in front blocked the body. Claude prompts contain XML-style tags and source that match XSS body rules. **A short curl passes while a real session fails** | Exempt `/v1/messages` from request-body inspection. **Applies to SafeLine, which fronts this deployment** |
| `[GuardPrompt] Užklausa užblokuota` | gliner is down or pseudonymization failed; fail-closed refused rather than forwarding raw content | Check `docker compose logs gliner`. `GP_FAIL_CLOSED=false` disables the guard — raw content then reaches Anthropic on failure |
| Answers come back containing `GP_a3298922c55a` | The mapping is gone: vault pruned (`GP_VAULT_TTL_DAYS`), `GP_TOKEN_SECRET` changed, or the developer re-logged in and became a new owner | Start a new conversation. Do not change `GP_TOKEN_SECRET` |
| Claude Code asks to log in (Mode A) | A gateway credential variable is set somewhere and replaced the subscription | Unset `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` |
| First request very slow, later ones fast | Expected: gliner processes the whole conversation once, then the block cache serves it (measured 2.3s → 0.3s) | Nothing |
| `Unable to connect to API` | The proxy is bound to `127.0.0.1` and the developer is on another machine | Publish it over the VPN or a reverse proxy |

---

## 9. What this does and does not protect

**Does:** the values matched by the imported deterministic rules (secrets,
tokens, keys, connection strings, emails, IBANs, phones, Lithuanian personal
codes, credit-card numbers, crypto addresses, VAT numbers, keyword-anchored
company codes, document numbers, plates, GPS) and by gliner (person, health,
criminal, political, religious, …), plus everything in `GP_CUSTOM_WORDS`, never
reach Anthropic in the clear. The rule set covers the same categories the
document anonymizer masks, minus two deliberately dropped for source code: bare
dates and bare company codes, which as raw digit runs would tokenize ordinary
numeric literals (see below). gliner **person** spans are validated by the same
shared filter (`person_noise.py`) the anonymizer uses, so job titles and
institutions ("…departamento direktoriui") are not tokenised as names — less
prompt bloat, identical behaviour on both paths.

**Does not:**

- **Sensitive values with no pattern and not in `GP_CUSTOM_WORDS`.** An internal
  hostname or a customer name nobody listed goes through as-is.
- **Bare dates and bare (unlabelled) company codes.** Deliberately not masked
  here, unlike the document anonymizer: as raw digit runs they would tokenize
  every date and every 7-9 digit literal in source code, degrading Claude's help
  for no privacy gain. A company code written next to its keyword ("įmonės kodas
  302471233") *is* masked; a lone `302471233` is not.
- **Local transcripts.** Claude Code stores session transcripts in plaintext
  under `~/.claude/projects/` for 30 days by default (`cleanupPeriodDays`), on
  each developer's laptop. The proxy protects the network hop, not the disk.
- **The vault itself.** `gp_vault` in Postgres holds the plaintext of everything
  ever masked — one table containing all of it. Protect it accordingly.
- **Secrets living in source.** The proxy is a net, not a fix. Anything hardcoded
  in the repository is already on every laptop, in git history, and in every
  clone; masking it on the way to Claude closes one path out of many.
