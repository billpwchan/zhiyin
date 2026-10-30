import datetime as dt
import re
import unicodedata

from . import i18n, netease, store, ytm
from .text import display_title, dur_s, fold, song_key

MV = {"A": "ATV", "O": "OMV", "U": "UGC", "S": "OFFICIAL_SOURCE_MUSIC"}
LONG_MIX_S = 600


def _record(rank, vid, mvt, title, artists, album, dur, source):
    d = dur_s(dur) if isinstance(dur, str) else (dur or 0)
    return {"rank": rank, "vid": vid, "type": mvt, "title": title, "artists": artists, "album": album,
            "dur": d, "long": d > LONG_MIX_S, "source": source}


def import_snapshot(path) -> list[dict]:
    """TSV exported from the liked-songs page in the browser: rank, vid, type, title, artists, album, duration."""
    out = []
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 7 or not p[1]:
            continue
        rank, vid, mv, title, arts, alb, dur = p[:7]
        artists = []
        if arts.startswith("~"):
            artists = [{"name": arts[1:], "id": None}]
        else:
            for a in arts.split(";"):
                name, _, aid = a.rpartition("@")
                artists.append({"name": name, "id": aid or None})
        album = None
        if alb:
            n, _, aid = alb.rpartition("@")
            album = {"name": n, "id": aid or None}
        out.append(_record(int(rank), vid, MV.get(mv, mv or "UNKNOWN"), title, artists, album, dur, "snapshot"))
    return out


def sync_from_account() -> list[dict]:
    """Needs data/browser.json (ytmusicapi browser auth the user sets up themselves)."""
    yt = ytm.client(auth=True)
    res = yt.get_liked_songs(limit=None)
    out = []
    for i, t in enumerate(res.get("tracks", [])):
        if not t.get("videoId"):
            continue
        artists = [{"name": a["name"], "id": a.get("id")} for a in (t.get("artists") or [])]
        album = {"name": t["album"]["name"], "id": t["album"].get("id")} if t.get("album") else None
        out.append(_record(i, t["videoId"], (t.get("videoType") or "").replace("MUSIC_VIDEO_TYPE_", ""),
                           t["title"], artists, album, t.get("duration_seconds") or t.get("duration"), "account"))
    return out


def counterpart(title: str, names: list[str], dur: int) -> dict | None:
    """The audio track of the same recording, when YouTube Music has one."""
    from .lyrics import _score
    best = (0.0, None)
    for h in ytm.search(f"{names[0] if names else ''} {title}", "songs", 6):
        if h.get("type") != "ATV" or (dur and h.get("dur") and h["dur"] > dur + 4):
            continue
        sc = _score(title, names, 0, h["title"], ", ".join(a["name"] for a in h["artists"]), 0)
        if sc > best[0]:
            best = (sc, h)
    return best[1] if best[0] >= 0.85 else None


def _channel_artist(channel: str) -> str:
    for tail in (" - Topic", " - 主題", "VEVO", " Official", " official"):
        channel = channel.removesuffix(tail)
    return channel.strip()


def _from_like(item: dict, info: dict) -> dict | None:
    """One liked video as a library record, preferring the audio track of the same recording."""
    channel = info.get("channel") or item["channel"]
    artist = _channel_artist(channel)
    raw = info.get("title") or item["title"]
    title = display_title(raw, [{"name": artist}])
    dur = info.get("dur") or 0
    if not channel.endswith((" - Topic", " - 主題")):
        h = counterpart(title, [artist], dur)
        if h:
            return {**_record(0, h["vid"], "ATV", h["title"], h["artists"], h.get("album"), h.get("dur") or dur, "google"),
                    "ll": item["vid"], "mv": item["vid"]}
    t = ytm.track(item["vid"])
    if t:
        return {**_record(0, item["vid"], t["type"] or "UGC", t["title"], t["artists"], t.get("album"), t.get("dur") or dur,
                          "google"), "ll": item["vid"]}
    return {**_record(0, item["vid"], "UGC", title, [{"name": artist, "id": None}], None, dur, "google"), "ll": item["vid"]}


def sync_from_google(log=print, glimpsed=None) -> dict:
    """Merge the listener's liked videos into the library. Ranks never move: rank orders likes (lower is newer) and
    is also how the taste profile names them, so new likes get ranks below the current newest.

    On the first import, the liked videos as YouTube lists them are written out at once (store.GLIMPSE), before the
    minutes it takes to match each one to its song, so the record can be drawn while that runs; then `glimpsed()`."""
    from . import google
    uid = store.uid()
    lib = store.read_json(store.LIBRARY) or {}
    recs = lib.get("tracks", [])
    first = not recs
    items = google.likes(uid, log=log)
    ll_ids = {it["vid"] for it in items}
    have_ids = {t[k] for t in recs for k in ("vid", "mv", "ll") if t.get(k)}
    have_keys = {(song_key(t["title"]), fold(t["artists"][0]["name"]) if t["artists"] else "") for t in recs}
    # A library imported another way only takes likes made after it was taken; older entries are already in it,
    # often under another video of the same song.
    since = 0 if first else lib.get("google_since") or lib.get("synced") or 0

    def liked_ts(it):
        try:
            return dt.datetime.fromisoformat(it["at"].replace("Z", "+00:00")).timestamp()
        except (AttributeError, ValueError):
            return 0
    new = [it for it in items if it["vid"] not in have_ids and liked_ts(it) > since - 86400]
    log(i18n.tr("查看 {n} 个新喜欢的视频是不是歌", n=len(new)))
    info = google.videos(uid, [it["vid"] for it in new])
    music = [it for it in new if info.get(it["vid"], {}).get("cat") == google.MUSIC_CATEGORY
             and not info[it["vid"]].get("live")]
    if first:
        songs = []
        for it in music:
            v = info[it["vid"]]
            if v["dur"] > LONG_MIX_S:
                continue
            artist = _channel_artist(v["channel"] or it["channel"])
            songs.append({"vid": it["vid"], "title": display_title(v["title"] or it["title"], [{"name": artist}]),
                          "artist": artist, "at": (it["at"] or "")[:10], "dur": v["dur"]})
        store.write_json(store.GLIMPSE, {"at": store.now(), "songs": songs})
        if glimpsed:
            glimpsed()
    done = [0]

    def resolve(it):
        r = _from_like(it, info[it["vid"]])
        done[0] += 1
        if done[0] % 20 == 0:
            log(i18n.tr("整理歌曲 {d} / {n}", d=done[0], n=len(music)))
        return r
    with store.Pool(6) as ex:
        resolved = list(ex.map(resolve, music))
    added = []
    for it, r in zip(music, resolved):
        key = (song_key(r["title"]), fold(r["artists"][0]["name"]) if r["artists"] else "")
        if r["vid"] in have_ids or key in have_keys:
            continue
        have_ids.add(r["vid"])
        have_keys.add(key)
        r["liked_est"] = (it["at"] or "")[:10] or None
        added.append(r)
    base = min((t["rank"] for t in recs), default=len(added))
    for j, r in enumerate(added):  # added is newest first
        r["rank"] = base - len(added) + j
    removed = [t for t in recs if t.get("source") == "google" and t.get("ll") and t["ll"] not in ll_ids]
    gone = {id(t) for t in removed}
    recs = added + [t for t in recs if id(t) not in gone]
    recs.sort(key=lambda t: t["rank"])
    store.write_json(store.LIBRARY, {**lib, "synced": store.now(), "google_since": store.now(), "tracks": recs})
    store.GLIMPSE.unlink(missing_ok=True)   # only for drawing the record before the library existed; not kept
    return {"videos": len(items), "added": len(added), "removed": len(removed),
            "songs": sum(1 for t in recs if not t["long"]), "first": first}


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_HAN_NAME = re.compile(r"[\u3400-\u9fff]{2,4}")


def _bare(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _pinyin(names: list[str]) -> list[str]:
    """A Chinese name the way YouTube Music often spells it: pinyin, family name first or last (宋冬野 Song Dongye,
    李荣浩 Ronghao Li)."""
    from pypinyin import lazy_pinyin
    out = []
    for n in names:
        if _HAN_NAME.fullmatch(n):
            p = lazy_pinyin(n)
            out += [" ".join(p), " ".join(p[1:] + p[:1])]
    return out


def match_netease(t: dict) -> dict | None:
    """The YouTube Music song for a NetEase like: the same title and length, by the same artist. YouTube Music often
    writes a Chinese or Japanese artist's name in Latin letters (陈奕迅 / Eason Chan, 宋冬野 / Song Dongye), so a name
    in the other script is checked against its pinyin and the other names NetEase knows them by; a different name in
    the same script is someone's cover."""
    from .lyrics import DUR_TOL, VERSION, _artist_sim, _sim
    names = [a["name"] for a in t["artists"]]
    alias = None
    for h in ytm.search(f"{names[0] if names else ''} {t['title']}", "songs", 6):
        if t["dur"] and h.get("dur") and abs(h["dur"] - t["dur"]) > DUR_TOL:
            continue
        if VERSION.search(h["title"]) and not VERSION.search(t["title"]):
            continue
        cand = ", ".join(a["name"] for a in h["artists"])
        # "默 - Mo", "Sofia" for "Sofía": YouTube Music glosses titles and drops accents
        if not cand or max(_sim(t["title"], h["title"]),
                           _sim(_bare(t["title"]), _bare(display_title(h["title"], h["artists"])))) < 0.9:
            continue
        if _artist_sim(names, cand) >= 0.6:
            return h
        if bool(_CJK.search(cand)) == bool(_CJK.search(" ".join(names))):
            continue
        if _artist_sim(_pinyin(names), cand) >= 0.9:
            return h
        if alias is None:
            alias = [x for aid in t.get("ne_ar", [])[:2] for x in netease.aliases(aid)]
        if alias and _artist_sim(alias, cand) >= 0.6:
            return h
    return None


def sync_from_netease(link: str, log=print, glimpsed=None, got: dict | None = None) -> dict:
    """The listener's NetEase likes, as YouTube Music songs: the stations are built and played from YouTube's
    catalogue. A like with no match there is kept aside (`unmatched`) so it is never recommended back to them.
    Ranks never move, as in sync_from_google; a song they unliked on NetEase leaves."""
    lib = store.read_json(store.LIBRARY) or {}
    recs = lib.get("tracks", [])
    first = not recs
    got = got or netease.likes(link)
    ne_tracks = got["tracks"]
    if first:
        store.write_json(store.GLIMPSE, {"at": store.now(), "songs": [
            {"vid": t["vid"], "title": t["title"], "artist": t["artists"][0]["name"] if t["artists"] else "",
             "at": t["liked_est"] or "", "dur": t["dur"], "ne": t["ne"], "ne_ar": t["ne_ar"]} for t in ne_tracks]})
        if glimpsed:
            glimpsed()
    have = {t["ne"] for t in recs if t.get("ne")}
    todo = [t for t in ne_tracks if t["ne"] not in have]
    log(i18n.tr("在 YouTube Music 上找 {n} 首歌", n=len(todo)))
    done = [0]

    def find(t):
        h = match_netease(t)
        # kept aside under every name of its artist, so YouTube Music's spelling of it is recognised too
        aka = [] if h else [x for aid in t["ne_ar"][:1] for x in netease.aliases(aid)]
        done[0] += 1
        if done[0] % 20 == 0:
            log(i18n.tr("整理歌曲 {d} / {n}", d=done[0], n=len(todo)))
        return h, aka
    with store.Pool(6) as ex:
        found = list(ex.map(find, todo))
    have_ids = {t[k] for t in recs for k in ("vid", "mv", "ll") if t.get(k)}
    added, unmatched = [], []
    for t, (h, aka) in zip(todo, found):
        if not h:
            unmatched.append({"ne": t["ne"], "title": t["title"], "artists": [a["name"] for a in t["artists"]] + aka,
                              "liked_est": t["liked_est"]})
            continue
        if h["vid"] in have_ids:
            continue   # a second NetEase entry of the same recording (a re-release, a duplicate upload)
        have_ids.add(h["vid"])
        r = _record(0, h["vid"], h["type"] or "ATV", h["title"], h["artists"], h.get("album"), h.get("dur") or t["dur"], "163")
        added.append({**r, "liked_est": t["liked_est"], "ne": t["ne"], "ne_title": t["title"],
                      "ne_artists": [a["name"] for a in t["artists"]]})
    base = min((t["rank"] for t in recs), default=len(added))
    for j, r in enumerate(added):  # added is newest first
        r["rank"] = base - len(added) + j
    now_ids = {t["ne"] for t in ne_tracks}
    removed = [t for t in recs if t.get("ne") and t["ne"] not in now_ids]
    gone = {id(t) for t in removed}
    recs = added + [t for t in recs if id(t) not in gone]
    recs.sort(key=lambda t: t["rank"])
    scores = netease.ranking(got.get("owner"))
    for t in recs:
        t["ne_score"] = scores.get(t.get("ne"))
    store.write_json(store.LIBRARY, {**lib, "synced": store.now(), "source": "163", "tracks": recs, "unmatched": unmatched,
                                     "netease": {"key": got["key"], "total": got["total"]}})
    store.GLIMPSE.unlink(missing_ok=True)
    return {"videos": got["total"], "added": len(added), "removed": len(removed), "unmatched": len(unmatched),
            "songs": sum(1 for t in recs if not t["long"]), "first": first, "key": got["key"]}


def unmatched() -> list[dict]:
    """NetEase likes with no YouTube Music match: not in the library, but already theirs."""
    return (store.read_json(store.LIBRARY) or {}).get("unmatched", [])


def save(records: list[dict]) -> None:
    lib = store.read_json(store.LIBRARY) or {}
    store.write_json(store.LIBRARY, {**lib, "synced": store.now(), "tracks": records})


def load() -> list[dict]:
    return (store.read_json(store.LIBRARY) or {}).get("tracks", [])


def find(q: str, n: int = 8) -> list[dict]:
    """Their own likes matching what they typed, word by word, in title, artist or album and in either Chinese
    script. Songs come before fancams and AI covers; then a title that starts with it, a singer who is it, a title
    that holds it; then the newest likes."""
    words = [w for w in (fold(i18n.convert(x, "zh-Hant", "zh-Hans")) for x in (q or "").split()) if w]
    if not words:
        return []
    zh = lambda s: fold(i18n.convert(s, "zh-Hant", "zh-Hans"))   # noqa: E731
    kinds = {v: x.get("kind") for v, x in (store.read_json(store.TAGS) or {}).items()}
    hits = []
    for t in load():
        title, artists = zh(t["title"]), [zh(a["name"]) for a in t["artists"]]
        rest = "".join(artists) + zh((t.get("album") or {}).get("name") or "")
        if all(w in title or w in rest for w in words):
            w = words[0]
            tier = 0 if title.startswith(w) else 1 if any(a.startswith(w) for a in artists) else 2 if w in title else 3
            hits.append((kinds.get(t["vid"]) in ("novelty", "clip"), tier, t["rank"], t))
    hits.sort(key=lambda h: h[:3])
    return [h[3] for h in hits[:n]]


def estimate_like_dates(records: list[dict]) -> None:
    """YouTube Music hides when a song was liked. A like can't precede the upload it points at, so the running
    2nd-newest upload date among older likes is a lower bound. Album-track (ATV) uploads are skipped because
    labels re-upload them years later and YouTube silently swaps the liked video to the new upload."""
    import heapq
    top: list[str] = []
    for t in sorted(records, key=lambda t: -t["rank"]):
        d = ytm.song(t["vid"]).get("date")
        t["uploaded"] = d
        if d and t["type"] != "ATV":
            heapq.heappush(top, d)
            if len(top) > 2:
                heapq.heappop(top)
        t["liked_est"] = top[0] if top else None
