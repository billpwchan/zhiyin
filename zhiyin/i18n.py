"""The listener's language: what the server says to them, what Claude writes for them, and turning text that was
already written in one Chinese script into the other. Messages are written in Simplified Chinese where they are used
and looked up here, the same way web/i18n.js does it for the page."""
import contextvars
import functools
import json
import os
import re

import opencc

from . import accounts, store

LANGS = ("zh-Hans", "zh-Hant", "en")
COOKIE = "zhiyin_lang"
_s2t = opencc.OpenCC("s2twp")
_t2s = opencc.OpenCC("tw2sp")
# Song titles keep the script they were written in, whatever the listener reads.
_TITLE = re.compile(r"(《[^》]*》|〈[^〉]*〉)")

# How Claude is told to write, per language.
WRITE = {
    "zh-Hans": {"lang": "Simplified Chinese", "name": "2-4 Simplified Chinese characters",
                "headline": "at most 30 Chinese characters", "reason": "at most 34 characters",
                "intent": "one short Simplified Chinese phrase (no more than 16 characters)",
                "titles": "Put song titles inside 《》.", "cliche": "你一定会喜欢",
                "label": "at most 12 Chinese characters (a Latin name counts as one character)"},
    "zh-Hant": {"lang": "Traditional Chinese as written in Taiwan and Hong Kong (never a Simplified character)",
                "name": "2-4 Traditional Chinese characters", "headline": "at most 30 Chinese characters",
                "reason": "at most 34 characters",
                "intent": "one short Traditional Chinese phrase (no more than 16 characters)",
                "titles": "Put song titles inside 《》.", "cliche": "你一定會喜歡",
                "label": "at most 12 Chinese characters (a Latin name counts as one character)"},
    "en": {"lang": "English", "name": "1-3 English words", "headline": "at most 18 words",
           "reason": "at most 16 words", "intent": "one short English phrase (no more than 6 words)",
           "titles": "Put song titles inside curly quotes “ ”.", "cliche": "you'll love this",
           "label": "at most 6 words (count them)"},
}


def norm(tag: str | None) -> str | None:
    """A browser or Accept-Language tag as one of LANGS."""
    t = (tag or "").strip().lower().replace("_", "-")
    if t in ("zh-hans", "zh-hant", "en"):
        return {"zh-hans": "zh-Hans", "zh-hant": "zh-Hant", "en": "en"}[t]
    if t.startswith("zh"):
        return "zh-Hant" if re.match(r"zh-(hant|tw|hk|mo)", t) else "zh-Hans"
    if t.startswith("en"):
        return "en"
    return None


def from_request(request) -> str:
    """For pages shown before anyone signs in: the choice made in this browser, else what the browser asks for."""
    picked = norm(request.cookies.get(COOKIE))
    if picked:
        return picked
    for part in (request.headers.get("accept-language") or "").split(","):
        got = norm(part.split(";")[0])
        if got:
            return got
    return "en"


def system() -> str:
    """For a command run before anyone opened the app: ZHIYIN_LANG, else the machine's locale (zh_TW.UTF-8 and so on)."""
    for v in (os.environ.get("ZHIYIN_LANG"), os.environ.get("LC_ALL"), os.environ.get("LANG")):
        got = norm((v or "").split(".")[0])
        if got:
            return got
    return "en"


# A visitor trying the sample listener has no account to keep a language in: their browser's choice for this request.
reader: contextvars.ContextVar[str | None] = contextvars.ContextVar("zhiyin_reader", default=None)


def of(uid: str | None = None) -> str:
    """The listener's language: their choice, set from their browser the first time they open the app."""
    if store.is_sample(uid) or (uid or store.uid()) == store.CARDS:
        return reader.get() or "en"
    return (accounts.prefs(uid or store.uid()) or {}).get("lang") or system()


def migrate() -> None:
    """Accounts from before there was a choice keep the language their stations were written in (Simplified Chinese
    when the profile predates the field, or when setup had begun); a fresh install starts from the browser."""
    if store.kv_get("lang-migrated"):
        return
    for u in accounts.users():
        if not u or u["prefs"].get("lang"):
            continue
        d = store.USERS / u["id"]
        prof = store.read_json(d / "profile.json")
        if prof or (d / "library.json").exists() or u["status"] not in ("new", "ready"):
            accounts.set_prefs(u["id"], lang=(prof or {}).get("lang", "zh-Hans"))
    store.kv_set("lang-migrated", True)


def write(key: str, uid: str | None = None) -> str:
    return WRITE[of(uid)][key]


def convert(text, src: str, dst: str):
    """Text written in one Chinese script, for a reader of the other; English and same-script text pass through."""
    if not isinstance(text, str) or not text or src == dst or "en" in (src, dst):
        return text
    if dst == "zh-Hant":   # 台 is the everyday Taiwan and Hong Kong form (台北, 電台); the converter writes 臺
        return "".join(p if _TITLE.fullmatch(p) else _s2t.convert(p).replace("臺", "台") for p in _TITLE.split(text))
    return "".join(p if _TITLE.fullmatch(p) else _t2s.convert(p) for p in _TITLE.split(text))


_TEXT_KEYS = {"headline", "paragraphs", "threads", "label", "text", "name", "blurb", "when", "what", "why", "reason",
              "intent", "sub", "lead", "years"}
# names, and the listener's own words, stay as they are
_NAMES = {"artists", "album", "title", "seeds", "core_artists", "explore_artists", "q", "avoid", "queries", "english"}


def _slots(obj, out: list, key: str | None = None) -> list:
    """Every piece of written text in a profile, edition or request history, as (container, key) pairs."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _NAMES:
                continue
            if isinstance(v, str):
                if k in _TEXT_KEYS and v.strip():
                    out.append((obj, k))
            else:
                _slots(v, out, k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                if key in _TEXT_KEYS and v.strip():
                    out.append((obj, i))
            else:
                _slots(v, out, key)
    return out


def convert_tree(obj, src: str, dst: str):
    if src == dst or "en" in (src, dst) or obj is None:
        return obj
    obj = json.loads(json.dumps(obj))
    for c, k in _slots(obj, []):
        c[k] = convert(c[k], src, dst)
    return obj


def family(lang: str | None) -> str:
    return "en" if lang == "en" else "zh"


# ---------- what a response says, as one reader sees it ----------
# A name changes script only when it is written in the other one (Taiwan's character forms for a Traditional reader):
# 終於了解自由 and 朴載範 stay as written for a Traditional reader, where s2tw would make 了解 瞭解 and 朴 樸.
_NAME_T2S = opencc.OpenCC("t2s")
_NAME_S2T = opencc.OpenCC("s2tw")
_JP2T = opencc.OpenCC("jp2t")
_HAN = re.compile(r"[㐀-鿿]")
_KANA = re.compile(r"[぀-ゟ゠-ヺー-ヿㇰ-ㇿ]")   # not ・, which Chinese also writes inside foreign names
_GAP = re.compile(r"(?<=[㐀-鿿])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[㐀-鿿])")


def _in(c: str, charset: str) -> bool:
    try:
        c.encode(charset)
        return True
    except UnicodeEncodeError:
        return False


@functools.lru_cache(maxsize=1 << 16)
def _kind(c: str) -> str:
    """"s" for a character only Simplified writes (in GB2312, not Big5), "t" only Traditional, "j" a Shinjitai neither
    writes (変 戦 黒 気: an older form exists and neither set has it; the older form alone would also catch 秘 祕, 予 豫,
    為 爲), "" either."""
    gb, b5 = _in(c, "gb2312"), _in(c, "big5")
    if gb != b5:
        return "s" if gb else "t"
    return "j" if c == "渕" or (not gb and _JP2T.convert(c) != c) else ""


def _kinds(text: str) -> set[str]:
    return {_kind(c) for c in _HAN.findall(text)}


@functools.lru_cache(maxsize=1 << 15)
def japanese(text: str) -> bool:
    """Kana; or a kanji only Japanese writes; or characters of both Chinese scripts at once (残響散歌: a Simplified 残
    beside a Traditional 響)."""
    k = _kinds(text)
    return bool(_KANA.search(text)) or "j" in k or {"s", "t"} <= k


@functools.lru_cache(maxsize=1 << 15)
def _scripted(text: str, lang: str) -> str:
    if japanese(text):
        return text
    if lang == "zh-Hans":
        return _NAME_T2S.convert(text) if "t" in _kinds(text) else text
    return _NAME_S2T.convert(text).replace("臺", "台") if "s" in _kinds(text) else text


def script(text, lang: str):
    """A name or a lyric line in the reader's Chinese script; Japanese as written."""
    return text if lang == "en" or not isinstance(text, str) else _scripted(text, lang)


def typeset(text, lang: str):
    """Text written for a Chinese reader: the songs it quotes in their script, and a space where Chinese meets Latin
    letters or digits, as the interface writes it (Claude often leaves none: 2014年, Gareth.T常驻)."""
    if lang == "en" or not isinstance(text, str) or not text:
        return text
    return "".join(p[0] + script(p[1:-1], lang) + p[-1] if _TITLE.fullmatch(p) else _GAP.sub(" ", p)
                   for p in _TITLE.split(text))


def song(title, artists: list, album, lang: str):
    """One song's title, artist names and album name as this reader sees them, and as written when that differs (the
    lyric sites are asked with the names as written). A song with anything Japanese about it stays as written."""
    from .ytm import plain_title
    shown = plain_title(title) if isinstance(title, str) else title
    texts = [x for x in (title, album, *artists) if isinstance(x, str)]
    if lang == "en" or any(japanese(x) for x in texts):
        return shown, artists, album, None
    out = (script(shown, lang), [script(a, lang) for a in artists], script(album, lang))
    if (out[0], out[1], out[2]) == (shown, artists, album):
        return *out, None
    return *out, {"t": title or "", "a": "|".join(a for a in artists if isinstance(a, str)), "al": album or ""}


def _line(x, lang: str):
    from .ytm import plain_title
    return script(plain_title(x), lang) if isinstance(x, str) and lang != "en" and not japanese(x) else for_reader(x, lang)


def for_reader(obj, lang: str):
    """Songs and text in a response as this reader sees them, changed in place: titles, artists and albums with the
    feat. written out and in their Chinese script (`o` keeps them as written); written text typeset for them. The
    listener's own words stay as they typed them."""
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            obj[i] = for_reader(v, lang)
        return obj
    if not isinstance(obj, dict):
        return obj
    if isinstance(obj.get("title"), str) and ("vid" in obj or "artists" in obj or "artist" in obj):
        arts = obj.get("artists") if isinstance(obj.get("artists"), list) else []
        names = [a.get("name") if isinstance(a, dict) else a for a in arts] or ([obj["artist"]] if isinstance(obj.get("artist"), str) else [])
        al = obj.get("album")
        title, names2, al_name, o = song(obj["title"], names, al.get("name") if isinstance(al, dict) else al, lang)
        obj["title"] = title
        if arts:
            obj["artists"] = [{**a, "name": n} if isinstance(a, dict) else n for a, n in zip(arts, names2)]
        elif isinstance(obj.get("artist"), str):
            obj["artist"] = names2[0]
        if isinstance(al, dict):
            obj["album"] = {**al, "name": al_name}
        elif isinstance(al, str):
            obj["album"] = al_name
        if o:
            obj["o"] = o
    elif isinstance(obj.get("artist"), str):
        obj["artist"] = script(obj["artist"], lang)
    for k, v in obj.items():
        if k in ("title", "artists", "artist", "album", "o", "q", "queries", "english", "core_artists", "explore_artists", "avoid"):
            continue
        if k == "songs" and isinstance(v, list) and v and all(isinstance(x, list) and len(x) >= 4 for x in v):
            for x in v:   # the record's songs: [vid, title, artist names, album, ...] (ear._song), `o` appended
                x[1], x[2], x[3], o = song(x[1], x[2], x[3], lang)
                if o:
                    x.append(o)
        elif k in ("near", "seeds"):   # a song as one line ("Title (feat. X)"), or the songs themselves
            obj[k] = [_line(x, lang) for x in v] if isinstance(v, list) else _line(v, lang)
        elif k in _TEXT_KEYS and isinstance(v, str):
            obj[k] = typeset(v, lang)
        elif k in _TEXT_KEYS and isinstance(v, list) and all(isinstance(x, str) for x in v):
            obj[k] = [typeset(x, lang) for x in v]
        else:
            obj[k] = for_reader(v, lang)
    return obj


def stale() -> bool:
    """Written by Claude for a reader of the other language (Chinese vs English)."""
    prof = store.read_json(store.PROFILE) or {}
    return bool(prof.get("portrait")) and family(prof.get("lang", "zh-Hans")) != family(of())


RETELL_SCHEMA = {"type": "object", "properties": {"out": {"type": "array", "items": {"type": "object", "properties": {
    "i": {"type": "integer"}, "x": {"type": "string"}}, "required": ["i", "x"]}}}, "required": ["out"]}
RETELL_SYSTEM = """You rewrite the text of one listener's private music recommender for them, now that they read @LANG@.
Each input line is "index<TAB>text": a taste portrait, the names and descriptions of their listening lanes, and the
one-line reason given for each recommended song. Return each line in natural @LANG@ with the same index and meaning,
about as long as the original, plain and specific. Song titles, album names and artist names stay exactly as written.
@TITLES@ Lane names stay short (@NAME@). Chinese takes full-width punctuation (，。：；？！). Add nothing about the
listener, such as whether an artist is new to them: the page says that itself."""

_CJK = "\u3400-\u9fff\u3040-\u30ff"
_HALF = re.compile(rf"(?<=[{_CJK}》」』）])\s*([,;:?!])\s*|\s*([,;:?!])\s*(?=[{_CJK}《「『（])")
_FULL = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}


def zh_punct(text: str) -> str:
    """Claude now and then writes Chinese with ASCII commas; beside Chinese characters they read as typos. Titles keep
    theirs."""
    return "".join(p if _TITLE.fullmatch(p) else _HALF.sub(lambda m: _FULL[m.group(1) or m.group(2)], p) for p in _TITLE.split(text))


def retell(log) -> dict:
    """Rewrite what Claude already wrote (portrait, lanes, reasons) in the listener's language, without rebuilding."""
    from . import llm, rank
    lang = of()
    w = WRITE[lang]
    system = (RETELL_SYSTEM.replace("@LANG@", w["lang"]).replace("@TITLES@", w["titles"]).replace("@NAME@", w["name"]))
    docs = {f: store.read_json(f) for f in (store.PROFILE, store.EDITION, store.ASKS)}
    units = [d for d in (docs[store.PROFILE], docs[store.EDITION], *(docs[store.ASKS] or [])) if d]
    units = [d for d in units if family(d.get("lang", "zh-Hans")) != family(lang)]
    todo = [(d, c, k) for d in units for c, k in _slots(d, [])]
    log(tr("改写 {n} 段", n=len(todo)))
    chunks = [todo[i:i + 120] for i in range(0, len(todo), 120)]

    def run(chunk):
        prompt = "\n".join(f"{i}\t{c[k]}".replace("\n", " ") for i, (_, c, k) in enumerate(chunk))
        res = llm.call(prompt, system, RETELL_SCHEMA, model="sonnet", timeout=600, retries=1)
        for x in res["out"]:
            if 0 <= x["i"] < len(chunk) and x["x"].strip():
                _, c, k = chunk[x["i"]]
                c[k] = x["x"].strip() if lang == "en" else zh_punct(x["x"].strip())
                if k == "reason":
                    c[k] = rank.about_them(c[k])
    with store.Pool(3) as ex:   # each call bills the listener whose job this is
        list(ex.map(run, chunks))
    for d in units:
        d["lang"] = lang
    for f, d in docs.items():
        now = store.read_json(f)
        same = (f == store.PROFILE and (now or {}).get("built") == (d or {}).get("built")
                or f == store.EDITION and (now or {}).get("id") == (d or {}).get("id")
                or f == store.ASKS and [x.get("created") for x in now or []] == [x.get("created") for x in d or []])
        if d and same:   # otherwise it was rebuilt meanwhile, already in the new language
            store.write_json(f, d)
    return {"lines": len(todo)}


# ---------- messages ----------
EN = {
    # progress lines printed by the command line and the server log
    "{n} 首交给 Mac 试听": ("{n} song handed to the Mac to hear", "{n} songs handed to the Mac to hear"),
    "试听 {n} 首新歌": ("Hearing {n} new song", "Hearing {n} new songs"),
    "理解需求": "Reading the request",
    "从 {s} 首你的歌和 {a} 位歌手出发找歌": "Searching out from {s} of your songs and {a} artists",
    "{n} 首候选，编辑挑选中": "{n} candidates; the editor is choosing",
    "完成，用时 {s} 秒": "Done in {s} s",
    "{lane}: {c} 首候选，{p} 首进入试听": "{lane}: {c} candidates, {p} go on to be heard",
    "试听完成 {stats}": "Heard: {stats}",
    "试听失败，按图谱排序 ({e})": "Couldn't hear them, ranking by the graph ({e})",
    "专注: {n} 个长歌单候选": "Focus: {n} long mixes found",
    "编辑精选中（{n} 条线并行）": "The editor is choosing ({n} stations at once)",
    "Claude 通读每条线的全部候选（{n} 条线）": "Claude is reading every candidate for each station ({n} stations)",
    "整理歌曲信息": "Tidying song details",
    "已读 {n} / {total} 个喜欢的视频": "Read {n} of {total} liked videos",
    "查看 {n} 个新喜欢的视频是不是歌": "Checking whether {n} newly liked videos are songs",
    "整理歌曲 {d} / {n}": "Sorting songs {d} / {n}",
    "给每首喜欢的歌标上听感和场景": "Tagging each liked song with its sound and moments",
    "找出你的几种听歌状态": "Finding the kinds of music you listen to",
    "把每首歌放进对应的电台": "Putting each song in its station",
    "把 {n} 首新喜欢放进电台": ("Putting {n} new like into stations", "Putting {n} new likes into stations"),
    "新增 {n} 首": ("{n} new like", "{n} new likes"),
    "没读到 YouTube 上的其他信号（{e}）": "Couldn't read your other YouTube signals ({e})",
    "读到 {d} 首不喜欢、{f} 个订阅的音乐频道、{s} 首歌单里的歌": "Read {d} thumbs-down songs, {f} music channels you follow, {s} songs in your playlists",
    "常听的歌暂时没放进电台（{e}）": "Songs you play often aren't in a station yet ({e})",
    "从播放里读出 {n} 首你常听、没点喜欢的歌": ("Read {n} song you play often without a like", "Read {n} songs you play often without a like"),
    "没有新的喜欢": "No new likes",
    "改写 {n} 段": ("Rewriting {n} passage", "Rewriting {n} passages"),
    "读取你在 YouTube 点过的喜欢": "Reading what you liked on YouTube",
    "读取你在网易云喜欢的歌": "Reading the songs you liked on NetEase",
    "读取你在 QQ 音乐喜欢的歌": "Reading the songs you liked on QQ Music",
    "在 YouTube Music 上找 {n} 首歌": ("Finding {n} song on YouTube Music", "Finding {n} songs on YouTube Music"),
    "这个账号已经在用别的喜欢了": "This account already gets its likes from somewhere else",
    "现在只能通过朋友的邀请加入": "Right now you can only join through a friend's invite",
    "了解你的口味": "Learning your taste",
    "挑第一期电台": "Picking the first stations",
    "需要重新登录": "Please sign in again",
    "今天 {hm}": "today {hm}",
    "明天 {hm}": "tomorrow {hm}",
    "Google 登录还没配置": "Google sign-in isn't set up yet",
    "先在设置里连接 YouTube Music": "Connect YouTube Music in Settings first",
    "今天写入 YouTube 的额度用完了，{at} 后再存": "Today's YouTube write quota is used up. Save again after {at}",
    "YouTube Music 的连接失效了，在设置里重新连接": "Lost the connection to YouTube Music. Reconnect in Settings",
    "YouTube 拒绝了请求：{e}": "YouTube refused the request: {e}",
    "现在不需要重新准备": "Nothing to set up again right now",
    "还没连接 YouTube Music": "YouTube Music isn't connected yet",
    "先听着": "For now",
    "从你最近的喜欢出发": "Starting from your recent likes",
    "用同一个 Google 账号登录就行": "Sign in with the same Google account",
    "主人的数据不能在这里删": "The owner's data can't be deleted here",
    "只有主人可以邀请": "Only the owner can invite",
    "先在服务器上配置 Claude API key：你的 Claude 订阅只能你自己用": "Set up a Claude API key on the server first: your Claude subscription is for you alone",
    "写个名字": "Add a name",
    "YouTube 没有返回临时播放列表": "YouTube didn't return a queue",
    "沿着〈{s}〉的电台继续": "Following on from “{s}”",
    "知音挑的歌": "Picked by Zhiyin",
    "服务器上还没有配置 Claude": "Claude isn't set up on the server yet",
    "主人还没有为其他听众配置 Claude API key": "The owner hasn't set up a Claude API key for other listeners yet",
    "Mac 不在线（睡着或关机了）": "The Mac is offline (asleep or shut down)",
    "今天大家共用的 Claude 额度到了上限，明天再挑": "Today's shared Claude allowance is used up. New picks tomorrow",
    "你今天的 Claude 额度用完了，明天再来": "Your Claude allowance for today is used up. Come back tomorrow",
    "这个月大家共用的 Claude 额度用完了，过几天会恢复": "This month's shared Claude allowance is used up. It comes back in a few days",
    "先在设置里打开「同步喜欢」，知音才能往 YouTube 写歌单": "Turn on “Sync likes” in Settings first, so Zhiyin can write playlists to YouTube",
    "今天的 Claude 额度（${cap}）用完了，明天再来": "Today's Claude allowance (${cap}) is used up. Come back tomorrow",
    "Mac 中途离线了": "The Mac went offline midway",
    "Mac 上的 Claude 没有按时答复": "Claude on the Mac didn't answer in time",
    "网易云音乐": "NetEase Cloud Music",
    "知音": "Zhiyin",
    "朋友": "Friend",
    "排队中：另一位听众的电台正在准备": "Waiting: another listener's stations are being set up",
    "第一次准备用完了它的 Claude 额度；额度按 30 天计算，过些天再试":
        "Your first setup used up its Claude allowance, which counts over 30 days; try again in a few days",
    "排队中：前面还有 {n} 位，大约 {m} 分钟后开始": ("Waiting: 1 listener ahead of you, starting in about {m} min",
                                           "Waiting: {n} listeners ahead of you, starting in about {m} min"),
    "知音：把你在 YouTube Music 点过的喜欢，画成一张唱片": "Zhiyin: every song you've liked on YouTube Music, drawn as a record",
    "用 Google 登录，把你的喜欢画成一张唱片，给你的口味起个名字；之后每周为你挑几组没听过的歌。":
        "Sign in with Google to draw your likes as a record and get a name for your taste, then new songs every week "
        "you haven't heard.",
    "其他": "Other",
    "{n} 年": ("{n} year", "{n} years"),
    "{n} 种语言": ("{n} language", "{n} languages"),
    "{n} 首": ("{n} song", "{n} songs"),
    "最早的一首是《{title}》，{who}。": "Your first like: “{title}”, {who}.",
    "最早的一首是《{title}》。": "Your first like: “{title}”.",
    "最老的一首是《{title}》，{who}。": "The oldest: “{title}”, {who}.",
    "最老的一首是《{title}》。": "The oldest: “{title}”.",
    "你喜欢的歌，有一半发行在 {y} 年或更早。": "Half the songs you like came out in {y} or earlier.",
    "今天换了好几次了，明天再换": "That's a few new names today. Try again tomorrow",
    "陪你最久的是{name}：从 {a} 到 {b}，一共 {n} 首。": "The one who's been with you longest is {name}: from {a} to {b}, {n} songs in all.",
    "最近一年的新喜欢里，「{lane}」占了 {p1}%，之前只有 {p0}%。": "{lane} makes up {p1}% of the past year's new likes, up from {p0}%.",
    "「{lane}」是最晚出现的一种口味，那年才有第一首，现在已经 {n} 首。": "{lane} is your newest taste: its first song came that year, and now there are {n}.",
    "隔了一阵又点了一次喜欢，像《{title}》，前后隔了 {gap} 年。": "Songs you came back to and liked again, like “{title}”, {gap} years apart.",
    "隔了一阵又点了一次喜欢，像《{title}》。": "Songs you came back to and liked again, like “{title}”.",
    "点得最密的一个月是 {y} 年 {m} 月。": "Your busiest month for likes was {month}.",
    "{p}% 的歌，你在它发行的当年就点了喜欢。": "{p}% of your songs you liked in the year they came out.",
    "韩语": "Korean", "英语": "English", "国语": "Mandarin", "粤语": "Cantonese", "日语": "Japanese", "泰语": "Thai",
    "纯音乐": "Instrumental",
    "知音 · {name} · {date}": "Zhiyin · {name} · {date}",
    "这不像网易云或 QQ 音乐的主页、歌单链接。在 App 里点分享，选「复制链接」再贴过来": "That doesn't look like a NetEase or QQ Music profile or playlist link. In the app, tap Share, choose Copy link, and paste it here",
    "这是一首歌的链接。要的是整份喜欢：在网易云打开「我喜欢的音乐」，点分享，复制链接贴过来": "That's a link to one song, and this needs all your likes: open “My Liked Music” in NetEase, tap Share, copy the link and paste it here",
    "这是一首歌的链接。要的是整份喜欢：在 QQ 音乐点头像进主页，右上角「···」点分享，复制链接贴过来": "That's a link to one song, and this needs all your likes: in QQ Music, tap your picture to open your profile, then “···” at the top right and Share, and copy the link",
    "这份「我喜欢的音乐」只有本人看得到。在网易云的隐私设置里改成所有人可见，或者贴一份公开歌单的链接": "Only its owner can see this “My Liked Music”. Make it visible to everyone in NetEase's privacy settings, or paste a link to a public playlist",
    "你的「喜欢」只有自己看得到。在 QQ 音乐点头像进主页，右上角「···」→「访问设置」，打开「喜欢」再贴一次；或者贴一份公开歌单的链接": "Only you can see your likes. In QQ Music, tap your picture to open your profile, then “···” at the top right → 访问设置 (visitor settings), turn on 喜欢 (likes) and paste again; or paste a link to a public playlist",
    "QQ 音乐那边没有回应，过一会儿再试": "QQ Music isn't answering. Try again in a little while",
    "这份歌单只有 {n} 首，至少要 20 首才画得出来": ("This playlist has only {n} song; a record needs at least 20", "This playlist has only {n} songs; a record needs at least 20"),
    "网易云那边没有回应，过一会儿再试": "NetEase isn't answering. Try again in a little while",
    "做得有点快，过几分钟再试": "That's a lot of records at once. Try again in a few minutes",
    "今天起名字的额度用完了，明天再来起名": "Today's names have run out. Come back tomorrow for yours",
    "起名字的时候出了点问题，再试一次": "Something went wrong while naming it. Try again",
    "现在起不了名字，唱片先画好了": "It can't be named right now, so here's the record on its own",
    "名字还没起好，等一下再分享": "Your name isn't ready yet. Share it in a moment",
    "今天分享得够多了，明天再来": "That's enough links for today. More tomorrow",
    "这张唱片过期了，重新做一张再分享": "This record has expired. Draw it again to share it",
    "我的知音唱片": "My Zhiyin record",
    "{n} 首喜欢，{y} 年至今，每一圈是一年。做一张你自己的。": "{n} liked songs since {y}, one ring a year. Make your own.",
    "{n} 首喜欢，每一圈是一年。做一张你自己的。": "{n} liked songs, one ring a year. Make your own.",
    "「{r}」": "“{r}” ",
    "让 Claude 也锐评一下你的歌单。": "Let Claude roast your likes too.",
    "让 Claude 锐评你的网易云、QQ 音乐歌单": "Let Claude roast your NetEase or QQ Music likes",
    "贴一个网易云或 QQ 音乐的歌单链接，出一张你的唱片：Claude 给你的口味起个名字，再锐评一句。":
        "Paste a NetEase or QQ Music link and get your record: Claude names your taste and roasts it in one line.",
    "大众度：你喜欢的歌在网易云的平均热度是 {p}，热歌榜是 100。": "How mainstream: the songs you like average {p} on NetEase's popularity scale, where the hot chart is 100.",
}
# Taiwan and Hong Kong wording the converter doesn't know.
HANT = {
    "知音：把你在 YouTube Music 点过的喜欢，画成一张唱片": "知音：把你在 YouTube Music 按過的喜歡，畫成一張唱片",
    "用 Google 登录，把你的喜欢画成一张唱片，给你的口味起个名字；之后每周为你挑几组没听过的歌。":
        "用 Google 登入，把你的喜歡畫成一張唱片，幫你的口味取個名字；之後每週為你挑幾組沒聽過的歌。",
    "先在服务器上配置 Claude API key：你的 Claude 订阅只能你自己用": "先在伺服器上設定 Claude API key：你的 Claude 訂閱只能你自己用",
    "YouTube Music 的连接失效了，在设置里重新连接": "YouTube Music 的連接失效了，在設定裡重新連接",
    "先在设置里连接 YouTube Music": "先在設定裡連接 YouTube Music",
    "还没连接 YouTube Music": "還沒連接 YouTube Music",
    "用同一个 Google 账号登录就行": "用同一個 Google 帳戶登入就行",
    "YouTube 没有返回临时播放列表": "YouTube 沒有回傳臨時播放清單",
    "知音挑的歌": "知音挑的歌",
    "这不像网易云或 QQ 音乐的主页、歌单链接。在 App 里点分享，选「复制链接」再贴过来": "這不像網易雲或 QQ 音樂的主頁、歌單連結。在 App 裡點分享，選「複製連結」再貼過來",
    "这是一首歌的链接。要的是整份喜欢：在网易云打开「我喜欢的音乐」，点分享，复制链接贴过来": "這是一首歌的連結。要的是整份喜歡：在網易雲打開「我喜歡的音樂」，點分享，複製連結貼過來",
    "这是一首歌的链接。要的是整份喜欢：在 QQ 音乐点头像进主页，右上角「···」点分享，复制链接贴过来": "這是一首歌的連結。要的是整份喜歡：在 QQ 音樂點頭像進主頁，右上角「···」點分享，複製連結貼過來",
    "这份「我喜欢的音乐」只有本人看得到。在网易云的隐私设置里改成所有人可见，或者贴一份公开歌单的链接": "這份「我喜歡的音樂」只有本人看得到。在網易雲的隱私設定裡改成所有人可見，或者貼一份公開歌單的連結",
    "你的「喜欢」只有自己看得到。在 QQ 音乐点头像进主页，右上角「···」→「访问设置」，打开「喜欢」再贴一次；或者贴一份公开歌单的链接": "你的「喜歡」只有自己看得到。在 QQ 音樂點頭像進主頁，右上角「···」→「訪問設置」，打開「喜歡」再貼一次；或者貼一份公開歌單的連結",
    "贴一个网易云或 QQ 音乐的歌单链接，出一张你的唱片：Claude 给你的口味起个名字，再锐评一句。": "貼一個網易雲或 QQ 音樂的歌單連結，出一張你的唱片：Claude 幫你的口味取個名字，再銳評一句。",
    "今天起名字的额度用完了，明天再来起名": "今天取名字的額度用完了，明天再來取名",
    "起名字的时候出了点问题，再试一次": "取名字的時候出了點問題，再試一次",
    "名字还没起好，等一下再分享": "名字還沒取好，等一下再分享",
    "现在起不了名字，唱片先画好了": "現在取不了名字，唱片先畫好了",
    "{n} 首喜欢，{y} 年至今，每一圈是一年。做一张你自己的。": "{n} 首喜歡，{y} 年至今，每一圈是一年。做一張你自己的。",
    "{n} 首喜欢，每一圈是一年。做一张你自己的。": "{n} 首喜歡，每一圈是一年。做一張你自己的。",
    "这份歌单只有 {n} 首，至少要 20 首才画得出来": "這份歌單只有 {n} 首，至少要 20 首才畫得出來",
    "这个账号已经在用别的喜欢了": "這個帳戶已經在用別的喜歡了",
    "现在只能通过朋友的邀请加入": "現在只能透過朋友的邀請加入",
}


def tr(text: str, lang: str | None = None, **kw) -> str:
    lang = lang or of()
    out = text if lang == "zh-Hans" else EN.get(text, text) if lang == "en" else HANT.get(text) or convert(text, "zh-Hans", "zh-Hant")
    if isinstance(out, tuple):
        out = out[0] if kw.get("n") == 1 else out[1]
    return out.format(**kw) if kw else out
