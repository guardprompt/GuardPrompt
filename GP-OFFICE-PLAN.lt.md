# gp-office — Office failų (Excel / Word / PowerPoint) palaikymo scope

> Būsena: **PLANAS / SCOPE** (2026-09-23). Dar nediegta. Aptarimui ir patvirtinimui.
> Tikslas: universalus sprendimas, dengiantis ABU poreikius — (A) gerą Office failų
> skaitymą į žinių bazę/chatą ir (B) Office failų kūrimą/redagavimą chate — telpantis
> į esamą GuardPrompt architektūrą (anonimizacija, on-prem, be trečių šalių kodo backend'e).

---

## 1. Problema

Kolegos skundžiasi: OpenWebUI (OWUI) **blogai dirba su Excel / Word / PowerPoint** failais.

Dvi skirtingos problemos po vienu skundu:

- **(A) Skaitymas / RAG.** Įkeli Office failą → klausi apie jį → AI gauna nešvarų arba
  nepilną turinį → blogas atsakymas. Failo turinys išgaunamas **įkėlimo metu**
  (`CONTENT_EXTRACTION_ENGINE`, dabar `docling`).
- **(B) Kūrimas / redagavimas.** Nori, kad AI **sukurtų** naują Office failą arba
  **redaguotų** esamą tiesiai chate. Šiandien to nėra.

## 2. Kodėl dabar blogai (A)

Šiuo metu visi Office failai eina per **docling** (`docling-serve`, „auto" kelias =
bazinis `DocumentConverter()`). docling puikus PDF'ams (OCR, layout, lentelės), bet
Office failams silpnas. Realiai patikrinta (2026-09-23), tie patys failai:

| Ką praranda docling | Pasekmė |
|---|---|
| Excel **lapų pavadinimai** (Nuolaidos / Kainos) | AI nežino iš kurio lapo duomenys |
| Excel **formulės / suvestinės celės** (`=AVERAGE`) | dingsta skaičiuota reikšmė |
| PowerPoint **kalbėtojo pastabos (notes)** | dingsta visiškai |
| PowerPoint **skaidrių numeriai** | nėra nuorodos į skaidrę |
| dvigubi bullet'ai („- •") | šiukšlės tekste |

Palyginimui **MarkItDown** (Microsoft, nemokamas, be ML/GPU) tuos pačius failus
išskaito su lapų pavadinimais (`## Nuolaidos`), skaidrių numeriais
(`<!-- Slide number: 1 -->`) ir **pastabomis** (`### Notes:`). Trūkumas — sujungtų
antraščių „Unnamed" artefaktas (išvalomas post-processu).

## 3. Tikslas — universalus vienas Office variklis

Vienas naujas servisas **`gp-office`** (kaip kiti `gp-*` servisai) = VIENAS Office
variklis abiem keliams. Vienas kodas, vienas saugos auditas, be GPU.

```
                    ┌──────────────── gp-office ────────────────┐
                    │  MarkItDown          → tekstas/markdown    │
  A. Įkėlimas ─────▶│  openpyxl/pptx/docx  → struktūra (r/w)     │
  (docling-serve    │  LibreOffice headless→ legacy/fallback     │
   Office maršrutas)│                                            │
                    │  /convert   — ištraukimas į KB (A)         │
  B. Chatas ───────▶│  MCP/OpenAPI tools — read/create/edit (B) │
  (OWUI tools)      └────────────────────────────────────────────┘
```

- **A:** `docling-serve` Office failus persiunčia į `gp-office /convert`
  (MarkItDown + LibreOffice fallback) → švarus markdown → KB. **PDF lieka docling**
  (jo stiprybė).
- **B:** `gp-office` išstato **įrankius** (MCP arba OpenAPI) OWUI'ui: skaityk lapą/celę,
  sukurk lentelę/dokumentą/skaidres, (vėliau) redaguok.
- Abu keliai eina per **tą pačią anonimizacijos ribą**.

## 4. Anonimizacija — svarbiausias ribojimas

Mūsų sistema **paslepia asmens duomenis prieš siųsdama į išorinį AI** (`Jonas
Petraitis` → `GP_ab12cd34`), o atsakyme **atverčia atgal**.

| Veiksmas | Ar veikia | Kodėl |
|---|---|---|
| **Skaityti** failą (A + B-read) | ✅ lengva | AI dirba su paslėpta versija, atsakymas atverčiamas |
| **Kurti naują** failą (B-create) | ✅ lengva | nėra esamų asmens duomenų |
| **Redaguoti esamą su PII** (B-edit) | ⚠️ sudėtinga | AI grąžina failą su `GP_` kodais → kiekvieną reikia TIKSLIAI atverst; redaguodamas AI gali perkelt/pamest kodą → sugadintas failas |

**Sprendimas B-edit:** eiti per **atverčiamų kodų kelią** (`gp-openai-proxy` /
`gp-claude-proxy` — tą, kur šioje sesijoje pridėtas `tool_call` argumentų atvertimas),
NE per įprastą OWUI vienkryptį slėpimą (kuris paslepia negrįžtamai — tinka tik
KB/skaitymui). Todėl B-edit = atskira, vėlesnė fazė su kruopščiu testu.

## 5. Scope pagal fazes

### Fazė 0 — Pamatas (A: geras skaitymas)
- [ ] Naujas servisas `gp-office` (FastAPI, be GPU), `POST /convert` (failas → markdown)
- [ ] Variklis: MarkItDown (docx/xlsx/pptx), post-process „Unnamed"/dvigubų bullet'ų valymas
- [ ] `docling-serve` Office maršrutą (`use_docling_auto` šaka) nukreipti į `gp-office/convert`; PDF/paveikslėliai lieka docling
- [ ] Fallback: jei `gp-office` neatsako/klysta → docling (kad neliktų be ištraukimo)
- [ ] `docker-compose.yml` + `.env`/`.env.example` (env checklist), publish.ps1 (obfuskacija pagal poreikį)
- [ ] Testai: Excel (keli lapai/formulės), PPTX (notes), DOCX (lentelės/paveikslėliai) — palyginti su docling baseline

### Fazė 1 — LibreOffice fallback (A: legacy + fidelity)
- [ ] LibreOffice headless `gp-office` viduje (arba atskiras sidecar) senams formatams `.doc/.xls/.ppt` ir egzotiškiems
- [ ] Maršrutas: MarkItDown pirma → jei nepavyksta/legacy → LibreOffice konversija → markdown
- [ ] Resursų ribos (procesas per konversiją, concurrency limitas), be GPU

### Fazė 2 — Įrankiai chate: skaityti + kurti (B-read, B-create)
- [ ] `gp-office` išstato įrankius per **OpenAPI** (arba MCP + `mcpo`) — OWUI native tool
- [ ] Įrankiai: `office_read` (lapas/celė/skaidrė/pastraipa on-demand — tikslesnis nei RAG chunk'ai), `office_create` (markdown/JSON → .xlsx/.docx/.pptx)
- [ ] Failas grąžinamas per OWUI storage (kaip generator įrankiai)
- [ ] Anonimizacija: įrankio išvestis eina per gp-pipeline (`role==tool` jau maskuojamas) — patvirtinti, kad neteka
- [ ] Function-calling suderinamumas su KB (mūsų KB reikalauja *Legacy* function calling — patikrinti, kad tools nekerta RAG)
- [ ] White-label + licencija (kaip kiti servisai)

### Fazė 3 — Redaguoti esamus failus (B-edit) — atskira, atsargi
- [ ] Nukreipti per **atverčiamų kodų** kelią (gp-openai-proxy stilius), NE vienkryptį
- [ ] `office_edit` (celė/eilutė/tekstas/skaidrė) su openpyxl/python-docx/pptx
- [ ] Griežtas atvertimo testas: `GP_` kodai per redagavimą NELEIDŽIAMI likti faile (0 leak į diską)
- [ ] Fail-closed: jei atvertimas nepilnas → operacija atmetama, ne sugadintas failas

### Fazė 4 — Poliravimas
- [ ] Milžiniškų Excel chunking strategija (tūkstančiai eilučių → protingas skaidymas, ne viena lentelė)
- [ ] PPTX paveikslėlių aprašymai (VLM) — jei skaidrė = tik paveikslėlis (perpanaudoti esamą docling+LM Studio describe kelią)
- [ ] Metrikos (`/metrics`), warmup integracija, monitoringas (Zabbix)

## 6. Sauga
- Savas kodas (be trečių šalių Tool backend'e) — atitinka mūsų principą; jei imamas MCP/lib iš išorės → **auditas prieš diegimą**
- `gp-office` be docker.sock, be viešo porto (tik vidinis, kaip kiti data-store servisai → 127.0.0.1)
- Failų dydžio/tipo ribos, SSRF apsauga (jokių URL fetch iš turinio)
- Anonimizacija privaloma abiem keliams; B-edit fail-closed
- Licencijos gate (kaip kiti servisai)

## 7. Testai (priėmimo kriterijai)
- **A:** Excel su keliais lapais + formulėmis, PPTX su notes, DOCX su lentelėm/paveikslėliais → visi lapai/pastabos/lentelės išgautos; palyginti su docling baseline (turi būti geriau)
- **A leak:** įkeltas Office su PII (vardas+kodas+telefonas) → KB turinys užmaskuotas (0 leak)
- **B-read/create:** įrankis grąžina teisingą turinį/failą; PII užmaskuota LLM pusėje
- **B-edit:** redaguotas failas diske — 0 `GP_` kodų; atvertimas tikslus; fail-closed veikia
- Regresija: PDF ištraukimas (docling) nepaliestas

## 8. Diegimas
- Naujas servisas → `docker compose up -d --build gp-office docling-serve` (+ OWUI tools registracija B fazei)
- Shared host VW-DI-VSSA: **NE** `-v` / `--remove-orphans` / `prune`
- Env checklist: `.env`, `.env.example`, compose, kodas, publish.ps1
- Staged: A (KB/skaitymas) → B-read/create → B-edit

## 9. Ne scope (kol kas)
- Tiesioginis SharePoint/M365 Office redagavimas (atskiras Office Add-in planas)
- Realaus laiko bendra redagavimo sesija
- Formulių perskaičiavimas (skaičiuoklės variklis) — išgaunam reikšmes, neskaičiuojam

## 10. Atviri klausimai
1. Redaguoti reikia **esamus su PII** (Fazė 3), ar dažniau **skaityti + kurti naujus** (Fazė 2)? — nuo to priklauso prioritetas
2. Legacy formatai (`.doc/.xls/.ppt`) — reikia? (lemia LibreOffice Fazę 1)
3. `gp-office` įrankiai per **OpenAPI** ar **MCP** (OWUI palaiko abu; OpenAPI paprasčiau mūsų setup'e)
4. PPTX paveikslėlių aprašymai (VLM) — reikia, ar tekstas užtenka?

---

*Susiję: [[project-office-addin]] (M365/SharePoint kelias), docling picture fix (šios
sesijos), anonimizacijos atverčiami kodai (gp-openai-proxy `tool_call` restore).*
