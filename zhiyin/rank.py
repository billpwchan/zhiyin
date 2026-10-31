import random
import re
import time

from . import candidates, i18n, llm, quality, settings, store
from .text import fold, song_key

PICK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "integer"},
        "fit": {"type": "number"},
        "reason": {"type": "string"},
        "like": {"type": "integer"},
    }, "required": ["id", "fit", "reason", "like"]}}},
    "required": ["picks"],
}

SYSTEM = """You are the listener's music editor. Choose from a shortlist of real tracks for one listening lane.
Write reasons in natural @LANG@ (keep song titles and artist names
exactly as given; @TITLES@), plain and specific, @REASON@, no exclamation marks, no clichés, no "@CLICHE@".

What a pick is for: a song this listener would add to their likes on the first listen. Fewer picks that are surely
right beat more picks that might be. Quality and texture come first: songs that are genuinely good, with real
songwriting and a voice and production of real texture, in the original studio recording.

Rules:
- Only choose ids from the shortlist. Never invent tracks.
- Judge fit to THIS lane: its scene, language and lineage as much as its sound and use. A lane is a kind of music,
  not just a mood; a mellow Mandopop ballad does not belong in a jazz lane however soft it sounds. Reject tracks that
  break the lane (wrong language for a language lane, wrong energy, a sound listed under avoid).
- Reject karaoke, lyric, sped-up, slowed, cover, fan-cam, live and remix uploads, and generic filler, unless the
  lane is explicitly about them.
- A well-known or older song is welcome when it fits and is not already in their likes: having been popular is not
  a flaw, and being new or obscure is never a reason on its own. Prefer songs surfaced by several of their likes;
  include fresh releases and new artists when they are as good as the rest.
- Their whole list for this lane (newest first) and how our earlier picks for it went are given when known: favour
  the qualities of what they kept and heard through, stay away from what they skipped within seconds or refused, and
  weigh their recent likes above old ones unless an old song is plainly the lane's core.
- Do not pick two songs by the same artist.
- reason: one natural sentence on what the song itself does: its sound, its mood, why it suits this lane right now.
  Say nothing about the listener: no titles of their songs, no counts, nothing about whether an artist is in their
  likes. The page shows those facts itself, from their data, next to your sentence. Describe the sound only for
  artists or songs you actually know; otherwise rely on the facts given. Never state facts you are unsure of
  (dates, awards, collaborations, charts, influences). Vary the phrasing across picks.
- like: the number of the one song in THEIR SONGS this pick is closest to, if one is genuinely close in sound and
  spirit; -1 otherwise. The page offers it to the listener to hear side by side, so pick it honestly.
- fit: 0-1, your honest confidence this listener will want this in this lane right now. Be strict: 0.9 only for
  songs you are sure of, 0.7 for good bets; below 0.6 means do not return it.
Return at most 12 picks ordered best first; return fewer rather than pad the list."""

MIN_FIT = 0.7


def system() -> str:
    w = i18n.WRITE[i18n.of()]
    return (SYSTEM.replace("@LANG@", w["lang"]).replace("@TITLES@", w["titles"]).replace("@REASON@", w["reason"])
            .replace("@CLICHE@", w["cliche"]))


def _fmt(i, c):
    arts = ", ".join(a["name"] for a in c["artists"])
    fam = (f"artist already loved ({c['familiar']} likes)" if c["familiar"]
           else "artist they follow on YouTube (no liked songs yet)" if c.get("knows") == "follow"
           else "artist they play often without having liked a song" if c.get("knows") == "plays"
           else "artist new to them")
    via = []
    for v in c["via"][:3]:
        if v.startswith("editor:"):
            via.append("editor suggestion: " + v[7:])
        elif v.startswith("similar:"):
            via.append("YouTube lists the artist as similar to " + v[8:])
        elif v.startswith("new:"):
            via.append("new release " + v[4:])
        elif v.startswith("follow:"):
            via.append("by an artist they follow, whom YouTube lists near their likes")
        else:
            via.append("from their like " + v)
    alb = f" | album {c['album']['name']}" if c.get("album") else ""
    yr = f" | {c['year']}" if c.get("year") else ""
    return f"[{i}] {c['title']} — {arts}{alb}{yr} | {fam} | " + "; ".join(via)


def pick(lane: dict, shortlist: list[dict], seeds: list[dict], negatives: list[str], model: str = "opus",
         story: list[str] = (), went: list[str] = ()) -> list[dict]:
    order = list(range(len(shortlist)))
    random.shuffle(order)  # LLM rankers favour early items; shuffle so code-score order doesn't leak in
    lines = [_fmt(i, shortlist[i]) for i in order]
    seed_lines = [f"{i}. {s['title']} — {', '.join(a['name'] for a in s['artists'])}" for i, s in enumerate(seeds[:10])]
    prompt = (
        f"LANE: {lane['name']} ({lane['english']})\nSound: {lane['sound']}\nWhen: {lane['when']}\n"
        f"Languages: {', '.join(lane['langs'])} | energy {lane['energy']}\nAvoid: {'; '.join(lane['avoid'])}\n"
        f"Target share of new artists: {lane['discovery']:.0%}\n"
        + (f"THEIR OWN WORDS ABOUT THIS LANE (follow them): {lane['note']}\n" if lane.get("note") else "") + "\n"
        "THEIR SONGS THAT DEFINE THIS LANE NOW:\n" + "\n".join(seed_lines)
        + ("\n\nALL THEIR SONGS IN THIS LANE, newest first:\n" + "\n".join(story) if story else "")
        + ("\n\nHOW OUR EARLIER PICKS FOR THIS LANE WENT, newest first:\n" + "\n".join(went) if went else "")
        + ("\n\nRECENTLY REJECTED BY THEM (avoid similar):\n" + "\n".join(negatives[:15]) if negatives else "")
        + "\n\nSHORTLIST:\n" + "\n".join(lines)
    )
    res = llm.call(prompt, system(), PICK_SCHEMA, model=model, timeout=600)
    out, seen_artists = [], set()
    their_keys = {song_key(s["title"]) for s in seeds}
    for p in res["picks"]:
        if not (0 <= p["id"] < len(shortlist)):
            continue
        c = shortlist[p["id"]]
        a = fold(c["artists"][0]["name"])
        if a in seen_artists:
            continue
        seen_artists.add(a)
        like = seeds[p["like"]] if 0 <= p.get("like", -1) < min(10, len(seeds)) else None
        out.append({**c, "fit": min(1.0, max(0.0, float(p["fit"]))), "reason": clean_reason(p["reason"], c, their_keys),
                    "like_vid": like["vid"] if like else None})
    return out


# --- What the screen and the editor are told about the listener, and the screen itself ---

STORY_N = 150   # a lane's own songs given to the screen and the editor (when the screen runs; otherwise fewer)


def lane_story(lane: dict, tracks: list[dict], profile: dict, loves=(), n: int = STORY_N, here: bool = True) -> list[str]:
    """Their songs in this lane, newest first: likes made here (unless `here` is off, as for a look back from before
    them), then their library with the month each was liked, then songs they play often without a like. Ten sampled
    seeds were all the editor used to see of a lane."""
    assign = profile.get("assign", {})
    aside = {r for s in profile.get("set_aside", []) for r in s["ranks"]}
    nm = settings.not_me()
    out = [f"- {r['title']} — {r['artist']} (liked here, {time.strftime('%Y-%m', time.localtime(r['ts']))})" for r in store.db().execute(
        "select title, artist, ts from feedback where uid=? and action='like' and lane=? and title is not null order by ts desc",
        (store.uid(), lane["key"])) if here]
    mine = sorted((t for t in tracks if not t["long"] and t["rank"] not in aside and not settings.is_not_me(t, nm)
                   and lane["key"] in assign.get(t["vid"], [])), key=lambda t: t["rank"])
    out += [f"- {t['title']} — {', '.join(a['name'] for a in t['artists'][:2])}"
            + (f" (liked {t['liked_est'][:7]})" if t.get("liked_est") else "") for t in mine]
    out += [f"- {r['title']} — {', '.join(a['name'] for a in r['artists'][:2])} (played often, never liked)"
            for r in loves if lane["key"] in (r.get("lane") or [])[:1] and not settings.is_not_me(r, nm)]
    return out[:n]


# the reason the page sends with "only not in this station" (app.js nope), in each language it is written in
WRONG_LANE = {"只是不该在这个电台", "只是不該在這個電台", "Just not in this station"}


def outcomes(lane_key: str, n: int = 30) -> list[str]:
    """How the songs picked for this lane went, newest first. Only verdicts: a listen left for something else says
    nothing about the song."""
    con, uid = store.db(), store.uid()
    names = {r["vid"]: (r["title"], r["artist"]) for r in con.execute(
        "select vid, title, artist from plays where uid=? and title is not null", (uid,))}
    fb = {}
    for r in con.execute("select vid, action, reason, lane, title, artist, ts from feedback where uid=? order by ts", (uid,)):
        fb[r["vid"]] = r
        if r["title"]:
            names.setdefault(r["vid"], (r["title"], r["artist"]))
    rows = {}
    for x in quality.first_listens(0, uid):
        if x["lane"] == lane_key:
            rows[x["vid"]] = (x["ts"], x["out"])
    for v, r in fb.items():   # turned down or loved from the list, without a full listen
        if r["lane"] == lane_key and r["action"] in ("like", "dislike") and v not in rows:
            rows[v] = (r["ts"], None)
    out = []
    for v, (ts, how) in sorted(rows.items(), key=lambda kv: -kv[1][0]):
        f, name = fb.get(v), names.get(v)
        if not name:
            continue
        if f and f["action"] == "like":
            what = "loved it (added to likes)"
        elif f and f["action"] == "dislike" and f["reason"] in WRONG_LANE:
            what = "said it's fine but doesn't belong in this lane"
        elif f and f["action"] == "dislike":
            what = "said it's not for them" + (f": {f['reason']}" if f["reason"] else "")
        elif how == "good":
            what = "heard it through"
        elif how == "early":
            what = "skipped it within seconds"
        else:
            continue
        out.append(f"- {name[0]} — {name[1]}: {what}")
    return out[:n]


SCREEN_SYSTEM = """You are screening candidate songs for one listener and one of their listening lanes. From a long list
of real tracks, keep the @K@ this listener is most likely to add to their likes on the first listen in this lane.
Judge like a friend who knows their library well: scene, language and lineage, the specific qualities of the songs they
keep (voice, production, era, songwriting), what they kept and skipped of our earlier picks, and what they never keep.
A well-known song is fine if it fits and they don't have it; obscurity is not a merit. Skip karaoke, covers, live,
sped-up, remixes and filler. Return exactly @K@ ids from the list, best first."""
IDS_SCHEMA = {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "integer"}}}, "required": ["ids"]}
SCREEN_K = 64      # what the screen keeps for listening and the shortlist
SCREEN_PASSES = 1  # three shuffled reads merged kept no more held-out likes than one (evaluate.screen_report)
SCREEN_CAP = 700   # the most of a lane's pool one read takes, best by the graph score


def _screen_line(i: int, c: dict) -> str:
    fam = (f"artist in their likes ×{c['familiar']}" if c.get("familiar") else "artist they follow" if c.get("knows") == "follow"
           else "artist they play without a like" if c.get("knows") == "plays" else "new artist")
    via = "; ".join(v.split(":", 1)[-1] if v.startswith(("similar:", "new:", "follow:")) else v
                    for v in c["via"][:2] if not v.startswith(("playlist:", "editor:")))
    alb = f" | {c['album']['name']}" if c.get("album") else ""
    yr = f" | {c['year']}" if c.get("year") else ""
    return f"[{i}] {c['title']} — {', '.join(a['name'] for a in c['artists'])}{alb}{yr} | {fam}" + (f" | via {via}" if via else "")


def screen_pool(lane: dict, cands: dict) -> list[dict]:
    """What one read takes: the lane's pool best by the graph score, songs found only in playlists left out."""
    return sorted((c for c in cands.values() if set(c["sources"]) - {"playlist"}),
                  key=lambda c: -candidates.score(c, lane))[:SCREEN_CAP]


def taste_lines(rd: dict | None) -> str:
    """What a reading of all their likes found their ears need (profile.read), for the screen."""
    if not rd:
        return ""
    return ("\n\nWHAT THEIR EARS NEED, from a reading of all their likes:\n" + rd["core"]
            + "\nA song must have: " + " ".join(x["quality"] for x in rd["loves"])
            + "\nWhat loses them: " + " ".join(x["quality"] for x in rd["loses"]))


def screen_head(lane: dict, story: list[str], went: list[str]) -> str:
    return (f"LANE: {lane['name']} ({lane['english']})\nSound: {lane['sound']}\nWhen: {lane['when']}\n"
            f"Languages: {', '.join(lane['langs'])} | energy {lane['energy']}\nAvoid: {'; '.join(lane['avoid'])}\n"
            + (f"THEIR OWN WORDS ABOUT THIS LANE (follow them): {lane['note']}\n" if lane.get("note") else "")
            + "\nTHEIR SONGS IN THIS LANE, newest first:\n" + "\n".join(story)
            + ("\n\nHOW OUR EARLIER PICKS FOR THIS LANE WENT, newest first:\n" + "\n".join(went) if went else ""))


def screen_system() -> str:
    return SCREEN_SYSTEM.replace("@K@", str(SCREEN_K))


def screen_prompt(head: str, pool: list[dict], key: str, seed: int) -> str:
    order = list(range(len(pool)))
    random.Random(f"{key}|{seed}").shuffle(order)
    return head + f"\n\nCANDIDATES ({len(pool)}):\n" + "\n".join(_screen_line(i, pool[i]) for i in order)


def screen_ids(out: dict, pool: list[dict]) -> list[str]:
    ids = [i for i in out.get("ids", []) if isinstance(i, int) and 0 <= i < len(pool)]
    return [pool[i]["vid"] for i in dict.fromkeys(ids)][:SCREEN_K]


def merge_reads(reads: list[list[str]]) -> list[str]:
    votes = {}
    for r in reads:
        for i, v in enumerate(r):
            votes[v] = votes.get(v, 0) + 1 / (10 + i)
    return sorted(votes, key=lambda v: -votes[v])[:SCREEN_K]


def with_graph(graph: list[str], read: list[str]) -> list[str]:
    """The graph's order and the read's, taken in turn. Each keeps songs the other misses: alone they kept 45 and 46 of
    124 held-out likes, in turn 57."""
    out = {}
    for i in range(max(len(graph), len(read))):
        for v in (graph[i] if i < len(graph) else None, read[i] if i < len(read) else None):
            if v:
                out.setdefault(v)
        if len(out) >= SCREEN_K:
            break
    return list(out)[:SCREEN_K]


def screen(lane: dict, cands: dict, story: list[str], went: list[str], model: str = "opus") -> list[str] | None:
    """The whole pool read the way the editor reads a shortlist, taken in turn with the graph score's order, SCREEN_K
    in all. None when the pool is small or every read failed: the graph order stands."""
    pool = screen_pool(lane, cands)
    if len(pool) <= SCREEN_K:
        return None
    head = screen_head(lane, story, went)

    def read(seed: int) -> list[str]:
        try:
            # high effort for everyone: the effort the eval measured it at
            out = llm.call(screen_prompt(head, pool, lane["key"], seed), screen_system(), IDS_SCHEMA, model=model,
                           timeout=900, retries=1, effort="high")
        except llm.LLMError:
            return []
        return screen_ids(out, pool)

    with store.Pool(SCREEN_PASSES) as ex:
        reads = [r for r in ex.map(read, range(SCREEN_PASSES)) if r]
    return with_graph([c["vid"] for c in pool], merge_reads(reads)) if reads else None


_QUOTED = re.compile(r"[《〈“\"]([^》〉”\"]{1,80})[》〉”\"]")
_SENTENCE = re.compile(r"[^。！？.!?]+[。！？.!?]?\s*")
# Whether they have an artist is said by the page, from their data; the same claim in the reason repeats it.
_ABOUT_THEM = re.compile(r"(没|沒|没有|沒有|从没|從沒|未曾?)(收藏|点过喜欢|點過喜歡|听过|聽過)|你的收藏|"
                         r"new to (you|them)|(you|they) (haven['’]t|have not|never) (liked|saved|heard)|"
                         r"(your|their) likes|in (your|their) library", re.I)


def about_them(reason: str) -> str:
    """Drops the sentences on whether they know or have liked the artist, if another sentence is left."""
    keep = [x for x in _SENTENCE.findall(reason) if not _ABOUT_THEM.search(x)]
    return "".join(keep).strip() or reason


def clean_reason(reason: str, pick: dict, their_keys: set[str]) -> str:
    """The editor is told to leave the listener out of its sentence. When it still names one of their songs
    (`their_keys`: song_key of each of their titles), that sentence goes, if another is left; what the page says
    about them comes from their data, never from the model. Whole sentences only: cutting a clause out of one
    ("a gentle, unhurried ballad as “X”") leaves a broken one."""
    mine = their_keys - {song_key(pick["title"])}
    keep = [x for x in _SENTENCE.findall(reason) if not any(song_key(m) in mine for m in _QUOTED.findall(x))]
    return about_them("".join(keep).strip() or reason)


def enforce_quota(picks: list[dict], n: int, discovery: float) -> list[dict]:
    """The editor ranks; code holds the familiar/new balance the listener set for the lane."""
    want_new = round(n * discovery)
    new = [p for p in picks if candidates.is_new(p)]
    old = [p for p in picks if not candidates.is_new(p)]
    take_new = new[:want_new]
    take_old = old[:n - len(take_new)]
    if len(take_new) + len(take_old) < n:
        rest = [p for p in picks if p not in take_new and p not in take_old]
        take_new += rest[:n - len(take_new) - len(take_old)]
    chosen = set(id(p) for p in take_new + take_old)
    return [p for p in picks if id(p) in chosen][:n]
