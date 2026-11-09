#!/usr/bin/env bash
# =============================================================================
# gpu-license-textfile.sh — export the NVIDIA vGPU (Grid) LICENSE state as a
# Prometheus node-exporter *textfile* metric.
#
# WHY: no exporter reports vGPU licence status, and gliner_model_on_gpu cannot
# catch a runtime licence drop (it is set once at startup and stays 1). When the
# DLS/token becomes unreachable the licence lapses, `nvidia-smi -q` flips to
# "License Status : Unlicensed", and ALL CUDA compute throws
# cudaErrorDeviceNotLicensed — gliner /analyze 500s and the platform fail-closes.
# This script surfaces that state DIRECTLY so Zabbix can alert before users are
# blocked.
#
# INSTALL (production GPU host only — VW-DI-VSSA):
#   # Invoke via `/bin/bash` — NOT `./script`. The repo is published from Windows,
#   # where git stores the file mode 100644 (no exec bit), so every
#   # `git reset --hard` on the host strips +x and a `./script` cron dies with
#   # "Permission denied" (exit 126) — the textfile then freezes at its last value
#   # and Zabbix alerts on a stale licence state. `bash <file>` ignores the exec
#   # bit, so it survives every redeploy. The `grep -v` keeps the entry unique.
#   ( crontab -l 2>/dev/null | grep -v gpu-license-textfile.sh; \
#     echo "* * * * * /bin/bash /srv/dockerapp/GuardPrompt/monitoring/gpu-license-textfile.sh" \
#   ) | crontab -
# node-exporter reads ./monitoring/textfile (mounted at /textfile) and republishes
# node_nvidia_vgpu_licensed; the Zabbix template alerts on =0. See MONITORING.md.
#
# No GPU / no nvidia-smi (e.g. Docker Desktop dev box): emits value 0 with
# reason="unavailable" — harmless; just don't wire the cron there.
# =============================================================================
set -euo pipefail

OUT_DIR="$(cd "$(dirname "$0")" && pwd)/textfile"
OUT="${OUT_DIR}/gpu_license.prom"
TMP="${OUT}.$$"
mkdir -p "${OUT_DIR}"

lic=0
reason="unavailable"

if command -v nvidia-smi >/dev/null 2>&1; then
  # Query once. `License Status : Licensed` == good; `Unlicensed` == lapsed.
  # The colon-anchored pattern deliberately does NOT match "Unlicensed".
  q="$(nvidia-smi -q 2>/dev/null || true)"
  if printf '%s' "$q" | grep -qE 'License Status[[:space:]]*:[[:space:]]*Licensed'; then
    lic=1
    reason="licensed"
  elif printf '%s' "$q" | grep -qiE 'License Status[[:space:]]*:[[:space:]]*Unlicensed'; then
    lic=0
    reason="unlicensed"
  else
    # nvidia-smi present but no vGPU licence section (e.g. passthrough GPU):
    # treat as licensed=1 so we don't false-alarm on non-vGPU hosts.
    lic=1
    reason="not_vgpu"
  fi
fi

{
  echo '# HELP node_nvidia_vgpu_licensed vGPU Grid license status (1 licensed/not-applicable, 0 unlicensed/unavailable)'
  echo '# TYPE node_nvidia_vgpu_licensed gauge'
  echo "node_nvidia_vgpu_licensed ${lic}"
  echo '# HELP node_nvidia_vgpu_license_info vGPU license reason (labelled), always 1'
  echo '# TYPE node_nvidia_vgpu_license_info gauge'
  echo "node_nvidia_vgpu_license_info{reason=\"${reason}\"} 1"
} > "${TMP}"
mv -f "${TMP}" "${OUT}"
