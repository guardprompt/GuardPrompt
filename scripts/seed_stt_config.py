# -*- coding: utf-8 -*-
"""Seed OpenWebUI's Speech-to-Text config so built-in voice input uses the LOCAL
gp-transcribe engine (Lithuanian svogunas model, auto-detects EN too, no external
egress). Runs INSIDE the open-webui container (which has
psycopg2 + DATABASE_URL + the DB network):

    docker cp scripts/seed_stt_config.py open-webui-dk:/tmp/seed_stt.py
    docker exec -e GP_STT_API_KEYS=<key> open-webui-dk python /tmp/seed_stt.py
    docker restart open-webui-dk    # so OpenWebUI reloads the audio config

Idempotent UPSERT of three config keys (engine + base URL + api key). The api key
must equal gp-transcribe's GP_STT_API_KEYS (empty there => open, and this seeds an
empty key too). Touches nothing else.
"""
import json
import os
import sys
import time

import psycopg2

BASE_URL = os.environ.get("GP_STT_BASE_URL", "http://gp-transcribe:8000/v1")
# GP_STT_API_KEYS may be comma-separated (gp-transcribe accepts several); OpenWebUI
# sends ONE, so seed the first. Empty => open endpoint (internal net + license gate).
API_KEY = (os.environ.get("GP_STT_API_KEYS", "") or "").split(",")[0].strip()

VALUES = {
    "audio.stt.engine": "openai",
    "audio.stt.openai.api_base_url": BASE_URL,
    "audio.stt.openai.api_key": API_KEY,
}


def main():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[seed-stt] ERROR: DATABASE_URL not set (run inside the open-webui container)", flush=True)
        sys.exit(2)
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    ts = int(time.time())
    for k, v in VALUES.items():
        cur.execute(
            "INSERT INTO config (key, value, updated_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at",
            (k, json.dumps(v), ts))
    conn.commit()
    cur.close()
    conn.close()
    print("[seed-stt] OpenWebUI STT -> %s (api key %s)" % (BASE_URL, "set" if API_KEY else "EMPTY/open"), flush=True)


if __name__ == "__main__":
    main()
