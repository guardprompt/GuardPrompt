# ---- Base image ----
FROM python:3.11-slim

# ---- Environment setup ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    RUNNING_IN_DOCKER=1

# ---- Workdir ----
WORKDIR /app

# --- Playwright ---
RUN pip install playwright
RUN playwright install-deps
RUN playwright install chromium
RUN pip install beautifulsoup4 lxml
# -------------------

# ---- System dependencies ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- Copy source ----
COPY . .

# ---- Python dependencies ----
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        fastapi \
        uvicorn[standard] \
        requests \
        langdetect \
        python-multipart \
        zstandard \
        pydantic \
        httpx

# ---- Expose port ----
EXPOSE 8005

# ---- Entrypoint ----
CMD ["uvicorn", "dk_anonymizer:app", "--host", "0.0.0.0", "--port", "8005"]
