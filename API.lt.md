> 🌐 **Kalba / Language:** **Lietuvių** · [English](API.md)

# GuardPrompt — anonimizavimo API

Siunčiate tekstą, gaunate tą patį tekstą su asmens ir jautriais duomenimis,
pakeistais žymekliais (`[PERSON]`, `[HEALTH]`, `[IBAN]`, …). Viskas vyksta jūsų
pačių įrangoje: tekstas iš mašinos neiškeliauja.

Naudokite tai savo programų duomenims anonimizuoti — prieš archyvuojant, prieš
siunčiant į išorinę paslaugą ar prieš bet kokį kitą apdorojimą.

- **Kas ir kodėl uždengiama:** [COMPLIANCE.lt.md](COMPLIANCE.lt.md) (BDAR 9/10 str., ES DI aktas)
- **Kaip tai dera platformoje:** [ARCHITECTURE.lt.md](ARCHITECTURE.lt.md)

---

## Du API, du darbai

GuardPrompt turi du nepriklausomus programinius įėjimus. Rinkitės pagal poreikį:

| | **Anonimizavimo API** (šis dokumentas, žemiau) | **Anonimizuojantis chat API** ([↓ per OpenWebUI](#chat-api-per-openwebui-openai-suderinamas)) |
|---|---|---|
| Paskirtis | Uždengti tekstą / dokumentus | Kviesti LLM (OpenRouter) prieš tai pašalinus asmens duomenis |
| Endpoint | `http://…:8005/api/v1/anonymize` | `http://…/api/chat/completions` (OpenAI-suderinamas) |
| Autentikacija | `ANON_API_KEYS` | OpenWebUI API raktas |
| Grąžina | Uždengtą tekstą | LLM atsakymą — įvestis uždengta prieš modeliui ją matant |
| Grįžtama? | Ne — vienkryptė | Ne — vienkryptė. Reikia tikrų reikšmių atgal atsakyme? Naudokite grįžtamą Claude šliuzą: [GP-CLAUDE-PROXY.lt.md](GP-CLAUDE-PROXY.lt.md) |

Likusi dalis aprašo **Anonimizavimo API**; chat API — dokumento
[gale](#chat-api-per-openwebui-openai-suderinamas).

---

## Bazinis adresas

| Iš kur kviečiate | URL |
|---|---|
| Iš kito stack'o konteinerio | `http://anonymizer:8005` |
| Iš Docker host'o | `http://localhost:8005` |

> ⚠️ 8005 portas atidarytas **visoms sąsajoms** (`0.0.0.0`). Kas pasiekia host'ą,
> pasiekia ir šį API, todėl **nustatykite API raktą** (žr. žemiau). Jei išorinė
> prieiga nereikalinga, apribokite portą `docker-compose.yml`
> (`"127.0.0.1:8005:8005"`) arba ugniasiene.

## Autentikacija

Raktą iš `ANON_API_KEYS` (`.env`) siųskite kaip Bearer token'ą:

```
Authorization: Bearer <raktas>
```

Veikia ir `X-API-Key: <raktas>`. `install.ps1` / `install.sh` raktą sugeneruoja
automatiškai ir parodo vieną kartą diegimo pabaigoje.

Jei `ANON_API_KEYS` **tuščias — API rakto nereikalauja** ir yra atviras bet kam,
kas pasiekia portą. `ANON_API_KEYS` gali turėti kelis kablelriais atskirtus
raktus, tad kiekvienas klientas gali gauti savo ir būti atšauktas netrukdant
kitiems.

| Atsakymas | Reikšmė |
|---|---|
| `401` | Rakto nėra arba jis neteisingas |
| `400` | Netaisyklinga užklausa (blogas JSON, tuščias tekstas) |
| `200` | Sėkmė |

---

## `POST /api/v1/anonymize`

Pagrindinis endpoint'as. JSON į vidų, JSON į išorę.

**Užklausa**

```json
{
  "text": "Jonas Vaitkevičius serga vėžio liga. Tel. +37060012345.",
  "do_anonymize": true
}
```

| Laukas | Tipas | Privalomas | Aprašymas |
|---|---|---|---|
| `text` | string | taip | Tekstas, kurį anonimizuoti |
| `do_anonymize` | bool | ne (numatyta `true`) | `false` grąžina pranešimą apie praleidimą, o ne tekstą — žalio įvesties niekada negrąžina |

**Atsakymas**

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

> **Lietuviškas tekstas ir JSON koduotė.** Siųskite UTF-8 ir leiskite savo HTTP
> bibliotekai sudaryti JSON (`json=` su `requests`, `JSON.stringify` su JS).
> Tvarkomos abi formos — ir `"vėžio"`, ir `ė` pavidalo — servisas JSON
> iššifruoja prieš anonimizuodamas. **Nedarykite** JSON eilutės ranka ir
> nesiųskite jos kaip `text/plain`: tas kelias visą apvalkalą traktuoja kaip prozą.

### Kiti priimami formatai

Tas pats endpoint'as priima ir gryną tekstą, ir failo įkėlimą. Patogu shell
skriptams; naujoms integracijoms naudokite JSON.

```bash
# zalias body
curl -X POST http://localhost:8005/api/v1/anonymize \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -H "Content-Type: text/plain" \
  --data-binary "Jonas Vaitkevičius serga vėžio liga."

# failo ikelimas (grazina JSON su "anon_text" lauku)
curl -X POST http://localhost:8005/api/v1/anonymize \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -F "file=@notes.txt"
```

### `POST /api/anonimize` (alias)

Pirminis kelias, paliktas suderinamumui — atkreipkite dėmesį į lietuvišką rašybą
(`anonimize`). Elgsena identiška. Naujame kode naudokite `/api/v1/anonymize`;
`/api/anonimize` nebus pašalintas.

---

## `PUT /process` — dokumentai

Ištraukia ir anonimizuoja dokumentą (PDF, DOCX, XLSX, PPTX, nuotraukas, …). Šį
endpoint'ą OpenWebUI naudoja kaip *external document loader*; galite kviesti ir
tiesiogiai. Ne tekstiniai formatai pirma keliauja per Docling ekstrakcijai.

Siųskite žalius failo baitus kaip body, failo vardą — antraštėje:

```bash
curl -X PUT http://localhost:8005/process \
  -H "Authorization: Bearer $ANON_API_KEY" \
  -H "X-Filename: ataskaita.pdf" \
  -H "Content-Type: application/pdf" \
  --data-binary @ataskaita.pdf
```

**Atsakymas** — puslapių/blokų sąrašas:

```json
[
  {
    "page_content": "[PERSON] serga [HEALTH].",
    "metadata": {
      "filename": "ataskaita.pdf",
      "mime_type": "application/pdf",
      "processed_by": "guardprompt-docling"
    }
  }
]
```

---

## Pagalbiniai endpoint'ai

Šiems raktas **nereikalingas** — registracija turi veikti dar neturint rakto.

| Endpoint | Paskirtis |
|---|---|
| `GET /` | Sveikatos patikra → `{"status":"ok"}` |
| `GET /api/reginfo` | Host ID + IP licencijos registracijai ([LICENSING_INFO.lt.md](LICENSING_INFO.lt.md)) |
| `GET /metrics` | Prometheus metrikos — anon užklausos/statusas, maskavimo trukmė, `fail_closed{license,gliner}`, aptikta injekcija. Skaito Zabbix stebėsenos plokštuma ([MONITORING.lt.md](MONITORING.lt.md)) |

`POST /api/webcrawle` (svetainės nuskaitymas į žinių bazę) rakto **reikalauja**.

> **Matomumas.** `gliner` (`:8500/metrics`) ir Claude proxy
> (`gp-claude-proxy:8006/metrics`) atskleidžia tą patį Prometheus formatą,
> suteikdami vienodus latencijos, pralaidumo, `model_on_gpu` ir fail-closed
> signalus visame anonimizacijos kelyje — žr. [MONITORING.lt.md](MONITORING.lt.md).

---

## Elgsena, kuriai reikia pasiruošti

API yra **fail-closed**: kai negali garantuoti anonimizavimo, jis atsisako
grąžinti tekstą, o ne grąžina tekstą, kuris gali nutekėti. Šiuos traktuokite kaip
klaidas, ne kaip turinį — jie ateina su HTTP `200`:

| Grąžinamas tekstas | Priežastis |
|---|---|
| `[PROCESSING DISABLED: LICENSE IS NOT VALID]` | Licencijos nėra arba pasibaigusi — žr. [LICENSING_INFO.lt.md](LICENSING_INFO.lt.md) |
| `[PROCESSING DISABLED: ANONYMIZATION SERVICE UNAVAILABLE]` | Nukritęs `gliner` NER servisas, tad BDAR 9/10 str. kategorijų aptikti neįmanoma. `ANON_REQUIRE_GLINER=false` `.env`'e leidžia dirbti sumažintu režimu |

**Laukimo laikai.** Trumpas tekstas greitas, didelis dokumentas — ne: `gliner`
NER **GPU spartinamas su dinaminiu batching** (~70 užkl./s), bet Docling
ekstrakcija sunki. Skirkite bent 30 s `/api/v1/anonymize` ir gerokai daugiau
`/process`.

**Startas.** Servisas licenciją patikrina asinchroniškai, kelias sekundes po
paleidimo. Kvietimas tame lange gaus `LICENSE IS NOT VALID` net su galiojančia
licencija — apklauskite `GET /` ir pakartokite, o ne laikykite pirmo atsakymo
galutiniu.

**Diakritikai svarbu.** Aptikimas suderintas tikram lietuviškam tekstui. `vėžio`
atpažįstamas kaip sveikatos duomuo; `vezio` — gali ir ne. Nenuimkite diakritikų
prieš siųsdami.

**Idempotentiškas.** Pakartotinai anonimizuoti jau uždengtą tekstą saugu —
žymekliai apsaugoti ir iš naujo nežymimi.

## Konfigūracija

Ką uždengti, valdo `ANON_*` vėliavos `.env` faile (žr. `.env.example` — ten
aprašyta kiekviena). Terminai, kurie turi likti matomi, keliauja į
`ANON_ALLOW_WORDS` / `ANON_ALLOW_DOMAINS`; leidimų sąrašas turi aukščiausią
prioritetą.

---

## Chat API per OpenWebUI (OpenAI-suderinamas)

Antrasis įėjimas. Programuotojams ir įrankiams, norintiems **kviesti LLM su
automatiškai pritaikoma anonimizacija**: užklausa eina per OpenWebUI, GuardPrompt
filtras ją uždengia, ir tik tada pasiekia OpenRouter. Tikri asmens duomenys
išeinančioje LLM užklausoje iš mašinos neiškeliauja.

Tai *tas pats* anonimizatorius, kurį naudoja chat UI — globalus `pipelines: ["*"]`
filtras — atvertas per OpenWebUI standartinį OpenAI-suderinamą API, tad bet kuris
OpenAI SDK veikia be pakeitimų. Atskiro serviso leisti nereikia.

- **Bazinis adresas:** tas pats host'as/domenas kaip OpenWebUI web programos, plius
  `/api` (pvz. `https://chat.example.com/api`).
- **Autentikacija:** **OpenWebUI API raktas** — *ne* `ANON_API_KEYS`. Kiekvienas
  vartotojas susikuria jį *Settings → Account → API Keys*; duokite kiekvienam
  programuotojui savo, kad prieigą būtų galima atšaukti individualiai.
- **Modeliai:** bet kuris OpenWebUI teikiamas modelis — sąrašas per
  `GET /api/models`, naudokite OpenRouter id (pvz. `openai/gpt-5.6-luna`).

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://chat.example.com/api",   # OpenWebUI — NE openrouter.ai
    api_key="<jūsų OpenWebUI API raktas>",
)
resp = client.chat.completions.create(
    model="openai/gpt-5.6-luna",               # bet kuris OpenRouter modelis
    messages=[{"role": "user",
               "content": "Jonas Petraitis, a.k. 38901011234 — parenk atsakymą."}],
)
print(resp.choices[0].message.content)
```

OpenRouter gauna `[PERSON], [ID] — parenk atsakymą.` — vardas ir asmens kodas
uždengiami **prieš** užklausai išeinant iš mašinos.

### curl

```bash
curl -X POST https://chat.example.com/api/chat/completions \
  -H "Authorization: Bearer <OpenWebUI API raktas>" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-5.6-luna","messages":[{"role":"user","content":"..."}]}'
```

### Vienkryptė, negrįžtama

Šis kelias **uždengia** (kaip teksto API aukščiau): LLM mato tik `[PERSON]`, tad
ir jo atsakymas kalba apie `[PERSON]` — tikros reikšmės neatstatomos. Jei klientui
reikia tikrų duomenų atgal atsakyme (grįžtama pseudonimizacija), naudokite
Anthropic/Claude šliuzą — [GP-CLAUDE-PROXY.lt.md](GP-CLAUDE-PROXY.lt.md).

> **Fail-closed**, kaip ir visa platforma: jei anonimizatorius nepasiekiamas,
> žinutė blokuojama, o ne siunčiama neuždengta (konfigūruojama filtre).

> Atsakymuose gali likti nematomų zero-width žymeklio simbolių, kuriuos prideda
> pipeline (`​‌⁣`). Jie nekenksmingi — ne nutekėjimas — bet pašalinkite, jei
> tolimesnė sistema jiems jautri.
