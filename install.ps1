# GuardPrompt installer — Windows 11 + Docker Desktop
# Step-by-step wizard: generates .env with unique passwords.
# Run after git clone (PowerShell):  .\install.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$ENV_FILE = ".env"
$EXAMPLE  = ".env.example"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "      GuardPrompt setup (Windows)" -ForegroundColor Cyan
Write-Host "==================================================="

# ----------------------------------------------------------------------
# 1. Docker
# ----------------------------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker not found. Install Docker Desktop:" -ForegroundColor Red
    Write-Host "  https://www.docker.com/products/docker-desktop/"
    exit 1
}
try { docker info | Out-Null } catch {
    Write-Host "ERROR: Docker daemon not reachable. Start Docker Desktop and wait." -ForegroundColor Red
    exit 1
}
try { docker compose version | Out-Null } catch {
    Write-Host "ERROR: 'docker compose' (v2) not found. Update Docker Desktop." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Docker is running." -ForegroundColor Green

# ----------------------------------------------------------------------
# 1b. Disk space for Docker Desktop's storage.
#     Docker Desktop keeps images and layers in a WSL2 virtual disk under
#     %LOCALAPPDATA%\Docker (normally on C:) — NOT in the project folder. A
#     build that fills that drive dies midway with a confusing package-manager
#     error, so check up front instead of after ~10 minutes of building.
# ----------------------------------------------------------------------
$NeedGB = if ($env:GP_REQUIRED_GB) { [int]$env:GP_REQUIRED_GB } else { 60 }
$dockerDrive = Split-Path -Qualifier $env:LOCALAPPDATA          # e.g. "C:"
$freeGB = [math]::Floor((Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$dockerDrive'").FreeSpace / 1GB)
Write-Host ("Checking free space on {0} (Docker Desktop storage, need {1} GB): {2} GB free" -f $dockerDrive, $NeedGB, $freeGB)
if ($freeGB -lt $NeedGB) {
    Write-Host "[ERROR] Not enough free space on $dockerDrive — a full build needs roughly 40-60 GB." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Reclaim space first (safe - does NOT delete volumes or your data):"
    Write-Host "    docker system prune -af"
    Write-Host ""
    Write-Host "  Or move Docker's disk image to a bigger drive:"
    Write-Host "    Docker Desktop > Settings > Resources > Advanced > Disk image location"
    Write-Host ""
    $ans = Read-Host "Continue anyway? [y/N]"
    if ($ans -ne "y") { exit 1 }
    Write-Host "Continuing - the build may still fail if space runs out." -ForegroundColor Yellow
} else {
    Write-Host "[OK] Enough free space for Docker storage." -ForegroundColor Green
}

# ----------------------------------------------------------------------
# 2. GPU (warning)
# ----------------------------------------------------------------------
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Write-Host "[OK] NVIDIA driver found (GPU via WSL2)." -ForegroundColor Green
} else {
    Write-Host "[WARNING] nvidia-smi not found — GPU services will run without GPU." -ForegroundColor Yellow
}

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
function New-Alnum([int]$len = 24) {
    # CSPRNG (not Get-Random / System.Random, which has a ~2^31 seed an attacker can
    # brute) — this generates the Postgres/Grafana/N8N/Zabbix passwords. Rejection
    # sampling avoids modulo bias across the 62-char alphabet.
    $chars = (48..57) + (65..90) + (97..122)   # 0-9 A-Z a-z (62)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $max = 256 - (256 % $chars.Count)
    $out = New-Object System.Text.StringBuilder
    $b = New-Object byte[] 1
    while ($out.Length -lt $len) {
        $rng.GetBytes($b)
        if ($b[0] -lt $max) { [void]$out.Append([char]($chars[$b[0] % $chars.Count])) }
    }
    $out.ToString()
}
function New-Hex([int]$bytes = 32) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    ($b | ForEach-Object { $_.ToString("x2") }) -join ""
}
function Set-Env([string]$key, [string]$val) {
    $pattern = "(?m)^" + [regex]::Escape($key) + "=.*"
    $valEsc  = $val -replace '\$', '$$$$'      # protect .NET replacement from $
    $script:envText = [regex]::Replace($script:envText, $pattern, "$key=$valEsc")
}
function Ask([string]$prompt, [string]$def) {
    $v = Read-Host "  $prompt [$def]"
    if ([string]::IsNullOrWhiteSpace($v)) { return $def } else { return $v }
}

# ----------------------------------------------------------------------
# 3. .env handling
# ----------------------------------------------------------------------
$skipEnv = $false
if (Test-Path $ENV_FILE) {
    Write-Host ""
    $ow = Read-Host "Existing .env found. Overwrite with a fresh one (new passwords)? [y/N]"
    if ($ow -ne "y") {
        Write-Host "Keeping existing .env. Moving on to startup."
        $skipEnv = $true
    } else {
        $bak = "$ENV_FILE.bak.$(Get-Date -Format yyyyMMddHHmmss)"
        Copy-Item $ENV_FILE $bak
        Write-Host "[OK] Old .env -> $bak" -ForegroundColor Green
    }
}

if (-not $skipEnv) {
    if (-not (Test-Path $EXAMPLE)) {
        Write-Host "ERROR: $EXAMPLE (template) is missing. Cannot generate .env." -ForegroundColor Red
        exit 1
    }
    $script:envText = Get-Content $EXAMPLE -Raw

    Write-Host ""
    Write-Host "--- Generating unique passwords / secrets ---" -ForegroundColor Yellow
    $pgPass   = New-Alnum 28
    $webuiKey = New-Hex 32
    $searx    = New-Hex 24
    $gfPass   = New-Alnum 20
    $n8nPass  = New-Alnum 20
    $kbSecret = New-Hex 32
    # Anonymizer API key. Port 8005 is published on 0.0.0.0, so without this the
    # anonymization API — including the URL-fetching /api/webcrawle — is callable
    # by anything on the network. ANON_API_KEYS = keys the service ACCEPTS,
    # ANON_API_KEY = the one its own clients (gp-pipeline, OpenWebUI) send.
    $anonKey = "gp_" + (New-Hex 32)
    # Zabbix monitoring stack's own Postgres password (kept out of compose).
    $zbxPass = New-Alnum 28
    # Qdrant REST API key — internal-net hardening. Without it any container on
    # openwebui_net can read/write/delete all document vectors (qdrant has no
    # auth by default). OpenWebUI reads QDRANT_API_KEY natively; kb-admin +
    # uploads-cleaner send it too. /metrics + health stay exempt.
    $qdrantKey = New-Hex 24
    # Open Terminal auth token — only OpenWebUI (which holds it) may drive the
    # command sandbox. Register in Admin -> Integrations -> Open Terminal.
    $openTerminalKey = New-Hex 24
    # Bearer key for gp-transcribe's OpenAI-compatible STT endpoint (OpenWebUI voice
    # input). Seeded into OWUI's audio config below; the same value gates
    # /v1/audio/transcriptions so only OpenWebUI can call it.
    $sttKey = "gpstt-" + (New-Hex 20)
    Set-Env "POSTGRES_PASSWORD_ENV"   $pgPass
    Set-Env "ZABBIX_DB_PASSWORD"      $zbxPass
    Set-Env "QDRANT_API_KEY"          $qdrantKey
    Set-Env "OPEN_TERMINAL_API_KEY"   $openTerminalKey
    # The Open Terminal office/PDF/data toolset is baked into the custom image
    # (open-terminal/Dockerfile), built by `docker compose build` below — so it is
    # installed automatically on first install with fast, offline-capable starts.
    # The OPEN_TERMINAL_*_PACKAGES env knobs stay empty (for optional extras).
    Set-Env "WEBUI_SECRET_KEY"        $webuiKey
    Set-Env "SEARXNG_SECRET"          $searx
    Set-Env "GF_ADMIN_PASSWORD_ENV"   $gfPass
    Set-Env "N8N_ADMIN_PASSWORD"      $n8nPass
    Set-Env "KBADMIN_SESSION_SECRET"  $kbSecret
    Set-Env "ANON_API_KEYS"           $anonKey
    Set-Env "ANON_API_KEY"            $anonKey
    Set-Env "GP_STT_API_KEYS"         $sttKey
    Write-Host "[OK] Passwords generated." -ForegroundColor Green

    Write-Host ""
    Write-Host "--- Configuration (press Enter to keep the default) ---" -ForegroundColor Yellow
    Set-Env "POSTGRES_USER_ENV"     (Ask "Postgres user"            "guardprompt")
    Set-Env "POSTGRES_DB_ENV"       (Ask "Postgres database name"   "guardprompt")
    Set-Env "DOCLING_PUBLIC_SCHEME" (Ask "Public scheme (http/https)" "https")
    Set-Env "DOCLING_PUBLIC_HOST"   (Ask "Public domain"            "chat.example.com")
    Set-Env "DOCLING_PUBLIC_PORT"   (Ask "Public port (empty if 80/443)" "")
    Set-Env "LICENSING_URL_ENV"     (Ask "Licensing URL"            "https://www.dkprojektai.lt")
    Set-Env "CLEANER_DELETE_AFTER_DAYS" (Ask "Delete uploads after X days" "30")

    # Write without BOM, LF line endings (so Linux containers read it correctly)
    $script:envText = $script:envText -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot $ENV_FILE), $script:envText, (New-Object System.Text.UTF8Encoding($false)))

    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host " Generated credentials (write these down!):"
    Write-Host "   Postgres pass : $pgPass"
    Write-Host "   Grafana admin : $gfPass"
    Write-Host "   N8N admin     : $n8nPass"
    Write-Host "   Anonymizer API key : $anonKey"
    Write-Host "     ^ use this to call the API (Authorization: Bearer <key>)."
    Write-Host "   (WEBUI_SECRET / SEARXNG_SECRET — internal, stored in .env)"
    Write-Host "===================================================" -ForegroundColor Cyan
}

# ----------------------------------------------------------------------
# 3b. Machine license key — per-machine, generated once, NOT shipped by publish.
#     Bind-mounted read-only into anonymizer + kb-admin, so the host file must exist.
# ----------------------------------------------------------------------
$KeyFile = "anonymizer/machine_key.txt"
if (-not (Test-Path $KeyFile) -or ((Get-Item $KeyFile).Length -eq 0)) {
    New-Item -ItemType Directory -Force -Path "anonymizer" | Out-Null
    [guid]::NewGuid().ToString() | Out-File -FilePath $KeyFile -Encoding ascii -NoNewline
    Write-Host "[OK] Generated new machine key: $(Get-Content $KeyFile)" -ForegroundColor Green
    Write-Host "     Register it with GuardPrompt (see: http://localhost:8005/api/reginfo)."
} else {
    Write-Host "[OK] Machine key exists: $(Get-Content $KeyFile)" -ForegroundColor Green
}

# ----------------------------------------------------------------------
# 4. Build + start
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# 3c. Per-deployment branding — NAME + LOGO, set here so the deployment is branded
#     on first boot with no manual editing. brand.json + client-logo.svg are
#     gitignored and never published (customer identity stays out of the repo) and
#     survive 'git reset --hard'.
# ----------------------------------------------------------------------
$curName = "GuardPrompt"
if (Test-Path "guardproxy/brand.json") {
    try { $n = (Get-Content "guardproxy/brand.json" -Raw | ConvertFrom-Json).name; if (-not [string]::IsNullOrWhiteSpace($n)) { $curName = $n } } catch {}
}
$brandName = Ask "Brand / company name (UI + browser-tab title)" $curName
$logoSrc = Ask "Path to your logo file (SVG recommended; blank = keep current/default)" ""
if (-not [string]::IsNullOrWhiteSpace($logoSrc)) {
    if (Test-Path $logoSrc) {
        Copy-Item $logoSrc "guardproxy/client-logo.svg" -Force
        Write-Host "[OK] Logo installed from $logoSrc" -ForegroundColor Green
        if ($logoSrc -notmatch '\.svg$') { Write-Host "[WARN] Non-SVG logo served as image/svg+xml; convert to SVG if it doesn't render." -ForegroundColor Yellow }
    } else {
        Write-Host "[WARN] '$logoSrc' not found - keeping current/default logo." -ForegroundColor Yellow
    }
}
if (-not (Test-Path "guardproxy/client-logo.svg")) { Copy-Item "guardproxy/client-logo.default.svg" "guardproxy/client-logo.svg" }
# Meeting-protocol page defaults (default model + prompt); gitignored, created from default.
if (-not (Test-Path "guardproxy/protokolas.config.json")) { Copy-Item "guardproxy/protokolas.config.default.json" "guardproxy/protokolas.config.json" }
# Name AND non-empty logo path (the shipped default has logo="" -> logo never shows).
(@{ name = $brandName; logo = "/_gp/client-logo.svg" } | ConvertTo-Json) | Set-Content -Path "guardproxy/brand.json" -Encoding utf8
Write-Host "[OK] Branded as '$brandName' (guardproxy/brand.json + client-logo.svg)" -ForegroundColor Green

Write-Host ""
Write-Host "Pulling / building images..."
docker compose pull --ignore-buildable
docker compose build
Write-Host "Starting the stack..."
docker compose up -d

# --- gliner: pre-download the Art.9/10 NER model (first /analyze pulls ~1GB).
#     Best-effort so the first anonymized document isn't slow. ---
Write-Host "Warming up gliner (downloads NER model, first run only)..."
for ($i = 0; $i -lt 30; $i++) {
    docker exec gliner python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}
docker exec gliner python -c "import urllib.request,json;urllib.request.urlopen(urllib.request.Request('http://localhost:8000/analyze',data=json.dumps({'text':'test','labels':['person']}).encode(),headers={'content-type':'application/json'}),timeout=600)" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] gliner model ready." -ForegroundColor Green
} else {
    Write-Host "[WARNING] gliner warmup skipped — model downloads on the first document." -ForegroundColor Yellow
}

# ----------------------------------------------------------------------
# 4c. Seed the GuardPrompt "kas nusiųsta į modelį" OpenWebUI function.
#     OpenWebUI Filter functions live in its DB (not file-mounted like pipelines)
#     and must be owned by an admin user — so this runs AFTER the first account is
#     created (the first signup becomes admin). The seeder is idempotent: it
#     UPSERTs by id and preserves the admin's valves / enabled / global settings.
# ----------------------------------------------------------------------
Write-Host ""
Write-Host "--- GuardPrompt OpenWebUI functions ---" -ForegroundColor Yellow
Write-Host "Open http://localhost:8080 and create your admin account (first signup = admin)."
Read-Host "Press Enter once the admin account exists to install the functions"
$seeder = "scripts/seed_openwebui_function.py"
# Both global: the "what was sent" notice AND the EU AI-label watermark (global so
# generated images always get "AI GENERATED"; it is a no-op on plain text). Kept in
# sync with install.sh.
$functions = @(
    @{ id = "guardprompt_kas_nusiusta_i_modeli"; global = "true"; file = "pipelines/openwebui-functions/guardprompt_show_sent.py"; name = "GuardPrompt — kas nusiųsta į modelį" },
    @{ id = "guardprompt_ai_label";              global = "true"; file = "pipelines/openwebui-functions/guardprompt_ai_label.py";  name = "GuardPrompt — DI ženklas paveikslėliams" }
)
$seeded = $false
for ($try = 1; $try -le 5; $try++) {
    docker cp $seeder open-webui-dk:/tmp/seed_fn.py | Out-Null
    $allOk = $true; $noAdmin = $false
    foreach ($fn in $functions) {
        docker cp $fn.file open-webui-dk:/tmp/gp_fn.py | Out-Null
        docker exec -e GP_FN_SRC=/tmp/gp_fn.py -e "GP_FN_ID=$($fn.id)" -e "GP_FN_NAME=$($fn.name)" -e "GP_FN_GLOBAL=$($fn.global)" open-webui-dk python /tmp/seed_fn.py
        $code = $LASTEXITCODE
        if ($code -eq 2) { $noAdmin = $true; $allOk = $false; break }
        elseif ($code -ne 0) { $allOk = $false; Write-Host "[WARNING] $($fn.id) seeding failed (exit $code)." -ForegroundColor Yellow }
    }
    if ($allOk) { $seeded = $true; break }
    elseif ($noAdmin) { Read-Host "No admin account found yet. Create it, then press Enter to retry" }
    else { break }
}
# Seed OpenWebUI's STT config -> local gp-transcribe (LT svogunas, auto-detects EN,
# no OpenRouter egress — audio never leaves the machine). Independent of the admin account; the
# api key must match gp-transcribe's GP_STT_API_KEYS.
$sttSeeder = "scripts/seed_stt_config.py"
if (Test-Path $sttSeeder) {
    $sttLine = Select-String -Path $ENV_FILE -Pattern '^GP_STT_API_KEYS=' | Select-Object -First 1
    $sttVal = ""
    if ($sttLine) { $sttVal = $sttLine.Line.Substring('GP_STT_API_KEYS='.Length) }
    docker cp $sttSeeder open-webui-dk:/tmp/seed_stt.py | Out-Null
    docker exec -e "GP_STT_API_KEYS=$sttVal" open-webui-dk python /tmp/seed_stt.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] OpenWebUI voice input -> local gp-transcribe." -ForegroundColor Green
        docker restart open-webui-dk | Out-Null
    } else {
        Write-Host "[WARNING] STT config seeding failed - set it manually in Admin -> Settings -> Audio (Base URL http://gp-transcribe:8000/v1, key = GP_STT_API_KEYS)." -ForegroundColor Yellow
    }
}

if ($seeded) {
    Write-Host "Restarting OpenWebUI to load the functions..."
    docker restart open-webui-dk | Out-Null
    Write-Host "[OK] GuardPrompt functions installed (enabled globally)." -ForegroundColor Green
} else {
    Write-Host "[WARNING] Functions not fully installed. Install later, e.g. the AI-label:" -ForegroundColor Yellow
    Write-Host "  docker cp scripts/seed_openwebui_function.py open-webui-dk:/tmp/seed_fn.py"
    Write-Host "  docker cp pipelines/openwebui-functions/guardprompt_ai_label.py open-webui-dk:/tmp/gp_fn.py"
    Write-Host "  docker exec -e GP_FN_SRC=/tmp/gp_fn.py -e GP_FN_ID=guardprompt_ai_label -e GP_FN_GLOBAL=true open-webui-dk python /tmp/seed_fn.py"
    Write-Host "  docker restart open-webui-dk"
}

Write-Host ""
Write-Host "=== Done. Status: ===" -ForegroundColor Cyan
docker compose ps
Write-Host ""
Write-Host "OpenWebUI:  http://localhost:8080"
Write-Host "guardproxy: http://localhost:9099"
Write-Host "Logs:       docker compose logs -f <service>"
