# GuardPrompt Claude proxy — packages baked in (no runtime pip, works offline).
# python:3.11-slim to match anonymizer/gliner: same Python minor means this
# container can share the existing pyarmor runtime when the anonymizer's rule
# modules get imported here in stage 2.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx asyncpg prometheus_client
COPY app.py pseudonymizer.py store.py bodywalk.py nerclient.py metrics.py person_noise.py /app/
EXPOSE 8006
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8006"]
