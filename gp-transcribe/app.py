"""
GP Transcribe — chunked, delay-tolerant meeting transcription engine with an
ADAPTIVE chunk size (= adaptive latency).

The page uploads audio chunks during a meeting; this VAD-filters + transcribes
each with faster-whisper (large-v3-turbo) and returns text, appended
progressively. Chunk size is NOT fixed: the server watches its own queue AND the
real GPU utilisation (NVML) and tells each client how big to make the next chunk
via `next_ms` in the response. Idle GPU -> small chunks (~MIN_MS, low latency);
busy GPU / deep queue / 100 concurrent meetings -> chunks grow toward MAX_MS so
throughput keeps up and the delay flexes instead of the pipeline falling behind.
Because the server sees GLOBAL load across all sessions, it can back every client
off together — and because the prod GPU is shared (gliner/docling/ollama), high
utilisation from those stacks also (correctly) pushes chunks larger.
"""
import os
import io
import re
import time
import uuid
import shutil
import base64
import asyncio
import tempfile
import subprocess
import hmac
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import PlainTextResponse
from faster_whisper import WhisperModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

import pseudo       # separate reversible-pseudonymisation module (names <-> GP_ tokens)
import gp_license   # license gate — refuse to transcribe when the license is inactive

# Backend: "faster" = faster-whisper/CTranslate2 (fast, quantised); "transformers"
# = original HF openai/whisper-* (reference fp16, slower); "cloud" = external
# OpenAI-compatible API (Groq / OpenAI). Cloud sends raw audio off-premises.
IMPL     = os.environ.get("WHISPER_IMPL", "faster")
_def_model = "openai/whisper-large-v3-turbo" if IMPL == "transformers" else "large-v3-turbo"
MODEL_ID = os.environ.get("WHISPER_MODEL", _def_model)
# Cloud backend config. For IMPL=openrouter we transcribe via a multimodal LLM
# (audio in a chat message). The API key is NOT hard-coded: it is read from
# OpenWebUI's own DB config (the OpenRouter connection) so the secret never
# leaves the stack and is never written to a file.
_or_default = IMPL == "openrouter"
CLOUD_BASE  = os.environ.get("CLOUD_BASE_URL", "https://openrouter.ai/api/v1" if _or_default else "https://api.groq.com/openai/v1")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "google/gemini-2.5-flash" if _or_default else "whisper-large-v3")
CLOUD_KEY   = os.environ.get("CLOUD_API_KEY", "")


def _key_from_owui(match: str):
    """Pull the API key for the connection whose base URL contains `match`
    (e.g. 'openrouter') from OpenWebUI's config table. Returns '' on any error."""
    try:
        import json
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            dbname=os.environ.get("POSTGRES_DB", "guardprompt"),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
        )
        cur = conn.cursor()
        def _get(k):
            cur.execute("SELECT value FROM config WHERE key=%s", (k,))
            row = cur.fetchone()
            if not row:
                return None
            v = row[0]
            return v if isinstance(v, (list, dict)) else json.loads(v)
        urls = _get("openai.api_base_urls") or []
        keys = _get("openai.api_keys") or []
        conn.close()
        for i, u in enumerate(urls):
            if match in (u or "") and i < len(keys) and keys[i]:
                return keys[i]
    except Exception as e:
        print(f"[gp-transcribe] could not read key from OpenWebUI DB: {e}", flush=True)
    return ""
DEVICE   = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE  = os.environ.get("WHISPER_COMPUTE", "float16")
LANG     = os.environ.get("WHISPER_LANG", "lt")
MAX_CONC = int(os.environ.get("WHISPER_MAX_CONCURRENCY", "3"))
BEAM     = int(os.environ.get("WHISPER_BEAM", "1"))
# DoS guards: cap how much a single request can pull into memory. nginx already
# limits the public path, but a direct call on the internal net would otherwise
# read an unbounded body. Audio is read with an explicit ceiling; text form fields
# are bounded too.
MAX_AUDIO_BYTES = int(os.environ.get("GP_MAX_AUDIO_MB", "400")) * 1024 * 1024
MAX_TEXT_CHARS  = int(os.environ.get("GP_MAX_TEXT_MB", "12")) * 1024 * 1024
# Anti-hallucination for the full-file pass: penalise repeated tokens and block
# exact n-gram loops (Whisper's classic "stuck phrase" on music/silence). 1.0 =
# off; ~1.1 is a gentle nudge that does not distort normal speech.
REP_PENALTY     = float(os.environ.get("WHISPER_REP_PENALTY", "1.1"))
NO_REPEAT_NGRAM = int(os.environ.get("WHISPER_NO_REPEAT_NGRAM", "3"))
MIN_MS   = int(os.environ.get("CHUNK_MIN_MS", "3000"))    # latency floor (quality)
MAX_MS   = int(os.environ.get("CHUNK_MAX_MS", "20000"))   # ceiling under load

print(f"[gp-transcribe] loading {MODEL_ID} ({IMPL}) on {DEVICE} …", flush=True)
_t0 = time.time()
model = None
asr_pipe = None
if IMPL == "transformers":
    import torch
    from transformers import pipeline
    asr_pipe = pipeline("automatic-speech-recognition", model=MODEL_ID,
                        torch_dtype=torch.float16, device=0 if DEVICE == "cuda" else -1)
elif IMPL in ("openrouter", "cloud"):
    if not CLOUD_KEY:
        CLOUD_KEY = _key_from_owui("openrouter" if IMPL == "openrouter" else "")
    print(f"[gp-transcribe] cloud backend: {CLOUD_MODEL} @ {CLOUD_BASE} "
          f"(key {'OK' if CLOUD_KEY else 'MISSING'})", flush=True)
else:
    model = WhisperModel(MODEL_ID, device=DEVICE, compute_type=COMPUTE)
print(f"[gp-transcribe] model ready in {time.time()-_t0:.1f}s", flush=True)

# Optional real GPU utilisation via NVML (nvidia-ml-py). On a vGPU the value may
# be limited/zero — we fall back to queue pressure only.
_HAVE_NVML = False
try:
    import pynvml
    pynvml.nvmlInit()
    _NVH = pynvml.nvmlDeviceGetHandleByIndex(0)
    _HAVE_NVML = True
    print("[gp-transcribe] NVML available — adaptive chunking uses real GPU util", flush=True)
except Exception as e:
    print(f"[gp-transcribe] NVML unavailable ({e}); adaptive chunking uses queue pressure only", flush=True)

def _gpu_util():
    if not _HAVE_NVML:
        return -1
    try:
        return int(pynvml.nvmlDeviceGetUtilizationRates(_NVH).gpu)
    except Exception:
        return -1

sem = asyncio.Semaphore(MAX_CONC)
inflight_n = 0
queued_n = 0

REQS   = Counter("gp_transcribe_requests_total", "Transcription requests", ["result"])
LAT    = Histogram("gp_transcribe_seconds", "Wall time per chunk",
                   buckets=(0.2, 0.5, 1, 2, 3, 5, 8, 13, 21, 34))
INFLIGHT = Gauge("gp_transcribe_in_flight", "Chunks currently on the GPU")
QUEUE    = Gauge("gp_transcribe_queued", "Chunks waiting for a GPU slot")
AUDIO    = Counter("gp_transcribe_audio_seconds_total", "Audio seconds transcribed")
ONGPU    = Gauge("gp_transcribe_model_on_gpu", "1 if model is on CUDA")
GPUUTIL  = Gauge("gp_transcribe_gpu_util", "GPU utilisation % (NVML, -1 if n/a)")
RECMS    = Gauge("gp_transcribe_recommended_ms", "Current recommended client chunk ms")
ONGPU.set(1 if DEVICE == "cuda" else 0)

app = FastAPI()

# License gate: every working endpoint is refused (503) when the license is
# inactive. /health and /metrics stay open so monitoring still sees the container.
# is_licensed() is cached (re-checks every GP_LICENSE_TTL), run off the event loop.
_LICENSE_OPEN = {"/health", "/metrics", "/license"}


@app.middleware("http")
async def _license_gate(request, call_next):
    if request.url.path in _LICENSE_OPEN:
        return await call_next(request)
    # DoS guard: reject an oversized body at the HTTP layer (by declared
    # Content-Length) BEFORE FastAPI buffers/parses it into RAM. Absolute ceiling =
    # the largest legitimate upload (audio). Per-endpoint bounds still apply below
    # (_read_capped for streamed audio, MAX_TEXT_CHARS for text fields).
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_AUDIO_BYTES:
        return PlainTextResponse("payload too large", status_code=413)
    ok = await asyncio.get_event_loop().run_in_executor(None, gp_license.is_licensed)
    if not ok:
        return PlainTextResponse("License inactive — gp-transcribe disabled.", status_code=503)
    return await call_next(request)


@app.get("/license")
def license_status():
    return gp_license.status()

# Dedicated temp dir for our ffmpeg scratch files. Everything here is transient;
# a sweeper deletes anything older than GP_TMP_TTL (default 30 min) so an orphan
# left by a crash mid-transcription can never accumulate and fill the disk.
TMPD = os.environ.get("GP_TMP", "/tmp/gp-transcribe")
TMP_TTL = int(os.environ.get("GP_TMP_TTL", "1800"))
os.makedirs(TMPD, exist_ok=True)


def _sweep(max_age=TMP_TTL):
    now = time.time()
    for name in os.listdir(TMPD):
        p = os.path.join(TMPD, name)
        try:
            if now - os.path.getmtime(p) > max_age:
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.unlink(p)
        except OSError:
            pass


@app.on_event("startup")
async def _startup_cleanup():
    _sweep(0)                                   # wipe leftovers from a previous run
    async def _loop():
        while True:
            await asyncio.sleep(600)
            _sweep()
    asyncio.create_task(_loop())


def recommended_ms():
    """Map current pressure (own queue + real GPU util) to a chunk size in
    [MIN_MS, MAX_MS]. Low pressure -> MIN (snappy); high -> MAX (survive load)."""
    load_p = (inflight_n + queued_n) / max(MAX_CONC, 1)   # our own pressure, 0..N
    gpu = _gpu_util()
    GPUUTIL.set(gpu)
    gpu_p = (gpu / 100.0) if gpu >= 0 else -1.0
    p = load_p if gpu_p < 0 else max(load_p, gpu_p)
    # dead-band: below 0.3 stay at MIN, above 1.0 clamp to MAX, linear between.
    frac = (p - 0.3) / 0.7
    frac = 0.0 if frac < 0 else (1.0 if frac > 1 else frac)
    ms = int(MIN_MS + (MAX_MS - MIN_MS) * frac)
    RECMS.set(ms)
    return ms


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID, "device": DEVICE}


@app.get("/load")
def load():
    return {"in_flight": inflight_n, "queued": queued_n,
            "gpu_util": _gpu_util(), "next_ms": recommended_ms()}


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


_ELLIPSIS = re.compile(r"\.{2,}")   # "..." (2+ dots) — Whisper's pause/boundary marker
_WS = re.compile(r"\s+")
# Collapse a word repeated 3+ times in a row ("kurių, kurių, kurių") — a classic
# Whisper hallucination on music / intro / silence. \w is unicode-aware.
_REPEAT = re.compile(r"\b(\w+)(?:[\s,]+\1\b){2,}", re.IGNORECASE | re.UNICODE)
# Filler-only interjections to drop entirely (whole-string match, punctuation
# stripped first). Real short words (Ne, Taip, OK) are NOT matched.
_FILLER = re.compile(r"^(mhm|h+m+|m+h+|mm+|u[hm]+|uhm+|hmm+)$", re.IGNORECASE)


def _clean(text: str) -> str:
    # Whisper marks pauses and chunk-boundary cuts with "..." / "…". They are
    # noise in a protocol (a word split across two chunks shows as "iškasi... "
    # then "...dešimt"), so collapse ellipses to a space and trim stray edge
    # punctuation. Single sentence-ending "." is left untouched.
    text = text.replace("…", "...")
    text = _ELLIPSIS.sub(" ", text)
    text = _REPEAT.sub(r"\1", text)              # kill repetition hallucinations
    text = _WS.sub(" ", text).strip()
    text = re.sub(r"^[.,;:\-–—\s]+", "", text)   # strip leading junk
    text = re.sub(r"[,;:\-–—\s]+$", "", text)    # trailing junk, but keep . ? !
    # Drop a chunk that is only a filler interjection (mhm / hm / uh …) — a common
    # LLM/Whisper artifact on near-silent audio. Real short words (Ne, Taip) stay.
    if _FILLER.match(re.sub(r"[.,!?…\s]", "", text)):
        return ""
    return text


def _run_cloud(data: bytes, language: str):
    # Transcribe via a multimodal LLM on an OpenAI-compatible API (OpenRouter):
    # decode the webm chunk to mp3, send it as input_audio in a chat message, and
    # ask for a verbatim transcript. No local GPU.
    import requests
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False, dir=TMPD) as fin:
        fin.write(data); src = fin.name
    dst = src + ".mp3"
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
                        "-ar", "16000", "-ac", "1", dst], check=True)
        with open(dst, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    finally:
        for p in (src, dst):
            try: os.unlink(p)
            except OSError: pass
    prompt = ("Transcribe the audio verbatim in its original language "
              "(Lithuanian, English or Russian). Output ONLY the transcript text — "
              "no quotes, no commentary, no language label. If the audio contains "
              "no discernible speech (silence, music or noise only), output nothing "
              "at all. Never invent or guess words that were not clearly spoken.")
    body = {"model": CLOUD_MODEL, "temperature": 0, "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}},
        ]}]}
    r = requests.post(CLOUD_BASE + "/chat/completions",
                      headers={"Authorization": "Bearer " + CLOUD_KEY,
                               "Content-Type": "application/json"},
                      json=body, timeout=90)
    r.raise_for_status()
    return _clean(r.json()["choices"][0]["message"]["content"])


def _run(data: bytes, language: str, context: str):
    if IMPL in ("openrouter", "cloud"):
        return _run_cloud(data, language), 0.0
    if IMPL == "transformers":
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False, dir=TMPD) as f:
            f.write(data); path = f.name
        try:
            res = asr_pipe(path, chunk_length_s=30, batch_size=1,
                           generate_kwargs={"task": "transcribe",
                                            "language": (language or LANG) or None})
            txt = res.get("text", "") if isinstance(res, dict) else str(res)
            return _clean(txt), 0.0
        finally:
            try: os.unlink(path)
            except OSError: pass
    segments, info = model.transcribe(
        io.BytesIO(data),
        language=(language or LANG) or None,
        vad_filter=True,
        beam_size=BEAM,
        initial_prompt=(context or None),
        condition_on_previous_text=False,
        compression_ratio_threshold=2.2,   # drop over-repetitive (hallucinated) segments
        no_speech_threshold=0.6,
    )
    text = _clean(" ".join(s.text.strip() for s in segments))
    return text, float(getattr(info, "duration", 0.0) or 0.0)


async def _read_capped(file: UploadFile, limit: int = MAX_AUDIO_BYTES) -> bytes:
    """Read an upload with a hard byte ceiling so one request can't exhaust RAM.
    Reads limit+1 and refuses (413) if the body exceeds the cap."""
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")
    return data


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language: str = Form(""), context: str = Form("")):
    global inflight_n, queued_n
    data = await _read_capped(file)
    if not data or len(data) < 1200:
        REQS.labels("empty").inc()
        return {"text": "", "next_ms": recommended_ms()}
    queued_n += 1; QUEUE.set(queued_n)
    try:
        async with sem:
            queued_n -= 1; QUEUE.set(queued_n)
            inflight_n += 1; INFLIGHT.set(inflight_n)
            t0 = time.time()
            try:
                loop = asyncio.get_event_loop()
                text, dur = await loop.run_in_executor(None, _run, data, language, context)
                AUDIO.inc(dur)
                REQS.labels("ok").inc()
                return {"text": text, "next_ms": recommended_ms()}
            except Exception as e:
                REQS.labels("error").inc()
                return {"text": "", "error": str(e), "next_ms": recommended_ms()}
            finally:
                LAT.observe(time.time() - t0)
                inflight_n -= 1; INFLIGHT.set(inflight_n)
    except Exception:
        queued_n -= 1; QUEUE.set(queued_n)
        raise


# ---- Full-file mode: record the whole meeting, transcribe it in one pass -----
# The page uploads the complete recording on stop; we transcribe the WHOLE file
# (full acoustic + textual context = best quality, no chunk-boundary errors) as
# an async job so a long meeting does not time out the request. Poll the status.
_jobs = {}   # job_id -> {"status": pending|done|error, "text"/"error"}


# Audio preprocessing before Whisper. Music/noise is the #1 cause of Whisper
# errors + hallucinations; denoising can cut WER 60-75% on noisy audio. Chain:
# highpass (drop rumble / music bass), afftdn (FFT denoiser), loudnorm (level).
DENOISE = os.environ.get("DENOISE", "true").lower() in ("1", "true", "yes")
DENOISE_AF = os.environ.get(
    "DENOISE_AF", "highpass=f=90,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11")


def _preprocess(data: bytes):
    """webm/opus bytes -> denoised, normalized 16 kHz mono wav path (or None)."""
    if not DENOISE:
        return None
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False, dir=TMPD) as f:
        f.write(data); src = f.name
    wav = src + ".wav"
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
                        "-af", DENOISE_AF, "-ar", "16000", "-ac", "1", wav], check=True)
        return wav
    except Exception:
        return None
    finally:
        try: os.unlink(src)
        except OSError: pass


def _run_full(data: bytes, language: str, hint: str = ""):
    # `hint` = participant names / terms; fed as Whisper initial_prompt so it
    # spells proper nouns (names) the way the user expects — ASR mis-hears names
    # (out-of-vocabulary), and the LLM can't fix a name it doesn't know.
    if model is not None:                       # faster-whisper (local)
        wav = _preprocess(data)
        try:
            segments, info = model.transcribe(
                wav or io.BytesIO(data),
                # "auto" -> None = true Whisper language detection (needed so English
                # voice input isn't forced to Lithuanian). "" -> LANG (lt) keeps the
                # protocol's Lithuanian default; an explicit code (en/ru/…) is honored.
                language=(None if language == "auto" else (language or LANG)),
                vad_filter=True,
                beam_size=max(BEAM, 5),
                # condition_on_previous_text=False: feeding the previous segment
                # back as a prefix makes the decoder DRIFT on long audio (a wrong
                # segment reinforces itself into garbage in the tail) — confirmed
                # on the svogunas LT model where the last third degraded with True
                # and was clean with False. Independent segments = robust.
                condition_on_previous_text=False,
                initial_prompt=(hint.strip() or None),
                compression_ratio_threshold=2.4,     # slightly looser (catch repetition)
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,             # drop low-confidence hallucinated segments
                repetition_penalty=REP_PENALTY,      # discourage stuck/looping phrases
                no_repeat_ngram_size=NO_REPEAT_NGRAM,
            )
            return _clean(" ".join(s.text.strip() for s in segments))
        finally:
            if wav:
                try: os.unlink(wav)
                except OSError: pass
    return _run(data, language, hint)[0]         # cloud / transformers fallback


async def _do_full(job_id: str, data: bytes, language: str, hint: str = ""):
    async with sem:
        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, _run_full, data, language, hint)
            _jobs[job_id] = {"status": "done", "text": text}
            REQS.labels("ok").inc()
        except Exception as e:
            _jobs[job_id] = {"status": "error", "error": str(e)}
            REQS.labels("error").inc()


@app.post("/transcribe_full")
async def transcribe_full(file: UploadFile = File(...), language: str = Form(""), hint: str = Form("")):
    data = await _read_capped(file)
    if not data or len(data) < 1200:
        return {"job_id": "", "error": "empty audio"}
    if len(_jobs) > 200:                          # simple cap: drop finished jobs
        for k in [k for k, v in _jobs.items() if v.get("status") in ("done", "error")][:100]:
            _jobs.pop(k, None)
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "pending"}
    asyncio.create_task(_do_full(job_id, data, language, hint))
    return {"job_id": job_id}


@app.get("/transcribe_status/{job_id}")
def transcribe_status(job_id: str):
    return _jobs.get(job_id, {"status": "unknown"})


# ---- OpenAI-compatible STT endpoint -----------------------------------------
# Drop-in replacement for stt-proxy so OpenWebUI's built-in voice input / audio
# transcription can use OUR local Lithuanian model (svogunas) instead of routing
# audio to OpenRouter. Point OpenWebUI's audio.stt.openai.api_base_url at
# `http://gp-transcribe:8000/v1`. Synchronous (voice clips are short); returns the
# OpenAI shape `{"text": ...}`. License-gated like every other working endpoint.
# Optional Bearer-key check: set GP_STT_API_KEYS (comma-separated) and put the same
# value in OpenWebUI's audio.stt.openai.api_key; empty => open (internal net + license).
STT_API_KEYS = [k.strip() for k in os.environ.get("GP_STT_API_KEYS", "").split(",") if k.strip()]


def _stt_key_ok(request: Request) -> bool:
    if not STT_API_KEYS:
        return True
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth[:7].lower() == "bearer " else auth.strip()
    return any(hmac.compare_digest(token, k) for k in STT_API_KEYS)


@app.post("/v1/audio/transcriptions")
async def openai_transcriptions(request: Request, file: UploadFile = File(...), model: str = Form(""),
                                language: str = Form(""), response_format: str = Form("json")):
    if not _stt_key_ok(request):
        return PlainTextResponse("invalid api key", status_code=401)
    data = await _read_capped(file)
    if not data or len(data) < 500:
        return {"text": ""}
    # OpenWebUI voice input sends no language -> auto-detect (so English works, not
    # just Lithuanian). An explicit code from the client (e.g. a language selector)
    # is passed through and honored.
    lang = (language or "").strip() or "auto"
    t0 = time.time()
    async with sem:
        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, _run_full, data, lang, "")
            REQS.labels("ok").inc()
        except Exception as e:
            REQS.labels("error").inc()
            return PlainTextResponse("transcription error: %s" % e, status_code=500)
        finally:
            LAT.observe(time.time() - t0)
    if response_format in ("text", "srt", "vtt"):
        return PlainTextResponse(text)
    return {"text": text}


# ---- Transcribe from a URL: any downloadable link, or a SharePoint/OneDrive ---
# sharing link (fetched via Microsoft Graph client-credentials, same app reg as
# kb-admin). The file is downloaded server-side and transcribed locally.
SP_TENANT = os.environ.get("SHAREPOINT_TENANT_ID", "")
SP_CLIENT = os.environ.get("SHAREPOINT_CLIENT_ID", "")
SP_SECRET = os.environ.get("SHAREPOINT_CLIENT_SECRET", "")
_gtok = {"v": "", "exp": 0.0}


def _graph_token():
    if _gtok["v"] and _gtok["exp"] - 60 > time.time():
        return _gtok["v"]
    import requests
    r = requests.post(
        f"https://login.microsoftonline.com/{SP_TENANT}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": SP_CLIENT,
              "client_secret": SP_SECRET, "scope": "https://graph.microsoft.com/.default"},
        timeout=30)
    r.raise_for_status()
    d = r.json()
    _gtok["v"] = d["access_token"]
    _gtok["exp"] = time.time() + int(d.get("expires_in", 3600))
    return _gtok["v"]


def _is_public_http_url(url: str) -> bool:
    """SSRF guard for the plain (non-SharePoint) fetch branch: allow only
    http/https resolving to a PUBLIC IP. Blocks internal Docker services
    (postgres, gliner, open-webui-dk...), loopback, link-local and cloud metadata
    (169.254.169.254) so a user-supplied URL cannot pivot into the internal net."""
    try:
        import ipaddress
        import socket
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        port = p.port or (443 if p.scheme == "https" else 80)
        for _fam, _t, _pr, _c, sockaddr in socket.getaddrinfo(
                p.hostname, port, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(sockaddr[0])
            if not ip.is_global or ip.is_reserved:
                return False
        return True
    except Exception:
        return False


def _download_url(url: str) -> bytes:
    import requests
    is_sp = ("sharepoint.com" in url) or ("1drv.ms" in url) or ("-my.sharepoint" in url) or ("/:v:/" in url) or ("/:f:/" in url)
    if is_sp:
        if not (SP_TENANT and SP_CLIENT and SP_SECRET):
            raise RuntimeError("SharePoint not configured (SHAREPOINT_* env missing)")
        enc = "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        # Fixed Graph host + short-lived token scoped to graph.microsoft.com only.
        r = requests.get(f"https://graph.microsoft.com/v1.0/shares/{enc}/driveItem/content",
                         headers={"Authorization": "Bearer " + _graph_token()},
                         timeout=180, allow_redirects=True)
    else:
        # Arbitrary user-supplied URL: block non-public targets and refuse to follow
        # redirects (a public URL could otherwise 302 to 169.254.169.254 / internal).
        if not _is_public_http_url(url):
            raise RuntimeError("URL neleidžiama (turi būti viešas http(s) adresas).")
        r = requests.get(url, timeout=180, allow_redirects=False)
        if 300 <= r.status_code < 400:
            # YouTube short links / streaming sites redirect; we don't follow (SSRF).
            raise RuntimeError("Nuoroda nukreipia kitur (pvz. YouTube/srautinės paslaugos). "
                               "Naudokite „Pradėti“ ir pasirinkite YouTube lango/garso įrašymą.")
        r.raise_for_status()
        # Size guard (DoS): reject an over-large declared body before buffering it.
        _cl = int(r.headers.get("content-length") or 0)
        _max = int(os.getenv("GP_STT_URL_MAX_BYTES", str(1024 * 1024 * 1024)))
        if _cl and _cl > _max:
            raise RuntimeError(f"Failas per didelis ({_cl} B > {_max} B).")
        # A page URL (YouTube watch, article...) returns HTML, not a media file —
        # feeding that to ffmpeg gives a cryptic "Invalid data" error. Detect it and
        # point the user at the screen-capture path instead.
        ctype = r.headers.get("content-type", "").lower()
        head = r.content[:64].lstrip().lower()
        if "text/html" in ctype or head.startswith(b"<!doctype") or head.startswith(b"<html"):
            raise RuntimeError("Nuoroda yra tinklalapis, ne tiesioginis medijos failas "
                               "(pvz. YouTube). Tiesioginė nuoroda turi baigtis .mp3/.mp4/.wav "
                               "ir pan. YouTube įrašymui naudokite „Pradėti“ ir pasirinkite lango įrašymą.")
        return r.content
    r.raise_for_status()
    return r.content


async def _do_url(job_id: str, url: str, language: str, hint: str = ""):
    async with sem:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, _download_url, url)
            if not data or len(data) < 1200:
                raise RuntimeError("downloaded file is empty or too small")
            text = await loop.run_in_executor(None, _run_full, data, language, hint)
            _jobs[job_id] = {"status": "done", "text": text}
            REQS.labels("ok").inc()
        except Exception as e:
            _jobs[job_id] = {"status": "error", "error": str(e)[:300]}
            REQS.labels("error").inc()


@app.post("/transcribe_url")
async def transcribe_url(url: str = Form(...), language: str = Form(""), hint: str = Form("")):
    if not url.strip():
        return {"job_id": "", "error": "empty url"}
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "pending"}
    asyncio.create_task(_do_url(job_id, url.strip(), language, hint))
    return {"job_id": job_id}


# ---- Reversible pseudonymisation for the protocol path (names <-> GP_ tokens) --
# The page calls /mask on the transcript, runs the correction/summary LLM on the
# masked text (so the external LLM sees only tokens), then /restore to put the
# real names back. The mapping lives in memory for GP_MAP_TTL (default 30 min).
_maps = {}   # map_id -> (mapping, expiry)
MAP_TTL = int(os.environ.get("GP_MAP_TTL", "1800"))


@app.post("/mask")
async def mask_ep(text: str = Form(...)):
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="text too large")
    loop = asyncio.get_event_loop()
    masked, mp = await loop.run_in_executor(None, pseudo.mask, text)
    now = time.time()
    for k, (m, e) in list(_maps.items()):
        if e < now:
            _maps.pop(k, None)
    mid = uuid.uuid4().hex
    _maps[mid] = (mp, now + MAP_TTL)
    return {"masked": masked, "map_id": mid, "n": len(mp)}


@app.post("/restore")
async def restore_ep(text: str = Form(...), map_id: str = Form("")):
    ent = _maps.get(map_id)
    return {"text": pseudo.restore(text, ent[0]) if ent else text}


# ---- Protocol LLM (correction / summary) with reversible masking, BYPASSING ---
# OpenWebUI's gp-pipeline. That one-way filter re-runs gliner and would mask our
# GP_ tokens back to [PERSON] (the tokens sit in person-name slots), destroying
# the round-trip. So we mask -> call the LLM directly (OpenRouter) -> restore
# here. The external LLM only ever sees GP_ tokens; names are restored in-house.
LLM_BASE  = os.environ.get("PROTOCOL_LLM_BASE", "https://openrouter.ai/api/v1").rstrip("/")
LLM_MODEL = os.environ.get("PROTOCOL_MODEL", "google/gemini-2.5-flash")
_llm_key_cache = {"v": ""}


def _llm_key():
    if not _llm_key_cache["v"]:
        _llm_key_cache["v"] = CLOUD_KEY or _key_from_owui("openrouter")
    return _llm_key_cache["v"]


# The protocol page's model dropdown offers OpenWebUI *workspace models* (e.g.
# "Konspektuotojas") whose id is NOT a provider id and which carry their own base
# model + system prompt in OWUI's `model` table. Because /llm bypasses OWUI, we
# must resolve that ourselves: follow base_model_id to a real provider id and pull
# the custom model's system prompt — otherwise a workspace model silently
# degraded to plain LLM_MODEL with no system prompt (its whole identity lost).
_model_cache = {}   # owui_id -> (real_model_id, system_prompt, expiry)
MODEL_CACHE_TTL = int(os.environ.get("GP_MODEL_CACHE_TTL", "300"))


def _resolve_owui_model(model_id: str):
    """(real_provider_model_id, system_prompt). A provider id (has '/') is used
    as-is with no system prompt. A workspace id is looked up in OWUI's `model`
    table: follow base_model_id to a provider id, and take the first non-empty
    params.system along the chain (the workspace model's own prompt)."""
    mid = (model_id or "").strip()
    if not mid:
        return LLM_MODEL, ""
    if "/" in mid:
        return mid, ""
    now = time.time()
    hit = _model_cache.get(mid)
    if hit and hit[2] > now:
        return hit[0], hit[1]
    real, system = LLM_MODEL, ""
    try:
        import json as _json
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            dbname=os.environ.get("POSTGRES_DB", "guardprompt"),
            user=os.environ.get("POSTGRES_USER", "postgres"),
            password=os.environ.get("POSTGRES_PASSWORD", ""),
        )
        cur = conn.cursor()
        cur_id, seen = mid, set()
        for _ in range(5):                       # bounded chain walk
            cur.execute("SELECT base_model_id, params FROM model WHERE id=%s", (cur_id,))
            row = cur.fetchone()
            if not row:
                break
            base, params = row
            p = params if isinstance(params, dict) else (_json.loads(params) if params else {})
            if not system and p.get("system"):
                system = p["system"]
            if not base:
                break
            if "/" in base:
                real = base
                break
            if base in seen:
                break
            seen.add(base); cur_id = base
        conn.close()
    except Exception as e:
        print(f"[gp-transcribe] model resolve failed for {mid}: {e}", flush=True)
    _model_cache[mid] = (real, system, now + MODEL_CACHE_TTL)
    return real, system


# Placeholder-preservation rule — ALWAYS enforced in the system message so the LLM
# never drops/renumbers our name tokens (the round-trip depends on it).
_PH_RULE = ("The text may contain placeholders like [[GP1]], [[GP2]] that stand for redacted "
            "sensitive terms (not necessarily names). Keep every such placeholder EXACTLY as-is "
            "(same number, same brackets) — do not translate, renumber, merge, remove it, or "
            "treat it as a participant's name.")


def _or_chat(model: str, user_content: str, system: str = "") -> str:
    import requests
    msgs = []
    if system.strip():
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user_content})
    r = requests.post(LLM_BASE + "/chat/completions",
                      headers={"Authorization": "Bearer " + _llm_key(), "Content-Type": "application/json"},
                      json={"model": model, "temperature": 0, "messages": msgs}, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# Fallback instruction for the "build protocol" call when the user left the prompt
# field EMPTY *and* the chosen model has no system prompt of its own — otherwise the
# model would just get a bare transcript and echo it. When the model DOES carry a
# system prompt (e.g. "Konspektuotojas"), that prompt does the job and we send no
# instruction. The correction call always passes a non-empty prompt, so it is
# unaffected.
DEFAULT_PROTOCOL_PROMPT = (
    "Iš žemiau pateikto susitikimo transkripto parenk aiškų, struktūruotą protokolą TA "
    "PAČIA kalba kaip transkriptas. Skyriai: Dalyviai, Aptartos temos, Sprendimai, "
    "Užduotys (su atsakingais ir terminais, jei minima). Būk faktiškas, nieko neišgalvok.")


@app.post("/llm")
async def llm_ep(prompt: str = Form(""), text: str = Form(...), model: str = Form("")):
    if not text.strip():
        return {"text": ""}
    if len(text) > MAX_TEXT_CHARS or len(prompt) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="text too large")
    loop = asyncio.get_event_loop()
    # Fail CLOSED here: /llm sends the (masked) transcript to an EXTERNAL LLM
    # (OpenRouter). If the NER backend is down, masking couldn't run, so refuse
    # rather than egress raw special-category PII. (/mask, which stays same-origin,
    # keeps the lenient default.)
    try:
        masked, mp = await loop.run_in_executor(None, lambda: pseudo.mask(text, strict=True))
    except pseudo.MaskUnavailable:
        return {"text": "", "error": "Pseudonimizavimas nepasiekiamas — protokolas neapdorotas "
                                     "(jautri informacija nebūtų paslėpta). Bandykite vėliau."}
    real, sysprompt = await loop.run_in_executor(None, _resolve_owui_model, model)
    p = prompt.strip()
    if not p and not sysprompt.strip():
        p = DEFAULT_PROTOCOL_PROMPT     # empty field + prompt-less model -> built-in default
    content = (p + "\n\n" + masked) if p else masked   # p empty => rely on model's system prompt
    # Enforce the placeholder rule ONLY when placeholders actually exist. Appending
    # this English rule to the system prompt unconditionally degraded the model's
    # Lithuanian markdown formatting (sections merged) even when nothing was masked.
    system_full = sysprompt.strip()
    if mp:
        system_full = ((system_full + "\n\n") if system_full else "") + _PH_RULE
    try:
        out = await loop.run_in_executor(None, _or_chat, real, content, system_full)
    except Exception as e:
        return {"text": "", "error": str(e)[:300]}
    return {"text": pseudo.restore(out, mp)}
