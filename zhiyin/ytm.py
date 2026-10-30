import hashlib
import json
import os
import re
import threading
import time

import httpx
from ytmusicapi import YTMusic

from . import store
from .text import dur_s

_local = threading.local()
_lock = threading.Lock()
_last = [0.0]
MIN_GAP = 0.25  # seconds between requests across all threads; YouTube starts returning 429s on bursts

DAY = 86400


# Titles and artist names are read the way YouTube Music shows them in this interface language (one per server:
# zh_TW shows Chinese artists in Chinese); the region decides what is available. An empty region lets YouTube go
# by the requesting IP.
LANGUAGE = os.environ.get("ZHIYIN_YT_LANGUAGE", "en")
REGION = os.environ.get("ZHIYIN_YT_REGION", "")


def client(auth: bool = False, lang: str = LANGUAGE) -> YTMusic:
    """ytmusicapi's search and artist-page parsers only work reliably in English (zh_TW artist search returns
    nothing), so those calls use lang="en"."""
    if auth:
        if not store.AUTH.exists():
            raise RuntimeError("YouTube Music auth not set up: run `uv run zhiyin auth` first")
        return YTMusic(str(store.AUTH), language=LANGUAGE, location=REGION)
    key = f"yt_{lang}"
    yt = getattr(_local, key, None)
    if yt is None:
        yt = YTMusic(language=lang, location=REGION)
        setattr(_local, key, yt)
    return yt


def _pace():
    with _lock:
        wait = _last[0] + MIN_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def _cached(kind: str, key: str, ttl: float, fn):
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    path = store.CACHE / kind / f"{h}.json"
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text())
    for attempt in range(3):
        try:
            _pace()
            data = fn()
            break
        except Exception:  # ytmusicapi raises plain Exceptions for HTTP errors
            if attempt == 2:
                if path.exists():
                    return json.loads(path.read_text())
                raise
            time.sleep(2 ** (attempt + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
    return data


_FEAT_ZH = re.compile(r"[(（]合作演出[：:]\s*([^)）]*)[)）]")


def plain_title(title: str) -> str:
    """zh_TW YouTube Music writes "(feat. X、Y)" as "(合作演出：X、Y)"."""
    return _FEAT_ZH.sub(lambda m: f"(feat. {m.group(1).replace('、', ', ')})", title or "")


def _track(t: dict) -> dict | None:
    vid = t.get("videoId")
    if not vid:
        return None
    arts = [{"name": a.get("name"), "id": a.get("id")} for a in (t.get("artists") or []) if a.get("name")]
    alb = t.get("album")
    thumbs = t.get("thumbnail") or t.get("thumbnails") or []
    year = t.get("year")
    views = t.get("views")
    # Watch-playlist results put the release year in "views" for album tracks ("2006年" / "2006").
    v = views.rstrip("年") if isinstance(views, str) else ""
    if not year and v.isdigit() and 1900 < int(v) < 2100:
        year, views = v, None
    return {
        "vid": vid,
        "title": plain_title(t.get("title")),
        "artists": arts,
        "album": {"name": alb.get("name"), "id": alb.get("id")} if isinstance(alb, dict) and alb.get("name") else None,
        "type": (t.get("videoType") or "").replace("MUSIC_VIDEO_TYPE_", ""),
        "dur": t.get("duration_seconds") or dur_s(t.get("length") or t.get("duration")),
        "year": int(year) if str(year or "").isdigit() else None,
        "views": views,
        "thumb": thumbs[-1]["url"] if thumbs else None,
    }


def radio(vid: str, limit: int = 50) -> dict:
    def fn():
        wp = client().get_watch_playlist(videoId=vid, radio=True, limit=limit)
        return {"related": wp.get("related"), "tracks": [x for x in (_track(t) for t in wp.get("tracks", [])) if x]}
    return _cached("radio", vid, 7 * DAY, fn)


def related(browse_id: str) -> dict:
    def fn():
        out = {"songs": [], "artists": []}
        try:
            sections = client().get_song_related(browse_id)
        except KeyError:  # "no related content" message instead of sections
            return out
        for sec in sections:
            contents = sec.get("contents")
            if not isinstance(contents, list):
                continue
            for c in contents:
                if c.get("videoId"):
                    t = _track(c)
                    if t:
                        out["songs"].append(t)
                elif c.get("browseId", "").startswith("UC") and not c.get("playlistId"):
                    out["artists"].append({"name": c.get("title"), "id": c["browseId"]})
        return out
    return _cached("related", browse_id, 14 * DAY, fn)


def artist(channel_id: str) -> dict:
    def fn():
        try:
            a = client(lang="en").get_artist(channel_id)
        except (KeyError, IndexError, TypeError):  # uploader channels (playlists, covers) have no artist page
            return {"name": None, "id": channel_id, "songs": [], "related": [], "releases": [], "subscribers": None, "thumb": None}
        songs = [x for x in (_track(t) for t in (a.get("songs") or {}).get("results", [])) if x]
        rel = [{"name": r.get("title"), "id": r.get("browseId")} for r in (a.get("related") or {}).get("results", [])]
        releases = []
        for k in ("singles", "albums"):
            for r in (a.get(k) or {}).get("results", []):
                releases.append({"kind": k, "title": r.get("title"), "id": r.get("browseId"), "year": r.get("year")})
        thumbs = a.get("thumbnails") or []
        return {"name": a.get("name"), "id": channel_id, "songs": songs, "related": rel, "releases": releases,
                "subscribers": a.get("subscribers"), "thumb": thumbs[-1]["url"] if thumbs else None}
    return _cached("artist", channel_id, 3 * DAY, fn)


def album(browse_id: str) -> dict:
    def fn():
        a = client().get_album(browse_id)
        thumbs = a.get("thumbnails") or []
        tracks = []
        for t in a.get("tracks", []):
            x = _track(t)
            if x:
                x["album"] = {"name": a.get("title"), "id": browse_id}
                x["year"] = int(a["year"]) if str(a.get("year") or "").isdigit() else None
                x["thumb"] = thumbs[-1]["url"] if thumbs else x["thumb"]
                if not x["artists"]:
                    x["artists"] = [{"name": r.get("name"), "id": r.get("id")} for r in (a.get("artists") or [])]
                tracks.append(x)
        return {"title": a.get("title"), "year": a.get("year"), "type": a.get("type"), "tracks": tracks}
    return _cached("album", browse_id, 30 * DAY, fn)


def search(query: str, kind: str = "songs", limit: int = 10) -> list:
    def fn():
        res = client(lang="en").search(query, filter=kind, limit=limit)
        if kind == "artists":
            return [{"name": r.get("artist"), "id": r.get("browseId")} for r in res if r.get("browseId")]
        return [x for x in (_track(r) for r in res) if x]
    return _cached("search", f"{kind}:{query}", 14 * DAY, fn)


def playlists(query: str, limit: int = 6) -> list[dict]:
    """Listener-made playlists matching a scene or a pair of artists."""
    def fn():
        res = client(lang="en").search(query, filter="community_playlists", limit=limit)
        out = []
        for r in res:
            pid = r.get("browseId") or r.get("playlistId")
            if pid:
                out.append({"id": pid, "title": r.get("title"), "count": r.get("itemCount")})
        return out
    return _cached("plsearch", query, 14 * DAY, fn)


def playlist(pid: str, limit: int = 150) -> dict:
    def fn():
        try:
            p = client().get_playlist(pid, limit=limit)
        except Exception:
            return {"title": None, "tracks": []}
        return {"title": p.get("title"), "tracks": [x for x in (_track(t) for t in p.get("tracks") or []) if x]}
    return _cached("playlist", pid, 7 * DAY, fn)


def song(vid: str) -> dict:
    def fn():
        s = client().get_song(vid)
        mf = (s.get("microformat") or {}).get("microformatDataRenderer") or {}
        vd = s.get("videoDetails") or {}
        ps = s.get("playabilityStatus") or {}
        return {"vid": vid, "date": (mf.get("publishDate") or mf.get("uploadDate") or "")[:10],
                "views": int(vd.get("viewCount") or 0), "dur": int(vd.get("lengthSeconds") or 0),
                "embed": ps.get("playableInEmbed"), "status": ps.get("status"), "author": vd.get("author")}
    return _cached("song", vid, 90 * DAY, fn)


def track(vid: str) -> dict | None:
    """The track as the listener's own app shows it (original-language title and artist names)."""
    def fn():
        wp = client().get_watch_playlist(videoId=vid, limit=1)
        ts = [x for x in (_track(t) for t in wp.get("tracks", [])) if x and x["vid"] == vid]
        return ts[0] if ts else None
    return _cached("track", vid, 90 * DAY, fn)


def cached(kind: str, key: str) -> dict | None:
    """What song(), track() and the like last fetched, from the cache only, never the network: None if never."""
    path = store.CACHE / kind / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


COVER_HOSTS = ("i.ytimg.com", "lh3.googleusercontent.com", "yt3.googleusercontent.com", "yt3.ggpht.com")
COVER_MAX = 2 << 20


def cover_url(t: dict, size: int = 120) -> str:
    """Same rule as the page's cover(): album art at the requested size, else the video thumbnail."""
    u = t.get("thumb") or ""
    if "googleusercontent" in u or "ggpht" in u:
        return re.sub(r"=s\d+", f"=s{size}", re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", u))
    return u or f"https://i.ytimg.com/vi/{t['vid']}/mqdefault.jpg"


def _cover_path(u: str):
    return store.CACHE / "img" / hashlib.sha1(u.encode()).hexdigest()


def cover_cached(u: str) -> bool:
    return _cover_path(u).exists()


def cover_file(u: str):
    from urllib.parse import urlparse
    if urlparse(u).hostname not in COVER_HOSTS:
        raise ValueError("host")
    f = _cover_path(u)
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        data = b""
        with httpx.stream("GET", u, timeout=15, follow_redirects=True) as r:
            r.raise_for_status()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > COVER_MAX:
                    raise ValueError("size")
        f.write_bytes(data)
    return f


def warm_covers(tracks: list[dict], size: int = 120) -> None:
    with store.Pool(8) as ex:
        list(ex.map(lambda t: _quiet(cover_file, cover_url(t, size)), tracks))


def _quiet(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None
