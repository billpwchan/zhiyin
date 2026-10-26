import random
import re

from . import candidates, i18n, llm
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


def pick(lane: dict, shortlist: list[dict], seeds: list[dict], negatives: list[str], model: str = "opus") -> list[dict]:
    order = list(range(len(shortlist)))
    random.shuffle(order)  # LLM rankers favour early items; shuffle so code-score order doesn't leak in
    lines = [_fmt(i, shortlist[i]) for i in order]
    seed_lines = [f"{i}. {s['title']} — {', '.join(a['name'] for a in s['artists'])}" for i, s in enumerate(seeds[:10])]
    prompt = (
        f"LANE: {lane['name']} ({lane['english']})\nSound: {lane['sound']}\nWhen: {lane['when']}\n"
        f"Languages: {', '.join(lane['langs'])} | energy {lane['energy']}\nAvoid: {'; '.join(lane['avoid'])}\n"
        f"Target share of new artists: {lane['discovery']:.0%}\n\n"
        "THEIR SONGS THAT DEFINE THIS LANE NOW:\n" + "\n".join(seed_lines)
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
