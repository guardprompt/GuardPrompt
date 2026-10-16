> 🌐 **Language / Kalba:** [English](MONITORING.md) · **Lietuvių**

# GuardPrompt — Stebėsena

Kaip stebima visa GuardPrompt platforma: kas renkama, kaip pasiekia jūsų
stebėsenos sistemą ir kokios sąlygos sukelia aliarmą **prieš** virstant
incidentu. Gili metrikų→trigerių nuoroda — [MONITORING-PLAN.md](MONITORING-PLAN.md);
šis puslapis — operacinis vadovas.

---

## 1. Architektūra — vienas rinkimo tipas

Viskas kalba **viena kalba** (Prometheus text per HTTP) ir skaitoma **vienu
mechanizmu** (Zabbix **HTTP agent** — serveris pats scrape'ina kiekvieną
`/metrics` URL). Jokio agento konteineriuose, niekas nestumia.

```
app'ai + exporteriai  ──(/metrics, Prometheus text)──▶  Zabbix HTTP agent
                                                        ├─ LLD (per-user, per-container)
                                                        ├─ preventyvūs + leak trigeriai
                                                        └─ dashboard
```

Trys šaltinių tipai, vienas formatas:

| Šaltinis | Ką duoda |
|---|---|
| **App `/metrics`** — gp-claude-proxy, gliner, anonymizer | business, našumo, saugos ir leak/kokybės signalai iš serviso vidaus |
| **Native** — qdrant `/metrics` | vektorinės saugyklos būklė |
| **Standartiniai exporteriai** — node, cAdvisor, postgres, blackbox, DCGM | host, konteineriai, DB + usage SQL, synthetic probes, GPU |

Per-user usage **nėra** `/metrics` (išsprogdintų label cardinality) — jis eina iš
`gp_audit` lentelės per postgres-exporter custom queries.

Grafana pridedama vėliau per Zabbix datasource — **be pakeitimų šaltiniuose**.

---

## 2. Kas stebima

**Custom app metrikos** (`GET /metrics` kiekviename servise):

- **gp-claude-proxy** — užklausos + latency (pagal endpoint), maskavimo trukmė ir
  užmaskuotų span skaičius, upstream status/`429`/pasiekiamumas, **`fail_closed`**
  (maskavimas atmestas — saugos aliarmas), gliner/audit klaidos, ir leak gauges:
  DB-pool in-use/idle/max, upstream in-flight, **event-loop lag**, asyncio task
  skaičius, cache size/hits/misses/evictions, plius `process_*` memory/FD/threads.
- **gliner** — analyze + injection užklausų dažnis ir latency, rastos entities,
  **`model_on_gpu`** (0/1 — pagauna tylų CPU fallback), GPU prieinamumas, batch
  size, **queue depth**, injekcijų detektai, inference klaidos.
- **anonymizer** — užklausų dažnis/latency, masked spans, **`fail_closed`**
  (`license` / `gliner` priežastis), injekcijų detektai.

**Infrastruktūra** (standartiniai exporteriai, be kodo):

- **node-exporter** — host CPU/mem/**diskai** (`/` ir `/srv`)/net.
- **cAdvisor** — per-container mem/cpu/net/fd, **OOMKilled**, restart skaičiai.
- **postgres-exporter** — connections, DB ir lentelių dydžiai, `pg_stat_*`, ir
  custom queries: per-user usage, DAU/WAU, `gp_audit` **dead-tuple bloat** ir
  autovacuum amžius, vault dydis, idle-in-transaction connections.
- **blackbox-exporter** — synthetic HTTP/TCP probes: išorinių priklausomybių
  pasiekiamumas (OpenRouter, Anthropic, embeddings), **TLS sertifikato galiojimas**,
  end-to-end patikros.
- **DCGM-exporter** — GPU util/VRAM/temp/ECC (prod host'ai su tikru NVIDIA
  runtime; ne Docker Desktop, ribotas ant vGPU).
- **qdrant** — native `/metrics` (scrape'inamas tiesiai).

---

## 3. Diegimas

**3.1 App `/metrics`** jau įtaisyti trijų servisų image'uose — nieko įjungt
nereikia. `gliner` portas publish'intas į `127.0.0.1:8500`, kad host-local Zabbix
galėtų scrape'int; proxy (`:8006`) ir anonymizer (`:8005`) jau pasiekiami.

**3.2 Exporteriai** — paleisk (loopback):

```bash
docker compose up -d node-exporter cadvisor postgres-exporter blackbox-exporter
```

Tik GPU host:

```bash
docker compose up -d dcgm-exporter
```

**vGPU licencijos metrika (tik GPU host).** Jokis exporteris nerodo NVIDIA vGPU
(Grid) licencijos būsenos, o `gliner_model_on_gpu` **negaudo** *runtime* licencijos
kritimo (nustatoma vieną kartą startupe ir lieka `1`). Host cron atiduoda ją
node-exporter'iui per textfile collector:

```bash
# Kviesk per /bin/bash (ne ./script): repo publish'inamas iš Windows, tad git
# saugo failą be exec bito ir kiekvienas `git reset --hard` nuima +x — tada
# `./script` cron miršta su "Permission denied", metrika užšąla ties paskutine
# reikšme, o Zabbix alertina dėl pasenusios licencijos. `bash <file>` exec bito
# nepaiso. `grep -v` išlaiko cron įrašą unikalų.
( crontab -l 2>/dev/null | grep -v gpu-license-textfile.sh; \
  echo "* * * * * /bin/bash $(pwd)/monitoring/gpu-license-textfile.sh" ) | crontab -
```

Rašo `node_nvidia_vgpu_licensed` (1/0) į `monitoring/textfile/`, kurį node-exporter
mount'ina read-only (`--collector.textfile.directory`). Template alertina ties `=0`
(**disaster**, suveikia vos licencijai nulėkus — dar prieš gliner klaidas blokuojant
vartotojus). Dev'e praleisk (nėra GPU / cron).

Config yra `monitoring/` — `pg_queries.yaml` (usage + bloat SQL), `blackbox.yml`
(probe moduliai) ir `gpu-license-textfile.sh` (vGPU licencija).

**3.3 Patikrink šaltinį** (pvz.):

```bash
curl -s http://127.0.0.1:8006/metrics | grep gp_fail_closed_total
curl -s "http://127.0.0.1:9115/probe?target=https://openrouter.ai/api/v1/models&module=http_api_alive" | grep probe_success
```

---

## 4. Zabbix

**Importuok** `monitoring/zabbix_guardprompt.yaml` (Data collection → Templates →
Import). Jis apibrėžia master HTTP items kurie scrape'ina kiekvieną `/metrics`
blob'ą ir dependent items kurie ištraukia reikšmes su Prometheus preprocessing —
vienas scrape, daug metrikų.

**Macros.** URL macros default — **container vardai** `openwebui_net` tinkle
(pvz. `http://gp-claude-proxy:8006/metrics`, `http://gliner:8000/metrics`) — bundled
Zabbix sukasi kaip konteineris tame tinkle, tad `127.0.0.1` būtų pats Zabbix
konteineris, ne host'as (#1 gotcha). Veikia iš karto; keisk tik jei Zabbix server
**už** compose tinklo. Per-host reikšmės: `{$GP.QDRANT.APIKEY}` = `QDRANT_API_KEY`
(qdrant neišima `/metrics`), `{$GP.CERT.TARGET}` (domenas kurio sertifikatą stebėt),
`{$GP.DISK.MOUNT}` (duomenų diskas, pvz. `/srv`). Šias nustatyk kaip **host** macros —
template re-import nuplauna template macros, host macros išlieka.

**Prilink** šabloną prie host'o ir (pasirinktinai) pridėk oficialius Zabbix
šablonus node-exporter, cAdvisor, blackbox greta.

> Šablonas — pradinis taškas, **neimport-testuotas** prieš gyvą Zabbix; pritaikyk
> versijos eilutę ar preprocessing, jei Zabbix atmeta. Plėsk klonuodamas dependent
> item bet kuriai kitai metrikai iš [MONITORING-PLAN.md](MONITORING-PLAN.md).

---

## 5. Aliarmai — preventyvūs, ne reaktyvūs

Trigeriai numato problemą **prieš** jai įvykstant, naudodami `forecast()`,
`timeleft()`, `nodata()` ir trend baselines, su warn→high→disaster sunkumu.

| Trigeris | Kodėl svarbu |
|---|---|
| **`fail_closed` suveikė** (proxy, anonymizer) | maskavimas atmestas — galimas leak kelias; **disaster**, iškart |
| **vGPU Grid licenca nulėkė** (`node_nvidia_vgpu_licensed = 0`) | NVIDIA vGPU licenca krito (DLS/token nepasiekiamas) → **visas** CUDA compute blokuotas (`cudaErrorDeviceNotLicensed`); **disaster**, suveikia *prieš* gliner klaidas blokuojant vartotojus |
| **gliner inference klaidos** (`gliner_inference_errors_total` auga) | NER forward pass krenta — in-service gaudymas viršuj esančiam licencijos kritimui (arba OOM/driver) |
| **`gliner_model_on_gpu = 0`** | NER modelis buvo ant CPU **starto metu** — throughput griūva. ⚠️ **Negaudo** *runtime* licencijos kritimo (nustatoma vieną kartą, lieka `1`); tam skirtos dvi eilutės viršuj |
| gliner **queue depth** auga | consumer lėtesnis nei producer — kaupiasi perkrova |
| proxy **event-loop lag** aukštas | vienas worker blokuotas CPU darbo, badina I/O |
| proxy **DB pool** artėja prie max | connection leak → exhaustion, prognozuota anksti |
| **disk `timeleft` < 7d** (`/`, `/srv`) | numato pilną diską prieš sustabdant platformą |
| **cert `timeleft` < 14d** | būtent tos klasės gedimas kaip praeitas `502` |
| `gp_audit` **dead tuples ≫ live** | prune DELETE'ai pučia lentelę; autovacuum nespėja |
| **idle-in-transaction** connections | įstrigusi transakcija / connection leak |
| **qdrant RECOVERY režimas** | vektorių DB startavo degradavęs (korupcija / ankstesnis OOM) — skaitymai/rašymai rizikoje |
| **qdrant indeksavimo backlog** (`update_queue_length`) | rašymai lenkia indeksavimą → RAG grąžina pasenusius/dingusius rezultatus, qdrant signalas „pradeda feilint po apkrova" |
| **qdrant dead shard replicas** | shard replika nukritusi — duomenų pasiekiamumo rizika |
| **`nodata`** ant bet kurio šaltinio | servisas nustojo pranešt — pagauta prieš vartotojui pastebint |

Usage widget'ai (aktyvūs vartotojai, užklausos, per-user per LLD) tame pačiame board'e.

> **Qdrant `/metrics` reikia api-key.** Po vidinio tinklo sugriežtinimo qdrant
> reikalauja `api-key` kiekvienam REST kvietimui ir `/metrics` **NEexempt'ina**.
> Zabbix master item siunčia jį per `{$GP.QDRANT.APIKEY}` macro (nustatytą host'e =
> `QDRANT_API_KEY`); `{$GP.QDRANT.URL}` rodo į `http://qdrant:6333/metrics`.

### Kiekvienas trigeris neša savo pataisymą

Kiekvieno trigerio **description** turi trumpą *Priežastis → Sprendimas* runbook'ą
(tikslios `docker`/`psql` komandos diagnozei ir pataisymui). Rodoma Zabbix problemos
detalėje ir pasiekiama pranešimams per `{TRIGGER.COMMENTS}` macro — budintis
inžinierius mato *kas lūžo ir kaip taisyti* pačiame aliarme.

**Pranešimų pristatymui:** sukonfigūruok **media type** (email / Slack / webhook į
`NOTIFY_URL`) ir **trigger action**, kurios žinutėje būtų `{TRIGGER.NAME}`,
`{TRIGGER.SEVERITY}`, `{ITEM.LASTVALUE}` ir `{TRIGGER.COMMENTS}` (pataisymo žingsniai).
Email reikia tavo SMTP host'o; webhook — tik URL.

---

## 6. Leak ir kodo kokybės aptikimas

Leak'ai aptinkami kaip augimas kuris **negrįžta**: kylantis `trendmin()`
grindys diena-po-dienos = leak (skirtingai nei load spike, kuris nukrenta).
Signalai — RSS/FD/thread trend'ai (nemokamai iš `prometheus_client`), DB-pool
in-use, idle-in-transaction, asyncio-task ir queue augimas, `gp_audit` bloat,
proxy **event-loop lag** — visi šablone ar exporteriuose. Pilnas leak-trigerių
katalogas — [MONITORING-PLAN.md](MONITORING-PLAN.md).

---

## 7. Dev vs. prod pastabos

- Ant **Docker Desktop** (dev) node-exporter mato WSL2 VM, ne Windows, o DCGM
  nepasileidžia. Ant **native Ubuntu** work host'o abu mato tikrą dėžę, įskaitant
  `/srv`; gali grąžint `,rslave` node-exporter mount'ui pilnam nested-mount
  matomumui.
- Visi exporterių portai bind'inti į `127.0.0.1`, tad išorinis Zabbix serveris
  tiesiogiai jų neskaitys. **Korporatyviniam Zabbix** paleisk opt-in vietinį
  **Zabbix proxy** (`docker compose --profile external-zabbix up -d zabbix-proxy`)
  — skaito viduje, persiunčia išeinančiu. Pilni žingsniai:
  **[ZABBIX-INTEGRATION.lt.md](ZABBIX-INTEGRATION.lt.md)**.
- App `/metrics` (proxy, gliner, anonymizer) turi tik agreguotus skaičius, niekada
  turinį; anonymizer'io pridėtas į `PUBLIC_PATHS`, kad API-key middleware neblokuotų.
  **Qdrant `/metrics` api-key REIKALAUJA** po vidinio hardening'o — template siunčia
  per `{$GP.QDRANT.APIKEY}`.

## 8. Runbook — dažni alertai ir sprendimai

Praktikoje patikrinti sprendimai šio template'o alertams. Kiekvienas trigeris turi ir
savo `description` su fiksu; čia — suvestinė.

### GPU VRAM baigiasi (HIGH) / gliner OOM
Vieną L40S-24C vGPU dalijasi gliner + OWUI embed/reranker + docling + gp-transcribe +
ollama. Kai laisvos VRAM nelieka, gliner NER meta CUDA OOM → gp-claude/openai-proxy
fail-closed → **503 visiems pokalbiams**. Šis trigeris — ankstyvas perspėjimas (~2 GB
laisvos, prieš OOM).
- `nvidia-smi` — rask kas valgo (PID→konteineris per `/proc/<pid>/cgroup`).
- Atlaisvink ~5 GB: ollama `OLLAMA_KEEP_ALIVE=5m` (idle gemma iškraunama), mažink
  `DOCLING_CUDA_MEM_GB` (per-process cap, default 6), arba OWUI reranker/embedding į CPU.
- gliner OOM'ą išgyvena nukritęs ant CPU (žr. žemiau) — jokio 503, tik lėtai.
- **NEnaudok** `PYTORCH_CUDA_ALLOC_CONF=expandable_segments` gliner'iui — šis vGPU neturi
  CUDA VMM, tad meta "operation not supported" ir gliner užsikrauna ant CPU. Naudok
  `max_split_size_mb:256`.

### gliner NER ant CPU / CPU-fallback (HIGH / AVERAGE)
gliner dirbo ant CPU (~17x lėčiau). Arba jis restartino kai GPU buvo pilnas/sugedęs ir
`.to("cuda")` neįvyko starte (`gliner_model_on_gpu=0`), arba užklausa pataikė į CUDA OOM ir
degradavo per-request (`gliner_cpu_fallback_total`). Fiksas: **pirma** atlaisvink VRAM, tada
`docker restart gliner`; patikrink kad log rašo `NER model on GPU (cuda)`. Jei klaida
"operation not supported" — patikrink kad `PYTORCH_CUDA_ALLOC_CONF` yra `max_split_size_mb`,
ne `expandable_segments`.

### Disko timeleft mažas (WARNING) — dažniausiai build-cache churn
Nebūtinai tikra vietos problema: `/srv` yra 2 TB. timeleft **prognozė** suveikia dėl
staigaus augimo, o kiekvienas `docker compose up -d --build` (publish) kaupia build cache
(matyta 85 GB). Saugus valymas host'e (niekada konteineryje — jokio docker.sock):
`docker builder prune -f --reserved-space 20GB` + `docker image prune -f` (tik dangling;
**niekada** `-a`/volume/`system prune` šiame shared host'e). Tai automatizuota
`gp-docker-prune.timer` systemd timer'iu, kuris kasdien paleidžia
`scripts/gp-docker-cache-prune.sh`.

### proxy fail-closed suveikė (DISASTER)
Pseudonimizacija nepavyko → užklausa atmesta (duomenys neteko, vartotojai blokuoti) —
beveik visada gliner nukritęs ar ant CPU/klysta. Tvarkyk gliner (aukščiau); praeina kai
maskavimas veikia. **NIEKADA** nestatyk `GP_FAIL_CLOSED=false` (siųstų neužmaskuotus duomenis).

### Susitikimo įkėlimas grąžina 500 (dideli įrašai)
Full-file transkripcija (`/_gp/transcribe_full`) ilgo susitikimo gali 500'int. Jei
gp-transcribe log'e nieko — tai nginx `auth_request`: `_authcheck` subrequest'as atmeta body
didesnį nei jo `client_max_body_size` (413 → auth "unexpected status" → 500). Location dabar
nustato `client_max_body_size 300m`. Signatūra: "too large body … subrequest: /_gp/_authcheck".

### KB priskirta, bet modelis atsako bendrai
Ne monitoringo alertas, bet dažniausias ticket'as — žr.
**[KB-ADMIN-APP-PLAN.lt.md §15](KB-ADMIN-APP-PLAN.lt.md)**: modelio Function Calling nustatyk
į **Legacy** ir failus dėk KB šaknyje (ne subkataloge).
