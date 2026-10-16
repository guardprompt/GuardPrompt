> 🌐 **Language / Kalba:** **English** · [Lietuvių](ZABBIX-INTEGRATION.lt.md)

# GuardPrompt → corporate Zabbix (via a local Zabbix proxy)

Forward all GuardPrompt metrics to an **existing company Zabbix** without weakening
the platform's network hardening and without running two monitoring servers.

The GuardPrompt `/metrics` endpoints are bound to `127.0.0.1`, so a Zabbix server
on another host cannot scrape them directly. The answer is a **local Zabbix
proxy**: a container on `openwebui_net` that scrapes the internal `/metrics` by
container name and connects **outbound** to your corporate Zabbix server. Nothing
new is exposed; the loopback hardening stays intact.

```
GuardPrompt host
  ┌───────────────────────────────────────────┐
  │ gp-claude-proxy / gliner / anonymizer /    │   scrapes internally
  │ qdrant / node / cadvisor / pg / blackbox   │◀──(container-name /metrics)──┐
  │                                            │                              │
  │   zabbix-proxy  ──────────────────────────────── outbound :10051 (PSK) ──┼──▶  Corporate Zabbix server
  └───────────────────────────────────────────┘                              │
```

The bundled standalone Zabbix (`zabbix-server` / `zabbix-web`) is **untouched** —
it stays available for a local view, or you stop it once the corporate server
owns monitoring. The proxy is **opt-in**: it only runs under the
`external-zabbix` compose profile.

---

## Prerequisites

- Admin access to your corporate Zabbix (to create a Proxy, a Host, and import a template).
- The GuardPrompt host can reach the corporate Zabbix server on **TCP 10051 outbound**.

> ⚠️ **Proxy version must match the server (7.0).** A Zabbix proxy cannot be a
> different major version from its server — a 6.0 proxy will **not** connect to a
> 7.0 server. The compose image defaults to `alpine-7.0-latest` (our corporate
> server is 7.0); it's set by `ZBX_PROXY_VERSION` in `.env`. The bundled
> standalone `zabbix-server`/`web` were also migrated to **7.0** (`ZBX_VERSION`),
> so the whole platform is now 7.0.

- **Template imports into 7.0 as-is — verified.** `monitoring/zabbix_guardprompt.yaml`
  is a `version: '6.0'` export; Zabbix 7.0 imports older exports directly, and we
  confirmed it re-imports into a live 7.0 instance with **no errors** (items,
  triggers with their remediation `description`, LLD and macros all intact). Just
  import the file — no editing needed.

---

## 1. Import the template

In corporate Zabbix: **Data collection → Templates → Import** →
`monitoring/zabbix_guardprompt.yaml`. This brings in all items, triggers (each
with its *Cause → Fix* remediation in the description), the per-user LLD and the
macros.

## 2. Create the Proxy + PSK

**On the GuardPrompt host**, generate the pre-shared key:

```bash
openssl rand -hex 32 > monitoring/zabbix_proxy.psk
chmod 600 monitoring/zabbix_proxy.psk
```

In corporate Zabbix: **Administration → Proxies → Create proxy**
- **Proxy name:** `GuardPrompt-proxy` (must equal `ZBX_PROXY_NAME` / `ZBX_HOSTNAME`)
- **Proxy mode:** *Active*
- **Encryption:** *PSK* — **PSK identity** = `GuardPrompt-proxy` (your `ZBX_PROXY_PSK_ID`),
  **PSK** = the hex string from the file above.

## 3. Configure `.env`

```bash
CORP_ZABBIX_SERVER=zabbix.company.lan     # your Zabbix server (or its proxy)
CORP_ZABBIX_PORT=10051
ZBX_PROXY_NAME=GuardPrompt-proxy
ZBX_PROXY_PSK_ID=GuardPrompt-proxy
```

## 4. Start the proxy (opt-in profile)

```bash
docker compose --profile external-zabbix up -d zabbix-proxy
docker compose logs -f zabbix-proxy      # expect "proxy started", then connections to the server
```

Within a minute the corporate Zabbix **Administration → Proxies** list shows
`GuardPrompt-proxy` with a recent *Last seen*.

## 5. Create the Host (monitored by the proxy)

In corporate Zabbix: **Data collection → Hosts → Create host**
- **Host name:** e.g. `GuardPrompt-<site>`
- **Monitored by proxy:** `GuardPrompt-proxy`
- **Templates:** link *GuardPrompt Platform*
- **Macros** (the proxy is on `openwebui_net`, so use **container-name** URLs):

  | Macro | Value |
  |---|---|
  | `{$GP.PROXY.URL}` | `http://gp-claude-proxy:8006/metrics` |
  | `{$GP.GLINER.URL}` | `http://gliner:8000/metrics` |
  | `{$GP.ANON.URL}` | `http://anonymizer:8005/metrics` |
  | `{$GP.NODE.URL}` | `http://node-exporter:9100/metrics` |
  | `{$GP.PG.URL}` | `http://postgres-exporter:9187/metrics` |
  | `{$GP.QDRANT.URL}` | `http://qdrant:6333/metrics` |
  | `{$GP.QDRANT.APIKEY}` | *(the `QDRANT_API_KEY` from `.env`)* |
  | `{$GP.BLACKBOX}` | `http://blackbox-exporter:9115` |
  | `{$GP.CERT.TARGET}` | your public URL, e.g. `https://chat.company.lt` |
  | `{$GP.DISK.MOUNT}` | `/` or `/srv` (the real disk on the work host — **not** `/mnt/docker-desktop-disk`) |

## 6. Verify

- Proxy *Last seen* is recent (step 4).
- **Monitoring → Latest data**, filter by the host → items collecting (e.g.
  `qdrant: total vectors`, `proxy: fail-closed total`).
- Trigger a harmless test if you like (e.g. stop gliner briefly → the
  `gliner /metrics not answering` trigger fires with its remediation text).

---

## Notifications & remediation

You do **not** configure alerting here — your corporate Zabbix already owns media
types and actions. Every GuardPrompt trigger ships a *Cause → Fix* runbook in its
description, exposed as the **`{TRIGGER.COMMENTS}`** macro. Add that macro to your
existing action message template and each alert carries *what broke and how to fix
it*.

## Turning the bundled server off (optional)

Once the corporate server owns monitoring, free the local resources:

```bash
docker compose stop zabbix-server zabbix-web zabbix-postgres
```

The `zabbix-proxy` keeps forwarding. Re-start them anytime for a local view.

## Notes & gotchas

- **Active proxy = outbound only.** No inbound port is published; the firewall
  rule you need is *GuardPrompt host → corporate Zabbix :10051*.
- **PSK file** `monitoring/zabbix_proxy.psk` is gitignored and excluded from
  `publish.ps1` — it never leaves the host.
- **Reachability:** the proxy resolves container names because it is on
  `openwebui_net`; do not switch the macros to `127.0.0.1` (the proxy has its own
  network namespace).
- **Two proxies with the same name clash** — pick one `ZBX_PROXY_NAME` per host.
