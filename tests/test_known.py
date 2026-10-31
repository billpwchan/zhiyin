from zhiyin import candidates


def track(vid, title, *artists):
    return {"vid": vid, "title": title, "artists": [{"name": a, "id": None} for a in artists], "long": False}


def known():
    return candidates.Known([track("liked1", "Like I Do (with William Singe)", "J.Tajor")], {})


def test_liked_song_is_rejected_by_id_and_by_identity():
    k = known()
    assert k.reject(track("liked1", "anything", "x")) == "liked"
    assert k.reject(track("other", "Like I Do", "J.Tajor")) == "same song"


def test_upload_with_artists_in_the_title_is_the_same_song():
    assert known().reject(track("up1", "J Tajor & sunkis - Like I Do", "sunkis 宋秉勤")) == "same song"


def test_a_new_song_by_a_liked_artist_passes():
    assert known().reject(track("new1", "Another Song", "J.Tajor")) is None


def test_taken_in_another_lane_is_rejected():
    k = known()
    k.taken.add("dup")
    assert k.reject(track("dup", "Song", "Someone")) == "taken"


def test_a_song_heard_once_never_comes_back_under_any_video():
    from zhiyin import store
    with store.as_user("heard1"):
        con = store.db()
        con.execute("insert into plays (vid, lane, ts, ev, pos, uid, title, artist) values (?,?,?,?,?,?,?,?)",
                    ("heard000001", "x", 1, "left", 95, "heard1", "Sukiyaki (Live)", "Kyu Sakamoto"))
        con.execute("insert into plays (vid, lane, ts, ev, pos, uid, title, artist) values (?,?,?,?,?,?,?,?)",
                    ("started0001", "x", 1, "start", 0, "heard1", "Started Only", "Someone"))
        con.commit()
        k = candidates.Known([], {})
        assert k.reject(track("heard000001", "Sukiyaki", "Kyu Sakamoto")) == "heard"
        assert k.reject(track("othervideo1", "Sukiyaki", "Kyu Sakamoto")) == "heard"
        assert k.reject(track("othervideo2", "Sukiyaki", "A Cover Band")) is None
        assert k.reject(track("started0001", "Started Only", "Someone")) is None   # pressing play isn't hearing


def test_a_like_that_is_not_their_taste_neither_seeds_nor_brings_its_artist():
    import random
    from zhiyin import settings, store
    from zhiyin.text import fold
    with store.as_user("notme1"):
        settings.set_not_me(vid="mine0000001")
        s = settings.load()
        s["not_me"]["artists"] = [fold("Kids Band")]
        settings.save(s)
        tracks = [dict(track(f"mine{i:07d}", f"Song {i}", "Kids Band" if i % 2 else "Real Artist"), rank=i, liked_est=None, type="ATV")
                  for i in range(1, 9)]
        lane = {"key": "a", "seeds": [], "core_artists": []}
        profile = {"assign": {t["vid"]: ["a"] for t in tracks}}
        seeds = candidates.lane_seeds(lane, tracks, profile, random.Random(1))
        assert seeds and all(t["artists"][0]["name"] == "Real Artist" and t["vid"] != "mine0000001" for t in seeds)
        assert candidates.Known(tracks, {}).reject(track("new0000001", "New Song", "Kids Band")) == "blocked artist"


def test_an_artist_set_aside_in_one_script_is_the_same_artist_in_the_other():
    from zhiyin import settings, store
    with store.as_user("notme2"):
        s = settings.load()
        s["not_me"]["artists"] = ["張震嶽"]   # stored before fold met Chinese script
        settings.save(s)
        assert settings.is_not_me(track("x0000000001", "愛我別走", "张震岳"), settings.not_me())
        settings.set_not_me(artist="张震岳", on=True)
        assert settings.load()["not_me"]["artists"] == ["张震岳"]   # one entry, not two
        settings.set_not_me(artist="張震嶽", on=False)
        assert settings.load()["not_me"]["artists"] == []


def test_songs_kept_in_another_app_years_ago_are_heard_and_their_artists_known():
    from zhiyin import signals, store
    with store.as_user("archive1"):
        signals.save_archive({"key": "qq:u:x", "lists": [{"title": "2016前我喜欢", "n": 2}], "songs": [
            {"title": "Rain", "artists": ["太妍"], "aka": ["TAEYEON"], "album": "", "released": "2016-02-03", "lists": [0]},
            {"title": "횡단보도 (人行横道)", "artists": ["赵权"], "aka": ["조권"], "album": "", "released": None, "lists": [0]}]})
        k = candidates.Known([], {})
        assert k.reject(track("new0000001", "Rain", "TAEYEON")) == "same song"
        assert k.reject(track("new0000002", "횡단보도", "조권")) == "same song"
        assert k.reject(track("new0000003", "Rain", "Someone Else")) is None
        assert k.artist_known([{"name": "TAEYEON", "id": None}]) == "earlier" and not k.is_new([{"name": "太妍", "id": None}])
