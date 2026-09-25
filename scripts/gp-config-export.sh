#!/usr/bin/env bash
# GuardPrompt — config snapshot (EXPORT).
# Captures the CONFIG you tuned after install so a reinstall can restore it:
#   - OpenWebUI settings + models + functions + tools + prompts (Postgres:
#     config/model/function/tool/prompt — NOT chat/message/file/knowledge/user,
#     so no conversations / uploads / PII are included)
#   - .env (secrets + settings)
#   - guardproxy/brand.json + client-logo.svg  (branding)
#   - anonymizer/machine_key.txt               (license binding, same-host reinstall)
#
# Output: gp-config-<timestamp>.tar.gz in the repo root.
#
# ⚠️ SENSITIVE: the archive contains .env AND the DB config (which holds API keys,
#    e.g. the OpenRouter key). Store it somewhere safe; NEVER commit it.
#
# Usage:  bash scripts/gp-config-export.sh
set -euo pipefail
cd "$(dirname "$0")/.."                      # repo root (where docker-compose.yml is)

TS="$(date +%Y%m%d-%H%M%S)"
STAGE="gp-config-$TS"
ARCHIVE="$STAGE.tar.gz"
TABLES="config model function tool prompt"

mkdir -p "$STAGE"

echo "[1/2] Dumping OpenWebUI config tables ($TABLES)..."
# --data-only + default COPY format => pg_dump appends setval() for the id
# sequences, so a later restore keeps them consistent. Container's own
# POSTGRES_USER/DB are used, so no host .env parsing is needed.
TARGS=""; for t in $TABLES; do TARGS="$TARGS -t $t"; done
docker compose exec -T postgres sh -c \
  "pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --data-only $TARGS" \
  > "$STAGE/owui-config.sql"

echo "[2/2] Copying config files (.env, brand, machine_key)..."
cp .env                          "$STAGE/env"              2>/dev/null && echo "  + .env"            || echo "  - .env (missing)"
cp guardproxy/brand.json         "$STAGE/brand.json"       2>/dev/null && echo "  + brand.json"      || echo "  - brand.json (missing)"
cp guardproxy/client-logo.svg    "$STAGE/client-logo.svg"  2>/dev/null && echo "  + client-logo.svg" || echo "  - client-logo.svg (missing)"
cp anonymizer/machine_key.txt    "$STAGE/machine_key.txt"  2>/dev/null && echo "  + machine_key.txt" || echo "  - machine_key.txt (missing)"

# manifest for sanity on restore
{
  echo "created=$TS"
  echo "host=$(hostname)"
  echo "tables=$TABLES"
  echo "sql_bytes=$(wc -c < "$STAGE/owui-config.sql")"
} > "$STAGE/MANIFEST"

tar czf "$ARCHIVE" "$STAGE"
rm -rf "$STAGE"

echo ""
echo "[OK] Snapshot: $ARCHIVE  ($(du -h "$ARCHIVE" | cut -f1))"
echo "     Restore with:  bash scripts/gp-config-import.sh $ARCHIVE"
echo "     ⚠️ Contains secrets (.env + API keys) — keep it safe, do not commit."
