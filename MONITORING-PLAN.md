# GuardPrompt — Monitoring plan (Zabbix, HTTP-agent uniform)

> ✅ **STATUS: BUILT & DEPLOYED (2026-07-23).** This is the original design doc,
> kept for the rationale behind each metric and trigger. The system it describes
> is implemented and running — for the delivered stack, the importable template,
> the dashboard and the operator guide see **[MONITORING.md](MONITORING.md)**
> (Lithuanian: [MONITORING.lt.md](MONITORING.lt.md)). All three app `/metrics`,
> the exporters, the Zabbix stack (migrated 6.0 → **7.0**), the per-user LLD and 14 triggers are
> live. Remaining operator tasks: change the Zabbix Admin password and set the
> `{$GP.DISK.MOUNT}` macro for the target host.

Design agreed 2026-07-23. One collection type (**Zabbix HTTP agent**) scrapes
Prometheus-text `/metrics` from every source; nothing pushes, no per-app agent.
Dashboards in Zabbix (Grafana later via the Zabbix datasource, no source change).

```
apps + exporters  --(/metrics, Prometheus text)-->  Zabbix HTTP agent
                                                      -> LLD (per-user/-container)
                                                      -> preventive triggers
                                                      -> dashboard
```

Three feeder types, one format:
1. **App `/metrics`** — gp-claude-proxy, gliner, anonymizer (this spec).
2. **Native** — qdrant `/metrics`.
3. **Standard exporters** — node_exporter (host), cAdvisor (containers),
   postgres_exporter (DB + usage SQL), DCGM-exporter (GPU), blackbox_exporter
   (synthetic end-to-end + external dep reachability).

Usage/business per-user stays OUT of `/metrics` (cardinality) — it comes from
`gp_audit` + the OpenWebUI DB via postgres_exporter custom queries.

---

## Common to all three apps

Add `prometheus_client`; it exports these FREE (base for leak/mem detection):
`process_resident_memory_bytes`, `process_open_fds`, `process_max_fds`,
`process_threads`, `process_cpu_seconds_total`, `python_gc_*`.
Endpoint: `GET /metrics` → `generate_latest()` (Prometheus text).

Metric legend: **[B]** business/usage · **[P]** preventive/perf · **[L]** leak/quality.

---

## 1. gp-claude-proxy `/metrics`

| Metric | Type | Labels | Class | Feeds trigger |
|---|---|---|---|---|
| `gp_requests_total` | counter | endpoint,status | B/P | 4xx/5xx rate |
| `gp_request_duration_seconds` | histogram | endpoint | P | p95↑ vs baseline; p99/p50 tail |
| `gp_mask_duration_seconds` | histogram | — | P/L | masking latency creep |
| `gp_masked_spans_total` | counter | — | B/P | spans/req drop = masking degrading |
| `gp_upstream_status_total` | counter | code | P | **429**/5xx rate rising |
| `gp_upstream_reachable` | gauge 0/1 | — | P | Anthropic reachability |
| `gp_fail_closed_total` | counter | reason | **SAFETY** | **>0 → critical now** |
| `gp_gliner_errors_total` | counter | — | P | gliner dependency failing |
| `gp_audit_write_errors_total` | counter | — | L | audit path failing |
| `gp_db_pool_size` / `_inuse` / `_idle` | gauge | — | **L** | pool leak / exhaustion forecast |
| `gp_http_connections_active` | gauge | — | **L** | httpx conn leak trend |
| `gp_asyncio_tasks` | gauge | — | **L** | task leak (create_task piling) |
| `gp_event_loop_lag_seconds` | gauge | — | **L** | **1-worker + regex blocking loop** |
| `gp_cache_size` | gauge | — | L | cache at MAX / thrashing |
| `gp_cache_hits_total` / `_misses_total` / `_evictions_total` | counter | — | P/L | hit% drop → gliner load ↑ |

## 2. gliner `/metrics`

| Metric | Type | Labels | Class | Feeds trigger |
|---|---|---|---|---|
| `gliner_analyze_requests_total` | counter | status | B/P | error rate |
| `gliner_analyze_duration_seconds` | histogram | — | P | p95↑ before 500ms SLA |
| `gliner_entities_found_total` | counter | — | B | detection volume |
| `gliner_batch_size` | histogram | — | P | batching health (=1 → no batching) |
| `gliner_batch_wait_seconds` | histogram | — | P | wait creep |
| `gliner_queue_depth` | gauge | — | **L/P** | **consumer<producer, unbounded → alert** |
| `gliner_model_on_gpu` | gauge 0/1 | — | **P** | **=0 → GPU fell back to CPU (our bug!)** |
| `gliner_gpu_available` | gauge 0/1 | — | P | CUDA visibility |
| `gliner_injection_requests_total` | counter | status | B/P | — |
| `gliner_injection_duration_seconds` | histogram | — | P | — |
| `gliner_injection_detected_total` | counter | — | B/SEC | spike = possible attack |
| `gliner_inference_errors_total` | counter | — | P/L | model errors |

## 3. anonymizer `/metrics` (OpenWebUI ingestion path)

| Metric | Type | Labels | Class | Feeds trigger |
|---|---|---|---|---|
| `anon_requests_total` | counter | status | B/P | error rate |
| `anon_duration_seconds` | histogram | — | P | latency creep |
| `anon_masked_spans_total` | counter | — | B/P | coverage drop |
| `anon_fail_closed_total` | counter | reason | **SAFETY** | **>0 → critical** |
| `anon_gliner_errors_total` | counter | — | P | dependency |
| `anon_injection_detected_total` | counter | — | SEC | attack signal |
| `anon_queue_depth` | gauge | — | L | backlog (if queued) |

---

## Exporters (no app code — standard containers)

| Exporter | Provides | Key leak/preventive signal |
|---|---|---|
| node_exporter | host CPU/mem/disk/net | **`/` (96 GB) + `/srv` (2 TB)** `timeleft()`; mem trendmin |
| cAdvisor | per-container mem/cpu/net/fd | **OOMKilled**, container mem `forecast()`, restart count |
| postgres_exporter | connections, DB/table size, **n_dead_tup**, autovacuum, idle-in-transaction | **audit/vault bloat**; pool exhaustion; usage SQL |
| DCGM-exporter | GPU util/VRAM/temp/ECC | VRAM→OOM; util; temp |
| blackbox_exporter | HTTP/TCP probes | **cert `timeleft()`** (NPM/CF), external deps (OpenRouter/Anthropic/embeddings), synthetic end-to-end, `nodata()` |

Usage-by-user (postgres_exporter custom queries on `gp_audit` + OpenWebUI DB):
requests/tokens/masked-spans per user/day, DAU/MAU, docs ingested, chats, RAG
queries, model split, seat utilization, storage growth.

---

## Trigger layers (all with warn→high→disaster tiers)

- **Capacity (predict):** disk `timeleft()`<7d/48h/12h; table-size timeleft;
  pool `forecast()`>70%; VRAM→OOM.
- **Perf (before SLA):** gliner/proxy p95 trend; queue depth; cache-hit drop;
  **`gliner_model_on_gpu`=0**.
- **Availability:** `nodata()` on any `/metrics`; external-dep latency/flap;
  **cert timeleft<14d**; 429/5xx rate.
- **Safety (immediate):** **`*_fail_closed_total`>0**; injection spike;
  masked-spans/req drop; license `timeleft()`.
- **Lifecycle:** restart-count rate; watchtower-update→post-health; prune-not-running.
- **Leak/quality:** RSS `trendmin()` rising 3d; OOMKilled; FD/socket trend;
  idle-in-transaction>0; asyncio-task/thread trend; queue unbounded;
  **audit `n_dead_tup`** + autovacuum lag; ERROR-log rate; **event-loop lag**;
  p99/p50 ratio; CPU baseline creep.

---

## Build order

1. **App `/metrics`** — add `prometheus_client` + the counters/gauges/histograms
   above to gp-claude-proxy, gliner, anonymizer (this is the only code).
2. **Exporters** — compose services + config (node, cAdvisor, postgres_exporter
   with custom usage queries, DCGM, blackbox with probe list).
3. **Zabbix** — HTTP-agent templates per source + Prometheus preprocessing + LLD
   + the trigger catalog + dashboard. (Grafana later via Zabbix datasource.)
