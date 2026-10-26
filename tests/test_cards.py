import struct
import time

import pytest

from zhiyin import cards, ear, netease, server


def test_a_netease_link_is_read_whichever_way_it_was_copied():
    assert netease.parse("https://music.163.com/#/user/home?id=9003") == ("user", 9003)
    assert netease.parse("https://music.163.com/user/home?id=9003") == ("user", 9003)
    assert netease.parse("https://music.163.com/playlist?id=8009&userid=9003") == ("playlist", 8009)
    assert netease.parse("https://music.163.com/#/playlist?id=8009") == ("playlist", 8009)
    shared = "分享云音乐小秘书创建的歌单「云音乐小秘书喜欢的音乐」: https://y.music.163.com/m/playlist?id=8009&userid=9003 (来自@网易云音乐)"
    assert netease.parse(shared) == ("playlist", 8009)
    for bad in ("hello", "https://music.163.com/#/song?id=1", "https://evil.example/?u=music.163.com/playlist?id=1",
                "https://music.163.com.evil.example/playlist?id=1"):
        with pytest.raises(netease.Unreadable) as e:
            netease.parse(bad)
        assert e.value.why == "link"


def _song(i, year=2015):
    return {"id": i, "name": f"Song {i}", "ar": [{"name": f"Artist {i % 7}"}], "al": {"name": "Album", "picUrl": f"https://p1.music.126.net/{i}.jpg"},
            "dt": 200000, "publishTime": int(time.mktime((year, 6, 1, 0, 0, 0, 0, 0, 0)) * 1000), "pop": 40 + i % 41}


def _fake(monkeypatch, n, code=200, gone=()):
    at0 = int(time.mktime((2016, 1, 10, 0, 0, 0, 0, 0, 0)) * 1000)
    refs = [{"id": i, "at": at0 + i * 9 * 86400 * 1000} for i in range(1, n + 1)]

    def get(c, path, **params):
        if path == "/api/user/playlist":
            return {"code": 200, "playlist": [{"id": 77, "specialType": 5, "creator": {"userId": params["uid"]}}]}
        return {"code": code, "playlist": {"trackIds": refs} if code == 200 else None}
    monkeypatch.setattr(netease, "_get", get)
    monkeypatch.setattr(netease, "_songs", lambda c, ids: {i: _song(i) for i in ids if i not in gone})


def test_likes_come_newest_first_and_skip_songs_netease_took_down(monkeypatch):
    _fake(monkeypatch, 40, gone={3})
    got = netease.likes("https://music.163.com/#/user/home?id=5")
    assert got["key"] == "163:77" and got["total"] == 40
    assert [t["vid"] for t in got["tracks"][:2]] == ["n40", "n39"] and "n3" not in {t["vid"] for t in got["tracks"]}
    assert [t["rank"] for t in got["tracks"]] == list(range(39))
    assert got["tracks"][0]["year"] == 2015 and got["tracks"][-1]["liked_est"].startswith("2016-01")


def test_a_hidden_or_short_list_says_why(monkeypatch):
    _fake(monkeypatch, 40, code=401)
    with pytest.raises(netease.Unreadable) as e:
        netease.likes("https://music.163.com/playlist?id=1")
    assert e.value.why == "private"
    _fake(monkeypatch, 12)
    with pytest.raises(netease.Unreadable) as e:
        netease.likes("https://music.163.com/playlist?id=1")
    assert (e.value.why, e.value.n) == ("few", 12)


def test_a_netease_record_is_laid_out_like_a_new_listeners(monkeypatch):
    _fake(monkeypatch, 60)
    rec = ear.from_tracks(netease.likes("https://music.163.com/playlist?id=1")["tracks"], "zh-Hans")
    assert len(rec["songs"]) == 60 and rec["sectors"] == [] and rec["real_dates"]
    assert int(rec["span"][0]) == 2016 and rec["center"] == 2015
    assert {"first", "center"} <= {f["key"] for f in rec["facts"]}


def _jpeg(w=1080, h=1440) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def test_only_a_card_sized_jpeg_is_taken():
    assert cards.jpeg_size(_jpeg()) == (1080, 1440)
    assert cards.valid_image(_jpeg())
    assert not cards.valid_image(_jpeg(1200, 630))
    assert not cards.valid_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)


def test_a_token_carries_what_the_server_said_and_nothing_else():
    tok = cards.sign({"label": "粤语慢歌", "exp": time.time() + 60, "nonce": "a"})
    assert cards.unsign(tok)["label"] == "粤语慢歌"
    body, mac = tok.split(".")
    assert cards.unsign(body[:-2] + "xx." + mac) is None
    assert cards.unsign(cards.sign({"label": "x", "exp": time.time() - 1, "nonce": "b"})) is None


def test_a_card_made_without_an_account_shares_once_and_comes_down_by_its_key(monkeypatch):
    from fastapi.testclient import TestClient
    _fake(monkeypatch, 50)
    monkeypatch.setattr(cards, "verdict", lambda *a, **k: ("钢琴和雨天", "七首德彪西轮着放，雨都被你听停了。"))
    c = TestClient(server.app, headers={"Accept-Language": "zh-CN"})
    r = c.post("/api/card/make", json={"link": "https://music.163.com/playlist?id=5"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["label"] == "钢琴和雨天" and d["n"] == 50 and len(d["pics"]) == 50
    assert d["roast"].startswith("七首") and d["pop"] == round(sum(40 + i % 41 for i in range(1, 51)) / 50) and d["facts"][0]["key"] == "pop"
    bad = c.post("/api/card/make", json={"link": "https://example.com/"})
    assert bad.status_code == 422 and "网易云" in bad.json()["detail"]

    assert c.post(f"/api/card/share?token={d['token']}", content=_jpeg(800, 600)).status_code == 400
    s = c.post(f"/api/card/share?token={d['token']}", content=_jpeg())
    assert s.status_code == 200, s.text
    link = s.json()
    assert link["url"].endswith(f"/c/{link['id']}")
    assert c.post(f"/api/card/share?token={d['token']}", content=_jpeg()).status_code == 403   # one link per card

    page = c.get(f"/c/{link['id']}")
    assert page.status_code == 200 and 'property="og:title" content="钢琴和雨天"' in page.text
    assert 'content="「七首德彪西轮着放，雨都被你听停了。」让 Claude' in page.text
    assert f"/c/{link['id']}.jpg" in page.text and "__" not in page.text
    assert c.get(f"/c/{link['id']}.jpg").content == _jpeg()
    bare = TestClient(server.app).get(f"/c/{link['id']}", headers={"accept-language": ""})
    assert "<title>钢琴和雨天 · 知音</title>" in bare.text and '<html lang="zh-Hans">' in bare.text

    assert c.post("/api/card/delete", json={"id": link["id"], "key": "wrong"}).status_code == 404
    assert c.post("/api/card/delete", json={"id": link["id"], "key": link["key"]}).status_code == 200
    assert c.get(f"/c/{link['id']}").status_code == 404
    assert c.get(f"/c/{link['id']}.jpg").status_code == 404


def test_a_name_for_a_playlist_is_kept_for_the_day_and_tries_are_counted(monkeypatch):
    _fake(monkeypatch, 30)
    names = iter(["一", "二", "三", "四"])
    monkeypatch.setattr(cards, "verdict", lambda *a, **k: (next(names), "roast"))
    link = "https://music.163.com/playlist?id=9"
    assert cards.make(link, "zh-Hans")["label"] == "一"
    assert cards.make(link, "zh-Hans")["label"] == "一"           # the same list again: no new call
    assert cards.make(link, "zh-Hans", again=True)["label"] == "二"
    assert cards.make(link, "zh-Hans", again=True)["label"] == "三"
    last = cards.make(link, "zh-Hans", again=True)
    assert last["label"] == "三" and last["why"]                   # three names a day for one list


def test_deleting_an_account_takes_its_shared_cards_down():
    from zhiyin import accounts
    uid = accounts.redeem(accounts.invite("Lin"))
    mine = cards.save(_jpeg(), "x", "zh-Hans", 30, 2019, uid, None)
    theirs = cards.save(_jpeg(), "y", "zh-Hans", 30, 2019, None, "n-keep")
    accounts.delete(uid)
    assert cards.get(mine["id"]) is None and not (cards.DIR / f"{mine['id']}.jpg").exists()
    assert cards.get(theirs["id"])


def test_the_operator_can_take_down_a_card_nobody_signed_in_made(monkeypatch):
    import sys
    from zhiyin import cli
    c = cards.save(_jpeg(), "x", "zh-Hans", 30, 2019, None, "n-op")
    assert not cards.remove(c["id"])
    monkeypatch.setattr(sys, "argv", ["zhiyin", "cards", "--rm", c["id"]])
    cli.main()
    assert cards.get(c["id"]) is None


def test_the_roast_is_asked_with_the_numbers_it_may_lean_on(monkeypatch):
    from zhiyin import llm
    _fake(monkeypatch, 40)
    seen = {}

    def call(prompt, system, schema, **k):
        seen.update(prompt=prompt, system=system, model=k.get("model"))
        return {"label": "周杰倫的回頭客", "roast": "《晴天》存了三個版本。"}
    monkeypatch.setattr(llm, "call", call)
    tracks = netease.likes("https://music.163.com/playlist?id=3")["tracks"]
    label, roast = cards.verdict(tracks, 40, "zh-Hans")
    assert (label, roast) == ("周杰伦的回头客", "《晴天》存了三个版本。")     # the likes' script doesn't leak into the card
    assert seen["model"] == "haiku" and "大众度" in seen["prompt"] and "Most liked artists: Artist" in seen["prompt"]
    assert "roast" in seen["system"] and "@" not in seen["system"]
