"""A QQ Music (QQ 音乐) listener's public likes, read for a record and a name without signing in.

Only what anyone can see on their profile is read: their 我喜欢 (or a public playlist they link), each song's title,
singers, album, cover, length and release date; and every other list there (`lists`): their own, and the playlists
and albums they keep. QQ Music shows nobody when a song was liked, so those dates are estimated (`_estimate`).
Nothing about a listener is written to disk here; the other names of singers are cached."""
import heapq
import json
import re
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from . import store
from .netease import Unreadable

API = "https://u.y.qq.com/cgi-bin/musicu.fcg"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36", "Referer": "https://y.qq.com/"}
COMM = {"ct": 24, "cv": 0, "format": "json", "inCharset": "utf-8", "outCharset": "utf-8", "notice": 0,
        "platform": "yqq.json", "needNewCode": 1, "uin": 0}   # what y.qq.com sends for a visitor who isn't signed in
MAX_SONGS = 3000
MIN_SONGS = 20
PAGE = 1000
LIKES = 201   # every listener's 我喜欢 is this folder of theirs
_gate = threading.BoundedSemaphore(3)
_LINK = re.compile(r"https?://[^\s，。、“”\"'<>（）()]+")
_EUIN = re.compile(r"[0-9A-Za-z_-]{6,40}\*{0,2}")
# the profile page reads whichever of these it is given (i.y.qq.com share pages, y.qq.com on a computer)
_WHO = ("encrypt_uin", "userid", "userId", "euin", "uin")


def _ok(host: str | None) -> bool:
    return bool(host) and (host == "y.qq.com" or host.endswith(".y.qq.com"))


def ours(text: str) -> bool:
    """The first link in what they pasted is QQ Music's."""
    m = _LINK.search(text or "")
    return bool(m) and _ok(urlsplit(m.group(0)).hostname)


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=12, follow_redirects=False)


def parse(text: str, c: httpx.Client | None = None) -> tuple[str, int | str]:
    """("playlist", id) or ("user", their encrypted id) from what a listener pastes: their profile or a playlist,
    the app's share text around one, or its c6.y.qq.com short link."""
    m = _LINK.search(text or "")
    if not m:
        raise Unreadable("link", app="qq")
    if c is None:
        with _client() as c:
            return parse(text, c)
    url = m.group(0)
    for _ in range(4):
        parts = urlsplit(url)
        if not _ok(parts.hostname) or ":" in parts.netloc or "@" in parts.netloc:
            raise Unreadable("link", app="qq")
        if "/fcgi-bin/u" not in parts.path:
            break
        try:   # the app's short links redirect to the real page; follow only QQ Music's own hops
            r = c.get(url)
        except httpx.HTTPError:
            raise Unreadable("upstream", app="qq") from None
        url = r.headers.get("location", "")
        if not url:
            raise Unreadable("link", app="qq")
    parts = urlsplit(url)
    if not _ok(parts.hostname):
        raise Unreadable("link", app="qq")
    path, q = parts.path.lower(), parse_qs(parts.query)
    tail = re.search(r"/playlist/(\d+)", path)
    if tail:
        return "playlist", int(tail.group(1))
    for k in ("id", "disstid"):
        v = (q.get(k) or [""])[0]
        if v.isdigit() and ("playlist" in path or "taoge" in path or k == "disstid"):
            return "playlist", int(v)
    if "profile" in path:
        for k in _WHO:
            v = (q.get(k) or [""])[0]
            if _EUIN.fullmatch(v) and not v.isdigit():
                return "user", v
    if "song" in path or q.get("songmid") or q.get("songid"):
        raise Unreadable("song", app="qq")
    raise Unreadable("link", app="qq")


def _call(c: httpx.Client, module: str, method: str, param: dict) -> dict:
    try:
        r = c.post(API, content=json.dumps({"comm": COMM, "req": {"module": module, "method": method, "param": param}}))
        d = r.json()["req"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise Unreadable("upstream", app="qq") from None
    if d.get("code") != 0:
        raise Unreadable("upstream", app="qq")
    return d.get("data") or {}


def _diss(c: httpx.Client, which: dict, begin: int, num: int = PAGE) -> dict:
    return _call(c, "music.srfDissInfo.DissInfo", "CgiGetDiss", {**which, "song_begin": begin, "song_num": num})


def _day(ts) -> str | None:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts and ts > 0 else None


def _estimate(tracks: list[dict], since: str | None, until: str | None) -> None:
    """When each like happened, at the earliest. A song can't be liked before it came out, so the second newest
    release among it and the likes below it bounds it (the second: one re-release dated years late can't drag a
    whole stretch forward). The list's start and its last change bound it on either side."""
    top: list[str] = []
    for t in reversed(tracks):   # oldest like first
        if t["released"]:
            heapq.heappush(top, t["released"])
            if len(top) > 2:
                heapq.heappop(top)
        d = top[0] if top else None
        if d and since and d < since:
            d = since
        if d and until and d > until:
            d = until
        t["liked_est"] = d


def likes(text: str) -> dict:
    """{"key": which list, "tracks": newest first, in the library's shape, "total": songs in the list}, as
    netease.likes. `ne` and `ne_ar` hold QQ Music's song id and singer mids (the names came with NetEase)."""
    if not _gate.acquire(timeout=30):
        raise Unreadable("upstream", app="qq")
    try:
        with _client() as c:
            kind, ref = parse(text, c)
            which = {"disstid": 0, "dirid": LIKES, "enc_host_uin": ref} if kind == "user" else {"disstid": ref}
            d = _diss(c, which, 0)
            info = d.get("dirinfo") or {}
            total = d.get("total_song_num") or 0
            songs = list(d.get("songlist") or [])
            if not total and (d.get("code") or not info.get("id")):
                raise Unreadable("link", app="qq")   # no such playlist (-100006)
            if "隐私" in (info.get("title") or "") or (total and not songs):
                raise Unreadable("private", app="qq")
            if total < MIN_SONGS:
                raise Unreadable("few", total, app="qq")
            begin, more = PAGE, d.get("hasmore")
            while more and begin < min(total, MAX_SONGS):   # offsets count the whole list, taken-down songs too
                d = _diss(c, which, begin)
                songs += d.get("songlist") or []
                begin, more = begin + PAGE, d.get("hasmore")
    finally:
        _gate.release()
    tracks = []
    for s in songs[:MAX_SONGS]:
        name = s.get("title") or s.get("name")
        if not name or not s.get("mid"):
            continue
        al = s.get("album") or {}
        pub = (s.get("time_public") or "")[:10]
        year = int(pub[:4]) if pub[:4].isdigit() and int(pub[:4]) > 1900 else 0
        singers = [a for a in s.get("singer") or [] if a.get("name")]
        tracks.append({"rank": len(tracks), "vid": f"q{s['mid']}", "ll": None, "title": name,
                       "artists": [{"name": a["name"]} for a in singers],
                       "album": {"name": al["name"]} if al.get("name") else None, "dur": s.get("interval") or 0,
                       "liked_est": None, "released": pub if year else None, "source": "qq", "long": False,
                       "pic": f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{al['mid']}.jpg" if al.get("mid") else "",
                       "year": year, "pop": None, "ne": s.get("id") or s["mid"], "ne_ar": [a["mid"] for a in singers if a.get("mid")]})
    if len(tracks) < MIN_SONGS:
        raise Unreadable("few", len(tracks), app="qq")
    _estimate(tracks, _day(info.get("ctime")), _day(info.get("mtime")))
    key = f"qq:u:{ref}" if kind == "user" else f"qq:p:{ref}"
    return {"key": key, "owner": None, "tracks": tracks, "total": total}


FOLDER_GAP = 5   # a profile's own lists are numbered from 1; this many missing in a row is past the last
LAST_FOLDER = 199   # from 200 the numbers are QQ Music's: 201 is 我喜欢, 202 and up the lists it makes for them
MAX_KEPT = 50   # playlists by others, and albums, that a profile keeps: the newest, one request each
KEPT_SONGS = 500   # read from a playlist someone else made: enough to say what it is
_BACKING = re.compile(r"伴奏|伴唱|off ?vocal", re.I)   # a song again without its voice, for singing along


def _kept(c: httpx.Client, module: str, method: str, param: dict) -> list[dict]:
    out = []
    while len(out) < MAX_KEPT:
        d = _call(c, module, method, {**param, "offset": len(out), "size": 30})
        if d.get("hide"):
            return []
        got = [x for x in d.get("v_list") or [] if x not in out]
        out += got
        if not got or not d.get("hasmore"):   # nothing new: a page that ignores the offset ends it too
            break
    return out[:MAX_KEPT]


def lists(text: str, likes: bool = True) -> dict:
    """Every list anyone can see on a QQ Music profile, with its songs: their own (我喜欢 too unless `likes` is
    False, but not the lists QQ Music makes for them: 今日私享, 新发风向), playlists by others they keep, and albums
    they keep. {"key", "lists": [{"title", "kind", "by", "at", "changed", "n"}], "songs": [{"title", "artists", "aka",
    "album", "released", "lists"}]}: kind is "likes", "own", "saved" (someone else's playlist) or "album"; `at` is when
    they made or kept it. Each song is listed once, with the lists it is in (indices) and the other names of its singers
    (YouTube Music often uses those: 太妍 is TAEYEON there)."""
    if not _gate.acquire(timeout=60):
        raise Unreadable("upstream", app="qq")
    lists, songs = [], {}

    def add(meta: dict, got: list[dict], released: str | None = None) -> None:
        i, n = len(lists), 0
        for s in got:
            name = s.get("title") or s.get("name")
            if not name or not s.get("mid") or _BACKING.search(name):
                continue
            pub = (s.get("time_public") or released or "")[:10]
            rec = songs.setdefault(s["mid"], {
                "title": name, "artists": [a["name"] for a in s.get("singer") or [] if a.get("name")],
                "ar": [a["mid"] for a in s.get("singer") or [] if a.get("mid")],
                "album": (s.get("album") or {}).get("name") or "", "released": pub if pub[:4].isdigit() and pub[:4] > "1900" else None,
                "lists": []})
            if i not in rec["lists"]:
                rec["lists"].append(i)
                n += 1
        if n:
            lists.append({**meta, "n": n})
    try:
        with _client() as c:
            kind, ref = parse(text, c)
            if kind != "user":
                raise Unreadable("link", app="qq")
            missed = 0
            for dirid in ([LIKES] if likes else []) + list(range(1, LAST_FOLDER + 1)):
                if missed >= FOLDER_GAP:
                    break
                which = {"disstid": 0, "dirid": dirid, "enc_host_uin": ref}
                try:
                    d = _diss(c, which, 0)
                except Unreadable:
                    missed += dirid != LIKES
                    continue
                info, total = d.get("dirinfo") or {}, d.get("total_song_num") or 0
                if not info.get("id") or "隐私" in (info.get("title") or ""):
                    missed += dirid != LIKES
                    continue
                missed = 0
                got, begin = list(d.get("songlist") or []), PAGE
                while d.get("hasmore") and begin < min(total, MAX_SONGS):
                    d = _diss(c, which, begin)
                    got += d.get("songlist") or []
                    begin += PAGE
                add({"title": "我喜欢" if dirid == LIKES else info.get("title") or "", "kind": "likes" if dirid == LIKES else "own",
                     "by": None, "at": _day(info.get("ctime")), "changed": _day(info.get("mtime"))}, got)
            for p in _kept(c, "music.musicasset.PlaylistFavRead", "CgiGetPlaylistFavInfo", {"uin": ref}):
                if not p.get("tid") or not p.get("name"):
                    continue   # taken down by whoever made it
                try:
                    d = _diss(c, {"disstid": p["tid"]}, 0, KEPT_SONGS)
                except Unreadable:
                    continue
                add({"title": p["name"], "kind": "saved", "by": p.get("nickname") or None, "at": _day(p.get("orderTime")),
                     "changed": _day(p.get("updateTime"))}, (d.get("songlist") or [])[:KEPT_SONGS])
            for al in _kept(c, "music.musicasset.AlbumFavRead", "CgiGetAlbumFavInfo", {"euin": ref}):
                if not al.get("mid") or not al.get("name"):
                    continue
                try:
                    d = _call(c, "music.musichallAlbum.AlbumSongList", "GetAlbumSongList",
                              {"albumMid": al["mid"], "begin": 0, "num": 100, "order": 2})
                except Unreadable:
                    continue
                add({"title": al["name"], "kind": "album", "by": " / ".join(x["name"] for x in al.get("v_singer") or [] if x.get("name")) or None,
                     "at": _day(al.get("ordertime")), "changed": None},
                    [x.get("songInfo") or {} for x in d.get("songList") or []], _day(al.get("pubtime")))
    finally:
        _gate.release()
    mids = list({m for s in songs.values() for m in s["ar"]})
    with store.Pool(3) as ex:   # _gate lets three through at a time
        aka = dict(zip(mids, ex.map(aliases, mids)))
    for s in songs.values():
        s["aka"] = list(dict.fromkeys(x for m in s.pop("ar") for x in aka.get(m, []) if x not in s["artists"]))
    return {"key": f"qq:u:{ref}", "lists": lists, "songs": list(songs.values())}


def link_of(key: str) -> str:
    """The list a read came from, as a link `likes` reads again."""
    kind, _, ref = key.removeprefix("qq:").partition(":")
    if kind == "u":
        return f"https://i.y.qq.com/n2/m/share/profile_v2/index.html?encrypt_uin={quote(ref, safe='')}"
    return f"https://y.qq.com/n/ryqq/playlist/{ref}"


def name_parts(name: str) -> list[str]:
    """The names inside one QQ Music name: 华莎 (화사), G.E.M.邓紫棋."""
    out = [x.strip() for x in re.split(r"[()（）]", name) if x.strip()]
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9 .'&-]*?)\s*([㐀-鿿]{2,})", name)
    if m:
        out += [m.group(1).strip(), m.group(2)]
    return [x for x in dict.fromkeys(out) if x != name]


ALIAS_DAYS = 90
ALIASES = store.CACHE / "qq_singer"


def aliases(mid: str) -> list[str]:
    """Other names QQ Music knows a singer by ("Eason Chan" for 陈奕迅), which is often how YouTube Music lists them."""
    if not re.fullmatch(r"[0-9A-Za-z]{6,20}", mid or ""):
        return []
    path = ALIASES / f"{mid}.json"
    if path.exists() and time.time() - path.stat().st_mtime < ALIAS_DAYS * 86400:
        return json.loads(path.read_text())
    if not _gate.acquire(timeout=30):
        return []
    try:
        with _client() as c:
            d = _call(c, "music.musichallSinger.SingerInfoInter", "GetSingerDetail",
                      {"singer_mids": [mid], "ex_singer": 1, "wiki_singer": 0, "group_singer": 0, "pic": 0, "photos": 0})
    except Unreadable:
        return []
    finally:
        _gate.release()
    s = (d.get("singer_list") or [{}])[0]
    name = (s.get("basic_info") or {}).get("name") or ""
    out = [x for x in [(s.get("ex_info") or {}).get("foreign_name") or "", *name_parts(name)] if x and x != name]
    ALIASES.mkdir(parents=True, exist_ok=True)
    store.write_json(path, out)
    return out
