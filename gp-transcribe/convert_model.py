"""Bake the Lithuanian ASR model into the image as a CTranslate2 model dir.

We use `svogunas/whisper-large-v3-turbo-lt` — a whisper-large-v3-turbo fine-tune
trained on the LIEPA-3 corpus (~7.23M clips, VDU/CLARIN-LT) for high-accuracy
Lithuanian transcription. It emits lowercase / no punctuation (LIEPA-3 style), which
the LLM correction step restores. It ships as a transformers checkpoint, so we convert
it to CT2 float16 here (build time, one egress) so faster-whisper can run it with
VAD + our params. Idempotent: skips if already converted.
"""
import os
import subprocess

SRC = os.environ.get("LT_MODEL_SRC", "svogunas/whisper-large-v3-turbo-lt")
DST = os.environ.get("LT_MODEL_DST", "/models/svogunas-lt-ct2")

if os.path.exists(os.path.join(DST, "model.bin")):
    print(f"[convert] {DST} already present — skipping", flush=True)
    raise SystemExit(0)

os.makedirs(os.path.dirname(DST), exist_ok=True)
print(f"[convert] converting {SRC} -> {DST} (CT2 float16) …", flush=True)
subprocess.run([
    "ct2-transformers-converter", "--model", SRC, "--output_dir", DST,
    "--quantization", "float16", "--force", "--copy_files", "preprocessor_config.json",
], check=True)

# faster-whisper loads tokenizer.json from the model dir; the CT2 converter does
# not emit one, so materialise it from the same repo's fast tokenizer.
from transformers import WhisperTokenizerFast
WhisperTokenizerFast.from_pretrained(SRC).save_pretrained(DST)
print(f"[convert] done — {DST}", flush=True)
