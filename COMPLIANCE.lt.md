> 🌐 **Kalba / Language:** **Lietuvių** · [English](COMPLIANCE.md)

# GuardPrompt — atitiktis GDPR ir ES DI aktui

Šis dokumentas parodo, **kaip GuardPrompt techninėmis priemonėmis palaiko** atitiktį
Bendrajam duomenų apsaugos reglamentui (BDAR / GDPR, 2016/679) ir ES Dirbtinio
intelekto aktui (DI aktas / Reg. 2024/1689).

> **Svarbu:** GuardPrompt teikia **technines priemones**. Galutinė teisinė atitiktis
> priklauso nuo diegimo konteksto, naudojimo tikslo ir organizacijos procesų —
> už ją atsako duomenų valdytojas. Šis dokumentas nėra teisinė garantija ar
> sertifikatas.

---

## 1. Pamatinis principas — duomenys neišeina

Visa sistema veikia **on-premise** (organizacijos serveryje): OpenWebUI, RAG
(Qdrant), duomenų bazė (PostgreSQL), OCR (Docling), anonimizatorius, lokalus LLM
(Ollama) ir **kalba-į-tekstą** (lokalus lietuviškas transkripcijos variklis). Jokie
dokumentai, pokalbiai **ar garsas** nesiunčiami į debesį, **nebent** sąmoningai
sukonfigūruojamas išorinis LLM (pvz. OpenRouter) — ir net tada **kiekviena žinutė
pirma anonimizuojama** (žr. 4 skyrių). Balso įvestis ir susitikimų įrašai
transkribuojami lokaliai, tad neapdorotas garsas niekada nepalieka mašinos; gautas
tekstas anonimizuojamas tuo pačiu keliu kaip bet koks chat. Jei anonimizatorius
negali veikti, užklausa **blokuojama, o ne siunčiama neanonimizuota** (fail-closed) —
serviso sutrikimas niekada nevirsta tyliu duomenų nutekėjimu.

---

## 2. BDAR (GDPR) atitiktis

| Straipsnis | Reikalavimas | Kaip GuardPrompt palaiko |
|---|---|---|
| **5 str.** | Duomenų minimizavimas, tikslo apribojimas, vientisumas ir konfidencialumas | Anonimizatorius pašalina perteklinius asmens duomenis prieš saugojimą/apdorojimą; on-prem izoliacija |
| **9 str.** | Specialių kategorijų duomenys | Slepiama: **sveikata, psichika, rasinė/etninė kilmė, politinės pažiūros, religiniai ir filosofiniai įsitikinimai, profsąjunga, biometrija, seksualinė orientacija/lytinis gyvenimas** |
| **10 str.** | Apkaltinamojo pobūdžio duomenys | Slepiami nusikaltimų/teistumo duomenys (`[CRIMINAL]`) |
| **25 str.** | Pritaikytoji ir standartizuotoji duomenų apsauga (*by design / by default*) | Anonimizavimas įjungtas pagal nutylėjimą; „nutekėjimas blogiau nei per-uždengimas"; **fail-closed** |
| **30 str.** | Duomenų tvarkymo veiklos įrašai | `gp-claude-proxy` gali saugoti **pseudonimizuotą kas-ką-siuntė auditą** (`gp_audit`) kiekvienai DI užklausai — siuntėjo tapatybę, laiką ir užmaskuotą turinį, saugomą konfigūruojamą laiką (`GP_AUDIT_TTL_DAYS`) |
| **32 str.** | Apdorojimo saugumas | On-prem, konteinerių izoliacija, licencijos raktas, audit log; paslaptys `.env`, ne kode; **fail-closed anonimizacija** ir **Zabbix stebėsenos plokštuma** su preventyviais + nutekėjimo trigeriais ir `*_fail_closed` aliarmais suteikia nuolatinį patvirtinimą, kad apsaugos veikia |
| **35 str.** | Poveikio duomenų apsaugai vertinimas (DPIA) | On-prem architektūra ir anonimizavimas mažina riziką, palengvina DPIA |

**Slepiami identifikatoriai (be 9/10 str.):** vardai/pavardės, asmens kodas, el. paštas,
telefonas, IBAN, mokėjimo kortelė, kripto adresai, IP, adresai, datos, įmonių/PVM/dok.
numeriai, **pasas, ATK, SODRA, SWIFT/BIC, bylos/sutarties nr., paciento/ligos istorijos
nr., transporto numeriai, vairuotojo pažymėjimas/VKK, registracijos liudijimas, VIN, MAC,
IMEI, GPS koordinatės**, dev/IT paslaptys (API raktai, tokenai, sertifikatai, connection
stringai).

---

## 3. ES DI akto (2024/1689) atitiktis

| Straipsnis | Reikalavimas / draudimas | Kaip GuardPrompt palaiko |
|---|---|---|
| **5(1)(g) str.** | Draudžiamas biometrinis kategorizavimas **išvedant** rasę, politines pažiūras, profsąjungą, religinius/filosofinius įsitikinimus, lytinį gyvenimą, seksualinę orientaciją | Anonimizatorius **pašalina** šiuos atributus → LLM jų nemato → **negali jų išvesti** (atitiktis *by-design*) |
| **5(1)(f) str.** | Draudžiamas emocijų atpažinimas darbo/švietimo srityse | GuardPrompt **nevykdo** emocijų atpažinimo |
| **10 str.** | Aukštos rizikos: duomenų valdymas ir kokybė | Anonimizuoti, minimizuoti duomenys; valdomas KB turinys per `kb-admin` |
| **12 str.** | Įrašų saugojimas (*logging*) | OpenWebUI audit log (`AUDIT_LOG`), anonimizatoriaus veiklos žymos, ir nebūtinas `gp_audit` Claude-proxy naudojimo įrašas (pseudonimizuotas turinys + siuntėjo tapatybė) — plius Prometheus metrikos, saugomos Zabbix |
| **14 str.** | Žmogaus atliekama priežiūra | Administratorius per `kb-admin` valdo žinių bazes, prieigą, sinchronizavimą |
| **50(1) str.** | Skaidrumas — informuoti, kad bendraujama su AI | Realizuojama OpenWebUI sąsajos lygiu |
| **50(2) str.** | Mašinos skaitomas dirbtinio turinio žymėjimas | **Spraga — žr. žemiau.** Provenance metaduomenys šiuo metu prarandami |
| **50(4) str.** | Atskleidimas, kad turinys sugeneruotas dirbtinai | **Įgyvendinta paveikslėliams** — oficialus ES ženklas įdeginamas į kiekvieną sugeneruotą vaizdą (žemiau) |

### 3.1 Sugeneruotų paveikslėlių žymėjimas

50 str. taikomas nuo **2026-08-02**; jau rinkoje esančioms sistemoms mašinos skaitomam
žymėjimui numatytas terminas iki **2026-12-02**. Baudos siekia 15 mln. € arba 3 %
pasaulinės apyvartos. Komisijos praktikos kodeksas reikalauja **sluoksniuoto**
sprendimo — matomo atskleidimo, mašinos skaitomo provenance, nematomo vandens ženklo
ir turinio atspaudų; nė vienas metodas atskirai nepakanka.

**Ką GuardPrompt daro dabar**

Kiekvienas pokalbyje sugeneruotas paveikslėlis pažymimas oficialiu Europos Komisijos
**„AI GENERATED"** ženklu (*Fully AI-Generated* piktograma, paskelbta laisvam
naudojimui be atribucijos). Uždeda OpenWebUI filtro funkcija `guardprompt_ai_label`:

- įdeginama **į pačius pikselius**, todėl ženklas išlieka atsisiuntus ir persiuntus —
  vien sąsajos etiketė neišliktų, o kodeksas reikalauja, kad liktų matomas;
- apatinis dešinys kampas, ~9,5 % vaizdo pločio, ES pusiau permatomas variantas;
- juodas ar baltas variantas parenkamas **automatiškai** pagal foną, kad ženklas
  liktų įskaitomas ant bet kokio vaizdo;
- idempotentiška — pergeneravus ar pakartotinai apdorojus ženklas nedubliuojamas.

Techninė pastaba: ženklas dedamas filtro `stream` kabliuke. Tai vienintelė galima
vieta — OpenWebUI `outlet` filtrams perduoda tik atrinktus žinutės laukus (`id`,
`role`, `content`, `info`, `timestamp`, `output`), o `files` sąrašas su paveikslėliu
iškerpamas, todėl `outlet` filtras vaizdo nepasiekia.

**Žinoma spraga — mašinos skaitomas provenance (50(2) str.)**

Paveikslėliai iš modelio tiekėjo ateina su pasirašytu C2PA manifestu, bet jis
neišlieka: OpenWebUI perkoduoja vaizdą dar prieš filtrą, o bet koks matomas ženklas
parašą vis tiek paverstų negaliojančiu — C2PA parašas dengia pikselius. Negaliojantis
manifestas **sąmoningai neperkeliamas**: pateikti sugadintą kredencialą blogiau nei
nepateikti jokio.

Spragai uždaryti reikia pasirašyti savo C2PA manifestu (savas sertifikatas + parašo
servisas). Planuojama iki 2026-12-02 termino. Iki tol diegimas tenkina **matomo
atskleidimo** prievolę, bet ne mašinos skaitomo — tai turi būti nurodyta atitikties
dokumentuose, o ne laikoma savaime įvykdyta.

---

## 4. Kur veikia anonimizavimas

Anonimizatorius įtrauktas **keliuose taškuose**:

1. **KB ingestija** — įkeliami dokumentai (Docling OCR → tekstas) anonimizuojami prieš
   patenkant į žinių bazę (Qdrant).
2. **Live pokalbis** — `gp-pipeline.py` *inlet* filtras anonimizuoja **kiekvieną
   vartotojo žinutę ir prisegtų nuotraukų OCR** PRIEŠ siunčiant į LLM (įskaitant išorinį
   OpenRouter).
3. **Programuotojų įrankiai** — `gp-claude-proxy` stovi tarp įmonės Claude Code klientų
   (Claude Code CLI, VS Code plėtinio, JetBrains IDE; o darbalaukio aplikacijos tik API-rakto
   režime) ir `api.anthropic.com`. Kodas ir užklausos pseudonimizuojami prieš išeinant; Anthropic gauna tik neskaidrias žymes
   (`GP_a3298922c55a`). Skirtingai nei 1 ir 2 keliuose, šis yra **grįžtamas** — modelio
   atsakymas įrašomas į failus, tad žemėlapis privalo atstatyti pakeliui atgal. Žemėlapis
   laikomas šio diegimo Postgres'e ir iš jo neišeina. Nebūtina **audito** lentelė
   (`gp_audit`) papildomai fiksuoja, *kas* siuntė kiekvieną užklausą ir *kada*, saugodama
   tik jau pseudonimizuotą turinį — 30 str. DI naudojimo įrašas, laikomas atskirai nuo
   grįžtamos saugyklos. ([GP-CLAUDE-PROXY.lt.md](GP-CLAUDE-PROXY.lt.md))
4. **Jūsų pačių programos** — tas pats anonimizatorius prieinamas kaip **REST API** (Bearer
   raktas; JSON, grynas tekstas ar failas; `/process` PDF/DOCX/…), tad išorinės sistemos gali
   anonimizuoti prieš archyvavimą, persiuntimą ar kitą apdorojimą. ([API.lt.md](API.lt.md))

**Fail-closed garantija:** jei anonimizavimas nepavyksta ar užtrunka (timeout), žinutė
**blokuojama** — neapdorotas tekstas niekada nepasiekia LLM. Tas pat galioja, jei `gliner`
NER servisas nepasiekiamas: užuot tyliai grąžinus tekstą be Art. 9/10 dengimo, užklausa
blokuojama — `[PROCESSING DISABLED: ANONYMIZATION SERVICE UNAVAILABLE]` (`ANON_REQUIRE_GLINER`).
Negaliojanti licencija blokuoja taip pat (`[PROCESSING DISABLED: LICENSE IS NOT VALID]`).
`gp-claude-proxy` veikia tuo pačiu principu (`GP_FAIL_CLOSED`, pagal nutylėjimą įjungta):
gliner gedimas užklausą atmeta, o ne persiunčia žalią kodą.

Trys techniniai sluoksniai (visi valdomi `.env` `ANON_*`, taisomi `ANON_ALLOW_WORDS` /
`ANON_ALLOW_REGEX`):
determinist. regex (identifikatoriai + dokumentų numeriai + dev/IT paslaptys) →
`gliner` NER (GDPR 9/10 str. + DI akto 5(1)(g) str. kategorijos). Detalės:
[ARCHITECTURE.lt.md](ARCHITECTURE.lt.md) skyrius „Anonimizavimo aprėptis".

---

## 5. Ribos ir atsakomybė

- GuardPrompt **negarantuoja** 100% aptikimo — nestruktūruotos, retos ar konteksto
  neturinčios jautrios frazės gali prasprūsti. Principas: linkstama į per-uždengimą,
  konkretūs atvejai valdomi allowlist'u (`ANON_ALLOW_WORDS` / `ANON_ALLOW_REGEX`) / custom žodžiais.
- **Maskavimo tikslumas (5 str. kokybė).** NER sluoksnis gali per plačiai žymėti — pareigybės
  ir institucijos gali būti palaikytos vardais. Bendras validavimo filtras (`person_noise.py`,
  naudojamas ir anonimizatoriaus, ir Claude šliuzo) tokius span'us atmeta, tad tikras
  per-uždengimas sumažinamas nesilpninant tikrų vardų aptikimo. Per-uždengimas niekada nesukelia
  nutekėjimo.
- Išorinio LLM (OpenRouter ir pan.) naudojimas — organizacijos sprendimas; net tada
  siunčiamas tik anonimizuotas tekstas, bet už tiekėjo sąlygas atsako valdytojas.
- **Prompt injection yra apribota, bet neišspręsta.** Į žinių bazę įkeltas dokumentas gali
  turėti modeliui skirto teksto („ignoruok instrukcijas", „atsiųsk tai …"). Žalą galiausiai
  riboja **gebėjimų apribojimas ir anonimizacija**, ne aptikimas: nesukonfigūruota jokių
  įrankių ar įrankių serverių, kodo vykdymas veikia naršyklėje (Pyodide, be Jupyter),
  todėl įterptas nurodymas **neturi kuo veikti** — o modelis mato tik anonimizuotą tekstą,
  tad negali atskleisti asmens duomenų, kurių niekada negavo, nei nieko išsiųsti adresu,
  kuris jau tapo `[EMAIL]`. Ant to sluoksniuojasi keturi aptikimo mechanizmai; rasta vieta
  keičiama į `[PROTECTION]`, o dokumentas apdorojamas įprastai, ne atmetamas:

  | Sluoksnis | Kur | Ką gaudo |
  |---|---|---|
  | Regex + obfuskacijos šalinimas | anonimizatorius | tiesiogines formuluotes išvardytomis kalbomis, plius leetspeak, išskaidytas raides, zero-width simbolius, homoglifus ir base64 užkoduotą turinį |
  | Paslėpto teksto tikrinimas | docling ekstrakcija | tekstą, kurio skaitytojas nematytų — baltą ant balto, ~1 pt, už puslapio ribų. Nepriklauso nuo kalbos: netikrina, ką tekstas sako, tik ar žmogus galėjo jį matyti |
  | Rašto anomalija | anonimizatorius (gale) | CJK/arabų/devanagari sakinį lietuviškame dokumente, nesvarbu ką jis sako |
  | Semantinis tikrinimas | gliner `/injection` | instrukcijų perrašymo ketinimą ~100 kalbų, įskaitant perfrazes |

  Eiliškumas svarbus: rašto ir semantinis sluoksniai veikia **po** viso anonimizavimo, ant
  galutinio teksto. Kai jie buvo įterpti tarp maskavimo perėjimų, vieno sluoksnio įrašytas
  žymeklis susiliedavo su kitu sakiniu ir tikrą injekciją nustumdavo žemiau slenksčio —
  viena apsauga tyliai išjungdavo kitą.

  Semantinis sluoksnis vertina **sakiniais** (injekcija 2,5 tūkst. simbolių chunk'e gavo
  0,40, o atskirai — 0,83; chunk'o lygiu atrodytų, kad veikia, bet praleistų viską), o
  balas yra **kontrastinis**: panašumas į injekcijos prototipus minus panašumas į įprastą
  administracinę kalbą. Vien panašumas netiko — kalibruojant su tikru 606 sakinių kliento
  dokumentu artimiausias teisėtas sakinys gavo 0,660, o silpniausia injekcija 0,661.
  Kontrastinis vertinimas nuleido teisėtų p99 iki 0,035 ir davė darbinę maržą be klaidingų
  suveikimų tame dokumente.

  Sąžiningos ribos: vien regex išmatuotas **1/15** su ta pačia injekcija, išversta į
  penkiolika kalbų — tai greičio ribotuvas, ne riba, ir niekada neturi būti pristatomas
  kaip riba. Semantinis slenkstis kalibruotas vienu korpusu ir turi būti pertikrintas su
  iš esmės kitokiu (`INJ_THRESHOLD`). Specializuoti klasifikatoriai buvo įvertinti ir
  atmesti: laisvai prieinami arba nereaguoja į lietuvių kalbą, arba pažymėjo 4 iš 7
  teisėtų lietuviškų teisinių tekstų; daugiakalbis generatyvinis kainavo ~535 ms kvietimui.
  Likutinė rizika — klaidinantis **atsakymas**, ne duomenų atskleidimas ar veiksmas
  užpuoliko naudai.
- Teisinę atitiktį (DPIA, sutartys, informavimas, saugojimo terminai) užtikrina
  organizacija; GuardPrompt teikia technines priemones tam palengvinti.
