"""Read-only queries over gp_audit (the proxies' Postgres). SELECT only — this service
never writes. gp_audit columns: ts, user_id, owner, client_ip, model, role, content,
bytes, masked_spans."""
import asyncpg

from . import config

_POOL: asyncpg.Pool | None = None


async def start():
    global _POOL
    if not config.DB_URL:
        raise RuntimeError("GP_DB_URL not set — cannot read gp_audit")
    _POOL = await asyncpg.create_pool(config.DB_URL, min_size=1, max_size=5, command_timeout=30)
    # our own tiny tables (admin-editable in the UI) — the only tables gp-usage writes.
    async with _POOL.acquire() as c:
        await c.execute("CREATE TABLE IF NOT EXISTS gp_usage_names ("
                        "account text PRIMARY KEY, name text NOT NULL, "
                        "updated_at timestamptz NOT NULL DEFAULT now())")
        # read-only viewers: OWUI users granted VIEW access (no editing). Admins are not
        # here (they come from OWUI role==admin or GP_USAGE_ADMIN_EMAILS).
        await c.execute("CREATE TABLE IF NOT EXISTS gp_usage_access ("
                        "email text PRIMARY KEY, "
                        "added_at timestamptz NOT NULL DEFAULT now())")
        # accounts hidden from the identify panel (declutter). gp_audit is read-only, so
        # "delete row" = hide the account here; reversible via the "show hidden" toggle.
        await c.execute("CREATE TABLE IF NOT EXISTS gp_usage_hidden ("
                        "account text PRIMARY KEY, "
                        "hidden_at timestamptz NOT NULL DEFAULT now())")


async def viewers() -> set:
    """Emails granted read-only access (lowercased)."""
    async with _POOL.acquire() as c:
        rows = await c.fetch("SELECT email FROM gp_usage_access ORDER BY email")
    return {r["email"] for r in rows}


async def add_viewer(email: str):
    e = (email or "").strip().lower()
    if not e:
        return
    async with _POOL.acquire() as c:
        await c.execute("INSERT INTO gp_usage_access (email) VALUES ($1) "
                        "ON CONFLICT (email) DO NOTHING", e)


async def del_viewer(email: str):
    e = (email or "").strip().lower()
    async with _POOL.acquire() as c:
        await c.execute("DELETE FROM gp_usage_access WHERE email = $1", e)


async def hidden() -> set:
    """Accounts hidden from the identify panel."""
    async with _POOL.acquire() as c:
        rows = await c.fetch("SELECT account FROM gp_usage_hidden")
    return {r["account"] for r in rows}


async def hide_account(account: str):
    a = (account or "").strip()
    if not a:
        return
    async with _POOL.acquire() as c:
        await c.execute("INSERT INTO gp_usage_hidden (account) VALUES ($1) "
                        "ON CONFLICT (account) DO NOTHING", a)


async def unhide_account(account: str):
    async with _POOL.acquire() as c:
        await c.execute("DELETE FROM gp_usage_hidden WHERE account = $1", (account or "").strip())


async def names() -> dict:
    async with _POOL.acquire() as c:
        rows = await c.fetch("SELECT account, name FROM gp_usage_names")
    return {r["account"]: r["name"] for r in rows}


async def set_name(account: str, name: str):
    async with _POOL.acquire() as c:
        if name and name.strip():
            await c.execute(
                "INSERT INTO gp_usage_names (account, name) VALUES ($1, $2) "
                "ON CONFLICT (account) DO UPDATE SET name = excluded.name, updated_at = now()",
                account, name.strip())
        else:
            await c.execute("DELETE FROM gp_usage_names WHERE account = $1", account)


async def identify(days: int = 90, include_hidden: bool = False):
    """Per account: activity + first/last seen + newest content sample/IP/models — the
    signals an admin needs to recognise who it is. Bounded to a window + DISTINCT ON for
    the latest sample (far cheaper than array_agg over all history). Accounts an admin has
    hidden are dropped unless include_hidden (the 'show hidden' toggle)."""
    q = r"""
      WITH base AS (
        SELECT COALESCE(
                 substring(user_id from '"account_uuid":"([0-9a-fA-F-]+)"'),
                 substring(user_id from '"device_id":"([0-9a-fA-F-]+)"'),
                 user_id) AS account,
               ts, client_ip, model, content
        FROM gp_audit
        WHERE ts >= now() - ($1::int || ' days')::interval
      ),
      agg AS (
        SELECT account, count(*)::int AS req, max(ts) AS last_seen, min(ts) AS first_seen,
               string_agg(DISTINCT COALESCE(model,'?'), ', ') AS models
        FROM base GROUP BY account
      ),
      latest AS (
        SELECT DISTINCT ON (account) account, client_ip AS last_ip,
               left(regexp_replace(COALESCE(content,''), '\s+', ' ', 'g'), 220) AS sample
        FROM base ORDER BY account, ts DESC
      )
      SELECT a.account, a.req, a.last_seen, a.first_seen, a.models, l.last_ip, l.sample
      FROM agg a LEFT JOIN latest l USING (account)
      ORDER BY a.req DESC
    """
    async with _POOL.acquire() as c:
        rows = await c.fetch(q, days)
    hide = set() if include_hidden else await hidden()
    return [{"account": r["account"], "req": r["req"],
             "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
             "first_seen": r["first_seen"].isoformat() if r["first_seen"] else None,
             "models": r["models"], "last_ip": r["last_ip"], "sample": r["sample"] or ""}
            for r in rows if r["account"] not in hide]


async def close():
    if _POOL:
        await _POOL.close()


async def _exists() -> bool:
    async with _POOL.acquire() as c:
        return await c.fetchval("SELECT to_regclass('public.gp_audit') IS NOT NULL")


async def aggregates(days: int):
    """Per day/user/model totals for the window (bounded: days x users x models)."""
    # user_id may be a JSON blob from Claude clients ({"device_id","account_uuid",
    # "session_id"}) — session_id changes every session, so grouping on the raw string
    # splits one user into many rows. Normalise to the STABLE account_uuid when present
    # (regex extract, no jsonb cast so malformed values never throw); else keep the raw
    # user_id (e.g. an OWUI email).
    q = """
      SELECT to_char(date_trunc('day', ts AT TIME ZONE $2), 'YYYY-MM-DD') AS day,
             COALESCE(substring(user_id from '"account_uuid":"([0-9a-fA-F-]+)"'),
                      substring(user_id from '"device_id":"([0-9a-fA-F-]+)"'),
                      user_id, '(nežinomas)') AS "user",
             COALESCE(model, '(nenurodyta)')  AS model,
             count(*)::int                    AS req,
             COALESCE(sum(bytes),0)::bigint   AS bytes,
             COALESCE(sum(masked_spans),0)::bigint AS spans,
             -- exact token usage from the response (NULL on old/no-usage rows)
             COALESCE(sum(prompt_tokens),0)::bigint     AS ptok,
             COALESCE(sum(completion_tokens),0)::bigint AS ctok,
             -- bytes of rows that have NO exact usage yet -> frontend estimates those
             COALESCE(sum(bytes) FILTER (WHERE prompt_tokens IS NULL AND completion_tokens IS NULL),0)::bigint AS bytes_est,
             max(ts)                          AS last_ts
      FROM gp_audit
      WHERE ts >= now() - ($1::int || ' days')::interval
      GROUP BY 1, 2, 3
      ORDER BY 1
    """
    async with _POOL.acquire() as c:
        rows = await c.fetch(q, days, config.TZ)
    return [dict(r) | {"last_ts": r["last_ts"].isoformat() if r["last_ts"] else None} for r in rows]


async def review(days: int, user: str | None, model: str | None, proxy: str = "all",
                 search: str | None = None, page: int = 1, page_size: int = 25):
    """Paged content review with free-text search over content/model/IP/account."""
    _uid = ("COALESCE(substring(user_id from '\"account_uuid\":\"([0-9a-fA-F-]+)\"'), "
            "substring(user_id from '\"device_id\":\"([0-9a-fA-F-]+)\"'), user_id)")
    conds = ["ts >= now() - ($1::int || ' days')::interval"]
    args: list = [days]
    if user and user != "all":
        args.append(user); conds.append(f"{_uid} = ${len(args)}")
    if model and model != "all":
        args.append(model); conds.append(f"model = ${len(args)}")
    # proxy is derived from the model name (no proxy column): claude/anthropic vs the rest.
    if proxy == "claude":
        conds.append("(model ILIKE '%claude%' OR model ILIKE '%anthropic%')")
    elif proxy == "openai":
        conds.append("NOT (model ILIKE '%claude%' OR model ILIKE '%anthropic%')")
    if search and search.strip():
        args.append("%" + search.strip() + "%")
        i = len(args)
        conds.append(f"(content ILIKE ${i} OR model ILIKE ${i} OR client_ip ILIKE ${i} OR {_uid} ILIKE ${i})")
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    args.append(page_size); lim = f"${len(args)}"
    args.append((page - 1) * page_size); off = f"${len(args)}"
    q = f"""
      SELECT count(*) OVER()::int AS total, ts,
             COALESCE({_uid}, '(nežinomas)') AS "user", COALESCE(model,'(nenurodyta)') AS model,
             role, client_ip, COALESCE(bytes,0)::bigint AS bytes,
             COALESCE(masked_spans,0)::int AS spans,
             COALESCE(prompt_tokens,0)::int AS ptok, COALESCE(completion_tokens,0)::int AS ctok,
             (prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL) AS has_tok,
             content
      FROM gp_audit
      WHERE {' AND '.join(conds)}
      ORDER BY ts DESC
      LIMIT {lim} OFFSET {off}
    """
    async with _POOL.acquire() as c:
        rows = await c.fetch(q, *args)
    total = rows[0]["total"] if rows else 0
    return {
        "total": total, "page": page, "page_size": page_size,
        "rows": [{"ts": r["ts"].isoformat(), "user": r["user"], "model": r["model"], "role": r["role"],
                  "ip": r["client_ip"], "bytes": r["bytes"], "spans": r["spans"],
                  "ptok": r["ptok"], "ctok": r["ctok"], "has_tok": r["has_tok"],
                  "content": r["content"] or ""}
                 for r in rows],
    }
