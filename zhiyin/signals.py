"""What the listener's behaviour says beyond their likes.

From YouTube, with the same read-only access as the likes (kept and deleted like them): the songs they gave a
thumbs-down, the music channels they follow, the songs in playlists they made. From Zhiyin's play log: how each
listen started (did they choose the song?) and how far it got. From a Google Takeout file they upload: on how many
days each YouTube Music song was played.

Out of these come the songs they love without having liked them (`loves`: seeds and positive examples, listed on
「你的耳朵」 so they can confirm or drop each), the sounds they refuse (`refused`), and the artists they know
without a like (followed, or played often), who are not "new" to them."""
import json
import time
from collections import Counter, defaultdict

from . import google, i18n, library, llm, settings, store, ytm
from .text import display_title, fold, song_key

READ_EVERY_H = 24
KEEP_DAYS = 28
# Spotify (Mehrotra et al., CIKM 2021) weighs a stream by whether the listener chose the track; a song that merely
# played on is the weakest evidence there is. These are the sources of a start where the listener picked the song.
CHOSEN = {"pick", "prev", "ear"}
FULL, EARLY = 0.8, 10           # a listen that got 80% through is a full one; one left within 10 s an early skip
W_CHOSEN, W_PLAYED, W_IDLE, W_REPLAY = 0.3, 0.1, 0.05, 0.3
IDLE_S = 1800                   # nobody touched the page this long: the song may have played to an empty room
DAY_CAP = 0.4                   # repeats on one day saturate (Sguerra et al., RecSys 2022); days apart are what count
HALF_LIFE_DAYS = 120
W_HISTORY_DAY = 0.2             # a day in the Takeout history: who started the song is unknown
HISTORY_HALF_LIFE_DAYS = 365
W_SAVED, SAVED_HALF_LIFE_YEARS = 1.0, 2.0   # a save is a choice like a like: a love for about a year
W_EARLY = 0.2
RUN_S = 180                     # early skips this close together are a listener looking for something else right now
LOVE = 0.7                      # e.g. picked and heard through on three days, or saved to a playlist within the year
MAX_LOVES = 200
TZ_SHIFT = (8 - 5) * 3600       # days in UTC+8, starting at 5 am, so a late night counts with its evening
MUSIC_TOPICS = {"Jazz", "Reggae", "Rhythm_and_blues"}   # the other music topics all have "music" in their name
TOPIC = (" - Topic", " - 主題", " - 主题")   # YouTube's channel for an artist's catalogue


def day_of(ts: float) -> int:
    return int((ts + TZ_SHIFT) // 86400)


# ---------- read from YouTube ----------

def read_youtube(log=print, force: bool = False) -> dict:
    """Dislikes, followed music channels and own playlists, re-read once a day at most: one quota unit per page of
    50, about 15-40 units for most listeners and at most about 160 at the caps in google.py. A failure keeps what was read
    before and waits a day; nothing here may stop the likes from being read."""
    uid = store.uid()
    old = store.read_json(store.SIGNALS) or {}
    if not force and time.time() - max(old.get("read", 0), old.get("tried", 0)) < READ_EVERY_H * 3600:
        return old
    try:
        if not google.can_write(200):
            raise google.QuotaExceeded()   # leave the day's last units to the likes and the writes
        dis = google.disliked(uid)
        subs = google.subscriptions(uid)
        items = google.own_playlists(uid)
        info = google.videos(uid, [x["vid"] for x in items])
    except Exception as e:   # noqa: BLE001 - quota, a revoked token or a 5xx all mean "try tomorrow"
        log(i18n.tr("没读到 YouTube 上的其他信号（{e}）", e=str(e)[:80] or type(e).__name__))
        if time.time() - old.get("read", 0) > KEEP_DAYS * 86400:   # YouTube's rule: refreshed within 30 days, or gone
            old = {}
        store.write_json(store.SIGNALS, {**old, "tried": time.time()})
        return old

    def artist(channel):
        return library._channel_artist(channel or "")
    music = [d for d in dis if d["cat"] == google.MUSIC_CATEGORY]
    out = {
        "read": time.time(),
        "disliked": [{"vid": d["vid"], "title": display_title(d["title"], [{"name": artist(d["channel"])}]),
                      "artist": artist(d["channel"])} for d in music[:300]],
        "follows": [{"id": s["id"], "name": artist(s["title"])} for s in subs
                    if s["title"].endswith(TOPIC) or any("music" in t.lower() or t in MUSIC_TOPICS for t in s["topics"])],
        "saved": [{"vid": x["vid"], "title": display_title(info[x["vid"]]["title"] or x["title"], [{"name": artist(x["channel"])}]),
                   "artist": artist(x["channel"]), "at": (x["at"] or "")[:10] or None}
                  for x in items if info.get(x["vid"], {}).get("cat") == google.MUSIC_CATEGORY
                  and 60 <= info[x["vid"]]["dur"] <= library.LONG_MIX_S],
        "counts": {"disliked": len(dis), "subscriptions": len(subs), "playlist_items": len(items)},
    }
    store.write_json(store.SIGNALS, out)
    log(i18n.tr("读到 {d} 首不喜欢、{f} 个订阅的音乐频道、{s} 首歌单里的歌",
                d=len(out["disliked"]), f=len(out["follows"]), s=len(out["saved"])))
    return out


def youtube() -> dict:
    return store.read_json(store.SIGNALS) or {}


def follows() -> tuple[set[str], set[str]]:
    """Followed music channels as (channel ids, folded names). On YouTube Music an artist's id is their channel."""
    f = youtube().get("follows", [])
    return {x["id"] for x in f}, {fold(x["name"]) for x in f if fold(x["name"])}


# ---------- the play log ----------

def listens(uid: str | None = None, since: float = 0) -> list[dict]:
    """Each start in the log joined to how it ended: {"vid", "lane", "src", "ts", "end", "pos", "dur", "idle",
    "replays", and what the page showed with the song: "fit", "slot", "fam", "probe"}; "end" is done | skip | left |
    stop | error, or None when the page never said (closed mid-song before the log was complete). Test sessions are left
    out."""
    rows = store.db().execute(
        "select vid, lane, ts, ev, pos, src, dur, idle, fit, slot, fam, probe from plays where uid=? and ts>=? and test=0"
        " order by ts", (uid or store.uid(), since)).fetchall()
    out, open_ = [], {}
    for r in rows:
        ev = r["ev"] or "start"
        if ev == "start":
            if r["vid"] in open_:
                out.append(open_.pop(r["vid"]))
            open_[r["vid"]] = {"vid": r["vid"], "lane": r["lane"], "src": r["src"], "ts": r["ts"], "end": None,
                               "pos": 0.0, "dur": r["dur"], "idle": None, "replays": 0,
                               **{k: r[k] for k in ("fit", "slot", "fam", "probe")}}
            continue
        x = open_.get(r["vid"])
        if not x:
            continue
        if ev == "replay":
            x["replays"] += 1
            continue
        x["pos"] = max(x["pos"], r["pos"] or 0)
        x["dur"] = r["dur"] or x["dur"]
        if ev == "away":   # the page went to the background: where it was, in case nothing else arrives
            continue
        x.update(end=ev, idle=r["idle"])
        out.append(open_.pop(r["vid"]))
    out += open_.values()
    out.sort(key=lambda x: x["ts"])
    return out


def full(x: dict) -> bool:
    return x["end"] == "done" or bool(x["dur"] and x["pos"] >= FULL * x["dur"])


def early(x: dict) -> bool:
    """Skipped with Next within the first seconds. Leaving for another station, a song from the list, a comparison
    or a closed page ("stop") says nothing about the song."""
    return x["end"] == "skip" and (x["pos"] or 0) < EARLY


def lone_early_skips(ls: list[dict]) -> set[str]:
    """Songs left within the first seconds on their own. A run of quick skips says "not this, not now" about the
    moment (Meggetto et al., CIKM 2021); it isn't a verdict on each song in it."""
    ends = [x for x in ls if x["end"]]
    out = set()
    for i, x in enumerate(ends):
        if not early(x) or x["src"] == "compare" or x["lane"] == "ear":
            continue
        near = [y for y in ends[max(0, i - 1):i] + ends[i + 1:i + 2] if early(y) and abs(y["ts"] - x["ts"]) < RUN_S]
        if not near:
            out.add(x["vid"])
    return out


def play_scores(ls: list[dict]) -> dict[str, dict]:
    """How much each song's listens say the listener wants it: {vid: {"w", "days", "plays", "lanes"}}."""
    per = defaultdict(lambda: {"day": defaultdict(float), "early": 0, "plays": 0, "lanes": Counter(), "last": 0.0})
    now = time.time()
    for x in ls:
        if x["src"] == "compare":
            continue
        s = per[x["vid"]]
        s["last"] = max(s["last"], x["ts"])
        if x["lane"] and x["lane"] != "ear":
            s["lanes"][x["lane"]] += 1
        d = day_of(x["ts"])
        if full(x):
            s["plays"] += 1
            idle = (x["idle"] or 0) > IDLE_S
            s["day"][d] += W_CHOSEN if x["src"] in CHOSEN else W_IDLE if idle else W_PLAYED
        if x["replays"]:
            s["day"][d] += W_REPLAY
        if early(x):
            s["early"] += 1
    out = {}
    for v, s in per.items():
        w = sum(min(DAY_CAP, a) * 0.5 ** ((now / 86400 - d) / HALF_LIFE_DAYS) for d, a in s["day"].items())
        out[v] = {"w": w - W_EARLY * s["early"], "days": sum(1 for a in s["day"].values() if a > 0),
                  "plays": s["plays"], "lanes": s["lanes"], "last": s["last"]}
    return out


# ---------- imported history (Google Takeout) ----------

_hist_cache: dict[str, tuple[int, dict]] = {}


def history() -> dict:
    """The imported history, read once per change: an export of years of listening can run to megabytes."""
    p = store.HISTORY
    try:
        m = p.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    hit = _hist_cache.get(str(p))
    if not hit or hit[0] != m:
        hit = _hist_cache[str(p)] = (m, store.read_json(p) or {})
    return hit[1]


def forget_history() -> None:
    """Delete the imported history and, at once, every love that came only from it (with what was looked up for it)."""
    store.HISTORY.unlink(missing_ok=True)
    cache = store.read_json(store.IMPLICIT)
    if not cache:
        return
    loves = [r for r in cache.get("loves", []) if r.get("why") != ["history"]]
    keep = {r["vid"] for r in loves} | settings.not_me()[0]   # a dropped one stays listed, so it can be put back
    store.write_json(store.IMPLICIT, {**cache, "loves": loves, "meta": {v: m for v, m in cache.get("meta", {}).items() if v in keep},
                                      "assign": {v: a for v, a in cache.get("assign", {}).items() if v in keep}})


def history_heard() -> set[str]:
    """Songs played on YouTube Music twice or more: they know them, so they are not recommended."""
    return set(history().get("songs", {}))


def save_history(songs: list[list], span: list[str], entries: int) -> dict:
    """Aggregates the page made from the Takeout file, which itself never leaves the browser: per song
    [vid, plays, days, first day, last day, recency-weighted days, title, artist]."""
    keep = {}
    for s in songs:
        vid, n, days, first, last, rw, title, artist = s
        keep[vid] = {"n": int(n), "days": int(days), "first": first, "last": last, "rw": float(rw),
                     "title": title, "artist": artist}
    out = {"at": time.time(), "span": span, "entries": entries, "songs": keep}
    store.write_json(store.HISTORY, out)
    return out


def history_scores() -> dict[str, dict]:
    h = history()
    age = (time.time() - h.get("at", time.time())) / 86400
    fade = 0.5 ** (age / HISTORY_HALF_LIFE_DAYS)
    return {v: {"w": W_HISTORY_DAY * s["rw"] * fade, "days": s["days"], "plays": s["n"]} for v, s in h.get("songs", {}).items()}


# ---------- what it all says ----------

def _years(d: str | None) -> float:
    try:
        return max(0.0, (time.time() - time.mktime(time.strptime(d[:10], "%Y-%m-%d"))) / (365.25 * 86400))
    except (TypeError, ValueError):
        return 9.0


def _excluded() -> tuple[set[str], dict]:
    """Songs that can't be an unspoken love: already liked (any of their videos), answered in Zhiyin, refused on
    YouTube, or said not to be the listener's taste."""
    tracks = library.load()
    vids = {t[k] for t in tracks for k in ("vid", "mv", "ll") if t.get(k)}
    con = store.db()
    vids |= {r["vid"] for r in con.execute("select vid from feedback where uid=?", (store.uid(),))}
    vids |= {d["vid"] for d in youtube().get("disliked", [])}
    vids |= settings.not_me()[0]
    songs = defaultdict(set)
    for t in tracks:
        songs[song_key(t["title"])] |= {fold(a["name"]) for a in t["artists"]}
    return vids, songs


ASSIGN_SYSTEM = ("Assign each song the listener plays often (without having liked it) to the single best-fitting "
                 "listening lane, and optionally a second lane in 'also' ('none' if no second lane fits). Use 'none' as "
                 "the main lane only if the song fits no lane at all. Lanes:\n")


def _assign(prof: dict, recs: list[dict]) -> dict[str, list[str]]:
    from .profile import ASSIGN_SCHEMA
    keys = [l["key"] for l in prof["lanes"]] + ["none"]
    schema = json.loads(json.dumps(ASSIGN_SCHEMA))
    for k in ("lane", "also"):
        schema["properties"]["items"]["items"]["properties"][k]["enum"] = keys
    lanes = "\n".join(f"- {l['key']}: {l['english']} — {l['sound']} (langs {','.join(l['langs'])}; energy {l['energy']})"
                      for l in prof["lanes"])
    out = {}
    for i in range(0, len(recs), 150):
        chunk = recs[i:i + 150]
        lines = "\n".join(f"{j}|{r['title']}|{', '.join(a['name'] for a in r['artists'])}|played on {r['days']} days"
                          for j, r in enumerate(chunk))
        res = llm.call("i|title|artists|how often\n" + lines, ASSIGN_SYSTEM + lanes, schema, model="sonnet")
        for x in res["items"]:
            if 0 <= x["i"] < len(chunk):
                out[chunk[x["i"]]["vid"]] = [x["lane"]] + ([x["also"]] if x["also"] not in ("none", x["lane"]) else [])
    return out


def refresh(prof: dict, log=print) -> list[dict]:
    """Work out the songs loved without a like, with each one's station, and keep them for `loves()`."""
    cache = store.read_json(store.IMPLICIT) or {}
    meta, assign = cache.get("meta", {}), cache.get("assign", {})
    lane_keys = {l["key"] for l in prof.get("lanes", [])}
    plays = play_scores(listens())
    total = defaultdict(lambda: {"w": 0.0, "days": 0, "plays": 0, "why": set(), "lanes": Counter()})
    for v, s in plays.items():
        t = total[v]
        t["w"] += s["w"]
        t["days"] += s["days"]
        t["plays"] += s["plays"]
        t["lanes"] += Counter({k: n for k, n in s["lanes"].items() if k in lane_keys})
        if s["w"] > 0:
            t["why"].add("plays")
    for v, s in history_scores().items():
        t = total[v]
        t["w"] += s["w"]
        t["days"] += s["days"]
        t["plays"] += s["plays"]
        t["why"].add("history")
    for s in youtube().get("saved", []):
        t = total[s["vid"]]
        t["w"] += W_SAVED * 0.5 ** (_years(s["at"]) / SAVED_HALF_LIFE_YEARS)
        t["why"].add("playlist")
    vids, liked_songs = _excluded()
    todo = sorted((v for v, t in total.items() if t["w"] >= LOVE and v not in vids), key=lambda v: -total[v]["w"])
    todo = todo[:MAX_LOVES * 2]
    def look(v):
        try:
            return meta.get(v) or ytm.track(v)
        except Exception:   # noqa: BLE001 - a video taken down since: leave it out, keep the rest
            return None
    with store.Pool(4) as ex:
        found = dict(zip(todo, ex.map(look, todo)))
    loves, seen = [], {}
    for v in todo:
        m = found.get(v)
        if not m or not m.get("artists") or m.get("type") not in ("ATV", "OMV") or not 60 <= (m.get("dur") or 200) <= library.LONG_MIX_S:
            continue
        meta[v] = {k: m.get(k) for k in ("title", "artists", "type", "dur", "thumb")}
        names = {fold(a["name"]) for a in m["artists"]}
        key = (song_key(display_title(m["title"], m["artists"])), fold(m["artists"][0]["name"]))
        if liked_songs.get(key[0], set()) & names:
            continue   # a like of theirs under another video
        if key in seen:   # the same song under two videos: one entry, with both listens
            seen[key]["w"] += total[v]["w"]
            continue
        t = total[v]
        seen[key] = rec = {"vid": v, **meta[v], "w": round(t["w"], 3), "days": t["days"], "plays": t["plays"],
                           "why": sorted(t["why"]), "lane": [t["lanes"].most_common(1)[0][0]] if t["lanes"] else assign.get(v)}
        loves.append(rec)
        if len(loves) >= MAX_LOVES:
            break
    need = [r for r in loves if not r["lane"]]
    if need and prof.get("lanes") and not llm.unavailable():
        try:
            got = _assign(prof, need)
            assign.update(got)
            for r in need:
                r["lane"] = got.get(r["vid"])
        except Exception as e:   # noqa: BLE001 - placing them can wait for the next edition
            log(i18n.tr("常听的歌暂时没放进电台（{e}）", e=str(e)[:80]))
    for r in loves:
        r["lane"] = r["lane"] or ["none"]
    keep = set(todo) | settings.not_me()[0]   # nothing about a song that no longer counts, but a dropped one stays listed
    store.write_json(store.IMPLICIT, {"at": time.time(), "loves": loves, "meta": {v: m for v, m in meta.items() if v in keep},
                                      "assign": {v: a for v, a in assign.items() if v in keep}})
    if loves:
        log(i18n.tr("从播放里读出 {n} 首你常听、没点喜欢的歌", n=len(loves)))
    return loves


def loves() -> list[dict]:
    """The songs loved without a like, as of the last `refresh`, less any liked, answered or dropped since."""
    got = (store.read_json(store.IMPLICIT) or {}).get("loves", [])
    if not got:
        return []
    vids, liked_songs = _excluded()
    return [r for r in got if r["vid"] not in vids
            and not (liked_songs.get(song_key(display_title(r["title"], r["artists"])), set())
                     & {fold(a["name"]) for a in r["artists"]})]


def refused() -> set[str]:
    """Songs whose sound the listener turned down: "not for me" here, a thumbs-down on YouTube, or skipped within
    seconds on its own (not one of a run of quick skips), unless they liked it, heard it through or play it often."""
    con = store.db()
    fb = con.execute("select vid, action from feedback where uid=?", (store.uid(),)).fetchall()
    out = {r["vid"] for r in fb if r["action"] == "dislike"}
    out |= {d["vid"] for d in youtube().get("disliked", [])}
    tracks = library.load()
    taken_back = {t[k] for t in tracks for k in ("vid", "mv", "ll") if t.get(k)}
    taken_back |= {r["vid"] for r in fb if r["action"] == "like"} | {r["vid"] for r in loves()}
    ls = listens()
    taken_back |= {x["vid"] for x in ls if full(x)}
    return out | (lone_early_skips(ls) - taken_back)


def weight(r: dict) -> float:
    return min(1.0, r["w"])
