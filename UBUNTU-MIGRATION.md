# GuardPrompt migracija → Ubuntu Desktop + native Docker + GPU

Tikslas: perkelti dabartinį Windows 11 + Docker Desktop stacką į galingą Ubuntu
Desktop mašiną su pilnu NVIDIA GPU našumu, išlaikant grafinį patogumą
(Portainer + VS Code native), be Docker Desktop.

> ⚠️ SVARBIAUSIA: Ubuntu'e **nediek „Docker Desktop for Linux"** GPU darbui —
> jis sukasi savo VM (KVM) ir NVIDIA GPU į container'ius **nepralenda**.
> Diek **native Docker Engine (docker-ce)** + **nvidia-container-toolkit**.

---

## 0. Prieš pradedant

- Pasidaryk dabartinio stacko backup: `docker-compose.yml`, `.env`, visi
  bind-mount folderiai (`anonymizer/`, `guardproxy/`, `pipelines/`,
  `gp-transcribe/`, `dbtrigger/`, `uploads-cleaner/`, `searxng/`, `gp-claude-proxy/`,
  `gliner/`, `kb-admin/`, `monitoring/`, `warmup/`) ir Docker volume'ai
  (`pgdata`, `qdrant_storage`, `open-webui-data`, `zabbix_pgdata`).
- Volume backup būdas: `docker run --rm -v pgdata:/v -v ${PWD}:/b alpine tar czf /b/pgdata.tgz -C /v .`
  (kiekvienam volume atskirai).

---

## 1. Ubuntu Desktop diegimas

- Atsisiųsk Ubuntu Desktop **24.04 LTS**: https://ubuntu.com/download/desktop
- Diegimo instrukcija (grafinis installer): https://ubuntu.com/tutorials/install-ubuntu-desktop
- Bootable USB (Windows) per Rufus: https://rufus.ie

---

## 2. NVIDIA tvarkyklė (driver)

Grafiškai, be CLI:
- Atidaryk **Software & Updates → Additional Drivers** → pasirink
  proprietary (tested) NVIDIA driver → Apply → restart.
- Oficiali Ubuntu instrukcija: https://ubuntu.com/server/docs/nvidia-drivers-installation
- Patikra po restart: terminale `nvidia-smi` → turi rodyti GPU.

---

## 3. Docker Engine (native, NE Docker Desktop)

- Oficiali Ubuntu diegimo instrukcija (apt repo): https://docs.docker.com/engine/install/ubuntu/
- Post-install (paleisti docker be sudo): https://docs.docker.com/engine/install/linux-postinstall/
  - `sudo usermod -aG docker $USER` → atsijungti/prisijungti.
- Patikra: `docker run hello-world`

---

## 4. NVIDIA Container Toolkit (GPU container'iuose)

Tai duoda `runtime: nvidia` veikimą (kaip dabar compose).
- Oficiali diegimo instrukcija: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
- Po diegimo: `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`
- Patikra: `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`
  → turi rodyti GPU container'io viduje.

---

## 5. Portainer (Docker GUI naršyklėj, ~Docker Desktop)

- Oficiali diegimo instrukcija: https://docs.portainer.io/start/install-ce/server/docker/linux
- Greitas startas:
  ```
  docker volume create portainer_data
  docker run -d -p 9443:9443 --name portainer --restart=always \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v portainer_data:/data \
    portainer/portainer-ce:latest
  ```
- Atidaryk `https://localhost:9443` → susikurk admin → matai container'ius,
  logus, stats, exec, compose „stacks".

---

## 6. VS Code (native Linux)

- Atsisiųsk `.deb`: https://code.visualstudio.com/docs/setup/linux
  (dukart spustelėt → įsidiegia grafiškai)
- Naudingi extension'ai:
  - Docker: https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-docker
  - Dev Containers: https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers
- Open Folder → projekto katalogas → redaguoji compose/app.py lokaliai.

---

## 7. Stacko perkėlimas

1. Nukopijuok visą projekto katalogą + `.env` į Ubuntu.
2. Atstatyk volume'us (jei migruoji duomenis): atvirkščias `tar` į naujus volume'us.
3. `docker compose up -d`
4. Patikrink GPU servisus: `open-webui-dk`, `docling-serve` **ir `gliner`** mato
   GPU (`docker exec gliner python -c "import torch;print(torch.cuda.is_available())"`
   → `True`; metrika `gliner_model_on_gpu` turi būti `1`). Native GPU host'e
   gliner pagaliau gauna tikrą GPU (~70 užkl./s vietoj CPU-fallback).
5. **Stebėsena:** native GPU host'e gali paleist ir `dcgm-exporter` (GPU metrikos
   Zabbix'ui) — nebuvo įmanoma ant Docker Desktop. `docker compose up -d dcgm-exporter`;
   parink image tag pagal driver'į. Zabbix host'e `{$GP.DISK.MOUNT}` nustatyk į `/`
   arba `/srv` (ne Docker Desktop `/mnt/...`). Žr. [MONITORING.lt.md](MONITORING.lt.md).

> Pastaba: bind-mount keliai compose faile turi būti suderinti su Linux
> (pvz. `./guardproxy/...` veikia, bet jokių Windows `F:\` kelių).
> Patikrink `docker-compose.yml` ar nėra absoliučių Windows kelių.

---

## 8. oikb — Knowledge Base Sync (SharePoint / Jira / Confluence)

Reikalavimai: OpenWebUI **0.9.6+** (turim) + **API keys ĮJUNGTI**.

- Dokumentacija: https://docs.openwebui.com/features/knowledge-base-sync/
- Daemon deployment: https://docs.openwebui.com/features/knowledge-base-sync/daemon/
- Repo (pilnos connector opcijos): https://github.com/open-webui/oikb

### Connector'iai

| Šaltinis | Connector string | Auth (env) |
|---|---|---|
| SharePoint | `sharepoint:site[/library]` | `SHAREPOINT_TENANT_ID` + `SHAREPOINT_CLIENT_ID` + `SHAREPOINT_CLIENT_SECRET` (arba `SHAREPOINT_CERTIFICATE_PATH`) |
| Jira | `jira:PROJECT` | `JIRA_URL` + `JIRA_USER` + `JIRA_TOKEN` |
| Confluence | `confluence:SPACE` | `CONFLUENCE_URL` + `CONFLUENCE_USER` + `CONFLUENCE_TOKEN` |

- Atlassian API token (Jira + Confluence): https://id.atlassian.com/manage-profile/security/api-tokens
- SharePoint = Azure app registration (Graph `Sites.Read.All`) → **reikia Azure
  admin consent** (sunkiausia dalis, planuok su IT).

### PASENĘ: atskiro `oikb` daemon serviso NEBĖRA

> Ankstesnis planas turėjo atskirą `oikb` konteinerį su HTTP `/sync` endpoint'ais
> (todėl ir `OIKB_API_KEY`). **Realioje architektūroje oikb paleidžiamas kaip
> subprocesas `kb-admin` viduje** (`oikb sync <source>` per `subprocess.Popen`).
> Nėra atskiro serviso, portų ar `OIKB_API_KEY`. Žr. `kb-admin` servisą
> `docker-compose.yml` ir [KB-ADMIN-APP-PLAN.md](KB-ADMIN-APP-PLAN.md).

### .oikb.yaml (mapping šaltinis → kolekcija)

```yaml
sources:
  - source: "confluence:DOCS"
    knowledge: "Confluence DOCS"
  - source: "jira:PROJ?limit=500"
    knowledge: "Jira PROJ"
  - source: "sharepoint:mysite/Documents"
    knowledge: "SharePoint Docs"
```

### Eiliškumas (nuo lengviausio)

1. **Confluence** viena space (Atlassian token, jokio admin) → testuok sync.
2. **Jira** vienas projektas (tas pats Atlassian token).
3. **SharePoint** paskutinį (reikia Azure admin consent).

> Inkrementinis sync: jei šaltiny ištrini failą → oikb ištrina iš KB.
> Atsargiai, kad netyčia neišvalytum kolekcijos.
> Server-side indeksavimas async → didelis pradinis embeddings krūvis (GPU).

---

## Verdiktas

Ubuntu Desktop + native Docker Engine + nvidia-container-toolkit + Portainer +
VS Code native = Windows-like patogumas + pilnas Linux GPU našumas.
Vienintelė vieta kur gali tekt terminalo — NVIDIA driver setup ir
`docker compose up`, visa kita grafiškai.
