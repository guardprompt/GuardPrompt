#!/usr/bin/env sh
# Write browser-extension/env-config.js from .env DOCLING_PUBLIC_HOST so the OWUI
# base URL is taken straight from .env — no per-machine config, no registry, nothing
# to type. Run at home (dev) once, and automatically by publish.ps1 for prod.
#   usage: sh gen-env-config.sh [path/to/.env]
set -e
here="$(cd "$(dirname "$0")" && pwd)"
env_file="${1:-$here/../.env}"
[ -f "$env_file" ] || { echo "no .env at $env_file"; exit 1; }
host="$(grep -E '^DOCLING_PUBLIC_HOST=' "$env_file" | head -1 | cut -d= -f2- | tr -d '"'\'' \r\t')"
[ -n "$host" ] || { echo "DOCLING_PUBLIC_HOST not set in $env_file"; exit 1; }
case "$host" in
  http://*|https://*) base="$host" ;;
  *) base="https://$host" ;;
esac
base="${base%/}"
# Per-deployment model id the extension locks to (matches gp-openai-proxy-browser's
# GP_MODEL_ID). Default neutral 'gp-browser'; a client can override via .env.
filter="$(grep -E '^GP_BROWSER_MODEL_ID=' "$env_file" | head -1 | cut -d= -f2- | tr -d '"'\'' \r\t')"
[ -n "$filter" ] || filter="gp-browser"
{
  printf 'window.GP_OWUI_BASE = "%s";\n' "$base"
  printf 'window.GP_MODEL_FILTER = "%s";\n' "$filter"
} > "$here/env-config.js"
echo "env-config.js -> base=$base model=$filter"
