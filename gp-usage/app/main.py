"""gp-usage — proxy usage dashboard. Login-gated (OpenWebUI/LDAP, admin only), reads
gp_audit read-only, prices from OpenRouter. Serves a single-page dashboard."""
import asyncio
import pathlib

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import auth, config, db, pricing

app = FastAPI(title="gp-usage")
_STATIC = pathlib.Path(__file__).resolve().parent.parent / "static"


def _page(name: str) -> str:
    return (_STATIC / name).read_text(encoding="utf-8")


@app.on_event("startup")
async def _startup():
    await db.start()
    asyncio.create_task(pricing.loop())
    print("[gp-usage] started :8016 — auth=%s db=ok" % config.AUTH_MODE, flush=True)


@app.on_event("shutdown")
async def _shutdown():
    await db.close()


@app.get("/healthz")
async def healthz():
    return {"ok": True}


def _client_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return xff or (request.client.host if request.client else "?")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return _page("login.html")


@app.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    try:
        user = auth.login(email, password, _client_ip(request))
    except HTTPException as e:
        html = _page("login.html").replace("<!--ERR-->", f'<div class="err">{e.detail}</div>')
        return HTMLResponse(html, status_code=e.status_code)
    # relative redirects + cookie path "/" so the app works both at root (:8016) and
    # mounted under a reverse-proxy sub-path (/usage/) without knowing its prefix.
    resp = RedirectResponse("./", status_code=303)
    resp.set_cookie(auth.COOKIE_NAME, auth.make_cookie(user), max_age=config.SESSION_TTL,
                    httponly=True, samesite="lax", path="/")
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("login", status_code=303)
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        user = auth.require_admin(request)
    except HTTPException:
        return RedirectResponse("login", status_code=303)
    html = _page("index.html").replace("__WHO__", (user.get("name") or user.get("email") or "admin"))
    return HTMLResponse(html)


def _guard(request: Request):
    auth.require_admin(request)  # raises 401/403 -> FastAPI returns JSON error


@app.get("/api/data")
async def api_data(request: Request, days: int = 30):
    _guard(request)
    days = max(1, min(days, config.MAX_DAYS))
    rows = await db.aggregates(days)
    models = sorted({r["model"] for r in rows})
    prices = {m: round(pricing.eur_per_token(m), 10) for m in models}
    # merged name map: env GP_USAGE_USER_MAP first, DB (admin-edited in the UI) overrides.
    umap = dict(config.USER_MAP)
    umap.update(await db.names())
    return JSONResponse({
        "days": days,
        "rows": rows,
        "prices": prices,
        "bytes_per_token": config.BYTES_PER_TOKEN,
        "price_status": pricing.status(),
        "max_days": config.MAX_DAYS,
        "user_map": umap,
    })


@app.get("/api/identify")
async def api_identify(request: Request, days: int = 90):
    _guard(request)
    days = max(1, min(days, config.MAX_DAYS))
    return JSONResponse({"rows": await db.identify(days), "names": await db.names(),
                         "env_map": config.USER_MAP})


@app.post("/api/name")
async def api_name(request: Request, account: str = Form(...), name: str = Form("")):
    _guard(request)
    await db.set_name(account, name)
    return JSONResponse({"ok": True})


@app.get("/api/review")
async def api_review(request: Request, days: int = 30, user: str = "all", model: str = "all",
                    proxy: str = "all", q: str = "", page: int = 1, page_size: int = 25):
    _guard(request)
    days = max(1, min(days, config.MAX_DAYS))
    res = await db.review(days, user, model, proxy, q, page, page_size)
    return JSONResponse(res)
