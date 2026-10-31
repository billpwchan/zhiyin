"""A NetEase Cloud Music (网易云音乐) listener's public likes, read for a record and a name without signing in.

Only what anyone can see on their page is read: the playlist of liked songs (or a public playlist they link), when each
song went into it, each song's title, artists, album, cover and release date, their 听歌排行, and every other playlist
there (`lists`): their own and the ones they keep. Nothing about a listener is written to disk here; the other names of
artists are cached."""
import json
import re
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx

from . import store

API = "https://music.163.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36", "Referer": "https://music.163.com/"}
MAX_SONGS = 3000        # the newest; a record of more is no different to look at, and each 500 is one more request
MIN_SONGS = 20
BATCH = 500
HOSTS = ("music.163.com", "y.music.163.com", "163cn.tv")
# every visitor's import goes out from the server's one address: a few at a time, so NetEase never sees a flood
_gate = threading.BoundedSemaphore(3)


class Unreadable(Exception):
    """`why` is one of: link (not a profile or playlist link), song (a link to one song), private, few, upstream.
    `app` is whose link it was: "163", or "qq" from qqmusic."""

    def __init__(self, why: str, n: int = 0, app: str = "163"):
        super().__init__(why)
        self.why, self.n, self.app = why, n, app


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=12, follow_redirects=False)


def _ok(host: str | None) -> bool:
    return bool(host) and any(host == h or host.endswith("." + h) for h in HOSTS)


def parse(text: str, c: httpx.Client | None = None) -> tuple[str, int]:
    """("playlist" | "user", id) from what a listener pastes: a profile or playlist link, the app's share text around
    one, or its 163cn.tv short link."""
    m = re.search(r"https?://[^\s，。、“”\"'<>（）()]+", text or "")
    if not m:
        raise Unreadable("link")
    url = m.group(0)
    for _ in range(4):
        parts = urlsplit(url)
        if not _ok(parts.hostname):
            raise Unreadable("link")
        if parts.hostname != "163cn.tv" and not parts.hostname.endswith(".163cn.tv"):
            break
        try:   # the app's short links redirect to the real page; follow only NetEase's own hops
            r = (c or _client()).get(url)
        except httpx.HTTPError:
            raise Unreadable("upstream") from None
        url = r.headers.get("location", "")
        if not url:
            raise Unreadable("link")
    parts = urlsplit(url)
    if not _ok(parts.hostname):
        raise Unreadable("link")
    # the web player keeps the page in the fragment: music.163.com/#/playlist?id=1
    for path, query in ((parts.path, parts.query), *([urlsplit(parts.fragment)[2:4]] if parts.fragment else [])):
        q = parse_qs(query)
        ids = q.get("id") or []
        tail = re.search(r"/(playlist|user(?:/home)?)/(\d+)", path)
        if tail:
            return ("playlist" if tail.group(1) == "playlist" else "user", int(tail.group(2)))
        if ids and ids[0].isdigit():
            if "playlist" in path:
                return "playlist", int(ids[0])
            if "user" in path:
                return "user", int(ids[0])
        if "song" in path and ids:
            raise Unreadable("song")
    raise Unreadable("link")


def _get(c: httpx.Client, path: str, **params) -> dict:
    try:
        r = c.get(API + path, params=params)
        return r.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        raise Unreadable("upstream") from None


def liked_playlist(c: httpx.Client, uid: int) -> int:
    d = _get(c, "/api/user/playlist", uid=uid, limit=30, offset=0)
    if d.get("code") != 200:
        raise Unreadable("link" if d.get("code") == 404 else "upstream")
    for p in d.get("playlist") or []:
        if p.get("specialType") == 5 and (p.get("creator") or {}).get("userId", uid) == uid:
            return p["id"]
    raise Unreadable("private")   # hidden from others in their privacy settings


def _songs(c: httpx.Client, ids: list[int]) -> dict[int, dict]:
    out = {}
    for i in range(0, len(ids), BATCH):
        part = ids[i:i + BATCH]
        try:
            r = c.post(API + "/api/v3/song/detail", data={"c": json.dumps([{"id": x} for x in part])})
            d = r.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            raise Unreadable("upstream") from None
        for s in d.get("songs") or []:
            out[s["id"]] = s
    return out


def _date(ms) -> str | None:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d") if ms and ms > 0 else None


def likes(text: str) -> dict:
    """{"key": a playlist id, "tracks": newest first, in the library's shape, "total": songs in the playlist}."""
    if not _gate.acquire(timeout=30):
        raise Unreadable("upstream")
    try:
        with _client() as c:
            kind, n = parse(text, c)
            pid = liked_playlist(c, n) if kind == "user" else n
            d = _get(c, "/api/v6/playlist/detail", id=pid, n=0)
            if d.get("code") in (401, 403) or (d.get("code") == 200 and not d.get("playlist")):
                raise Unreadable("private")
            if d.get("code") == 404:
                raise Unreadable("link")
            if d.get("code") != 200:
                raise Unreadable("upstream")
            owner = (d["playlist"].get("creator") or {}).get("userId") or (n if kind == "user" else None)
            # whose page the rest of their lists are on: theirs, or whoever's liked songs they chose to go by
            user = n if kind == "user" else owner if d["playlist"].get("specialType") == 5 else None
            refs = [x for x in d["playlist"].get("trackIds") or [] if x.get("id")]
            refs.sort(key=lambda x: -(x.get("at") or 0))
            total = len(refs)
            if total < MIN_SONGS:
                raise Unreadable("few", total)
            refs = refs[:MAX_SONGS]
            info = _songs(c, [x["id"] for x in refs])
    finally:
        _gate.release()
    tracks = []
    for x in refs:
        s = info.get(x["id"])
        if not s or not s.get("name"):
            continue   # taken down: NetEase keeps the id in the playlist but has nothing to say about it
        al = s.get("al") or {}
        pub = _date(s.get("publishTime"))
        tracks.append({"rank": len(tracks), "vid": f"n{s['id']}", "ll": None, "title": s["name"],
                       "artists": [{"name": a["name"]} for a in s.get("ar") or [] if a.get("name")],
                       "album": {"name": al["name"]} if al.get("name") else None, "dur": (s.get("dt") or 0) // 1000,
                       "liked_est": _date(x.get("at")), "source": "163", "long": False,
                       "pic": al.get("picUrl") or "", "year": int(pub[:4]) if pub else 0, "pop": s.get("pop"),
                       "ne": s["id"], "ne_ar": [a["id"] for a in s.get("ar") or [] if a.get("id")]})
    if len(tracks) < MIN_SONGS:
        raise Unreadable("few", len(tracks))
    return {"key": f"163:{pid}", "owner": owner, "user": user, "tracks": tracks, "total": total}


MAX_LISTS = 100   # playlists on a profile, in the order NetEase shows them: their own first
KEPT_SONGS = 500   # read from a playlist someone else made: enough to say what it is


def lists(uid: int, likes: bool = True) -> dict:
    """Every playlist anyone can see on a NetEase profile, with its songs, in qqmusic.lists' shape: their own (their
    liked songs too unless `likes` is False) and the ones by others they keep (kind "saved")."""
    if not _gate.acquire(timeout=60):
        raise Unreadable("upstream")
    try:
        with _client() as c:
            d = _get(c, "/api/user/playlist", uid=uid, limit=MAX_LISTS, offset=0)
            if d.get("code") != 200:
                raise Unreadable("link" if d.get("code") == 404 else "upstream")
            found = []
            for p in d.get("playlist") or []:
                creator = p.get("creator") or {}
                mine = creator.get("userId") == uid
                liked = mine and p.get("specialType") == 5
                if (liked and not likes) or not p.get("trackCount"):
                    continue
                try:
                    x = _get(c, "/api/v6/playlist/detail", id=p["id"], n=0)
                except Unreadable:
                    continue
                ids = list(dict.fromkeys(t["id"] for t in (x.get("playlist") or {}).get("trackIds") or [] if t.get("id")))
                if ids:
                    found.append(({"title": "我喜欢的音乐" if liked else p.get("name") or "",
                                   "kind": "likes" if liked else "own" if mine else "saved",
                                   "by": None if mine else creator.get("nickname"),
                                   "at": _date(p.get("createTime")) if mine else None, "changed": _date(p.get("updateTime"))},
                                  ids[:MAX_SONGS if mine else KEPT_SONGS]))
            info = _songs(c, list(dict.fromkeys(i for _, ids in found for i in ids))[:3 * MAX_SONGS])
    finally:
        _gate.release()
    out, songs = [], {}
    for meta, ids in found:
        got = [info[i] for i in ids if info.get(i, {}).get("name")]
        if not got:
            continue
        for s in got:
            pub = _date(s.get("publishTime"))
            songs.setdefault(s["id"], {"title": s["name"], "artists": [a["name"] for a in s.get("ar") or [] if a.get("name")],
                                       "ar": [a["id"] for a in s.get("ar") or [] if a.get("id")],
                                       "album": (s.get("al") or {}).get("name") or "", "released": pub, "lists": []})["lists"].append(len(out))
        out.append({**meta, "n": len(got)})
    ids = list({a for s in songs.values() for a in s["ar"]})
    with store.Pool(3) as ex:   # _gate lets three through at a time
        aka = dict(zip(ids, ex.map(aliases, ids)))
    for s in songs.values():
        s["aka"] = list(dict.fromkeys(x for a in s.pop("ar") for x in aka.get(a, []) if x not in s["artists"]))
    return {"key": f"163:u:{uid}", "lists": out, "songs": list(songs.values())}


def link_of(key: str) -> str:
    """The playlist a read came from, as a link `likes` reads again."""
    return f"https://music.163.com/playlist?id={key.removeprefix('163:')}"


def ranking(owner: int | None) -> dict[int, int]:
    """听歌排行, all time: song id -> score (100 is their most played; the top 100 only). {} if they hide it."""
    if not owner or not _gate.acquire(timeout=30):
        return {}
    try:
        with _client() as c:
            d = _get(c, "/api/v1/play/record", uid=owner, type=0)
    except Unreadable:
        return {}
    finally:
        _gate.release()
    if d.get("code") != 200:
        return {}
    return {x["song"]["id"]: int(x.get("score") or 0) for x in d.get("allData") or [] if (x.get("song") or {}).get("id")}


ALIAS_DAYS = 90
ALIASES = store.CACHE / "ne_artist"


def aliases(aid: int) -> list[str]:
    """Other names NetEase knows an artist by ("Eason Chan" for 陈奕迅), which is often how YouTube Music lists them."""
    path = ALIASES / f"{int(aid)}.json"
    if path.exists() and time.time() - path.stat().st_mtime < ALIAS_DAYS * 86400:
        return json.loads(path.read_text())
    if not _gate.acquire(timeout=30):
        return []
    try:
        with _client() as c:
            d = _get(c, "/api/artist/head/info/get", id=aid)
    except Unreadable:
        return []
    finally:
        _gate.release()
    if d.get("code") != 200:
        return []
    a = (d.get("data") or {}).get("artist") or {}
    out = [x for x in [*(a.get("alias") or []), *(a.get("transNames") or []), a.get("trans") or ""] if x and isinstance(x, str)]
    ALIASES.mkdir(parents=True, exist_ok=True)
    store.write_json(path, out)
    return out
