import json
import time

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
            .replace("@HEADLINE@", w["headline"]).replace("@TITLES@", w["titles"]))


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
        "portrait": {"type": "object", "properties": {
            "headline": {"type": "string"},
            "paragraphs": {"type": "array", "items": {"type": "string"}},
            "eras": {"type": "array", "items": {"type": "object", "properties": {
                "from_rank": {"type": "integer"}, "to_rank": {"type": "integer"},
                "years": {"type": "string"}, "label": {"type": "string"}, "text": {"type": "string"}},
                "required": ["from_rank", "to_rank", "years", "label", "text"]}},
            "threads": {"type": "array", "items": {"type": "string"}},
        }, "required": ["headline", "paragraphs", "eras", "threads"]},
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
    "required": ["portrait", "lanes", "focus", "set_aside"],
}

LANE_SYSTEM = """You are a world-class music editor, writing the taste model behind one person's private recommender.
@LISTENER@
You get every liked song with tags, newest first, plus a summary of the long focus mixes they save.

Think like a listener and an editor, not a statistician:
- Find the real listening modes ("lanes"): what they reach for and when. A lane is defined by sound and use,
  not by language alone. Cross-language lanes are welcome where the sound is shared (e.g. groove/R&B sung in
  several languages). Language-specific lanes are right where the language is the point.
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
  spirit; avoid = what would make a focus mix wrong for them.
- portrait (@LANG@, keeping song titles and artist names exactly as given (@TITLES@); warm and specific, no flattery, no clichés, no bullet-y
  slogans): headline = ONE sentence of @HEADLINE@ that names the through-line of their taste; 3-4 short paragraphs that
  read their taste with concrete artists/songs as evidence; eras = 4-6 periods by rank range, with years taken from the "liked around" dates (never guessed from
  release years),
  a short label and one sentence each; threads = 3-5 things that stay constant across languages and years."""


def _summary_lines(tracks, tags):
    lines = []
    for t in tracks:
        g = tags.get(t["vid"])
        if not g:
            continue
        arts = ", ".join(a["name"] for a in t["artists"])
        liked = (t.get("liked_est") or "?")[:7]
        lines.append(f"{t['rank']}|{liked}|{t['title']}|{arts}|{g['kind']}|{g['lang']}|{g['scene']}|{g['sound']}|{g['mood']}|e{g['energy']}")
    return lines


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
    llm.require()
    log(i18n.tr("给每首喜欢的歌标上听感和场景"))
    tag()
    log(i18n.tr("找出你的几种听歌状态"))
    prof = synthesize(model)
    log(i18n.tr("把每首歌放进对应的电台"))
    prof["assign"] = assign(prof)
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
- Name what is most them: a sound, a scene, a city, an era, a language, one artist they keep coming back to.
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


def label() -> str:
    """A short name for the listener's taste, from the likes alone (the matched library, or the liked videos as
    YouTube lists them while that runs). Quick: it is the first thing a new listener reads."""
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
    return name_taste(rows, i18n.of(), service=service, dated=not qq)


def sample(rows: list, lines: int) -> list:
    """The newest in full, then an even sample of the years before."""
    if len(rows) <= lines:
        return rows
    head = lines * 2 // 3
    old = rows[head:]
    return rows[:head] + old[::max(1, len(old) // (lines - head))][:lines - head]


def name_taste(rows: list[tuple[str, str, str]], lang: str, lines: int = LABEL_LINES, model: str = "sonnet",
               service: str = "YouTube", dated: bool = True) -> str:
    """The label from (month liked, title, artists) rows, newest first (`dated` False: the year each came out)."""
    if not rows:
        return ""
    rows = sample(rows, lines)
    w = i18n.WRITE[lang]
    system = LABEL_SYSTEM.replace("@ROWS@", ROWS[dated]).replace("@LABEL@", w["label"]).replace("@LANG@", w["lang"]) \
        .replace("@SERVICE@", service)
    prompt = "\n".join(" | ".join(r) for r in rows)
    for _ in range(2):
        out = llm.call(prompt, system, LABEL_SCHEMA, model=model, timeout=180, retries=1)["label"].strip().rstrip("。.!！")
        if len(out.split()) <= 7 if lang == "en" else len(out) <= 18:
            break
        prompt += f"\n\n(\"{out}\" is too long: {w['label']}.)"
    if lang == "en":
        return out
    # the script of the likes can leak into the label (粵語 for a Simplified reader)
    return i18n.zh_punct(i18n.convert(out, "zh-Hant" if lang == "zh-Hans" else "zh-Hans", lang))


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
