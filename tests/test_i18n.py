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
