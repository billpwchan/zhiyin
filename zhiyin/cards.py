"""Cards made without an account (from someone's public NetEase or QQ Music likes), and every card anyone chooses to
share by link.

A shared card is only the picture plus the few words its page shows (the name, the roast, how many likes, since when,
how mainstream). The likes it
was drawn from are never stored: the record goes back to the browser that asked for it and is gone from here."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from collections import Counter

from . import ear, i18n, library, llm, profile, store

DIR = store.DATA / "cards"
DIR.mkdir(parents=True, exist_ok=True)
W, H = 1080, 1440
MAX_BYTES = 1_500_000
TOKEN_S = 86400
NAMES_A_DAY = 3      # names for one playlist per day: the first and two more tries
MAKES = (12, 600)    # imports from one address per ten minutes
SHARES_A_DAY = 20    # links one account or address makes in a day
NAME_LINES = 600
MIN_POP = 20       # songs with a popularity before 大众度 means anything

_recent: dict[str, list[float]] = {}

VERDICT_SCHEMA = {"type": "object", "properties": {"label": {"type": "string"}, "roast": {"type": "string"}},
                  "required": ["label", "roast"]}
ROAST = """

Then write `roast`, @ROAST@ in @LANG@: what a friend with sharp ears would say out loud about this taste to make the
table laugh, the line they will screenshot and post.
- Hang it on something the list really shows: an artist they can't stop liking, a run of the same kind of song, a year
  they never left, how mainstream they are (大众度 below), the guilty pleasure sitting next to the serious stuff.
- Tease the music and the habit, never the person: nothing about looks, age, gender, love life, where they are from,
  money or mental health. Calling the songs emo is fine.
- One idea and one punchline. Don't stack several facts or recite the numbers; pick the one that lands.
- Funny over clever: spoken rhythm, plain words. No compliment dressed up as a roast, no "but deep down" turn, no
  advice, no question to the reader.
- Don't reuse the label's words. No emoji or hashtags."""
ROAST_MAX = {"zh-Hans": (99, 48), "zh-Hant": (99, 48), "en": (32, 999)}   # (words, characters) a card can hold
ROAST_LEN = {"zh-Hans": "one or two sentences, at most 40 Chinese characters",
             "zh-Hant": "one or two sentences, at most 40 Chinese characters",
             "en": "one or two sentences, at most 26 words"}


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


def popularity(tracks: list[dict]) -> int | None:
    """大众度: the mean of NetEase's own 0-100 popularity over the likes (its hot chart is 100, a little-known indie
    list about 20, a typical listener's likes 70-80)."""
    pops = [t["pop"] for t in tracks if t.get("pop") is not None]
    return round(sum(pops) / len(pops)) if len(pops) >= MIN_POP else None


def _about(tracks: list[dict], total: int, dated: bool = True) -> str:
    """The numbers the roast may lean on, in the prompt's own words."""
    first = min((t["liked_est"] for t in tracks if t["liked_est"]), default="")[:4] if dated else ""
    top = Counter(t["artists"][0]["name"] for t in tracks if t["artists"]).most_common(3)
    years = sorted(t["year"] for t in tracks if t["year"] > 1950)
    out = [f"{total} liked songs" + (f", the first liked in {first}" if first else "") + "."]
    if (pop := popularity(tracks)) is not None:
        out.append(f"大众度 (mean NetEase popularity, 0-100; the hot chart scores 100, a little-known indie list about "
                   f"20, most people's likes 70-80): {pop}.")
    if len(years) >= 30:
        out.append(f"Half the songs came out in {years[(len(years) - 1) // 2]} or before.")
    if top:
        out.append("Most liked artists: " + ", ".join(f"{a} ({n})" for a, n in top) + ".")
    return " ".join(out)


def _short(text: str, lang: str, words: int, chars: int) -> bool:
    return len(text.split()) <= words if lang == "en" else len(text) <= chars


def _clip(roast: str, lang: str) -> str:
    """A roast that is still too long ends at its last full sentence that fits: the card has room for three lines."""
    words, chars = ROAST_MAX[lang]
    if _short(roast, lang, words, chars):
        return roast
    if lang == "en":
        head = " ".join(roast.split()[:words])
        cut = max(head.rfind(p) for p in ".!?")
    else:
        head = roast[:chars]
        cut = max(head.rfind(p) for p in "。！？")
    return head[:cut + 1] if cut > 0 else roast


SERVICE = {"163": "NetEase Cloud Music", "qq": "QQ Music"}


def verdict(tracks: list[dict], total: int, lang: str, model: str = "haiku", app: str = "163") -> tuple[str, str]:
    """(label, roast) for a card: the taste's name, and one line teasing it."""
    dated = app != "qq"   # QQ Music's like dates are only estimates: the roast must not count on them
    rows = profile.sample([((t["liked_est"] or "")[:7] if dated else (t.get("released") or "")[:4], t["title"],
                            ", ".join(a["name"] for a in t["artists"][:2])) for t in tracks], NAME_LINES)
    w = i18n.WRITE[lang]
    system = (profile.LABEL_SYSTEM + ROAST).replace("@ROWS@", profile.ROWS[dated]).replace("@LABEL@", w["label"]) \
        .replace("@LANG@", w["lang"]).replace("@SERVICE@", SERVICE[app]).replace("@ROAST@", ROAST_LEN[lang])
    prompt = "About them: " + _about(tracks, total, dated) + "\n\nTheir likes:\n" + "\n".join(" | ".join(r) for r in rows)
    label = roast = ""
    for _ in range(3):
        out = llm.call(prompt, system, VERDICT_SCHEMA, model=model, timeout=180, retries=1)
        label, roast = out["label"].strip().rstrip("。.!！"), out["roast"].strip()
        long = [f"\"{v}\" is too long: {rule}." for v, ok, rule in (
            (label, _short(label, lang, 7, 18), w["label"]), (roast, _short(roast, lang, ROAST_MAX[lang][0], ROAST_MAX[lang][1]), ROAST_LEN[lang]))
            if not ok]
        if not long:
            break
        prompt += "\n\n(" + " ".join(long) + ")"
    roast = _clip(roast, lang)
    if lang != "en":   # the script of the likes can leak in (粵語 for a Simplified reader)
        other = "zh-Hant" if lang == "zh-Hans" else "zh-Hans"
        label, roast = (i18n.zh_punct(i18n.convert(v, other, lang)) for v in (label, roast))
    return label, roast


def _verdict(tracks: list[dict], total: int, key: str, lang: str, again: bool, app: str) -> tuple[str | None, str | None, str | None]:
    """(label, roast, why there are none). A playlist read today keeps its verdict unless they ask for another."""
    k = hashlib.sha256(f"{key}|{lang}".encode()).hexdigest()[:24]
    today = time.strftime("%Y-%m-%d")
    con = store.db()
    row = con.execute("select label, roast, day, rolls from card_names where k=?", (k,)).fetchone()
    rolls = row["rolls"] if row and row["day"] == today else 0
    kept = (row["label"], row["roast"]) if row else (None, None)
    if row and row["label"] and row["roast"] and (not again or rolls >= NAMES_A_DAY):   # names kept before roasts get one
        return *kept, i18n.tr("今天换了好几次了，明天再换", lang) if again else None
    with store.as_user(store.CARDS):
        if llm.unavailable():
            cap = llm.spent(store.CARDS, days=1) >= llm.CARD_DAILY_USD
            return *kept, i18n.tr("今天起名字的额度用完了，明天再来起名" if cap else "现在起不了名字，唱片先画好了", lang)
        try:
            label, roast = verdict(tracks, total, lang, app=app)
        except llm.LLMError:
            return *kept, i18n.tr("起名字的时候出了点问题，再试一次", lang)
    con.execute("insert or replace into card_names(k, label, day, rolls, roast) values (?, ?, ?, ?, ?)",
                (k, label, today, rolls + 1, roast))
    con.execute("delete from card_names where day < ?", (time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400)),))
    con.commit()
    return label, roast, None


def make(link: str, lang: str, again: bool = False) -> dict:
    got = library.app_likes(link)
    tracks = got["tracks"]
    app = got["key"].split(":", 1)[0]
    label, roast, why = _verdict(tracks, got["total"], got["key"], lang, again, app)
    rec = ear.from_tracks(tracks, lang, released=app == "qq")
    pop = popularity(tracks)
    if pop is not None:
        rec["facts"].insert(0, {"key": "pop", "lead": f"{pop}%",
                                "text": i18n.tr("大众度：你喜欢的歌在网易云的平均热度是 {p}，热歌榜是 100。", lang, p=pop), "vids": []})
    rec.update(label=label, roast=roast, pop=pop, n=got["total"], source=app, why=why,
               pics={t["vid"]: t["pic"] for t in tracks if t["pic"]})
    since = 0 if rec["dates"] == "released" else int(rec["span"][0])   # 0: no year their likes start from
    rec["token"] = sign({"label": label or "", "roast": roast or "", "pop": pop, "n": got["total"], "since": since,
                         "lang": lang, "exp": time.time() + TOKEN_S, "nonce": secrets.token_hex(8)})
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


def save(img: bytes, label: str, lang: str, n: int, since: int, who: str | None, nonce: str | None,
         roast: str | None = None, pop: int | None = None) -> dict:
    cid = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
    key = secrets.token_urlsafe(18)
    (DIR / f"{cid}.jpg").write_bytes(img)
    con = store.db()
    con.execute("insert into cards(id, created, label, lang, n, since, uid, del, nonce, roast, pop) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, time.time(), label, lang, n, since, who, hashlib.sha256(key.encode()).hexdigest(), nonce, roast, pop))
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
