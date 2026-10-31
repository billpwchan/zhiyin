import json
import re
import subprocess
from pathlib import Path

from zhiyin import i18n

WEB = Path(__file__).resolve().parents[1] / "web"


def _keys() -> set[str]:
    """Every string the pages look up: t('…') in the scripts, data-i18n* in the markup."""
    keys = set()
    for f in ("app.js", "gate.html"):
        src = (WEB / f).read_text()
        keys |= {m.group(2) for m in re.finditer(r"\bt\((['`])((?:\\.|(?!\1).)*)\1", src)}
    for f in ("index.html", "gate.html"):
        keys |= set(re.findall(r'data-i18n(?:-label|-ph|-title)?="([^"]+)"', (WEB / f).read_text()))
    return {k for k in keys if "${" not in k}


def _strings() -> dict:
    out = subprocess.run(["node", "-e", "global.document={documentElement:{dataset:{}}};global.navigator={languages:[]};"
                          "eval(require('fs').readFileSync(process.argv[1],'utf8')+';process.stdout.write(JSON.stringify(STRINGS))')",
                          str(WEB / "i18n.js")], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_every_page_string_has_both_translations():
    strings, keys = _strings(), _keys()
    for lang in ("en", "zh-Hant"):
        missing = sorted(k for k in keys if k not in strings[lang])
        assert not missing, f"{lang} lacks {missing}"


def test_translations_keep_their_placeholders():
    for lang, d in _strings().items():
        for k, v in d.items():
            want = set(re.findall(r"\{(\w+)\}", k))
            for x in v if isinstance(v, list) else [v]:
                assert set(re.findall(r"\{(\w+)\}", x)) <= want | {"n"}, (lang, k, x)


def test_traditional_has_no_simplified_left():
    import opencc
    cc = opencc.OpenCC("s2t")
    for k, v in _strings()["zh-Hant"].items():
        for x in v if isinstance(v, list) else [v]:
            # 台 is how Taiwan and Hong Kong write 電台; the converter's default is 臺
            assert all(cc.convert(ch) == ch for ch in x if ch != "台"), (k, x)


def test_server_messages_translate_and_keep_titles():
    assert i18n.tr("{n} 首", "en", n=1) == "1 song"
    assert i18n.tr("最早的一首是《{title}》，{who}。", "zh-Hant", title="后来", who="刘若英") == "最早的一首是《后来》，刘若英。"
    assert i18n.convert("听感接近〈后来〉", "zh-Hans", "zh-Hant") == "聽感接近〈后来〉"


def test_lang_from_browser_tags():
    assert [i18n.norm(x) for x in ("zh-TW", "zh-HK", "zh-Hant-MO", "zh-CN", "zh", "en-GB", "ja")] == \
        ["zh-Hant", "zh-Hant", "zh-Hant", "zh-Hans", "zh-Hans", "en", None]


def test_each_account_keeps_its_own_language_and_reads_its_own_script(monkeypatch):
    from fastapi.testclient import TestClient

    from zhiyin import accounts, server, store
    monkeypatch.setattr(server, "AUTH", True)
    a = accounts.redeem(accounts.invite("A"))
    b = accounts.redeem(accounts.invite("B"))
    for uid in (a, b):
        with store.as_user(uid):
            store.write_json(store.PROFILE, {"lang": "zh-Hans", "lanes": [], "portrait": {"headline": "从〈后来〉开始的听感", "paragraphs": []}})
            # written for a Traditional reader by the editor, but the station's name copied from the profile as is
            store.write_json(store.EDITION, {"id": "e", "lang": "zh-Hant", "focus": None, "lanes": [
                {"key": "k", "name": "日光律动", "blurb": "白天听", "when": "想动一动的时候", "picks": [], "reserve": []}]})
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(b))
    r = c.post("/api/account/lang", json={"lang": "zh-Hant"}, headers={"X-Zhiyin-Uid": b})
    assert r.status_code == 200 and r.cookies.get(i18n.COOKIE) == "zh-Hant"
    assert accounts.prefs(b)["lang"] == "zh-Hant" and accounts.prefs(a).get("lang") != "zh-Hant"
    st = c.get("/api/state").json()
    # the song it quotes is shown in the reader's script too, like every title on the page
    assert st["me"]["lang"] == "zh-Hant" and st["portrait"]["headline"] == "從〈後來〉開始的聽感"
    assert (st["edition"]["lanes"][0]["name"], st["edition"]["lanes"][0]["when"]) == ("日光律動", "想動一動的時候")
    assert '<html lang="zh-Hant" data-lang="zh-Hant">' in c.get("/").text
    c.cookies.set(accounts.COOKIE, accounts.new_session(a))
    assert c.get("/api/state", headers={"X-Zhiyin-Uid": a}).json()["portrait"]["headline"] == "从〈后来〉开始的听感"


def test_a_new_listener_starts_in_their_browsers_language(monkeypatch):
    from fastapi.testclient import TestClient

    from zhiyin import accounts, server
    monkeypatch.setattr(server, "AUTH", True)
    uid = accounts.redeem(accounts.invite("C"))
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    assert 'data-lang="en"' in c.get("/", headers={"accept-language": "en-US,en;q=0.9"}).text
    assert accounts.prefs(uid)["lang"] == "en"
    assert 'data-lang="en"' in c.get("/", headers={"accept-language": "zh-TW"}).text   # chosen once, then kept


def test_chinese_rewrites_get_full_width_punctuation():
    assert i18n.zh_punct("律动,从里约到东京。") == "律动，从里约到东京。"
    assert i18n.zh_punct("《Love, Again》很接近,听起来") == "《Love, Again》很接近，听起来"
    assert i18n.zh_punct("和 Bill Evans, Chet Baker 一样，05:00 出") == "和 Bill Evans, Chet Baker 一样，05:00 出"
    assert i18n.zh_punct("《恋は、ダンス!》很轻,适合") == "《恋は、ダンス!》很轻，适合"


def test_accounts_from_before_the_choice_keep_the_language_they_were_written_in():
    from zhiyin import accounts, store
    en, old, fresh = (accounts.redeem(accounts.invite(n)) for n in ("E", "O", "F"))
    with store.as_user(en):
        store.write_json(store.PROFILE, {"lang": "en", "lanes": []})
    with store.as_user(old):
        store.write_json(store.PROFILE, {"lanes": []})
    for u in (en, old, fresh):
        accounts.set_prefs(u, lang=None)
    store.kv_set("lang-migrated", False)
    i18n.migrate()
    assert accounts.prefs(en)["lang"] == "en" and accounts.prefs(old)["lang"] == "zh-Hans"
    assert "lang" not in accounts.prefs(fresh)        # their browser decides on the first visit


def test_no_two_functions_share_a_name_in_the_page_script():
    # a second top-level `function x` silently replaces the first everywhere (the settings page went blank that way)
    names = re.findall(r"^(?:async )?function (\w+)\(", (WEB / "app.js").read_text(), re.M)
    assert not [n for n in set(names) if names.count(n) > 1]


def test_songs_and_text_reach_each_reader_in_their_script():
    from zhiyin.i18n import for_reader
    page = {"lanes": [{"name": "台北歌本", "picks": [
        {"vid": "a", "title": "愛我別走", "artists": [{"name": "張震嶽"}], "album": {"name": "秘密基地"},
         "reason": "《After 17》是最朴素的陈绮贞，2005年的歌"},
        {"vid": "b", "title": "Just Stay (合作演出：JUNNY和Def.)", "artists": [{"name": "ØFFSHORE"}]},
        {"vid": "c", "title": "丸ノ内サディスティック", "artists": [{"name": "椎名林檎"}]},
        {"vid": "d", "title": "残響散歌", "artists": [{"name": "Aimer"}]}]}],
        "asks": [{"q": "下雨的周日，聽點city pop", "picks": []}]}
    out = for_reader(page, "zh-Hans")
    a, b, c, d = out["lanes"][0]["picks"]
    assert (a["title"], a["artists"][0]["name"], a["album"]["name"]) == ("爱我别走", "张震岳", "秘密基地")
    assert a["reason"] == "《After 17》是最朴素的陈绮贞，2005 年的歌"
    assert b["title"] == "Just Stay (feat. JUNNY & Def.)"
    assert (c["title"], d["title"]) == ("丸ノ内サディスティック", "残響散歌")   # Japanese keeps its own kanji
    assert out["asks"][0]["q"] == "下雨的周日，聽點city pop"   # the listener's own words stay
    assert for_reader({"vid": "x", "title": "写不来情歌", "artists": ["艾志恒Asen"]}, "zh-Hant") == \
        {"vid": "x", "title": "寫不來情歌", "artists": ["艾志恆Asen"], "o": {"t": "写不来情歌", "a": "艾志恒Asen", "al": ""}}
    assert for_reader({"vid": "x", "title": "愛我別走", "reason": "2005年"}, "en") == {"vid": "x", "title": "愛我別走", "reason": "2005年"}


def test_names_take_taiwan_forms_and_japanese_keeps_its_own():
    assert [i18n.script(x, "zh-Hant") for x in ("汪峰", "为你写诗", "这里", "台湾")] == ["汪峰", "為你寫詩", "這裡", "台灣"]
    # already in the reader's script: as written, not respelled (了解 is not made 瞭解, nor 朴 樸)
    assert [i18n.script(x, "zh-Hant") for x in ("終於了解自由", "朴載範", "臺灣")] == ["終於了解自由", "朴載範", "臺灣"]
    assert [i18n.script(x, "zh-Hans") for x in ("臺灣", "朴載範", "怎麼了")] == ["台湾", "朴载范", "怎么了"]
    # Shinjitai neither Chinese script writes, kana (but not the ・ Chinese also uses), a kanji only Japanese writes
    assert all(i18n.japanese(x) for x in ("変わらないもの", "黒い羊", "長渕剛", "残響散歌"))
    assert not any(i18n.japanese(x) for x in ("周杰倫", "林俊杰", "麦克・杰克逊", "秘密基地", "給予", "研究", "為你", "新郎"))
    # anything Japanese about a song keeps all of it as written; kanji alone can't tell (米津玄師 reads 米津玄师)
    out = i18n.for_reader({"vid": "x", "title": "感電", "artists": [{"name": "米津玄師"}], "album": {"name": "STRAY SHEEP"}}, "zh-Hans")
    assert (out["title"], out["artists"][0]["name"]) == ("感电", "米津玄师")
    out = i18n.for_reader({"vid": "x", "title": "感電", "artists": [{"name": "米津玄師"}], "album": {"name": "感電 / ストレイ"}}, "zh-Hans")
    assert (out["title"], out["artists"][0]["name"]) == ("感電", "米津玄師") and "o" not in out


def test_the_records_songs_and_the_lyric_lookup_keep_the_names_as_written():
    rec = {"label": "台北2005", "songs": [["v1", "愛我別走", ["張震嶽"], "秘密基地", 200, 2005.1, "k", 30, None, 0],
                                         ["v2", "Lemon", ["米津玄師"], "レモン", 255, 2019.2, "k", 40, None, 0]]}
    out = i18n.for_reader(rec, "zh-Hans")
    assert out["label"] == "台北 2005"
    assert out["songs"][0][1:4] == ["爱我别走", ["张震岳"], "秘密基地"]
    assert out["songs"][0][10] == {"t": "愛我別走", "a": "張震嶽", "al": "秘密基地"}   # what the lyric sites are asked
    assert len(out["songs"][1]) == 10
    page = {"edition": {"seeds": [{"vid": "a", "title": "後來", "artists": [{"name": "劉若英"}]}], "near": "後來 (合作演出：A和B)"}}
    out = i18n.for_reader(page, "zh-Hans")["edition"]
    assert (out["seeds"][0]["title"], out["seeds"][0]["artists"][0]["name"]) == ("后来", "刘若英")
    assert out["near"] == "后来 (feat. A & B)"


def test_timed_lyric_words_convert_as_one_phrase():
    from zhiyin import lyrics
    assert lyrics._words([[0, 1, "头"], [1, 2, "发"], [2, 3, "现在"]], "zh-Hant") == [[0, 1, "頭"], [1, 2, "髮"], [2, 3, "現在"]]


def test_a_name_is_the_same_key_in_either_script():
    from zhiyin.text import fold, song_key
    assert fold("劉若英") == fold("刘若英") and song_key("後來 (Live)") == song_key("后来")
    assert song_key("為妳寫的歌") == song_key("为你写的歌")


def test_each_piece_of_claudes_text_is_judged_by_what_it_is_written_in():
    assert i18n.written_in("K-pop 二代以后的 R&B，夜里开车听", "en") == "zh"
    assert i18n.written_in("Crowd Lu's new work, as warm as “愚人節快樂”", "zh-Hans") == "en"
    assert i18n.written_in("Night Drives", "en") == "en" and i18n.written_in("City Pop", "zh-Hans") == "zh"
    assert i18n.written_in("Gareth.T、Kiri T、moon tang、Dear Jane", "zh-Hans") == "zh"   # names, not English
    assert i18n.written_in("2016–2018", "en") is None
    for name in ("The 周杰伦 years", "陈奕迅 deep cuts", "Like 陈奕迅 and 林宥嘉, slower"):   # names inside English
        assert i18n.written_in(name, "en") == "en", name
    assert i18n.written_in("那几年循环 Coldplay 和 Keane", "en") == "zh"
    assert i18n.written_in("后来换成了 Coldplay、Keane 这些", "en") == "zh"


def _translator(monkeypatch, calls, fail=False):
    from zhiyin import llm

    def call(prompt, system, schema, **kw):
        calls.append(prompt)
        if fail:
            raise llm.LLMError("down")
        lines = [ln.split("\t") for ln in prompt.split("\n")]
        return {"out": [{"i": int(i), "x": f"EN {text}"} for i, _, text in lines]}
    monkeypatch.setattr(llm, "call", call)
    monkeypatch.setattr(llm, "unavailable", lambda *a, **k: None)


def _listener(name):
    from zhiyin import accounts, store
    uid = accounts.redeem(accounts.invite(name))
    accounts.set_status(uid, "ready")
    accounts.set_prefs(uid, lang="zh-Hans")
    with store.as_user(uid):
        lane = {"key": "k", "name": "夜车", "english": "night drive", "blurb": "夜里开车听的", "when": "开夜车的时候", "sound": "",
                "langs": [], "energy": "", "core_artists": [], "avoid": [], "discovery": 0.3}
        store.write_json(store.PROFILE, {"lang": "zh-Hans", "lanes": [lane],
                                         "portrait": {"headline": "你在夜里听得最多", "paragraphs": []}})
        store.write_json(store.EDITION, {"id": "e", "lang": "zh-Hans", "focus": None, "created": store.now(), "lanes": [
            {"key": "k", "name": "夜车", "blurb": "夜里开车听的", "when": "开夜车的时候", "picks": [
                {"vid": "v", "title": "后来", "artists": [{"name": "刘若英"}], "reason": "和你常听的那几首一样慢"}], "reserve": []}]})
        store.write_json(store.IDENT, {"label": "夜行的人", "lang": "zh-Hans"})
    return uid


def _settled(uid):
    import time

    from zhiyin import server
    for _ in range(200):
        j = server._jobs.get((uid, "retell"))
        if not j or not j["running"]:
            return j
        time.sleep(0.02)
    raise AssertionError("still filling")


def _client(uid, monkeypatch):
    from fastapi.testclient import TestClient

    from zhiyin import accounts, server
    monkeypatch.setattr(server, "AUTH", True)
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    c.headers["X-Zhiyin-Uid"] = uid
    return c


def test_a_switch_waits_for_the_words_then_turns_the_whole_page_over(monkeypatch):
    from zhiyin import accounts, ear, store
    calls = []
    _translator(monkeypatch, calls)
    uid = _listener("S")
    c = _client(uid, monkeypatch)
    me = c.post("/api/account/lang", json={"lang": "en"}).json()["me"]
    assert (me["lang"], me["lang_to"]) in (("zh-Hans", "en"), ("en", None))   # the page stays Chinese until it's ready
    assert not _settled(uid)["error"] and accounts.prefs(uid)["lang"] == "en" and "lang_to" not in accounts.prefs(uid)
    st = c.get("/api/state").json()
    assert st["portrait"]["headline"] == "EN 你在夜里听得最多" and not st["stale_lang"]
    lane = st["edition"]["lanes"][0]
    assert (lane["name"], lane["when"], lane["picks"][0]["reason"]) == ("EN 夜车", "EN 开夜车的时候", "EN 和你常听的那几首一样慢")
    with store.as_user(uid):
        assert ear.label() == "EN 夜行的人"
        assert store.read_json(store.PROFILE)["portrait"]["headline"] == "你在夜里听得最多"   # what Claude wrote is kept
    n = len(calls)
    # back and forth again: nothing to write, nothing to wait for
    assert c.post("/api/account/lang", json={"lang": "zh-Hant"}).json()["me"]["lang"] == "zh-Hant"
    assert c.get("/api/state").json()["portrait"]["headline"] == "你在夜裡聽得最多"
    assert c.post("/api/account/lang", json={"lang": "en"}).json()["me"]["lang"] == "en" and len(calls) == n


def test_a_switch_happens_even_when_claude_fails_and_the_rest_follows_later(monkeypatch):
    from zhiyin import accounts, store
    calls = []
    _translator(monkeypatch, calls, fail=True)
    uid = _listener("F")
    c = _client(uid, monkeypatch)
    c.post("/api/account/lang", json={"lang": "en"})
    assert _settled(uid)["error"] and accounts.prefs(uid)["lang"] == "en"
    st = c.get("/api/state").json()
    assert st["stale_lang"] and st["portrait"]["headline"] == "你在夜里听得最多"
    with store.as_user(uid):   # the share card leaves the headline off rather than print it in the other language
        assert i18n.translated("你在夜里听得最多", "zh-Hans", "en") is None
    n = len(calls)
    c.get("/api/state")
    assert len(calls) == n   # not again on every visit after a failure


def test_text_written_in_the_old_language_after_a_switch_is_put_into_the_new_one(monkeypatch):
    from zhiyin import store
    calls = []
    _translator(monkeypatch, calls)
    uid = _listener("B")
    c = _client(uid, monkeypatch)
    c.post("/api/account/lang", json={"lang": "en"})
    _settled(uid)
    with store.as_user(uid):   # an ask that started before the switch, written in Chinese
        store.write_json(store.ASKS, [{"q": "下雨天", "lang": "zh-Hans", "intent": "下雨天慢慢听", "created": 1, "picks": []}])
    c.get("/api/state")
    assert not _settled(uid)["error"]
    assert c.get("/api/state").json()["asks"][0]["intent"] == "EN 下雨天慢慢听"


def test_a_job_writes_in_the_language_it_started_in():
    import contextvars

    from zhiyin import accounts, store
    uid = _listener("P")

    def job():
        i18n.pin()
        accounts.set_prefs(uid, lang="en")   # switched while it runs
        return i18n.of(), i18n.tr("{n} 首", n=2)
    with store.as_user(uid):
        lang, msg = contextvars.copy_context().run(job)
        assert lang == "zh-Hans" and msg == "2 首" and i18n.of() == "en"
        assert i18n.again(msg) == "2 songs"   # a job's last line, read after the switch
        with i18n.writing("zh-Hant"):   # a portrait rewritten in its own language
            assert i18n.of() == "zh-Hant"
        assert i18n.of() == "en"


def test_what_a_job_wrote_before_a_switch_shows_in_the_new_language_when_it_ends(monkeypatch):
    import time

    from zhiyin import accounts, server, store
    calls = []
    _translator(monkeypatch, calls)
    uid = _listener("J")

    def build(log):   # a build that started in Chinese; the listener switched halfway
        accounts.set_prefs(uid, lang="en")
        store.write_json(store.ASKS, [{"q": "下雨天", "lang": i18n.of(), "intent": "下雨天慢慢听", "created": 1, "picks": []}])
        return {}
    with store.as_user(uid):
        j = server._start("ask", build)
        for _ in range(200):
            if not j["running"]:
                break
            time.sleep(0.02)
        assert not j["error"] and store.read_json(store.ASKS)[0]["lang"] == "zh-Hans"
        assert i18n.translated("下雨天慢慢听", "zh-Hans", "en") == "EN 下雨天慢慢听"   # filled before it ended


def test_lines_claude_leaves_out_are_not_asked_for_on_every_visit(monkeypatch):
    from zhiyin import llm, store
    calls = []

    def call(prompt, system, schema, **kw):
        calls.append(prompt)
        lines = [ln.split("\t") for ln in prompt.split("\n")]
        return {"out": [{"i": int(i), "x": f"EN {text}"} for i, _, text in lines if "一样慢" not in text]}
    monkeypatch.setattr(llm, "call", call)
    monkeypatch.setattr(llm, "unavailable", lambda *a, **k: None)
    uid = _listener("L")
    c = _client(uid, monkeypatch)
    c.post("/api/account/lang", json={"lang": "en"})
    assert _settled(uid)["result"]["left"] == ["和你常听的那几首一样慢"]
    n = len(calls)
    c.get("/api/state")
    assert len(calls) == n and not _settled(uid)["running"]
    with store.as_user(uid):   # a new edition's lines still are
        ed = store.read_json(store.EDITION)
        ed["lanes"][0]["when"] = "下班路上"
        store.write_json(store.EDITION, ed)
    c.get("/api/state")
    _settled(uid)
    assert len(calls) > n


def test_nothing_claude_wrote_for_the_sample_reads_as_the_other_language():
    # Chinese around English names, English quoting Chinese titles: each judged as the language it was written in
    assert i18n.written_in("Sergio Mendes with The Black Eyed Peas，《Mas Que Nada》", "zh-Hans") == "zh"
    root = Path(__file__).resolve().parents[1] / "demo"
    for f in sorted(root.rglob("*.json")):
        d = json.loads(f.read_text())
        for doc in d if isinstance(d, list) else [d]:
            if not isinstance(doc, dict) or "lang" not in doc:
                continue
            wrong = [t for t, _ in i18n._texts(doc) if i18n.written_in(t, doc["lang"]) not in (None, i18n.family(doc["lang"]))]
            assert not wrong, (f.name, wrong[:3])


def test_a_name_translated_one_way_comes_back_as_it_was_written(monkeypatch):
    from zhiyin import store
    uid = _listener("R")
    with store.as_user(uid):   # the edition took the profile's English name into Chinese; now read in English again
        store.write_json(store.TRANSLATIONS, {"zh-Hans": {"Night Groove": "夜色律动"}})
        assert i18n.localize("夜色律动", "zh-Hans", "en") == "Night Groove"
        assert i18n.localize("夜色律动", "zh-Hans", "zh-Hant") == "夜色律動"


def test_a_switch_left_hanging_by_a_restart_is_taken_up_on_the_next_visit(monkeypatch):
    from zhiyin import accounts
    calls = []
    _translator(monkeypatch, calls)
    uid = _listener("H")
    accounts.set_prefs(uid, lang_to="en")   # asked for, then the server restarted: no job, the page says "preparing"
    c = _client(uid, monkeypatch)
    c.get("/api/state")
    _settled(uid)
    assert accounts.prefs(uid)["lang"] == "en" and "lang_to" not in accounts.prefs(uid)


def test_another_language_picked_while_one_fails_is_the_one_that_happens(monkeypatch):
    from zhiyin import accounts, llm
    uid = _listener("A")

    def call(prompt, system, schema, **kw):
        accounts.set_prefs(uid, lang_to="zh-Hant")   # changed their mind while English was being prepared
        raise llm.LLMError("down")
    monkeypatch.setattr(llm, "call", call)
    monkeypatch.setattr(llm, "unavailable", lambda *a, **k: None)
    c = _client(uid, monkeypatch)
    c.post("/api/account/lang", json={"lang": "en"})
    assert not _settled(uid)["error"] and accounts.prefs(uid)["lang"] == "zh-Hant" and "lang_to" not in accounts.prefs(uid)


def test_a_taste_name_in_the_other_language_is_translated_not_replaced(monkeypatch):
    from zhiyin import accounts, llm, server, store
    monkeypatch.setattr(llm, "unavailable", lambda *a, **k: None)
    uid = _listener("N")
    accounts.set_prefs(uid, lang="en")
    with store.as_user(uid):
        server._want_label()
    assert (uid, "label") not in server._jobs
