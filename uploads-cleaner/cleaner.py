import json
import os
import time
import logging
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
log = logging.getLogger("cleaner")

DB_URL = os.environ["DB_URL"]
DELETE_AFTER_DAYS = int(os.environ.get("DELETE_AFTER_DAYS", "30"))
RUN_HOUR = int(os.environ.get("RUN_HOUR", "2"))
TRIGGER_FILE = "/tmp/run_now"
SWEEP_FILE = "/tmp/sweep_now"

# Filesystem deletes are confined under this root (the OpenWebUI data volume). A
# file whose DB `path` resolves outside it is NOT removed from disk, so a bad/rogue
# path can never delete host-mounted files elsewhere.
UPLOAD_ROOT = os.path.realpath(os.environ.get("CLEANER_UPLOAD_ROOT", "/app/backend/data"))
# Safety floor: if the KB/note protect-set comes back EMPTY while there are more
# than this many deletion candidates, abort — an empty protect-set usually means the
# OpenWebUI schema drifted (KB/note refs moved) and deleting would destroy attached
# files. Set CLEANER_ALLOW_EMPTY_PROTECT=1 for a genuinely empty deployment.
EMPTY_PROTECT_FLOOR = int(os.environ.get("CLEANER_EMPTY_PROTECT_FLOOR", "5"))
ALLOW_EMPTY_PROTECT = os.environ.get("CLEANER_ALLOW_EMPTY_PROTECT", "false").lower() in ("1", "true", "yes", "on")

# Qdrant: OpenWebUI stores every file's chunks in one multi-tenant collection.
# Each point payload has metadata.file_id = <file id>, so we delete by that filter.
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QDRANT_FILES_COLLECTION = os.environ.get("QDRANT_FILES_COLLECTION", "open-webui_files")
# Qdrant now requires an api-key on the REST API (internal-net hardening). Sent on
# every direct call; empty (dev without the key) just omits it and still works.
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")


def _qdrant_headers():
    h = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        h["api-key"] = QDRANT_API_KEY
    return h


def delete_qdrant_points(file_id):
    """Delete all vector points for a file from Qdrant. Best-effort: never raises."""
    url = f"{QDRANT_URL}/collections/{QDRANT_FILES_COLLECTION}/points/delete?wait=true"
    body = json.dumps(
        {"filter": {"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]}}
    ).encode()
    req = urllib.request.Request(
        url, data=body, headers=_qdrant_headers(), method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status == 200:
                log.info(f"Qdrant deleted points: {file_id}")
                return True
            log.warning(f"Qdrant delete HTTP {r.status} for {file_id}")
    except urllib.error.HTTPError as e:
        log.warning(f"Qdrant delete failed {file_id}: HTTP {e.code} {e.read()[:200]}")
    except Exception as e:
        log.warning(f"Qdrant delete failed {file_id}: {e}")
    return False


def parse_db_url(url):
    url = url.replace("postgresql://", "")
    userpass, rest = url.split("@")
    user, password = userpass.split(":")
    hostport, db = rest.split("/")
    host, port = (hostport.split(":") + ["5432"])[:2]
    return dict(host=host, port=int(port), dbname=db, user=user, password=password)


def qdrant_scroll_file_ids():
    """Return the set of all distinct metadata.file_id values in the files collection.
    Raises on HTTP/connection failure so the caller can abort safely."""
    ids = set()
    url = f"{QDRANT_URL}/collections/{QDRANT_FILES_COLLECTION}/points/scroll"
    offset = None
    while True:
        payload = {"limit": 256, "with_payload": ["metadata.file_id"], "with_vector": False}
        if offset is not None:
            payload["offset"] = offset
        req = urllib.request.Request(
            # BUG: hardcoded headers omitted the Qdrant api-key, so every scroll got
            # 401 and orphan_sweep aborted before deleting a single stale vector.
            # Qdrant now requires the key on ALL REST calls (internal-net hardening).
            url, data=json.dumps(payload).encode(),
            headers=_qdrant_headers(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        result = data.get("result", {})
        for p in result.get("points", []):
            md = (p.get("payload") or {}).get("metadata") or {}
            fid = md.get("file_id")
            if fid:
                ids.add(fid)
        offset = result.get("next_page_offset")
        if not offset:
            break
    return ids


def orphan_sweep():
    """One-off: delete Qdrant vectors whose file_id no longer exists in the DB
    'file' table (leftovers from deletions before Qdrant cleanup existed)."""
    log.info("Orphan sweep: comparing Qdrant file_ids against DB 'file' table")
    conn = psycopg2.connect(**parse_db_url(DB_URL))
    cur = conn.cursor()
    cur.execute("SELECT id FROM file")
    db_ids = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()

    try:
        q_ids = qdrant_scroll_file_ids()
    except Exception as e:
        log.warning(f"Orphan sweep aborted (Qdrant scan failed): {e}")
        return

    orphans = q_ids - db_ids
    log.info(f"DB files: {len(db_ids)}, Qdrant files: {len(q_ids)}, orphans: {len(orphans)}")
    for fid in sorted(orphans):
        delete_qdrant_points(fid)
    log.info(f"Orphan sweep done. Removed orphan vectors for {len(orphans)} file(s)")


def run_cleanup():
    log.info(f"Starting cleanup: files older than {DELETE_AFTER_DAYS} days")
    cutoff = int((datetime.now() - timedelta(days=DELETE_AFTER_DAYS)).timestamp())

    conn = psycopg2.connect(**parse_db_url(DB_URL))
    cur = conn.cursor()

    cur.execute("SELECT file_id FROM knowledge_file")
    kb_ids = {row[0] for row in cur.fetchall()}
    log.info(f"KB protected: {len(kb_ids)}")

    # Also protect files ATTACHED TO NOTES (note.data.files[].id) — the meeting
    # protocol attaches its audio recording to the note so it is preserved. Without
    # this, the cleaner would delete the recording after DELETE_AFTER_DAYS and leave
    # a broken attachment on the note.
    note_ids = set()
    cur.execute("SELECT data FROM note")
    for (data,) in cur.fetchall():
        try:
            d = data if isinstance(data, dict) else (json.loads(data) if data else {})
            for f in (d.get("files") or []):
                fid = f.get("id") if isinstance(f, dict) else None
                if fid:
                    note_ids.add(fid)
        except Exception:
            pass
    log.info(f"Note-attached protected: {len(note_ids)}")

    cur.execute("SELECT id, filename, created_at, path FROM file WHERE created_at < %s", (cutoff,))
    old_files = cur.fetchall()
    log.info(f"Old files found: {len(old_files)}")

    # Safety floor: a suspiciously empty protect-set with many delete candidates most
    # likely means the OpenWebUI schema changed and our KB/note queries silently
    # matched nothing — deleting here would wipe files that are actually attached.
    if (len(kb_ids) + len(note_ids)) == 0 and len(old_files) > EMPTY_PROTECT_FLOOR and not ALLOW_EMPTY_PROTECT:
        log.error(f"ABORT: 0 protected files but {len(old_files)} deletion candidates — "
                  f"likely an OpenWebUI schema mismatch (KB/note refs not found). Refusing "
                  f"to delete. Set CLEANER_ALLOW_EMPTY_PROTECT=1 if this deployment truly "
                  f"has no KBs or notes.")
        cur.close()
        conn.close()
        return

    deleted = skipped = 0
    for file_id, filename, cat, path in old_files:
        if file_id in kb_ids or file_id in note_ids:
            log.info(f"SKIP ({'KB' if file_id in kb_ids else 'note'}): {filename}")
            skipped += 1
            continue
        if path and os.path.exists(path):
            # Confine to the uploads volume: never remove a file that resolves
            # outside UPLOAD_ROOT (symlink/rogue-path guard).
            rp = os.path.realpath(path)
            if rp != UPLOAD_ROOT and not rp.startswith(UPLOAD_ROOT + os.sep):
                log.warning(f"Disk delete refused (outside upload root): {path}")
            else:
                try:
                    os.remove(path)
                    log.info(f"Disk deleted: {path}")
                except Exception as e:
                    log.warning(f"Disk delete failed {path}: {e}")
        cur.execute("DELETE FROM file WHERE id = %s", (file_id,))
        log.info(f"DB deleted: {filename}")
        # Remove the file's vectors from Qdrant (orphan embeddings otherwise)
        delete_qdrant_points(file_id)
        deleted += 1

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"Done. Deleted: {deleted}, skipped KB: {skipped}")


def is_run_time():
    return datetime.now().hour == RUN_HOUR


if __name__ == "__main__":
    log.info(f"Cleaner started. Runs daily at {RUN_HOUR:02d}:00, deletes files older than {DELETE_AFTER_DAYS} days")
    last_run_day = None

    while True:
        now = datetime.now()

        # Orphan sweep trigger — one-off Qdrant cleanup
        if os.path.exists(SWEEP_FILE):
            os.remove(SWEEP_FILE)
            log.info("Sweep trigger detected - running orphan sweep now")
            orphan_sweep()

        # Trigger failas — paleisti iš karto
        if os.path.exists(TRIGGER_FILE):
            os.remove(TRIGGER_FILE)
            log.info("Trigger file detected - running cleanup now")
            run_cleanup()
            last_run_day = now.day

        # Kasdieninis paleidimas
        elif is_run_time() and last_run_day != now.day:
            run_cleanup()
            last_run_day = now.day

        time.sleep(60)
