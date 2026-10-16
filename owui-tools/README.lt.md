# OWUI Tools — Office failų kūrimas/redagavimas (B dalis)

## edit-office-files.py

OpenWebUI įrankis Office failams **skaityti / redaguoti / kurti** (.xlsx, .docx, .pptx)
chate. Šaltinis: [sergiofspedro/openwebui-edit-office-files](https://github.com/sergiofspedro/openwebui-edit-office-files)
v4.0.5, **sutvirtintas GuardPrompt** (žr. žemiau).

### GuardPrompt saugumo pakeitimai (nuo originalo)
1. **Išmesta** `google-api-python-client, google-auth` iš `requirements` — nenaudojami,
   nereikia išorinio cloud egzfiltracijos vektoriaus.
2. **Išjungtas visas išorinis tinklas pagal nutylėjimą.** `_validate_outbound_url` grąžina
   klaidą, kol `OFFICE_TOOL_ALLOW_EGRESS` nenustatytas `true`. Tai neutralizuoja VISAS
   prompt-injection egzfiltracijos funkcijas vienoje vietoje:
   - `import_from_url` (parsisiųsti iš bet kokio URL)
   - `import_from_api` (bet koks API URL)
   - `webhook_trigger` (POST į bet kokį URL)
   - `upload_to_drive` (Google Drive) — atskiras guard
3. Originalūs SSRF apsaugos (loopback/private/file blokavimas) lieka — jei kada įjungsi
   egzfiltraciją, jos vis tiek galioja.
4. **Išjungtos aplankų operacijos** (`bulk_folder_ops`, `file_search`) — jos išvardija/
   perskaito VISĄ uploads aplanką (visų vartotojų failus → privatumo leak + apsunkina
   paprastą redagavimą). Default OFF; `OFFICE_TOOL_ALLOW_FOLDER_OPS=true` įjungia.
   Tool'as dirba tik su PRISEGTU failu (pagal file_id).

### Download nuoroda (kad būtų domenas, ne localhost:3000)
Workspace > Tools > „Office Files" > **Valves** → `base_url` = `https://di.regitra.lt`.
(arba nustatyk OWUI `WEBUI_URL=https://di.regitra.lt`.)

**On-prem + anonimizuotai sistemai — palik `OFFICE_TOOL_ALLOW_EGRESS` NEnustatytą (off).**

### Diegimas (OWUI naršyklės sąsajoje, ne konteineris)
1. OWUI → **Workspace > Tools** (arba Admin Panel > Tools) → **„+"** (naujas)
2. Įklijuok VISĄ `edit-office-files.py` turinį → **Save**
3. Priklausomybės (`openpyxl, python-docx, python-pptx, ...`): OWUI bando `pip install`
   iš `requirements` antraštės automatiškai. Jei jūsų OWUI tai riboja → įkepti į OWUI
   image (pasakyk — pridėsiu vieną RUN pip eilutę compose'e)
4. **Įjunk** įrankį modeliui/vartotojams (Tools sąraše arba per Model settings)

### Testas (kartu su KB — svarbu)
- Prisegk Excel → „perskaityk 2 lapą" → įrankis grąžina turinį
- „sukurk lentelę su stulpeliais A,B,C" → sugeneruoja .xlsx
- **Patikrink KB:** mūsų KB reikalauja **Legacy function calling**. Įjungus įrankį,
  patikrink, kad KB atsakymai NEniužta (jei kertasi — įrankį tik ne-KB modeliams)

### Anonimizacija
- Įrankio išvestis eina per gp-pipeline (`role==tool` maskuojamas) → skaityti/kurti
  privatumas OK
- Redaguoti **esamą su PII** — jautru (AI matys `GP_` kodus); daryti per atverčiamą
  kelią, atskira fazė (žr. `GP-OFFICE-PLAN.lt.md`)
