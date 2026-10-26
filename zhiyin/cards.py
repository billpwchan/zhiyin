"""Cards made without an account (from someone's public NetEase likes), and every card anyone chooses to share by link.

A shared card is only the picture plus the few words its page shows (the name, how many likes, since when). The likes it
was drawn from are never stored: the record goes back to the browser that asked for it and is gone from here."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time

from . import ear, i18n, llm, netease, profile, store

DIR = store.DATA / "cards"
DIR.mkdir(parents=True, exist_ok=True)
W, H = 1080, 1440
MAX_BYTES = 1_500_000
TOKEN_S = 86400
NAMES_A_DAY = 3      # names for one playlist per day: the first and two more tries
MAKES = (12, 600)    # imports from one address per ten minutes
SHARES_A_DAY = 20    # links one account or address makes in a day
NAME_LINES = 600

_recent: dict[str, list[float]] = {}


def _key() -> bytes:
    path = store.DATA / "card.key"
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
        path.chmod(0o600)
    return path.read_bytes()


def sign(d: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()).decode().rstrip("=")
    mac = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{mac}"


def unsign(token: str) -> dict | None:
    body, _, mac = (token or "").partition(".")
    if not body or not hmac.compare_digest(mac, hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]):
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    return d if d.get("exp", 0) > time.time() else None


def may_make(ip: str) -> bool:
    n, span = MAKES
    now = time.time()
    seen = _recent[ip] = [t for t in _recent.get(ip, []) if now - t < span]
    if len(seen) >= n:
        return False
    seen.append(now)
    if len(_recent) > 5000:   # forget addresses gone quiet
        for k in [k for k, v in _recent.items() if not v or now - v[-1] > span]:
            _recent.pop(k, None)
    return True


def _name(tracks: list[dict], key: str, lang: str, again: bool) -> tuple[str | None, str | None]:
    """(label, why there is none). A playlist named today keeps its name unless they ask for another."""
    k = hashlib.sha256(f"{key}|{lang}".encode()).hexdigest()[:24]
    today = time.strftime("%Y-%m-%d")
    con = store.db()
    row = con.execute("select label, day, rolls from card_names where k=?", (k,)).fetchone()
    rolls = row["rolls"] if row and row["day"] == today else 0
    if row and row["label"] and (not again or rolls >= NAMES_A_DAY):
        return row["label"], i18n.tr("今天换了好几次了，明天再换", lang) if again else None
    with store.as_user(store.CARDS):
        if llm.unavailable():
            cap = llm.spent(store.CARDS, days=1) >= llm.CARD_DAILY_USD
            return (row["label"] if row else None), i18n.tr(
                "今天起名字的额度用完了，明天再来起名" if cap else "现在起不了名字，唱片先画好了", lang)
        rows = [((t["liked_est"] or "")[:7], t["title"], ", ".join(a["name"] for a in t["artists"][:2])) for t in tracks]
        try:
            label = profile.name_taste(rows, lang, NAME_LINES, model="haiku", service="NetEase Cloud Music")
        except llm.LLMError:
            return (row["label"] if row else None), i18n.tr("起名字的时候出了点问题，再试一次", lang)
    con.execute("insert or replace into card_names values (?, ?, ?, ?)", (k, label, today, rolls + 1))
    con.execute("delete from card_names where day < ?", (time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400)),))
    con.commit()
    return label, None


def make(link: str, lang: str, again: bool = False) -> dict:
    got = netease.likes(link)
    tracks = got["tracks"]
    label, why = _name(tracks, got["key"], lang, again)
    rec = ear.from_tracks(tracks, lang)
    rec["label"] = label
    rec["n"] = got["total"]
    rec["pics"] = {t["vid"]: t["pic"] for t in tracks if t["pic"]}
    rec["source"] = "163"
    rec["why"] = why
    since = int(rec["span"][0])
    rec["token"] = sign({"label": label or "", "n": got["total"], "since": since, "lang": lang,
                         "exp": time.time() + TOKEN_S, "nonce": secrets.token_hex(8)})
    return rec


def jpeg_size(b: bytes) -> tuple[int, int] | None:
    """(width, height) from a baseline or progressive JPEG's frame header."""
    if b[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            return None
        m = b[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + seg
    return None


def valid_image(b: bytes) -> bool:
    return 0 < len(b) <= MAX_BYTES and jpeg_size(b) == (W, H)


def shares_today(who: str) -> int:
    since = time.time() - 86400
    return store.db().execute("select count(*) from cards where uid=? and created>?", (who, since)).fetchone()[0]


def save(img: bytes, label: str, lang: str, n: int, since: int, who: str, nonce: str | None) -> dict:
    cid = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
    key = secrets.token_urlsafe(18)
    (DIR / f"{cid}.jpg").write_bytes(img)
    con = store.db()
    con.execute("insert into cards(id, created, label, lang, n, since, uid, del, nonce) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, time.time(), label, lang, n, since, who, hashlib.sha256(key.encode()).hexdigest(), nonce))
    con.commit()
    return {"id": cid, "key": key}


def used(nonce: str) -> bool:
    return bool(store.db().execute("select 1 from cards where nonce=?", (nonce,)).fetchone())


def get(cid: str) -> dict | None:
    r = store.db().execute("select * from cards where id=?", (cid,)).fetchone()
    return dict(r) if r and (DIR / f"{cid}.jpg").exists() else None


def seen(cid: str) -> None:
    con = store.db()
    con.execute("update cards set views = views + 1 where id=?", (cid,))
    con.commit()


def remove(cid: str, key: str | None = None, uid: str | None = None, operator: bool = False) -> bool:
    c = get(cid)
    if not c:
        return False
    if not (operator or (key and hmac.compare_digest(c["del"], hashlib.sha256(key.encode()).hexdigest()))
            or (uid and c["uid"] == uid)):
        return False
    (DIR / f"{cid}.jpg").unlink(missing_ok=True)
    con = store.db()
    con.execute("delete from cards where id=?", (cid,))
    con.commit()
    return True


def drop(uid: str) -> None:
    """Every card an account shared comes down with the account."""
    for r in store.db().execute("select id from cards where uid=?", (uid,)).fetchall():
        remove(r["id"], uid=uid)


def listing(limit: int = 50) -> list[dict]:
    return [dict(r) for r in store.db().execute(
        "select id, created, label, lang, n, since, uid, views from cards order by created desc limit ?", (limit,))]
