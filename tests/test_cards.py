import struct
import time

import pytest

from zhiyin import cards, ear, library, netease, qqmusic, server


def test_a_netease_link_is_read_whichever_way_it_was_copied():
    assert netease.parse("https://music.163.com/#/user/home?id=9003") == ("user", 9003)
    assert netease.parse("https://music.163.com/user/home?id=9003") == ("user", 9003)
    assert netease.parse("https://music.163.com/playlist?id=8009&userid=9003") == ("playlist", 8009)
    assert netease.parse("https://music.163.com/#/playlist?id=8009") == ("playlist", 8009)
    shared = "分享云音乐小秘书创建的歌单「云音乐小秘书喜欢的音乐」: https://y.music.163.com/m/playlist?id=8009&userid=9003 (来自@网易云音乐)"
    assert netease.parse(shared) == ("playlist", 8009)
    for bad in ("hello", "https://evil.example/?u=music.163.com/playlist?id=1", "https://music.163.com.evil.example/playlist?id=1"):
        with pytest.raises(netease.Unreadable) as e:
            netease.parse(bad)
        assert e.value.why == "link"
    with pytest.raises(netease.Unreadable) as e:   # the song playing, shared instead of the likes
        netease.parse("https://music.163.com/#/song?id=1")
    assert (e.value.why, e.value.app) == ("song", "163")


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



class _Hops:
    """A short link's redirect, without the network."""
    def __init__(self, to):
        self.to = to

    def get(self, url):
        return type("R", (), {"headers": {"location": self.to}})()


def test_a_qq_music_link_is_read_whichever_way_it_was_copied():
    me = "oKcPoKoP7i4soz**"
    assert qqmusic.parse(f"https://i.y.qq.com/n2/m/share/profile_v2/index.html?ADTAG=wxfshare&encrypt_uin={me}") == ("user", me)
    assert qqmusic.parse("https://i2.y.qq.com/n3/other/pages/share/profile_v2/index.html?userid=7eE57ivP7wn*") == ("user", "7eE57ivP7wn*")
    assert qqmusic.parse("https://y.qq.com/n/ryqq/profile/like/song?uin=NKSl7e-iNe-i") == ("user", "NKSl7e-iNe-i")
    assert qqmusic.parse("https://y.qq.com/n/ryqq/playlist/7256912512") == ("playlist", 7256912512)
    shared = f"分享歌单「夜里」: https://i.y.qq.com/n2/m/share/details/taoge.html?platform=11&id=7256912512&hosteuin={me} @QQ音乐"
    assert qqmusic.parse(shared) == ("playlist", 7256912512)
    short = "https://c6.y.qq.com/base/fcgi-bin/u?__=Ab3dEf"
    assert qqmusic.parse(short, _Hops(f"https://i.y.qq.com/n2/m/share/profile_v2/index.html?encrypt_uin={me}")) == ("user", me)
    with pytest.raises(netease.Unreadable) as e:   # a short link may only lead on within QQ Music
        qqmusic.parse(short, _Hops("https://evil.example/n2/m/share/profile_v2/index.html?encrypt_uin=x"))
    assert e.value.why == "link"
    for song in ("https://y.qq.com/n/ryqq/songDetail/002q83Sd2G7Y7D", "https://i.y.qq.com/v8/playsong.html?songmid=002q83Sd2G7Y7D"):
        with pytest.raises(netease.Unreadable) as e:
            qqmusic.parse(song)
        assert (e.value.why, e.value.app) == ("song", "qq")
    for bad in ("https://y.qq.com.evil.example/n/ryqq/playlist/1", "https://evil.example/?u=https://y.qq.com/n/ryqq/playlist/1",
                "https://y.qq.com/n/ryqq/profile?uin=12345678"):   # a bare QQ number: only the encrypted id is read
        with pytest.raises(netease.Unreadable) as e:
            qqmusic.parse(bad)
        assert e.value.why == "link"
    assert [library.app_of(x) for x in (shared, "https://music.163.com/playlist?id=1", "hello")] == ["qq", "163", "163"]
    assert qqmusic.parse(qqmusic.link_of(f"qq:u:{me}")) == ("user", me)
    assert qqmusic.parse(qqmusic.link_of("qq:p:7256912512")) == ("playlist", 7256912512)


def _qsong(i, year=2015):
    return {"id": i, "mid": f"00{i:08d}", "name": f"Song {i}", "title": f"Song {i}", "interval": 200,
            "time_public": f"{year}-06-01", "singer": [{"mid": f"S{i % 7:07d}", "name": f"Singer {i % 7}"}],
            "album": {"mid": f"A{i:08d}", "name": "Album"}}


def _qfake(monkeypatch, songs, title="我喜欢", total=None, ctime=1356998400, mtime=1790000000):
    asked = []

    def diss(c, which, begin):
        asked.append((dict(which), begin))
        part = songs[begin:begin + qqmusic.PAGE]
        if total == 0:
            return {"code": -100006, "dirinfo": {"id": 0, "title": ""}, "total_song_num": 0, "songlist": []}
        return {"dirinfo": {"id": 2725367359, "title": title, "ctime": ctime, "mtime": mtime},
                "total_song_num": len(songs) if total is None else total, "songlist": part,
                "hasmore": int(begin + qqmusic.PAGE < len(songs))}
    monkeypatch.setattr(qqmusic, "_diss", diss)
    return asked


def test_qq_likes_come_newest_first_from_every_page_with_dates_no_earlier_than_the_songs(monkeypatch):
    years = [2025, 2026, 2024, 2023] + [2010] * 1100 + [2008] * 96   # newest like first
    songs = [_qsong(i, y) for i, y in enumerate(years)]
    asked = _qfake(monkeypatch, songs)
    got = qqmusic.likes("https://i.y.qq.com/n2/m/share/profile_v2/index.html?encrypt_uin=oKcPoKoP7i4soz**")
    assert asked == [({"disstid": 0, "dirid": 201, "enc_host_uin": "oKcPoKoP7i4soz**"}, 0),
                     ({"disstid": 0, "dirid": 201, "enc_host_uin": "oKcPoKoP7i4soz**"}, 1000)]
    assert got["key"] == "qq:u:oKcPoKoP7i4soz**" and got["total"] == 1200 and len(got["tracks"]) == 1200
    t0 = got["tracks"][0]
    assert (t0["vid"], t0["source"], t0["ne_ar"], t0["pop"]) == ("q0000000000", "qq", ["S0000000"], None)
    assert t0["pic"] == "https://y.gtimg.cn/music/photo_new/T002R300x300M000A00000000.jpg"
    # the second newest release at or below each like; the list began in 2013, so nothing is dated before it
    assert [t["liked_est"][:4] for t in got["tracks"][:4]] == ["2025", "2024", "2023", "2013"]
    assert got["tracks"][-1]["liked_est"][:4] == "2013"
    rec = ear.from_tracks(got["tracks"], "zh-Hans")
    assert not rec["real_dates"]                           # the page says "around 2019", not a month


def test_a_hidden_short_or_missing_qq_list_says_why(monkeypatch):
    link = "https://y.qq.com/n/ryqq/playlist/7256912512"
    for songs, title, total, why in (([], "歌单被主人设为隐私", 63, "private"), ([_qsong(i) for i in range(5)], "我喜欢", None, "few"),
                                     ([], "", 0, "link")):
        _qfake(monkeypatch, songs, title, total)
        with pytest.raises(netease.Unreadable) as e:
            qqmusic.likes(link)
        assert (e.value.why, e.value.app) == (why, "qq")
    msg = server._why(netease.Unreadable("private", app="qq"), "zh-Hans")
    assert "访问设置" in msg and "网易云" not in msg
    assert "网易云" in server._why(netease.Unreadable("private"), "zh-Hans")


def test_a_qq_card_is_named_as_qq_music_and_has_no_popularity(monkeypatch):
    from zhiyin import llm
    _qfake(monkeypatch, [_qsong(i, year=2000 + i % 20) for i in range(40)])
    seen = {}

    def call(prompt, system, schema, **k):
        seen.update(prompt=prompt, system=system)
        return {"label": "老歌回收站", "roast": "一半的歌比你的手机还老。"}
    monkeypatch.setattr(llm, "call", call)
    monkeypatch.setattr(llm, "unavailable", lambda *a, **k: None)
    rec = cards.make("https://y.qq.com/n/ryqq/playlist/7256912512", "zh-Hans")
    assert rec["source"] == "qq" and rec["pop"] is None and "pop" not in {f["key"] for f in rec["facts"]}
    assert "QQ Music" in seen["system"] and "NetEase" not in seen["system"] and "大众度" not in seen["prompt"]
    # its like dates are estimates: the rows carry the year each song came out, and no date is offered as a like's
    assert "doesn't show when a song was liked" in seen["system"] and "month of each like" not in seen["system"]
    assert "2000 | Song 0 | Singer 0" in seen["prompt"] and "first liked" not in seen["prompt"]
    # and the record places each song where it came out, so it says nothing of a first like or a year they start from
    assert rec["dates"] == "released" and int(rec["span"][0]) == 2000 and int(rec["span"][1]) == 2019
    facts = {f["key"]: f for f in rec["facts"]}
    assert facts["first"]["text"].startswith("最老的一首是《Song ") and facts["first"]["lead"] == "2000" and "longest" not in facts
    assert cards.unsign(rec["token"])["since"] == 0
    assert rec["pics"]["q0000000001"].startswith("https://y.gtimg.cn/")


def test_qq_singers_other_names_include_the_ones_inside_their_name():
    assert qqmusic.name_parts("华莎 (화사)") == ["华莎", "화사"]
    assert qqmusic.name_parts("G.E.M.邓紫棋") == ["G.E.M.", "邓紫棋"]
    assert qqmusic.name_parts("陈奕迅") == []


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


def test_a_name_kept_from_before_roasts_is_written_again_with_one(monkeypatch):
    import hashlib
    from zhiyin import store
    _fake(monkeypatch, 30)
    k = hashlib.sha256("163:77|zh-Hans".encode()).hexdigest()[:24]
    con = store.db()
    con.execute("insert or replace into card_names(k, label, day, rolls) values (?, '旧名字', ?, 1)", (k, time.strftime("%Y-%m-%d")))
    con.commit()
    monkeypatch.setattr(cards, "verdict", lambda *a, **k: ("新名字", "一句锐评"))
    got = cards.make("https://music.163.com/#/user/home?id=5", "zh-Hans")
    assert (got["label"], got["roast"]) == ("新名字", "一句锐评")


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
    assert "roast" in seen["system"] and "@" not in seen["system"] and "month of each like" in seen["system"]


def test_a_roast_too_long_for_the_card_is_asked_again_then_cut_at_a_sentence(monkeypatch):
    from zhiyin import llm
    _fake(monkeypatch, 40)
    long = "James Bay 十三首，Ed Sheeran 七首，2017 年 3 月一口气存了一大把。之后就再没出来过，耳朵停在 2017，像是路过顺手点了个赞。"
    calls = []

    def call(prompt, system, schema, **k):
        calls.append(prompt)
        return {"label": "停在2017", "roast": long}
    monkeypatch.setattr(llm, "call", call)
    tracks = netease.likes("https://music.163.com/playlist?id=3")["tracks"]
    label, roast = cards.verdict(tracks, 40, "zh-Hans")
    assert len(calls) == 3 and "too long" in calls[-1]
    assert roast == "James Bay 十三首，Ed Sheeran 七首，2017 年 3 月一口气存了一大把。"


def test_qq_covers_pass_through_only_as_covers_and_on_each_visitors_own_allowance(monkeypatch):
    from zhiyin import ytm
    u = "https://y.gtimg.cn/music/photo_new/T002R90x90M000002q83Sd2G7Y7D.jpg"
    assert ytm.passed(u)
    for bad in ("https://y.gtimg.cn/music/photo_new/../../x", "https://y.gtimg.cn:8443/music/photo_new/T002R90x90M000002q83Sd2G7Y7D.jpg",
                "http://y.gtimg.cn/music/photo_new/T002R90x90M000002q83Sd2G7Y7D.jpg", u + "?x=1", "https://y.gtimg.cn/other.jpg"):
        assert not ytm.passed(bad)
        with pytest.raises(ValueError):
            ytm.cover_bytes(bad)
    monkeypatch.setattr(server, "_passed", {})
    monkeypatch.setattr(server, "PASS_PER_IP", 3)
    shared = list(server._sample_fetched["img"])
    assert [server._sample_may_fetch("/api/img", {"u": u}, "1.1.1.1") for _ in range(4)] == [True, True, True, False]
    assert server._sample_may_fetch("/api/img", {"u": u}, "2.2.2.2")   # another visitor's record isn't held up
    assert server._sample_fetched["img"] == shared                       # nor anyone's YouTube covers


def _qq_profile(monkeypatch):
    lists = {201: ("我喜欢", ["a"]), 1: ("2016前我喜欢", ["a", "b"]), 2: ("新建歌单", []), 3: ("always", ["c"]),
             202: ("的今日私享", ["z"])}
    asked = []

    def song(m, title=None):
        return {"mid": m, "title": title or m.upper(), "singer": [{"name": "S", "mid": "sm0001"}], "time_public": "2015-01-02"}

    def diss(c, which, begin, num=qqmusic.PAGE):
        if which["disstid"]:   # a playlist someone else made, kept on the profile
            return {"dirinfo": {"id": which["disstid"]}, "total_song_num": 3, "songlist": [song("c"), song("d"), song("e")][:num]}
        asked.append(which["dirid"])
        title, mids = lists.get(which["dirid"], ("", []))
        return {"dirinfo": {"id": 1, "title": title, "ctime": 1450000000, "mtime": 1460000000} if title else {},
                "total_song_num": len(mids), "hasmore": 0, "songlist": [song(m) for m in mids]}

    def call(c, module, method, param):
        if method == "CgiGetPlaylistFavInfo":
            assert param["uin"] == "euin**"
            return {"hasmore": 0, "v_list": [{"tid": 9, "name": "唱见の治愈歌声", "nickname": "凌舟", "orderTime": 1594339200},
                                             {"tid": 8, "name": "", "songnum": 0}]}   # taken down by its maker
        if method == "CgiGetAlbumFavInfo":
            return {"hasmore": 0, "v_list": [{"mid": "al1", "name": "那么骄傲", "v_singer": [{"name": "伯远"}],
                                              "pubtime": 1638201600, "ordertime": 1638203481}]}
        assert method == "GetAlbumSongList" and param["albumMid"] == "al1"
        return {"songList": [{"songInfo": {"mid": "f", "title": "那么骄傲", "singer": [{"name": "伯远", "mid": "by01"}]}},
                             {"songInfo": {"mid": "g", "title": "那么骄傲 (伴奏)", "singer": [{"name": "伯远", "mid": "by01"}]}}]}
    monkeypatch.setattr(qqmusic, "parse", lambda text, c=None: ("user", "euin**"))
    monkeypatch.setattr(qqmusic, "_diss", diss)
    monkeypatch.setattr(qqmusic, "_call", call)
    monkeypatch.setattr(qqmusic, "aliases", lambda mid: ["에스"] if mid == "sm0001" else [])
    return asked


def test_every_list_on_a_qq_profile_is_read_their_own_until_the_numbers_run_out(monkeypatch):
    asked = _qq_profile(monkeypatch)
    got = qqmusic.lists("https://c6.y.qq.com/base/fcgi-bin/u?__=x")
    assert [(x["title"], x["kind"], x["n"]) for x in got["lists"]] == [
        ("我喜欢", "likes", 1), ("2016前我喜欢", "own", 2), ("always", "own", 1), ("唱见の治愈歌声", "saved", 3), ("那么骄傲", "album", 1)]
    assert got["lists"][1]["at"] < got["lists"][1]["changed"] and got["lists"][3]["by"] == "凌舟" and got["lists"][4]["by"] == "伯远"
    assert {s["title"]: s["lists"] for s in got["songs"]} == {"A": [0, 1], "B": [1], "C": [2, 3], "D": [3], "E": [3], "那么骄傲": [4]}
    assert got["songs"][0]["aka"] == ["에스"] and got["songs"][0]["released"] == "2015-01-02"
    assert got["songs"][-1]["released"] == "2021-11-30"   # an album's songs come out with it; its karaoke track is left out
    assert 202 not in asked and max(asked[1:]) == 3 + qqmusic.FOLDER_GAP   # QQ Music's own lists are never read
    asked.clear()
    rest = qqmusic.lists("https://c6.y.qq.com/base/fcgi-bin/u?__=x", likes=False)   # their likes are read on their own
    assert 201 not in asked and [x["title"] for x in rest["lists"]][0] == "2016前我喜欢"


def test_every_playlist_on_a_netease_profile_is_read_theirs_and_the_ones_they_keep(monkeypatch):
    def get(c, path, **params):
        if path == "/api/user/playlist":
            assert params["uid"] == 5
            return {"code": 200, "playlist": [
                {"id": 77, "specialType": 5, "trackCount": 2, "creator": {"userId": 5}, "name": "Lin喜欢的音乐"},
                {"id": 78, "specialType": 0, "trackCount": 2, "creator": {"userId": 5}, "name": "写作业", "createTime": 1450000000000},
                {"id": 79, "specialType": 0, "trackCount": 0, "creator": {"userId": 5}, "name": "新建歌单"},
                {"id": 80, "specialType": 0, "trackCount": 1, "creator": {"userId": 6, "nickname": "小秘书"}, "name": "华语私藏"}]}
        ids = {77: [1, 2], 78: [2, 3, 3], 80: [4]}[params["id"]]
        return {"code": 200, "playlist": {"trackIds": [{"id": i} for i in ids]}}
    monkeypatch.setattr(netease, "_get", get)
    monkeypatch.setattr(netease, "_songs", lambda c, ids: {i: _song(i) for i in ids})
    monkeypatch.setattr(netease, "aliases", lambda aid: [])
    got = netease.lists(5, likes=False)
    assert got["key"] == "163:u:5"
    assert [(x["title"], x["kind"], x["by"], x["n"]) for x in got["lists"]] == [("写作业", "own", None, 2), ("华语私藏", "saved", "小秘书", 1)]
    assert {s["title"]: s["lists"] for s in got["songs"]} == {"Song 2": [0], "Song 3": [0], "Song 4": [1]}
    assert got["lists"][0]["at"].startswith("2015-12") and got["lists"][1]["at"] is None


def test_a_listeners_own_card_page_opens_with_the_portraits_headline():
    from fastapi.testclient import TestClient
    c = cards.save(_jpeg(), "方大同和 Gareth.T 的常客", "zh-Hant", 856, 2016, "owner", None, line="5年換了5種主打語言，今年輪到日文")
    page = TestClient(server.app, headers={"Accept-Language": "zh-TW"}).get(f"/c/{c['id']}")
    assert 'content="「5 年換了 5 種主打語言，今年輪到日文」856 首喜歡' in page.text
