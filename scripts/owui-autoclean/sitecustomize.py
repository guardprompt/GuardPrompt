# GuardPrompt GPU auto-clean for OpenWebUI — release idle VRAM WITHOUT restarting.
#
# Why: OWUI's local embed+reranker cache reserved CUDA blocks after each batch and
# NEVER return them (known OWUI limitation, no idle-unload). Over a day the process
# ratchets 2.6GB -> 6-8GB and holds it, starving the shared 24GB vGPU. We cannot cap
# it (OWUI has no OOM recovery -> a too-low cap would OOM->poison its CUDA context ->
# need a restart anyway), and torch.cuda.empty_cache() only frees memory from INSIDE
# the owning process (docker exec = a different CUDA context = no effect). So we inject
# this file via PYTHONPATH: Python auto-imports `sitecustomize` at interpreter startup,
# and here we start ONE daemon thread that periodically calls empty_cache() in OWUI's
# OWN process. That returns reserved-but-idle blocks to the device between requests,
# so free VRAM recovers continuously — no restart, no cap, no OOM risk (empty_cache
# never touches blocks currently in use, so active embedding is unaffected).
#
# Guarded so it runs ONLY in the OWUI server process (not short-lived CLI/management
# python invocations in the same image, which must stay fast and not import torch).
# Enable + tune via env on the open-webui-dk service:
#   GP_GPU_AUTOCLEAN_SEC   interval seconds (0/unset = disabled)   e.g. 180
import os
import sys
import threading


def _gp_start_autoclean():
    try:
        sec = int(os.environ.get("GP_GPU_AUTOCLEAN_SEC", "0") or "0")
    except ValueError:
        sec = 0
    if sec <= 0:
        return  # disabled

    # Only the long-lived server process — never a `python -c ...`/manage script.
    cmd = " ".join(sys.argv).lower()
    if not any(k in cmd for k in ("uvicorn", "open_webui", "start.sh", "gunicorn")):
        return

    def _loop():
        import time
        try:
            import torch
        except Exception:
            return
        # is_INITIALIZED, not is_available: sitecustomize is imported by EVERY python
        # process in the image (uvicorn master + worker, helper subprocesses), so >1
        # janitor thread can exist. empty_cache() on is_available() would FORCE a CUDA
        # context (~300-600MB VRAM) in a process that never used the GPU — pure waste.
        # is_initialized() is True only once THIS process has actually created a CUDA
        # context (the embed/reranker worker does, on the first RAG request), so the
        # janitor cleans only where there's real cache and stays a true no-op elsewhere.
        while True:
            time.sleep(sec)
            try:
                if torch.cuda.is_initialized():
                    torch.cuda.empty_cache()
            except Exception:
                pass  # never let the janitor thread crash the app

    threading.Thread(target=_loop, name="gp-gpu-autoclean", daemon=True).start()
    try:
        sys.stderr.write(
            "[gp-gpu-autoclean] started: empty_cache() every %ds (pid %d)\n"
            % (sec, os.getpid())
        )
        sys.stderr.flush()
    except Exception:
        pass


try:
    _gp_start_autoclean()
except Exception:
    pass  # a broken janitor must never stop OWUI from booting
