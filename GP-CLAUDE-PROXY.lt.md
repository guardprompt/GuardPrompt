> 🌐 **Kalba / Language:** **Lietuvių** · [English](GP-CLAUDE-PROXY.md)

# GuardPrompt Claude šliuzas — diegimas

Nukreipia jūsų Claude Code klientus — CLI, VS Code ir JetBrains — per GuardPrompt,
kad niekas nepasiektų Anthropic neapdorota (**darbalaukio aplikaciją** taip pat, bet
tik API-rakto režime, ne su claude.ai prenumerata — žr. §3). Jautrios reikšmės
pakeliui pirmyn keičiamos grįžtamomis žymėmis, o atgal — atstatomos: programuotojas
mato tikrą kodą, Anthropic — niekada. Žemėlapis neišeina iš jūsų infrastruktūros.

```
Claude Code CLI ─┐
VS Code ext ─────┤
JetBrains IDE ───┼─→ gp-claude-proxy ──→ api.anthropic.com
Desktop app * ───┘    (jūsų mašina)       (mato GP_a3298922c55a)
                            │
                    ┌───────┴───────┐
              Postgres saugykla   Postgres auditas
            (GP_… → tikra reikšmė) (kas ką siuntė, užmaskuota)

 * prenumeratos pass-through (A režimas) veikia CLI / VS Code / JetBrains;
   darbalaukio aplikacija per šliuzą eina tik API-rakto režime (B) — §3.
```

Tai **atskiras servisas** nuo `anonymizer` konteinerio. Tas aptarnauja OpenWebUI
vienkrypčiu tekstų maskavimu ir čia neliečiamas; šis tik importuoja jo taisyklių
modulius tik skaitymui.

Kodėl organizacijos tai naudoja: programuotojai toliau dirba su geriausiu rinkoje
kodavimo modeliu, o nei vienas kliento vardas, kredencialas, asmens kodas ar
jautraus kodo eilutė neišeina iš pastato atviru tekstu. GDPR, NIS2 ir vidaus
duomenų tvarkymo politika nustoja būti priežastis uždrausti AI įrankius.

---

## 1. Du kredencialų režimai — pasirink prieš diegimą

Šliuzas autentifikuojasi Anthropic vienu iš dviejų būdų. **Tai vienas globalus
jungiklis visam instance'ui, nulemtas ar užpildytas `GP_UPSTREAM_API_KEY` — NE
per vartotoją.** Maišyti viename instance negalima; jei reikia abiejų — paleisk
du instance ant dviejų portų.

| | **A režimas — Prenumeratos pass-through** | **B režimas — Bendras API raktas** |
|---|---|---|
| `GP_UPSTREAM_API_KEY` | tuščias (numatyta) | tikras `sk-ant-…` |
| Kas moka | kiekvieno programuotojo claude.ai prenumerata (Pro / Max / Team) | viena centrinė Anthropic **API** sąskaita, per-token |
| Reikia claude.ai login | **taip** | **ne** |
| Prieigos kontrolė prie šliuzo | tik tinklo lygis (`GP_PROXY_KEYS` ignoruojamas) | `GP_PROXY_KEYS` gate žymės, po vieną žmogui |
| Desktop app palaikymas | **ne** (žr. §3) | taip |
| Kam tinka | komanda jau turinti Pro/Team vietas | žmonės be licencijos, arba centralizuotas billing/apskaita |

Anthropic **API raktas** B režime (iš
[console.anthropic.com](https://console.anthropic.com)) yra *kitas produktas*
nei Pro/Team chat prenumerata — mokama per token, ne fiksuota mėnesinė vieta.
Tai dažniausia painiavos vieta; laikyk atskirai.

**Tinklo pasiekiamumas.** Šliuzas pagal nutylėjimą klausosi `127.0.0.1:8006`, tad
tik host'as pasiekia. Komandai — publikuok per VPN arba už reverse proxy su TLS
ir duok programuotojams tą URL. Neatverk į internetą: kas pasiekia, tas gali
savo turinį ne tik užmaskuoti, bet ir **atstatyti** — saugykla už šio porto.

---

## 2. Serverio konfigūracija

Sugeneruok žymių raktą vieną kartą ir įrašyk į `.env`. **Vėliau jį pakeitus
apmiršta visi esami žemėlapiai** — jau vykstančiame pokalbyje žymės nustoja
atsiverti — tad laikyk jį nuolatiniu. `install.ps1` / `install.sh` jį sugeneruoja
už tave; rankomis:

```powershell
$b = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
"GP_TOKEN_SECRET=" + (($b | ForEach-Object { $_.ToString("x2") }) -join "")
```

```bash
# .env
GP_TOKEN_SECRET=<sugeneruota reikšmė>   # HMAC sėkla; laikyk stabilų amžinai

# Klientų vardai, vidiniai domenai, projektų kodiniai pavadinimai — reikšmės,
# kurias tik tu žinai esant jautrias. gliner jų neras; niekas kitas šio sąrašo.
GP_CUSTOM_WORDS=YourCustomer,internal.example.com,ProjectFalcon

# --- REŽIMO SELEKTORIUS ---
# Tuščias -> A režimas (pass-through): programuotojai naudoja savo claude.ai.
# sk-ant  -> B režimas (bendras raktas): šliuzas moka už visus.
GP_UPSTREAM_API_KEY=

# Gate žymės — TIK B REŽIMAS (A režime ignoruojama). Po vieną programuotojui, kad
# atleidžiant panaikintum vieną raktą; taip pat identifikuoja siuntėją saugyklos
# scope'ui ir auditui. Generuok stiprias atsitiktines:
#   gpk_$(openssl rand -hex 20)
GP_PROXY_KEYS=
```

Paleisk:

```bash
docker compose up -d gp-claude-proxy
docker compose logs gp-claude-proxy | Select-String "gp-proxy"
```

Sveikas startas spausdina taisyklių skaičių, `gliner=ON`, `fail_closed=True` ir
išspręstą režimą:

```
[gp-proxy] credential mode=SUBSCRIPTION PASS-THROUGH (client's own claude.ai login is relayed)
[gp-proxy] proxy auth=n/a (pass-through) — restrict access at the network layer
```

arba B režime:

```
[gp-proxy] credential mode=API KEY (proxy-held, replaces client credential)
[gp-proxy] proxy auth=ON (3 keys)
```

---

## 3. Nukreipk kiekvieną aplikaciją

Pakeisk `https://gp-proxy.internal.example.com` savo URL.

### Claude Code CLI

`~/.claude/settings.json` (`%USERPROFILE%\.claude\settings.json` Windows'e):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gp-proxy.internal.example.com",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0"
  }
}
```

**A režime** NEnustatyk `ANTHROPIC_AUTH_TOKEN` ar `ANTHROPIC_API_KEY`: bet kuris
pakeičia claude.ai prenumeratą tuo kredencialu, prenumerata nustoja būti naudota,
o jos licencija švaistoma. **B režime** nustatyk `ANTHROPIC_API_KEY` (arba
`ANTHROPIC_AUTH_TOKEN`) į programuotojo **gate žymę** (`gpk_…`), *ne* į kokį
Anthropic raktą — tikras Anthropic raktas gyvena tik šliuzo konteineryje.

### VS Code plėtinys ("CLAUDE CODE" skiltis)

VS Code nuosavi user settings (**Preferences: Open User Settings (JSON)**), ne
`~/.claude/settings.json` — plėtinys tikrina kredencialus iš šio nustatymo prieš
paleidimą, o reikšmės Claude settings faile pasiekia paleistą procesą, bet ne
paties plėtinio login patikrą:

```json
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "https://gp-proxy.internal.example.com" },
    { "name": "CLAUDE_CODE_ATTRIBUTION_HEADER", "value": "0" }
  ]
}
```

> **Nepainiok su VS Code "CHAT" skiltimi** — tai **GitHub Copilot**, *atskira* AI
> aplikacija, siunčianti į GitHub/Microsoft ir niekada neliečianti šio šliuzo.
> Nepriklausomas, neužmaskuotas duomenų kelias. Išjunk jį vartotojams, kurie
> privalo likti ant šliuzo: `"chat.disableAIFeatures": true` VS Code settings
> (arba pašalink Copilot visame parke).

### JetBrains IDE (IntelliJ IDEA, PyCharm, …) — „Claude Code [Beta]" plugin

JetBrains plugin po gaubtu tiesiog paleidžia **Claude Code CLI** — jo **Settings →
Tools → Claude Code** skydelis turi tik *CLI Path* / *Node Path*, **base URL lauko
NĖRA** — o tas CLI skaito `~/.claude/settings.json`. Tad proxy jį traktuoja kaip CLI
ir **proxy pusėje keisti nieko nereikia**. *Patikrinta su IntelliJ IDEA 2026.2.*

Įrašyk tą patį `env` bloką kaip CLI (aukščiau) į `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gp-proxy.internal.example.com",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0"
  }
}
```

Tada **perkrauk IDE** (base URL nuskaitomas vieną kartą, agento starte — keitimas
sesijos viduryje neveikia). JetBrains plugin **nepalaiko** `/status` slash komandos
(`"/status isn't available in this environment"`), tad tikrink per **self-test
puslapį** žemiau (§3a). Autentifikacija identiška CLI — **A režime** palik `ANTHROPIC_AUTH_TOKEN` /
`ANTHROPIC_API_KEY` nenustatytus (claude.ai prenumerata); **B režime** developer'io
`gpk_…` tokeną.

> **Šis pakeitimas globalus** — `~/.claude/settings.json` valdo ir terminalo
> `claude` CLI. Kad **tik** IDE eitų per proxy, palik tą failą ramybėje ir plugin'o
> *CLI Path* nurodyk mažą wrapper skriptą, kuris eksportuoja `ANTHROPIC_BASE_URL`
> (ir `CLAUDE_CODE_ATTRIBUTION_HEADER=0`), tada kviečia tikrą `claude`.

> **Jei versija ignoruoja `~/.claude`** (JetBrains YouTrack **LLM-26098**: kai kurie
> naujesni `com.intellij.ml.llm` ACP agentai nenuskaito `ANTHROPIC_BASE_URL` iš
> aplinkos), įrašyk tą patį `env` objektą į
> `%APPDATA%\JetBrains\acp-agents\installed.json` (Linux/macOS
> `~/.config/JetBrains/acp-agents/installed.json`) po `acp.registry.claude-acp`,
> tada perkrauk. Tas katalogas atsiranda tik po to, kai plugin'as bent kartą
> paleidžia savo agentą.

### Desktop app — tik B režimas

**Desktop app negali daryti prenumeratos pass-through.** Jo šliuzo konfigūracija
(**Help → Troubleshooting → Enable Developer Mode**, tada **Developer → Configure
Third-Party Inference**) *reikalauja* "Credential kind", o galimi tik **Static
API key**, **Interactive sign-in (išorinis OIDC IdP)** arba **Helper script** —
nei vienas nėra claude.ai prenumerata. Tad desktop app per šį šliuzą veikia tik
**B režime** (duok jam `gpk_…` gate žymę kaip static API key), arba su tavo
valdomu OIDC/helper kredencialu.

Administratoriaus išdalinta konfigūracija turi pirmenybę ir padaro tą formą tik
skaitomą — taip diegiama parkui. Su sukonfigūruotu šliuzu desktop app sesijas
leidžia **tik lokaliai** — aplinkos parinkiklis nesiūlo SSH ar Anthropic cloud
aplinkų, o Remote Control neprieinamas.

Jei komanda ant Pro/Team vietų (A režimas), nukreipk jautrų darbą per CLI arba VS
Code "CLAUDE CODE" skiltį, o desktop app palik nuošalyje.

### 3a. Kaip pačiam patikrinti, kad veikia (bet kuris klientas — įrodo, kad TAVO srautas anonimizuojamas)

Developeris gali įsitikinti, kad būtent JO IDE srautas realiai eina per proxy — ne
tik kad proxy egzistuoja — tiesiai Claude pokalbyje, be jokio URL ir be serverio
prieigos. Parašyk žinutę, kuri **prasideda `GP-SELFTEST:`** ir po jos bet ką, ką
nori patikrinti:

```
GP-SELFTEST: Klientas Jonas Petraitis, a.k. 39001011234, tel. +37061234567
```

Proxy ją perima, užmaskuoja tekstą ir atsako **būtent tuo, ką būtų gavęs Anthropic**
— visai nekviesdamas Claude:

```
🛡️ GuardPrompt patikra — štai KĄ GAVO Claude (anonimizuota):
Klientas GP_53ef4c1638aa, a.k. GP_03ef34205f00, tel. GP_d8317e2c016f
Užmaskuota reikšmių: 3. …tavo srautas EINA per GuardPrompt proxy…
```

**Kodėl tai tikra patikra:** toks atsakymas gali atsirasti TIK jei žinutė realiai
pasiekė šį proxy. Jei base URL blogas (ne tas host/portas), `GP-SELFTEST:` žinutė
nueis kitur ir gausi ryšio klaidą arba įprastą Claude atsakymą — niekada šio. Tad
jei jį matai — tavo srautas **eina** per GuardPrompt ir anonimizuojamas. Veikia bet
kuriame kliente (CLI, VS Code, JetBrains) — tai rekomenduojama patikra **JetBrains
plugin'ui**, kuris neturi `/status` komandos.

*(Administratoriai papildomai gali patvirtinti realų srautą serverio pusėje:
`docker logs gp-claude-proxy` rodo `POST /v1/messages -> 200 mask=…ms` ir eilutę
`GP-SELFTEST owner=… masked_spans=N`, o `gp_vault` prisipildo `GP_` token→reikšmė
eilučių.)*

---

## 4. Du protokolo niuansai, kuriuos šliuzas privalo padaryti teisingai

Šiuos šliuzas jau tvarko; jie reikalingi tik suprasti gedimams ir išlaikyti
nepaliestus, jei šakoji kodą.

### 4a. Claude Code system-prompt tapatybė turi likti nepaliesta

Prenumeratos OAuth (A režimas) tikrina, kad kiekviena užklausa neštų tikrą Claude
Code tapatybės eilutę system prompt'e:

> `You are Claude Code, Anthropic's official CLI for Claude.`

Ankstesnė šliuzo versija maskavo *viską*, įskaitant tą eilutę (tokenizavo
"Claude"/"Anthropic"). Anthropic tada atmetė užklausą — **kaip `429
rate_limit_error`, ne 401** — kas atrodo lygiai kaip kvotos limitas ir siunčia
gaudyti ne tos problemos valandų valandas. Pataisa jau `bodywalk.py`: **niekada
nemaskuok system bloko, kuriame yra tapatybės eilutė.** Viskas *po* jos (user
tekstas, tool rezultatai, tool-use įvestys) toliau maskuojama normaliai. Jei
perrašinėji `bodywalk.py`, laikyk tapatybės bloką byte-identišką.

### 4b. `/api/hello` turi persiųsti, ne 404

Claude Code zonduoja tik-pirmos-šalies endpoint'ą (`HEAD /api/hello`) nuspręsti,
ar base URL yra tikras Anthropic API. Jei šliuzas jį 404'ina, klientas nusprendžia
kalbantis su trečios šalies šliuzu ir nustoja teisingai siųsti prenumeratos OAuth
→ kiekvienas `/v1/messages` tada grąžina **401 "Invalid bearer token"** net su
galiojančiu login. Tad šliuzas turi **catch-all maršrutą**, skaidriai
persiunčiantį bet kurį neatpažintą kelią upstream (aprašytą paskutinį, kad
eksplicitiniai maskavimo maršrutai laimėtų). `api.anthropic.com/api/hello`
grąžina `{"message":"hello"}`.

### 4c. Kodėl `CLAUDE_CODE_ATTRIBUTION_HEADER=0`

Claude Code prideda attribution bloką kaip pirmą `system` įrašą.
`api.anthropic.com` jį nuima prieš apdorojimą — **bet tik jei atkeliauja
byte-identiškas ir pirmas**. Nuėmimas pozicinis, o bet kuris šliuzas, kuris
perrašo system tekstą, jį sugriauna, įdedant bloką į prompt-cache raktą. Pačios
Anthropic dokumentacijos nurodo praleisti jį kliente būtent šiam atvejui — ką ir
daro šis nustatymas.

---

## 5. Auditas — kas ką siuntė (nebūtinas, GDPR 30 str.)

Šliuzas gali išsaugoti po vieną eilutę užklausai į `gp_audit` lentelę: **tik
naują turną**, **jau užmaskuotą** (GP_ žymės, niekada atviras turinys), plius
**kas jį siuntė** ir kada. Tai įrašas, kurio prašo auditorius — įrodymas ką ir
kas išsiuntė iš pastato — pačiam netampant antra jautrių duomenų kopija.

```bash
# .env
GP_AUDIT_ENABLED=true          # ĮJUNGTA pagal nutylėjimą (GDPR 30 str.); išjungti = false
GP_AUDIT_TTL_DAYS=180          # eilutės prunint'inamos po tiek (numatyta 180)
```

**Tapatybė ("kas siuntė")** išsprendžiama geriausiu-turimu:

1. `X-GP-User` užklausos header — nustatomas per-machine per managed config
   (`ANTHROPIC_CUSTOM_HEADERS`). **Įpurkšk jį savo reverse proxy'je**, o ne
   pasitikėk klientu, kad programuotojas negalėtų suklastoti kito tapatybės.
2. `metadata.user_id` iš užklausos kūno (atsarginis).
3. Kredencialo-hash `owner` visada saugomas šalia bet kuriuo atveju.

Auditas niekada nenuverčia užklausos: rašymo klaida logginama, ne keliama.
Saugomas turinys — užmaskuotas tekstas, tad pačios audito lentelės ekspozicija
apsiriboja GP_ žymėmis plius tapatybė/IP/laikas/baitų skaičius.

Grįžtama **saugykla** (`gp_vault`) yra jautri saugvietė — laiko viso, kas kada
nors maskuota, atvirą tekstą. Prunink su `GP_VAULT_TTL_DAYS` (numatyta 30) ir
saugok kaip karūnos brangenybes.

---

## 6. Stebėsena

Šliuzas atskleidžia Prometheus metrikas `GET /metrics` (užklausos/maskavimo
latencijos histogramos, užmaskuotų span'ų skaičiai, upstream statusas,
fail-closed skaitikliai, plius nutekėjimų-aptikimo gauge'ai: DB-pool naudojama/
laisva, event-loop delsa, asyncio task'ų skaičius, cache dydis/iškraustymai).
`gliner` ir `anonymizer` atskleidžia tą patį. Pilnas Zabbix template,
eksporteriai, dashboard'ai ir preventyvūs trigeriai — **[MONITORING.lt.md](MONITORING.lt.md)**.
Trigeriai `gliner_model_on_gpu=0` ir `*_fail_closed_total>0` kritinis kiekvienas
būtų pagavęs realų incidentą kūrimo metu.

---

## 7. Patikra

Iš programuotojo mašinos, prieš atveriant bet kurį Claude klientą:

```bash
curl -X POST "https://gp-proxy.internal.example.com/v1/messages" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-8","max_tokens":1,"messages":[{"role":"user","content":"."}]}'
```

**A režime** `401` čia yra laukiamas, teisingas atsakymas: įrodo, kad šliuzas
pasiekiamas ir persiuntė užklausą, o upstream atmetė, nes curl nesiuntė
prenumeratos kredencialo. **B režime** užklausa be gate žymės grąžina `401` iš
paties šliuzo (`"Invalid or missing gateway credential"`), o užklausa su
galiojančiu `Authorization: Bearer gpk_…` persiunčiama.

Tada Claude Code paleisk `/status`. **Anthropic base URL** eilutė turi rodyti
šliuzo adresą; A režime **Login method** eilutė turi vis dar įvardinti tavo
claude.ai paskyrą (ne API raktą).

Patvirtinti, kad maskavimas realiai vyksta — stebėk šliuzą programuotojui dirbant
arba tikrink saugyklą tiesiogiai:

```bash
docker compose logs -f gp-claude-proxy
# [gp-proxy] POST /v1/messages -> 200 mask=340ms total=4.1s cache 11/14 (79% hit)

docker exec postgres psql -U guardprompt -d guardprompt \
  -c "SELECT token, value FROM gp_vault ORDER BY value LIMIT 20;"
# tikras vardas/email/tel/IBAN/asmens kodas -> GP_xxxxxxxxxxxx
```

Nustatyk `GP_LOG_SENT=true`, kad užmaskuotos išeinančios `messages` būtų
logginamos į stdout — operatorius patvirtina, kad tikros reikšmės tapo GP_ žymėmis
prieš išeinant.

---

## 8. Gedimų šalinimas

| Simptomas | Priežastis | Sprendimas |
|---|---|---|
| Kiekviena užklausa `429 rate_limit_error`, žinutė `"Error"`, be `anthropic-ratelimit-*` header'ių | **Užmaskuota Claude Code system-prompt tapatybė** — prenumeratos OAuth atmeta netikrą klientą kaip rate limit (žr. §4a). Nutinka tik jei redagavai `bodywalk.py` | Laikyk tapatybės bloką nepaliestą; netokenizuok jo |
| `401 "Invalid bearer token"` A režime net su galiojančiu login | `/api/hello` 404'ino, tad klientas nustojo teisingai siųsti OAuth (žr. §4b) | Užtikrink, kad catch-all persiuntimo maršrutas yra |
| `401 "Invalid or missing gateway credential"` B režime | Klientas nepateikė gate žymės arba pateikė ne iš `GP_PROXY_KEYS` | Nustatyk `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` į programuotojo `gpk_…` |
| B režimo užklausa → `401 "invalid x-api-key"` su tikru `request_id` | **Upstream** Anthropic API raktas blogas/dummy — gate praėjo ir užklausa pasiekė Anthropic | Įdėk tikrą `sk-ant-…` į `GP_UPSTREAM_API_KEY` |
| `403` su HTML kūnu, o šliuzo loguose **jokios užklausos** | WAF/reverse proxy priekyje blokavo kūną. Claude prompt'ai turi XML tag'us ir kodą, atitinkantį XSS kūno taisykles. **Trumpas curl praeina, o reali sesija krenta** | Atleisk `/v1/messages` nuo kūno inspekcijos. **Taikoma SafeLine, kuris priekyje šio diegimo** |
| `[GuardPrompt] Užklausa užblokuota` | gliner nulūžęs arba maskavimas nepavyko; fail-closed atmetė, o ne persiuntė atvirą turinį | Tikrink `docker compose logs gliner`. `GP_FAIL_CLOSED=false` išjungia apsaugą — atviras turinys tada pasiekia Anthropic gedimo atveju |
| Atsakymai grįžta su `GP_a3298922c55a` | Žemėlapio nebėra: saugykla prunint'a (`GP_VAULT_TTL_DAYS`), pasikeitė `GP_TOKEN_SECRET`, arba programuotojas iš naujo prisilogino ir tapo nauju owner | Pradėk naują pokalbį. Nekeisk `GP_TOKEN_SECRET` |
| Claude Code prašo prisilogint (A režimas) | Kažkur nustatytas gateway kredencialo kintamasis ir pakeitė prenumeratą | Panaikink `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` |
| Pirma užklausa labai lėta, vėlesnės greitos | Laukiama: gliner apdoroja visą pokalbį kartą, tada block cache jį aptarnauja (išmatuota 2.3s → 0.3s) | Nieko |
| `Unable to connect to API` | Šliuzas prijungtas prie `127.0.0.1`, o programuotojas ant kitos mašinos | Publikuok per VPN arba reverse proxy |

---

## 9. Ką tai apsaugo ir ko ne

**Apsaugo:** reikšmes, atitinkančias importuotas deterministines taisykles
(paslaptys, žymės, raktai, connection string'ai, email'ai, IBAN'ai, telefonai,
LT asmens kodai, kortelių numeriai, kripto adresai, PVM kodai, prie raktažodžio
pririšti įmonių kodai, dokumentų numeriai, valstybiniai numeriai, GPS) ir gliner
(asmuo, sveikata, kriminalika, politika, religija, …), plius viską iš
`GP_CUSTOM_WORDS` — niekada nepasiekia Anthropic atviru tekstu. Taisyklių rinkinys
dengia tas pačias kategorijas kaip dokumentų anonimizatorius, minus dvi sąmoningai
išmestos kodui: plikos datos ir pliki įmonių kodai, kurie kaip pliki skaitmenų
srautai tokenizuotų paprastus skaitinius literalus (žr. žemiau). gliner **asmens**
span'ai validuojami to paties bendro filtro (`person_noise.py`), kurį naudoja
anonimizatorius, tad pareigos ir institucijos ("…departamento direktoriui")
netokenizuojamos kaip vardai — mažiau prompt'o pūtimo, identiškas elgesys abiejuose
keliuose.

**Neapsaugo:**

- **Jautrių reikšmių be šablono ir ne `GP_CUSTOM_WORDS`.** Vidinis hostname'as ar
  kliento vardas, kurio niekas neįrašė, praeina kaip yra.
- **Plikų datų ir plikų (nepažymėtų) įmonių kodų.** Sąmoningai nemaskuojama čia,
  skirtingai nei dokumentų anonimizatoriuje: kaip pliki skaitmenų srautai jie
  tokenizuotų kiekvieną datą ir kiekvieną 7-9 skaitmenų literalą kode, degraduojant
  Claude pagalbą be privatumo naudos. Įmonės kodas prie savo raktažodžio ("įmonės
  kodas 302471233") *maskuojamas*; vienišas `302471233` — ne.
- **Lokalių transkriptų.** Claude Code saugo sesijų transkriptus atviru tekstu po
  `~/.claude/projects/` 30 dienų pagal nutylėjimą (`cleanupPeriodDays`), ant
  kiekvieno programuotojo nešiojamo. Šliuzas saugo tinklo šuolį, ne diską.
- **Pačios saugyklos.** `gp_vault` Postgres'e laiko viso, kas kada nors maskuota,
  atvirą tekstą — viena lentelė su visu tuo. Saugok atitinkamai.
- **Paslapčių, gyvenančių kode.** Šliuzas — tinklas, ne pataisa. Bet kas įrašyta
  kietai repozitorijoje jau yra ant kiekvieno nešiojamo, git istorijoje ir
  kiekviename klone; užmaskavimas pakeliui į Claude uždaro vieną kelią iš daugelio.
