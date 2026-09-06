# GP Transcribe — faster-whisper (large-v3-turbo) chunked transcription engine.
# NVIDIA CUDA + cuDNN base because ctranslate2 (faster-whisper) needs libcudnn.
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/* && update-ca-certificates

RUN python3 -m venv /venv
ENV PATH=/venv/bin:$PATH

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      faster-whisper \
      transformers accelerate \
      fastapi "uvicorn[standard]" python-multipart prometheus_client nvidia-ml-py

# Cloud backend deps (OpenRouter call + reading the key from OpenWebUI's DB).
# Separate layer so it rebuilds fast without touching the torch/whisper layers.
RUN pip install --no-cache-dir requests psycopg2-binary

# Bake the Lithuanian CT2 model into the image (svogunas LIEPA-3 turbo fine-tune —
# best raw LT of everything benchmarked). One egress at build; offline afterwards.
COPY convert_model.py .
RUN python convert_model.py

# Copy the whole context so app.py, pseudo.py, gp_license.py and their runtime
# package are all included together.
COPY . .

# faster-whisper downloads any stock CT2 model to the HF cache; persist via a volume.
ENV HF_HOME=/root/.cache/huggingface
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
