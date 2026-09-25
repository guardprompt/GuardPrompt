# gp-usage — proxy usage dashboard. Light image (no GPU, no oikb): just FastAPI +
# asyncpg (read-only gp_audit) + httpx (OpenRouter prices) + itsdangerous (session).
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
EXPOSE 8016
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8016"]
