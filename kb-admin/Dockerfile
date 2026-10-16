# KB Admin App — based on the official oikb image so the bundled oikb CLI is the
# verified-working build (PyPI oikb wheel has a stale Jira endpoint → 410 Gone).
# Pinned by DIGEST, not :latest — this image's source is PATCHED below, so a
# moving tag silently moves the patch targets and breaks the build on someone
# else's machine. That already happened: upstream added follow_redirects and the
# old `assert "follow_redirects" not in s` aborted every fresh build.
# To move to a newer oikb, get the digest, bump it here, then rebuild and confirm
# the patch below still applies (it fails loudly if a target is gone):
#   docker buildx imagetools inspect ghcr.io/open-webui/oikb:latest --format '{{.Manifest.Digest}}'
FROM ghcr.io/open-webui/oikb@sha256:e61c1beef9fe91d2f00ca8612e847eacc7d579e2e8e258f40fb1ef3e2891e8d4
USER root
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# NOTE: `pip` here is the SYSTEM pip (/usr/local/bin) — the oikb base's `.venv`
# ships no pip binary, so PATH falls through to it. Our deps therefore land in
# system site-packages, NOT in `.venv`. The CMD below runs uvicorn from the SAME
# system python so it can see them (a bare `uvicorn`/`python` resolves to
# `.venv/bin` first and would miss e.g. itsdangerous). oikb stays a subprocess
# (`.venv/bin/oikb` via PATH), so it is unaffected.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Patch oikb's SharePoint connector. The base image is `oikb:latest` (a MOVING
# tag), so upstream drifts under us — this patch must be IDEMPOTENT and survive
# oikb absorbing our fixes. Each step is applied only if not already present.
#  1) follow_redirects: Graph /content returns a 302 to a pre-authenticated
#     download URL; without it every download fails ("Redirect response '302'").
#     NOTE: current oikb:latest already ships this — the old `assert "follow_redirects"
#     not in s` then hard-failed the build ("already patched"). Now a no-op if present.
#  2) checksum = file CONTENT hash (quickXorHash) instead of eTag[:16]. SharePoint
#     eTag is "{GUID},<version>"; truncating drops the version, and with library
#     versioning OFF edits NEVER re-sync. quickXorHash changes iff the bytes change.
#  3) optional SHAREPOINT_FOLDER env → sync ONE subfolder (set per-sync by
#     kb-admin at runtime). Empty/unset = whole library (drive root). Nothing
#     deployment-specific is baked in; the folder comes from the env at run time.
# Steps 2 & 3 still FAIL LOUDLY if their target is gone but not yet applied, so a
# real upstream change is caught instead of silently shipping broken sync logic.
RUN python - <<'PY'
import oikb.connectors.sharepoint as m, pathlib
p = pathlib.Path(m.__file__)
s = orig = p.read_text()

# 1) follow_redirects — idempotent; upstream may already include it.
if "follow_redirects" not in s:
    s = s.replace("timeout=60.0,",
                  "timeout=60.0,\n            follow_redirects=True,", 1)

# 2) content-hash checksum (quickXorHash) instead of truncated eTag.
if "quickXorHash" not in s:
    before = s
    s = s.replace(
        'etag = (item.get("eTag") or item.get("cTag", "")).strip(\'"\')',
        'etag = ((item.get("file") or {}).get("hashes") or {}).get("quickXorHash") '
        'or (item.get("cTag") or item.get("eTag") or "").strip(\'"\')', 1)
    s = s.replace('checksum=etag[:16] if etag else ""',
                  'checksum=etag if etag else ""', 1)
    assert s != before, "checksum patch target not found — oikb sharepoint.py changed"

# 3) optional SHAREPOINT_FOLDER subfolder sync (default = whole library / root).
if "SHAREPOINT_FOLDER" not in s:
    before = s
    s = s.replace(
        '        self._walk_folder("/", "", entries)',
        '        import os as _os\n'
        '        _start = _os.environ.get("SHAREPOINT_FOLDER", "").strip("/")\n'
        '        # prefix must equal the start folder so ManifestEntry.path is\n'
        '        # relative to the DRIVE ROOT (read_file downloads /root:/<path>/<file>).\n'
        '        self._walk_folder(_start or "/", _start, entries)', 1)
    assert s != before, "SHAREPOINT_FOLDER patch target not found — oikb sharepoint.py changed"

if s != orig:
    p.write_text(s)
    print("oikb sharepoint connector patched (idempotent): "
          "follow_redirects + quickXorHash + SHAREPOINT_FOLDER")
else:
    print("oikb sharepoint connector already patched — nothing to do")
PY
# COPY . . (not selective) so the protected build's sibling pyarmor_runtime_*
# package is included too — pyarmor places it next to app/, not inside it.
COPY . .
ENTRYPOINT []
EXPOSE 8000
# Explicit system python (see the pip note above): a bare `uvicorn` runs from
# `.venv` and cannot import the app's deps.
CMD ["/usr/local/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
