"""Who is listening. A friend joins through an invite link, which signs them in on that device; once they connect
Google they can sign in anywhere with it. Session and invite tokens are random and kept only as sha256."""
import hashlib
import json
import secrets
import shutil
import time

from . import store

COOKIE = "zy"
SESSION_DAYS = 365
INVITE_DAYS = 14


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get(uid: str | None = None) -> dict | None:
    r = store.db().execute("select * from users where id=?", (uid or store.uid(),)).fetchone()
    if not r:
        return None
    u = dict(r)
    u["prefs"] = json.loads(u.get("prefs") or "{}")
    u.pop("tokens", None)
    return u


def prefs(uid: str | None = None) -> dict:
    u = get(uid)
    return u["prefs"] if u else {}


def set_prefs(uid: str, **kv) -> dict:
    p = {**(get(uid) or {}).get("prefs", {}), **kv}
    p = {k: v for k, v in p.items() if v is not None}
    con = store.db()
    con.execute("update users set prefs=? where id=?", (json.dumps(p, ensure_ascii=False), uid))
    con.commit()
    return p


def set_status(uid: str, status: str) -> None:
    con = store.db()
    con.execute("update users set status=? where id=?", (status, uid))
    con.commit()


def users() -> list[dict]:
    return [get(r["id"]) for r in store.db().execute("select id from users order by created")]


def by_google(sub: str) -> str | None:
    r = store.db().execute("select id from users where google_sub=?", (sub,)).fetchone()
    return r["id"] if r else None


def link_google(uid: str, sub: str, email: str, name: str) -> None:
    con = store.db()
    con.execute("update users set google_sub=?, email=?, name=coalesce(nullif(name, ''), ?) where id=?", (sub, email, name, uid))
    con.commit()


def invite(name: str, uid: str | None = None, mine: bool = False) -> str:
    """A new listener (or a sign-in link for an existing one, e.g. the owner on a new server). `mine` is another
    account of the owner's own, which runs on the owner's Claude."""
    con = store.db()
    if uid is None:
        uid = "u" + secrets.token_hex(4)
        con.execute("insert into users(id, name, created, status, mine) values (?, ?, ?, 'new', ?)",
                    (uid, name.strip(), time.time(), int(mine)))
    elif name.strip():
        con.execute("update users set name=? where id=? and coalesce(name, '')=''", (name.strip(), uid))
    token = secrets.token_urlsafe(18)
    con.execute("insert into invites values (?, ?, ?, ?, null)", (_h(token), uid, name.strip(), time.time()))
    con.commit()
    return token


def redeem(token: str) -> str | None:
    """Invite links stay valid for a fortnight so the friend can open them on a second device."""
    con = store.db()
    r = con.execute("select uid, created from invites where token=?", (_h(token),)).fetchone()
    if not r or time.time() - r["created"] > INVITE_DAYS * 86400 or not get(r["uid"]):
        return None
    con.execute("update invites set used=coalesce(used, ?) where token=?", (time.time(), _h(token)))
    con.commit()
    return r["uid"]


def new_session(uid: str, ua: str = "") -> str:
    token = secrets.token_urlsafe(32)
    con = store.db()
    con.execute("insert into sessions values (?, ?, ?, ?, ?)", (_h(token), uid, time.time(), time.time(), ua[:200]))
    con.execute("update users set last_seen=? where id=?", (time.time(), uid))
    con.commit()
    return token


def session_uid(token: str | None) -> str | None:
    if not token:
        return None
    con = store.db()
    r = con.execute("select uid, last_seen from sessions where id=?", (_h(token),)).fetchone()
    if not r or time.time() - r["last_seen"] > SESSION_DAYS * 86400:
        return None
    if time.time() - r["last_seen"] > 600:
        con.execute("update sessions set last_seen=? where id=?", (time.time(), _h(token)))
        con.execute("update users set last_seen=? where id=?", (time.time(), r["uid"]))
        con.commit()
    return r["uid"]


def end_session(token: str | None) -> None:
    if token:
        con = store.db()
        con.execute("delete from sessions where id=?", (_h(token),))
        con.commit()


def delete(uid: str) -> None:
    """Everything the listener left here: likes read from their account, feedback, history, tokens, sessions."""
    if uid == store.OWNER:
        raise ValueError("the owner's data stays")
    con = store.db()
    for t in ("feedback", "shown", "plays", "outbox", "usage"):
        con.execute(f"delete from {t} where uid=?", (uid,))
    for t, col in (("sessions", "uid"), ("invites", "uid"), ("users", "id")):
        con.execute(f"delete from {t} where {col}=?", (uid,))
    con.commit()
    shutil.rmtree(store.USERS / uid, ignore_errors=True)
