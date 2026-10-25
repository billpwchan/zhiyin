import datetime as dt

from . import i18n, store, ytm
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


def sync_from_google(log=print) -> dict:
    """Merge the listener's liked videos into the library. Ranks never move: rank orders likes (lower is newer) and
    is also how the taste profile names them, so new likes get ranks below the current newest."""
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
    return {"videos": len(items), "added": len(added), "removed": len(removed),
            "songs": sum(1 for t in recs if not t["long"]), "first": first}


def save(records: list[dict]) -> None:
    lib = store.read_json(store.LIBRARY) or {}
    store.write_json(store.LIBRARY, {**lib, "synced": store.now(), "tracks": records})


def load() -> list[dict]:
    return (store.read_json(store.LIBRARY) or {}).get("tracks", [])


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
