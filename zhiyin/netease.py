"""A NetEase Cloud Music (网易云音乐) listener's public likes, read for a record and a name without signing in.

Only what anyone can see on their page is read: the playlist of liked songs (or a public playlist they link), when each
song went into it, and each song's title, artists, album, cover and release date. Nothing here is written to disk."""
import json
import re
import threading
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx

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
    """`why` is one of: link (not a NetEase profile or playlist), private, few, upstream."""

    def __init__(self, why: str, n: int = 0):
        super().__init__(why)
        self.why, self.n = why, n


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
                       "pic": al.get("picUrl") or "", "year": int(pub[:4]) if pub else 0, "pop": s.get("pop")})
    if len(tracks) < MIN_SONGS:
        raise Unreadable("few", len(tracks))
    return {"key": f"163:{pid}", "tracks": tracks, "total": total}
