> 🌐 **Kalba / Language:** **Lietuvių** · [English](WHAT_PROBLEMS_SOLVES.md)

# Kokias problemas sprendžia GuardPrompt
GuardPrompt sukurtas spręsti realius, pasikartojančius iššūkius organizacijose, kurios tvarko jautrią informaciją, didelius dokumentų kiekius ir turi griežtus atitikties reikalavimus. Šis dokumentas apžvelgia praktines problemas, kurias GuardPrompt sprendžia, ir teikiamą vertę.

**Viena eilute:** kiekvieną priežastį, dėl kurios organizacija dabar sako *"mes
negalime naudoti DI"* — duomenų išėjimą iš pastato, GDPR/NIS2 ekspoziciją, jokios
audito sekos, nepatikimą turinį, kainą už vietą — GuardPrompt paverčia į *"galime,
savo sąlygomis."* Tai pilna, self-hosted DI platforma, ne vienas įrankis.

---

## 1. Jautrios informacijos negalima saugiai siųsti į debesų DI
Organizacijos dirba su asmens duomenimis, sutartimis, procedūromis, personalo bylomis, žurnalais, vidaus ataskaitomis ir reguliaciniais dokumentais.  
Tokio turinio siuntimas debesų LLM tiekėjams (OpenAI, Google, Anthropic) kelia atitikties riziką.

**GuardPrompt tai sprendžia:**
- apdorodamas originalius dokumentus lokaliai,
- anonimizuodamas jautrius duomenis on-prem įrankiu,
- užtikrindamas, kad išorėje (jei organizacija to nori) būtų naudojamas tik *nuasmenintas* tekstas.

Tai leidžia saugiai diegti DI pagal BDAR, NIS2 ir vidaus saugumo politikas.

---

## 2. Reikia nuoseklaus, automatizuoto dokumentų anonimizavimo
Rankinis anonimizavimas yra:
- lėtas,
- nenuoseklus,
- klaidoms imlus,
- brangus.

**GuardPrompt teikia lokalų anonimizavimą** (determinist. regex + on-prem NER), kuris pašalina:
- vardus (t. p. užsienio ir linksniuotus), adresus, kontaktus,
- identifikatorius: asmens kodą, el. paštą, telefoną, IBAN, kortelę, kripto, IP, įmonės/PVM/dok. numerius,
- dokumentų numerius: pasą, ATK, SODRA, SWIFT/BIC, bylos/sutarties, paciento/ligos istorijos, produkto ir licencijos raktus,
- transporto ir IT duomenis: valst. numerius (LT + užsienio/vanity), vairuotojo pažymėjimą, registracijos liudijimą / techninį pasą, MAC, VIN, IMEI, GPS koordinates,
- programuotojų / IT paslaptis: cloud ir SaaS tokenus (AWS/GitHub/OpenAI/Slack/Google/Stripe/JWT), PEM privačius raktus ir sertifikatus, SSH raktus, connection stringus su kredencialais, Bearer / config key=value paslaptis,
- **GDPR 9/10 str. specialias kategorijas + ES DI akto 5(1)(g) str.**: sveikatą, psichiką, teistumą, politines pažiūras, religinius ir filosofinius įsitikinimus, profsąjungą, biometriją, rasinę/etninę kilmę, seksualinę orientaciją, pranešėjus. Pašalinus šiuos duomenis, LLM negali išvesti ar kategorizuoti pagal jautrius atributus — DI akto atitiktis by-design.

Viskas įjungiama/išjungiama pagal kategoriją ir taisoma allowlist'u.
Anonimizavimas vyksta prieš bet kokį išorinį naudojimą — nutekėjimas laikomas blogesniu nei per-uždengimas.

---

## 3. Darbuotojams sunku rasti informaciją tarp daugybės vidaus dokumentų
Žinios paslėptos:
- PDF failuose,
- skenuotuose failuose,
- Word dokumentuose,
- SharePoint,
- el. laiškų prieduose,
- intraneto portaluose.

Darbuotojai praranda valandas ieškodami ar perskaitinėdami dokumentus.

**GuardPrompt visus dokumentus paverčia ieškotina DI žinių baze**, paremta semantiniu RAG.

---

## 4. Nėra vidinio DI asistento, apmokyto pagal organizacijos dokumentus
Debesų DI agentai negali pasiekti vidinių failų (arba tai nesaugu).

**GuardPrompt teikia privatų DI asistentą**, kuris:
- atsako į klausimus pagal vidinius dokumentus,
- paaiškina taisykles, politikas ir procedūras,
- apibendrina ilgus dokumentus,
- palygina skirtingas versijas,
- išskiria esminius punktus ir įsipareigojimus.

Tai didina produktyvumą ir sprendimų kokybę.

---

## 5. Didelė individualių DI prenumeratų kaina (ChatGPT, Copilot ir kt.)
Prenumeratos pirkimas kiekvienam darbuotojui greitai tampa brangus.

**GuardPrompt pakeičia dešimtis ar šimtus prenumeratų vienu vidiniu DI varikliu**, todėl kaina vienam darbuotojui gerokai mažesnė, o naudojimas neribotas.

---

## 6. Organizacijoms reikia visiškos kontrolės savo DI infrastruktūrai
Debesų DI įrankiai neteikia:
- duomenų saugojimo kontrolės,
- prieigos kontrolės,
- audituojamumo,
- galimybės veikti offline,
- atkuriamo elgesio.

GuardPrompt yra visiškai on-premise:
- jokios telemetrijos,
- jokių išorinių API kvietimų,
- veikia izoliuotose (air-gapped) aplinkose,
- pilnas auditas ir valdysena.

---

## 7. Mažina žinių kliūtis („paklausk eksperto" problema)
Daug procesų priklauso nuo kelių pagrindinių ekspertų.  
Jiems nesant, darbo eiga sulėtėja.

**GuardPrompt demokratizuoja prieigą prie žinių**, užtikrindamas nuoseklius atsakymus be specialistų perkrovos.

---

## 8. Greitesnis naujų darbuotojų įvedimas ir mokymas
Nauji darbuotojai sunkiai randa reikiamus dokumentus ir supranta procesus.

Su GuardPrompt jie gali klausti:
- „Kaip mes tvarkome incidentų registravimą?"
- „Koks yra pirkimų procesas?"
- „Paaiškink skirtumą tarp šios politikos versijų."

Įvedimo laikas gerokai sutrumpėja.

---

## 9. Užtikrina nuoseklius atsakymus visoje organizacijoje
Be centrinio žinių variklio:
- kiekvienas taisykles interpretuoja skirtingai,
- cirkuliuoja pasenusios versijos,
- nesusipratimai kelia riziką.

GuardPrompt visada atsako naudodamas **oficialius, indeksuotus dokumentus**, užtikrindamas nuoseklumą.

---

## 10. Mažina klaidas kritiniuose procesuose
Klaidos dažnai atsiranda, kai:
- naudojamos pasenusios procedūrų versijos,
- darbuotojai praleidžia svarbias nuostatas,
- instrukcijos neaiškios.

GuardPrompt padaro aktualias taisykles aiškias ir lengvai patikrinamas.

---

## 11. Leidžia pilnatekstę paiešką skenuotuose PDF ir senuose dokumentuose
Tradicinė paieška nepavyksta su:
- skenuotais PDF,
- prastais OCR failais,
- lentelių duomenimis,
- daugiapuslapiais teksto ir vaizdų mišiniais.

GuardPrompt atkuria tekstą moderniu OCR ir analize, padarydamas archyvus ieškomus.

---

## 12. Panaikina rankinį dokumentų versijų palyginimą
Besikeičiančios politikos ir procedūros reikalauja atidaus skaitymo.

GuardPrompt gali atsakyti:
- „Kas pasikeitė nuo versijos 2.1?"
- „Apibendrink skirtumus tarp dviejų dokumentų."

Taupomos valandos rankinio darbo auditoriams, teisininkams ir atitikties skyriams.

---

## 13. Gerina komunikaciją tarp skyrių
Informacijos silosai sukelia vėlavimus ir nesusipratimus.

GuardPrompt teikia **vieną vieningą žinių bazę**, mažindamas trintį tarp komandų.

---

## 14. Mažina pasikartojančius klausimus vyresniems darbuotojams
Ekspertai dažnai gauna tuos pačius klausimus.

GuardPrompt tvarko šias užklausas, atlaisvindamas vyresnius darbuotojus vertingesnėms užduotims.

---

## 15. Veikia offline (izoliuotose aplinkose)
Būtina:
- valstybės institucijoms,
- gynybai ir teisėsaugai,
- kritinei infrastruktūrai,
- jautrioms IT sistemoms.

GuardPrompt nereikalauja interneto ryšio.

---

## 16. Palengvina auditą ir reguliacinius atsakymus
Auditoriams dažnai reikia greitai rasti konkrečius reikalavimus.

GuardPrompt leidžia momentinę semantinę paiešką per tūkstančius dokumentų.

---

## 17. Ateičiai atsparus ir integruojamas
Kadangi sistema modulinė, ji gali integruotis su:
- SharePoint,
- Confluence,
- dokumentų valdymo sistemomis,
- lokaliais katalogais,
- būsimais DI modeliais.

Tai daro GuardPrompt pritaikomą kintantiems poreikiams.

---

## 18. Programuotojai nuteka kodą ir klientų duomenis į DI įrankius
DI kodavimo asistentai (Claude Code, Copilot, Cursor) dabar nepakeičiami — ir
milžiniškas, nematomas nutekėjimo kelias. Kiekvienas prompt'as gali nunešti
klientų vardus, kredencialus, connection string'us, asmens kodus ir nuosavą kodą
tiesiai į debesų modelį.

**GuardPrompt suteikia Claude šliuzą**, stovintį tarp programuotojo įrankių ir
Anthropic, keičiantį jautrias reikšmes **grįžtamomis** žymėmis pakeliui pirmyn ir
atstatantį atgal — programuotojas mato tikrą kodą, Anthropic niekada, o žemėlapis
neišeina iš tavo infrastruktūros. Veikia su Claude Code CLI, VS Code plėtiniu ir
JetBrains IDE prenumeratos-passthrough arba bendro-API-rakto režimu (darbalaukio
aplikacija tik bendro-API-rakto režime), ir rašo **pseudonimizuotą kas-ką-siuntė
audito įrašą** (GDPR 30 str.). Tai skirtumas
tarp DI kodavimo įrankių uždraudimo ir saugaus jų priėmimo.

---

## 19. Dokumentai ir prompt'ai neša paslėptas atakas (prompt injekcija)
Įkeltas PDF ar įklijuotas tekstas gali turėti instrukcijas, nukreiptas į patį DI —
"ignoruok savo taisykles", paslėptą baltą-ant-balto tekstą, obfuskuotus
payload'us — pagrobiančias asistentą nutekinti duomenis ar netinkamai elgtis.

**GuardPrompt neutralizuoja prompt-injekciją** 4 sluoksnių detektoriumi (regex +
deobfuskacija, paslėptas tekstas, skripto anomalija, kontrastinis semantinis
vertinimas), veikiančiu *po* anonimizacijos ir keičiančiu priešiškus span'us į
`[PROTECTION]`, o ne atmetančiu dokumentą. Kenksmingos instrukcijos nukenksminamos;
teisėtas turinys vis tiek apdorojamas.

---

## 20. Jokio matomumo, jokio įrodymo, kad DI elgiasi gerai
"Ar anonimizatorius realiai veikia? Ar kas nutekа? Ar servisui tuoj baigsis
diskas, atmintis ar sertifikatas?" Dauguma self-hosted DI stekų negali atsakyti,
kol kažkas nesulūžta.

**GuardPrompt pristatomas su pilnu matomumu** — Zabbix stebėsenos steku,
skaitančiu vienodas `/metrics` iš kiekvieno serviso, su **preventyviais
trigeriais**, prognozuojančiais disko / sertifikato / connection-pool išsekimą
prieš įvykstant, ir **atminties-nutekėjimo bei kodo-kokybės trigeriais** (kylančio
dugno aptikimas, event-loop delsa, ryšių išsipūtimas, fail-closed aliarmai). Vienas
trigeris, `model_on_gpu=0`, būtų pagavęs realią greitaveikos regresiją kūrimo metu.
Gauni įrodymą, kad apsaugos veikia, ne tik pažadą.

---

## 21. Susitikimų protokolams reikia siųsti garsą į debesį

Susitikimų, skambučių ar diktavimų transkribavimas paprastai reiškia garso įkėlimą į
debesies kalbos-į-tekstą servisą — jautriausi neapdoroti duomenys (balsai, garsiai
ištarti vardai ir numeriai) palieka organizaciją **prieš** anonimizaciją, o
protokolą dar tenka rašyti ranka.

**GuardPrompt nauda:** susitikimai įrašomi ir transkribuojami **visiškai
on-premise** lokaliu lietuvišku kalbos-į-tekstą varikliu — garsas nepalieka mašinos.
Transkriptas anonimizuojamas kaip bet koks tekstas ir automatiškai paverčiamas
struktūruotu **susitikimo protokolu**, išsaugomu su prikabintu įrašu. Protokolas —
per kelias minutes, su **jokiu garso nutekėjimu**.

## 22. Interaktyvūs įrankiai ir terminalai nutekina komandų išvestį į DI

Kai vartotojai vykdo komandas ar įrankius, kurių išvestis grąžinama modeliui, ta
išvestis (failų turinys, hostai, kredencialai) gali pasiekti išorinį LLM nefiltruota.

**GuardPrompt nauda:** neprivalomas **izoliuotas terminalas** veikia su default-deny
egress ugniasiene ir tik-administratoriams privilegijų kėlimu, o jo išvestis
anonimizuojama tuo pačiu keliu kaip chat — net interaktyvūs įrankiai negali
nutekinti jautrių duomenų.

## Santraukos lentelė

| Problema | GuardPrompt nauda |
|--------|----------------------|
| Jautrių duomenų rizika | Lokalus anonimizavimas + kontroliuojamas išorinis naudojimas |
| Sunku rasti informaciją | Semantinė paieška ir DI atsakymai |
| Nėra vidinio DI asistento | Privatus RAG asistentas |
| Brangios individualios DI prenumeratos | Centralizuotas, ekonomiškas DI variklis |
| Reikia visiškos kontrolės | Visiškai on-prem, audituojamas, veikia offline |
| Žinių kliūtys | Demokratizuoja prieigą prie ekspertizės |
| Lėtas įvedimas | DI paaiškina dokumentus ir procesus |
| Versijų painiava | Automatinis palyginimas ir santraukos |
| Skenuotų PDF apribojimai | Modernus OCR ir ištraukimas |
| Skyrių nenuoseklumas | Vieninga žinių bazė |
| Audito spaudimas | Momentiniai atsakymai iš oficialių dokumentų |
| Programuotojai nuteka kodą/duomenis į DI įrankius | Claude šliuzas — grįžtamas maskavimas + kas-siuntė auditas |
| Kenksminga prompt injekcija dokumentuose | 4 sluoksnių injekcijų gynyba → `[PROTECTION]` |
| Susitikimų garsas siunčiamas į debesies transkripciją | On-prem transkripcija + auto-protokolas, jokio garso nutekėjimo |
| Įrankiai/terminalai nutekina komandų išvestį | Izoliuotas terminalas, išvestis anonimizuojama prieš bet kokį modelį |
| Jokio įrodymo, kad apsaugos veikia | Zabbix stebėsena su preventyviais ir nutekėjimo trigeriais |

---

# Parašyta aiškiai suprantamai:
- sprendimų priėmėjams,
- IT/saugumo komandoms,
- atitikties/teisės komandoms,
- techniniams skaitytojams.
