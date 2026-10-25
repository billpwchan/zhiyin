import contextvars
import datetime as dt
import hmac
import os
import secrets
import threading
import time
import traceback
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import accounts, ask, audio, candidates, ear, edition, google, library, llm, lyrics, profile, settings, store, ytm
from .text import display_title, is_version

WEB = store.ROOT / "web"
# On the server every request needs a session; on the Mac everything is the owner's, as before accounts.
AUTH = os.environ.get("ZHIYIN_AUTH") == "1"
WORKER_TOKEN = os.environ.get("ZHIYIN_WORKER_TOKEN", "")
MIN_LIKES = 20          # fewer liked songs than this can't define listening lanes yet
LIKE_SYNC_H = 6


@asynccontextmanager
async def _lifespan(_app):
    for fn in (_scheduler, _outbox_loop):
        threading.Thread(target=fn, daemon=True).start()
    yield


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")

OPEN = ("/login", "/privacy", "/i/", "/auth/google/", "/healthz", "/static/", "/api/worker/")


@app.middleware("http")
async def _who(request: Request, call_next):
    if not AUTH:
        return await call_next(request)
    uid = accounts.session_uid(request.cookies.get(accounts.COOKIE))
    if uid is None:
        if request.url.path.startswith(OPEN):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "需要重新登录"}, 401)
        return RedirectResponse("/login", 303)
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
_heavy = threading.Lock()
HEAVY = {"refresh", "setup"}
STALE_AFTER_H = 20
FRESH_HOUR = 5


def _start(kind: str, fn):
    uid = store.uid()
    with _job_lock:
        j = _jobs.get((uid, kind))
        if j and j["running"]:
            raise HTTPException(409, "已经在进行")
        j = _jobs[(uid, kind)] = {"kind": kind, "running": True, "error": None, "result": None, "started": time.time(),
                                  "msg": "", "step": 0}

    def log(msg, step=None):
        j["msg"] = msg
        if step is not None:
            j["step"] = step

    def run():
        try:
            if kind in HEAVY:
                if _heavy.locked():
                    log("排队中：另一位听众的电台正在准备")
                with _heavy:
                    j["result"] = fn(log)
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
    day = "今天" if at.date() == dt.datetime.now().date() else "明天"
    return f"{day} {at.hour}:{at:%M} "


def _edition_stale(ed: dict | None) -> bool:
    if not ed:
        return True
    created = dt.datetime.fromtimestamp(ed["created"])
    now = dt.datetime.now()
    today_fresh = now.replace(hour=FRESH_HOUR, minute=0, second=0, microsecond=0)
    return (now - created).total_seconds() > STALE_AFTER_H * 3600 or (now >= today_fresh > created)


def _auto_refresh(ed: dict | None):
    if not store.read_json(store.PROFILE) or not _edition_stale(ed) or llm.unavailable():
        return
    j = _jobs.get((store.uid(), "refresh"))
    if j and (j["running"] or time.time() - j.get("ended", 0) < 1800):
        return
    try:
        _start("refresh", lambda log: edition.build(log=log) and None)
    except HTTPException:
        pass


def _sync_likes(log):
    r = library.sync_from_google(log=log)
    if r["added"]:
        profile.absorb_new(log=log)
        if audio.REMOTE:
            audio.ensure([t for t in library.load() if not t["long"]], log=log)
    accounts.set_prefs(store.uid(), synced=time.time(), last_sync=r)
    log(f"新增 {r['added']} 首" if r["added"] else "没有新的喜欢")
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
                    if u["status"] == "ready":
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
        log("读取你在 YouTube 点过的喜欢", step=1)
        r = library.sync_from_google(log=log)
        accounts.set_prefs(uid, synced=time.time(), last_sync=r)
        if r["songs"] < MIN_LIKES:
            accounts.set_status(uid, "thin")
            return r
        if audio.REMOTE:
            audio.ensure([t for t in library.load() if not t["long"]], log=log)
        accounts.set_status(uid, "building")
        log("了解你的口味", step=2)
        if store.read_json(store.PROFILE):
            profile.absorb_new(log=log)   # a retry: the stations are there, only the edition failed
        else:
            profile.build(log=log)
        log("挑第一批电台", step=3)
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
    if accounts.prefs(uid).get("sync_likes") is False:
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


def _me() -> dict:
    u = accounts.get() or {"id": store.uid(), "name": "", "status": "ready", "prefs": {}, "email": None}
    ok = google.configured() and google.connected(u["id"])
    return {"uid": u["id"], "name": u["name"], "owner": u["id"] == store.OWNER, "status": u["status"], "auth": AUTH,
            "google": {"configured": google.configured(), "connected": ok, "email": u.get("email"),
                       "error": u["prefs"].get("google_error")},
            "sync_likes": u["prefs"].get("sync_likes", True), "sync": _sync_view(u["id"]),
            "synced": u["prefs"].get("synced"), "last_sync": u["prefs"].get("last_sync"),
            "worker": audio.worker_online() if audio.REMOTE else None,
            "claude": llm.view(u["id"]) if AUTH else None}


# ---------- sign-in ----------
def _gate(mode: str, **ctx) -> HTMLResponse:
    html = (WEB / "gate.html").read_text(encoding="utf-8")
    html = html.replace("/static/style.css", f"/static/style.css?v={int((WEB / 'style.css').stat().st_mtime)}")
    data = {"mode": mode, "google": google.configured(), **ctx}
    import json
    html = html.replace("__GATE__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "same-origin"})


def _signed_in(resp: Response, uid: str, request: Request) -> Response:
    tok = accounts.new_session(uid, request.headers.get("user-agent", ""))
    resp.set_cookie(accounts.COOKIE, tok, max_age=accounts.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=google.public_url().startswith("https"))
    return resp


@app.get("/privacy")
def privacy():
    html = (WEB / "privacy.html").read_text(encoding="utf-8")
    html = html.replace("/static/style.css", f"/static/style.css?v={int((WEB / 'style.css').stat().st_mtime)}")
    return HTMLResponse(html)


@app.get("/login")
def login(request: Request, e: str = ""):
    if AUTH and accounts.session_uid(request.cookies.get(accounts.COOKIE)):
        return RedirectResponse("/", 303)
    return _gate("login", error=e)


@app.get("/i/{token}")
def invite_link(token: str, request: Request, go: int = 0):
    uid = accounts.redeem(token)
    if not uid:
        return _gate("login", error="expired")
    cur = accounts.session_uid(request.cookies.get(accounts.COOKIE))
    if cur and cur != uid and not go:
        return _gate("switch", name=(accounts.get(uid) or {}).get("name") or "朋友",
                     me=(accounts.get(cur) or {}).get("name") or "", token=token)
    return _signed_in(RedirectResponse("/", 303), uid, request)


@app.post("/auth/logout")
def logout(request: Request):
    accounts.end_session(request.cookies.get(accounts.COOKIE))
    r = JSONResponse({"ok": True})
    r.delete_cookie(accounts.COOKIE)
    return r


@app.get("/auth/google/start")
def google_start(request: Request, mode: str = "connect"):
    if not google.configured():
        raise HTTPException(503, "Google 登录还没配置")
    connect = mode == "connect"
    uid = accounts.session_uid(request.cookies.get(accounts.COOKIE)) if AUTH else store.OWNER
    if connect and not uid:
        return RedirectResponse("/login", 303)
    state = secrets.token_urlsafe(24)
    verifier, challenge = google.pkce()
    store.kv_set(f"oauth:{state}", {"v": verifier, "connect": connect, "uid": uid, "t": time.time()})
    hint = (accounts.get(uid) or {}).get("email") if uid else None
    r = RedirectResponse(google.auth_url(state, challenge, connect, hint), 303)
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
        return RedirectResponse("/?google=cancelled" if st["connect"] else "/login?e=cancelled", 303)
    tok = google.exchange(code, st["v"])
    c = google.claims(tok["id_token"])
    if not st["connect"]:
        uid = accounts.by_google(c["sub"])
        if not uid:
            return RedirectResponse("/login?e=unknown", 303)
        return _signed_in(RedirectResponse("/", 303), uid, request)
    uid = st["uid"]
    other = accounts.by_google(c["sub"])
    if other and other != uid:
        return RedirectResponse("/?google=taken", 303)
    if not google.has_youtube(tok):
        return RedirectResponse("/?google=noscope", 303)
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
    return RedirectResponse("/", 303)


@app.get("/")
def index():
    # YouTube's embed player rejects requests without a Referer (error 153); keep the default
    # strict-origin-when-cross-origin policy and never send no-referrer.
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for name in ("style.css", "app.js"):
        html = html.replace(f"/static/{name}", f"/static/{name}?v={int((WEB / name).stat().st_mtime)}")
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
    if accounts.get() is None or accounts.get()["status"] == "ready":
        _auto_refresh(ed)
        _auto_sync()
    return {
        "portrait": prof.get("portrait"), "lanes": lanes, "focus": prof.get("focus"),
        "set_aside": [{"what": s["what"], "n": len(s["ranks"]), "why": s["why"]} for s in prof.get("set_aside", [])],
        "profile_built": prof.get("built"), "edition": ed,
        "asks": store.read_json(store.ASKS) or [], "feedback": fb, "timeline": timeline,
        "library": {"songs": sum(1 for t in tracks if not t["long"]), "mixes": sum(1 for t in tracks if t["long"]),
                    "synced": lib.get("synced"), "source": tracks[0]["source"] if tracks else None},
        "me": _me(), "jobs": jobs(), "owner_name": (accounts.get(store.OWNER) or {}).get("name") or "",
    }


@app.get("/api/ear")
def ear_view():
    return ear.build()


@app.get("/api/jobs")
def jobs():
    return {k: _job_view(k) for k in ("refresh", "ask", "sync", "setup")}


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
    vid: str
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
    vid: str
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
    vids: list[str]


@app.post("/api/playlist")
def playlist(p: PlaylistReq):
    uid = store.uid()
    if not (google.configured() and google.connected(uid)):
        raise HTTPException(400, "先在「你的耳朵」里连接 YouTube Music")
    vids = list(dict.fromkeys(p.vids))[:25]
    title = f"知音 · {p.name} · {dt.datetime.now().month}月{dt.datetime.now().day}日"
    try:
        pid = google.create_playlist(uid, title, "知音挑的歌", vids)
    except google.QuotaExceeded:
        raise HTTPException(429, f"今天写入 YouTube 的额度用完了，{_quota_reset()}后再存")
    except (google.Revoked, google.NotConnected):
        raise HTTPException(401, "YouTube Music 的连接失效了，在「你的耳朵」里重新连接")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"YouTube 拒绝了请求：{e}")
    return {"url": f"https://music.youtube.com/playlist?list={pid}", "title": title}


@app.post("/api/setup")
def setup():
    u = accounts.get()
    if not u or u["status"] not in ("thin", "error", "new") or not google.connected():
        raise HTTPException(400, "现在不需要重新准备")
    _start("setup", _setup)
    return jobs()


@app.post("/api/sync")
def sync():
    if not (google.configured() and google.connected()):
        raise HTTPException(400, "还没连接 YouTube Music")
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
    return {"name": "先听着", "sub": "从你最近的喜欢出发", "tracks": out[:30],
            "seeds": [display_title(t["title"], t["artists"]) for t in tracks]}


class Toggle(BaseModel):
    on: bool


@app.post("/api/account/sync-likes")
def account_sync_likes(t: Toggle):
    accounts.set_prefs(store.uid(), sync_likes=t.on)
    return _me()


@app.post("/api/account/device")
def account_device():
    """A sign-in link for another device of the same listener."""
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
        raise HTTPException(400, "主人的数据不能在这里删")
    google.disconnect(uid)
    accounts.delete(uid)
    r = JSONResponse({"ok": True})
    r.delete_cookie(accounts.COOKIE)
    return r


class InviteReq(BaseModel):
    name: str


def _owner_only():
    if store.uid() != store.OWNER:
        raise HTTPException(403, "只有主人可以邀请")


@app.post("/api/invite")
def invite(body: InviteReq):
    _owner_only()
    if not llm.API_KEY:
        raise HTTPException(409, "先在服务器上配置 Claude API key：你的 Claude 订阅只能你自己用")
    name = body.name.strip()[:20]
    if not name:
        raise HTTPException(400, "写个名字")
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
        out.append({"name": u["name"], "status": u["status"], "last_seen": u["last_seen"], "created": u["created"],
                    "songs": sum(1 for t in lib.get("tracks", []) if not t["long"]), "usd7": llm.spent(u["id"])})
    return {"users": out}


def _worker(request: Request):
    tok = request.headers.get("x-worker-token", "")
    if not WORKER_TOKEN or not hmac.compare_digest(tok, WORKER_TOKEN):
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
    usd: float = 0
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
    vids: list[str]


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
        raise HTTPException(502, "YouTube 没有返回临时播放列表")
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
def more(vid: str, exclude: str = ""):
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
                                    "reason": f"沿着〈{via}〉的电台继续" if via else ""}))
        if len(out) >= 15:
            break
    return {"tracks": out}


@app.get("/api/lyrics")
def lyrics_(vid: str, t: str = "", a: str = "", al: str = "", d: float = 0):
    if not t:
        tr = ytm.track(vid) or {}
        t, a, al, d = tr.get("title", ""), "|".join(x["name"] for x in tr.get("artists", [])), (tr.get("album") or {}).get("name", ""), tr.get("dur") or 0
    res = lyrics.get(vid, display_title(t, []), [x for x in a.split("|") if x], al, d)
    return {**res, "translating": lyrics.translate_later(vid) or vid in lyrics._tr_running}
