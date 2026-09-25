FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY warmup.py /app/warmup.py
CMD ["python", "-u", "/app/warmup.py"]
