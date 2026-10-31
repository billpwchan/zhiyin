import pytest
import random
import time

from fastapi.testclient import TestClient

from zhiyin import candidates, edition, quality, server, signals, store

DAY = 86400


def play(uid, vid, ts, ev, pos=0, **kw):
    cols = {"vid": vid, "lane": kw.pop("lane", "a"), "ts": ts, "ev": ev, "pos": pos, "uid": uid, **kw}
    con = store.db()
    con.execute(f"insert into plays ({', '.join(cols)}) values ({', '.join('?' * len(cols))})", list(cols.values()))
    con.commit()


def listen(uid, vid, ts, end="done", pos=200, dur=200, src="pick", test=0, **kw):
    play(uid, vid, ts, "start", 0, src=src, dur=dur, test=test, **kw)
    play(uid, vid, ts + max(pos, 1), end, pos, dur=dur, idle=5, test=test)


def test_chosen_and_heard_through_on_three_days_is_a_love_and_one_day_of_repeats_is_not():
    now = time.time()
    with store.as_user("sig1"):
        for d in (1, 4, 9):
            listen("sig1", "love0000001", now - d * DAY)
        for k in range(5):   # five times in one evening
            listen("sig1", "binge000001", now - 2 * DAY + k * 300)
        for d in (1, 4, 9):   # heard through, but it only played on
            listen("sig1", "auto0000001", now - d * DAY + 3600, src="auto")
        s = signals.play_scores(signals.listens())
    assert s["love0000001"]["w"] >= signals.LOVE and s["love0000001"]["days"] == 3
    assert s["binge000001"]["w"] < signals.LOVE
    assert s["auto0000001"]["w"] < signals.LOVE


def test_a_lone_early_skip_refuses_the_sound_but_a_run_of_skips_is_about_the_moment():
    now = time.time()
    with store.as_user("sig2"):
        listen("sig2", "lone0000001", now - 5000, end="skip", pos=4)
        for k, v in enumerate(("run00000001", "run00000002", "run00000003")):
            listen("sig2", v, now - 3000 + k * 20, end="skip", pos=5)
        listen("sig2", "late0000001", now - 1000, end="skip", pos=22)   # left at 22 s: not now, not "never"
        listen("sig2", "test0000001", now - 500, end="skip", pos=2, test=1)
        got = signals.lone_early_skips(signals.listens())
    assert got == {"lone0000001"}


def test_listens_join_each_start_to_its_end_and_a_checkpoint_does_not_end_it():
    now = time.time()
    with store.as_user("sig3"):
        play("sig3", "away0000001", now - 100, "start", src="station", dur=240, fit=0.85, slot=2, fam=0)
        play("sig3", "away0000001", now - 60, "away", 40, dur=240)
        play("sig3", "away0000001", now - 50, "replay", 41)
        ls = signals.listens()
    assert len(ls) == 1 and ls[0]["end"] is None and ls[0]["pos"] == 40 and ls[0]["replays"] == 1
    assert (ls[0]["fit"], ls[0]["slot"], ls[0]["fam"]) == (0.85, 2, 0)


def test_known_keeps_out_youtube_dislikes_playlist_songs_and_history_and_knows_followed_artists():
    with store.as_user("sig4"):
        store.write_json(store.SIGNALS, {
            "read": time.time(),
            "disliked": [{"vid": "dis00000001", "title": "Bad Song", "artist": "Loud Band"}],
            "follows": [{"id": "UCfollowed", "name": "Quiet Singer"}],
            "saved": [{"vid": "sav00000001", "title": "Kept Song", "artist": "Someone", "at": "2026-01-01"}]})
        store.write_json(store.HISTORY, {"at": time.time(), "songs": {
            "his00000001": {"n": 5, "days": 4, "first": "2025-01-01", "last": "2026-01-01", "rw": 2.0, "title": "Old Favourite", "artist": "Band"}}})
        k = candidates.Known([], {})

        def t(vid, title, artist, aid=None):
            return {"vid": vid, "title": title, "artists": [{"name": artist, "id": aid}]}
        assert k.reject(t("dis00000001", "x", "y")) == "feedback"
        assert k.reject(t("dis00000002", "Bad Song", "Loud Band")) == "feedback"   # another upload of it
        assert k.reject(t("sav00000001", "x", "y")) == "liked"
        assert k.reject(t("sav00000002", "Kept Song", "Someone")) == "same song"
        assert k.reject(t("his00000001", "x", "y")) == "heard"
        assert k.reject(t("his00000002", "Old Favourite", "Band")) == "same song"
        assert k.artist_known([{"id": "UCfollowed", "name": "Whatever"}]) == "follow"
        assert not k.is_new([{"id": None, "name": "Quiet Singer"}]) and k.is_new([{"id": None, "name": "Stranger"}])
        assert candidates.is_new({"familiar": 0, "knows": None}) and not candidates.is_new({"familiar": 0, "knows": "follow"})


def test_loves_get_their_station_from_where_they_played_seed_it_and_never_stand_in_for_a_like(monkeypatch):
    now = time.time()
    meta = {"love0000002": {"vid": "love0000002", "title": "Night Drive", "artists": [{"name": "Neon", "id": "UCneon"}], "type": "ATV", "dur": 210},
            "liked000001": {"vid": "liked000001", "title": "Mine", "artists": [{"name": "Me", "id": None}], "type": "ATV", "dur": 200}}
    monkeypatch.setattr(signals.ytm, "track", lambda v: meta.get(v))
    monkeypatch.setattr(signals.llm, "unavailable", lambda uid=None: "no claude in tests")
    with store.as_user("sig5"):
        store.write_json(store.LIBRARY, {"tracks": [{"rank": 0, "vid": "liked000001", "title": "Mine", "artists": [{"name": "Me", "id": None}],
                                                     "type": "ATV", "long": False, "liked_est": None}]})
        for d in (1, 3, 6):
            listen("sig5", "love0000002", now - d * DAY, lane="night")
            listen("sig5", "liked000001", now - d * DAY + 900, lane="night")
        prof = {"lanes": [{"key": "night"}], "assign": {}}
        loves = signals.refresh(prof, log=lambda *_: None)
        assert [r["vid"] for r in loves] == ["love0000002"] and loves[0]["lane"] == ["night"]
        assert [r["vid"] for r in signals.loves()] == ["love0000002"]
        lane = {"key": "night", "seeds": [], "core_artists": []}
        seeds = candidates.lane_seeds(lane, [], prof, random.Random(1), loves=loves)
        assert [s["vid"] for s in seeds] == ["love0000002"] and seeds[0]["implicit"]
        assert edition.because({"like_vid": "love0000002", "via": []}, seeds) is None
        k = candidates.Known([], prof)
        assert k.artist_known([{"id": "UCneon", "name": "Neon"}]) == "plays"
        assert k.reject({"vid": "love0000003", "title": "Night Drive", "artists": [{"name": "Neon", "id": None}]}) == "same song"
        from zhiyin import settings
        settings.set_not_me(vid="love0000002")   # "Not me": gone from the loves, still listed so it can be put back
        assert signals.refresh(prof, log=lambda *_: None) == [] and signals.loves() == []
        assert "love0000002" in store.read_json(store.IMPLICIT)["meta"]


def test_quality_counts_first_listens_by_confidence_and_probe():
    now = time.time()
    with store.as_user("sig6"):
        listen("sig6", "good0000001", now - 900, fit=0.92, slot=0, fam=0)
        listen("sig6", "good0000001", now - 100, fit=0.92, slot=0, fam=0, end="skip", pos=3)   # only the first counts
        listen("sig6", "skip0000001", now - 800, end="skip", pos=4, fit=0.75, slot=4, fam=1)
        listen("sig6", "prob0000001", now - 700, fit=0.6, slot=3, fam=0, probe="low")
        listen("sig6", "mine0000001", now - 600, src="compare")   # their own like, played side by side
        r = quality.report(14)
    g = r["groups"]
    assert g["all"]["all"]["n"] == 3 and g["all"]["all"]["good"] == 2 and g["all"]["all"]["early"] == 1
    assert g["fit"]["0.9+"]["good"] == 1 and g["fit"]["0.7-0.8"]["early"] == 1 and g["fit"]["probe"]["n"] == 1
    assert g["arm"]["probe:low"]["n"] == 1 and g["arm"]["editor"]["n"] == 2
    assert g["artist"]["new"]["n"] == 2 and g["artist"]["liked"]["n"] == 1


def song(vid, fit, artist=None):
    return {"vid": vid, "fit": fit, "artists": [{"name": artist or vid, "id": None}]}


def test_a_probe_goes_among_the_picks_never_first_and_only_in_a_full_station():
    picks = [song(f"p{i}", 0.9) for i in range(6)] + [song("cut", 0.79), song("same", 0.6, "p1"), song("low", 0.6)]
    for seed in range(8):
        chosen = [dict(p) for p in picks[:6]]
        reserve = [dict(p) for p in picks[6:]] + [song("graph", 0)]
        edition.probe({"key": "a"}, chosen, reserve, picks, random.Random(seed))
        added = [p for p in chosen if p.get("probe")]
        assert len(added) == 1 and chosen.index(added[0]) >= 2 and added[0] not in reserve
        # one the editor rated above the bar, or by an artist already in the station, is no test of the editor
        assert added[0]["vid"] in ("low", "graph") and added[0]["probe"] == ("low" if added[0]["vid"] == "low" else "graph")
    few = [dict(p) for p in picks[:3]]
    edition.probe({"key": "a"}, few, [song("graph", 0)], few, random.Random(3))
    assert not any(p.get("probe") for p in few)


def test_leaving_early_without_next_is_no_verdict_on_the_song():
    now = time.time()
    with store.as_user("sig7"):
        listen("sig7", "stop0000001", now - 5000, end="stop", pos=3)    # changed station 3 s in
        listen("sig7", "skip0000002", now - 3000, end="skip", pos=3)    # pressed Next 3 s in
        listen("sig7", "test0000003", now - 2000, end="done", test=1)   # an automated check
        ls = signals.listens()
        assert [x["end"] for x in ls] == ["stop", "skip"]
        assert signals.refused() == {"skip0000002"}
        k = candidates.Known([], {})
        assert k.reject({"vid": "stop0000001", "title": "a", "artists": [{"name": "b", "id": None}]}) is None
        assert k.reject({"vid": "test0000003", "title": "c", "artists": [{"name": "d", "id": None}]}) is None
        assert k.reject({"vid": "skip0000002", "title": "e", "artists": [{"name": "f", "id": None}]}) == "heard"
        assert quality.outcome(ls[0], False) == "unknown"
        listen("sig7", "skip0000002", now - 1000)   # came back to it and heard it through
        assert signals.refused() == set()


def test_a_playlist_save_this_year_is_a_love_and_deleting_the_history_takes_its_loves_with_it(monkeypatch):
    meta = {v: {"vid": v, "title": f"Song {v}", "artists": [{"name": f"Artist {v}", "id": None}], "type": "ATV", "dur": 200}
            for v in ("save0000001", "hist0000001")}
    monkeypatch.setattr(signals.ytm, "track", lambda v: meta.get(v))
    monkeypatch.setattr(signals.llm, "unavailable", lambda uid=None: "no claude in tests")
    with store.as_user("sig8"):
        store.write_json(store.SIGNALS, {"read": time.time(), "saved": [
            {"vid": "save0000001", "title": "Song save0000001", "artist": "Artist save0000001",
             "at": time.strftime("%Y-%m-%d", time.localtime(time.time() - 200 * DAY))}]})
        signals.save_history([["hist0000001", 9, 6, "2026-01-01", "2026-10-01", 5.0, "Song hist0000001", "Artist hist0000001"]],
                             ["2026-01-01", "2026-10-01"], 9)
        got = {r["vid"]: r["why"] for r in signals.refresh({"lanes": [{"key": "a"}]}, log=lambda *_: None)}
        assert got == {"save0000001": ["playlist"], "hist0000001": ["history"]}
        signals.forget_history()
        cache = store.read_json(store.IMPLICIT)
        assert [r["vid"] for r in cache["loves"]] == ["save0000001"] and set(cache["meta"]) == {"save0000001"}
        assert not signals.history() and [r["vid"] for r in signals.loves()] == ["save0000001"]


def test_play_and_history_endpoints_take_only_what_they_describe():
    c = TestClient(server.app)
    with store.as_user("owner"):
        ok = c.post("/api/play", json={"vid": "abcdefghijk", "ev": "start", "src": "pick", "fit": 0.8, "slot": 1, "fam": 2})
        assert ok.status_code == 200
        assert c.post("/api/play", json={"vid": "abcdefghijk", "ev": "listened"}).status_code == 422
        assert c.post("/api/play", json={"vid": "abcdefghijk", "src": "somewhere"}).status_code == 422
        r = c.post("/api/history", json={"songs": [["abcdefghijk", 4, 3, "2025-01-01", "2026-01-01", 1.5, "T", "A"],
                                                   ["../../etc/pw", 9, 9, "", "", 9, "x", "y"], ["short"],
                                                   ["bcdefghijkl", "many", 3, "", "", 1, "x", "y"]],
                                         "span": ["2020-01-01", "2026-01-01"], "entries": 40})
        assert r.status_code == 200 and r.json()["songs"] == 1
        assert set(signals.history()["songs"]) == {"abcdefghijk"}
        assert c.post("/api/history/delete").status_code == 200 and not signals.history()


def test_the_profile_reads_what_they_play_and_what_they_kept_elsewhere_years_ago(monkeypatch):
    from zhiyin import llm, profile
    sent = []
    monkeypatch.setattr(llm, "call", lambda prompt, system, schema, **kw: sent.append((prompt, system)) or {"lanes": []})
    with store.as_user("prof1"):
        store.write_json(store.LIBRARY, {"tracks": [{"rank": 0, "vid": "liked000001", "title": "玻璃", "artists": [{"name": "Gareth.T"}],
                                                     "long": False, "type": "ATV", "dur": 200, "liked_est": "2026-09-01"}]})
        store.write_json(store.TAGS, {"liked000001": {"kind": "song", "lang": "yue", "scene": "night", "sound": "r&b", "mood": "calm", "energy": 2}})
        signals.save_history([["liked000001", 30, 12, "2026-01-01", "2026-10-01", 9.0, "玻璃", "Gareth.T"],
                              ["other000001", 9, 6, "2026-01-01", "2026-10-01", 5.0, "夜闌人靜", "moon tang"]],
                             ["2025-11-28", "2026-10-30"], 39)
        signals.save_archive({"key": "qq:u:x", "lists": [{"title": "2016前我喜欢", "n": 1}],
                              "songs": [{"title": "说好的幸福呢", "artists": ["周杰伦"], "aka": [], "album": "", "released": "2008-10-15", "lists": [0]},
                                        {"title": "晴天", "artists": ["周杰伦"], "aka": [], "album": "", "released": "2003-07-31", "lists": [0]},
                                        {"title": "Rain", "artists": ["K.will"], "aka": [], "album": "", "released": "2013-02-01", "lists": [0]}]})
        profile.synthesize("opus")
    prompt, system = sent[0]
    assert "PLAYED ON YOUTUBE MUSIC (2025-11 to 2026-10" in prompt and "\n0|12|30|2026-10|玻璃|Gareth.T" in prompt
    assert "\n-|6|9|2026-10|夜阑人静|moon tang" in prompt   # played often, never liked; names in the reader's script
    assert "EARLIER LISTS, kept in QQ Music before their likes here begin" in prompt and "\n0|own|2016前我喜欢|-|-|-|1|周杰伦 2, K.will 1" in prompt
    assert "\n周杰伦|2|2003-2008|0|说好的幸福呢 / 晴天" in prompt and "One song each: K.will" in prompt
    assert "Never seed from them" in system


def test_an_app_listeners_other_lists_are_read_as_the_rest_of_their_page(monkeypatch):
    from zhiyin import library, llm, profile
    sent = []
    monkeypatch.setattr(llm, "call", lambda prompt, system, schema, **kw: sent.append(prompt) or {"lanes": []})
    with store.as_user("lists1"):
        store.write_json(store.LIBRARY, {"source": "qq", "tracks": [
            {"rank": i, "vid": f"liked{i:06d}", "title": f"歌 {i}", "artists": [{"name": "そらる" if i < 12 else f"Singer {i}"}],
             "long": False, "type": "ATV", "dur": 200, "liked_est": "2021-06-01", "source": "qq"} for i in range(24)]})
        signals.save_archive({"key": "qq:u:x", "lists": [
            {"title": "请给我一打洞爷湖", "kind": "own", "by": None, "at": "2021-11-26", "changed": "2021-11-26", "n": 2},
            {"title": "唱见の治愈歌声", "kind": "saved", "by": "凌舟", "at": "2020-07-10", "changed": "2021-07-29", "n": 2}],
            "songs": [{"title": "現状ディストラクション", "artists": ["SPYAIR"], "aka": [], "album": "", "released": "2013-01-01", "lists": [0]},
                      {"title": "サクラミツツキ", "artists": ["SPYAIR"], "aka": [], "album": "", "released": "2013-01-01", "lists": [0, 1]},
                      {"title": "夕溜まりのしおり", "artists": ["そらる"], "aka": [], "album": "", "released": "2016-01-01", "lists": [1]}]})
        profile.synthesize("opus")
        ev = profile.evidence(library.load(), {})
    prompt = sent[0]
    assert "THEIR OTHER LISTS in QQ Music, on the same page as the likes above" in prompt
    assert "\n0|own|请给我一打洞爷湖|-|2021-11|2021-11|2|SPYAIR 2" in prompt and "\n1|saved|唱见の治愈歌声|凌舟|2020-07|2021-07|2|" in prompt
    assert "SONGS IN THEIR OWN LISTS by artist (2 songs;" in prompt and "\nSPYAIR|2|2013|0|" in prompt   # not the saved list's
    assert "LISTS AND LIKES (artist: songs in their own lists, songs liked" in ev and "SPYAIR 2, 0" in ev
    assert "そらる" in ev.split("MOST LIKED AND ABSENT FROM THEIR OWN LISTS: ")[1]


def test_lists_are_read_from_every_page_once_a_week_and_a_failure_keeps_the_last(monkeypatch):
    from zhiyin import accounts, library
    reads = []

    def lists(page, likes=True):
        reads.append((page, likes))
        if page == "OLD" and len(reads) > 2:
            raise RuntimeError("QQ Music not answering")
        song = {"title": "優しい人", "artists": ["米津玄師"], "aka": [], "album": "", "released": None, "lists": [0]}
        return {"key": f"qq:u:{page}", "lists": [{"title": f"霓虹 {page}", "kind": "own", "n": 1}], "songs": [song]}
    monkeypatch.setattr(library, "page_lists", lists)
    monkeypatch.setattr(library, "app_page", lambda: "OWN")
    said = []
    uid = accounts.redeem(accounts.invite("Lists"))
    with store.as_user(uid):
        accounts.set_prefs(uid, pages=["OLD"])
        got = signals.read_lists(log=said.append)
        assert reads == [("OWN", False), ("OLD", True)]   # their likes are read on their own; an added page in full
        assert [(p["key"], p["same"], p["lists"]) for p in got["pages"]] == [("qq:u:OWN", True, 1), ("qq:u:OLD", False, 1)]
        assert [x["page"] for x in got["lists"]] == [0, 1] and got["songs"][0]["lists"] == [0, 1]   # one song, in both
        assert signals.read_lists()["songs"] and len(reads) == 2   # not again within the week
        assert signals.read_lists(force=True)["pages"] and len(reads) == 4   # a failed read keeps the last
        assert signals.read_lists() and len(reads) == 4                       # and is tried again a day later
        with pytest.raises(RuntimeError):
            signals.read_lists(force=True, strict=True)
        monkeypatch.setattr(library, "app_page", lambda: None)
        accounts.set_prefs(uid, pages=[])
        assert signals.read_lists() == {} and signals.archive() == {}   # pages taken off: their lists go
        signals.save_archive({"key": "qq:u:x", "lists": [], "songs": []})
        assert signals.read_lists()["key"] == "qq:u:x"   # a list kept by `zhiyin archive` before pages stays
    assert said == ["读到 QQ 音乐上的 1 个歌单和专辑，共 1 首歌"] * 2


def test_a_profile_added_for_its_lists_must_be_a_profile_and_one_that_shows_some(monkeypatch):
    from fastapi import HTTPException
    from zhiyin import accounts, library, qqmusic, server
    uid = accounts.redeem(accounts.invite("Ling"))
    jobs = []
    monkeypatch.setattr(server, "_start", lambda kind, fn: jobs.append((kind, fn)))
    monkeypatch.setattr(qqmusic, "parse", lambda text, c=None: ("playlist", 7) if "playlist" in text else ("user", "eu**"))
    monkeypatch.setattr(library, "app_page", lambda: None)
    with store.as_user(uid):
        with pytest.raises(HTTPException) as e:
            server.lists_add(server.PageReq(link="https://y.qq.com/n/ryqq/playlist/7"))
        assert e.value.status_code == 422 and "主页" in e.value.detail
        server.lists_add(server.PageReq(link="https://c6.y.qq.com/base/fcgi-bin/u?__=x"))
        page = qqmusic.link_of("qq:u:eu**")
        assert accounts.prefs(uid)["pages"] == [page] and jobs[-1][0] == "lists"
        monkeypatch.setattr(library, "page_lists", lambda p, likes=True: {"key": "qq:u:eu**", "lists": [], "songs": []})
        with pytest.raises(ValueError):   # nothing anyone else can see there: the page comes off again
            jobs[-1][1](lambda *a, **k: None)
        assert accounts.prefs(uid)["pages"] == []
        monkeypatch.setattr(library, "app_page", lambda: page)
        with pytest.raises(HTTPException) as e:   # the page their likes come from is read already
            server.lists_add(server.PageReq(link="https://c6.y.qq.com/base/fcgi-bin/u?__=x"))
        assert e.value.status_code == 409


def test_the_portrait_reads_counts_made_from_the_likes_not_its_own_counting():
    from zhiyin import profile
    def song(rank, vid, title, artist, liked, **tag):
        return ({"rank": rank, "vid": vid, "title": title, "artists": [{"name": artist}], "long": False, "type": "ATV",
                 "dur": 200, "liked_est": liked, "source": "google"},
                {"kind": "song", "lang": "yue", "scene": "x", "sound": "x", "mood": "x", "energy": 2, "year": 2015, **tag})
    rows = [song(i, f"run{i:08d}", f"Run {i}", "Karencici", "2026-09-01") for i in range(6)]
    rows += [song(6, "back0000001", "Back", "Crush", "2026-08-01"), song(7, "cover000001", "玻璃 (Cover)", "Someone", "2026-07-01",
                                                                         kind="cover", original="玻璃 - Gareth.T")]
    rows += [song(8 + i, f"fill{i:07d}", f"Fill {i}", f"Filler {i}", f"{2025 - i // 12}-06-01") for i in range(40)]
    rows += [song(48, "glass000001", "玻璃", "Gareth.T", "2021-01-01"), song(49, "back0000002", "Before", "Crush", "2020-05-01"),
             song(50, "back0000003", "Long before", "Crush", "2020-03-01"), song(51, "eason000001", "葡萄成熟時", "陳奕迅", "2020-02-01"),
             song(52, "eason000002", "K歌之王", "陳奕迅", "2020-01-01")]
    with store.as_user("ev1"):
        signals.save_history([["eason000001", 27, 9, "2026-01-01", "2026-10-01", 5.0, "葡萄成熟時", "Eason Chan"]],
                             ["2025-11-28", "2026-10-30"], 27)
        ev = profile.evidence([t for t, _ in rows], {t["vid"]: g for t, g in rows})
    assert "Karencici 6 of 25" in ev and "6 liked in all" in ev
    assert "Crush: around 2020-05, then none until 2026-08, 3 in all" in ev
    assert 'THE SAME SONG KEPT MORE THAN ONCE: 1 songs. "玻璃", Gareth.T x2 (cover, song' in ev   # the cover counts under its original
    assert "Eason Chan: 27, 1, 1, 2" in ev   # a channel's name links to the artist through the liked song it played


def test_the_portrait_is_its_own_call_and_lands_beside_the_stations(monkeypatch):
    from zhiyin import llm, profile
    seen = []

    def fake(prompt, system, schema, **kw):
        props = schema["properties"]
        seen.append(next(iter(props)))
        if "core" in props:   # the reading, in English, which the writer then turns into the page
            return {"core": "chords", "loves": [{"quality": "jazz chords", "evidence": "e", "ranks": [0]}], "loses": [],
                    "listener": [], "tension": {"reading": "t", "evidence": "e"}, "constant": "k", "changes": "c",
                    "eras": [{"from_rank": 0, "to_rank": 0, "years": "2026", "label": "L", "text": "T"}]}
        if "sound" in props:
            assert "- jazz chords Evidence: e Their songs that show it: \"玻璃\", Gareth.T" in prompt
            return {"sound": [{"claim": "s", "detail": "《玻璃》"}], "observations": [{"claim": "c", "evidence": "e"}],
                    "eras": [{"label": "l", "text": "t"}], "drafts": [], "headline": " h ", "names": [], "name": "和弦派。"}
        if "lanes" in props:
            return {"lanes": [{"key": "a", "name": "A", "english": "A", "blurb": "b", "when": "w", "sound": "s", "langs": ["yue"],
                               "energy": [1, 3], "seeds": [0], "core_artists": [], "explore_artists": [], "avoid": [],
                               "discovery": 0.3}], "focus": {}, "set_aside": []}
        return {"items": [{"i": 0, "lane": "a", "also": "none"}]}
    monkeypatch.setattr(llm, "call", fake)
    monkeypatch.setattr(llm, "require", lambda *a: None)
    with store.as_user("prof2"):
        store.write_json(store.LIBRARY, {"tracks": [{"rank": 0, "vid": "liked000001", "title": "玻璃", "artists": [{"name": "Gareth.T"}],
                                                     "long": False, "type": "ATV", "dur": 200, "liked_est": "2026-09-01"}]})
        store.write_json(store.TAGS, {"liked000001": {"kind": "song", "lang": "yue", "scene": "x", "sound": "x", "mood": "x", "energy": 2}})
        prof = profile.build(log=lambda *a: None)
        assert prof["portrait"]["observations"][0]["claim"] == "c" and prof["assign"] == {"liked000001": ["a"]}
        assert prof["portrait"]["headline"] == "h" and prof["portrait"]["sound"][0]["claim"] == "s"
        assert prof["portrait"]["eras"] == [{"from_rank": 0, "to_rank": 0, "years": "2026", "label": "l", "text": "t"}]
        assert prof["taste"]["core"] == "chords" and store.read_json(store.IDENT)["label"] == "和弦派"
        assert "name" not in prof["portrait"]
        assert "portrait" not in profile.LANE_SCHEMA["properties"]


def test_how_likes_sound_is_read_against_every_other_song_and_needs_enough_of_both():
    import numpy as np
    from zhiyin import audio
    rng = np.random.default_rng(3)
    jazz = np.zeros(512, dtype=np.float32)
    jazz[0] = 1
    con = audio._db()
    for p in audio.SOUND_TEXTS:
        v = jazz if p in audio.SOUND["jazz"] else rng.normal(size=512).astype(np.float32)
        con.execute("insert or replace into textemb (text, emb) values (?, ?)", (p, v.astype(np.float16).tobytes()))
    con.commit()
    assert audio.sound(["sndmine0000"]) == []   # words embedded, no song heard yet
    mine = [f"sndmine{i:04d}" for i in range(audio.SOUND_MIN)]
    for i, vid in enumerate(mine + [f"sndrest{i:04d}" for i in range(2 * audio.SOUND_MIN)]):
        v = rng.normal(size=512).astype(np.float32) + (jazz * 12 if vid in mine else 0)
        con.execute("insert into audio (vid, emb, ts) values (?, ?, 0)", (vid, v.astype(np.float16).tobytes()))
    con.commit()
    try:
        got = audio.sound(mine)
        assert got[0]["word"] == "jazz" and got[0]["d"] > 1 and set(got[0]["songs"]) <= set(mine)
        assert audio.sound(mine[:-1]) == []   # too few of theirs to say
        con.execute("delete from textemb where text=?", (audio.SOUND["jazz"][0],))
        con.commit()
        assert audio.sound(mine) == []   # the words aren't embedded yet
    finally:
        con.execute("delete from audio where vid like 'snd%'")
        con.execute(f"delete from textemb where text in ({','.join('?' * len(audio.SOUND_TEXTS))})", audio.SOUND_TEXTS)
        con.commit()
