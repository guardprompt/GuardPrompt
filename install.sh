#!/usr/bin/env bash
# GuardPrompt installer — Ubuntu / Linux (native Docker Engine + NVIDIA GPU)
# Step-by-step wizard: generates .env with unique passwords.
# Run after git clone:  bash install.sh
set -euo pipefail
cd "$(dirname "$0")"

ENV=".env"
EXAMPLE=".env.example"

echo "==================================================="
echo "      GuardPrompt setup (Linux)"
echo "==================================================="

# ----------------------------------------------------------------------
# 1. Docker
# ----------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker not found. Install native Docker Engine:"
  echo "  https://docs.docker.com/engine/install/ubuntu/"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' (v2) not found. Install docker-compose-plugin."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: cannot reach Docker daemon. Is it running? Are you in the 'docker' group?"
  echo "  sudo usermod -aG docker \$USER   (then log out / log in)"
  exit 1
fi
echo "[OK] Docker is running."

# ----------------------------------------------------------------------
# 1b. Disk space WHERE DOCKER ACTUALLY STORES DATA.
#     "100 GB free on the server" is not enough — it must be free on the
#     filesystem holding Docker's storage. Docker uses TWO locations, and with
#     the containerd image store the second is usually the larger one:
#        <data-root>          containers + volumes      (docker info)
#        /var/lib/containerd  image + snapshot store    (containerd `root`)
#     Both normally sit on a small ROOT partition while the big data disk is
#     mounted elsewhere (/srv, /data, ...). Without this check the build runs
#     for ~10 minutes and then dies with a confusing package-manager error
#     ("needs 68KB more space on the / filesystem") while df shows terabytes
#     free on the data disk. Fail early and say exactly how to fix it instead.
# ----------------------------------------------------------------------
NEED_GB="${GP_REQUIRED_GB:-60}"

_avail_gb() {   # free GB on the filesystem containing $1 (walk up if missing)
  _p="$1"
  while [ ! -d "$_p" ] && [ "$_p" != "/" ]; do _p="$(dirname "$_p")"; done
  df -PBG "$_p" 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}'
}

DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)"
DOCKER_ROOT="${DOCKER_ROOT:-/var/lib/docker}"
CTRD_ROOT="$(sed -n "s/^[[:space:]]*root[[:space:]]*=[[:space:]]*['\"]\([^'\"]*\)['\"].*/\1/p" \
             /etc/containerd/config.toml 2>/dev/null | head -1)"
CTRD_ROOT="${CTRD_ROOT:-/var/lib/containerd}"

echo "Checking free space where Docker stores data (need ${NEED_GB} GB):"
_disk_ok=1
for _d in "$DOCKER_ROOT" "$CTRD_ROOT"; do
  _a="$(_avail_gb "$_d")"
  [ -z "$_a" ] && continue
  _mp="$(df -P "$_d" 2>/dev/null | awk 'NR==2{print $6}')"
  printf '  %-26s on %-12s %s GB free\n' "$_d" "$_mp" "$_a"
  [ "$_a" -lt "$NEED_GB" ] && _disk_ok=0
done

if [ "$_disk_ok" -eq 0 ]; then
  echo ""
  echo "[ERROR] Not enough free space where Docker stores its data."
  echo "        A full build of every image needs roughly 40-60 GB."
  echo ""
  echo "  Filesystems with the most room:"
  df -h --output=avail,target -x tmpfs -x devtmpfs 2>/dev/null | sort -rh | head -5 | sed 's/^/    /'
  echo ""
  echo "  Reclaim space first (safe — does NOT delete volumes or your data):"
  echo "    docker system prune -af"
  echo ""
  echo "  Or move Docker onto the big disk (example target /srv):"
  echo "    1) /etc/docker/daemon.json      ->  \"data-root\": \"/srv/dockerdata\""
  echo "       keep any existing keys (e.g. the nvidia \"runtimes\" block)"
  echo "    2) /etc/containerd/config.toml  ->  root = \"/srv/containerd\""
  echo "    3) sudo systemctl restart containerd docker"
  echo "    4) docker info | grep 'Docker Root Dir'"
  echo ""
  printf "Continue anyway? [y/N] "
  read -r _ans
  case "$_ans" in
    y|Y) echo "Continuing — the build may still fail if space runs out." ;;
    *)   exit 1 ;;
  esac
else
  echo "[OK] Enough free space for Docker storage."
fi

# ----------------------------------------------------------------------
# 2. NVIDIA GPU (warning, not a blocker)
# ----------------------------------------------------------------------
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[OK] NVIDIA driver:"
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true
  if ! docker info 2>/dev/null | grep -qi 'nvidia'; then
    echo "[WARNING] nvidia-container-toolkit may not be configured:"
    echo "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
  fi
else
  echo "[WARNING] nvidia-smi not found — GPU services will run without GPU."
fi

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
gen_alnum() {  # $1 = length ; letters+digits only (safe inside DB URL)
  # '|| true': head closes the pipe early -> tr gets SIGPIPE (141); under
  # 'set -o pipefail' that would abort the whole script. Swallow it.
  LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom 2>/dev/null | head -c "${1:-24}" || true
}
gen_hex() {    # $1 = bytes -> hex
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "${1:-32}";
  else LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom 2>/dev/null | head -c "$(( ${1:-32} * 2 ))" || true; fi
}
set_env() {    # set_env KEY VALUE  -> replaces the line in .env (all keys exist in template)
  local k="$1" v="$2"
  sed -i "s|^${k}=.*|${k}=${v}|" "$ENV"
}
ask() {        # ask "Question" "default" -> returns input or default
  local p="$1" d="$2" a
  read -rp "  $p [$d]: " a
  echo "${a:-$d}"
}

# ----------------------------------------------------------------------
# 3. .env handling
# ----------------------------------------------------------------------
if [ -f "$ENV" ]; then
  echo ""
  read -rp "Existing .env found. Overwrite with a fresh one (new passwords)? [y/N]: " ow
  if [ "${ow:-N}" != "y" ]; then
    echo "Keeping existing .env. Moving on to startup."
    SKIP_ENV=1
  else
    cp "$ENV" "${ENV}.bak.$(date +%Y%m%d%H%M%S)"
    echo "[OK] Old .env saved as .bak"
    SKIP_ENV=0
  fi
else
  SKIP_ENV=0
fi

if [ "${SKIP_ENV:-0}" = "0" ]; then
  if [ ! -f "$EXAMPLE" ]; then
    echo "ERROR: $EXAMPLE (template) is missing. Cannot generate .env."
    exit 1
  fi
  cp "$EXAMPLE" "$ENV"

  echo ""
  echo "--- Generating unique passwords / secrets ---"
  PG_PASS="$(gen_alnum 28)"
  WEBUI_KEY="$(gen_hex 32)"
  SEARX="$(gen_hex 24)"
  GF_PASS="$(gen_alnum 20)"
  N8N_PASS="$(gen_alnum 20)"
  KB_SECRET="$(gen_hex 32)"
  # Anonymizer API key. Port 8005 is published on 0.0.0.0, so without this the
  # anonymization API — including the URL-fetching /api/webcrawle — is callable
  # by anything on the network. ANON_API_KEYS = keys the service ACCEPTS,
  # ANON_API_KEY = the one its own clients (gp-pipeline, OpenWebUI) send.
  ANON_KEY="gp_$(gen_hex 32)"
  # Zabbix monitoring stack's own Postgres password (must not sit in compose as
  # plaintext). User/db name are non-secret defaults in docker-compose.yml.
  ZBX_DB_PASS="$(gen_alnum 28)"
  # Qdrant REST API key — internal-net hardening. Without it any container on
  # openwebui_net can read/write/delete all document vectors (qdrant has no auth
  # by default). OpenWebUI reads QDRANT_API_KEY natively; kb-admin + uploads-
  # cleaner send it too. /metrics + health stay exempt (monitoring unaffected).
  QDRANT_KEY="$(gen_hex 24)"
  # Open Terminal auth token — only OpenWebUI (which holds it) may drive the
  # command sandbox. Register in Admin -> Integrations -> Open Terminal.
  OPEN_TERMINAL_KEY="$(gen_hex 24)"
  # Bearer key for gp-transcribe's OpenAI-compatible STT endpoint. OpenWebUI voice
  # input uses it (seeded into OWUI's audio config below); the same value gates the
  # /v1/audio/transcriptions endpoint so only OpenWebUI can call it.
  STT_KEY="gpstt-$(gen_hex 20)"
  set_env POSTGRES_PASSWORD_ENV "$PG_PASS"
  set_env ZABBIX_DB_PASSWORD    "$ZBX_DB_PASS"
  set_env QDRANT_API_KEY        "$QDRANT_KEY"
  set_env OPEN_TERMINAL_API_KEY "$OPEN_TERMINAL_KEY"
  # The Open Terminal office/PDF/data toolset is baked into the custom image
  # (open-terminal/Dockerfile), built by `docker compose build` below — so it is
  # installed automatically on first install with fast, offline-capable starts.
  # The OPEN_TERMINAL_*_PACKAGES env knobs stay empty (for optional extras).
  set_env WEBUI_SECRET_KEY      "$WEBUI_KEY"
  set_env SEARXNG_SECRET        "$SEARX"
  set_env GF_ADMIN_PASSWORD_ENV "$GF_PASS"
  set_env N8N_ADMIN_PASSWORD    "$N8N_PASS"
  set_env KBADMIN_SESSION_SECRET "$KB_SECRET"
  set_env ANON_API_KEYS         "$ANON_KEY"
  set_env ANON_API_KEY          "$ANON_KEY"
  set_env GP_STT_API_KEYS       "$STT_KEY"
  echo "[OK] Passwords generated."

  # Ubuntu docling vision LLM -> in-stack Ollama (GPU). 'host.docker.internal'
  # is Windows-only; COMPOSE_PROFILES=ollama auto-starts the ollama service.
  set_env LM_STUDIO_URL    "http://ollama:11434/v1/chat/completions"
  set_env LM_MODEL         "gemma3:4b"
  set_env COMPOSE_PROFILES "ollama"

  echo ""
  echo "--- Configuration (press Enter to keep the default) ---"
  set_env POSTGRES_USER_ENV     "$(ask 'Postgres user'            'guardprompt')"
  set_env POSTGRES_DB_ENV       "$(ask 'Postgres database name'   'guardprompt')"
  set_env DOCLING_PUBLIC_SCHEME "$(ask 'Public scheme (http/https)' 'https')"
  set_env DOCLING_PUBLIC_HOST   "$(ask 'Public domain'            'chat.example.com')"
  set_env DOCLING_PUBLIC_PORT   "$(ask 'Public port (empty if 80/443)' '')"
  set_env LICENSING_URL_ENV     "$(ask 'Licensing URL'            'https://www.dkprojektai.lt')"
  set_env CLEANER_DELETE_AFTER_DAYS "$(ask 'Delete uploads after X days' '30')"

  echo ""
  echo "==================================================="
  echo " Generated credentials (write these down!):"
  echo "   Postgres pass : $PG_PASS"
  echo "   Grafana admin : $GF_PASS"
  echo "   N8N admin     : $N8N_PASS"
  echo "   Anonymizer API key : $ANON_KEY"
  echo "     ^ use this to call the API (Authorization: Bearer <key>)."
  echo "   (WEBUI_SECRET / SEARXNG_SECRET — internal, stored in .env)"
  echo "==================================================="
fi

# ----------------------------------------------------------------------
# 4. CRLF -> LF for shell scripts (safety net for Windows-edited files)
# ----------------------------------------------------------------------
echo ""
echo "Normalizing line endings (.sh -> LF)..."
find . -type f -name "*.sh" -not -path "./.git/*" -exec sed -i 's/\r$//' {} +

# ----------------------------------------------------------------------
# 4b. Machine license key — per-machine, generated once, NOT shipped by publish.
#     Bind-mounted read-only into anonymizer + kb-admin, so the host file must
#     exist. Register this key with GuardPrompt to activate the license.
# ----------------------------------------------------------------------
KEY_FILE="anonymizer/machine_key.txt"
if [ ! -s "$KEY_FILE" ]; then
  mkdir -p anonymizer
  if [ -r /proc/sys/kernel/random/uuid ]; then
    cat /proc/sys/kernel/random/uuid > "$KEY_FILE"
  else
    python3 -c "import uuid; print(uuid.uuid4())" > "$KEY_FILE"
  fi
  echo "[OK] Generated new machine key: $(cat "$KEY_FILE")"
  echo "     Register it with GuardPrompt (see: http://localhost:8005/api/reginfo)."
else
  echo "[OK] Machine key exists: $(cat "$KEY_FILE")"
fi

# ----------------------------------------------------------------------
# 5. Build + start
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# 4c. Per-deployment branding — NAME + LOGO, set here so the deployment is
#     branded on first boot with no manual post-install editing. brand.json +
#     client-logo.svg are gitignored and never published (customer identity stays
#     out of the repo) and survive 'git reset --hard' (untracked files untouched).
# ----------------------------------------------------------------------
# Default to the current name (on a re-run) or the neutral fallback.
# NB: `|| true` — brand.json is gitignored (absent on a fresh clone), and under
# `set -euo pipefail` a failing `sed | head` would abort the whole installer right
# here (silently, mid-run). Tolerate the missing file and fall back below.
_cur_name="$(sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' guardproxy/brand.json 2>/dev/null | head -1 || true)"
[ -n "$_cur_name" ] || _cur_name="GuardPrompt"
BRAND_NAME="$(ask 'Brand / company name (UI + browser-tab title)' "$_cur_name")"

# Logo: copy the customer's file into place, or keep the current/default one.
LOGO_SRC="$(ask 'Path to your logo file (SVG recommended; blank = keep current/default)' '')"
if [ -n "$LOGO_SRC" ]; then
  if [ -f "$LOGO_SRC" ]; then
    cp "$LOGO_SRC" guardproxy/client-logo.svg && echo "[OK] Logo installed from $LOGO_SRC"
    case "$LOGO_SRC" in
      *.svg|*.SVG) : ;;
      *) echo "[WARN] Non-SVG logo is served as /_gp/client-logo.svg (image/svg+xml); convert to SVG if it does not render." ;;
    esac
  else
    echo "[WARN] '$LOGO_SRC' not found — keeping current/default logo."
  fi
fi
# Guarantee a logo file exists (a MISSING bind-mount source makes Docker create a
# directory in its place — caught below, but avoid it here).
[ -f guardproxy/client-logo.svg ] || cp guardproxy/client-logo.default.svg guardproxy/client-logo.svg

# Same for the meeting-protocol page defaults (default model + prompt). Gitignored
# so admin edits survive redeploys; created here from the tracked default.
[ -f guardproxy/protokolas.config.json ] || cp guardproxy/protokolas.config.default.json guardproxy/protokolas.config.json

# Write brand.json with the name AND a NON-EMPTY logo path. The shipped default
# has logo="" — copying it verbatim is why the logo file is present yet never
# appears; setting the path here fixes that class of "logo won't show" tickets.
_name_esc="$(printf '%s' "$BRAND_NAME" | sed 's/\\/\\\\/g; s/"/\\"/g')"
printf '{\n  "name": "%s",\n  "logo": "/_gp/client-logo.svg"\n}\n' "$_name_esc" > guardproxy/brand.json
echo "[OK] Branded as '$BRAND_NAME' (guardproxy/brand.json + client-logo.svg)"

# These files are bind-mounted into the guardproxy container and served by nginx,
# which runs as a different user than whoever uploaded them. A logo copied in over
# SFTP / VS Code Remote typically lands as 0600, and nginx then answers 403 for
# /_gp/client-logo.svg — the page loads but the logo silently never appears. Make
# them world-readable (they are public assets: a logo and a name).
chmod 644 guardproxy/brand.json guardproxy/client-logo.svg 2>/dev/null || true

# A bind mount of a MISSING file makes Docker create a DIRECTORY in its place,
# after which nginx can never serve it. Catch that here rather than at runtime.
for _f in guardproxy/brand.json guardproxy/client-logo.svg; do
  if [ -d "$_f" ]; then
    echo "[ERROR] $_f is a DIRECTORY (Docker created it because the file was missing)."
    echo "        Remove it and put the real file there:"
    echo "          sudo rmdir '$_f' && cp <your-file> '$_f' && chmod 644 '$_f'"
    exit 1
  fi
done

echo "Pulling / building images..."
docker compose pull --ignore-buildable || true
docker compose build
echo "Starting the stack..."
docker compose up -d

# --- Ollama vision model (docling image captions). Pull once; OLLAMA_KEEP_ALIVE=-1
#     keeps it in VRAM so there is no reload latency. ---
if docker compose ps --services 2>/dev/null | grep -qx "ollama"; then
  OLLAMA_MODEL="$(grep -E '^LM_MODEL=' "$ENV" 2>/dev/null | cut -d= -f2)"
  OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:4b}"
  echo "Waiting for Ollama, then pulling '$OLLAMA_MODEL' (first run only)..."
  for _ in $(seq 1 30); do docker exec ollama ollama --version >/dev/null 2>&1 && break; sleep 2; done
  if docker exec ollama ollama pull "$OLLAMA_MODEL"; then
    echo "[OK] Ollama model ready: $OLLAMA_MODEL"
  else
    echo "[WARNING] Ollama pull failed — run manually: docker exec ollama ollama pull $OLLAMA_MODEL"
  fi
fi

# --- gliner: pre-download the Art.9/10 NER model (first /analyze pulls ~1GB).
#     Best-effort so the first anonymized document isn't slow. ---
echo "Warming up gliner (downloads NER model, first run only)..."
for _ in $(seq 1 30); do
  docker exec gliner python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1 && break
  sleep 2
done
if docker exec gliner python -c "import urllib.request,json;urllib.request.urlopen(urllib.request.Request('http://localhost:8000/analyze',data=json.dumps({'text':'test','labels':['person']}).encode(),headers={'content-type':'application/json'}),timeout=600)" >/dev/null 2>&1; then
  echo "[OK] gliner model ready."
else
  echo "[WARNING] gliner warmup skipped — model downloads on the first document."
fi

# ----------------------------------------------------------------------
# 4c. Seed the GuardPrompt "kas nusiųsta į modelį" OpenWebUI function.
#     OpenWebUI Filter functions live in its DB (not file-mounted like pipelines)
#     and must be owned by an admin user — so this runs AFTER the first account is
#     created (the first signup becomes admin). The seeder is idempotent: it
#     UPSERTs by id and preserves the admin's valves / enabled / global settings.
# ----------------------------------------------------------------------
echo ""
echo "--- GuardPrompt OpenWebUI function ---"
echo "Open http://localhost:8080 and create your admin account (first signup = admin)."
printf "Press Enter once the admin account exists to install the function... "
read -r _
SEEDER="scripts/seed_openwebui_function.py"
FN_DIR="pipelines/openwebui-functions"

# id | global | file | description
#   global=true  -> runs for every model. Both are global:
#     - the "what was sent" notice, and
#     - the EU AI-label watermark (global so generated images ALWAYS get the
#       "AI GENERATED" mark for AI-Act transparency, regardless of which model
#       produced them; it is a no-op on plain text output). To scope it to one
#       model instead, seed with global=false and attach it under
#       Workspace -> Models -> <image model> -> Filters.
FN_LIST="
guardprompt_kas_nusiusta_i_modeli|true|$FN_DIR/guardprompt_show_sent.py|GuardPrompt — kas nusiųsta į modelį
guardprompt_ai_label|true|$FN_DIR/guardprompt_ai_label.py|GuardPrompt — DI ženklas paveikslėliams
"

seed_one() {   # $1=id  $2=global  $3=file  $4=name
  [ -f "$3" ] || { echo "[WARNING] $3 missing — skipped."; return 0; }
  docker cp "$3" open-webui-dk:/tmp/gp_fn.py >/dev/null
  docker cp "$SEEDER" open-webui-dk:/tmp/seed_fn.py >/dev/null
  docker exec -e GP_FN_SRC=/tmp/gp_fn.py -e GP_FN_ID="$1" \
              -e GP_FN_NAME="$4" -e GP_FN_GLOBAL="$2" \
              open-webui-dk python /tmp/seed_fn.py
}

seeded=0
for _ in 1 2 3 4 5; do
  rc=0
  echo "$FN_LIST" | while IFS='|' read -r fid fglob ffile fname; do
    [ -n "$fid" ] || continue
    seed_one "$fid" "$fglob" "$ffile" "$fname" || exit $?
  done
  rc=$?
  if [ "$rc" -eq 0 ]; then seeded=1; break
  elif [ "$rc" -eq 2 ]; then
    printf "No admin account yet. Create it, then press Enter to retry... "; read -r _
  else
    echo "[WARNING] function seeding failed (exit $rc)."; break
  fi
done
# Seed OpenWebUI's STT config so built-in voice input uses the LOCAL gp-transcribe
# engine (Lithuanian svogunas, auto-detects EN too, no OpenRouter egress — audio never
# leaves the machine). Independent of the admin account — the audio.* config rows exist once
# OpenWebUI has booted. The api key must match gp-transcribe's GP_STT_API_KEYS.
STT_SEEDER="scripts/seed_stt_config.py"
if [ -f "$STT_SEEDER" ]; then
  STT_VAL="$(sed -n 's/^GP_STT_API_KEYS=//p' "$ENV" | head -1)"
  if docker cp "$STT_SEEDER" open-webui-dk:/tmp/seed_stt.py >/dev/null 2>&1 \
     && docker exec -e GP_STT_API_KEYS="$STT_VAL" open-webui-dk python /tmp/seed_stt.py; then
    echo "[OK] OpenWebUI voice input -> local gp-transcribe."
    docker restart open-webui-dk >/dev/null    # reload the audio config
  else
    echo "[WARNING] STT config seeding failed — set it manually in Admin -> Settings -> Audio"
    echo "          (Base URL http://gp-transcribe:8000/v1, key = GP_STT_API_KEYS)."
  fi
fi

if [ "$seeded" -eq 1 ]; then
  echo "Restarting OpenWebUI to load the functions..."
  docker restart open-webui-dk >/dev/null
  echo "[OK] GuardPrompt functions installed."
  echo "     NOTE: the EU AI-label watermark is installed but NOT active until you"
  echo "     attach it: Workspace -> Models -> <image model> -> Filters."
else
  echo "[WARNING] Functions not installed. Install them later with:"
  echo "  docker cp $FN_DIR/<function>.py open-webui-dk:/tmp/gp_fn.py"
  echo "  docker cp $SEEDER open-webui-dk:/tmp/seed_fn.py"
  echo "  docker exec -e GP_FN_SRC=/tmp/gp_fn.py -e GP_FN_ID=<id> -e GP_FN_GLOBAL=<true|false> \\"
  echo "         open-webui-dk python /tmp/seed_fn.py"
  echo "  docker restart open-webui-dk"
fi

echo ""
echo "=== Done. Status: ==="
docker compose ps
echo ""
echo "OpenWebUI:  http://localhost:8080"
echo "guardproxy: http://localhost:9099"
echo "Logs:       docker compose logs -f <service>"
