#!/usr/bin/env bash
# GPU VRAM watchdog for the shared prod host (VW-DI-VSSA, vGPU L40S-24C 24GB).
#
# Why: OpenWebUI's local RAG embed+reranker (bge-m3 / bge-reranker-v2-m3) are cached
# in VRAM and NEVER released — a KNOWN OpenWebUI limitation (RAG-does-not-free-VRAM,
# no idle-unload; upstream feature req open). Over a day of chat/RAG the open-webui-dk
# process ratchets from ~2.6GB up to 6-8GB and holds it, squeezing the shared GPU below
# the ~2GB headroom gliner's NER / the anonymizer embed forward-pass need. When free
# hits ~0 the models CUDA-OOM -> anonymizer/proxy fail-closed -> 503 for ALL chat.
#
# The stock OpenWebUI image has no per-process VRAM cap (unlike gliner GLINER_CUDA_MEM_GB
# and docling DOCLING_CUDA_MEM_GB), and no engine-side keep_alive unless embedding is
# moved to an external server (Ollama/llama-swap) — a bigger migration (reindex, reranker
# gap). Until that (or a vGPU bump), this watchdog RECLAIMS the leaked VRAM by restarting
# ONLY open-webui-dk when free VRAM drops below a floor — a targeted ~30s recycle. Chat
# LLMs are external (OpenRouter via the proxy), so only the web UI blips; no chat is lost.
#
# Runs on the HOST via systemd timer — NOT a container. We never mount docker.sock on this
# shared box (wazuh/zabbix/velociraptor/etc). A root-owned host timer calling the docker CLI
# is the safe way. SAFE BY DESIGN: the ONLY mutation is `docker restart <one container>`.
# Never prunes, never -v, never touches other stacks.
set -euo pipefail

MIN_FREE_MB="${GP_GPU_MIN_FREE_MB:-2500}"      # restart trigger: free VRAM below this
CONTAINER="${GP_GPU_GUARD_CONTAINER:-open-webui-dk}"
OWUI_MIN_MB="${GP_GPU_GUARD_OWUI_MIN_MB:-4000}" # only recycle if the container is actually
                                                # holding this much VRAM (else the low-free
                                                # is someone else's — restarting owui won't help)
COOLDOWN_MIN="${GP_GPU_GUARD_COOLDOWN_MIN:-30}" # never restart more often than this
STAMP="${GP_GPU_GUARD_STAMP:-/run/gp-gpu-guard.last}"
LOG="${GP_GPU_GUARD_LOG:-/var/log/gp-gpu-guard.log}"

log() { echo "$(date -Is) $*" >> "$LOG"; }

# --- free VRAM (MiB) ---
free_mb="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')"
if ! [[ "$free_mb" =~ ^[0-9]+$ ]]; then
  log "SKIP: could not read GPU free VRAM (nvidia-smi output: '${free_mb:-}')"
  exit 0
fi

[ "$free_mb" -ge "$MIN_FREE_MB" ] && exit 0     # healthy — nothing to do (quiet, no log spam)

# --- below floor: is $CONTAINER the culprit (holding OWUI_MIN_MB)? best-effort ---
owui_mb=0
cpid="$(docker inspect --format '{{.State.Pid}}' "$CONTAINER" 2>/dev/null || echo 0)"
if [[ "$cpid" =~ ^[0-9]+$ ]] && [ "$cpid" -gt 0 ]; then
  # sum VRAM of every compute-app PID whose cgroup belongs to $CONTAINER's container id
  cid="$(docker inspect --format '{{.Id}}' "$CONTAINER" 2>/dev/null || true)"
  while IFS=',' read -r pid mem; do
    pid="$(echo "$pid" | tr -d ' ')"; mem="$(echo "$mem" | tr -d ' ')"
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    if grep -qs "$cid" "/proc/$pid/cgroup" 2>/dev/null; then
      owui_mb=$(( owui_mb + ${mem:-0} ))
    fi
  done < <(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null)
fi

if [ "$owui_mb" -gt 0 ] && [ "$owui_mb" -lt "$OWUI_MIN_MB" ]; then
  log "SKIP: free=${free_mb}MB < ${MIN_FREE_MB} but $CONTAINER only holds ${owui_mb}MB (< ${OWUI_MIN_MB}); culprit is elsewhere — not restarting"
  exit 0
fi

# --- cooldown: don't thrash ---
now="$(date +%s)"
if [ -f "$STAMP" ]; then
  last="$(cat "$STAMP" 2>/dev/null || echo 0)"
  [[ "$last" =~ ^[0-9]+$ ]] || last=0
  age_min=$(( (now - last) / 60 ))
  if [ "$age_min" -lt "$COOLDOWN_MIN" ]; then
    log "SKIP: free=${free_mb}MB, $CONTAINER=${owui_mb}MB — within cooldown (${age_min}min < ${COOLDOWN_MIN}min)"
    exit 0
  fi
fi

log "ACTION: free=${free_mb}MB < ${MIN_FREE_MB}, $CONTAINER holds ${owui_mb}MB -> docker restart $CONTAINER"
if docker restart "$CONTAINER" >>"$LOG" 2>&1; then
  echo "$now" > "$STAMP" 2>/dev/null || true
  sleep 8
  after="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')"
  log "DONE: restarted $CONTAINER; free ${free_mb}MB -> ${after:-?}MB"
else
  log "ERROR: docker restart $CONTAINER failed"
fi
