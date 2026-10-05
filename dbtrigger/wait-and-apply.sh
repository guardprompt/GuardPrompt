#!/bin/sh
# Laukia kol OpenWebUI sukurs 'chat' lentelę, tada pritaiko dedup trigger'į.
# Idempotentu — saugu vykdyti kiekvieno `docker compose up` metu.

export PGPASSWORD="$POSTGRES_PASSWORD"
PSQL="psql -h postgres -U $POSTGRES_USER -d $POSTGRES_DB"

echo "[db-trigger-init] laukiu 'chat' lentelės..."
until $PSQL -tAc "SELECT to_regclass('public.chat');" 2>/dev/null | grep -q '^chat$'; do
    echo "[db-trigger-init] 'chat' dar nėra, kartoju po 5s"
    sleep 5
done

echo "[db-trigger-init] pritaikau trigger'į..."
$PSQL -f /apply.sql

echo "[db-trigger-init] baigta."
