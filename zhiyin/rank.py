import random

from . import llm
from .text import fold

PICK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "integer"},
        "fit": {"type": "number"},
        "reason": {"type": "string"},
    }, "required": ["id", "fit", "reason"]}}},
    "required": ["picks"],
}

SYSTEM = """You are the listener's music editor. Choose from a shortlist of real tracks for one listening lane.
Write reasons in natural Simplified Chinese (keep song titles and artist names
exactly as given), plain and specific, at most 34 characters, no exclamation marks, no clichés, no "你一定会喜欢".

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
- reason: one natural sentence a friend with great taste would say. Lead with what the song does (its sound, mood,
  or why it suits this lane right now), then at most a short nod to what led here ("和你常听的〈玻璃〉一路"). Do not
  list several seed titles, do not count their likes, and never call anyone "新歌手"; an artist not in their likes
  is simply "你还没收藏过的". Describe the sound only for artists or songs you actually know; otherwise rely on the
  facts given. Never state facts you are unsure of (dates, awards, collaborations, charts). Vary the phrasing
  across picks.
- fit: 0-1, your honest confidence this listener will want this in this lane right now. Be strict: 0.9 only for
  songs you are sure of, 0.7 for good bets; below 0.6 means do not return it.
Return at most 12 picks ordered best first; return fewer rather than pad the list."""

MIN_FIT = 0.7


def system() -> str:
    return SYSTEM


def _fmt(i, c):
    arts = ", ".join(a["name"] for a in c["artists"])
    fam = f"artist already loved ({c['familiar']} likes)" if c["familiar"] else "artist new to them"
    via = []
    for v in c["via"][:3]:
        if v.startswith("editor:"):
            via.append("editor suggestion: " + v[7:])
        elif v.startswith("similar:"):
            via.append("YouTube lists the artist as similar to " + v[8:])
        elif v.startswith("new:"):
            via.append("new release " + v[4:])
        else:
            via.append("from their like " + v)
    alb = f" | album {c['album']['name']}" if c.get("album") else ""
    yr = f" | {c['year']}" if c.get("year") else ""
    return f"[{i}] {c['title']} — {arts}{alb}{yr} | {fam} | " + "; ".join(via)


def pick(lane: dict, shortlist: list[dict], seeds: list[dict], negatives: list[str], model: str = "opus") -> list[dict]:
    order = list(range(len(shortlist)))
    random.shuffle(order)  # LLM rankers favour early items; shuffle so code-score order doesn't leak in
    lines = [_fmt(i, shortlist[i]) for i in order]
    seed_lines = [f"{s['title']} — {', '.join(a['name'] for a in s['artists'])}" for s in seeds[:10]]
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
    for p in res["picks"]:
        if not (0 <= p["id"] < len(shortlist)):
            continue
        c = shortlist[p["id"]]
        a = fold(c["artists"][0]["name"])
        if a in seen_artists:
            continue
        seen_artists.add(a)
        out.append({**c, "fit": p["fit"], "reason": p["reason"]})
    return out


def enforce_quota(picks: list[dict], n: int, discovery: float) -> list[dict]:
    """The editor ranks; code holds the familiar/new balance the listener set for the lane."""
    want_new = round(n * discovery)
    new = [p for p in picks if not p["familiar"]]
    old = [p for p in picks if p["familiar"]]
    take_new = new[:want_new]
    take_old = old[:n - len(take_new)]
    if len(take_new) + len(take_old) < n:
        rest = [p for p in picks if p not in take_new and p not in take_old]
        take_new += rest[:n - len(take_new) - len(take_old)]
    chosen = set(id(p) for p in take_new + take_old)
    return [p for p in picks if id(p) in chosen][:n]
