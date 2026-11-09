> 🌐 **Language / Kalba:** **English** · [Lietuvių](KB-ADMIN-APP-PLAN.lt.md)

# KB Admin App — MVP plan (no code)

A management console (separate app) with which OpenWebUI administrators curate
knowledge bases from external sources (Confluence / Jira / SharePoint) and assign
access to users/groups. It orchestrates `oikb` + OpenWebUI access.

> Status: ✅ **IMPLEMENTED AND RUNNING** (kb-admin container up at
> `127.0.0.1:8090`, ~1580-line FastAPI: auth / confluence / jira / sharepoint /
> oikb_runner / openwebui / db / license). This document stands as the
> architecture/decision rationale. Default `AUTH_MODE=openwebui`.
> Related: oikb runs as a CLI subprocess inside kb-admin (§13.11).

---

## 1. Purpose and actors

- **Actor:** OpenWebUI administrator (there may be several). Must be:
  1. an **LDAP** user (of our organisation) — *if LDAP is enabled*,
  2. holding the **OpenWebUI admin** role.
- **Goal:** the admin finds an external resource → sets who may see it → sets the
  sync interval → launches it → sees the job list, can edit/delete. Everything is
  audited.

---

## 2. Overall flow

```
[KB Admin App — separate container, on the openwebui_net network]

  Login (LDAP bind, if enabled) ──► OpenWebUI role==admin ──► session (cookie)
        │
        ▼
  UNIVERSAL search (single field):
     - external resources: Confluence spaces / Jira projects / SharePoint
     - + existing oikb jobs (kb_jobs) — so you see what is already configured
     - per-result indicators: reachable / already assigned / status
        │
        ▼
  After picking a resource:
     1. Access (checkboxes): Everyone / Group(s) / Individuals (subjects from OpenWebUI)
     2. Sync interval (dropdown): 10 min / 1 h / 4 h / 12 h / 24 h
     3. KB name: suggested automatically, the ADMIN MAY EDIT it before saving
        │
        ▼
  [Create job] ──► (async, BackgroundTask, returns status=processing)
     a) creates a KB (1 resource = 1 KB) under the name the admin confirmed
     b) sets KB access_control per audience (DECLARATIVELY)
     c) runs oikb sync in the background → updates kb_jobs.status in the DB
        │
        ▼
  Logs (audit + sync results)
  Job list: view / edit (access, interval, name) /
            delete (+oikb reset) / cancel a stuck one (kill pid)
```

---

## 3. Components

| Layer | Technology | Role |
|---|---|---|
| Backend | FastAPI (Python) | API, orchestration, async jobs, scheduler |
| DB | existing Postgres, new `kbadmin` schema | source of truth for jobs + audit |
| Frontend | plain HTML/JS (served by FastAPI) | search, checkboxes, job table |
| Execution | `oikb` (CLI app in the container, or exec) | the actual sync |
| Container | new compose service `kb-admin` | isolated, openwebui_net |

---

## 4. Authentication, authorization, session

**Auth modes (env `AUTH_MODE`):**
- `ldap` — full: **LDAP bind** (org directory) + **OpenWebUI admin** role. BOTH.
- `openwebui` — **without LDAP** (this deployment has no LDAP): OpenWebUI admin
  role only (+ the password is checked via OpenWebUI). The default for a
  dev / no-LDAP environment.
- `dev` — a local allowlist (`ADMIN_FALLBACK_EMAILS`) — testing only.

Every mode ALWAYS requires the **OpenWebUI admin** role — that is the common guard.

**Session:** after login — an **HttpOnly, Secure, SameSite=Strict signed cookie**
(server-side session in the DB, or a signed JWT with `SESSION_SECRET` from env).
No token in browser JS, so the plain HTML/JS never holds secrets. Short TTL.

**Basic brute-force protection:**
- A login-attempt limit per IP/user (e.g. 5/5 min) → temporary block.
- An audit record for every failed login.
- If `AUTH_MODE=ldap`, LDAP policies (lockout) add to this; the app limit still
  acts as the first line of defence.

---

## 5. Data model (schema `kbadmin`)

### `kb_jobs` — curation jobs (source of truth)
| Field | Type | Description |
|---|---|---|
| id | uuid | job id |
| source_type | text | confluence / jira / sharepoint |
| source_id | text | **numeric space ID** (what oikb needs) |
| source_key | text | human-readable key (e.g. "SD") — shown to the admin |
| source_title | text | human-readable title |
| kb_id | uuid | id of the created OpenWebUI KB |
| kb_name | text | KB name (confirmed/edited by the admin) |
| audience_type | text | all / groups / users |
| audience_ids | jsonb | list of group/user ids |
| interval | text | 10m / 1h / 4h / 12h / 24h |
| status | text | processing / active / paused / error |
| pid | integer | PID of the running oikb process (kill/cancel) |
| error_message | text | failure reason for the admin (e.g. "Bad Atlassian token") |
| last_sync_at | timestamptz | time of the last sync |
| last_result | jsonb | +added/-deleted/errors |
| created_by | text | admin (LDAP/email) |
| created_at | timestamptz | |

> **Space ID vs Key:** verified — oikb uses the **numeric space ID**
> (`confluence:65857`), NOT the key ("SD"). We store **both** — the ID for
> execution, the Key/Title to show the admin.

### `audit_log` — admin actions (who/what/when)
| Field | Type | Description |
|---|---|---|
| id | bigserial | |
| ts | timestamptz | when |
| actor | text | admin (LDAP/email) |
| action | text | login / login_failed / create_job / edit_job / delete_job / manual_sync / access_change / cancel_job |
| job_id | uuid | related job (if any) |
| details | jsonb | before/after values, audience, etc. |

---

## 6. Universal search + resource indicators

- **A single search field** searches in parallel:
  1. **External sources** (Confluence spaces, Jira projects, SharePoint),
  2. **Existing `kb_jobs`** (what is already configured) — to avoid duplicates.
- **Indicators next to results** (small):
  - 🟢 source reachable + token valid
  - 🔴 unreachable / bad token / not configured (env missing)
  - ✓ "already assigned" (a `kb_jobs` exists) → an "edit" button instead of "create"
- **Source health check:** for each type (Confluence/Jira/SharePoint) the app does
  a light ping (e.g. list spaces) → shows whether the tokens/URLs are correct.

---

## 7. Access model + DECLARATIVE permission sync

- **OpenWebUI access = per KB, NOT per file** → **1 resource = 1 KB**.
- subjects are taken from OpenWebUI (`/api/v1/users/`, `/api/v1/groups/`).

**Verified API (v0.9.6–v0.10.2 — uses `access_grants`, NOT the `access_control` json;
the `access_grants` format did not change in 0.10; 0.10.2 requires write access to
attach a file to a KB — kb-admin uses the admin key, so OK):**
- Set: `POST /api/v1/knowledge/{id}/access/update` body `{"access_grants":[...]}`
- Grant dict: `{principal_type, principal_id, permission}`
  (principal_type=`user`|`group`; principal_id=id or `"*"`; permission=`read`|`write`)
- **audience → grants:**
  - **Everyone (public):** `[{"principal_type":"user","principal_id":"*","permission":"read"}]`
  - **Group(s):** `{"principal_type":"group","principal_id":<gid>,"permission":"read"}`
  - **Individuals:** `{"principal_type":"user","principal_id":<uid>,"permission":"read"}`
  - **Private (default-deny):** `[]`
- The KB is created (`POST /api/v1/knowledge/create`) immediately private
  (`access_grants=[]`); access is applied with a separate `/access/update` (matches
  the default-deny order, §13.2).

**⚠️ Access Sync Trap (important):** permissions are applied NOT only at creation but
**declaratively on every sync** (before or right after oikb):
- kb-admin **re-pushes** `kb_jobs.audience_ids` → OpenWebUI KB access.
- This guarantees kb-admin is the **source of truth for permissions** on these KBs.
- Consequence: to change these (curated) KBs' permissions you must use the **console**,
  not OpenWebUI directly — otherwise the next sync overwrites it. (Show the admin a
  warning.)

---

## 8. Sync orchestration (async, resilient)

- **The app schedules it itself** (its own scheduler per `interval`), NOT an oikb
  daemon.
- **Async execution (FastAPI BackgroundTasks):**
  1. POST "create/sync" → returns `status=processing` immediately.
  2. In the background: (a) ensure KB + access (declaratively), (b) `oikb sync`,
     (c) update `kb_jobs.status`, `last_result`, `error_message`.
  3. Large spaces (minutes–hours) cause no HTTP timeout — everything is backgrounded.
- **PID / cancellation:** oikb runs as a subprocess → `pid` stored in the DB → the
  admin can "kill" a stuck job; after kill status=error.
- **Rate limiting / interruptions:** the first sync of a large resource may hit HTTP 429.
  - oikb does an **incremental** sync (SHA-256) → a retry after an interruption
    **continues** (uploads only the missing items), not from scratch.
  - keep `concurrency` low (2) to reduce 429s.
  - 429/error → status=error + error_message; the admin sees it and can retry.
  - (Verify exactly how oikb reacts to 429 — see §12.)
- **Deletion:** `oikb reset --kb-id ...` (goes through the OpenWebUI API) → delete
  the KB → remove the `kb_jobs` row → audit.
  - **Qdrant:** no extra cleanup needed. Verified live — an OpenWebUI file delete via
    the API **clears Qdrant itself** (files+knowledge 1→0). Condition: all deletes go
    through the OpenWebUI API (oikb reset does), NOT straight from the DB.
- Files in these KBs are **protected** from uploads-cleaner (they are `knowledge_file`).

---

## 9. Deployment (compose) — all secrets via env

```yaml
  kb-admin:
    build: ./kb-admin        # FastAPI + frontend + oikb CLI
    container_name: kb-admin
    environment:
      - AUTH_MODE=${KBADMIN_AUTH_MODE:-openwebui}   # ldap | openwebui | dev
      - SESSION_SECRET=${KBADMIN_SESSION_SECRET}
      - OPEN_WEBUI_URL=http://open-webui-dk:8080
      - OPEN_WEBUI_API_KEY=${OPEN_WEBUI_API_KEY}
      - DB_URL=postgresql://.../guardprompt          # schema kbadmin
      # NOTE: oikb runs as a subprocess (not an HTTP daemon), so
      # OIKB_API_KEY is not needed — removed.
      # LDAP (only if AUTH_MODE=ldap)
      - LDAP_URL=${LDAP_URL:-}
      - LDAP_BIND_DN=${LDAP_BIND_DN:-}
      - LDAP_BASE_DN=${LDAP_BASE_DN:-}
      # source tokens — from .env (Confluence/Jira/SharePoint)
    ports:
      - "127.0.0.1:8090:8000"
    depends_on: [postgres, open-webui-dk]
    networks: [openwebui_net]
    cap_drop: [NET_RAW]
```

**All sensitive data** (tokens, SESSION_SECRET, LDAP, API keys) — **env only**
(`.env`, not in code, not in git; `.env.example` with empty values).

---

## 10. Security

- Admin only (OpenWebUI role always; LDAP if enabled). Every action → `audit_log`.
- Brute-force limit (§4). Session is an HttpOnly signed cookie, short TTL.
- The app holds powerful tokens → internal network, port `127.0.0.1`, secrets in env.

---

## 11. Phases

1. **MVP:** auth (openwebui role; LDAP exception) + universal Confluence search
   + indicators + OpenWebUI users/groups + create job (KB with an editable name
   + declarative access + async first sync) + logs.
2. **Management:** job list + edit/delete/cancel (pid) + scheduler
   (10m/1h/4h/12h/24h) + periodic permission re-push.
3. **Expansion:** SharePoint (+Azure app + admin consent), Jira.

---

## 13. Critical safeguards and decisions (agreed in review)

### 13.1 Stale-delete "sanity guard" 🔴
If a source is deleted/archived OR the token loses access → the sync returns
0/far fewer → the incremental step would **delete the whole KB**. Guard: if the file
count drops **>50%** or to **0** → do NOT delete, `status=paused` + alert the admin
("confirm the mass delete"). Threshold configurable.

### 13.2 Default-deny KB creation order 🔴
Order: (1) create the KB **private**, (2) set access_control, (3) **only then** sync.
There is never a window where content is loaded while the KB is still public.

### 13.3 Audience "drift" 🔴
Before every access re-push (§7) validate `audience_ids` against the current
OpenWebUI users/groups. Missing subjects → mark "stale", skip, notify the admin.

### 13.4 Global sync queue / concurrency 🔴 (the most important "no-stall" item)
- **Max N syncs at once** (e.g. 2), the rest wait in a queue. Without this, 20 jobs
  on "1h" firing at once hammer the GPU/Atlassian → the system buckles.
- **A separate lane** for "big initial" syncs, so a long initial one does not block
  incremental refreshes.
- Big initial syncs — auto-scheduled to **off-hours**.

### 13.5 Zombie jobs after a restart 🔴
On app startup: reconcile — `status=processing` with no live PID → `error` (or
re-run). Schedule iterations missed during downtime → run at startup.

### 13.6 Large spaces (5000+ pages) strategy
- **A dry-run always shows the page count before commit**; > threshold → warning.
- Two paths for the admin: **narrow it** (Confluence CQL/label filter) / **allow it
  throttled** (low concurrency, off-hours).
- `max-file-size` skips huge attachments.

### 13.7 Dry-run preview before commit
Before creating a job — `oikb sync --dry-run` → shows "+N will be added". The admin
sees the scope and does not accidentally stall the system.

### 13.8 Manual control
A "Sync now" button (off-schedule) + Pause/Resume (`status=paused`) + Cancel
(kill `pid`) for every job.

### 13.9 Error notifications
A sync fails → the admin finds out: in-app indication + optional webhook
(`NOTIFY_URL` env). Not "find out a week later".

### 13.10 Content quality — document + verify
oikb pulls the page text; attached PDFs/Excel/images may not come through;
tables→txt lose structure. **Verify what oikb actually takes**, set expectations for
the admin. (Decision depends on the verification result.)

### 13.11 Architecture: kb-admin = the sole orchestrator
- The existing **`oikb` daemon compose service is DISABLED/REMOVED** — otherwise two
  schedulers (oikb daemon + kb-admin scheduler) would conflict.
- oikb is used as a **CLI subprocess inside the kb-admin image** (for `pid`
  kill/cancel). kb-admin controls EVERYTHING.

### 13.12 Rejected (NOT doing)
- ~~Anonymization at ingestion~~ — the OpenWebUI pipeline handles it, nothing extra needed.
- ~~A compliance "who sees what" report~~ — not now (possible later).
- ~~A separate Qdrant purge~~ — OpenWebUI clears it via the API itself (verified).

---

## 14. Verify before/while building (so nothing is guessed)

- [ ] OpenWebUI exact `access_control` format (read/write, group_ids, user_ids) —
      live via the API.
- [ ] OpenWebUI groups/users API fields.
- [ ] How oikb is invoked from the app (subprocess for pid vs daemon `/sync`).
- [ ] **oikb behaviour on HTTP 429** (retry/backoff?) and whether the incremental
      sync really continues after an interruption.
- [ ] Whether oikb-created KBs keep access_control after a sync (they should; if it
      overwrites — hence the declarative re-push, §7).
- [ ] LDAP specifics (bind DN template, email/uid attributes) — when available.
- [ ] Confluence **CQL/label filter** to narrow large spaces (oikb support).
- [ ] What oikb actually takes from a page (attachments? tables?) — §13.10.
- [x] ~~Whether oikb reset clears Qdrant~~ — VERIFIED: OpenWebUI clears it via the API.

## 15. Troubleshooting — KB attached but the model ignores it

**Symptom:** a model has a knowledge base attached, but it answers from general
knowledge / says "there is no information in the provided documents". The chat's
assistant message shows **no sources**, even though the KB clearly has content.

### 15.1 Function Calling must be **Legacy** (the #1 cause) 🔴

OpenWebUI retrieves a model's KB **only when the model's Function Calling mode is
`Legacy`**. In `Default`/`Native` mode the KB is handed to the LLM as a *tool the
model must call itself* — external models served through a proxy (e.g. Gemini via
OpenRouter) do not invoke that tool, so retrieval never runs and the answer has no
sources.

An OpenWebUI upgrade changed the **default** from legacy injection to native
tool-calling, so setups that "always worked" silently stop retrieving after an
update — nothing in the KB or the data changed.

**Fix:** Workspace → Models → *(model)* → Advanced Params → **Function Calling →
Legacy** → Save. Do this for **every** model that uses a knowledge base. Verify:
after asking a question, a **source/citation** must appear under the answer.

> Because retrieval never runs in native mode, this masks everything else — hybrid
> search, the reranker, the relevance threshold and KB access all look fine while
> producing zero sources. Always confirm Function Calling = Legacy first.

### 15.2 Files added inside a KB **subfolder** are not indexed into the KB

In the folder/directory view, a file dropped into a **subfolder** is embedded only
into the per-file collection, not into the KB's own collection, so KB-scoped
retrieval cannot see it (the file still shows in the tree and is linked to the KB).

**Fix:** add files at the **KB root**, or re-index the file into the KB collection:
`POST /api/v1/retrieval/process/file` with body
`{"file_id": "<id>", "collection_name": "<kb_id>"}` (admin token). Files ingested by
oikb (SharePoint/Confluence/Jira sync) are unaffected — they land in the KB
collection correctly; only files added manually into a subfolder need this.
