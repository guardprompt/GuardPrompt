> 🌐 **Language / Kalba:** **English** · [Lietuvių](MONITORING.lt.md)

# GuardPrompt — Monitoring

How the whole GuardPrompt platform is observed: what is collected, how it reaches
your monitoring system, and which conditions raise an alert **before** they turn
into an incident. The deep metric→trigger reference is in
[MONITORING-PLAN.md](MONITORING-PLAN.md); this page is the operational guide.

---

## 1. Architecture — one collection type

Everything speaks **one language** (Prometheus text over HTTP) and is read by
**one mechanism** (the Zabbix **HTTP agent** — the server scrapes each `/metrics`
URL). No agent is installed inside the containers, and nothing pushes.

```
apps + exporters  ──(/metrics, Prometheus text)──▶  Zabbix HTTP agent
                                                     ├─ LLD (per-user, per-container)
                                                     ├─ preventive + leak triggers
                                                     └─ dashboard
```

Three kinds of source, one format:

| Source | Provides |
|---|---|
| **App `/metrics`** — gp-claude-proxy, gliner, anonymizer | business, performance, safety, and leak/quality signals from inside each service |
| **Native** — qdrant `/metrics` | vector store health |
| **Standard exporters** — node, cAdvisor, postgres, blackbox, DCGM | host, containers, database + usage SQL, synthetic probes, GPU |

Per-user usage is **not** in `/metrics` (it would explode label cardinality); it
comes from the `gp_audit` table via the postgres-exporter custom queries.

Grafana can be added later with the Zabbix datasource — **no change to any source**.

---

## 2. What is monitored

**Custom app metrics** (`GET /metrics` on each service):

- **gp-claude-proxy** — requests + latency (per endpoint), masking duration and
  masked-span count, upstream status/`429`/reachability, **`fail_closed`** (masking
  refused — a safety alert), gliner/audit errors, and leak gauges: DB-pool
  in-use/idle/max, upstream in-flight, **event-loop lag**, asyncio task count,
  cache size/hits/misses/evictions, plus `process_*` memory/FD/threads.
- **gliner** — analyze + injection request rate and latency, entities found,
  **`model_on_gpu`** (0/1 — catches a silent CPU fallback), GPU availability,
  batch size, **queue depth**, injection detections, inference errors.
- **anonymizer** — request rate/latency, masked spans, **`fail_closed`**
  (`license` / `gliner` reason), injection detections.

**Infrastructure** (standard exporters, no code):

- **node-exporter** — host CPU/mem/**disk** (`/` and `/srv`)/net.
- **cAdvisor** — per-container mem/cpu/net/fd, **OOMKilled**, restart counts.
- **postgres-exporter** — connections, DB & table sizes, `pg_stat_*`, and the
  custom queries: per-user usage, DAU/WAU, `gp_audit` **dead-tuple bloat** and
  autovacuum age, vault size, idle-in-transaction connections.
- **blackbox-exporter** — synthetic HTTP/TCP probes: external-dependency
  reachability (OpenRouter, Anthropic, embeddings), **TLS certificate expiry**,
  end-to-end checks.
- **DCGM-exporter** — GPU util/VRAM/temp/ECC (production hosts with a real NVIDIA
  runtime; not Docker Desktop, limited on vGPU).
- **qdrant** — native `/metrics` (scraped directly).

---

## 3. Deploy

**3.1 App `/metrics`** ship inside the three service images already — nothing to
enable. `gliner`'s port is published to `127.0.0.1:8500` so a host-local Zabbix
can scrape it; the proxy (`:8006`) and anonymizer (`:8005`) are already reachable.

**3.2 Exporters** — bring them up (loopback-bound):

```bash
docker compose up -d node-exporter cadvisor postgres-exporter blackbox-exporter
```

GPU host only:

```bash
docker compose up -d dcgm-exporter
```

**vGPU licence metric (GPU host only).** No exporter reports the NVIDIA vGPU
(Grid) licence state, and `gliner_model_on_gpu` **cannot** catch a *runtime*
licence drop (it is set once at startup and stays `1`). A host cron feeds it to
node-exporter via the textfile collector:

```bash
# Invoke via /bin/bash (not ./script): the repo is published from Windows, so git
# stores the file without the exec bit and every `git reset --hard` would strip
# +x — a `./script` cron then dies with "Permission denied", freezing the metric
# at its last value while Zabbix alerts on a stale licence. `bash <file>` ignores
# the exec bit. `grep -v` keeps the cron entry unique across re-runs.
( crontab -l 2>/dev/null | grep -v gpu-license-textfile.sh; \
  echo "* * * * * /bin/bash $(pwd)/monitoring/gpu-license-textfile.sh" ) | crontab -
```

It writes `node_nvidia_vgpu_licensed` (1/0) into `monitoring/textfile/`, which
node-exporter mounts read-only (`--collector.textfile.directory`). The template
alerts on `=0` (**disaster**, fires the instant the licence lapses — before
gliner errors block users). Skip on dev (no GPU / no cron).

Config lives in `monitoring/` — `pg_queries.yaml` (usage + bloat SQL),
`blackbox.yml` (probe modules) and `gpu-license-textfile.sh` (vGPU licence).

**3.3 Verify a source** (example):

```bash
curl -s http://127.0.0.1:8006/metrics | grep gp_fail_closed_total
curl -s "http://127.0.0.1:9115/probe?target=https://openrouter.ai/api/v1/models&module=http_api_alive" | grep probe_success
```

---

## 4. Zabbix

**Import** `monitoring/zabbix_guardprompt.yaml` (Data collection → Templates →
Import). It defines master HTTP items that scrape each `/metrics` blob and
dependent items that extract single values with Prometheus preprocessing — one
scrape, many metrics.

**Macros.** The URL macros default to **container names** on `openwebui_net`
(e.g. `http://gp-claude-proxy:8006/metrics`, `http://gliner:8000/metrics`) — the
bundled Zabbix runs as a container on that network, so `127.0.0.1` would be the
Zabbix container itself, not the host (the #1 gotcha). These work out of the box;
override only if a Zabbix server runs **outside** the compose network. Per-host
values to set: `{$GP.QDRANT.APIKEY}` = `QDRANT_API_KEY` (qdrant does not exempt
`/metrics`), `{$GP.CERT.TARGET}` (the domain whose certificate to watch) and
`{$GP.DISK.MOUNT}` (the data disk, e.g. `/srv`). Set these as **host** macros —
a template re-import resets template-level macros, host macros survive.

**Link** the template to a host, and (optionally) add the official Zabbix
templates for node-exporter, cAdvisor and blackbox alongside it.

> The template is provided as a starting point and was **not** import-tested
> against a live Zabbix; adjust the version line or any preprocessing your Zabbix
> rejects. Extend it by cloning a dependent item for any other metric in
> [MONITORING-PLAN.md](MONITORING-PLAN.md).

---

## 5. Alerting — preventive, not reactive

Triggers predict a problem **before** it lands, using `forecast()`, `timeleft()`,
`nodata()` and trend baselines, with warn→high→disaster severity.

| Trigger | Why it matters |
|---|---|
| **`fail_closed` fired** (proxy, anonymizer) | masking was refused — a potential leak path; **disaster**, immediate |
| **vGPU Grid licence lapsed** (`node_nvidia_vgpu_licensed = 0`) | the NVIDIA vGPU licence dropped (DLS/token unreachable) → **all** CUDA compute blocked (`cudaErrorDeviceNotLicensed`); **disaster**, fires *before* gliner errors block users |
| **gliner inference errors** (`gliner_inference_errors_total` rising) | the NER forward pass is throwing — in-service catch for the licence drop above (or OOM/driver) |
| **`gliner_model_on_gpu = 0`** | the NER model was on CPU **at startup** — throughput collapses. ⚠️ Does **not** catch a *runtime* licence drop (set once at load, stays `1`); that is what the two rows above are for |
| gliner **queue depth** climbing | consumer slower than producer — overload building |
| proxy **event-loop lag** high | the single worker is blocked on CPU-bound work, starving I/O |
| proxy **DB pool** trending to its max | connection leak → exhaustion, predicted early |
| **disk `timeleft` < 7d** (`/`, `/srv`) | predicts a full disk before it stops the platform |
| **cert `timeleft` < 14d** | the class of failure behind a past `502` |
| `gp_audit` **dead tuples ≫ live** | prune DELETEs bloating the table; autovacuum not keeping up |
| **idle-in-transaction** connections | a stuck transaction / connection leak |
| **qdrant RECOVERY mode** | the vector DB booted degraded (corruption / prior OOM) — reads/writes at risk |
| **qdrant indexing backlog** (`update_queue_length`) | writes outpacing indexing → RAG returns stale/missing results, the qdrant signal that "starts failing under load" |
| **qdrant dead shard replicas** | a shard replica is down — data-availability risk |
| **`nodata`** on any source | a service stopped reporting — caught before users notice |

Usage widgets (active users, requests, per-user via LLD) sit on the same board.

> **Qdrant `/metrics` needs the api-key.** Since the internal-net hardening,
> qdrant requires `api-key` on every REST call and does **not** exempt `/metrics`.
> The Zabbix master item sends it via the `{$GP.QDRANT.APIKEY}` macro (set per
> host to `QDRANT_API_KEY`); `{$GP.QDRANT.URL}` points at `http://qdrant:6333/metrics`.

### Every trigger carries its own fix

Each trigger's **description** holds a short *Cause → Fix* runbook (the exact
`docker`/`psql` commands to diagnose and resolve it). It shows in the Zabbix
problem detail and is available to notifications as the `{TRIGGER.COMMENTS}`
macro — so an on-call engineer sees *what broke and how to fix it* in the alert
itself, not just that something is red.

**To deliver alerts:** configure a **media type** (email / Slack / webhook to
`NOTIFY_URL`) and a **trigger action** whose message includes `{TRIGGER.NAME}`,
`{TRIGGER.SEVERITY}`, `{ITEM.LASTVALUE}` and `{TRIGGER.COMMENTS}` (the fix steps).
Email needs your SMTP host; a webhook needs only the URL.

---

## 6. Leak & code-quality detection

Leaks are found as growth that **does not return**: a rising `trendmin()` floor
day-over-day is a leak (unlike a load spike, which falls back). The signals that
feed this — RSS/FD/thread trends (free from `prometheus_client`), DB-pool in-use,
idle-in-transaction, asyncio-task and queue growth, `gp_audit` bloat, and the
proxy **event-loop lag** — are all in the template or the exporters. See
[MONITORING-PLAN.md](MONITORING-PLAN.md) for the full leak-trigger catalogue.

---

## 7. Dev vs. production notes

- On **Docker Desktop** (dev) node-exporter sees the WSL2 VM, not Windows, and
  DCGM will not start. On the **native Ubuntu** work host both see the real box,
  including `/srv`; you may re-add `,rslave` to node-exporter's mount for full
  nested-mount visibility.
- All exporter ports are bound to `127.0.0.1`, so an external Zabbix server
  cannot scrape them directly. To feed a **corporate Zabbix**, run the opt-in
  local **Zabbix proxy** (`docker compose --profile external-zabbix up -d
  zabbix-proxy`) — it scrapes internally and forwards outbound. Full steps:
  **[ZABBIX-INTEGRATION.md](ZABBIX-INTEGRATION.md)**.
- App `/metrics` (proxy, gliner, anonymizer) carry only aggregate counts, never
  content; the anonymizer's is in its `PUBLIC_PATHS` so the API-key middleware
  does not block the scrape. **Qdrant `/metrics` DOES require the api-key** since
  the internal-net hardening — the template sends it via `{$GP.QDRANT.APIKEY}`.

## 8. Runbook — common alerts & fixes

Field-tested resolutions for the alerts this template raises. Every trigger also
carries its own `description` with a fix; this is the consolidated version.

### GPU VRAM nearly exhausted (HIGH) / gliner OOM
The one L40S-24C vGPU is shared by gliner + OWUI embed/reranker + docling +
gp-transcribe + ollama. When free VRAM runs out, gliner's NER throws CUDA OOM →
gp-claude/openai-proxy fail-closed → **503 for all chat**. This trigger is the early
warning (fires ~2 GB free, before the OOM).
- `nvidia-smi` — find the hog (map PID→container via `/proc/<pid>/cgroup`).
- Free ~5 GB: ollama `OLLAMA_KEEP_ALIVE=5m` (unloads idle gemma), lower
  `DOCLING_CUDA_MEM_GB` (per-process cap, default 6), or move OWUI reranker/embedding
  to CPU.
- gliner survives OOM by falling back to CPU (see next) — no 503, just slow.
- **Do NOT** set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments` on gliner — this vGPU
  has no CUDA VMM, so it throws "operation not supported" and gliner loads on CPU. Use
  `max_split_size_mb:256` instead.

### gliner NER on CPU / CPU-fallback (HIGH / AVERAGE)
gliner ran on CPU (~17x slower). Either it restarted while the GPU was full/broken and
`.to("cuda")` failed at load (`gliner_model_on_gpu=0`), or a request hit CUDA OOM and it
degraded per-request (`gliner_cpu_fallback_total`). Fix: free VRAM **first**, then
`docker restart gliner`; confirm the log says `NER model on GPU (cuda)`. If the error is
"operation not supported", check `PYTORCH_CUDA_ALLOC_CONF` is `max_split_size_mb`, not
`expandable_segments`.

### Disk timeleft low (WARNING) — usually build-cache churn
Not necessarily a real capacity problem: `/srv` is 2 TB. The timeleft **forecast** fires
on rapid growth, and every `docker compose up -d --build` (each publish) piles up build
cache (seen 85 GB). Safe reclaim, host-side (never in a container — no docker.sock):
`docker builder prune -f --reserved-space 20GB` + `docker image prune -f` (dangling only;
**never** `-a`/volumes/`system prune` on this shared host). This is automated by the
`gp-docker-prune.timer` systemd timer running `scripts/gp-docker-cache-prune.sh` daily.

### proxy fail-closed fired (DISASTER)
Pseudonymization failed so the request was refused (no data leaked, users blocked) —
almost always gliner is down or on CPU/erroring. Fix gliner (above); it clears once
masking works. **Never** set `GP_FAIL_CLOSED=false` (that would forward raw data).

### Meeting upload returns 500 (large recordings)
Full-file transcription (`/_gp/transcribe_full`) of a long meeting can 500. If gp-transcribe
logged nothing, it is the nginx `auth_request`: the `_authcheck` subrequest rejects a body
over its `client_max_body_size` (413 → auth "unexpected status" → 500). The location now sets
`client_max_body_size 300m`. Signature: "too large body … subrequest: /_gp/_authcheck".

### KB attached but the model answers generally
Not a monitoring alert, but the most common support ticket — see
**[KB-ADMIN-APP-PLAN.md §15](KB-ADMIN-APP-PLAN.md)**: set the model's Function Calling to
**Legacy**, and add KB files at the root (not a subfolder).
