# Uploads cleaner — packages baked in (no runtime pip, works offline)
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir psycopg2-binary
COPY cleaner.py /app/cleaner.py
CMD ["python", "-u", "/app/cleaner.py"]
