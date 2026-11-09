FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy the whole context so app.py and its runtime package are included together
# (.dockerignore keeps secrets/junk out of the context).
COPY . .

# Non-root: this proxy only reads roles + relays; it needs no privileges.
RUN useradd -u 10001 -m appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
