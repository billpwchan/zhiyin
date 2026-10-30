import datetime as dt
import math
import random
import re
from collections import Counter, defaultdict

from . import settings, signals, store, ytm
from .text import display_title, fold, is_version, song_key

_CREDIT_SPLIT = re.compile(r"\s+(?:x|×|and|feat\.?|ft\.?)\s+|\s*[&,、/]\s*", re.I)

SCRIPT = {"ko": re.compile(r"[가-힯]"), "ja": re.compile(r"[぀-ヿ]"), "th": re.compile(r"[฀-๿]")}
HALF_LIFE_YEARS = 0.6
FRESH_EDITIONS = 2     # the last editions stay out, so asking for a new edition brings new songs
SHOWN_DAYS = 21        # shown earlier but never played: may come back, behind fresher candidates of the same strength


def _years_ago(date: str | None) -> float:
    if not date:
        return 9.0
    d = dt.date.fromisoformat(date[:10])
    return max(0.0, (dt.date.today() - d).days / 365.25)


class Known:
    """Everything the listener already has or has rejected, used to keep picks new to them."""

    def __init__(self, tracks: list[dict], profile: dict):
        con = store.db()
        fb = con.execute("select vid, action, scope, artist_id, artist, title from feedback where uid=?", (store.uid(),)).fetchall()
        # Only what they actually heard is used up, and for good: a song they played or skipped never comes back,
        # under any of its videos. Excluding everything ever shown let each rebuild burn the best candidates, so later
        # editions were picked from leftovers (2026-10-25).
        shown_since = store.now() - SHOWN_DAYS * 86400
        heard = con.execute("select vid, title, artist from plays where uid=? and ev in ('done', 'skip', 'left') and test=0",
                            (store.uid(),)).fetchall()
        self.heard = {r["vid"] for r in heard}
        # a song YouTube refused to play here would only fail again
        self.heard |= {r["vid"] for r in con.execute("select distinct vid from plays where uid=? and ev='error' and test=0",
                                                     (store.uid(),))}
        self.heard |= signals.history_heard()   # played twice or more on YouTube Music (an imported Takeout file)
        self.heard_songs = defaultdict(set)
        for r in heard:
            if r["title"]:
                self.heard_songs[song_key(r["title"])].add(fold(r["artist"] or ""))
        self.recent_shown = {r["vid"] for r in con.execute("select vid from shown where uid=? and ts > ?",
                                                           (store.uid(), shown_since))} - self.heard
        self.just_shown = {r["vid"] for r in con.execute(
            "select vid from shown where uid=? and edition in (select edition from shown where uid=? group by edition"
            " order by max(ts) desc limit ?)", (store.uid(), store.uid(), FRESH_EDITIONS))} - self.heard
        self.taken = set()   # placed in another lane of the edition being built
        self.vids = {t["vid"] for t in tracks} | {t[k] for t in tracks for k in ("mv", "ll") if t.get(k)}
        self.songs = defaultdict(set)  # song_key -> folded artist names
        self.refused_songs = defaultdict(set)
        self.artist_likes = Counter()
        self.artist_names = {}
        from . import i18n, library
        for t in tracks:
            names = {fold(a["name"]) for a in t["artists"]}
            self.songs[song_key(t["title"])] |= names
            if t.get("ne_title"):   # the same song under its NetEase name, in either Chinese script
                for v in {t["ne_title"], i18n.convert(t["ne_title"], "zh-Hans", "zh-Hant")}:
                    self.songs[song_key(v)] |= names | {fold(a) for a in t["ne_artists"]}
            if t["long"]:
                continue
            for a in t["artists"]:
                k = a.get("id") or fold(a["name"])
                self.artist_likes[k] += 1
                self.artist_likes[fold(a["name"])] += 1
                self.artist_names[k] = a["name"]
        for x in library.unmatched():   # a NetEase like YouTube Music has under another name, or not at all
            for v in {x["title"], i18n.convert(x["title"], "zh-Hans", "zh-Hant")}:
                self.songs[song_key(v)] |= {fold(a) for a in x["artists"]}
        self.disliked = {r["vid"] for r in fb if r["action"] in ("dislike", "known", "like")}
        self.blocked_artists = {r["artist_id"] or fold(r["artist"] or "") for r in fb if r["scope"] == "artist"}
        self.blocked_artists |= settings.not_me()[1]   # an artist they said isn't them isn't recommended either
        for r in fb:
            if r["action"] == "like":
                self.songs[song_key(r["title"] or "")].add(fold(r["artist"] or ""))
        self.ledger = {fold(x) for x in settings.load().get("never", [])}
        yt = signals.youtube()
        for d in yt.get("disliked", []):   # a thumbs-down on YouTube, under any of the song's videos
            self.disliked.add(d["vid"])
            self.refused_songs[song_key(d["title"])].add(fold(d["artist"]))
        for x in yt.get("saved", []) + list(signals.history().get("songs", {}).values()):
            self.songs[song_key(x["title"])].add(fold(x["artist"]))   # in a playlist of theirs, or played on YouTube
        self.vids |= {x["vid"] for x in yt.get("saved", [])}
        self.follow_ids, self.follow_names = signals.follows()
        self.loves = signals.loves()
        self.played_artists = set()
        for r in self.loves:
            self.songs[song_key(r["title"])] |= {fold(a["name"]) for a in r["artists"]}
            self.played_artists |= {a.get("id") or fold(a["name"]) for a in r["artists"]} | {fold(a["name"]) for a in r["artists"]}

    def artist_familiarity(self, artists: list[dict]) -> int:
        """How many of the listener's likes are by these artists."""
        return max((self.artist_likes.get(a.get("id") or "", 0) or self.artist_likes.get(fold(a["name"]), 0)
                    for a in artists), default=0)

    def artist_known(self, artists: list[dict]) -> str | None:
        """Why an artist with no liked song isn't new to them: "follow" (they follow the channel on YouTube) or
        "plays" (they play the artist's songs often without liking them)."""
        if any((a.get("id") and a["id"] in self.follow_ids) or fold(a["name"]) in self.follow_names for a in artists):
            return "follow"
        if any((a.get("id") and a["id"] in self.played_artists) or fold(a["name"]) in self.played_artists for a in artists):
            return "plays"
        return None

    def is_new(self, artists: list[dict]) -> bool:
        return not self.artist_familiarity(artists) and not self.artist_known(artists)

    def reject(self, t: dict) -> str | None:
        if t["vid"] in self.vids:
            return "liked"
        if t["vid"] in self.disliked:
            return "feedback"
        if t["vid"] in self.heard:
            return "heard"
        if t["vid"] in self.taken:
            return "taken"
        if t["vid"] in self.just_shown:
            return "shown"
        names = {fold(a["name"]) for a in t["artists"]}
        key = song_key(t["title"])
        keys = {key, song_key(display_title(t["title"], t["artists"]))}
        left, dash, right = t["title"].partition(" - ")
        if dash and right:   # "J Tajor & sunkis - Like I Do": the uploader put the artists in the title
            keys.add(song_key(right))
            names |= {fold(x) for x in _CREDIT_SPLIT.split(left) if fold(x)}
        if any(k and k in self.songs and (self.songs[k] & names or not names) for k in keys):
            return "same song"
        if any(k and k in self.heard_songs and self.heard_songs[k] & names for k in keys):
            return "heard"
        if any(k and k in self.refused_songs and self.refused_songs[k] & names for k in keys):
            return "feedback"
        if any((a.get("id") or fold(a["name"])) in self.blocked_artists or fold(a["name"]) in self.blocked_artists
               for a in t["artists"]):
            return "blocked artist"
        if fold(t["title"]) in self.ledger or key in self.ledger:
            return "ledger"
        return None


def lane_seeds(lane: dict, tracks: list[dict], profile: dict, rng: random.Random, n: int = 10,
               loves: list[dict] = ()) -> list[dict]:
    assign = profile.get("assign", {})
    picked_by_editor = set(lane["seeds"])
    aside = {r for s in profile.get("set_aside", []) for r in s["ranks"]}
    nm = settings.not_me()
    reps = Counter(song_key(t["title"]) for t in tracks)
    pool = []
    for t in tracks:
        if t["long"] or t["rank"] in aside or t["type"] not in ("ATV", "OMV") or settings.is_not_me(t, nm):
            continue
        lanes = assign.get(t["vid"], [])
        if lane["key"] not in lanes and t["rank"] not in picked_by_editor:
            continue
        w = 0.5 ** (_years_ago(t.get("liked_est")) / HALF_LIFE_YEARS)
        w *= 1.0 if (lanes[:1] == [lane["key"]]) else 0.6
        w *= 1.5 if reps[song_key(t["title"])] > 1 else 1.0
        w *= 1.4 if t["rank"] in picked_by_editor else 1.0
        pool.append((w, t))
    for r in store.db().execute("select vid, title, artist, artist_id from feedback where uid=? and action='like' and lane=?",
                                (store.uid(), lane["key"])):
        pool.append((1.6, {"vid": r["vid"], "title": r["title"], "artists": [{"name": r["artist"], "id": r["artist_id"]}],
                           "rank": None, "type": "ATV", "liked_est": None}))
    # Played often without a like: as strong as a like when the evidence is (signals.LOVE and up, capped at 1).
    # Marked, so the page never calls one of these "a song you liked".
    for r in loves:
        if lane["key"] in (r.get("lane") or [])[:1] and not settings.is_not_me(r, nm):
            pool.append((1.2 * signals.weight(r), {"vid": r["vid"], "title": r["title"], "artists": r["artists"],
                                                    "rank": None, "type": r.get("type") or "ATV", "liked_est": None,
                                                    "implicit": True}))
    # Weighted sampling without replacement (Efraimidis-Spirakis) so each edition rotates through the lane.
    keyed = sorted(pool, key=lambda p: -(rng.random() ** (1.0 / p[0])))
    out, seen_art = [], Counter()
    for w, t in keyed:
        a = t["artists"][0]["name"] if t["artists"] else ""
        if seen_art[a] >= 2:
            continue
        seen_art[a] += 1
        out.append({**t, "w": w})
        if len(out) >= n:
            break
    return out


def _lang_ok(t: dict, langs: list[str]) -> bool:
    text = t["title"] + " " + " ".join(a["name"] for a in t["artists"])
    for code, rx in SCRIPT.items():
        if rx.search(text) and code not in langs:
            return False
    return True


def gather(lane: dict, seeds: list[dict], known: Known, core: list[dict], explore: bool = True) -> dict:
    """Collect candidate tracks for one lane from the YouTube Music graph. Returns {vid: candidate}."""
    cands: dict[str, dict] = {}
    rejected = Counter()

    def add(t, source, via, weight):
        if not t or not t.get("vid") or not t.get("artists"):
            return
        if not (90 <= (t.get("dur") or 200) <= 600) or t.get("type") not in ("ATV", "OMV", ""):
            rejected["format"] += 1
            return
        if is_version(t["title"]):
            rejected["version"] += 1
            return
        if not _lang_ok(t, lane["langs"]):
            rejected["language"] += 1
            return
        why = known.reject(t)
        if why:
            rejected[why] += 1
            return
        c = cands.get(t["vid"])
        if not c:
            c = cands[t["vid"]] = {**t, "support": 0.0, "via": [], "sources": set()}
        c["support"] += weight
        c["sources"].add(source)
        if via and via not in c["via"]:
            c["via"].append(via)

    def seed_job(s):
        r = ytm.radio(s["vid"])
        rel = ytm.related(r["related"]) if r.get("related") else {"songs": [], "artists": []}
        return s, r, rel

    related_artists = Counter()
    with store.Pool(4) as ex:
        for s, r, rel in ex.map(seed_job, seeds):
            label = f"{s['title']} - {s['artists'][0]['name']}" if s["artists"] else s["title"]
            for pos, t in enumerate(r["tracks"][1:]):
                add(t, "radio", label, s["w"] / (1 + pos / 12))
            for pos, t in enumerate(rel["songs"]):
                add(t, "related", label, 0.8 * s["w"] / (1 + pos / 8))
            for a in rel["artists"]:
                related_artists[(a["id"], a["name"])] += s["w"]

    # Artist graph: YouTube's "similar artists" around the lane's core artists, kept only if new to the listener.
    with store.Pool(4) as ex:
        core_pages = list(ex.map(lambda a: ytm.artist(a["id"]), core[:12]))
    for page in core_pages:
        for a in page["related"][:8]:
            related_artists[(a["id"], a["name"])] += 0.5
    new_artists = [(aid, name) for (aid, name), w in related_artists.most_common(40)
                   if aid and known.is_new([{"id": aid, "name": name}])][:10]
    # Artists they follow on YouTube without having liked a song, where YouTube places them near this lane.
    followed = [(aid, name) for (aid, name), w in related_artists.most_common(120)
                if aid and not known.artist_familiarity([{"id": aid, "name": name}])
                and known.artist_known([{"id": aid, "name": name}]) == "follow"][:6]

    explore_artists = []
    if explore:
        for e in lane.get("explore_artists", [])[:12]:
            hit = resolve_artist(e["name"])
            if hit and known.is_new([hit]):
                explore_artists.append((hit["id"], hit["name"], e))
    with store.Pool(4) as ex:
        pages = list(ex.map(lambda x: (x, ytm.artist(x[0])),
                            new_artists + followed + [(i, n) for i, n, _ in explore_artists]))
    explore_by_id = {i: e for i, _, e in explore_artists}
    followed_ids = {i for i, _ in followed}
    for (aid, name), page in pages:
        if aid in followed_ids:
            for pos, t in enumerate(page["songs"][:3]):
                add(t, "follow", f"follow:{name}", 0.9 / (1 + pos))
        elif aid in explore_by_id:
            e = explore_by_id[aid]
            for pos, t in enumerate(page["songs"][:4]):
                bonus = 1.6 if fold(e["song"]) and fold(e["song"]) in fold(t["title"]) else 1.0
                add(t, "explore", f"editor:{e['why']}", 0.9 * bonus / (1 + pos))
        else:
            for pos, t in enumerate(page["songs"][:3]):
                add(t, "artist", f"similar:{name}", 0.7 / (1 + pos))

    # Playlists people made around this scene. A playlist that already holds several of the listener's own
    # likes is a person with overlapping taste; the rest of it is their recommendation.
    queries = [lane["english"]] + [" ".join(a["name"] for a in core[i:i + 2]) for i in (0, 2) if len(core) > i + 1]
    with store.Pool(4) as ex:
        found = [p for ps in ex.map(lambda q: ytm.playlists(q), queries) for p in ps[:5]]
    pids = list(dict.fromkeys(p["id"] for p in found))[:12]
    with store.Pool(4) as ex:
        lists = list(ex.map(ytm.playlist, pids))
    used = 0
    for pl in lists:
        ts = pl["tracks"]
        if len(ts) < 8:
            continue
        mine = sum(1 for x in ts if x["vid"] in known.vids or song_key(x["title"]) in known.songs)
        near = sum(1 for x in ts if known.artist_familiarity(x["artists"]))
        overlap = (mine + 0.3 * near) / math.sqrt(len(ts))
        if mine < 2 and overlap < 1.0:
            continue
        used += 1
        for t in ts:
            add(t, "playlist", f"playlist:{pl['title']}", min(1.2, 0.35 * overlap))

    # New releases (this year and last) from the lane's core artists: the Release Radar slot.
    this_year = dt.date.today().year
    fresh = []
    for page in core_pages:
        rel = [r for r in page["releases"] if r.get("id") and str(r.get("year") or "").isdigit()
               and int(r["year"]) >= this_year - 1]
        fresh += rel[:3]
    with store.Pool(4) as ex:
        albums = list(ex.map(lambda r: ytm.album(r["id"]), fresh[:24]))
    for alb in albums:
        n = 1 if len(alb["tracks"]) <= 2 else 3
        for t in alb["tracks"][:n]:
            add(t, "release", f"new:{alb['title']}", 1.0)

    for c in cands.values():
        c["sources"] = sorted(c["sources"])
        c["familiar"] = known.artist_familiarity(c["artists"])
        c["knows"] = None if c["familiar"] else known.artist_known(c["artists"])
    return {"cands": cands, "rejected": dict(rejected), "new_artists": [n for _, n in new_artists], "playlists": used}


def resolve_artist(name: str) -> dict | None:
    """Editor-named artists are often written 'Chinese name English name'; accept the top hit only when the
    names agree, so a wrong artist never enters the pool."""
    tokens = [fold(x) for x in re.split(r"[\s()（）/]+", name) if len(fold(x)) >= 2] + [fold(name)]
    for a in ytm.search(name, "artists", 3):
        f = fold(a["name"] or "")
        if f and any(t == f or (len(t) >= 3 and (t in f or f in t)) for t in tokens):
            return a
    return None


def core_artists(lane: dict, tracks: list[dict], profile: dict) -> list[dict]:
    """The lane's anchor artists as YouTube channel ids, taken from the likes themselves (recency-weighted),
    with the editor's named core artists first."""
    assign = profile.get("assign", {})
    nm = settings.not_me()
    weight, names = Counter(), {}
    for t in tracks:
        if t["long"] or lane["key"] not in assign.get(t["vid"], []) or settings.is_not_me(t, nm):
            continue
        w = 0.5 ** (_years_ago(t.get("liked_est")) / HALF_LIFE_YEARS)
        for a in t["artists"][:2]:
            if a.get("id"):
                weight[a["id"]] += w
                names[a["id"]] = a["name"]
    by_name = {fold(n): i for i, n in names.items()}
    editor = [by_name[fold(n)] for n in lane.get("core_artists", []) if fold(n) in by_name and fold(n) not in nm[1]]
    order = list(dict.fromkeys(editor[:6] + [i for i, _ in weight.most_common(12)]))
    return [{"id": i, "name": names[i]} for i in order]


def is_new(c: dict) -> bool:
    """An artist the listener has neither liked, followed nor played often: what the lane's discovery share counts."""
    return not c.get("familiar") and not c.get("knows")


def views_n(c: dict) -> float:
    views = c.get("views")
    if not isinstance(views, str):
        return 0.0
    m = re.match(r"([\d.]+)\s*([萬億KMB]?)", views.replace(",", ""))
    return float(m.group(1)) * {"萬": 1e4, "億": 1e8, "K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2), 1) if m else 0.0


def score(c: dict, lane: dict) -> float:
    s = math.log1p(c["support"] * 3) + 0.25 * min(len(c["via"]), 5)
    if "release" in c["sources"]:
        s += 0.5
    if "explore" in c["sources"]:
        s += 0.3
    s += 0.25 * math.log1p(c.get("familiar", 0))
    if c.get("knows"):
        s += 0.15
    if "follow" in c["sources"]:
        s += 0.3
    if (c.get("familiar") or c.get("knows")) and views_n(c) > 3e7:
        s -= 0.5  # a big hit by an artist they already follow: probably heard it
    if c.get("shown_before"):
        s -= 0.4
    year = c.get("year")
    this_year = dt.date.today().year
    if year and year >= this_year - 1:
        s += 0.5
    elif year and year >= this_year - 2:
        s += 0.2
    return s


def shortlist(lane: dict, cands: dict, k: int = 32, order: list[str] | None = None) -> list[dict]:
    """The best k for the editor, holding the lane's share of new artists and at most two songs an artist. Best by
    the graph score, or by `order` (vids, best first, as the screen returned them) when there is one."""
    # public playlists only corroborate: alone they bring popular songs from outside the lane's scene
    pool = [c for c in cands.values() if set(c["sources"]) - {"playlist"}]
    if order is not None:
        at = {v: i for i, v in enumerate(order)}
        ranked = sorted((c for c in pool if c["vid"] in at), key=lambda c: at[c["vid"]])
    else:
        ranked = sorted(pool, key=lambda c: -score(c, lane))
    out, per_artist = [], Counter()
    target_new = lane.get("discovery", 0.4)
    n_new = max(1, round(k * target_new))
    news = [c for c in ranked if is_new(c)]
    olds = [c for c in ranked if not is_new(c)]
    for pool, quota in ((news, n_new), (olds, k - n_new)):
        taken = 0
        for c in pool:
            a = fold(c["artists"][0]["name"])
            if per_artist[a] >= 2:
                continue
            per_artist[a] += 1
            out.append(c)
            taken += 1
            if taken >= quota:
                break
    if len(out) < k:
        for c in ranked:
            if c not in out:
                out.append(c)
            if len(out) >= k:
                break
    return out
