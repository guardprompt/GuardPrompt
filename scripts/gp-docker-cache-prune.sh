#!/usr/bin/env bash
# Periodic, SAFE docker disk reclaim for the shared prod host.
#
# Why: build cache grows with every `docker compose up -d --build` (each publish),
# and the Zabbix disk-timeleft forecast fires on the growth spike (even though /srv
# has plenty of free space). This keeps the cache bounded so it stops triggering.
#
# Runs on the HOST via cron / systemd timer — NOT a container. We deliberately never
# mount docker.sock into a container on this shared host (a container with docker.sock
# = root on the host). A root-owned host timer calling the docker CLI is the safe way.
#
# SAFE BY DESIGN — prunes ONLY:
#   * build cache, keeping a recent working set (--keep-storage)
#   * dangling images (untagged leftovers from rebuilds)
# NEVER: `-a` (would drop images other stacks' stopped containers need), volumes,
# or `docker system prune`. This box also runs wazuh/zabbix/velociraptor/etc.
set -euo pipefail

KEEP="${GP_BUILDCACHE_KEEP:-20GB}"
LOG="${GP_PRUNE_LOG:-/var/log/gp-docker-prune.log}"

{
  echo "=== $(date -Is) gp-docker-cache-prune (keep=$KEEP) ==="
  # Keep a recent working set so publishes still hit build cache. The flag was
  # renamed (`--keep-storage` -> `--reserved-space`) in newer buildkit; try the
  # new name, fall back to the old, then to an unbounded prune on very old docker.
  docker builder prune -f --reserved-space "$KEEP" 2>/dev/null \
    || docker builder prune -f --keep-storage "$KEEP" 2>/dev/null \
    || docker builder prune -f || true
  docker image prune -f || true            # dangling only — safe
  echo "--- df /srv ---";           df -h /srv     || true
  echo "--- docker system df ---";   docker system df || true
  echo
} >> "$LOG" 2>&1
