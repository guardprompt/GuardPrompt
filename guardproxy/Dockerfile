FROM python:3.11-slim

# 🧱 Reikalingi įrankiai (Nginx + supervisor + net-tools + curl)
RUN apt-get update && \
    apt-get install -y nginx supervisor curl net-tools netcat-openbsd && \
    apt-get clean

# 🌍 Aplankas aplikacijai
WORKDIR /app

# 📜 Kodo kopijavimas
COPY . .

# 🧠 Fallback paketai, jei requirements.txt neegzistuoja
RUN pip install --no-cache-dir fastapi uvicorn httpx requests zstandard || true

# 🧩 Supervisord konfigūracija
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 🕒 "Wait-for" skriptas NGINX startui
RUN echo '#!/bin/bash\n\
set -e\n\
host="open-webui-dk"\n\
port=8080\n\
timeout=600\n\
elapsed=0\n\
echo "[WAIT] Checking if $host:$port is available..."\n\
while ! nc -z $host $port && [ $elapsed -lt $timeout ]; do\n\
  echo "[WAIT] Still waiting for $host:$port... ($elapsed s)";\n\
  sleep 5;\n\
  elapsed=$((elapsed+5));\n\
done;\n\
echo "[OK/Timeout] Starting NGINX (after $elapsed s)."\n\
exec nginx -g "daemon off;"' > /wait-and-start-nginx.sh && chmod +x /wait-and-start-nginx.sh

# 🔓 Portai: NGINX (80) + FastAPI (8010)
EXPOSE 80 8010

# ✅ HEALTHCHECK: tikrina ar abu servisai atsako HTTP 200
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fs http://localhost:80 || curl -fs http://localhost:8010 || exit 1

# 🏁 Startuojam abu procesus
CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
