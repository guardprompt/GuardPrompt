#!/bin/bash
set -e
host="open-webui-dk"
port=8080

echo "[WAIT] Checking if $host:$port is available..."
while ! nc -z $host $port; do
  echo "[WAIT] Still waiting for $host:$port..."
  sleep 5
done

echo "[OK] $host:$port is up. Starting NGINX."
exec nginx -g "daemon off;"
