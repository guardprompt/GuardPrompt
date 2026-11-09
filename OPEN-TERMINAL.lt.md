> 🌐 **Kalba / Language:** **Lietuvių** · [English](OPEN-TERMINAL.md)

# Open Terminal — AI agento darbo vieta ir prezentacijų studija

Suteikia OpenWebUI pokalbio modeliui **tikrą, izoliuotą Linux terminalą**. Užuot
aprašinėjęs ar imitavęs darbą, agentas kuria **realius failus** — dokumentus,
skaičiuokles, PDF ir dailias, brand'intas **prezentacijas** — kurie atsiranda failų
naršyklėje (*Rinkmenose*), paruošti atsisiųsti. Viskas, ką modelis siunčia, pirma
praeina GuardPrompt anonimizatorių, lygiai kaip įprastas pokalbis.

```
OpenWebUI pokalbis ─ run_command ─► open-terminal-proxy ─► open-terminal (sandbox)
      │  (modelio srautas anonim.                               /home/user
      │   per gp-pipeline)                                     realūs failai ↑
      └─────────────────── failų naršyklė (Rinkmenos) ◄────────────────────┘
```

---

## 1. Kas tai

- Pagrindas — **open-webui/open-terminal** (MIT). Sandbox **pats jokių LLM
  kvietimų nedaro** — jį valdo pokalbio modelis per `run_command` įrankį — tad visas
  modelio srautas lieka viename taške per OpenWebUI → `gp-pipeline` (anonimizuotas,
  įskaitant įrankių output).
- **Custom image** build metu įkepa visą biuro/PDF/duomenų įrankių rinkinį, kad
  veiktų neprisijungus su įjungtu egress firewall: LibreOffice (docx/pptx/xlsx →
  PDF), pandoc ir Python bibliotekos (`python-docx`, `openpyxl`, `xlsxwriter`,
  `reportlab`, `weasyprint`, `pandas`, `numpy`, `matplotlib`, `Pillow`, …) plius
  žemiau aprašyti deck įrankiai.
- Failai rašomi į `/home/user`, matomi *Rinkmenose*.

## 2. Architektūra ir saugumas

- **Rolėmis paremtas proxy** (`open-terminal-proxy`) stovi tarp OpenWebUI ir
  sandbox; OpenWebUI registruotas prieš proxy, ne prieš sandbox tiesiogiai. Jis
  perduoda autentifikuotą vartotojo tapatybę (`X-User-Id`) ir taiko **tik-adminams
  diegimo/privilegijuotas komandas**: ne-admino `sudo`/`apt`/`pip install`/`npm
  install` nevykdoma — pakeičiama į politikos pranešimą, kurį modelis perduoda
  („diegti gali tik administratorius"). Adminai praeina.
- **Sandbox izoliacija** = vienkartinis konteineris + jokių host mount'ų +
  **egress firewall** (pagal nutylėjimą blokuoja viską, papildomai galimas domenų
  whitelist) + jokio `docker.sock`, loopback bind, 4 CPU / 8 GB. (Tai ne
  konteinerio vidaus kalėjimas — saugumas iš izoliacijos + kontroliuojamo egress.)
- **Sinchroninis `run_command`.** Proxy blokuoja, kol komanda baigiasi, ir grąžina
  visą output vienu atsakymu, tad viena komanda kainuoja **vieną** modelio
  tool-call'ą, ne start-tada-poll ciklą. Mažiau apsikeitimų = greičiau ir, svarbu,
  daugiapakopis darbas nebeperžengia ribos, ties kuria kai kurie modeliai sugadina
  savo tool-calling būseną (žr. Trikčių šalinimą).
- **Darbo katalogas seka vartotoją.** Kai developeris failų naršyklėje įeina į
  katalogą, proxy jį įsimena (kiekvienam pokalbiui) ir modelio komandas vykdo
  **ten**, tad sugeneruoti failai atsiranda kataloge, į kurį vartotojas žiūri. Kode
  naudok paprastus reliatyvius failų vardus.

## 3. Prezentacijų studija — `gpdeck` ir `gpweb`

Grynas `python-pptx` kuria negražias tuščias baltas skaidres. Dvi įkeptos
bibliotekos vietoj to daro profesionalias, **brand'intas** skaidres:

| Biblioteka | Rezultatas | Kada naudoti |
|---|---|---|
| **`gpdeck`** | redaguojamas **.pptx** (+ `.pdf` per `to_pdf()`) | kai reikia PowerPoint failo redaguoti |
| **`gpweb`** | dizainerio **.html** (`save_html()`) arba **.pdf** (`save()`) | kai nori įspūdingo, neredaguojamo HTML/PDF |

Abi dalinasi tuo pačiu brand'u ir funkcijomis:

- **Brand** — spalvos, šriftai ir logo iš `brand.json` (organizacijos tapatybė).
  Turi generic numatytą; tikras kliento brand'as kraunamas vykdymo metu iš sandbox
  volume (`/home/user/.gpbrand/`), niekada neįkepamas į image ir necommit'inamas į
  viešą repo.
- **Temos** — `corporate` (numatyta), `dark`, `bold`, `minimal`, `emerald`
  (`gpdeck.Deck("vardas", theme="dark")`).
- **Skaidrių tipai** — title, section, bullets, two_column/columns, image,
  image_full, quote, closing, plius `kpi`, `agenda`, `comparison`, `timeline`,
  `table`, `icon_grid`.
- **Grafikai** — offline, brand spalvomis: `chart_bar`, `chart_line`, `chart_pie`.
- **Ikonos** — brand spalvos Lucide rinkinys (`gpdeck.icons_available()`).
- **AI paveikslai** — `gen_image("prompt")` sugeneruoja iliustraciją per proxy
  `/genimage` endpoint'ą (OpenRouter raktas lieka proxy, niekada ne sandbox'e, kur
  vartotojas galėtų jį perskaityti).
- **Oficialus brand kit** — jei sinchronizuota iš SharePoint, `gpdeck.kit_images()`
  / `gpdeck.kit_templates()` pateikia oficialias nuotraukas ir PPT šablonus (žr. §7).
- **„AI GENERATED" etiketė** — kiekviena skaidrė automatiškai pažymima viršuje
  dešinėje (skaidrumui). Nešalink jos.

```python
import gpweb
w = gpweb.Web("dokumentas", theme="corporate")
w.cover("Pavadinimas", "Paantraštė")
w.bullets("Antraštė", ["Punktas vienas", "Punktas du", "Punktas trys"])
w.columns("Palyginimas", "Kairė", ["a", "b"], "Dešinė", ["c", "d"])
w.closing("Ačiū!", "www.pavyzdys.lt")
w.save_html()      # -> dokumentas.html   (savarankiškas, atsidaro naršyklėj)
# w.save()         # -> dokumentas.pdf
```

```python
import gpdeck
d = gpdeck.Deck("pristatymas", theme="corporate")
d.title("Pavadinimas", "Paantraštė")
d.kpi("Rodikliai", [("190", "2024"), ("45", "paslaugos")])
chart = d.chart_bar("Augimas", {"2022": 120, "2023": 145, "2024": 190})
d.image("Augimas", chart, caption="Kasmet")
d.image_full(d.gen_image("modern flat corporate illustration, blue"), "Skaitmena", "Greita ir saugu")
d.closing("Ačiū!", "www.pavyzdys.lt")
d.save()           # -> pristatymas.pptx
d.to_pdf()         # -> pristatymas.pdf
```

## 4. Paruošimas

1. **Modelio galimybės** (OpenWebUI → modelis): **Terminal ĮJUNGTA**, **Code
   Interpreter IŠJUNGTA** (jo pyodide variklis pasisavina kodo vykdymą ir nepasiekia
   shell'o), **Builtin Tools IŠJUNGTA** (kitaip modelis renkasi „rašyk note / kurk
   task" nuorodą vietoj failo). Terminal = **Open Terminal**.
2. **System prompt** — įklijuok `open-terminal/SYSTEM-PROMPT.md` į modelio *System
   Prompt* lauką. Jis nukreipia modelį į `gpdeck`/`gpweb`, draudžia imituoti darbą
   ir reikalauja `ls` patikros po kiekvieno failo.
3. **Modelio pasirinkimas** — agentui reikia **patikimo daugiapakopio
   tool-calling**. Rinkis **Claude Haiku/Sonnet** (per [GuardPrompt Claude
   proxy](GP-CLAUDE-PROXY.lt.md)) arba **Gemini 2.5 Flash**. Venk **Gemini 3.x Flash
   / Flash-Lite** agentiniam darbui (žr. Trikčių šalinimą).

## 5. Darbo katalogas

Kiekvienas `run_command` pradeda naują shell'ą (būsena tarp komandų neišsaugoma),
bet proxy įšvirkščia katalogą, į kurį vartotojas naršo, kaip darbo katalogą, tad:

- Naudok **reliatyvius failų vardus** (`gpweb.Web("ataskaita")`) — failas atsiras
  vartotojo dabartiniame kataloge.
- Modelis **neturi** kurti savų pakatalogių ar naudoti `cd`; dirba dabartiniame
  kataloge ir `ls -la` patvirtina kiekvieną failą.

## 6. Trikčių šalinimas

| Simptomas | Priežastis | Sprendimas |
|---|---|---|
| Provideris grąžina **`400 Corrupted thought signature`** | **Gemini 3.x Flash/Flash-Lite** daugiapakopio tool-calling bug'as — po kelių tool-call'ų nustoja generuoti teisingą `thought_signature` | Pakeisk agento modelį į **Gemini 2.5 Flash** arba **Claude Haiku**. Sinchroninis `run_command` (§2) mažina apsikeitimus ir padeda, bet garantuotas gydymas — modelio keitimas. |
| Modelis **aprašo** darbą / rašo „note" vietoj failo | Paliktas Code Interpreter arba Builtin Tools, arba `run_command` neatpažįstamas | Nustatyk galimybes kaip §4; patvirtink, kad terminalas parinktas pokalbio composeryje. |
| Failo nėra *Rinkmenose* arba jie išsibarstę po katalogus | modelis naudojo absoliučius `/home/user` kelius ar savo pakatalogį, prieštaraujant darbo katalogo sinchronizacijai | Naudok reliatyvius vardus; sistema nukreipia komandą į vartotojo katalogą. |
| Negražios tuščios baltos skaidrės | naudotas grynas `python-pptx` | Naudok `gpdeck`/`gpweb` (system prompt to reikalauja). |
| Prašo HTML, gavo PDF | `gpweb.save()` rašo PDF | Naudok `save_html()` savarankiškam `.html`. |

## 7. Kliento brand'as ir brand kit

- **Saugumo riba.** Generic numatytieji (`brand.default.json`, deck kodas,
  AI-GENERATED etiketė, ikonų rinkinys) yra sekami ir publikuotini. **Tikras kliento
  brand'as** (`brand.json`, logotipai) yra git-ignored ir gyvena tik sandbox
  **volume** `/home/user/.gpbrand/` — niekada nepatenka į image, viešą repo, žinių
  bazę ar anonimizatorių.
- **Brand-kit sinchronizacija (tik adminams).** Neprivalomas darbas atspindi
  SharePoint dokumentų biblioteką (oficialius logo / PPT šablonus / nuotraukas) į
  volume per Microsoft Graph — **ne** į žinių bazę ir **ne** per anonimizatorių
  (brand tapatybė yra vieša įmonės medžiaga; anonimizavimas ją sugadintų).
  Konfigūruojama `.env` / KB Admin App, paleidžia tik OpenWebUI adminai.
