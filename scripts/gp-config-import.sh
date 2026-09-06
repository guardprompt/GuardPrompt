#!/usr/bin/env bash
# GuardPrompt — config snapshot (IMPORT / restore).
# Restores a snapshot made by gp-config-export.sh onto a fresh (or existing)
# install, so you don't re-do all the post-install tuning by hand.
#
# Typical reinstall flow:
#   git clone ... && cd GuardPrompt
#   bash scripts/gp-config-import.sh gp-config-YYYYMMDD-HHMMSS.tar.gz files-only
#   docker compose up -d --build          # brings the stack up with restored .env
#   # wait until OpenWebUI is reachable (it creates its DB schema on first boot)
#   bash scripts/gp-config-import.sh gp-config-YYYYMMDD-HHMMSS.tar.gz db-only
#
# Or, on an already-running stack, one shot restores files + DB:
#   bash scripts/gp-config-import.sh gp-config-YYYYMMDD-HHMMSS.tar.gz
#
# Modes (2nd arg): all (default) | files-only | db-only
set -euo pipefail
cd "$(dirname "$0")/.."

ARCHIVE="${1:-}"
MODE="${2:-all}"
[ -n "$ARCHIVE" ] || { echo "Usage: bash scripts/gp-config-import.sh <gp-config-*.tar.gz> [files-only|db-only]"; exit 1; }
[ -f "$ARCHIVE" ] || { echo "Not found: $ARCHIVE"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar xzf "$ARCHIVE" -C "$TMP"
SNAP="$TMP/$(ls "$TMP" | head -1)"
[ -f "$SNAP/owui-config.sql" ] || { echo "Invalid snapshot (no owui-config.sql inside)"; exit 1; }
echo "Snapshot: $(tr '\n' ' ' < "$SNAP/MANIFEST" 2>/dev/null)"

# ---- files ----
if [ "$MODE" != "db-only" ]; then
  echo "[files] Restoring .env / brand / machine_key ..."
  [ -f "$SNAP/env" ]             && cp "$SNAP/env" .env                                    && echo "  + .env"
  [ -f "$SNAP/brand.json" ]      && cp "$SNAP/brand.json" guardproxy/brand.json            && echo "  + brand.json"
  [ -f "$SNAP/client-logo.svg" ] && cp "$SNAP/client-logo.svg" guardproxy/client-logo.svg  && echo "  + client-logo.svg"
  [ -f "$SNAP/machine_key.txt" ] && { mkdir -p anonymizer; cp "$SNAP/machine_key.txt" anonymizer/machine_key.txt; echo "  + machine_key.txt"; }
  chmod 644 guardproxy/brand.json guardproxy/client-logo.svg 2>/dev/null || true
fi
[ "$MODE" = "files-only" ] && { echo "[OK] Files restored. Next: docker compose up -d --build"; exit 0; }

# ---- DB (needs postgres up AND OpenWebUI schema created) ----
if ! docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
  echo ""
  echo "[!] Postgres not up yet. Bring the stack up, then restore the DB:"
  echo "      docker compose up -d --build"
  echo "      bash scripts/gp-config-import.sh $ARCHIVE db-only"
  exit 0
fi
HAS="$(docker compose exec -T postgres sh -c 'psql -tAqU "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT to_regclass('"'"'public.config'"'"') IS NOT NULL;"' 2>/dev/null | tr -d '[:space:]')"
if [ "$HAS" != "t" ]; then
  echo "[!] OpenWebUI schema not found yet (config table). Let OpenWebUI boot once, then:"
  echo "      bash scripts/gp-config-import.sh $ARCHIVE db-only"
  exit 0
fi

echo "[db] Restoring config/model/function/tool/prompt (atomic; replaces current)..."
# DELETE + restore wrapped in ONE transaction: if anything fails it rolls back,
# so the live config is never left half-empty.
{
  echo "BEGIN;"
  echo "DELETE FROM prompt; DELETE FROM tool; DELETE FROM function; DELETE FROM model; DELETE FROM config;"
  cat "$SNAP/owui-config.sql"
  echo "COMMIT;"
} | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'

echo ""
docker compose restart open-webui-dk >/dev/null 2>&1 \
  && echo "[OK] Config restored + OpenWebUI restarted." \
  || echo "[OK] Config restored. Restart manually: docker compose restart open-webui-dk"
echo "     Hard-refresh the browser (Ctrl+Shift+R)."
echo "     Note: restored models/functions keep their original creator id —"
echo "     harmless for public models / global functions."
