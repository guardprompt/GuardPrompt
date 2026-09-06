> 🌐 **Kalba / Language:** **Lietuvių** · [English](KB-ADMIN-APP-PLAN.md)

# KB Admin App — MVP planas (be kodo)

Valdymo pultas (atskira app), kuriuo OpenWebUI administratoriai kuruoja žinių
bazes iš išorinių šaltinių (Confluence / Jira / SharePoint) ir priskiria prieigą
vartotojams/grupėms. Orkestruoja `oikb` + OpenWebUI prieigas.

> Statusas: ✅ **ĮGYVENDINTA IR VEIKIA** (kb-admin konteineris paleistas,
> `127.0.0.1:8090`, ~1580 eil. FastAPI: auth / confluence / jira / sharepoint /
> oikb_runner / openwebui / db / license). Šis dokumentas laikomas kaip
> architektūros/sprendimų pagrindimas. Numatyta `AUTH_MODE=openwebui`.
> Susiję: oikb kaip CLI subprocess kb-admin viduje (sk. 13.11).

---

## 1. Tikslas ir aktoriai

- **Aktorius:** OpenWebUI administratorius (gali būti keli). Privalo būti:
  1. **LDAP** vartotojas (mūsų organizacijos) — *jei LDAP įjungtas*,
  2. turintis **OpenWebUI admin** rolę.
- **Tikslas:** admin randa išorinį resursą → nustato kas matys → nustato sync
  dažnį → paleidžia → mato darbų sąrašą, gali redaguot/trinti. Viskas auditojama.

---

## 2. Bendras srautas

```
[KB Admin App — atskiras konteineris, openwebui_net tinkle]

  Login (LDAP bind, jei įjungtas) ──► OpenWebUI rolė==admin ──► sesija (cookie)
        │
        ▼
  UNIVERSALI paieška (vienas laukas):
     - išoriniai resursai: Confluence spaces / Jira projects / SharePoint
     - + esami oikb darbai (kb_jobs) — kad matytųsi kas jau sukonfigūruota
     - rezultate indikacijos: ar pasiekiama / ar jau priskirta / būsena
        │
        ▼
  Pasirinkus resursą:
     1. Prieiga (varnelės): Visi / Grupė(s) / Asmenys  (subjektai iš OpenWebUI)
     2. Sync dažnis (dropdown): 10 min / 1 val / 4 val / 12 val / 24 val
     3. KB pavadinimas: pasiūlomas automatiškai, ADMIN GALI REDAGUOTI prieš saugant
        │
        ▼
  [Sukurti darbą] ──► (async, BackgroundTask, grąžina status=processing)
     a) sukuria KB (1 resursas = 1 KB) pavadinimu, kurį patvirtino admin
     b) uždeda KB access_control pagal audience (DEKLARATYVIAI)
     c) paleidžia oikb sync fone → atnaujina kb_jobs.status DB
        │
        ▼
  Logai (audit + sync rezultatai)
  Darbų sąrašas: peržiūra / redaguot (prieiga, dažnis, pavadinimas) /
                 trinti (+oikb reset) / atšaukti pakibusį (kill pid)
```

---

## 3. Komponentai

| Sluoksnis | Technologija | Vaidmuo |
|---|---|---|
| Backend | FastAPI (Python) | API, orkestracija, async jobs, scheduler |
| DB | esamas Postgres, nauja schema `kbadmin` | darbų + audit tiesos šaltinis |
| Frontend | paprastas HTML/JS (served by FastAPI) | paieška, varnelės, darbų lentelė |
| Vykdymas | `oikb` (CLI app konteineryje arba exec) | faktinis sync |
| Konteineris | naujas compose servisas `kb-admin` | izoliuotas, openwebui_net |

---

## 4. Autentifikacija, autorizacija, sesija

**Auth režimai (env `AUTH_MODE`):**
- `ldap` — pilnas: **LDAP bind** (org katalogas) + **OpenWebUI admin** rolė. ABU.
- `openwebui` — **be LDAP** (šis kompas LDAP neturi): tik OpenWebUI admin rolė
  (+ slaptažodis tikrinamas per OpenWebUI). Numatyta išimtis dev/be-LDAP aplinkai.
- `dev` — lokalus allowlist (`ADMIN_FALLBACK_EMAILS`) — tik testavimui.

Visi režimai BŪTINAI reikalauja **OpenWebUI admin** rolės — tai bendras saugiklis.

**Sesija:** po login — **HttpOnly, Secure, SameSite=Strict signed cookie**
(serverio pusės sesija DB arba pasirašytas JWT su `SESSION_SECRET` iš env).
Jokio token'o naršyklės JS — kad paprastas HTML/JS nelaikytų paslapčių. Trumpas TTL.

**Mini apsauga nuo laužymo (brute-force):**
- Login bandymų limitas per IP/vartotoją (pvz 5/5min) → laikina blokuotė.
- Audit įrašas kiekvienam nepavykusiam login.
- Jei `AUTH_MODE=ldap` — LDAP politikos (lockout) papildo; app limitas vis tiek
  veikia kaip pirma gynyba.

---

## 5. Duomenų modelis (schema `kbadmin`)

### `kb_jobs` — kuravimo darbai (tiesos šaltinis)
| Laukas | Tipas | Aprašas |
|---|---|---|
| id | uuid | darbo id |
| source_type | text | confluence / jira / sharepoint |
| source_id | text | **numeric space ID** (oikb to reikia) |
| source_key | text | human-readable key (pvz „SD") — adminui rodyt |
| source_title | text | žmogui skaitomas pavadinimas |
| kb_id | uuid | sukurtos OpenWebUI KB id |
| kb_name | text | KB pavadinimas (admino patvirtintas/redaguotas) |
| audience_type | text | all / groups / users |
| audience_ids | jsonb | grupių/vartotojų id sąrašas |
| interval | text | 10m / 1h / 4h / 12h / 24h |
| status | text | processing / active / paused / error |
| pid | integer | vykdomo oikb proceso PID (kill/cancel) |
| error_message | text | klaidos priežastis adminui (pvz „Bad Atlassian token") |
| last_sync_at | timestamptz | paskutinio sync laikas |
| last_result | jsonb | +added/-deleted/errors |
| created_by | text | admin (LDAP/email) |
| created_at | timestamptz | |

> **Space ID vs Key:** patikrinta — oikb naudoja **numeric space ID**
> (`confluence:65857`), NE key („SD"). Saugom **abu** — ID vykdymui, Key/Title
> adminui rodyt.

### `audit_log` — admin veiksmai (kas/ką/kada)
| Laukas | Tipas | Aprašas |
|---|---|---|
| id | bigserial | |
| ts | timestamptz | kada |
| actor | text | admin (LDAP/email) |
| action | text | login / login_failed / create_job / edit_job / delete_job / manual_sync / access_change / cancel_job |
| job_id | uuid | susijęs darbas (jei yra) |
| details | jsonb | prieš/po reikšmės, auditorija ir pan. |

---

## 6. Universali paieška + resursų indikacijos

- **Vienas paieškos laukas** ieško lygiagrečiai:
  1. **Išoriniuose šaltiniuose** (Confluence spaces, Jira projects, SharePoint),
  2. **Esamuose `kb_jobs`** (kas jau sukonfigūruota) — kad nedublikuotų.
- **Indikacijos prie rezultatų** (mažos):
  - 🟢 šaltinis pasiekiamas + token galioja
  - 🔴 nepasiekiamas / blogas token / nesukonfigūruota (env trūksta)
  - ✓ „jau priskirta" (yra `kb_jobs`) → mygtukas „redaguoti" vietoj „kurti"
- **Šaltinių sveikatos patikra:** kiekvienam tipui (Confluence/Jira/SharePoint)
  app daro lengvą ping (pvz spaces sąrašas) → rodo ar tokenai/URL teisingi.

---

## 7. Prieigos modelis + DEKLARATYVUS teisių sinchronizavimas

- **OpenWebUI prieiga = per KB, NE per failą** → **1 resursas = 1 KB**.
- subjektai imami iš OpenWebUI (`/api/v1/users/`, `/api/v1/groups/`).

**Verified API (v0.9.6–v0.10.2 — naudoja `access_grants`, NE `access_control` json;
`access_grants` formatas nepakito 0.10; 0.10.2 reikalauja write access failui prisegti
prie KB — kb-admin naudoja admin raktą, tad OK):**
- Set: `POST /api/v1/knowledge/{id}/access/update` body `{"access_grants":[...]}`
- Grant dict: `{principal_type, principal_id, permission}`
  (principal_type=`user`|`group`; principal_id=id arba `"*"`; permission=`read`|`write`)
- **audience → grants:**
  - **Visi (public):** `[{"principal_type":"user","principal_id":"*","permission":"read"}]`
  - **Grupė(s):** `{"principal_type":"group","principal_id":<gid>,"permission":"read"}`
  - **Asmenys:** `{"principal_type":"user","principal_id":<uid>,"permission":"read"}`
  - **Private (default-deny):** `[]`
- KB sukuriama (`POST /api/v1/knowledge/create`), iškart privati (`access_grants=[]`),
  prieiga uždedama atskiru `/access/update` (atitinka default-deny tvarką, sk.13.2).

**⚠️ Access Sync Trap (svarbu):** teisės uždedamos NE tik kuriant, o
**deklaratyviai per kiekvieną sync** (prieš ar iškart po oikb):
- kb-admin **iš naujo pastumia** `kb_jobs.audience_ids` → OpenWebUI KB access.
- Tai garantuoja, kad kb-admin = **teisių tiesos šaltinis** šioms KB.
- Pasekmė: šių (kuruojamų) KB teises keisti reikia **pulte**, ne tiesiogiai
  OpenWebUI — kitaip kitas sync perrašys. (Rodyti adminui įspėjimą.)

---

## 8. Sync orkestracija (async, atspari)

- **Planuoja pati app** (savas scheduler pagal `interval`), NE oikb daemon.
- **Async vykdymas (FastAPI BackgroundTasks):**
  1. POST „sukurti/sync" → iškart grąžina `status=processing`.
  2. Fone: (a) užtikrint KB + access (deklaratyviai), (b) `oikb sync`,
     (c) atnaujint `kb_jobs.status`, `last_result`, `error_message`.
  3. Dideli space'ai (minutės–valandos) nedaro HTTP timeout — viskas fone.
- **PID / atšaukimas:** oikb vykdomas kaip subprocess → `pid` saugomas DB →
  adminas gali „nužudyt" pakibusį darbą; po kill status=error.
- **Rate limiting / nutrūkimai:** pirmas didelio resurso sync gali gaut HTTP 429.
  - oikb daro **inkrementinį** sync (SHA-256) → po nutrūkimo retry **tęsia**
    (kelia tik trūkstamus), ne nuo nulio.
  - `concurrency` laikom žemą (2) kad mažiau 429.
  - 429/klaida → status=error + error_message; adminas mato ir gali retry.
  - (Patikrinti tiksliai kaip oikb reaguoja į 429 — žr. sk.12.)
- **Trynimas:** `oikb reset --kb-id ...` (eina per OpenWebUI API) → ištrint KB →
  pašalint `kb_jobs` → audit.
  - **Qdrant:** valyt papildomai NEREIKIA. Patikrinta gyvai — OpenWebUI file
    delete per API **pats išvalo Qdrant** (files+knowledge 1→0). Sąlyga: visi
    trynimai eina per OpenWebUI API (oikb reset taip daro), NE tiesiai iš DB.
- Failai šiose KB **apsaugoti** nuo uploads-cleaner (jie `knowledge_file`).

---

## 9. Diegimas (compose) — visi secret'ai per env

```yaml
  kb-admin:
    build: ./kb-admin        # FastAPI + frontend + oikb CLI
    container_name: kb-admin
    environment:
      - AUTH_MODE=${KBADMIN_AUTH_MODE:-openwebui}   # ldap | openwebui | dev
      - SESSION_SECRET=${KBADMIN_SESSION_SECRET}
      - OPEN_WEBUI_URL=http://open-webui-dk:8080
      - OPEN_WEBUI_API_KEY=${OPEN_WEBUI_API_KEY}
      - DB_URL=postgresql://.../guardprompt          # schema kbadmin
      # NOTE: oikb paleidžiamas kaip subprocesas (ne HTTP daemon), tad
      # OIKB_API_KEY nereikalingas — pašalintas.
      # LDAP (tik jei AUTH_MODE=ldap)
      - LDAP_URL=${LDAP_URL:-}
      - LDAP_BIND_DN=${LDAP_BIND_DN:-}
      - LDAP_BASE_DN=${LDAP_BASE_DN:-}
      # source tokenai — iš .env (Confluence/Jira/SharePoint)
    ports:
      - "127.0.0.1:8090:8000"
    depends_on: [postgres, open-webui-dk]
    networks: [openwebui_net]
    cap_drop: [NET_RAW]
```

**Visi jautrūs duomenys** (tokenai, SESSION_SECRET, LDAP, API raktai) — **tik env**
(`.env`, ne kode, ne git; `.env.example` su tuščiais).

---

## 10. Saugumas

- Tik admin (OpenWebUI rolė visada; LDAP jei įjungtas). Visi veiksmai → `audit_log`.
- Brute-force limitas (sk.4). Sesija HttpOnly signed cookie, trumpas TTL.
- App laiko galingus token'us → vidinis tinklas, portas `127.0.0.1`, secret'ai env.

---

## 11. Etapai

1. **MVP:** auth (openwebui rolė; LDAP išimtis) + universali Confluence paieška
   + indikacijos + OpenWebUI users/groups + sukurti darbą (KB su redaguojamu
   pavadinimu + deklaratyvi prieiga + async pirmas sync) + logai.
2. **Valdymas:** darbų sąrašas + redaguot/trinti/atšaukti (pid) + scheduler
   (10m/1h/4h/12h/24h) + periodinis teisių re-push.
3. **Plėtra:** SharePoint (+Azure app + admin consent), Jira.

---

## 13. Kritinės apsaugos ir sprendimai (sutarta peržiūroj)

### 13.1 Stale-delete „sanity guard" 🔴
Jei šaltinis ištrinamas/archyvuojamas ARBA token praranda prieigą → sync grąžina
0/daug mažiau → inkrementinis **ištrintų visą KB**. Apsauga: jei failų kiekis
krenta **>50%** ar į **0** → NEtrint, `status=paused` + alert adminui („patvirtink
masinį trynimą"). Slenkstis konfigūruojamas.

### 13.2 Default-deny KB kūrimo tvarka 🔴
Tvarka: (1) sukurt KB **privačią**, (2) uždėt access_control, (3) **tik tada** sync.
Niekada nebūna lango kai turinys įkeltas, o KB dar vieša.

### 13.3 Audience „drift" 🔴
Prieš kiekvieną access re-push (sk.7) validuot `audience_ids` prieš esamus
OpenWebUI users/groups. Dingę subjektai → pažymėt „stale", praleist, pranešt adminui.

### 13.4 Globali sync eilė / concurrency 🔴 (svarbiausia „nestrigimui")
- **Max N sync vienu metu** (pvz 2), likę laukia eilėj. Be šito 20 darbų ties
  „1h" vienu metu kerta GPU/Atlassian → sistema klūpo.
- **Atskira juosta** „big initial" sync'ams, kad ilgas pradinis neblokuotų
  inkrementinių refresh'ų.
- Dideli pradiniai — auto į **off-hours**.

### 13.5 Zombie darbai po restart'o 🔴
App startuojant: reconcile — `status=processing` be gyvo PID → `error` (ar
pertestuot). Praleistos grafiko iteracijos per downtime → paleist startuojant.

### 13.6 Dideli space'ai (5000+ puslapių) strategija
- **Dry-run visada rodo puslapių skaičių prieš commit**; > slenksčio → įspėjimas.
- Adminui 2 keliai: **susiaurint** (Confluence CQL/label filtras) / **leist
  droseliuotai** (žemas concurrency, off-hours).
- `max-file-size` praleist milžiniškus attachment'us.

### 13.7 Dry-run peržiūra prieš commit
Prieš kuriant darbą — `oikb sync --dry-run` → rodo „+N pridės". Adminas mato
apimtį, nepakabina sistemos netyčia.

### 13.8 Rankinis valdymas
„Sync now" mygtukas (be grafiko) + Pause/Resume (`status=paused`) + Cancel
(kill `pid`) kiekvienam darbui.

### 13.9 Notifikacijos klaidoms
Sync krenta → adminas sužino: in-app indikacija + optional webhook (`NOTIFY_URL`
env). Ne „sužinai po savaitės".

### 13.10 Turinio kokybė — dokumentuot + patikrint
oikb traukia puslapio tekstą; prisegti PDF/Excel/nuotraukos gali nepatekti;
lentelės→txt praranda struktūrą. **Patikrint ką oikb realiai ima**, nustatyt
lūkesčius adminui. (Sprendimas pagal patikros rezultatą.)

### 13.11 Architektūra: kb-admin = vienintelis orkestratorius
- Esamas **`oikb` daemon compose servisas IŠJUNGIAMAS/PAŠALINAMAS** — kitaip du
  planuotojai (oikb daemon + kb-admin scheduler) konfliktuotų.
- oikb naudojamas kaip **CLI subprocess kb-admin image viduje** (dėl `pid`
  kill/cancel). kb-admin valdo VISKĄ.

### 13.12 Atmesta (NEdaroma)
- ~~Anonimizacija ingestijoj~~ — OpenWebUI pipeline susitvarko, papildomai nereikia.
- ~~Compliance „kas ką mato" report~~ — ne dabar (galima vėliau).
- ~~Atskiras Qdrant purge~~ — OpenWebUI per API pats valo (patikrinta).

---

## 14. Patikrinti prieš/kuriant (kad neprasimanyt)

- [ ] OpenWebUI tikslus `access_control` formatas (read/write, group_ids,
      user_ids) — gyvai per API.
- [ ] OpenWebUI groups/users API laukai.
- [ ] oikb iškvietimo būdas iš app (subprocess pid'ui vs daemon `/sync`).
- [ ] **oikb elgesys su HTTP 429** (retry/backoff?) ir ar inkrementinis sync
      tikrai tęsia po nutrūkimo.
- [ ] Ar oikb-sukurtos KB išlaiko access_control po sync (turėtų; jei perrašo —
      todėl deklaratyvus re-push, sk.7).
- [ ] LDAP konkretūs parametrai (bind DN šablonas, atributai email/uid) — kai bus.
- [ ] Confluence **CQL/label filtras** dideliems space'ams susiaurint (oikb palaikymas).
- [ ] Ką oikb realiai ima iš puslapio (attachments? lentelės?) — sk.13.10.
- [x] ~~Ar oikb reset išvalo Qdrant~~ — PATIKRINTA: OpenWebUI per API pats valo.

## 15. Trikčių šalinimas — KB priskirta, bet modelis jos nenaudoja

**Simptomas:** modeliui priskirta žinių bazė, bet jis atsakinėja iš bendrų žinių /
sako „pateiktuose dokumentuose informacijos nėra". Chato atsakymas rodo **jokių
šaltinių**, nors KB akivaizdžiai turi turinio.

### 15.1 Function Calling turi būti **Legacy** (dažniausia priežastis) 🔴

OpenWebUI ieško modelio KB **tik kai modelio Function Calling režimas = `Legacy`**.
`Default`/`Native` režime KB perduodama LLM'ui kaip *įrankis, kurį modelis turi pats
iškviesti* — išoriniai modeliai per proxy (pvz. Gemini per OpenRouter) to įrankio
neiškviečia, todėl retrieval nevyksta ir atsakymas be šaltinių.

OpenWebUI atnaujinimas pakeitė **default** iš tiesioginio (legacy) įterpimo į native
tool-calling, todėl setup'ai, kurie „visada veikė", po update tyliai nustoja ieškoję
— niekas KB'oje ar duomenyse nepasikeitė.

**Sprendimas:** Workspace → Models → *(modelis)* → Advanced Params → **Function
Calling → Legacy** → Save. Padaryk **kiekvienam** modeliui su žinių baze. Patikra:
uždavus klausimą, po atsakymu turi atsirasti **šaltinis/citata**.

> Kadangi native režime retrieval išvis nepasileidžia, tai užmaskuoja visa kita —
> hybrid paieška, reranker, relevance threshold ir KB prieiga atrodo tvarkingi, bet
> šaltinių 0. Visada pirma patikrink Function Calling = Legacy.

### 15.2 Failai KB **subkataloge** neįvektorinami į KB

Katalogų vaizde failas įdėtas į **subkatalogą** įvektorinamas tik į failo kolekciją,
o ne į pačios KB kolekciją, todėl KB-scope retrieval jo nemato (failas medyje matosi
ir prilinkuotas prie KB).

**Sprendimas:** failus dėk į **KB šaknį**, arba re-indeksuok failą į KB kolekciją:
`POST /api/v1/retrieval/process/file` su kūnu
`{"file_id": "<id>", "collection_name": "<kb_id>"}` (admin token). oikb įkelti failai
(SharePoint/Confluence/Jira sync) šios bėdos neturi — jie tvarkingai patenka į KB
kolekciją; tik rankomis į subkatalogą įdėti failai reikalauja šito.
