import concurrent.futures as cf
import contextvars
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("ZHIYIN_DATA", ROOT / "data"))
CACHE = DATA / "cache"       # shared by everyone: YouTube Music lookups, covers, lyrics
USERS = DATA / "users"
DB = DATA / "zhiyin.db"
OWNER = "owner"              # the first listener; their data predates accounts

for d in (DATA, CACHE, USERS):
    d.mkdir(parents=True, exist_ok=True)

# Whose library, profile and stations the current request or job is about. Set once at the edge (HTTP middleware,
# job thread, CLI) and read everywhere below, so the engine code stays single-listener.
_uid: contextvars.ContextVar[str | None] = contextvars.ContextVar("zhiyin_uid", default=None)
_PER_USER = {"LIBRARY": "library.json", "TAGS": "tags.json", "PROFILE": "profile.json", "PROFILES": "profiles",
             "EDITION": "edition.json", "ASKS": "asks.json", "SETTINGS": "settings.json", "AUTH": "browser.json"}


def uid() -> str:
    return _uid.get() or os.environ.get("ZHIYIN_USER") or OWNER


def udir(u: str | None = None) -> Path:
    d = USERS / (u or uid())
    (d / "profiles").mkdir(parents=True, exist_ok=True)
    return d


class as_user:
    """with store.as_user(uid): ... — everything inside reads and writes that listener's data."""

    def __init__(self, u: str):
        self.u, self.token = u, None

    def __enter__(self):
        self.token = _uid.set(self.u)
        return self

    def __exit__(self, *exc):
        _uid.reset(self.token)


def __getattr__(name):
    if name in _PER_USER:
        return udir() / _PER_USER[name]
    raise AttributeError(name)


class Pool(cf.ThreadPoolExecutor):
    """A thread pool whose workers see the caller's listener (plain pools start every thread with an empty context)."""

    def submit(self, fn, /, *args, **kwargs):
        ctx = contextvars.copy_context()
        return super().submit(ctx.run, fn, *args, **kwargs)


def _migrate_single_user() -> None:
    """Before accounts, one listener's files sat directly in data/. They become the owner's."""
    legacy = {k: DATA / f for k, f in _PER_USER.items()}
    if not any(p.exists() for p in legacy.values()):
        return
    dest = USERS / OWNER
    dest.mkdir(parents=True, exist_ok=True)
    for p in legacy.values():
        if p.exists() and not (dest / p.name).exists():
            p.replace(dest / p.name)


_migrate_single_user()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


_schema_lock = threading.Lock()
_schema_ready = False


def db() -> sqlite3.Connection:
    # The server, the daily build and the audio child process all write; WAL plus a wait keeps them from colliding.
    global _schema_ready
    con = sqlite3.connect(DB, timeout=60)
    con.row_factory = sqlite3.Row
    if _schema_ready:
        return con
    # once per process: switching a fresh database to WAL fails while another thread holds it open
    with _schema_lock:
        if not _schema_ready:
            _migrate(con)
            _schema_ready = True
    return con


def _migrate(con: sqlite3.Connection) -> None:
    if con.execute("pragma journal_mode").fetchone()[0] != "wal":
        con.execute("pragma journal_mode=wal")
    con.executescript("""
    create table if not exists feedback(
        vid text, action text, lane text, scope text, reason text, title text, artist text, artist_id text, ts real);
    create table if not exists shown(vid text, edition text, lane text, ts real);
    create table if not exists plays(vid text, lane text, ts real);
    create table if not exists users(
        id text primary key, name text, email text, google_sub text unique, created real, last_seen real,
        tokens blob, prefs text default '{}', status text default 'new');
    create table if not exists invites(token text primary key, uid text, name text, created real, used real);
    create table if not exists sessions(id text primary key, uid text, created real, last_seen real, ua text);
    create table if not exists kv(k text primary key, v text);
    create table if not exists outbox(id integer primary key, uid text, op text, vid text, arg text, tries integer default 0,
        created real, done real, error text);
    create table if not exists usage(uid text, day text, source text, calls integer, usd real,
        primary key(uid, day, source));
    create index if not exists feedback_vid on feedback(vid);
    create index if not exists shown_vid on shown(vid);
    """)
    cols = {r[1] for r in con.execute("pragma table_info(plays)")}
    if "ev" not in cols:
        con.execute("alter table plays add column ev text")
        con.execute("alter table plays add column pos real")
    if "next_try" not in {r[1] for r in con.execute("pragma table_info(outbox)")}:
        con.execute("alter table outbox add column next_try real")
    for t in ("feedback", "shown", "plays"):
        if "uid" not in {r[1] for r in con.execute(f"pragma table_info({t})")}:
            con.execute(f"alter table {t} add column uid text not null default '{OWNER}'")
            con.execute(f"create index if not exists {t}_uid on {t}(uid)")
    con.execute("insert or ignore into users(id, name, created, status) values (?, ?, ?, 'ready')", (OWNER, "", time.time()))
    con.commit()


def now() -> float:
    return time.time()


def kv_get(k: str, default=None):
    r = db().execute("select v from kv where k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def kv_set(k: str, v) -> None:
    con = db()
    con.execute("insert or replace into kv values (?, ?)", (k, json.dumps(v)))
    con.commit()
