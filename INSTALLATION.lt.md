> 🌐 **Kalba / Language:** **Lietuvių** · [English](INSTALLATION.md)

# GuardPrompt — diegimo ir naudojimo vadovas

Šis dokumentas paaiškina, kaip lokaliai įdiegti, sukonfigūruoti ir paleisti GuardPrompt.
Tinka tiek CPU, tiek GPU aplinkoms.

Architektūra (visi konteineriai, portai, priklausomybės): žr. [ARCHITECTURE.lt.md](ARCHITECTURE.lt.md)

GuardPrompt teikia:
- DI dokumentų asistentą (OpenWebUI)
- On-prem anonimizavimo variklį (Anonymizer)
- gliner (on-prem NER GDPR 9/10 str. specialioms kategorijoms; kviečia Anonymizer)
- Dokumentų ingestijos ir OCR liniją (Docling)
- RAG žinių bazę (Qdrant)
- Vidinį API vartų tarpininką (GuardProxy)
- KB Admin pultą — prijungti Confluence/Jira/SharePoint į OpenWebUI žinių bazes (kb-admin)
- LLM backend — per OpenWebUI (OpenRouter arba bet koks OpenAI-suderinamas API); lokalus vision modelis per Ollama (Ubuntu) arba LM Studio (Windows, pasirinktinai)

---

## 1. Sistemos reikalavimai

**Operacinė sistema:**
- Windows 10/11 (Docker Desktop), arba
- Linux serveris (rekomenduojama Ubuntu 22.04)

**Aparatūra (GPU versija):**
- NVIDIA GPU su CUDA palaikymu (rekomenduojama 6GB+ VRAM)
- Atnaujintos NVIDIA tvarkyklės + CUDA runtime

**Disko vieta:** min. 100 GB laisvos.

---

## 2. Programinės įrangos reikalavimai

1. **Docker Desktop** — https://www.docker.com/products/docker-desktop/
   Įsitikinkite, kad įjungtas „Use WSL2 backend".
2. **LLM backend** (OpenRouter / Ollama / LM Studio — žr. 7 skyrių).
   OpenWebUI chat LLM pasiekia per OpenRouter ar bet kokį OpenAI-suderinamą API.
   Ubuntu lokalus vision modelis veikia per Ollama; LM Studio — tik Windows.

---

## 3. Kodo gavimas

**Rekomenduojama — klonuoti repozitoriją:**

```bash
# Linux
git clone https://github.com/guardprompt/GuardPrompt.git /opt/guardprompt
cd /opt/guardprompt
```

```powershell
# Windows (PowerShell)
git clone https://github.com/guardprompt/GuardPrompt.git C:\GuardPrompt
cd C:\GuardPrompt
```

**Alternatyva** — jei gavote ZIP paketą, išpakuokite jį į pasirinktą aplanką, pvz.
`C:\GuardPrompt` arba `/opt/guardprompt`.

Aplanke turi būti: `docker-compose.yml`, `install.sh` / `install.ps1` (diegimo
skriptas), `guardproxy/`, `anonymizer/`, `gliner/`, `searxng/`, `docling_api.py`,
`.env.example` (šablonas).

### Greičiausias kelias

Paleiskite diegimo skriptą — jis atlieka 4 ir 5 skyrių veiksmus už jus:

```bash
# Linux
chmod +x install.sh && ./install.sh
```
```powershell
# Windows
.\install.ps1
```

Skriptas sugeneruoja `.env` su naujais slaptažodžiais, sukuria mašinos licencijos
raktą, subuildina ir paleidžia visus konteinerius bei įdiegia GuardPrompt OpenWebUI
funkciją. Pusiaukelėje paprašo susikurti administratoriaus paskyrą
`http://localhost:8080` (pirmoji registracija tampa administratoriumi).

4 ir 5 skyriai aprašo tuos pačius veiksmus rankiniu būdu — naudinga izoliuotiems
(air-gapped) ar pritaikytiems diegimams.

### Atnaujinimas vėliau

Leidimai publikuojami **force-push** būdu, todėl `git pull` neveiks (istorijos
išsiskiria). Atstatykite į publikuotą būseną:

```bash
git fetch origin && git reset --hard origin/main
docker compose up -d --build
```

`--build` svarbu: be jo liktų veikti seni image'ai. `.env`, `machine_key.txt` ir
prekės ženklo failai yra gitignore'inti, tad atstatymas jų nepaliečia.

---

## 4. Aplinkos paruošimas (.env failas)

Paprasčiausias būdas — paleisti diegimo skriptą, kuris sugeneruoja `.env` su unikaliais
slaptažodžiais:
- Linux: `bash install.sh`
- Windows: `.\install.ps1`

Išoriniai raktai/ID (OpenWebUI API, OpenRouter, Confluence, Jira, SharePoint, LDAP, mašinos raktas): žr. [CREDENTIALS.md](CREDENTIALS.md)

GDPR ir ES DI akto atitiktis (straipsnis po straipsnio): žr. [COMPLIANCE.lt.md](COMPLIANCE.lt.md)

---

## 5. Sistemos paleidimas

```
docker compose up -d
```

Bus paleista: GuardProxy, OpenWebUI, Anonymizer, gliner, Docling, Qdrant, PostgreSQL,
SearXNG, KB Admin (kb-admin), Ollama (Ubuntu), uploads-cleaner, Claude proxy
(gp-claude-proxy), Zabbix stebėsena (server + web + postgres) ir eksporteriai.

Patikrinti veikiančius konteinerius: `docker ps`

---

## 6. Prieiga prie sistemos

Paleidus, naršyklėje:
- `http://localhost:9099` → GuardProxy (pagrindinis įėjimas)
- `http://localhost:9099/ui` → OpenWebUI sąsaja
- `http://localhost:8005` → Anonymizer API
- `http://localhost:8777` → Docling OCR serveris
- `http://localhost:8006` → Claude proxy (programuotojų įrankiai — žr. GP-CLAUDE-PROXY.lt.md)
- `http://localhost:8880` → Zabbix stebėsena (prisijungimas Admin / zabbix — PAKEISK; žr. MONITORING.lt.md)

---

## 7. LLM backend nustatymas (OpenRouter / Ollama / LM Studio)

Chat LLM (numatytoji): konfigūruokite OpenWebUI viduje (Admin > Settings > Connections) —
OpenRouter arba bet koks OpenAI-suderinamas API. Dokumentų vaizdų aprašymai naudoja lokalų
vision modelį: Ubuntu paleidžia Ollama in-stack (`install.sh` automatiškai parsisiunčia modelį);
Windows galite naudoti LM Studio:

1. Paleiskite LM Studio
2. Įkelkite modelį (pvz. `google/gemma-3-4b`)
3. Įjunkite „Local Server" režimą (tik Windows/LM Studio), paprastai:
   `http://localhost:1234/v1/chat/completions`

Endpoint'as ir modelis nustatomi `.env` (`LM_STUDIO_URL`, `LM_MODEL`). Ubuntu `install.sh`
juos automatiškai nustato į in-stack Ollama.

---

## 8. Bandomosios licencijos aktyvavimas

Atidarykite anonimizatoriaus registracijos info: `http://localhost:8005/api/reginfo`

Pamatysite: Host ID (auto), Host IP (auto), Data Till (tuščia), Admin Email (įvesti),
Admin Pass (įvesti), Users Count.

Nusiųskite šią informaciją GuardPrompt palaikymui:
- El. paštas: info@guardprompt.lt
- Telegram: @GuardPrompt

Po aktyvavimo prasideda 30 dienų bandomasis laikotarpis, visos funkcijos atrakintos.
Detaliau: [LICENSING_INFO.lt.md](LICENSING_INFO.lt.md)

---

## 9. Sustabdymas / paleidimas iš naujo

- Sustabdyti visus servisus: `docker compose down`
- Paleisti iš naujo: `docker compose restart`
- Atnaujinti images (rankinis — versijos pinuotos): pakeiskite tag'ą `docker-compose.yml`,
  tada `docker compose pull && docker compose up -d --remove-orphans`

---

## 10. Trikčių šalinimas

1. **Portai užimti** — uždarykite konfliktuojančias programas arba keiskite portus `docker-compose.yml`.
2. **GPU neaptiktas** — įsitikinkite, kad įdiegtos NVIDIA tvarkyklės; įjunkite „Use GPU" Docker Desktop Settings > Resources > GPU.
3. **OpenWebUI nepasileidžia** — ištrinkite cache aplanką `./cache/`.
4. **Prasta OCR kokybė** — įsitikinkite, kad aktyvus Tesseract arba Docling-Serve GPU.
5. **Licencija nepriimama** — patikrinkite mašinos laikrodį ir kad `.env` reikšmės atitinka registracijos info.

---

## 11. Kontaktai ir palaikymas

- El. paštas: info@guardprompt.lt
- Telegram: @GuardPrompt

Komercinės licencijos apima: diegimo pagalbą, prioritetinius atnaujinimus, įmonių masto
diegimo pagalbą.

---

**Ačiū, kad pasirinkote GuardPrompt!**
