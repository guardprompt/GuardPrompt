#!/usr/bin/env python3
"""
brand-kit-sync — mirror a SharePoint document library into the sandbox brand kit.

Pulls the official visual-identity assets (logos, brand PowerPoint templates,
photos, PDFs) from a SharePoint document library via Microsoft Graph and writes
them as plain FILES into the sandbox brand volume at BRAND_KIT_DEST
(default /home/user/.gpbrand/kit). gpdeck and the AI agent then use them locally.

By design this does NOT touch any Knowledge Base and does NOT pass the assets
through the anonymizer — brand identity is public-facing corporate material, and
anonymizing it would corrupt it (e.g. mask the company name in a template).

Config comes ONLY from environment (admin-controlled; not exposed to sandbox
users or the model):

  SHAREPOINT_TENANT_ID / SHAREPOINT_CLIENT_ID / SHAREPOINT_CLIENT_SECRET
      Azure app registration (client-credentials) in the SAME tenant as the site.
  BRAND_KIT_SITE_HOST      e.g. regitra.sharepoint.com
  BRAND_KIT_SITE_PATH      e.g. /sites/naujasintranetas
  BRAND_KIT_LIBRARY        document library (drive) display name; default: first
  BRAND_KIT_FOLDER         optional sub-folder path inside the library
  BRAND_KIT_DEST           destination dir; default /home/user/.gpbrand/kit
  BRAND_KIT_EXTENSIONS     comma list; default png,jpg,jpeg,gif,svg,webp,pptx,potx,pdf
  BRAND_KIT_INTERVAL       seconds; if >0 loop forever, else run once
  BRAND_KIT_MAX_MB         skip files larger than this (default 50)

Run once:   docker compose run --rm brand-kit-sync
Scheduled:  set BRAND_KIT_INTERVAL and run as a normal service.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

GRAPH = "https://graph.microsoft.com/v1.0"


def _env(name, default=None, required=False):
    v = os.getenv(name, default)
    if required and not v:
        sys.exit(f"[brand-kit] missing required env {name}")
    return v


def get_token(tenant, cid, secret):
    data = urllib.parse.urlencode({
        "client_id": cid,
        "client_secret": secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode()
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        return json.load(r)["access_token"]


def graph(path, tok):
    url = path if path.startswith("http") else GRAPH + path
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def graph_paged(path, tok):
    """Yield all items across @odata.nextLink pages."""
    url = path
    while url:
        page = graph(url, tok)
        for it in page.get("value", []):
            yield it
        url = page.get("@odata.nextLink")


def download(url, dest, tok):
    # downloadUrl is pre-authenticated (no header needed); other URLs need auth.
    req = urllib.request.Request(url)
    if "graph.microsoft.com" in url:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def walk(drive_id, item_path, tok, exts, dest_root, max_bytes, rel="", kept=None):
    """Recursively download matching files under a drive folder."""
    if item_path:
        enc = urllib.parse.quote(item_path)
        listing = f"/drives/{drive_id}/root:/{enc}:/children"
    else:
        listing = f"/drives/{drive_id}/root/children"
    # No $select: @microsoft.graph.downloadUrl is a TRANSIENT annotation Graph
    # omits whenever the response is constrained by $select (even if named in
    # it), which made every file skip (no downloadUrl) and the sync copy 0 files
    # silently. The default field set returns name/size/folder/file + downloadUrl.
    listing += "?$top=200"

    n_files = n_bytes = 0
    for it in graph_paged(listing, tok):
        name = it["name"]
        if it.get("folder"):
            sub = (item_path + "/" + name) if item_path else name
            f, b = walk(drive_id, sub, tok, exts, dest_root, max_bytes,
                        os.path.join(rel, name), kept)
            n_files += f
            n_bytes += b
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if exts and ext not in exts:
            continue
        if it.get("size", 0) > max_bytes:
            print(f"[brand-kit] skip (too big): {name}")
            continue
        url = it.get("@microsoft.graph.downloadUrl")
        if not url:
            continue
        dest = os.path.join(dest_root, rel, name)
        try:
            b = download(url, dest, tok)
            if kept is not None:
                kept.add(os.path.abspath(dest))
            n_files += 1
            n_bytes += b
            print(f"[brand-kit] {os.path.join(rel, name)}  ({b//1024} KB)")
        except Exception as e:
            print(f"[brand-kit] FAIL {name}: {e}")
    return n_files, n_bytes


def prune(dest_root, kept):
    """Mirror behaviour: delete local files NOT fetched this run (renamed or
    removed in SharePoint). Never touches the control JSON. Drops emptied
    sub-folders. Caller only prunes when >=1 file was fetched, so a 0-file run
    cannot wipe the kit."""
    protect = {"manifest.json", "kit_config.json", "kit_status.json"}
    removed = 0
    for root, _dirs, files in os.walk(dest_root, topdown=False):
        for fn in files:
            if fn in protect:
                continue
            p = os.path.join(root, fn)
            if os.path.abspath(p) not in kept:
                try:
                    os.remove(p)
                    removed += 1
                    print(f"[brand-kit] prune (gone): {os.path.relpath(p, dest_root)}")
                except OSError:
                    pass
        if root != dest_root:
            try:
                os.rmdir(root)  # succeeds only if now empty
            except OSError:
                pass
    return removed


def write_manifest(dest_root, images_exts):
    """Index the kit so gpdeck/the agent can discover assets."""
    images, templates, other = [], [], []
    for root, _dirs, files in os.walk(dest_root):
        for fn in files:
            if fn == "manifest.json":
                continue
            rel = os.path.relpath(os.path.join(root, fn), dest_root)
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
            if ext in images_exts:
                images.append(rel)
            elif ext in ("pptx", "potx"):
                templates.append(rel)
            else:
                other.append(rel)
    manifest = {"images": sorted(images), "templates": sorted(templates),
                "other": sorted(other), "updated": int(time.time())}
    with open(os.path.join(dest_root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def run_once():
    tenant = _env("SHAREPOINT_TENANT_ID", required=True)
    cid = _env("SHAREPOINT_CLIENT_ID", required=True)
    secret = _env("SHAREPOINT_CLIENT_SECRET", required=True)
    host = _env("BRAND_KIT_SITE_HOST", required=True)
    site_path = _env("BRAND_KIT_SITE_PATH", required=True).rstrip("/")
    library = _env("BRAND_KIT_LIBRARY", "")
    folder = _env("BRAND_KIT_FOLDER", "").strip("/")
    dest = _env("BRAND_KIT_DEST", "/home/user/.gpbrand/kit")
    exts = {e.strip().lower() for e in _env(
        "BRAND_KIT_EXTENSIONS",
        "png,jpg,jpeg,gif,svg,webp,pptx,potx,pdf").split(",") if e.strip()}
    image_exts = {"png", "jpg", "jpeg", "gif", "svg", "webp"}
    max_bytes = int(float(_env("BRAND_KIT_MAX_MB", "50")) * 1024 * 1024)

    tok = get_token(tenant, cid, secret)
    # root site = just the hostname; a sub-site = host:/sites/<name>
    site_ref = f"/sites/{host}" if site_path in ("", "/") \
        else f"/sites/{host}:{site_path}"
    site = graph(site_ref, tok)
    sid = site["id"]
    print(f"[brand-kit] site: {site.get('displayName')} ({host}{site_path})")

    drives = graph(f"/sites/{sid}/drives", tok)["value"]
    drive = None
    if library:
        drive = next((d for d in drives if d.get("name") == library), None)
        if not drive:
            sys.exit(f"[brand-kit] library '{library}' not found; have: "
                     f"{[d.get('name') for d in drives]}")
    else:
        drive = drives[0]
    print(f"[brand-kit] library: {drive.get('name')}")

    os.makedirs(dest, exist_ok=True)
    kept = set()
    n, b = walk(drive["id"], folder, tok, exts, dest, max_bytes, kept=kept)
    # Only prune when something was fetched — else a 0-file run would delete the
    # whole kit (kept empty -> everything "unseen").
    removed = prune(dest, kept) if kept else 0
    m = write_manifest(dest, image_exts)
    print(f"[brand-kit] done: {n} files, {b//1024//1024} MB | "
          f"images={len(m['images'])} templates={len(m['templates'])} "
          f"other={len(m['other'])} removed={removed} -> {dest}")


def main():
    interval = int(_env("BRAND_KIT_INTERVAL", "0") or "0")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[brand-kit] ERROR: {e}", file=sys.stderr)
        if interval <= 0:
            break
        print(f"[brand-kit] sleeping {interval}s")
        time.sleep(interval)


if __name__ == "__main__":
    main()
