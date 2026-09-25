# -*- coding: utf-8 -*-
"""Seed (install/update) the GuardPrompt "kas nusiųsta į modelį" native Filter
function into OpenWebUI's database.

OpenWebUI Filter functions live in the DB (unlike file-mounted pipelines), so a
fresh install has none — this script puts it there. It is meant to run INSIDE the
open-webui container (which has psycopg2 + DATABASE_URL + the DB network):

    docker cp pipelines/openwebui-functions/guardprompt_show_sent.py open-webui-dk:/tmp/gp_fn.py
    docker cp scripts/seed_openwebui_function.py                       open-webui-dk:/tmp/seed_fn.py
    docker exec -e GP_FN_SRC=/tmp/gp_fn.py open-webui-dk python /tmp/seed_fn.py
    docker restart open-webui-dk    # so OpenWebUI loads the newly-seeded function

Behaviour:
  - Owner must be an admin user. On a brand-new install none exists yet (the first
    signup becomes admin), so if there is no admin the script exits 2 with a hint —
    the caller re-runs it after the admin account is created.
  - Idempotent UPSERT: updates content/name/meta only. On an EXISTING row it PRESERVES
    the admin's valves, is_active and is_global (never clobbers their settings). A new
    row is created enabled + global.
"""
import json
import os
import re
import sys
import time

import psycopg2

# Defaults describe the "kas nusiųsta į modelį" filter so install.sh keeps working
# unchanged; every field can be overridden so the same seeder installs any filter.
# GP_FN_GLOBAL=false is what a per-model filter needs (e.g. the AI-label watermark,
# which must run only for the image model, not on every answer).
FUNCTION_ID = os.environ.get("GP_FN_ID", "guardprompt_kas_nusiusta_i_modeli")
FUNCTION_NAME = os.environ.get("GP_FN_NAME", "GuardPrompt — kas nusiųsta į modelį")
FUNCTION_TYPE = os.environ.get("GP_FN_TYPE", "filter")
FUNCTION_GLOBAL = os.environ.get("GP_FN_GLOBAL", "true").lower() in ("1", "true", "yes")
SRC = os.environ.get("GP_FN_SRC", "/tmp/gp_fn.py")


def parse_frontmatter(text: str) -> dict:
    """Pull title/author/version/description/required_open_webui_version from the
    leading module docstring (best-effort; every field has a fallback)."""
    fm = {}
    head = text[:1500]
    for key in ("title", "author", "version", "description",
                "required_open_webui_version"):
        m = re.search(rf"^\s*{key}:\s*(.+?)\s*$", head, re.MULTILINE)
        if m:
            fm[key] = m.group(1).strip()
    return fm


def main() -> int:
    if not os.path.exists(SRC):
        print(f"[seed] ERROR: function source not found at {SRC}", flush=True)
        return 1
    with open(SRC, encoding="utf-8") as f:
        content = f.read()

    fm = parse_frontmatter(content)
    short_desc = fm.get("description", "Po atsakymu parodo, kas (anonimizuota) iškeliavo į LLM.")
    meta = json.dumps({
        "description": short_desc,
        "manifest": {
            "title": fm.get("title", FUNCTION_NAME),
            "author": fm.get("author", "guardprompt"),
            "version": fm.get("version", "1.0"),
            "description": short_desc,
            "required_open_webui_version": fm.get("required_open_webui_version", "0.5.0"),
        },
    }, ensure_ascii=False)

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[seed] ERROR: DATABASE_URL not set (run inside the open-webui container)", flush=True)
        return 1
    # psycopg2 wants postgresql:// (SQLAlchemy sometimes uses postgresql+psycopg2://)
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")

    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        cur.execute("""SELECT id FROM "user" WHERE role = 'admin'
                       ORDER BY created_at ASC LIMIT 1""")
        row = cur.fetchone()
        if not row:
            print("[seed] No admin user yet. Create your admin account at "
                  "http://localhost:8080 first, then re-run this seed.", flush=True)
            return 2
        admin_id = row[0]
        now = int(time.time())

        # UPSERT — on conflict keep the admin's valves / is_active / is_global.
        cur.execute("""
            INSERT INTO function
                (id, user_id, name, type, content, meta,
                 created_at, updated_at, valves, is_active, is_global)
            VALUES
                (%(id)s, %(uid)s, %(name)s, %(type)s, %(content)s, %(meta)s,
                 %(now)s, %(now)s, NULL, TRUE, %(glob)s)
            ON CONFLICT (id) DO UPDATE SET
                content = EXCLUDED.content,
                name    = EXCLUDED.name,
                meta    = EXCLUDED.meta,
                updated_at = EXCLUDED.updated_at
        """, {"id": FUNCTION_ID, "uid": admin_id, "name": FUNCTION_NAME,
              "type": FUNCTION_TYPE, "content": content, "meta": meta, "now": now,
              "glob": FUNCTION_GLOBAL})

        # Report whether it was newly inserted or updated.
        cur.execute("SELECT is_active, is_global FROM function WHERE id = %s", (FUNCTION_ID,))
        act, glob = cur.fetchone()
        conn.commit()
        print(f"[seed] OK: function '{FUNCTION_ID}' upserted (owner={admin_id}, "
              f"active={act}, global={glob}, {len(content)} chars). "
              f"Restart open-webui to load it.", flush=True)
        return 0
    except Exception as e:
        conn.rollback()
        print(f"[seed] ERROR: {e}", flush=True)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
