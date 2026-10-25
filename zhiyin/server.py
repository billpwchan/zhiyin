import contextvars
import datetime as dt
import hmac
import os
import re
import secrets
import threading
import time
import traceback
from contextlib import asynccontextmanager
from typing import Annotated
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import accounts, ask, audio, candidates, ear, edition, google, i18n, library, llm, lyrics, profile, settings, store, ytm
from .text import display_title, is_version

WEB = store.ROOT / "web"
# On the server every request needs a session; on the Mac everything is the owner's, as before accounts.
AUTH = os.environ.get("ZHIYIN_AUTH") == "1"
WORKER_TOKEN = os.environ.get("ZHIYIN_WORKER_TOKEN", "")
MIN_LIKES = 20          # fewer liked songs than this can't define listening lanes yet
LIKE_SYNC_H = 6
# Open seats: people who may join with Google without an invite, so the shared Claude pool and the YouTube project's
# user cap (100 while Google hasn't verified the app) hold. 0 keeps the server invite-only.
SEATS = int(os.environ.get("ZHIYIN_SEATS", 0))
SAMPLE_DIR = store.ROOT / "demo"
SAMPLE_GETS = ("/api/state", "/api/ear", "/api/jobs", "/api/img", "/api/more", "/api/lyrics")
# Signed-out visitors reach YouTube and the lyrics sites through the server's one address, which every listener shares,
# so what they make it fetch is capped per ten minutes, all of them together. Anything already cached is free.
SAMPLE_FETCHES = {"img": 400, "lyrics": 60, "more": 30}
_sample_fetched: dict[str, list[float]] = {k: [] for k in SAMPLE_FETCHES}


def _sample_may_fetch(path: str, q) -> bool:
    kind = path.rsplit("/", 1)[1]
    if kind not in SAMPLE_FETCHES:
        return True
    if kind == "img" and ytm.cover_cached(q.get("u", "")):
        return True
    if kind == "lyrics" and q.get("t") and re.fullmatch(VID, q.get("vid", "")) and lyrics.cached(q["vid"]):
        return True
    now = time.time()
    seen = _sample_fetched[kind] = [t for t in _sample_fetched[kind] if now - t < 600]
    if len(seen) >= SAMPLE_FETCHES[kind]:
        return False
    seen.append(now)
    return True


def _install_sample() -> bool:
    """The sample listener ships in demo/: English at the top, its Chinese rewrite in demo/zh-Hans."""
    if not (SAMPLE_DIR / "profile.json").exists():
        return False
    for uid, src in ((store.SAMPLE, SAMPLE_DIR), (store.SAMPLE_ZH, SAMPLE_DIR / "zh-Hans")):
        d = store.USERS / uid
        d.mkdir(parents=True, exist_ok=True)
        for f in ("library.json", "tags.json", "profile.json", "edition.json"):
            p = src / f if (src / f).exists() else SAMPLE_DIR / f
            (d / f).write_bytes(p.read_bytes())
    return True


SAMPLE_ON = [False]


@asynccontextmanager
async def _lifespan(_app):
    i18n.migrate()
    SAMPLE_ON[0] = AUTH and _install_sample()
    for fn in (_scheduler, _outbox_loop):
        threading.Thread(target=fn, daemon=True).start()
    yield


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")

OPEN = ("/login", "/privacy", "/lang", "/i/", "/auth/google/", "/healthz", "/static/", "/api/worker/")
# A YouTube video id. It names cache files, so nothing else gets through.
VID = r"^[A-Za-z0-9_-]{1,64}$"
Vid = Annotated[str, Field(pattern=VID)]


@app.middleware("http")
async def _who(request: Request, call_next):
    if request.url.path.startswith("/api/worker/") and not _worker_ok(request):
        return JSONResponse({"detail": "worker token"}, 403)   # before FastAPI reads a body
    if request.method != "GET" and request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        # SameSite=Lax still sends the cookie from sibling subdomains of the same site
        return JSONResponse({"detail": "cross-site"}, 403)
    if not AUTH:
        return await call_next(request)
    uid = accounts.session_uid(request.cookies.get(accounts.COOKIE))
    if uid is None:
        if request.url.path.startswith(OPEN):
            return await call_next(request)
        path = request.url.path
        if SAMPLE_ON[0] and request.method == "GET" and (path == "/" or path in SAMPLE_GETS):
            # Someone not signed in tries the app as the sample listener, read-only, in their browser's language.
            if not _sample_may_fetch(path, request.query_params):
                return JSONResponse({"detail": "busy"}, 429)
            lang = i18n.from_request(request)
            tu = store._uid.set(store.SAMPLE if lang == "en" else store.SAMPLE_ZH)
            tl = i18n.reader.set(lang)
            try:
                return await call_next(request)
            finally:
                store._uid.reset(tu)
                i18n.reader.reset(tl)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": i18n.tr("需要重新登录", i18n.from_request(request))}, 401)
        return RedirectResponse("/login", 303)
    # A page belongs to the account it was opened as. After signing in as someone else in another tab, the old tab
    # must not keep writing likes, plays or "不要" into the new account: its requests are refused and it reloads.
    page = request.headers.get("x-zhiyin-uid")
    if request.url.path.startswith("/api/") and (page != uid if page else request.method != "GET"):
        # a write without the header comes from a page loaded before this rule existed, which can't tell either
        return JSONResponse({"detail": "account-changed"}, 409)
    token = store._uid.set(uid)
    try:
        return await call_next(request)
    finally:
        store._uid.reset(token)


@app.get("/healthz")
def healthz():
    return Response("zhiyin-ok", media_type="text/plain")


# ---------- background jobs: one slot per listener and kind ----------
# A request for songs must not wait behind the daily build. Builds (profile, edition) run one at a time across
# listeners, because each holds Claude processes and the server has little memory.
_jobs: dict[tuple[str, str], dict] = {}
_job_lock = threading.Lock()
# Listeners' stations are built side by side, a few at a time; the editor calls themselves are rationed in llm.
HEAVY_AT_ONCE = int(os.environ.get("ZHIYIN_HEAVY", 2))
_heavy = threading.BoundedSemaphore(HEAVY_AT_ONCE)
_heavy_busy = [0]
HEAVY = {"setup"}   # a first run; editions ration their own gathering in edition.GATHER
STALE_AFTER_H = 20
ACTIVE_DAYS = 3   # a listener away longer gets the next edition when they come back, not every morning meanwhile
FRESH_HOUR = 5


def _start(kind: str, fn):
    uid = store.uid()
    with _job_lock:
        j = _jobs.get((uid, kind))
        if j and j["running"]:
            raise HTTPException(409, "busy")
        j = _jobs[(uid, kind)] = {"kind": kind, "running": True, "error": None, "result": None, "started": time.time(),
                                  "msg": "", "step": 0}

    def log(msg, step=None):
        j["msg"] = msg
        if step is not None:
            j["step"] = step

    def run():
        try:
            if kind in HEAVY:
                if _heavy_busy[0] >= HEAVY_AT_ONCE:
                    log(i18n.tr("排队中：另一位听众的电台正在准备"))
                with _heavy:
                    _heavy_busy[0] += 1
                    try:
                        j["result"] = fn(log)
                    finally:
                        _heavy_busy[0] -= 1
            else:
                j["result"] = fn(log)
        except Exception as e:
            traceback.print_exc()
            j["error"] = str(e)
        finally:
            j["running"] = False
            j["ended"] = time.time()

    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(run,), daemon=True).start()
    return j


def _job_view(kind: str) -> dict | None:
    j = _jobs.get((store.uid(), kind))
    if not j:
        return None
    return {"kind": kind, "running": j["running"], "error": j["error"], "msg": j["msg"], "step": j["step"],
            "started": j["started"], "ended": j.get("ended")}


def _quota_reset() -> str:
    """YouTube Data API quotas reset at midnight Pacific time, shown in the server's local time."""
    now = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    at = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone()
    day = "今天 {hm}" if at.date() == dt.datetime.now().date() else "明天 {hm}"
    return i18n.tr(day, hm=f"{at.hour}:{at:%M}")


def _edition_stale(ed: dict | None) -> bool:
    if not ed:
        return True
    created = dt.datetime.fromtimestamp(max(ed["created"], ed.get("checked", 0)))
    now = dt.datetime.now()
    today_fresh = now.replace(hour=FRESH_HOUR, minute=0, second=0, microsecond=0)
    return (now - created).total_seconds() > STALE_AFTER_H * 3600 or (now >= today_fresh > created)


def _auto_refresh(ed: dict | None):
    if not store.read_json(store.PROFILE) or not _edition_stale(ed) or llm.unavailable():
        return
    j = _jobs.get((store.uid(), "refresh"))
    if j and (j["running"] or time.time() - j.get("ended", 0) < 1800):
        return
    # Only the stations played from get new songs: the others still hold songs not yet heard, and rebuilding them
    # would spend the editor on picks nobody listens to.
    only = None
    if ed and ed.get("lang", "zh-Hans") == i18n.of() and {l["key"] for l in ed["lanes"]} >= {
            l["key"] for l in (store.read_json(store.PROFILE) or {}).get("lanes", []) if settings.lane_view(l)["enabled"]}:
        only = edition.played_since(ed)
        if not only:
            store.write_json(store.EDITION, {**ed, "checked": store.now()})
            return
    try:
        _start("refresh", lambda log: edition.build(log=log, only=only) and None)
    except HTTPException:
        pass


def _sync_likes(log):
    r = library.sync_from_google(log=log)
    if r["added"]:
        profile.absorb_new(log=log)
        if audio.REMOTE:
            audio.ensure([t for t in library.load() if not t["long"]], log=log)
    accounts.set_prefs(store.uid(), synced=time.time(), last_sync=r)
    log(i18n.tr("新增 {n} 首", n=r["added"]) if r["added"] else i18n.tr("没有新的喜欢"))
    return r


def _auto_sync():
    u = accounts.get()
    if not (u and u["status"] == "ready" and google.configured() and google.connected()):
        return
    if time.time() - u["prefs"].get("synced", 0) < LIKE_SYNC_H * 3600:
        return
    j = _jobs.get((u["id"], "sync"))
    if j and j["running"]:
        return
    try:
        _start("sync", _sync_likes)
    except HTTPException:
        pass


def _scheduler():
    while True:
        for u in accounts.users():
            try:
                with store.as_user(u["id"]):
                    j = _jobs.get((u["id"], "setup"))
                    if u["status"] in ("importing", "building") and not (j and j["running"]):
                        _start("setup", _setup)   # the server restarted in the middle of a first run
                    elif (u["status"] == "error" and u["prefs"].get("setup_fails", 0) < 3
                          and google.connected(u["id"]) and not llm.unavailable(u["id"])
                          and not (j and (j["running"] or time.time() - j.get("ended", 0) < 1800))):
                        _start("setup", _setup)   # a first run that failed, e.g. while Claude was out
                    if u["status"] == "ready" and time.time() - (u["last_seen"] or 0) < ACTIVE_DAYS * 86400:
                        with llm.background():
                            _auto_refresh(store.read_json(store.EDITION))
                        _auto_sync()
            except Exception:
                traceback.print_exc()
        time.sleep(1800)


def _setup(log):
    """First run for a listener who just connected Google: read likes, learn the lanes, pick the first stations."""
    uid = store.uid()
    accounts.set_status(uid, "importing")
    try:
        log(i18n.tr("读取你在 YouTube 点过的喜欢"), step=1)
        r = library.sync_from_google(log=log)
        accounts.set_prefs(uid, synced=time.time(), last_sync=r)
        if r["songs"] < MIN_LIKES:
            accounts.set_status(uid, "thin")
            return r
        if audio.REMOTE:
            audio.ensure([t for t in library.load() if not t["long"]], log=log)
        accounts.set_status(uid, "building")
        log(i18n.tr("了解你的口味"), step=2)
        if store.read_json(store.PROFILE):
            profile.absorb_new(log=log)   # a retry: the stations are there, only the edition failed
        else:
            profile.build(log=log)
        log(i18n.tr("挑第一批电台"), step=3)
        edition.build(log=log)
        accounts.set_status(uid, "ready")
        accounts.set_prefs(uid, setup_fails=0)
        return r
    except Exception:
        accounts.set_status(uid, "error")
        accounts.set_prefs(uid, setup_fails=accounts.prefs(uid).get("setup_fails", 0) + 1)
        raise


# ---------- likes written back to YouTube Music ----------
_wake = threading.Event()


def _queue_rate(vid: str, rating: str) -> str:
    uid = store.uid()
    if not (google.configured() and google.connected(uid)):
        return "none"
    if not google.writes_back(uid):
        return "read-only"
    if accounts.prefs(uid).get("sync_likes") is False:
        return "off"
    con = store.db()
    con.execute("delete from outbox where uid=? and vid=? and op='rate' and done is null", (uid, vid))
    con.execute("insert into outbox(uid, op, vid, arg, created) values (?, 'rate', ?, ?, ?)", (uid, vid, rating, time.time()))
    con.commit()
    _wake.set()
    return "queued"


def _backfill_likes() -> int:
    """Likes made in Zhiyin before YouTube Music was connected go across once it is."""
    uid = store.uid()
    if accounts.prefs(uid).get("sync_likes") is False or not google.writes_back(uid):
        return 0
    con = store.db()
    sent = {r["vid"] for r in con.execute("select vid from outbox where uid=? and op='rate'", (uid,))}
    todo = [r["vid"] for r in con.execute("select vid from feedback where uid=? and action='like' order by ts", (uid,))
            if r["vid"] not in sent]
    con.executemany("insert into outbox(uid, op, vid, arg, created) values (?, 'rate', ?, 'like', ?)",
                    [(uid, v, time.time()) for v in todo])
    con.commit()
    _wake.set()
    return len(todo)


def _outbox_loop():
    while True:
        _wake.wait(60)
        _wake.clear()
        con = store.db()
        rows = con.execute("select * from outbox where done is null and coalesce(next_try, 0) < ? order by id limit 30",
                           (time.time(),)).fetchall()
        for r in rows:
            later, done, err = None, None, None
            try:
                if not google.can_write():
                    raise google.QuotaExceeded()
                if r["op"] == "rate":
                    google.rate(r["uid"], r["vid"], r["arg"])
                done = time.time()
            except (google.Revoked, google.NotConnected):
                later, err = time.time() + 6 * 3600, "reconnect"
            except google.QuotaExceeded:
                later, err = time.time() + 3600, "quota"
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (400, 404):
                    done, err = time.time(), f"http {e.response.status_code}"
                else:
                    later, err = time.time() + 60 * 2 ** min(r["tries"], 8), f"http {e.response.status_code}"
            except httpx.HTTPError as e:
                later, err = time.time() + 60 * 2 ** min(r["tries"], 8), type(e).__name__
            con.execute("update outbox set done=?, next_try=?, error=?, tries=tries+? where id=?",
                        (done, later, err, 0 if done else 1, r["id"]))
            con.commit()


def _sync_view(uid: str) -> dict:
    con = store.db()
    pending = con.execute("select count(*) n, max(error) e from outbox where uid=? and done is null", (uid,)).fetchone()
    synced = con.execute("select count(*) n from outbox where uid=? and done is not null and error is null", (uid,)).fetchone()
    return {"pending": pending["n"], "error": pending["e"], "done": synced["n"]}


def _seats_left() -> int:
    return max(0, SEATS - accounts.joined())


def _join_state() -> str:
    """open: anyone may join with Google; full: they go on the waitlist; invite: only invite links make accounts."""
    if not (AUTH and SEATS and google.configured()) or (llm.HOSTED and not llm.API_KEY):
        return "invite"   # listeners who join run on the operator's API key, so there is nothing to join without one
    return "open" if _seats_left() else "full"


def _me() -> dict:
    if store.is_sample():
        return {"uid": store.uid(), "sample": True, "name": "", "owner": False, "mine": False, "status": "ready",
                "auth": AUTH, "lang": i18n.of(), "google": {"configured": google.configured(), "connected": False,
                                                           "verified": os.environ.get("ZHIYIN_GOOGLE_VERIFIED") == "1"},
                "join": _join_state(), "sync": {}, "claude": None}
    u = accounts.get() or {"id": store.uid(), "name": "", "status": "ready", "prefs": {}, "email": None}
    ok = google.configured() and google.connected(u["id"])
    return {"uid": u["id"], "name": u["name"], "owner": u["id"] == store.OWNER, "mine": store.is_owners(u["id"]), "status": u["status"], "auth": AUTH,
            "lang": i18n.of(u["id"]),
            "google": {"configured": google.configured(), "connected": ok, "email": u.get("email"),
                       "error": u["prefs"].get("google_error")},
            "sync_likes": u["prefs"].get("sync_likes", True) and (not ok or google.writes_back(u["id"])),
            "writes_back": ok and google.writes_back(u["id"]), "sync": _sync_view(u["id"]),
            "synced": u["prefs"].get("synced"), "last_sync": u["prefs"].get("last_sync"),
            "worker": audio.worker_online() if audio.REMOTE else None,
            "claude": llm.view(u["id"]) if AUTH else None}


# ---------- sign-in ----------
def _page(name: str, lang: str) -> str:
    html = (WEB / name).read_text(encoding="utf-8")
    for f in ("style.css", "i18n.js", "app.js"):
        html = html.replace(f"/static/{f}", f"/static/{f}?v={int((WEB / f).stat().st_mtime)}")
    # pages are written in Simplified Chinese; the language decided here is the one the page starts in
    return html.replace('<html lang="zh-Hans">', f'<html lang="{lang}" data-lang="{lang}">').replace(
        "<title>知音</title>", f"<title>{i18n.tr('知音', lang)}</title>")


def _gate(mode: str, request: Request, **ctx) -> HTMLResponse:
    html = _page("gate.html", i18n.from_request(request))
    data = {"mode": mode, "google": google.configured(), "join": _join_state(), "sample": SAMPLE_ON[0],
            "verified": os.environ.get("ZHIYIN_GOOGLE_VERIFIED") == "1", **ctx}
    import json
    html = html.replace("__GATE__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "same-origin"})


def _signed_in(resp: Response, uid: str, request: Request) -> Response:
    if not accounts.prefs(uid).get("lang"):
        accounts.set_prefs(uid, lang=i18n.from_request(request))
    tok = accounts.new_session(uid, request.headers.get("user-agent", ""))
    resp.set_cookie(accounts.COOKIE, tok, max_age=accounts.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=google.public_url().startswith("https"))
    return resp


@app.get("/privacy")
def privacy(request: Request):
    uid = accounts.session_uid(request.cookies.get(accounts.COOKIE)) if AUTH else store.OWNER
    lang = i18n.of(uid) if uid else i18n.from_request(request)
    html = _page("privacy.html", lang)
    # one block per language: <!--lang:xx--> … <!--/lang-->
    html = re.sub(r"<!--lang:([\w-]+)-->(.*?)<!--/lang-->", lambda m: m.group(2) if m.group(1) == lang else "", html, flags=re.S)
    return HTMLResponse(html)


@app.get("/lang")
def pick_lang(request: Request, to: str = "", back: str = "/login"):
    """The language picker on pages shown before signing in."""
    r = RedirectResponse(back if back.startswith("/") and not back.startswith("//") else "/login", 303)
    r.set_cookie(i18n.COOKIE, i18n.norm(to) or "en", max_age=365 * 86400, samesite="lax",
                 secure=google.public_url().startswith("https"))
    return r


@app.get("/login")
def login(request: Request, e: str = ""):
    if AUTH and accounts.session_uid(request.cookies.get(accounts.COOKIE)):
        return RedirectResponse("/", 303)
    return _gate("login", request, error=e)


@app.get("/i/{token}")
def invite_link(token: str, request: Request, go: int = 0):
    uid = accounts.redeem(token)
    if not uid:
        return _gate("login", request, error="expired")
    if (accounts.get(uid) or {}).get("google_sub") and google.configured():
        # once a listener is tied to a Google account, a forwarded or leaked link no longer opens it
        return RedirectResponse("/auth/google/start?mode=login", 303)
    cur = accounts.session_uid(request.cookies.get(accounts.COOKIE))
    if cur and cur != uid and not go:
        return _gate("switch", request, name=(accounts.get(uid) or {}).get("name") or i18n.tr("朋友", i18n.from_request(request)),
                     me=(accounts.get(cur) or {}).get("name") or "", token=token)
    return _signed_in(RedirectResponse("/", 303), uid, request)


@app.post("/auth/logout")
def logout(request: Request):
    accounts.end_session(request.cookies.get(accounts.COOKIE))
    r = JSONResponse({"ok": True})
    r.delete_cookie(accounts.COOKIE)
    return r


@app.get("/auth/google/start")
def google_start(request: Request, mode: str = "connect", write: int = 0,
                 as_: Annotated[str, Query(alias="as", max_length=254)] = ""):
    """mode=login&as=<email> is a bookmark that goes straight back into that listener's account. mode=join is
    signing up with Google in one step (no invite), asking only to read YouTube; write=1 adds writing likes back."""
    if not google.configured():
        raise HTTPException(503, i18n.tr("Google 登录还没配置", i18n.from_request(request)))
    uid = accounts.session_uid(request.cookies.get(accounts.COOKIE)) if AUTH else store.OWNER
    join = mode == "join" and AUTH and not uid and _join_state() != "invite"
    if mode == "join" and not join and not uid:
        mode = "login"
    connect = mode == "connect" or join
    if connect and not uid and not join:
        return RedirectResponse("/login", 303)
    asked_write = bool(write)
    # Someone who already reads and writes keeps both: include_granted_scopes only adds.
    write = asked_write or (uid is not None and google.writes_back(uid)) or not AUTH
    state = secrets.token_urlsafe(24)
    verifier, challenge = google.pkce()
    con = store.db()
    con.execute("delete from kv where k like 'oauth:%' and json_extract(v, '$.t') < ?", (time.time() - 900,))
    con.commit()
    store.kv_set(f"oauth:{state}", {"v": verifier, "connect": connect, "join": join, "uid": uid, "t": time.time(),
                                    "lang": i18n.from_request(request), "write_on": asked_write})
    named = "" if connect else as_
    hint = named or ((accounts.get(uid) or {}).get("email") if uid else None)
    r = RedirectResponse(google.auth_url(state, challenge, connect, hint, pick=not named, write=write), 303)
    r.set_cookie("zy_o", state, max_age=900, httponly=True, samesite="lax", secure=google.public_url().startswith("https"))
    return r


@app.get("/auth/google/callback")
def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    st = store.kv_get(f"oauth:{state}") if state else None
    if not st or request.cookies.get("zy_o") != state or time.time() - st["t"] > 900:
        return RedirectResponse("/?google=stale", 303)
    con = store.db()
    con.execute("delete from kv where k=?", (f"oauth:{state}",))
    con.commit()
    if error or not code:
        return RedirectResponse("/?google=cancelled" if st["connect"] and not st.get("join") else "/login?e=cancelled", 303)
    tok = google.exchange(code, st["v"])
    c = google.claims(tok["id_token"])
    if st.get("join"):
        st["uid"] = accounts.by_google(c["sub"])
        if not st["uid"]:
            if not google.has_youtube(tok):
                return RedirectResponse("/login?e=noscope", 303)   # no account is made without likes to read
            w = con.execute("select admitted from waitlist where sub=?", (c["sub"],)).fetchone()
            if not _seats_left() and not (w and w["admitted"]):
                con.execute("insert or ignore into waitlist values (?, ?, ?, ?, ?, null)",
                            (c["sub"], c.get("email", ""), c.get("name", ""), time.time(), st.get("lang")))
                con.commit()
                return RedirectResponse("/login?e=full", 303)
            st["uid"] = accounts.create(c.get("name", ""))
            accounts.set_prefs(st["uid"], joined=True, lang=st.get("lang"), sync_likes=False)
            con.execute("delete from waitlist where sub=?", (c["sub"],))
            con.commit()
    if not st["connect"]:
        uid = accounts.by_google(c["sub"])
        if not uid:
            w = con.execute("select admitted from waitlist where sub=?", (c["sub"],)).fetchone()
            if w and w["admitted"] and _join_state() != "invite":
                return RedirectResponse("/auth/google/start?mode=join", 303)   # let in from the waitlist: joins now
            return RedirectResponse("/login?e=unknown", 303)
        return _signed_in(RedirectResponse("/", 303), uid, request)
    uid = st["uid"]
    other = accounts.by_google(c["sub"])
    if other and other != uid:
        return RedirectResponse("/?google=taken", 303)
    if not google.has_youtube(tok):
        r = RedirectResponse("/?google=noscope", 303)
        return _signed_in(r, uid, request) if st.get("join") else r
    accounts.link_google(uid, c["sub"], c.get("email", ""), c.get("name", ""))
    google.save_tokens(uid, tok)
    accounts.set_prefs(uid, google_error=None)
    con.execute("update outbox set next_try=null where uid=? and done is null", (uid,))
    con.commit()
    _wake.set()
    with store.as_user(uid):
        _backfill_likes()
        u = accounts.get(uid)
        try:
            if u["status"] in ("new", "thin", "error"):
                _start("setup", _setup)
            else:
                _start("sync", _sync_likes)
        except HTTPException:
            pass
    if google.writes_back(uid) and st.get("write_on"):
        accounts.set_prefs(uid, sync_likes=True)
    r = RedirectResponse("/", 303)
    return _signed_in(r, uid, request) if st.get("join") else r


@app.get("/")
def index(request: Request):
    if not store.is_sample() and not accounts.prefs(store.uid()).get("lang"):
        accounts.set_prefs(store.uid(), lang=i18n.from_request(request))   # a new listener starts in their browser's language
    # YouTube's embed player rejects requests without a Referer (error 153); keep the default
    # strict-origin-when-cross-origin policy and never send no-referrer.
    html = _page("index.html", i18n.of())
    return HTMLResponse(html, headers={"Referrer-Policy": "strict-origin-when-cross-origin", "Cache-Control": "no-store"})


@app.get("/api/state")
def state():
    prof = store.read_json(store.PROFILE) or {}
    lib = store.read_json(store.LIBRARY) or {}
    tracks = lib.get("tracks", [])
    con = store.db()
    fb = [dict(r) for r in con.execute("select vid, action, scope, lane, reason, title, artist, ts from feedback where uid=? "
                                       "order by ts desc limit 200", (store.uid(),))]
    lanes = []
    assign = prof.get("assign", {})
    counts = {}
    for v in assign.values():
        if v:
            counts[v[0]] = counts.get(v[0], 0) + 1
    for l in prof.get("lanes", []):
        lv = settings.lane_view(l)
        lanes.append({k: lv[k] for k in ("key", "name", "english", "blurb", "when", "sound", "langs", "energy",
                                         "core_artists", "avoid", "discovery", "enabled")} | {"size": counts.get(l["key"], 0)})
    timeline = []
    for t in tracks:
        if t["long"]:
            continue
        lane = (assign.get(t["vid"]) or ["none"])[0]
        timeline.append([t["rank"], (t.get("liked_est") or "")[:7], lane, t["title"],
                         t["artists"][0]["name"] if t["artists"] else ""])
    ed = store.read_json(store.EDITION)
    if not store.is_sample() and (accounts.get() is None or accounts.get()["status"] == "ready"):
        _auto_refresh(ed)
        _auto_sync()
    out = {
        "portrait": prof.get("portrait"), "lanes": lanes, "focus": prof.get("focus"),
        "set_aside": [{"what": s["what"], "n": len(s["ranks"]), "why": s["why"]} for s in prof.get("set_aside", [])],
        "profile_built": prof.get("built"), "edition": ed,
        "asks": store.read_json(store.ASKS) or [], "feedback": fb, "timeline": timeline,
        "library": {"songs": sum(1 for t in tracks if not t["long"]), "mixes": sum(1 for t in tracks if t["long"]),
                    "synced": lib.get("synced"), "source": tracks[0]["source"] if tracks else None},
        "me": _me(), "jobs": jobs(), "owner_name": "" if store.is_sample() else (accounts.get(store.OWNER) or {}).get("name") or "",
        "stale_lang": i18n.stale(),
    }
    rl = i18n.of()
    if rl != "en":   # Claude's text was written in one Chinese script; show it in the reader's
        pl = prof.get("lang", "zh-Hans")
        for k in ("portrait", "lanes", "focus", "set_aside"):
            out[k] = i18n.convert_tree(out[k], pl, rl)
        out["edition"] = i18n.convert_tree(ed, (ed or {}).get("lang", "zh-Hans"), rl)
        out["asks"] = [i18n.convert_tree(a, a.get("lang", "zh-Hans"), rl) for a in out["asks"]]
    return out


@app.get("/api/ear")
def ear_view():
    return ear.build()


@app.get("/api/jobs")
def jobs():
    return {k: _job_view(k) for k in ("refresh", "ask", "sync", "setup", "retell")}


@app.post("/api/refresh")
def refresh():
    why = llm.unavailable()
    if why:
        raise HTTPException(503, why)
    _start("refresh", lambda log: edition.build(log=log) and None)
    return jobs()


class Ask(BaseModel):
    q: str


@app.post("/api/ask")
def ask_(body: Ask):
    q = body.q.strip()
    if not q:
        raise HTTPException(400, "empty")
    why = llm.unavailable()
    if why:
        raise HTTPException(503, why)
    _start("ask", lambda log: ask.run(q, log=log) and None)
    return jobs()


class Feedback(BaseModel):
    vid: Vid
    action: str  # like | dislike | known | undo
    scope: str = "song"  # song | artist
    lane: str | None = None
    reason: str | None = None
    title: str | None = None
    artist: str | None = None
    artist_id: str | None = None


@app.post("/api/feedback")
def feedback(f: Feedback):
    con = store.db()
    prev = con.execute("select action from feedback where uid=? and vid=?", (store.uid(), f.vid)).fetchone()
    con.execute("delete from feedback where uid=? and vid=?", (store.uid(), f.vid))
    if f.action != "undo":
        con.execute("insert into feedback (vid, action, lane, scope, reason, title, artist, artist_id, ts, uid) "
                    "values (?,?,?,?,?,?,?,?,?,?)",
                    (f.vid, f.action, f.lane, f.scope, f.reason, f.title, f.artist, f.artist_id, store.now(), store.uid()))
    con.commit()
    sync = None
    # "不要" stays here: a dislike on YouTube would also steer YouTube's own recommendations.
    if f.action == "like":
        sync = _queue_rate(f.vid, "like")
    elif prev and prev["action"] == "like":
        sync = _queue_rate(f.vid, "none")
    return {"ok": True, "sync": sync}


class Play(BaseModel):
    vid: Vid
    lane: str | None = None
    ev: str = "start"  # start | skip | done
    pos: float = 0


@app.post("/api/play")
def play(p: Play):
    con = store.db()
    con.execute("insert into plays (vid, lane, ts, ev, pos, uid) values (?,?,?,?,?,?)",
                (p.vid, p.lane, store.now(), p.ev, p.pos, store.uid()))
    con.commit()
    return {"ok": True}


class LaneSetting(BaseModel):
    key: str
    enabled: bool | None = None
    discovery: float | None = None


@app.post("/api/settings/lane")
def lane_setting(s: LaneSetting):
    cur = settings.load()
    o = cur["lanes"].setdefault(s.key, {})
    if s.enabled is not None:
        o["enabled"] = s.enabled
    if s.discovery is not None:
        o["discovery"] = max(0.0, min(1.0, s.discovery))
    settings.save(cur)
    return {"ok": True}


class PlaylistReq(BaseModel):
    name: str
    vids: list[Vid]


@app.post("/api/playlist")
def playlist(p: PlaylistReq):
    uid = store.uid()
    if not (google.configured() and google.connected(uid)):
        raise HTTPException(400, i18n.tr("先在设置里连接 YouTube Music"))
    vids = list(dict.fromkeys(p.vids))[:25]
    now, lang = dt.datetime.now(), i18n.of()
    date = now.strftime("%b %-d") if lang == "en" else f"{now.month}月{now.day}日"
    title = i18n.tr("知音 · {name} · {date}", name=p.name, date=date)
    try:
        pid = google.create_playlist(uid, title, i18n.tr("知音挑的歌"), vids)
    except google.QuotaExceeded:
        raise HTTPException(429, i18n.tr("今天写入 YouTube 的额度用完了，{at} 后再存", at=_quota_reset()))
    except (google.Revoked, google.NotConnected):
        raise HTTPException(401, i18n.tr("YouTube Music 的连接失效了，在设置里重新连接"))
    except httpx.HTTPError as e:
        raise HTTPException(502, i18n.tr("YouTube 拒绝了请求：{e}", e=e))
    return {"url": f"https://music.youtube.com/playlist?list={pid}", "title": title}


@app.post("/api/setup")
def setup():
    u = accounts.get()
    if not u or u["status"] not in ("thin", "error", "new") or not google.connected():
        raise HTTPException(400, i18n.tr("现在不需要重新准备"))
    _start("setup", _setup)
    return jobs()


@app.post("/api/sync")
def sync():
    if not (google.configured() and google.connected()):
        raise HTTPException(400, i18n.tr("还没连接 YouTube Music"))
    _start("sync", _sync_likes)
    return jobs()


@app.get("/api/warmup")
def warmup():
    """Something to listen to in the first minutes, before the stations exist: radios from the newest likes."""
    tracks = [t for t in library.load() if not t["long"] and t["type"] in ("ATV", "OMV")][:3]
    mine = set()
    if not tracks and google.configured() and google.connected():
        # Still importing: the first page of likes is enough to start.
        items = google.likes(store.uid(), pages=1)
        mine = {it["vid"] for it in items}
        info = google.videos(store.uid(), [it["vid"] for it in items[:12]])
        tracks = [{"vid": it["vid"], "title": info[it["vid"]]["title"], "artists": [{"name": info[it["vid"]]["channel"]}]}
                  for it in items[:12] if info.get(it["vid"], {}).get("cat") == google.MUSIC_CATEGORY
                  and info[it["vid"]]["dur"] <= 600][:3]
    known = candidates.Known(library.load(), {})
    radios = [ytm.radio(t["vid"])["tracks"] for t in tracks]
    out, seen = [], set()
    for i in range(50):
        for r in radios:
            if i < len(r):
                t = r[i]
                if (t["vid"] in seen or t["vid"] in mine or t["type"] == "UGC" or not (90 <= (t["dur"] or 0) <= 600)
                        or is_version(t["title"]) or known.reject(t)):
                    continue
                seen.add(t["vid"])
                out.append(edition._public({**t, "familiar": known.artist_familiarity(t["artists"]), "fit": 0,
                                            "sources": ["radio"], "via": []}))
    return {"name": i18n.tr("先听着"), "sub": i18n.tr("从你最近的喜欢出发"), "tracks": out[:30],
            "seeds": [display_title(t["title"], t["artists"]) for t in tracks]}


class Toggle(BaseModel):
    on: bool


class LangReq(BaseModel):
    lang: str


@app.post("/api/account/lang")
def account_lang(b: LangReq):
    lang = i18n.norm(b.lang)
    if not lang:
        raise HTTPException(400, "lang")
    accounts.set_prefs(store.uid(), lang=lang)
    if i18n.stale() and not llm.unavailable():
        try:
            _start("retell", i18n.retell)
        except HTTPException:
            pass
    r = JSONResponse({"me": _me(), "jobs": jobs()})
    r.set_cookie(i18n.COOKIE, lang, max_age=365 * 86400, samesite="lax", secure=google.public_url().startswith("https"))
    return r


@app.post("/api/account/retell")
def account_retell():
    if not i18n.stale():
        return jobs()
    llm.require()
    _start("retell", i18n.retell)
    return jobs()


@app.post("/api/account/sync-likes")
def account_sync_likes(t: Toggle):
    if t.on and google.connected() and not google.writes_back():
        return {**_me(), "grant": "/auth/google/start?mode=connect&write=1"}   # Google asks once more, for writing
    accounts.set_prefs(store.uid(), sync_likes=t.on)
    if t.on:
        _backfill_likes()
    return _me()


@app.post("/api/account/device")
def account_device():
    """A sign-in link for another device of the same listener, until they sign in with Google."""
    if (accounts.get() or {}).get("google_sub"):
        raise HTTPException(409, i18n.tr("用同一个 Google 账号登录就行"))
    tok = accounts.invite((accounts.get() or {}).get("name") or "", uid=store.uid())
    return {"url": f"{google.public_url()}/i/{tok}", "days": accounts.INVITE_DAYS}


@app.post("/api/account/disconnect")
def account_disconnect():
    google.disconnect(store.uid())
    return _me()


@app.post("/api/account/delete")
def account_delete(request: Request):
    uid = store.uid()
    if uid == store.OWNER:
        raise HTTPException(400, i18n.tr("主人的数据不能在这里删"))
    google.disconnect(uid)
    accounts.delete(uid)
    r = JSONResponse({"ok": True})
    r.delete_cookie(accounts.COOKIE)
    return r


class InviteReq(BaseModel):
    name: str = ""
    mine: bool = False   # another account of the owner's own


def _owner_only():
    if store.uid() != store.OWNER:
        raise HTTPException(403, i18n.tr("只有主人可以邀请"))


@app.post("/api/invite")
def invite(body: InviteReq):
    _owner_only()
    if body.mine:   # it runs on your Claude like your main account, so it needs no API key
        tok = accounts.invite(body.name.strip()[:20] or i18n.tr("我的另一个账号"), mine=True)
        return {"url": f"{google.public_url()}/i/{tok}", "days": accounts.INVITE_DAYS}
    if not llm.API_KEY:
        raise HTTPException(409, i18n.tr("先在服务器上配置 Claude API key：你的 Claude 订阅只能你自己用"))
    name = body.name.strip()[:20]
    if not name:
        raise HTTPException(400, i18n.tr("写个名字"))
    tok = accounts.invite(name)
    return {"url": f"{google.public_url()}/i/{tok}", "days": accounts.INVITE_DAYS}


@app.get("/api/users")
def users():
    _owner_only()
    out = []
    for u in accounts.users():
        if u["id"] == store.OWNER:
            continue
        with store.as_user(u["id"]):
            lib = store.read_json(store.LIBRARY) or {}
        out.append({"name": u["name"], "mine": bool(u.get("mine")), "email": u["email"] if u.get("mine") else None,
                    "status": u["status"], "last_seen": u["last_seen"], "created": u["created"],
                    "songs": sum(1 for t in lib.get("tracks", []) if not t["long"]), "usd7": llm.spent(u["id"])})
    return {"users": out}


def _worker_ok(request: Request) -> bool:
    return bool(WORKER_TOKEN) and hmac.compare_digest(request.headers.get("x-worker-token", ""), WORKER_TOKEN)


def _worker(request: Request):
    if not _worker_ok(request):
        raise HTTPException(403, "worker token")


@app.get("/api/worker/wanted")
def worker_wanted(request: Request, limit: int = 150):
    _worker(request)
    return audio.wanted(limit)


@app.get("/api/worker/llm")
def worker_llm(request: Request, wait: float = 25, have: str | None = None):
    """The owner's Claude calls, for a server without a Claude login of its own (long poll)."""
    _worker(request)
    return llm.take(min(max(wait, 0), 25), None if have is None else set(filter(None, have.split(","))))


class WorkerAnswer(BaseModel):
    data: dict | None = None
    usd: float = Field(0, ge=0, le=50, allow_inf_nan=False)
    error: str | None = None


@app.post("/api/worker/llm/{jid}")
def worker_llm_answer(request: Request, jid: str, body: WorkerAnswer):
    _worker(request)
    if body.error is not None or body.data is None:
        llm.answer(jid, {"error": body.error or "empty answer from the worker", "usd": body.usd})
    else:
        llm.answer(jid, {"data": body.data, "usd": body.usd})
    return {"ok": True}


class WorkerResult(BaseModel):
    audio: list[dict]
    text: list[dict] = []


@app.post("/api/worker/result")
def worker_result(request: Request, body: WorkerResult):
    _worker(request)
    n = audio.accept(body.audio, body.text)

    def redo():
        for u in accounts.users():
            with store.as_user(u["id"]):
                try:
                    edition.redecorate()
                except Exception:
                    traceback.print_exc()
    if n:
        threading.Thread(target=redo, daemon=True).start()
    return {"ok": True, "vectors": n}


class QueueReq(BaseModel):
    vids: list[Vid]


@app.post("/api/queue-link")
def queue_link(q: QueueReq):
    """Anonymous temporary playlist: youtube.com/watch_videos answers 303 with a TLGG list id that
    music.youtube.com also plays (and offers to save). No account access needed."""
    import httpx
    from urllib.parse import parse_qs, urlparse
    vids = q.vids[:50]
    r = httpx.get("https://www.youtube.com/watch_videos", params={"video_ids": ",".join(vids)},
                  follow_redirects=False, timeout=15)
    lst = parse_qs(urlparse(r.headers.get("location", "")).query).get("list", [None])[0]
    if not lst:
        raise HTTPException(502, i18n.tr("YouTube 没有返回临时播放列表"))
    return {"url": f"https://music.youtube.com/watch?v={vids[0]}&list={lst}"}


@app.get("/api/img")
def img(u: str):
    """Same-origin copy of a cover so the page can read its pixels for the ambient colour."""
    import httpx
    try:
        f = ytm.cover_file(u)
    except ValueError:
        raise HTTPException(400, "host")
    except httpx.HTTPStatusError as e:
        raise HTTPException(404 if e.response.status_code == 404 else 502, "img")
    except httpx.HTTPError:
        raise HTTPException(502, "img")
    data = f.read_bytes()
    kind = "image/webp" if data[8:12] == b"WEBP" else "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return Response(data, media_type=kind, headers={"Cache-Control": "max-age=2592000, immutable"})


@app.get("/api/more")
def more(vid: Annotated[str, Query(pattern=VID)], exclude: str = ""):
    """Keep going from one song: its YouTube Music radio, minus what the listener has or has refused."""
    prof = store.read_json(store.PROFILE) or {}
    known = candidates.Known(library.load(), prof)
    skip = set(filter(None, exclude.split(",")))
    r = ytm.radio(vid)
    src = r["tracks"][0] if r["tracks"] and r["tracks"][0]["vid"] == vid else None
    via = display_title(src["title"], src["artists"]) if src else ""
    out = []
    for t in r["tracks"]:
        if t["vid"] == vid or t["vid"] in skip or not (90 <= (t["dur"] or 0) <= 600) or is_version(t["title"]):
            continue
        if known.reject(t) not in (None, "shown"):
            continue
        fam = known.artist_familiarity(t["artists"])
        out.append(edition._public({**t, "familiar": fam, "fit": 0, "sources": ["radio"], "via": [],
                                    "reason": i18n.tr("沿着〈{s}〉的电台继续", s=via) if via else ""}))
        if len(out) >= 15:
            break
    return {"tracks": out}


@app.get("/api/lyrics")
def lyrics_(vid: Annotated[str, Query(pattern=VID)], t: str = "", a: str = "", al: str = "", d: float = 0):
    if not t:
        tr = ytm.track(vid) or {}
        t, a, al, d = tr.get("title", ""), "|".join(x["name"] for x in tr.get("artists", [])), (tr.get("album") or {}).get("name", ""), tr.get("dur") or 0
    res = lyrics.get(vid, display_title(t, []), [x for x in a.split("|") if x], al, d)
    lang = i18n.of()
    to = "en" if lang == "en" else "zh"
    return {**lyrics.for_reader(res, lang), "source": i18n.tr(res["source"], lang) if res.get("source") else None,
            "translating": lyrics.translate_later(vid, to) or f"{vid}:{to}" in lyrics._tr_running}
