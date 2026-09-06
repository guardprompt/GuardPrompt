# GuardPrompt OpenAI proxy — OpenAI-compatible gateway to OpenRouter with
# reversible pseudonymization. python:3.11-slim to match anonymizer/gliner/
# gp-claude-proxy: same Python minor lets it share the existing pyarmor runtime.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx asyncpg prometheus_client
COPY app.py pseudonymizer.py store.py bodywalk.py nerclient.py metrics.py person_noise.py /app/
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
