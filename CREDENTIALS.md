# GuardPrompt — kaip gauti raktus ir ID (.env)

Slaptažodžiai (Postgres, Grafana, SearXNG, sesijos, **Zabbix DB**, **Qdrant API
raktas**, Claude proxy `GP_TOKEN_SECRET`) **generuojami automatiškai** `install.sh`
/ `install.ps1`.
Žemiau — tik tie, kuriuos turi gauti pats iš išorinių sistemų. Sudėjus reikšmes į
`.env`, perleisk susijusį servisą: `docker compose up -d <servisas>`.

---

## 1. OpenWebUI API raktas — `OPEN_WEBUI_API_KEY`

kb-admin ir oikb naudoja jį valdymui (userių sąrašas, KB kūrimas, prieigos).

1. Prisijunk į OpenWebUI kaip **admin**.
2. **Settings → Account → API Keys** (API raktai turi būti **ENABLED**
   admin nustatymuose: Admin Settings → General → Enable API Key).
3. **Create new key** → nukopijuok `sk-...`.
4. `.env`: `OPEN_WEBUI_API_KEY=sk-...` → `docker compose up -d kb-admin`.

> Login į kb-admin API rakto **nereikia** — jis validuojamas per OpenWebUI
> admin el. paštą + slaptažodį. Pirmas užsiregistravęs OpenWebUI vartotojas = admin.

---

## 2. Chat LLM — OpenRouter (arba bet koks OpenAI-compat)

Pokalbių modelis jungiamas **OpenWebUI viduje**, ne per `.env`:

1. Gauk raktą: [openrouter.ai/keys](https://openrouter.ai/keys) → **Create Key** (`sk-or-...`).
2. OpenWebUI: **Admin Settings → Connections → OpenAI API**.
   - Base URL: `https://openrouter.ai/api/v1`
   - API Key: `sk-or-...`
3. Išsaugok — modeliai atsiras pokalbių pasirinkime.

STT (balsas → tekstas) apdorojamas VIETINIU `gp-transcribe` varikliu (lietuviškas
svogunas modelis, EN atpažįsta automatiškai — garsas nepalieka mašinos). OpenWebUI
nukreipiamas automatiškai per `install.sh` / `install.ps1` (raktas `GP_STT_API_KEYS`).

Vietinis vaizdų modelis (docling paveikslėlių aprašymui) — `ollama` (žr. `.env`
`LM_STUDIO_URL`/`LM_MODEL`), raktų nereikia.

---

## 3. Confluence — `CONFLUENCE_URL`, `CONFLUENCE_USER`, `CONFLUENCE_TOKEN`

Atlassian Cloud API tokenas:

1. `CONFLUENCE_URL` = tavo Atlassian svetainė, pvz. `https://imone.atlassian.net`.
2. `CONFLUENCE_USER` = tavo Atlassian el. paštas.
3. Tokenas: [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
   → **Create API token** → nukopijuok → `CONFLUENCE_TOKEN`.

> Šaltinį pulte nurodai per **space ID** (nekintantis). Tą suranda pats pultas.

---

## 4. Jira — `JIRA_URL`, `JIRA_USER`, `JIRA_TOKEN`

Ta pati Atlassian paskyra kaip Confluence:

1. `JIRA_URL` = `https://imone.atlassian.net` (dažniausiai tas pats).
2. `JIRA_USER` = tavo Atlassian el. paštas.
3. `JIRA_TOKEN` = **tas pats** API tokenas kaip #3 (arba sukurk atskirą).

> Šaltinis pulte nurodomas per **project ID** (nekintantis; KEY keičiasi, ID ne).

---

## 5. SharePoint — `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET`

Azure app registration (Microsoft Graph, app-only / client-credentials):

1. **Tenant ID:** [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID**
   → **Overview** → laukas **Tenant ID** → `SHAREPOINT_TENANT_ID`.
2. **App registration:** Entra ID → **App registrations** → **New registration**
   (pvz. „GuardPrompt KB Sync", Single tenant) → **Register**.
   - Overview → **Application (client) ID** → `SHAREPOINT_CLIENT_ID`.
3. **Secret:** ta app → **Certificates & secrets** → **New client secret** → **Add**
   → nukopijuok **Value** (ne Secret ID!) **iškart** → `SHAREPOINT_CLIENT_SECRET`.
4. **Teisės:** app → **API permissions** → **Add a permission** → **Microsoft Graph**
   → **Application permissions** → `Sites.Read.All` (jei reikės failų — `Files.Read.All`)
   → **Add** → **Grant admin consent** (reikia Azure Global/App admin — dažniausia kliūtis).

Be admin consent skaitant SharePoint bus 403.

---

## 6. Mašinos licencijos raktas — `anonymizer/machine_key.txt`

Ne `.env`, o failas. **Generuojamas automatiškai per install** (uuid, per mašiną).
**Nekopijuojamas per publish** — kiekviena mašina turi savo.

1. Po `install.sh` failas jau yra. Peržiūrėk raktą:
   `curl http://localhost:8005/api/reginfo` (arba `cat anonymizer/machine_key.txt`).
2. Nusiųsk raktą GuardPrompt registracijai (`info@guardprompt.lt` / Telegram `@GuardPrompt`).
3. Įregistravus — licencijos patikra grąžina `200 OK`, veiksmai atsirakina.

> Jei matai `403 Forbidden` + `license: HARD_FAIL` — raktas neregistruotas.

---

## 7. LDAP / Active Directory (OpenWebUI login — neprivaloma)

Įjungiama tik jei reikia AD prisijungimo. `.env`:

- `ENABLE_LDAP=true`
- `LDAP_SERVER_HOST` = AD serveris (pvz. `dc.imone.lt`), `LDAP_SERVER_PORT=389` (LDAPS `636`)
- `LDAP_APP_DN` = servisinės paskyros bind DN, `LDAP_APP_PASSWORD` = jos slaptažodis
- `LDAP_SEARCH_BASE` = kur ieškoti vartotojų (pvz. `DC=imone,DC=lt`)
- `LDAP_ATTRIBUTE_FOR_USERNAME=sAMAccountName`, `LDAP_ATTRIBUTE_FOR_MAIL=mail`

kb-admin atskiro LDAP nereikia — jis autentifikuoja per OpenWebUI (jei OpenWebUI
turi LDAP, tai jau eina per AD).

---

## 8. Claude proxy — `GP_UPSTREAM_API_KEY` (tik B režimas, neprivaloma)

Claude proxy pagal nutylėjimą veikia **A režimu** (prenumeratos pass-through) —
raktų gauti nereikia, kiekvienas programuotojas naudoja savo claude.ai login.

Raktas reikalingas **tik jei jungi B režimą** (bendras API raktas žmonėms be
prenumeratos / centrinis billing):

1. `GP_UPSTREAM_API_KEY` = tikras Anthropic **API** raktas iš
   [console.anthropic.com](https://console.anthropic.com) → **API Keys** → `sk-ant-...`.
   Tai per-token billing produktas, **kitas** nei Pro/Team chat prenumerata.
2. `GP_PROXY_KEYS` = per-programuotojo gate žymės (`gpk_...`) — **generuok stiprias
   atsitiktines**, po vieną žmogui. `.env`: `docker compose up -d gp-claude-proxy`.

> Detalus režimų paaiškinimas, saugumo niuansai ir testavimas —
> [GP-CLAUDE-PROXY.lt.md](GP-CLAUDE-PROXY.lt.md).

---

## 9. Zabbix stebėsena — numatytas admin slaptažodis

Zabbix DB slaptažodis generuojamas automatiškai (`.env` `ZABBIX_DB_PASSWORD`).
**Bet Zabbix web admin lieka numatytas `Admin` / `zabbix`** — po diegimo
**būtinai pakeisk** (Zabbix UI: User settings → Change password). Žr. [MONITORING.lt.md](MONITORING.lt.md).
