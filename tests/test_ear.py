from zhiyin.ear import _times


def test_like_dates_fill_gaps_and_never_go_back_in_time():
    tracks = [{"liked_est": "2024-01-01"}, {"liked_est": None}, {"liked_est": "2025-06-01"}, {"liked_est": "2020-01-01"}]
    ts = _times(tracks)   # newest first
    assert all(a >= b for a, b in zip(ts, ts[1:]))
    assert 2020 <= ts[1] <= 2024
    assert ts[2] <= ts[0]   # an estimate newer than a later like is pulled back


def test_a_new_listener_has_a_record_from_liked_videos_before_any_station():
    from zhiyin import ear, store
    with store.as_user("glimpse1"):
        store.write_json(store.GLIMPSE, {"at": 0, "songs": [
            {"vid": f"v{i:010d}", "title": f"Song {i}", "artist": "Some Channel", "at": f"20{18 + i % 7}-{1 + i % 12:02d}-10", "dur": 200}
            for i in range(40)]})
        d = ear.build()
    assert d["stage"] == "glimpse" and d["sectors"] == [] and len(d["songs"]) == 40
    assert all(8 <= s[7] <= 352 for s in d["songs"])   # laid out by time of year, clear of the gap at twelve o'clock
    first = next(f for f in d["facts"] if f["key"] == "first")
    assert "Some Channel" not in first["text"]          # a channel name is not yet an artist


def test_the_centre_year_is_the_lower_median_and_needs_enough_songs():
    from zhiyin.ear import center
    tracks = [{"vid": f"v{i}"} for i in range(40)]
    tags = {f"v{i}": {"year": 1990 + i} for i in range(40)}
    assert center(tracks, tags) == 2009
    assert center(tracks[:20], tags) is None
    assert center(tracks, {**tags, "v0": {"year": 0}, "v1": {"year": None}}) == 2010


def test_the_name_of_a_taste_follows_the_readers_script_but_not_their_language(monkeypatch):
    from zhiyin import ear, i18n, store
    with store.as_user("label1"):
        store.write_json(store.IDENT, {"label": "老派港乐，新派韩流", "lang": "zh-Hans", "built": 0})
        monkeypatch.setattr(i18n, "of", lambda uid=None: "zh-Hant")
        assert ear.label() == "老派港樂，新派韓流"
        monkeypatch.setattr(i18n, "of", lambda uid=None: "en")
        assert ear.label() is None   # an English reader gets a name of their own, not a translation


def test_eras_reach_the_page_oldest_first():
    from pathlib import Path
    from zhiyin import ear, store
    demo = Path(__file__).parent.parent / "demo"
    with store.as_user("eras1"):
        d = store.USERS / "eras1"
        d.mkdir(parents=True, exist_ok=True)
        for f in ("library.json", "tags.json", "profile.json", "edition.json", "ident.json"):
            (d / f).write_bytes((demo / f).read_bytes())
        eras = ear.build()["eras"]
    assert len(eras) > 2 and [e["t0"] for e in eras] == sorted(e["t0"] for e in eras)
