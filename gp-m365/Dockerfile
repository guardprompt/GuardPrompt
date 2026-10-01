FROM python:3.12-slim

WORKDIR /app

# Non-root: the service holds the Entra client secret; run unprivileged.
RUN useradd -m -u 10014 gpm365

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# .dockerignore keeps secrets/junk out of this context.
COPY . .

USER gpm365
EXPOSE 8015

# Single worker: state (OBO cache, budgets, semaphore) is in-process. Scale via replicas
# behind guardproxy if ever needed, not extra workers (which would fragment the state).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8015", "--workers", "1"]
