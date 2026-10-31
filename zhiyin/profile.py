import json
import time
import traceback

from . import i18n, library, llm, store

UNKNOWN_LISTENER = "Nothing is known about the listener beyond these likes; infer their languages and background from them."


def listener() -> str:
    from . import accounts
    tracks = library.load()
    dated = tracks and all(t.get("source") in ("google", "163") for t in tracks)
    when = ("'Liked around' is the date of the like." if dated else
            "'Liked around' is the estimated month of the like (a lower bound from upload dates).")
    return f"{accounts.prefs().get('about') or UNKNOWN_LISTENER} Lower ranks are more recent likes. {when}"


def _sys(template: str) -> str:
    w = i18n.WRITE[i18n.of()]
    return (template.replace("@LISTENER@", listener()).replace("@LANG@", w["lang"]).replace("@NAME@", w["name"])
            .replace("@HEADLINE@", w["headline"]).replace("@TITLES@", w["titles"]).replace("@CLAIM@", w["claim"])
            .replace("@EVIDENCE@", w["evidence"]).replace("@LABEL@", w["label"]))


TAG_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "i": {"type": "integer"},
            "kind": {"type": "string", "enum": ["song", "cover", "live", "remix", "instrumental", "novelty", "medley", "clip"]},
            "lang": {"type": "string", "enum": ["yue", "cmn", "ko", "ja", "en", "th", "vi", "es", "ru", "id", "instrumental", "mixed"]},
            "scene": {"type": "string"},
            "sound": {"type": "string"},
            "mood": {"type": "string"},
            "energy": {"type": "integer", "minimum": 1, "maximum": 5},
            "year": {"type": "integer"},
            "original": {"type": "string"},
            "known": {"type": "boolean"},
        },
        "required": ["i", "kind", "lang", "scene", "sound", "mood", "energy", "year", "original", "known"],
    }}},
    "required": ["items"],
}

TAG_SYSTEM = """You annotate one person's liked music so a recommender can understand their taste.
@LISTENER@
For every input line output one item with:
- kind: song (studio original), cover, live, remix, instrumental (beat/instrumental track), novelty (parody/comedy/meme), medley (multi-song live or compilation under 10 min), clip (dance practice, fancam, tutorial, short snippet).
- lang: sung language. yue = Cantonese, cmn = Mandarin. Decide Cantonese vs Mandarin from the artist and the song, not the script.
- scene: the specific scene or micro-genre a knowledgeable music editor would file it under, e.g. "Cantopop R&B", "Cantopop ballad", "K-R&B", "Korean underground hip-hop", "J-pop", "Japanese city pop revival", "anime opening rock", "4th-gen K-pop girl group", "Mandopop R&B", "Taiwanese indie", "neo-soul", "vocal jazz standard", "lofi jazzhop", "trap", "EDM/big room", "electro swing", "Western pop", "Thai pop".
- sound: 4-8 English words on the actual sound (instruments, groove, vocal, production), e.g. "Rhodes chords, swung pocket, airy falsetto".
- mood: 1-3 English words.
- energy: 1 (very calm) to 5 (very high).
- year: original release year of the recording, 0 if you really do not know.
- original: for covers/live/remix/medley, "Title - Original Artist"; otherwise "".
- known: true if you genuinely know this exact song; false if you are inferring from artist/title. Be honest; false is fine.
Never invent facts; when unsure, infer conservatively from the artist."""


def _line(t):
    arts = ", ".join(a["name"] for a in t["artists"])
    alb = f" [album: {t['album']['name']}]" if t.get("album") else ""
    return f"{t['rank']}\t{t['title']}\t{arts}{alb}\t{t['type']}\t{t['dur']}s"


def tag(force: bool = False, batch: int = 100, workers: int = 4) -> dict:
    tracks = [t for t in library.load() if not t["long"]]
    tags = {} if force else (store.read_json(store.TAGS) or {})
    todo = [t for t in tracks if t["vid"] not in tags]
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]

    def run(chunk):
        prompt = "Annotate every line (rank, title, artists, video type, duration):\n" + "\n".join(_line(t) for t in chunk)
        res = llm.call(prompt, _sys(TAG_SYSTEM), TAG_SCHEMA, model="sonnet")
        by_rank = {t["rank"]: t for t in chunk}
        return {by_rank[x["i"]]["vid"]: {k: v for k, v in x.items() if k != "i"}
                for x in res["items"] if x["i"] in by_rank}

    with store.Pool(workers) as ex:
        for out in ex.map(run, chunks):
            tags.update(out)
            store.write_json(store.TAGS, tags)
    missing = [t for t in todo if t["vid"] not in tags]
    if missing and not force:
        print(f"retrying {len(missing)} untagged")
        for out in map(run, [missing[i:i + batch] for i in range(0, len(missing), batch)]):
            tags.update(out)
        store.write_json(store.TAGS, tags)
    return tags


LANE_SCHEMA = {
    "type": "object",
    "properties": {
        "lanes": {"type": "array", "items": {"type": "object", "properties": {
            "key": {"type": "string"},
            "name": {"type": "string"},
            "english": {"type": "string"},
            "blurb": {"type": "string"},
            "when": {"type": "string"},
            "sound": {"type": "string"},
            "langs": {"type": "array", "items": {"type": "string"}},
            "energy": {"type": "array", "items": {"type": "integer"}},
            "seeds": {"type": "array", "items": {"type": "integer"}},
            "core_artists": {"type": "array", "items": {"type": "string"}},
            "explore_artists": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "why": {"type": "string"}, "song": {"type": "string"}},
                "required": ["name", "why", "song"]}},
            "avoid": {"type": "array", "items": {"type": "string"}},
            "discovery": {"type": "number"},
        }, "required": ["key", "name", "english", "blurb", "when", "sound", "langs", "energy", "seeds",
                        "core_artists", "explore_artists", "avoid", "discovery"]}},
        "focus": {"type": "object", "properties": {
            "blurb": {"type": "string"}, "when": {"type": "string"},
            "queries": {"type": "array", "items": {"type": "string"}},
            "avoid": {"type": "array", "items": {"type": "string"}}},
            "required": ["blurb", "when", "queries", "avoid"]},
        "set_aside": {"type": "array", "items": {"type": "object", "properties": {
            "what": {"type": "string"}, "ranks": {"type": "array", "items": {"type": "integer"}}, "why": {"type": "string"}},
            "required": ["what", "ranks", "why"]}},
    },
    "required": ["lanes", "focus", "set_aside"],
}

LANE_SYSTEM = """You are a world-class music editor, writing the taste model behind one person's private recommender.
@LISTENER@
You get every liked song with tags, newest first, plus a summary of the long focus mixes they save; when known, also
what they play most and the other lists they keep in a music app.

Think like a listener and an editor, not a statistician:
- Find the real listening modes ("lanes"): what they reach for and when. A lane is defined by sound and use,
  not by language alone. Cross-language lanes are welcome where the sound is shared (e.g. groove/R&B sung in
  several languages). Language-specific lanes are right where the language is the point.
- PLAYED, when given, is how often they actually play each song: weigh it with recency when ordering lanes and
  choosing seeds. A song played on many days without a like still speaks for their taste; only liked ranks can be seeds.
- LISTS THEY KEEP IN MUSIC APPS, when given: THEIR OTHER LISTS are the rest of the page their likes come from; LISTS
  ON ANOTHER PAGE OF THEIRS come from an app they use besides or an account they used before (the dates say which);
  EARLIER LISTS were kept before their likes here begin. Lists from before their likes are where their taste comes
  from. Their own lists are songs they chose one by one, sorted the way they think about music (the names are their own
  words); playlists by others and albums they keep are what they went looking for. Never seed from them, and give what
  they hold a lane only where the likes or plays carry it on.
- 6 to 8 lanes for songs, ordered by how central they are NOW (weight recent likes and repeat-liked songs far more
  than their oldest likes). Do not make a lane for long focus mixes; they are handled separately.
- Old likes that no longer reflect the person (meme songs, practice or cover clips, one-off party
  tracks, songs from a phase long past) go to set_aside with the reason (what and why in plain @LANG@), so they never seed recommendations.
- seeds: 10-16 ranks per lane that best define it today (prefer recent, repeat-liked, and archetypal songs).
- core_artists: the artists from their likes that anchor the lane.
- explore_artists: 12-15 REAL artists NOT in their likes who this person would plausibly love in this lane, with one
  real signature song each and a short why. Favour cross-language bridges and artists active 2018-2026 across
  Hong Kong, Taiwan, mainland China, Korea, Japan, Southeast Asia and the West. No artist that appears in the likes.
  Only name artists and songs you are confident exist. If a lane is defined by a language (e.g. Cantonese), every
  explore artist must sing in that language; cross-language bridges belong only in cross-language lanes.
- avoid: concrete things that would feel wrong in this lane (sounds, sub-genres, versions).
- discovery: target share (0-1) of recommendations from artists NOT already liked, for this lane.
- key: short ascii slug. name: @NAME@, evocative but plain (no slogans). english: 2-4 words.
- blurb: one plain @LANG@ sentence on the sound. when: one plain @LANG@ phrase on when they reach for it.
- focus: the long background mixes they save for work (e.g. lofi, jazz or ambient playlists). blurb and when in
  plain @LANG@; queries = 8-10 YouTube search queries (any language) that would find NEW long mixes in the same
  spirit; avoid = what would make a focus mix wrong for them."""


def _summary_lines(tracks, tags, known: bool = False):
    lines = []
    for t in tracks:
        g = tags.get(t["vid"])
        if not g:
            continue
        arts = ", ".join(a["name"] for a in t["artists"])
        liked = (t.get("liked_est") or "?")[:7]
        lines.append(f"{t['rank']}|{liked}|{t['title']}|{arts}|{g['kind']}|{g['lang']}|{g['scene']}|{g['sound']}|{g['mood']}|e{g['energy']}"
                     + (f"|{'known' if g.get('known') else 'guessed'}" if known else ""))
    return lines


PLAYED_LINES = 150


def _played(songs: list[dict]) -> str:
    """The songs they play most, from an imported YouTube Music history (Takeout), liked ones by rank."""
    from . import signals
    h = signals.history()
    if not h.get("songs"):
        return ""
    lang = i18n.of()
    rank = {t[k]: t["rank"] for t in songs for k in ("vid", "mv", "ll") if t.get(k)}
    top = sorted(h["songs"].items(), key=lambda kv: (-kv[1]["days"], -kv[1]["n"]))[:PLAYED_LINES]
    span = " to ".join(str(x)[:7] for x in h.get("span") or [])
    return (f"\n\nPLAYED ON YOUTUBE MUSIC ({span}, from their Google Takeout; rank if liked else -|days played|plays|"
            "last played|title|artists):\n"
            + "\n".join(f"{rank.get(v, '-')}|{s['days']}|{s['n']}|{(s.get('last') or '')[:7]}|"
                        f"{i18n.script(s['title'], lang)}|{i18n.script(s['artist'], lang)}" for v, s in top))


LIST_ARTISTS = 4


def _kept(a: dict) -> tuple[list[bool], set[int]]:
    """For each list in `a` (signals.archive), whether it is on the page the likes come from; and which are their own."""
    pages = a.get("pages")
    if pages is None:   # read before pages: one page, the likes' own when it is in the app they come from
        one = (store.read_json(store.LIBRARY) or {}).get("source") == a.get("key", "").split(":")[0]
        same = [one] * len(a.get("lists", []))
    else:
        same = [bool(pages[x.get("page", 0)].get("same")) for x in a.get("lists", [])]
    return same, {i for i, x in enumerate(a.get("lists", [])) if x.get("kind", "own") in ("own", "likes")}


APPS = {"qq": "QQ Music", "163": "NetEase Cloud Music"}


def _lists() -> str:
    from collections import Counter

    from . import signals
    a = signals.archive()
    if not a.get("songs"):
        return ""
    lang = i18n.of()
    same, own = _kept(a)
    pages = a.get("pages") or [{"key": a.get("key", "")}]

    def app(x):
        return APPS.get(pages[x.get("page", 0)]["key"].split(":")[0], "another app")
    tops = {}
    for s in a["songs"]:
        for i in s["lists"]:
            tops.setdefault(i, Counter())[s["artists"][0] if s["artists"] else "?"] += 1

    def row(i, x):
        return (f"{i}|{x.get('kind', 'own')}|{x['title']}|{x.get('by') or '-'}|{(x.get('at') or '-')[:7]}|{(x.get('changed') or '-')[:7]}|"
                f"{x['n']}|" + ", ".join(f"{i18n.script(n, lang)} {c}" for n, c in tops.get(i, Counter()).most_common(LIST_ARTISTS)))
    lists = list(enumerate(a["lists"]))
    here = [row(i, x) for i, x in lists if same[i]]
    there = [row(i, x) for i, x in lists if not same[i]]
    there_head = (f"EARLIER LISTS, kept in {app(lists[0][1])} before their likes here begin" if "pages" not in a else
                  "LISTS ON ANOTHER PAGE OF THEIRS, in " + " and ".join(dict.fromkeys(app(x) for i, x in lists if not same[i]))
                  + " (an app they use besides, or an account they used before: the dates say which)")
    # by artist, not song by song: a long archive listed in full crowded out the likes and the room to think
    by = {}
    for s in a["songs"]:
        if own & set(s["lists"]):
            by.setdefault(s["artists"][0] if s["artists"] else "?", []).append(s)
    rows, once = [], []
    for name, ss in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(ss) == 1:
            once.append(i18n.script(name, lang))
            continue
        ys = sorted(s["released"][:4] for s in ss if (s.get("released") or "")[:4].isdigit())
        years = (ys[0] if ys[0] == ys[-1] else f"{ys[0]}-{ys[-1]}") if ys else "?"
        titles = " / ".join(i18n.script(s["title"], lang) for s in sorted(ss, key=lambda s: -len(s["lists"]))[:3])
        rows.append(f"{i18n.script(name, lang)}|{len(ss)}|{years}|{','.join(map(str, sorted(own & {i for s in ss for i in s['lists']})))}|"
                    f"{titles}")
    return ("\n\nLISTS THEY KEEP IN MUSIC APPS (i|kind: likes, own, saved = a playlist someone else made, album = an album they "
            "keep|title|by|made or kept|last changed|songs|most frequent artists)"
            + (f"\n{('THEIR OTHER LISTS in ' + app(lists[[i for i, _ in lists if same[i]][0]][1]) + ', on the same page as the likes above')}:\n"
               + "\n".join(here) if here else "")
            + (f"\n{there_head}:\n" + "\n".join(there) if there else "")
            + (f"\n\nSONGS IN THEIR OWN LISTS by artist ({sum(len(v) for v in by.values())} songs; "
               "artist|songs|released|lists|a few titles):\n" + "\n".join(rows) if by else "")
            + (f"\nOne song each: {', '.join(once)}" if once else ""))


RUN = 25   # consecutive likes: one artist holding several of them is a run on that artist


def evidence(songs: list[dict], tags: dict) -> str:
    """What the portrait stands on, counted here so the model reads the numbers instead of counting them."""
    from collections import Counter, defaultdict
    from statistics import median

    from . import accounts, ear, signals
    from .text import fold, song_key
    songs = sorted(songs, key=lambda t: t["rank"])
    if len(songs) < 20:
        return ""
    lang = i18n.of()
    ts = dict(zip((t["rank"] for t in songs), ear._times(songs)))
    ne = (accounts.prefs().get("netease") or {}).get("link")
    released = bool(ne) and library.app_of(ne) == "qq"   # QQ Music shows no like dates: they are guessed from releases
    exact = all(t.get("source") in ("google", "163") for t in songs)

    def tg(t):
        return tags.get(t["vid"]) or {}

    def who(t):
        return t["artists"][0]["name"] if t["artists"] else ""

    def month(t):
        return ear._month(ts[t["rank"]])

    shown = {fold(who(t)): i18n.script(who(t), lang) for t in songs if who(t)}
    ranks = defaultdict(list)
    for t in songs:
        if who(t):
            ranks[fold(who(t))].append(t["rank"])
    by_rank = {t["rank"]: t for t in songs}
    out = []

    if not released:
        years = defaultdict(Counter)
        for t in songs:
            years[int(ts[t["rank"]])][tg(t).get("lang") or "?"] += 1
        out.append("LANGUAGE OF THE LIKES BY YEAR (year: likes, top languages): " + "; ".join(
            f"{y}: {sum(c.values())}, " + ", ".join(f"{k} {round(100 * n / sum(c.values()))}%" for k, n in c.most_common(3))
            for y, c in sorted(years.items())))

    best = {}
    for i in range(len(songs)):
        for k, n in Counter(fold(who(t)) for t in songs[i:i + RUN] if who(t)).items():
            if n > best.get(k, (0, 0))[0]:
                best[k] = (n, i)
    runs = sorted(((n, k, i) for k, (n, i) in best.items() if n >= 4), reverse=True)[:8]
    if runs:
        def run_at(k, i):
            if released:
                return ""
            return f", around {month(next(t for t in songs[i:i + RUN] if fold(who(t)) == k))}"
        out.append(f"RUNS (one artist holding many of {RUN} consecutive likes): " + "; ".join(
            f"{shown[k]} {n} of {RUN}{run_at(k, i)}, {len(ranks[k])} liked in all" for n, k, i in runs))

    if not released:
        back = []
        for k, rs in ranks.items():
            if len(rs) >= 3:
                g, a, b = max((ts[b] - ts[a], a, b) for a, b in zip(rs[::-1], rs[-2::-1]))
                if g >= 2 and a - b > 30:   # estimated dates can jump; many likes between can't
                    back.append((g, k, a, b))
        if back:
            out.append("RETURNS (an artist liked, then none for years, then liked again): " + "; ".join(
                f"{shown[k]}: around {month(by_rank[a])}, then none until {month(by_rank[b])}, {len(ranks[k])} in all"
                for _, k, a, b in sorted(back, reverse=True)[:8]))

    def song(t):
        """(title, artist) of the song itself: a cover or live take counts under the original it names."""
        o = tg(t).get("original") or ""
        if " - " in o and tg(t).get("kind") in ("cover", "live", "remix", "medley"):
            title, artist = o.rsplit(" - ", 1)
            return title, artist
        return t["title"], who(t)
    same = defaultdict(list)
    for t in songs:
        title, artist = song(t)
        same[(song_key(title), fold(artist))].append(t)
    twice = sorted((v for v in same.values() if len(v) >= 2), key=lambda v: (-len(v), ts[v[-1]["rank"]] - ts[v[0]["rank"]]))
    if twice:
        def kept(v):
            title, artist = song(v[-1])
            kinds = ", ".join(sorted({tg(t).get("kind") or "song" for t in v}))
            when = "" if released else f"; around {month(v[-1])} and {month(v[0])}"
            return f'"{title}", {i18n.script(artist, lang)} x{len(v)} ({kinds}{when})'
        out.append(f"THE SAME SONG KEPT MORE THAN ONCE: {len(twice)} songs. " + "; ".join(kept(v) for v in twice[:8]))

    kinds = Counter(tg(t).get("kind") or "song" for t in songs)
    out.append(f"VERSIONS, of {len(songs)} likes: " + ", ".join(f"{n} {k}" for k, n in kinds.most_common() if k != "song"))
    en = Counter(tg(t).get("energy") for t in songs)
    out.append("ENERGY (1 very calm to 5 very high): " + ", ".join(f"{e}: {en[e]}" for e in range(1, 6)))

    if not released:
        lag = [(max(0.0, ts[t["rank"]] - tg(t)["year"]), t) for t in songs if 1900 < (tg(t).get("year") or 0) <= ts[t["rank"]] + 1]
        if len(lag) >= 30:
            xs = [x for x, _ in lag]
            per = defaultdict(list)
            for x, t in lag:
                per[tg(t).get("lang")].append(x)
            out.append(
                f"HOW OLD A SONG IS WHEN THEY LIKE IT ({len(xs)} songs with a known year): median {median(xs):.1f} years; "
                f"{round(100 * sum(x < 1 for x in xs) / len(xs))}% within a year of release, "
                f"{round(100 * sum(x >= 10 for x in xs) / len(xs))}% at 10 years or more; median by language: "
                + ", ".join(f"{k} {median(v):.1f}" for k, v in per.items() if len(v) >= 15)
                + ("" if exact else ". Like dates are lower bounds here, so the true gaps are at least this long"))
            out.append("THE OLDEST SONGS THEY LIKED (released, liked around): " + "; ".join(
                f'"{t["title"]}", {shown.get(fold(who(t)), "?")} ({tg(t)["year"]}, {int(ts[t["rank"]])})'
                for _, t in sorted(lag, key=lambda p: -p[0])[:8]))

    h = signals.history()
    hs = h.get("songs") or {}
    if hs:
        span = " to ".join(str(x)[:7] for x in h.get("span") or [])
        mine = {t[k]: t["rank"] for t in songs for k in ("vid", "mv", "ll") if t.get(k)}
        art = defaultdict(lambda: [0, 0, 0])
        # a channel's name is often not the artist's name in the likes (Eason Chan, 陳奕迅): the liked songs it played link them
        same_as = defaultdict(set)
        for v, s in hs.items():
            k = fold(s["artist"])
            a = art[k]
            a[0] += s["n"]
            a[1] += 1
            if v in mine:
                a[2] += 1
                same_as[k].add(fold(who(by_rank[mine[v]])))
        called = {fold(s["artist"]): i18n.script(s["artist"], lang) for s in hs.values()}

        def liked(k):
            return sum(len(rs) for j, rs in ranks.items() if j == k or j in same_as[k])
        out.append(f"MOST PLAYED ARTISTS, {span} (artist: plays, songs played, of those liked, songs of theirs liked in "
                   "all): " + "; ".join(f"{called[k]}: {p}, {n}, {lk}, {liked(k)}"
                                       for k, (p, n, lk) in sorted(art.items(), key=lambda kv: -kv[1][0])[:12]))
        rep = [v for v, s in hs.items() if s["days"] >= 3]
        out.append(f"REPLAYED (played on 3 or more days, {span}): {len(rep)} songs, {sum(v in mine for v in rep)} of them liked")
        if not released:
            kept = {mine[v] for v, s in hs.items() if s["days"] >= 2 and v in mine}
            yrs = defaultdict(lambda: [0, 0])
            for t in songs:
                y = yrs[int(ts[t["rank"]])]
                y[0] += 1
                y[1] += t["rank"] in kept
            out.append(f"LIKES STILL PLAYED (songs liked each year that were played on 2 or more days, {span}): "
                       + ", ".join(f"{y} {p} of {n}" for y, (n, p) in sorted(yrs.items())))

    a = signals.archive()
    same, own = _kept(a)
    before = "pages" not in a and not any(same)   # kept before their likes here, as `zhiyin archive` once read it
    kept = [s for s in a.get("songs", []) if s["artists"] and own & set(s["lists"])]
    if kept:
        then = Counter(fold(s["artists"][0]) for s in kept)
        was = {fold(s["artists"][0]): i18n.script(s["artists"][0], lang) for s in kept}
        place = {k: i + 1 for i, k in enumerate(sorted(ranks, key=lambda k: -len(ranks[k])))}
        lists, where = ("the earlier lists", "liked here") if before else ("their own lists", "liked")
        out.append(f"{'THEN AND NOW' if before else 'LISTS AND LIKES'} (artist: songs in {lists}, songs {where}, place among "
                   f"the most {where}): " + "; ".join(f"{was[k]} {n}, {len(ranks.get(k, []))}" + (f", #{place[k]}" if k in place else "")
                                                     for k, n in then.most_common(15)))
        new = sorted(((len(rs), k) for k, rs in ranks.items() if k not in then), reverse=True)[:10]
        out.append(f"MOST {where.upper()} AND ABSENT FROM {lists.upper()}: " + ", ".join(f"{shown[k]} {n}" for n, k in new))
    return "\n".join(f"- {x}" for x in out)


READ_SCHEMA = {
    "type": "object",
    "properties": {
        "core": {"type": "string"},
        "loves": {"type": "array", "items": {"type": "object", "properties": {
            "quality": {"type": "string"}, "evidence": {"type": "string"}, "ranks": {"type": "array", "items": {"type": "integer"}}},
            "required": ["quality", "evidence", "ranks"]}},
        "loses": {"type": "array", "items": {"type": "object", "properties": {
            "quality": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["quality", "evidence"]}},
        "listener": {"type": "array", "items": {"type": "object", "properties": {
            "reading": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["reading", "evidence"]}},
        "tension": {"type": "object", "properties": {"reading": {"type": "string"}, "evidence": {"type": "string"}},
                    "required": ["reading", "evidence"]},
        "constant": {"type": "string"},
        "changes": {"type": "string"},
        "eras": {"type": "array", "items": {"type": "object", "properties": {
            "from_rank": {"type": "integer"}, "to_rank": {"type": "integer"},
            "years": {"type": "string"}, "label": {"type": "string"}, "text": {"type": "string"}},
            "required": ["from_rank", "to_rank", "years", "label", "text"]}},
    },
    "required": ["core", "loves", "loses", "listener", "tension", "constant", "changes", "eras"],
}

READ_SYSTEM = """You are the friend who knows this person's music best: a musician and critic who has watched them listen
for years. Work out what they love in music and what kind of listener they are, from their own data. Two people read
what you write: the writer of their page, who turns it into a few lines for them, and the editor who chooses new songs
for them each week. Both need the truth about this one person, as specific as the data allows.
@LISTENER@

You get every liked song with tags, newest first (songs that don't speak for them are already left out); SOUND, measured
from the recordings by code; what they did with the songs the app chose for them; EVIDENCE about how they listen,
counted by code (trust its numbers over your own counting); and, when known, what they played this past year, the long
focus mixes they save and the lists they keep in a music app. The tags were written by a model that knew only some of
the songs (known=false means it guessed from the artist), so for the songs at the centre of their listening, use what
you know about the recordings themselves.

Start from the music:
- Take the artists and songs at the centre (most liked, kept longest, played most, come back to, kept in their own
  lists) and ask what the recordings have in common, across languages and genres: the voice (register, how hard it
  pushes, how close it sounds), the harmony (plain pop chords, or the colour of jazz, soul and gospel), the rhythm
  (where the beat sits, how busy the drums are), the arrangement and production (sparse or full, played or programmed,
  which instrument carries the song), the writing (how a melody moves, how the hook lands, whether the singer writes
  and produces their own songs), and the words, where the data shows they matter.
- SOUND compares their songs with the other songs the app has heard, most of them found for listeners of the same
  kinds of music, so it shows what sets them apart within their own genres. Trust its direction and size; any one
  song's place in it is noisy.
- What they did in the app is the sharpest evidence there is: every song there was already chosen to fit their
  genres, so what they loved, heard through, skipped within seconds or turned down shows what a song must have and
  what loses them.
- A quality counts only if it would be false for most people who like the same genres and artists. "Smooth R&B
  vocals" is true of anyone with these likes. A finding such as "the songs they keep sit on jazz chords under a singer
  who never raises their voice, and the moment a track gets crowded or shouts, they are gone" is about them, if their
  data shows it.
- Find what stayed in the music while the languages, scenes and years changed.

Then the listener:
- How they live with music: how they find it, keep it, come back to it and use it; what they play but never like,
  what they collect, what they let go and what took its place. Say what each shows about them, tied to the music
  where you can.
- One real tension, where two things in their data pull against each other.
- Never guess what the data can't show: feelings, love life, mood, life events, the time of day, who with, their job,
  age, where they live or come from, or what language they speak (names are written in the script their music app
  shows, not theirs).

Write in plain English, for the writer and the editor, not for the listener:
- core: three or four sentences on what the music they love has in common, in concrete musical terms, and what has
  stayed through the changes.
- loves: 3 to 5 qualities a song needs to keep them, strongest first. quality: one sentence. evidence: the facts,
  numbers and songs that show it, with SOUND and app evidence where it applies. ranks: 2 to 4 of their liked songs
  that show it best, by rank, only songs whose recordings you know.
- loses: 1 to 3 things that lose them, with evidence: turned down or skipped in the app, missing from their likes where
  listeners of the same genres have plenty, sounds they lean away from.
- listener: 3 to 5 readings of how they live with music, each with its evidence.
- tension: one, with its evidence.
- constant: what in the music has stayed through their years of listening. changes: what changed, and what took the
  place of what.
- eras: 4 to 6 periods by rank range, newest first, with years from the "liked around" dates (never from release
  years) written like 2019–2021 or 2026, a short label and one sentence on what changed in the music they liked,
  naming at most two artists."""

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "sound": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"}, "detail": {"type": "string"}}, "required": ["claim", "detail"]}},
        "observations": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["claim", "evidence"]}},
        "eras": {"type": "array", "items": {"type": "object", "properties": {
            "i": {"type": "integer"}, "label": {"type": "string"}, "text": {"type": "string"}}, "required": ["i", "label", "text"]}},
        "drafts": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "post": {"type": "integer"}, "stranger": {"type": "integer"},
            "unsaid": {"type": "integer"}}, "required": ["text", "post", "stranger", "unsaid"]}},
        "headline": {"type": "string"},
        "names": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "post": {"type": "integer"}, "true": {"type": "integer"}},
            "required": ["text", "post", "true"]}},
        "name": {"type": "string"},
    },
    "required": ["sound", "observations", "eras", "drafts", "headline", "names", "name"],
}

WRITE_SYSTEM = """You write the part of one person's music page that reads them, from what the friend who knows their
music best worked out about them (READING, written for you in English, with the evidence). @LISTENER@
They open the page to see whether we understood them, and they may post it for their friends. The bar: they read it
and think "that's me, how did it know", and a friend who sees it learns something true about them and wants to agree
or argue. A statistic is not a reading, and neither is a habit stated as a habit: say what it shows about them.

What to write, in @LANG@ (keep song titles and artist names exactly as given; @TITLES@):
- sound: 3 or 4 items on the music they love, strongest first, then one on what loses them. claim: one plain sentence
  of @CLAIM@, a friend telling them something about their own ears, with no numbers. detail: one or two sentences of
  @EVIDENCE@ that make it concrete for someone who doesn't play music, naming two or three of their own songs that show
  it, inside the sentence (from the songs given; they can play them right there). For what loses them, name the kinds
  of song they turn down, and only songs they turned down or skipped, never one they heard through. Choose what is most them: a quality that would be false for most listeners of the same
  genres beats one that is true of all of them; a quality together with the place where it stops holding (one
  language, one kind of song) is worth more than another quality of the same sound; what the artists they stay with
  have in common as musicians (who writes, produces or plays their own songs) counts as much as the sound.
- observations: 3 or 4 items on how they live with music, among them the tension. Nothing here says again what the
  sound items or the headline say. claim: @CLAIM@, no numbers: what the habit shows about them, never the habit
  itself, which belongs in the evidence. evidence: @EVIDENCE@ with the facts that show it, at most two numbers and
  three names, counted the way a person counts (years, months, songs, plays; never ranks). Give the facts and stop.
- eras: one for each period given: i (its number), label (a few words, never its years, which the page shows beside
  it) and text (one sentence) in @LANG@.
- drafts, then headline: the one line under the name of their taste, on their page and on the card they may post. Say
  what the reading adds up to about them, one sentence of @HEADLINE@, preferring what they may not have noticed about
  themselves. A stranger who sees only the card must get it in one read: everyday words, one idea, no numbers or
  years, at most one name. First write five drafts, each from a different angle, and score each from 1 to 5: post (how
  much they would want it on their card), stranger (how well someone who doesn't know them gets it in one read) and
  unsaid (how much it says what they hadn't put into words; a fact they plainly know about themselves scores 1). The
  headline is the best of them, tightened, and never a line already on the page.
- names, then name: what a friend would call their ears, or the kind of listener they are, in @LABEL@. It heads their
  page and the card, above the headline, and says something the headline doesn't. A name, never a sentence, an
  instruction or a list of artists; plain words, a little wry is good, never flattering, no big words (soul, universe,
  collector, connoisseur, 灵魂, 宇宙, 收藏家, 品味, 氛围感). Five drafts, each scored from 1 to 5 for post (would they
  put it on their card) and true (how much of the reading it holds), then the best one.

How it sounds:
- A friend talking to them ("you"): everyday words, short sentences, dry humour or warmth where the data earns it.
  Never flattering, never praising their taste, never the voice of a report or a review. Every claim is a statement
  about them, never an instruction or a rule.
- Concrete words for sound are welcome, the ones a friend who plays would use and anyone can follow: voice, falsetto,
  chords, piano, electric piano, drums, bass, horns, synths, beat, chorus, arrangement, sung softly, shouted (假声,
  和弦, 钢琴, 电钢琴, 鼓, 贝斯, 铜管, 合成器, 节拍, 副歌, 编曲, 唱得很轻, 喊). Explain a term the first time if
  someone who doesn't play wouldn't know it. Vague adjectives say nothing: never smooth, chill, dreamy, warm, soulful,
  vibe, texture, 丝滑, 治愈, 温暖, 温柔, 氛围, 质感, 慵懒, 松弛, 梦幻, 高级.
- Say a thing once: a fact or a song used in one item is not used again in another. No hedging (seems, perhaps, in a way, 似乎, 或许, 某种程度上), no line explaining the line before it.
- Whatever you say about a song you name must be true of that recording; when unsure of one, name another. A song
  named beside an artist is that artist's.
- The app is never the subject. What they did with its songs is evidence about their ears, nothing more: no line about
  how they use the app, how much they trust it or how its picks went.
- Never: slogans, or two mirrored clauses that sound like one (对仗); "not X but Y" (不是…而是, 与其说…不如说); "from X
  to Y" (从…到…); telling them what they think or assume (你以为, 你可能觉得, you think, you'd guess); rhetorical
  questions; colons or dashes; exclamation marks; metaphors or similes; more than three names in a row; the words
  soul, journey, story, eclectic, through-line, 灵魂, 旅程, 故事, 诉说, 仿佛, 底色, 交织, 贯穿, 一脉相承, 骨子里,
  不仅…更.
- In Chinese, write the way a person talks in writing: numbers in Arabic digits, full-width punctuation, no 「」 around
  ideas, no four-character set phrases strung together.

The gap between a report and a reading, from other listeners (theirs, not yours; never reuse their wording):
- Report: "你喜欢的歌里 R&B 最多。" Reading: "你要的 R&B 是唱给一个人听的那种，一开始喊你就切走了。"
- Report: "Many of your likes feature acoustic guitar." Reading: "Play the guitar by hand and you have their attention;
  program it and you've lost them."
- Report: "你收了 4 个版本的《Fly Me to the Moon》。" Reading: "一首歌你喜欢了，就要听遍每个人唱它。"
- Report: "Only 9 of your 160 likes are above medium energy." Reading: "Nothing you like is in a hurry."
- Habit: "You replay a handful of songs for weeks." Reading: "When a song gets you, you wear it out before you let
  anything else in."
- Habit: "你喜欢的歌，大多是发行十年以后才点的。" Reading: "你要等一首歌被时间筛过一遍，才肯认真听它。\""""

APP_LINES = 40


def _app() -> str:
    """What they did with the songs the app chose for them: loved, heard through, skipped within seconds, turned down."""
    from . import quality
    con, uid = store.db(), store.uid()
    names = {r["vid"]: (r["title"], r["artist"]) for r in con.execute(
        "select vid, title, artist from plays where uid=? and title is not null", (uid,))}
    fb = {r["vid"]: r for r in con.execute("select vid, action, title, artist from feedback where uid=? order by ts", (uid,))}
    for v, r in fb.items():
        if r["title"]:
            names.setdefault(v, (r["title"], r["artist"]))
    first = {x["vid"]: x["out"] for x in quality.first_listens(0, uid)}
    lang = i18n.of()
    rows = {"LOVED (added to their likes)": [v for v, r in fb.items() if r["action"] == "like"],
            "TURNED DOWN (said it's not for them)": [v for v, r in fb.items() if r["action"] == "dislike"],
            "SKIPPED WITHIN SECONDS": [v for v, o in first.items() if o == "early" and v not in fb],
            "HEARD THROUGH": [v for v, o in first.items() if o == "good" and v not in fb]}
    out = [f"{k} ({len(vs)}): " + "; ".join(f'"{i18n.script(names[v][0], lang)}"'
                                             + (f", {i18n.script(names[v][1], lang)}" if names[v][1] else "")
                                             for v in vs[-APP_LINES:][::-1] if v in names)
           for k, vs in rows.items() if vs]
    return ("\n\nWHAT THEY DID WITH SONGS THE APP CHOSE FOR THEM, newest first:\n" + "\n".join(out)) if out else ""


def _sound(songs: list[dict]) -> str:
    """The SOUND words their songs lean towards and away from, against everything else the app has heard."""
    from . import audio
    got = audio.sound([t["vid"] for t in songs])
    if not got:
        return ""
    by_vid = {t["vid"]: t for t in songs}
    return ("\n\nSOUND, measured from 30-second previews of their songs against the other songs the app has heard "
            "(d: difference in standard deviations; 0.2 small, 0.5 medium):\n"
            + "\n".join(f"{x['d']:+.2f} {x['word']}" + (": strongest in " + "; ".join(
                f"{by_vid[v]['rank']} \"{by_vid[v]['title']}\"" for v in x["songs"][:5] if v in by_vid) if x["songs"] else "")
                for x in got))


PORTRAIT_MIXES = 30


def read(prof: dict, model: str = "opus", tracks: list[dict] | None = None, own: bool = True) -> dict:
    """What a perceptive friend would work out about the listener's ears, in English, for their page (the screen read
    it worse than without, eval-screen's taste arm, so the stations don't). `tracks` narrows the likes it reads (an eval window's older likes), and without
    `own` it reads the likes alone: nothing from the app, their plays or their lists, which may postdate them."""
    from . import settings
    nm = settings.not_me()
    tags = store.read_json(store.TAGS) or {}
    aside = {r for s in prof.get("set_aside", []) for r in s["ranks"]}
    tracks = library.load() if tracks is None else tracks
    songs = [t for t in tracks if not t["long"] and not settings.is_not_me(t, nm) and t["rank"] not in aside]
    mixes = [t for t in tracks if t["long"]]
    lanes = "\n".join(f"- {ln['name']}: {ln['blurb']}" for ln in prof.get("lanes", []))
    ev = evidence(songs, tags)
    prompt = (
        "LIKED SONGS (rank|liked around|title|artists|kind|lang|scene|sound|mood|energy|known):\n"
        + "\n".join(_summary_lines(songs, tags, known=True))
        + _sound(songs) + (_app() if own else "")
        + (f"\n\nEVIDENCE, counted from the same data (trust these numbers over your own counting):\n{ev}" if ev else "")
        + (f"\n\nLONG FOCUS MIXES SAVED: {len(mixes)} (some titles): "
           + " / ".join(m["title"][:60] for m in mixes[:PORTRAIT_MIXES]) if mixes else "")
        + (_played(songs) + _lists() if own else "")
        + (f"\n\nTHEIR STATIONS:\n{lanes}" if lanes else ""))
    return llm.call(prompt, READ_SYSTEM.replace("@LISTENER@", listener()), READ_SCHEMA, model=model, timeout=900)


def write(rd: dict, songs: list[dict], model: str = "opus") -> dict:
    """The page's reading of the listener, in their language, from read()."""
    from .ytm import plain_title
    by_rank = {t["rank"]: t for t in songs}

    def named(ranks):
        return "; ".join(f"\"{plain_title(by_rank[r]['title'])}\", {', '.join(a['name'] for a in by_rank[r]['artists'][:2])}"
                         for r in ranks if r in by_rank)
    prompt = ("READING:\nCore: " + rd["core"]
              + "\n\nWhat a song needs to keep them:\n" + "\n".join(
                  f"- {x['quality']} Evidence: {x['evidence']} Their songs that show it: {named(x['ranks'])}" for x in rd["loves"])
              + "\n\nWhat loses them:\n" + "\n".join(f"- {x['quality']} Evidence: {x['evidence']}" for x in rd["loses"])
              + "\n\nHow they live with music:\n" + "\n".join(f"- {x['reading']} Evidence: {x['evidence']}" for x in rd["listener"])
              + f"\n\nTension: {rd['tension']['reading']} Evidence: {rd['tension']['evidence']}"
              + f"\n\nWhat has stayed: {rd['constant']}\nWhat changed: {rd['changes']}"
              + "\n\nPERIODS, newest first:\n" + "\n".join(f"{i}. {e['years']}: {e['label']}. {e['text']}"
                                                         for i, e in enumerate(rd["eras"])))
    out = llm.call(prompt, _sys(WRITE_SYSTEM), WRITE_SCHEMA, model=model, timeout=600)
    # each period is written beside its own ranks, matched by number: one run wrote them oldest first
    if {w["i"] for w in out["eras"]} != set(range(len(rd["eras"]))):
        out = llm.call(prompt + f"\n\n(Write all {len(rd['eras'])} periods, each with its number.)", _sys(WRITE_SYSTEM),
                       WRITE_SCHEMA, model=model, timeout=600)
    wrote = {w["i"]: w for w in out["eras"]}
    eras = [{**e, "label": _no_years(wrote[i]["label"], e["years"]), "text": wrote[i]["text"]}
            for i, e in enumerate(rd["eras"]) if i in wrote]
    lang, name = i18n.of(), out["name"].strip().rstrip("。.!！")
    return {"headline": out["headline"].strip(), "sound": out["sound"], "observations": out["observations"], "eras": eras,
            "name": _in_script(name, lang) if _fits(name, lang) else "", "lang": lang}


def portrait(prof: dict, model: str = "opus") -> tuple[dict, dict]:
    """The page's reading of the listener and, in English, what it stands on (prof["taste"]). Written apart from the
    stations so it gets the model's whole attention."""
    from . import settings
    nm = settings.not_me()
    aside = {r for s in prof.get("set_aside", []) for r in s["ranks"]}
    songs = [t for t in library.load() if not t["long"] and not settings.is_not_me(t, nm) and t["rank"] not in aside]
    rd = read(prof, model)
    return write(rd, songs, model), rd


def synthesize(model: str = "opus") -> dict:
    from . import settings
    nm = settings.not_me()
    tracks = library.load()
    tags = store.read_json(store.TAGS) or {}
    songs = [t for t in tracks if not t["long"] and not settings.is_not_me(t, nm)]
    mixes = [t for t in tracks if t["long"]]
    repeats = {}
    from .text import song_key
    for t in songs:
        repeats.setdefault(song_key(t["title"]), []).append(t["rank"])
    rep = [f"{v[0]}x{len(v)}" for v in repeats.values() if len(v) > 1]
    prompt = (
        "LIKED SONGS (rank|liked around|title|artists|kind|lang|scene|sound|mood|energy):\n"
        + "\n".join(_summary_lines(songs, tags))
        + "\n\nREPEAT-LIKED (rank of newest x times liked): " + ", ".join(rep)
        + f"\n\nLONG FOCUS MIXES SAVED: {len(mixes)} (titles): "
        + " / ".join(m["title"][:60] for m in mixes[:60])
        + _played(songs) + _lists()
    )
    res = llm.call(prompt, _sys(LANE_SYSTEM), LANE_SCHEMA, model=model, timeout=1200)
    res["built"] = time.time()
    res["model"] = model
    res["lang"] = i18n.of()
    return res


ASSIGN_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "i": {"type": "integer"}, "lane": {"type": "string"}, "also": {"type": "string"}},
        "required": ["i", "lane", "also"]}}},
    "required": ["items"],
}


def assign(profile: dict, batch: int = 150, workers: int = 4, only: set | None = None) -> dict:
    tracks = [t for t in library.load() if not t["long"]]
    tags = store.read_json(store.TAGS) or {}
    aside = {r for s in profile.get("set_aside", []) for r in s["ranks"]}
    lanes_desc = "\n".join(f"- {l['key']}: {l['english']} — {l['sound']} (langs {','.join(l['langs'])}; energy {l['energy']})"
                           for l in profile["lanes"])
    keys = [l["key"] for l in profile["lanes"]] + ["none"]
    schema = json.loads(json.dumps(ASSIGN_SCHEMA))
    schema["properties"]["items"]["items"]["properties"]["lane"]["enum"] = keys
    schema["properties"]["items"]["items"]["properties"]["also"]["enum"] = keys
    system = ("Assign each liked song to the single best-fitting listening lane, and optionally a second lane in 'also' "
              "('none' if no second lane fits). Use 'none' as the main lane only if the song fits no lane at all. Lanes:\n" + lanes_desc)
    todo = [t for t in tracks if t["rank"] not in aside and (only is None or t["vid"] in only)]
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]

    def run(chunk):
        prompt = "rank|liked around|title|artists|kind|lang|scene|sound|mood|energy\n" + "\n".join(_summary_lines(chunk, tags))
        res = llm.call(prompt, system, schema, model="sonnet")
        return {x["i"]: [x["lane"]] + ([x["also"]] if x["also"] not in ("none", x["lane"]) else []) for x in res["items"]}

    out = {}
    with store.Pool(workers) as ex:
        for r in ex.map(run, chunks):
            out.update(r)
    by_rank = {t["rank"]: t["vid"] for t in tracks}
    return {by_rank[r]: v for r, v in out.items() if r in by_rank}


def build(model: str = "opus", log=print) -> dict:
    i18n.repin()
    llm.require()
    log(i18n.tr("给每首喜欢的歌标上听感和场景"))
    tag()
    log(i18n.tr("找出你的几种听歌状态"))
    prof = synthesize(model)
    log(i18n.tr("把每首歌放进对应的电台"))
    with store.Pool(1) as ex:
        po = ex.submit(portrait, prof, model)
        prof["assign"] = assign(prof)
        prof["portrait"], prof["taste"] = po.result()
    _rename(prof)
    prev = store.read_json(store.PROFILE)
    if prev:
        stamp = time.strftime("%Y%m%d-%H%M", time.localtime(prev.get("built", time.time())))
        store.write_json(store.PROFILES / f"{stamp}.json", prev)
    store.write_json(store.PROFILE, prof)
    return prof


LABEL_SCHEMA = {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]}
LABEL_SYSTEM = """You name one person's taste in music, from the songs they liked on @SERVICE@ (@ROWS@).
Write one label of @LABEL@ in @LANG@: a name for their taste or for the kind of listener they are, the way a sharp
friend would put it. It is the first line on their own page and on the card they may post, so they should read it
and think "that's me", and their friends should want to argue with it.
- Name what is most them: a sound, a scene, a city, an era, a language, one artist they keep coming back to. When a
  reading of their ears comes first, name what it found (the sound they need, the kind of listener they are), not
  who they play.
- A name, not a summary: not a list of genres and not a "from X to Y" story.
- Plain words; a little wry is good. No flattery and no big words (soul, universe, journey, collector, connoisseur,
  eclectic, vibes, 灵魂, 宇宙, 收藏家, 品味, 氛围感). No emoji, hashtags or final punctuation.
- Only what the list shows. Never guess when, where or with whom they listen: no times of day or seasons (night,
  midnight, morning, 深夜, 夜晚, 清晨), no moods they might be in.
- Keep artist names exactly as given.
Shapes other listeners got (theirs, not yours; don't reuse the wording): "Mostly Fujii Kaze, and everyone near him",
"A jazz piano person who won't admit it", "老派港乐，新派韩流", "粤语慢歌，偶尔被 K-R&B 拐走"."""
LABEL_LINES = 600
# what a row starts with: QQ Music shows nobody when a song was liked, so its rows give the year the song came out
ROWS = {True: "newest first, with the month of each like",
        False: "in the order @SERVICE@ lists them, likely newest first, with the year each song came out; @SERVICE@ "
               "doesn't show when a song was liked"}


def label(rd: dict | None = None) -> str:
    """A short name for the listener's taste: from the likes alone at first (the matched library, or the liked videos
    as YouTube lists them while that runs), as it is the first thing a new listener reads; from the reading of their
    ears (`rd`, else the profile's) once there is one."""
    from . import accounts, settings
    tracks = [t for t in library.load() if not t["long"]]
    ne = (accounts.prefs().get("netease") or {}).get("link")
    qq = bool(ne) and library.app_of(ne) == "qq"

    def when(t: dict, liked: str | None) -> str:
        return (t.get("released") or "")[:4] if qq else (liked or "")[:7]
    if tracks:
        rows = [(when(t, t.get("liked_est")), t["title"], ", ".join(a["name"] for a in t["artists"][:2])) for t in tracks]
    else:
        rows = [(when(x, x["at"]), x["title"], x["artist"]) for x in (store.read_json(store.GLIMPSE) or {}).get("songs", [])]
    nm = settings.not_me()
    rows = [r for r, t in zip(rows, tracks or [None] * len(rows)) if not (t and settings.is_not_me(t, nm))]
    service = ("QQ Music" if qq else "NetEase Cloud Music") if ne else "YouTube"
    rd = rd or (store.read_json(store.PROFILE) or {}).get("taste")
    gist = (rd["core"] + " What a song needs to keep them: " + " ".join(x["quality"] for x in rd["loves"])
            + " What loses them: " + " ".join(x["quality"] for x in rd["loses"])) if rd else ""
    return name_taste(rows, i18n.of(), service=service, dated=not qq, reading=gist)


def _rename(prof: dict) -> None:
    """A new reading names their taste again (the first name came from the likes alone)."""
    try:
        name = prof["portrait"].pop("name", None) or label(prof["taste"])
    except Exception:   # noqa: BLE001 - the name they have stays
        traceback.print_exc()
        return
    if name:
        store.write_json(store.IDENT, {"label": name, "lang": i18n.of(), "built": store.now()})


def sample(rows: list, lines: int) -> list:
    """The newest in full, then an even sample of the years before."""
    if len(rows) <= lines:
        return rows
    head = lines * 2 // 3
    old = rows[head:]
    return rows[:head] + old[::max(1, len(old) // (lines - head))][:lines - head]


def name_taste(rows: list[tuple[str, str, str]], lang: str, lines: int = LABEL_LINES, model: str = "sonnet",
               service: str = "YouTube", dated: bool = True, reading: str = "") -> str:
    """The label from (month liked, title, artists) rows, newest first (`dated` False: the year each came out), and
    what a reading of their ears found, when there is one."""
    if not rows:
        return ""
    rows = sample(rows, lines)
    w = i18n.WRITE[lang]
    system = LABEL_SYSTEM.replace("@ROWS@", ROWS[dated]).replace("@LABEL@", w["label"]).replace("@LANG@", w["lang"]) \
        .replace("@SERVICE@", service)
    prompt = (f"READING OF THEIR EARS: {reading}\n\nTHEIR LIKES:\n" if reading else "") + "\n".join(" | ".join(r) for r in rows)
    for _ in range(2):
        out = llm.call(prompt, system, LABEL_SCHEMA, model=model, timeout=180, retries=1)["label"].strip().rstrip("。.!！")
        if _fits(out, lang):
            break
        prompt += f"\n\n(\"{out}\" is too long: {w['label']}.)"
    return _in_script(out, lang)


def _no_years(label: str, years: str) -> str:
    """The page shows the years beside the label; one run wrote them into it too."""
    return label[len(years):].lstrip(" ·:：-–") if label.startswith(years) and label != years else label


def _fits(name: str, lang: str) -> bool:
    return len(name.split()) <= 7 if lang == "en" else len(name) <= 18


def _in_script(name: str, lang: str) -> str:
    if lang == "en":
        return name
    # the script of the likes can leak into the label (粵語 for a Simplified reader)
    return i18n.zh_punct(i18n.convert(name, "zh-Hant" if lang == "zh-Hans" else "zh-Hans", lang))


def rewrite_portrait(model: str = "opus") -> dict:
    """A new reading of the listener on the stations they have, as when an imported history or earlier lists add to
    what is known about them."""
    llm.require()
    prof = store.read_json(store.PROFILE)
    if not prof:
        raise ValueError("no profile: build it")
    # in the language they read now, said natively: the portrait keeps its own `lang` inside the profile
    prof["portrait"], prof["taste"] = portrait(prof, model)
    _rename(prof)
    store.write_json(store.PROFILE, prof)
    return prof["portrait"]


def absorb_new(log=print) -> int:
    """Likes added since the profile was built: tag them and file them under the existing lanes."""
    prof = store.read_json(store.PROFILE)
    if not prof:
        return 0
    todo = {t["vid"] for t in library.load() if not t["long"] and t["vid"] not in prof.get("assign", {})}
    if not todo:
        return 0
    log(i18n.tr("把 {n} 首新喜欢放进电台", n=len(todo)))
    tag()
    got = assign(prof, only=todo)
    prof["assign"].update({v: got.get(v, ["none"]) for v in todo})
    store.write_json(store.PROFILE, prof)
    return len(todo)
