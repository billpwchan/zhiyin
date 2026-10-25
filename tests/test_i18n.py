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
    b = accounts.redeem(accounts.invite("B", mine=True))
    for uid in (a, b):
        with store.as_user(uid):
            store.write_json(store.PROFILE, {"lang": "zh-Hans", "lanes": [], "portrait": {"headline": "从〈后来〉开始的听感", "paragraphs": []}})
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(b))
    r = c.post("/api/account/lang", json={"lang": "zh-Hant"}, headers={"X-Zhiyin-Uid": b})
    assert r.status_code == 200 and r.cookies.get(i18n.COOKIE) == "zh-Hant"
    assert accounts.prefs(b)["lang"] == "zh-Hant" and accounts.prefs(a).get("lang") != "zh-Hant"
    st = c.get("/api/state").json()
    assert st["me"]["lang"] == "zh-Hant" and st["portrait"]["headline"] == "從〈后来〉開始的聽感"
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
