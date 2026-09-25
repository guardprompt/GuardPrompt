> 🌐 **Kalba / Language:** **Lietuvių** · [English](ZABBIX-INTEGRATION.md)

# GuardPrompt → korporatyvinis Zabbix (per vietinį Zabbix proxy)

Persiųsk visas GuardPrompt metrikas į **esamą įmonės Zabbix** nesusilpninant
platformos tinklo hardening'o ir nepaleidžiant dviejų stebėsenos serverių.

GuardPrompt `/metrics` prijungti prie `127.0.0.1`, tad Zabbix serveris kitame
host'e tiesiogiai jų neskaitys. Sprendimas — **vietinis Zabbix proxy**:
konteineris `openwebui_net` tinkle, skaitantis vidinius `/metrics` per container
vardą ir jungiantis **išeinančiu** ryšiu į tavo korporatyvinį Zabbix serverį.
Nieko naujo neatveriama; loopback hardening lieka.

```
GuardPrompt host
  ┌───────────────────────────────────────────┐
  │ gp-claude-proxy / gliner / anonymizer /    │   skaito viduje
  │ qdrant / node / cadvisor / pg / blackbox   │◀──(container-name /metrics)──┐
  │                                            │                              │
  │   zabbix-proxy  ──────────────────────────────── išeinantis :10051 (PSK)─┼──▶ Įmonės Zabbix serveris
  └───────────────────────────────────────────┘                              │
```

Bundled standalone Zabbix (`zabbix-server` / `zabbix-web`) — **nepaliestas** —
lieka vietinei peržiūrai, arba jį sustabdai, kai stebėseną perima korporatyvinis
serveris. Proxy — **opt-in**: veikia tik su `external-zabbix` compose profiliu.

---

## Reikalavimai

- Admin prieiga korporatyviniame Zabbix (sukurt Proxy, Host, importuot template).
- GuardPrompt host pasiekia įmonės Zabbix serverį **TCP 10051 išeinančiu**.
> ⚠️ **Proxy versija turi sutapt su serveriu (7.0).** Zabbix proxy negali būt
> kito major nei serveris — 6.0 proxy **NEsijungs** prie 7.0 serverio. Compose
> image default `alpine-7.0-latest` (mūsų korporatyvinis serveris 7.0); nustato
> `ZBX_PROXY_VERSION` `.env`. Bundled standalone `zabbix-server`/`web` taip pat
> migruoti į **7.0** (`ZBX_VERSION`), tad visa platforma dabar 7.0.

- **Template importuojasi į 7.0 kaip yra — patikrinta.** `monitoring/zabbix_guardprompt.yaml`
  yra `version: '6.0'` eksportas; Zabbix 7.0 importuoja senesnius tiesiogiai, ir mes
  patvirtinom, kad jis re-importuojasi į gyvą 7.0 **be klaidų** (items, trigeriai su
  remediacija, LLD ir macros nepaliesti). Tiesiog importuok failą — redaguot nereikia.

---

## 1. Importuok template

Korporatyviniame Zabbix: **Data collection → Templates → Import** →
`monitoring/zabbix_guardprompt.yaml`. Įtraukia visus items, trigerius (kiekvienas
su *Priežastis → Sprendimas* remediacija description'e), per-user LLD ir macros.

## 2. Sukurk Proxy + PSK

**GuardPrompt host'e** sugeneruok pre-shared raktą:

```bash
openssl rand -hex 32 > monitoring/zabbix_proxy.psk
chmod 600 monitoring/zabbix_proxy.psk
```

Korporatyviniame Zabbix: **Administration → Proxies → Create proxy**
- **Proxy name:** `GuardPrompt-proxy` (turi sutapt su `ZBX_PROXY_NAME` / `ZBX_HOSTNAME`)
- **Proxy mode:** *Active*
- **Encryption:** *PSK* — **PSK identity** = `GuardPrompt-proxy` (`ZBX_PROXY_PSK_ID`),
  **PSK** = hex eilutė iš failo aukščiau.

## 3. Sukonfigūruok `.env`

```bash
CORP_ZABBIX_SERVER=zabbix.company.lan     # tavo Zabbix serveris (ar jo proxy)
CORP_ZABBIX_PORT=10051
ZBX_PROXY_NAME=GuardPrompt-proxy
ZBX_PROXY_PSK_ID=GuardPrompt-proxy
```

## 4. Paleisk proxy (opt-in profilis)

```bash
docker compose --profile external-zabbix up -d zabbix-proxy
docker compose logs -f zabbix-proxy      # lauk "proxy started", tada ryšių į serverį
```

Per minutę korporatyvinio Zabbix **Administration → Proxies** sąraše `GuardPrompt-proxy`
rodo šviežų *Last seen*.

## 5. Sukurk Host (stebimą per proxy)

Korporatyviniame Zabbix: **Data collection → Hosts → Create host**
- **Host name:** pvz. `GuardPrompt-<vieta>`
- **Monitored by proxy:** `GuardPrompt-proxy`
- **Templates:** prilink *GuardPrompt Platform*
- **Macros** (proxy yra `openwebui_net`, tad **container-name** URL):

  | Macro | Reikšmė |
  |---|---|
  | `{$GP.PROXY.URL}` | `http://gp-claude-proxy:8006/metrics` |
  | `{$GP.GLINER.URL}` | `http://gliner:8000/metrics` |
  | `{$GP.ANON.URL}` | `http://anonymizer:8005/metrics` |
  | `{$GP.NODE.URL}` | `http://node-exporter:9100/metrics` |
  | `{$GP.PG.URL}` | `http://postgres-exporter:9187/metrics` |
  | `{$GP.QDRANT.URL}` | `http://qdrant:6333/metrics` |
  | `{$GP.QDRANT.APIKEY}` | *(`QDRANT_API_KEY` iš `.env`)* |
  | `{$GP.BLACKBOX}` | `http://blackbox-exporter:9115` |
  | `{$GP.CERT.TARGET}` | tavo viešas URL, pvz. `https://chat.company.lt` |
  | `{$GP.DISK.MOUNT}` | `/` arba `/srv` (tikras diskas darbo host'e — **ne** `/mnt/docker-desktop-disk`) |

## 6. Patikra

- Proxy *Last seen* šviežias (4 žingsnis).
- **Monitoring → Latest data**, filtruok pagal host → items renka (pvz.
  `qdrant: total vectors`, `proxy: fail-closed total`).
- Nori — nekenksmingas testas (pvz. trumpam sustabdyk gliner → suveiks
  `gliner /metrics not answering` trigeris su remediacija).

---

## Pranešimai ir remediacija

Aliarmų čia **nekonfigūruoji** — korporatyvinis Zabbix jau turi media types ir
actions. Kiekvienas GuardPrompt trigeris neša *Priežastis → Sprendimas* runbook'ą
description'e, atskleistą per **`{TRIGGER.COMMENTS}`** macro. Pridėk tą macro į
esamą action žinutės šabloną — ir kiekvienas aliarmas neša *kas lūžo ir kaip taisyti*.

## Bundled serverio išjungimas (nebūtina)

Kai korporatyvinis serveris perima stebėseną, atlaisvink vietinius resursus:

```bash
docker compose stop zabbix-server zabbix-web zabbix-postgres
```

`zabbix-proxy` toliau persiunčia. Bet kada paleisk atgal vietinei peržiūrai.

## Pastabos ir spąstai

- **Aktyvus proxy = tik išeinantis.** Jokio inbound porto; firewall taisyklė:
  *GuardPrompt host → korporatyvinis Zabbix :10051*.
- **PSK failas** `monitoring/zabbix_proxy.psk` gitignore'intas ir išskirtas iš
  `publish.ps1` — niekad neišeina iš host'o.
- **Pasiekiamumas:** proxy sprendžia container vardus, nes yra `openwebui_net`;
  nekeisk macro į `127.0.0.1` (proxy turi savo tinklo namespace).
- **Du proxy tuo pačiu vardu konfliktuoja** — vienas `ZBX_PROXY_NAME` host'ui.
