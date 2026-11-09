# GuardPrompt Office Add-in

Anonimizuojantis AI asistentas **Word** ir **Outlook** viduje (vėliau Teams + SharePoint).
Tas pats principas kaip `browser-extension/`: kalbasi tik su jūsų OWUI, turinys
anonimizuojamas per `gp-pipeline` prieš išorinį LLM. Skirtumas — tekstą ima/rašo per
**Office.js** (dokumentas / laiškas), o ne per naršyklės DOM.

## Kaip veikia (etapas 1A — jau čia)

Task pane su mygtukais: **anonimizuok pažymėtą / perrašyk / paruošk atsakymą / apibendrink**.
Office.js paima pažymėtą tekstą → OWUI `/api/chat/completions` (gp-pipeline anonimizuoja)
→ atsakymas įrašomas atgal (Word: pakeičia pažymėjimą; Outlook: atsakymo juodraštis).

## Auth — svarbiausia sąlyga

Add-in **turi būti serveruojamas iš to paties OWUI origin** (pvz. `https://chat.regitra.lt/officeaddin/`).
Tada `/api` kvietimai yra same-origin ir **OWUI sesijos slapukas keliauja automatiškai**
(`credentials:'include'`) — jokio token valdymo, kaip side panel. Serveravus iš kito
domeno slapukas NEsiunčiamas.

## Hostinimas (guardproxy)

1. Sudėk statinius failus po guardproxy, kad atsidarytų per `https://__HOST__/officeaddin/`.
   Nginx pavyzdys (guardproxy `nginx.conf`):
   ```nginx
   location /officeaddin/ {
     alias /usr/share/nginx/officeaddin/;
     add_header Cache-Control "no-cache";
   }
   ```
   (arba bind-mount `./office-addin` į tą kelią compose'e.)
2. Sugeneruok `env-config.js` iš `.env` (kaip extension). Paprasčiausia — palik
   `GP_OWUI_BASE=""` (same-origin) ir nustatyk `GP_MODEL_FILTER` į savo modelio id.
3. Įdėk ikonas į `office-addin/assets/` (`icon-16/32/64/80/128.png`). Gali panaudoti
   esamą `guardproxy/GuardPrompt.png` sumažintą.

## Prieš naudojant — pakeisk manifestuose

- `__HOST__` → jūsų OWUI hostas (HTTPS, tas pats kaip OWUI).
- `__ADDIN_GUID__` → šviežias GUID (Word ir Outlook — **skirtingi**):
  ```powershell
  [guid]::NewGuid(); [guid]::NewGuid()
  ```

## Testavimas (sideload, be admin)

**Word (Windows):** Insert → My Add-ins → Upload My Add-in → `manifest.word.xml`.
Arba per Shared Folder katalogo sideload (Trust Center → Trusted Add-in Catalogs).

**Outlook (web/naujas):** Settings → Mail → nustatymuose „Manage add-ins“ / „Get Add-ins“
→ My add-ins → Add a custom add-in → From file → `manifest.outlook.xml`.

Validacija: [manifest validator](https://learn.microsoft.com/office/dev/add-ins/testing/troubleshoot-manifest)
arba `npx office-addin-manifest validate manifest.word.xml`.

## Diegimas visai organizacijai (be AppSource)

Microsoft 365 Admin Center → **Settings → Integrated Apps → Upload custom apps** →
įkelk manifestą, priskirk grupei/visiems. Reikia **Exchange admin**. Vartotojo Word/Outlook
atsiranda „GuardPrompt“ mygtukas ribbon'e.

---

## Etapas 1B — „naudok visus mano dokumentus“ (Graph)

Kodas eina į backend (atskiras endpoint / `gp-m365`), NE į šį task pane. Ciklas:
`Graph Search (delegated) → injection-scan → anonimizacija → reranker → 1 LLM call →
de-anon`. Pigus kelias: nemokami įrankiai atrenka, išorinis LLM iškviečiamas vieną kartą.

### Ką TURITE padaryti pirma — Entra app registracija

Be šito 1B netestuojamas. Azure Portal → **Microsoft Entra ID → App registrations → New**:

1. **Name:** `GuardPrompt M365`. Supported accounts: *Single tenant*.
2. **Authentication:** pridėk platformą *Single-page application*, Redirect URI:
   `https://__HOST__/officeaddin/auth.html` (Office SSO — vėliau papildysim).
3. **API permissions → Microsoft Graph → Delegated** (mažiausi reikalingi):
   - `User.Read` (bazinis)
   - `Mail.Read` — piliečių susirašinėjimas
   - `Files.Read.All` — OneDrive/SharePoint failai vartotojo teisėmis
   - `Sites.Read.All` — SharePoint svetainės
   - (pagal poreikį) `Chat.Read` / `ChannelMessage.Read.All` — Teams
   → **Grant admin consent**.
4. Pasižymėk **Application (client) ID** ir **Directory (tenant) ID** — jų reikės backend'ui.
5. **NENAUDOK Application permissions** personaliniams duomenims — tik **Delegated**
   (add-in veikia kaip vartotojas, mato tik ką jis pats mato).

Kai turėsit client/tenant ID + admin consent — pranešk, prijungsim Graph endpoint'ą
proxy pusėje ir įjungsim „naudok visus dokumentus“.
