"""The listener's language: what the server says to them, what Claude writes for them, and turning text that was
already written in one Chinese script into the other. Messages are written in Simplified Chinese where they are used
and looked up here, the same way web/i18n.js does it for the page."""
import contextvars
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
    if store.is_sample(uid):
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
@TITLES@ Lane names stay short (@NAME@). Chinese takes full-width punctuation (，。：；？！)."""

_CJK = "\u3400-\u9fff\u3040-\u30ff"
_HALF = re.compile(rf"(?<=[{_CJK}》」』）])\s*([,;:?!])\s*|\s*([,;:?!])\s*(?=[{_CJK}《「『（])")
_FULL = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}


def zh_punct(text: str) -> str:
    """Claude now and then writes Chinese with ASCII commas; beside Chinese characters they read as typos. Titles keep
    theirs."""
    return "".join(p if _TITLE.fullmatch(p) else _HALF.sub(lambda m: _FULL[m.group(1) or m.group(2)], p) for p in _TITLE.split(text))


def retell(log) -> dict:
    """Rewrite what Claude already wrote (portrait, lanes, reasons) in the listener's language, without rebuilding."""
    from . import llm
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
    "整理歌曲信息": "Tidying song details",
    "已读 {n} / {total} 个喜欢的视频": "Read {n} of {total} liked videos",
    "查看 {n} 个新喜欢的视频是不是歌": "Checking whether {n} newly liked videos are songs",
    "整理歌曲 {d} / {n}": "Sorting songs {d} / {n}",
    "给每首喜欢的歌标上听感和场景": "Tagging each liked song with its sound and moments",
    "找出你的几种听歌状态": "Finding the kinds of music you listen to",
    "把每首歌放进对应的电台": "Putting each song in its station",
    "把 {n} 首新喜欢放进电台": ("Putting {n} new like into stations", "Putting {n} new likes into stations"),
    "新增 {n} 首": ("{n} new like", "{n} new likes"),
    "没有新的喜欢": "No new likes",
    "改写 {n} 段": ("Rewriting {n} passage", "Rewriting {n} passages"),
    "读取你在 YouTube 点过的喜欢": "Reading what you liked on YouTube",
    "了解你的口味": "Learning your taste",
    "挑第一批电台": "Picking the first stations",
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
    "我的另一个账号": "My other account",
    "先在服务器上配置 Claude API key：你的 Claude 订阅只能你自己用": "Set up a Claude API key on the server first: your Claude subscription is for you alone",
    "写个名字": "Add a name",
    "YouTube 没有返回临时播放列表": "YouTube didn't return a queue",
    "沿着〈{s}〉的电台继续": "Following on from “{s}”",
    "知音挑的歌": "Picked by Zhiyin",
    "服务器上还没有配置 Claude": "Claude isn't set up on the server yet",
    "主人还没有为其他听众配置 Claude API key": "The owner hasn't set up a Claude API key for other listeners yet",
    "Mac 不在线（睡着或关机了）": "The Mac is offline (asleep or shut down)",
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
    "用 Google 登录，一分钟内画出你的唱片，给你的口味起个名字。之后每天几首你没听过的歌，每首都写着为什么挑它。":
        "Sign in with Google and within a minute you get your record and a name for your taste. Then a few songs a day "
        "you haven't heard, each with the reason it was picked.",
    "其他": "Other",
    "{n} 年": ("{n} year", "{n} years"),
    "{n} 种语言": ("{n} language", "{n} languages"),
    "{n} 首": ("{n} song", "{n} songs"),
    "最早的一首是《{title}》，{who}。": "Your first like: “{title}”, {who}.",
    "最早的一首是《{title}》。": "Your first like: “{title}”.",
    "你喜欢的歌，有一半发行在 {y} 年或更早。": "Half the songs you like came out in {y} or earlier.",
    "今天换了好几次了，明天再换": "That's a few new names today. Try again tomorrow",
    "陪你最久的是 {name}：从 {a} 到 {b}，一共 {n} 首。": "The one who's been with you longest is {name}: from {a} to {b}, {n} songs in all.",
    "最近一年的新喜欢里，「{lane}」占了 {p1}%，之前只有 {p0}%。": "{lane} makes up {p1}% of the past year's new likes, up from {p0}%.",
    "「{lane}」是最晚出现的一种口味，那年才有第一首，现在已经 {n} 首。": "{lane} is your newest taste: its first song came that year, and now there are {n}.",
    "隔了一阵又点了一次喜欢，像《{title}》，前后隔了 {gap} 年。": "Songs you came back to and liked again, like “{title}”, {gap} years apart.",
    "隔了一阵又点了一次喜欢，像《{title}》。": "Songs you came back to and liked again, like “{title}”.",
    "点得最密的一个月是 {y} 年 {m} 月。": "Your busiest month for likes was {month}.",
    "{p}% 的歌，你在它发行的当年就点了喜欢。": "{p}% of your songs you liked in the year they came out.",
    "韩语": "Korean", "英语": "English", "国语": "Mandarin", "粤语": "Cantonese", "日语": "Japanese", "泰语": "Thai",
    "纯音乐": "Instrumental",
    "知音 · {name} · {date}": "Zhiyin · {name} · {date}",
}
# Taiwan and Hong Kong wording the converter doesn't know.
HANT = {
    "知音：把你在 YouTube Music 点过的喜欢，画成一张唱片": "知音：把你在 YouTube Music 按過的喜歡，畫成一張唱片",
    "用 Google 登录，一分钟内画出你的唱片，给你的口味起个名字。之后每天几首你没听过的歌，每首都写着为什么挑它。":
        "用 Google 登入，一分鐘內畫出你的唱片，幫你的口味取個名字。之後每天幾首你沒聽過的歌，每首都寫著為什麼挑它。",
    "先在服务器上配置 Claude API key：你的 Claude 订阅只能你自己用": "先在伺服器上設定 Claude API key：你的 Claude 訂閱只能你自己用",
    "YouTube Music 的连接失效了，在设置里重新连接": "YouTube Music 的連接失效了，在設定裡重新連接",
    "先在设置里连接 YouTube Music": "先在設定裡連接 YouTube Music",
    "还没连接 YouTube Music": "還沒連接 YouTube Music",
    "用同一个 Google 账号登录就行": "用同一個 Google 帳戶登入就行",
    "我的另一个账号": "我的另一個帳戶",
    "YouTube 没有返回临时播放列表": "YouTube 沒有回傳臨時播放清單",
    "知音挑的歌": "知音挑的歌",
}


def tr(text: str, lang: str | None = None, **kw) -> str:
    lang = lang or of()
    out = text if lang == "zh-Hans" else EN.get(text, text) if lang == "en" else HANT.get(text) or convert(text, "zh-Hans", "zh-Hant")
    if isinstance(out, tuple):
        out = out[0] if kw.get("n") == 1 else out[1]
    return out.format(**kw) if kw else out
