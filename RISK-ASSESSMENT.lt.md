> 🌐 **Kalba / Language:** **Lietuvių** · [English](RISK-ASSESSMENT.md)

# Rizikos vertinimas — Claude naudojimas programuotojams per GuardPrompt šliuzą

| | |
|---|---|
| **Vertinamas sprendimas** | `gp-claude-proxy` — GuardPrompt šliuzas tarp įmonės Claude aplikacijų ir Anthropic |
| **Pirkimo objektas** | claude.ai prenumeratos programuotojams — **Team**, ne Pro/Max (žr. R15) |
| **Data** | 2026-07-17 · atnaujinta 2026-07-24 |
| **Statusas** | Sukurtas ir **patikrintas gyvai prieš tikrą `api.anthropic.com`.** Prenumeratos pass-through veikia end-to-end (tikri 200 atsakymai, PII užmaskuota saugykloje, audito eilutės rašomos); bendro-API-rakto režimas patikrintas dėl gate + maskavimo + owner izoliacijos. Parko pilotas vis dar rekomenduojamas (R14). |

---

## 1. Santrauka sprendimų priėmėjui

Sprendimas **reikšmingai sumažina**, bet **nepanaikina** jautrių duomenų patekimo pas Anthropic rizikos.

**Ką jis daro:** pakeičia jautrias *reikšmes* (paslaptis, raktus, asmens duomenis, klientų pavadinimus) grįžtamomis žymėmis prieš išsiunčiant, ir atstato jas grįžtant. Žemėlapis lieka mūsų infrastruktūroje. Jis taip pat gali laikyti **pseudonimizuotą kas-ką-siuntė audito seką** ir yra stebimas **Zabbix stebėsenos plokštumos**, aliarmuojančios, jei maskavimo apsauga kada nors sugestų — atskaitomybė, kurios asmeninė Claude paskyra negali suteikti.

**Ko jis nedaro — ir tai svarbiausia šiame dokumente:**

> **Sprendimas uždengia reikšmes, bet ne kodo LOGIKĄ.** Algoritmai, struktūra, metodų pavadinimai, komentarai ir verslo logika **pasiekia Anthropic**. Jei mūsų intelektinė nuosavybė yra pats algoritmas, o ne jame esančios konstantos — ši rizika **lieka beveik nepakitusi**.

**Rekomendacija: vykdyti pirkimą.**

Viena blokuojanti sąlyga: **pirkti Team, ne Pro/Max** (R15) — Pro/Max leidžia Anthropic treniruoti modelį mūsų duomenimis.

Vienas sprendimas vadovybei: **priimti R1** (kodo logika pasiekia Anthropic) arba atsisakyti Claude apskritai. Tai pasirinkimas, ne kliūtis — šliuzas R1 nekeičia (žr. 5 sk.).

Visa kita — diegimo sąlygos, netrukdančios pirkti (8 skyrius).

---

## 2. Kas konkrečiai vyksta

```
Programuotojas → gp-claude-proxy → api.anthropic.com
   (mūsų mašina)   ├─ 68 taisyklės (regex)
                   ├─ gliner NER (asmuo, sveikata, kriminalas…)
                   ├─ mūsų sąrašas (klientai, domenai)
                   └─ Postgres žemėlapis (neišeina)
```

**Iliustracija — ką realiai mato Anthropic** (tikras testo rezultatas su mūsų kodu):

```python
class Pipeline:                                    ← MATO
    def __init__(self):                            ← MATO
        self.name = "GP_db7ada001391 Anonymizer"   ← reikšmė uždengta
        self.AWS = "GP_0472b55b6a55"               ← reikšmė uždengta
        self.DB  = "GP_a3298922c55a"               ← reikšmė uždengta

    def run(self):                                 ← MATO
        headers = {"Authorization": "Bearer GP_9e6be8c56d19"}
        return requests.post(self.DB, headers=headers)   ← LOGIKA MATOMA
```

Tai tiksliai parodo ribą: **konstantos paslėptos, sandara — ne.**

---

## 3. Rizikų registras

Tikimybė / Poveikis: 1 = žema, 2 = vidutinė, 3 = aukšta. Lygis = sandauga.

| ID | Rizika | Tik. | Pov. | Lygis | Valdymo priemonė |
|---|---|:--:|:--:|:--:|---|
| **R1** | **Kodo logika, struktūra ir komentarai pasiekia Anthropic.** Uždengiamos tik reikšmės | 3 | 3 | **9** | Nėra techninės. Vienintelis sprendimas — inferencija savo debesyje (Azure/AWS), kurio neturime. **Priimti arba atsisakyti pirkimo** |
| **R2** | **Jautrios reikšmės be šablono** — vidiniai hostname'ai, klientų pavadinimai, projektų kodiniai vardai, kurių nėra `GP_CUSTOM_WORDS` — praeina kaip yra | 3 | 2 | **6** | Kruopščiai užpildyti ir prižiūrėti `GP_CUSTOM_WORDS`. Periodinė peržiūra |
| **R3** | **Lokalūs transkriptai.** Claude Code sesijas saugo **atviru tekstu** `~/.claude/projects/` 30 d. ant kiekvieno nešiojamojo kompiuterio | 3 | 1 | **3** | **BitLocker aktyvus visuose kompiuteriuose** — pamestas/pavogtas kompiuteris šifruotas, pagrindinis vektorius uždarytas. Lieka: `cleanupPeriodDays` sumažinti; IT politika |
| **R4** | **`gp_vault` lentelė** — viena vieta, kur surinktas atviras tekstas **visko, kas kada nors uždengta** | 1 | 3 | **3** | Riboti DB rolę; `GP_VAULT_TTL_DAYS=30`; įtraukti į atsarginių kopijų apsaugos apimtį |
| **R5** | **Šliuzas nukrenta → sustoja visa komanda.** Fail-closed pagal dizainą | 2 | 2 | **4** | **Zabbix stebėsena įdiegta** — `/metrics` ant proxy + gliner + anonymizer, su `nodata()` source-down trigeriais, `*_fail_closed_total` aliarmais ir preventyviu pool/disko/sertifikato prognozavimu. `GP_FAIL_CLOSED=false` yra avarinis jungiklis, **bet jį įjungus žalias kodas keliauja pas Anthropic** |
| **R6** | **gliner yra tikimybinis** — asmenvardžius, sveikatos duomenis gali praleisti | 2 | 2 | **4** | Deterministinės regex taisyklės dengia identifikatorius; gliner tik papildo |
| **R7** | **Slack ir web Claude negali eiti per šliuzą** (Anthropic talpinami) | 2 | 3 | **6** | **Privaloma** išjungti tuos paviršius šiems vartotojams |
| **R8** | **Anthropic keičia šliuzo kontraktą.** Claude Code gauna naujų galimybių su kiekviena laida | 2 | 2 | **4** | Antraštės ir laukai apdorojami kaip **atviri sąrašai**, ne allowlist. Testuoti po Claude Code atnaujinimų |
| **R9** | **Naujas kodas, kurį reikia prižiūrėti.** Šliuzas — mūsų atsakomybė | 3 | 1 | **3** | ~950 eilučių, testų rinkinys yra. Priežiūra — mūsų komanda |
| **R10** | **Konfigūracija nėra aiškiai aprašyta Anthropic dokumentacijoje** (šliuzas, kuris modifikuoja turinį). Blogiausiu realiu atveju — „nepalaikoma konfigūracija" kreipiantis pagalbos | 1 | 2 | **2** | Grąžinimas atgal — **vienas kintamasis** (`ANTHROPIC_BASE_URL`), viskas veikia kaip anksčiau. Paklausti per įprastą palaikymą, kai bus proga — **ne blokuojanti sąlyga** (žr. 7 sk.) |
| **R11** | **Uždengus identifikatorius, Claude prasčiau supranta kodą** → prastesni patarimai | 2 | 1 | **2** | Matuoti po pirmo mėnesio. `GP_CUSTOM_WORDS` siaurinti, jei per daug |
| **R12** | **SafeLine WAF tyliai sulaužys.** Claude prompt'uose XML žymės ir kodas atitinka XSS taisykles; curl testas praeina, tikra sesija — ne | 3 | 1 | **3** | Atleisti `/v1/messages` nuo kūno inspekcijos. Dokumentuota |
| **R13** | **Paslaptys, gyvenančios kode.** Šliuzas uždaro vieną kelią; jos lieka git istorijoje, klonuose, nešiojamuosiuose kompiuteriuose. **Kodas lieka mūsų on-prem GitLab — tai vidinė ekspozicija (repo prieiga, dev kompiuteriai, CI logai, atsargkopijos), ne išorinis nutekėjimas** | 3 | 1 | **3** | **Nepriklausomas darbas.** Šliuzas šito neišsprendžia ir neturi būti pateikiamas kaip sprendimas. **On-prem GitLab prieigos kontrolė + BitLocker aktyvus visuose kompiuteriuose** apriboja iki autorizuotos vidinės prieigos |
| **R14** | **Netestuota su tikru Claude.** Testai — su butaforiniu upstream'u ir atmintimi | 2 | 2 | **4** | Bandomasis laikotarpis su 1 programuotoju prieš plečiant |
| **R15** | **Pro/Max planai = vartotojiškos sąlygos.** Anthropic **gali treniruoti modelį** mūsų duomenimis, jei programuotojo asmeniniame nustatyme įjungta; saugojimas **5 metai** vietoj 30 d. Įmonė to centralizuotai nekontroliuoja | 3 | 3 | **9** | **Pirkti Team planą** (komercinės sąlygos: netreniruoja, 30 d.). Enterprise — jei reikia ZDR |

---

## 4. Aukščiausios rizikos — detaliau

### R1 — kodo logika pasiekia Anthropic

Pseudonimizavimas dirba su **reikšmėmis**. Funkcijos pavadinimas, kontrolės srautas, komentarai, importai, klasių sandara, algoritmas — viskas keliauja.

Jei nerimą kelia **klientų duomenys kode** — R1 nesvarbi, sprendimas veikia.
Jei nerimą kelia **mūsų pačių algoritmų nutekėjimas** — R1 reiškia, kad sprendimas šito neišsprendžia.

**Vienintelė alternatyva:** inferencija mūsų nuomojamame debesyje (Microsoft Foundry „Hosted on Azure", AWS Bedrock arba Google). Tada kodas fiziškai nepasiekia Anthropic. **Reikalauja Azure/AWS prenumeratos, kurios neturime.**

Net ir ten yra išlyga: Foundry dokumentacija sako, kad *„content flagged by Anthropic's safety systems egress to Anthropic"* — saugumo sistemų pažymėtas turinys vis tiek iškeliauja.

### R13 — paslaptys kode (lygis 3, ne išorinis nutekėjimas)

Šiuo metu jautri informacija yra pačiame kode. Tai reiškia, kad ji jau yra: git istorijoje, kiekvieno programuotojo nešiojamajame kompiuteryje, kiekviename klone, CI loguose, atsarginėse kopijose.

**Visa tai lieka mūsų on-prem GitLab — niekas neiškeliauja iš mūsų infrastruktūros.** Ekspozicija vidinė: bet kas su repo prieiga, CI logai, atsargkopijos. Pamestas ar pavogtas kompiuteris **nėra** vektorius — **BitLocker aktyvus visuose kompiuteriuose**, diskas šifruotas. Lieka reali, bet apribota higienos problema autorizuotai vidinei prieigai, **ne** vieša/išorinė ekspozicija, kurią implikavo 9 lygio vertinimas — todėl lygis 3, ribojamas GitLab prieigos kontrolės ir viso disko šifravimo.

Šliuzas uždengia ją pakeliui pas Claude. **Visi kiti (vidiniai) keliai lieka atviri.**

Šis darbas turi būti atliktas **nepriklausomai nuo pirkimo**. Jis nėra šio sprendimo dalis ir šliuzas jo nepakeičia.

---

## 5. Rizikos, jei sprendimo NEDIEGSIME

| Scenarijus | Rizika |
|---|---|
| **Programuotojai naudos Claude savo iniciatyva** (asmeninės paskyros, telefonai, namų kompiuteriai) | Nulinė kontrolė, nulinis auditas, nulinis uždengimas. Asmeninė paskyra = **vartotojiškos sąlygos** → Anthropic **gali treniruoti modelį** mūsų kodu, saugoti **5 metus**. **Blogiau visais matmenimis** |
| **AI įrankių neduodame visai** | Prarandamas produktyvumas; konkurencinis atsilikimas. Praktikoje virsta pirmuoju scenarijumi — draudimas nesustabdo, tik nuveda į šešėlį |
| **Duodame Claude be šliuzo** | Viskas — paslaptys, klientų duomenys, kodas — keliauja neapdorota |

Bazinė linija nėra „nulis rizikos". Bazinė linija yra **arba nulinė kontrolė, arba nulis AI**.

### Išvada

**Šliuzas nėra rizika — jis yra rizikos sumažinimas kiekvienos realios alternatyvos atžvilgiu.**

Sprendimas skyla į du **nepriklausomus** klausimus, kuriuos svarbu neišpainioti:

**1. Ar apskritai naudojame Claude?**
Čia priklauso R1 (kodo logika pasiekia Anthropic). Šis klausimas galioja **vienodai su šliuzu ir be jo** — šliuzas jo nei pagerina, nei pablogina. R1 **nėra argumentas prieš šliuzą**; tai argumentas dėl Claude naudojimo apskritai.

**2. Jei Claude naudojame — su šliuzu ar be?**
Atsakymas vienareikšmis: **su šliuzu**. Jis nieko nepablogina ir uždengia viską, ką įmanoma uždengti be savo debesies. Kaina — viena prižiūrima paslauga ir pirmos užklausos latencija.

**Draudimas nėra saugus variantas.** Jei licencijų neperkame, programuotojai Claude naudos asmeninėmis paskyromis. Tada gauname **blogiausią įmanomą derinį**: nulinis uždengimas, nulinis auditas, ir — dėl vartotojiškų sąlygų — Anthropic **gali treniruoti modelį** mūsų kodu bei saugoti jį **5 metus**. Nepirkimas yra **rizikingesnis nei pirkimas**, ne tik lėtesnis.

**Rekomendacija: diegti.** Su Team planu ir 8 skyriaus sąlygomis šis sprendimas yra geriausias pasiekiamas variantas be nuosavos debesies infrastruktūros.

---

## 6. Ką patikrinome (įrodymai)

| Patikrinta | Rezultatas |
|---|---|
| Transportas, srautas, prenumeratų perdavimas | 11/11 testų |
| Grįžtamas pseudonimizavimas ant tikro mūsų kodo | 11/11 testų |
| Uždengtas kodas lieka galiojantis Python | ✅ (įtraukos, eilutės nepakitusios) |
| Atstatymas 1:1 su originalu | ✅ |
| Deterministika (Anthropic prompt cache išlieka) | ✅ |
| Izoliacija tarp programuotojų | ✅ (dev-b negali atstatyti dev-a reikšmių) |
| Žymė, perskelta per du srauto gabalus | ✅ atstatoma |
| gliner latencija su kešu | 2,3 s → 0,3 s (**6,7×**) |
| Fail-closed | ✅ blokuoja, neperduoda |
| Transportas iki **tikro** `api.anthropic.com` | ✅ pasiekia tikrą galą (grąžina `request_id`; atmeta tik testinį raktą) |
| Išsaugojimas **tikroje** Postgres saugykloje | ✅ žymės + originalai įrašomi ir nuskaitomi per veikiantį konteinerį |
| Aprėpties atitikimas anonimizatoriui | ✅ pridėti asmens kodas, kortelė, kripto, PVM, įmonės kodas; patikrinta uždengimas nuo galo iki galo |
| Kodo literalai neperdengiami | ✅ portai, timeout'ai, versijos (6–10 skaitmenų skaičiai) nepaliesti |
| **Prenumeratos pass-through prieš tikrą Claude** | ✅ tikri `200` atsakymai per proxy; **`429` buvo užmaskuota system-prompt tapatybė, dabar pataisyta** (žr. GP-CLAUDE-PROXY §4a) |
| **Bendro-API-rakto režimas** | ✅ gate atmeta blogus raktus (401), priima galiojančius, maskuoja prieš siuntimą, owner izoliacija per gate raktą — upstream `200` vis dar reikia tikro `sk-ant-` |
| **Kas-siuntė auditas** | ✅ `gp_audit` eilutės rašomos su siuntėjo tapatybe + užmaskuotu turiniu |
| **Stebėsena gyva** | ✅ Zabbix skaito visus tris `/metrics`; trigeriai `model_on_gpu=0`, `*_fail_closed`, nodata, disko/sertifikato prognozės aktyvūs |

**Ko NEpatikrinome** (pilotinis žingsnis, R14):

- Realios latencijos su 100k tokenų kontekstu
- Ilgų (kelių valandų) sesijų parke masiškai
- Bendro-API-rakto režimo grąžinant tikrą upstream `200` (reikia tikro Anthropic API rakto)

---

## 7. R10 — kodėl tai maža rizika (blaivus vertinimas)

Ankstesnėje šio dokumento versijoje buvo rekomendacija „gauti raštišką Anthropic patvirtinimą prieš pirkimą". **Ji atmesta kaip nepraktiška ir neproporcinga** — sąlyga, kurios neįmanoma įvykdyti, ne valdo riziką, o užšaldo sprendimą.

**Ką iš tikro sako įrodymai:**

1. **Pati šliuzo konfigūracija yra oficialiai palaikoma ir dokumentuota.** Anthropic aprašo prenumeratos srauto nukreipimą per šliuzą (`ANTHROPIC_BASE_URL` be šliuzo kredencialo) ir netgi nurodo, ką šliuzas privalo persiųsti, kad tai veiktų.

2. **Nerimą kėlusi eilutė yra techninė, ne teisinė.** Ji yra skyriuje apie **funkcijų perdavimą** (*feature pass-through*) ir įspėja apie **gedimą**, ne draudžia:

   > *„A gateway that rewrites or redacts request bodies for content inspection **breaks the pairing** the same way stripping does…"*

   Kalbama apie beta antraščių ir jų kūno laukų poras: sulaužius jas gaunamos `400` klaidos. **Mūsų šliuzas jų neliečia** — antraštės persiunčiamos pažodžiui, laukų sandara nekeičiama, keičiamos tik teksto **reikšmės** laukuose, kurie yra mūsų pačių turinys.

3. **Tai mūsų pačių turinys, siunčiamas iš mūsų pačių infrastruktūros.** Modifikuojame savo kodą prieš išsiųsdami — tai nėra Anthropic paslaugos apėjimas ar naudojimo apribojimų laužymas.

**Reali blogiausio atvejo riba:** ne sutarties pažeidimas su sankcijomis, o **„nepalaikoma konfigūracija"** kreipiantis į palaikymą. Tai reiškia, kad triktį taisytume patys — kaip ir bet kurį kitą savo komponentą.

**Grąžinimas atgal kainuoja vieną eilutę.** Išjungus `ANTHROPIC_BASE_URL`, visos trys aplikacijos jungiasi tiesiogiai ir veikia įprastai. Nėra migracijos, nėra duomenų praradimo, nėra užrakto.

**Proporcingas veiksmas:** paklausti per įprastą Team plano palaikymo kanalą, kai bus proga. **Neblokuoti pirkimo.**

---

## 8. Rekomendacija

**Vykdyti pirkimą su šiomis sąlygomis:**

**Blokuojanti sąlyga tik viena:**

0. **Pirkti Team planą, ne Pro/Max** (R15). Pro/Max yra vartotojiškos sąlygos: Anthropic gali treniruoti modelį mūsų duomenimis ir saugoti 5 metus, o nustatymą valdo kiekvienas programuotojas asmeniškai. Team = komercinės sąlygos: netreniruoja, 30 d. saugojimas. **Tai vienintelis punktas, keičiantis pirkimo objektą — patikrinti prieš pasirašant.**

**Sprendimas, kurį turi priimti vadovybė (ne sąlyga, o pasirinkimas):**

1. **R1 — kodo logika pasiekia Anthropic.** Priimti arba atsisakyti Claude naudojimo apskritai. Šliuzas šito nekeičia nei į gerą, nei į blogą (žr. 5 sk. išvadą).

**Diegimo sąlygos (po pirkimo, netrukdo pirkti):**

2. **Pradėti nuo 1 programuotojo** bandomajam laikotarpiui (R14), tada plėsti.
4. **Užpildyti `GP_CUSTOM_WORDS`** prieš pirmą naudojimą (R2).
5. **Išjungti Claude Slack/web** šiems vartotojams (R7).
6. **SafeLine išimtis** `/v1/messages` (R12).
7. **`cleanupPeriodDays`** programuotojų nešiojamuosiuose kompiuteriuose (R3). BitLocker jau aktyvus visuose kompiuteriuose.
8. **R13 (paslaptys kode) pradėti atskirai** — nelaukiant šio sprendimo ir nelaikant jo sprendimu.

**Neverta pirkti, jei:** pagrindinis nerimas yra R1 (mūsų algoritmų nutekėjimas). Tada vienintelis kelias — Azure/AWS prenumerata ir inferencija savo debesyje.

---

## 9. Susiję dokumentai

- Diegimas ir konfigūracija: [GP-CLAUDE-PROXY.lt.md](GP-CLAUDE-PROXY.lt.md)
- Architektūra: [ARCHITECTURE.lt.md](ARCHITECTURE.lt.md)
- BDAR / DI akto atitiktis: [COMPLIANCE.lt.md](COMPLIANCE.lt.md)
