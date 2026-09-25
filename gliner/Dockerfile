FROM python:3.11-slim
WORKDIR /app
# CUDA torch: this container now serves TWO models — gliner NER and the bge-m3
# encoder behind /injection. Measured for the encoder: 23 ms/sentence on GPU vs
# 182 ms on CPU, and 1.2 s vs 20.8 s for a ~500-sentence document. gliner NER
# gains from the same device. app.py falls back to CPU if no GPU is present, so
# the image still runs on a CPU-only host — just slower.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu128 \
 && pip install --no-cache-dir gliner sentence-transformers fastapi "uvicorn[standard]" prometheus_client
COPY app.py .
ENV MODEL_ID=urchade/gliner_multi_pii-v1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
