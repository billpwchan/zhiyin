from zhiyin.edition import one_each


def pick(vid, title, artist, mv=None):
    return {"vid": vid, "mv": mv, "title": title, "artists": [{"name": artist}]}


def test_one_song_once_per_edition():
    lane_a = [pick("a1", "Hype Boy", "NewJeans"), pick("a2", "Ditto", "NewJeans")]
    lane_b = [pick("b1", "Hype Boy (Official MV)", "NewJeans", mv="mv1"), pick("b2", "OMG", "NewJeans")]
    reserve = [pick("mv1", "something", "x"), pick("r1", "Ditto", "NewJeans"), pick("r2", "Cool With You", "NewJeans")]
    one_each([lane_a, lane_b, reserve])
    assert [p["vid"] for p in lane_a] == ["a1", "a2"]
    assert [p["vid"] for p in lane_b] == ["b2"]
    assert [p["vid"] for p in reserve] == ["r2"]


def test_a_reason_drops_sentences_about_the_listeners_songs_but_never_breaks_one():
    from zhiyin.rank import clean_reason
    from zhiyin.text import song_key
    theirs = {song_key(t) for t in ("Peace Piece", "爛泥", "Hatachi No Koi")}
    pick = {"title": "Hatachi No Koi"}
    one = "Bill Evans plays a gentle, unhurried ballad in the same spirit as “Peace Piece”."
    assert clean_reason(one, pick, theirs) == one   # cutting at its commas would leave "Bill Evans plays a gentle."
    assert clean_reason("A slow waltz. Close to “Peace Piece”.", pick, theirs) == "A slow waltz."
    assert clean_reason("唱着逝去的青春。和《爛泥》是近亲，但更温和。", pick, theirs) == "唱着逝去的青春。"
    assert clean_reason("“Hatachi No Koi” is Lamp at their softest. Warm.", pick, theirs) == "“Hatachi No Koi” is Lamp at their softest. Warm."


def test_a_reason_leaves_whether_they_know_the_artist_to_the_page():
    from zhiyin.rank import about_them
    assert about_them("低声吟唱的英国灵魂乐，很适合深夜。你还没收藏过 Cleo Sol。") == "低声吟唱的英国灵魂乐，很适合深夜。"
    assert about_them("A slow soul groove. Cleo Sol is new to you.") == "A slow soul groove."
    assert about_them("Pedal steel and sleepy vocals. An artist you haven’t saved yet.") == "Pedal steel and sleepy vocals."
    assert about_them("你还没收藏过的歌手：林宥嘉唱了一首克制的抒情歌。") == "你还没收藏过的歌手：林宥嘉唱了一首克制的抒情歌。"
    assert about_them("適合深夜，你沒聽過也會喜歡的那種。慢。") == "慢。"


def test_a_pick_is_shown_next_to_a_real_like_of_theirs():
    from zhiyin import edition
    theirs = [{"vid": "like0000001", "title": "Drifter", "artists": [{"name": "KIRINJI"}], "liked_est": "2024-03-02"},
              {"vid": "like0000002", "title": "Aliens", "artists": [{"name": "KIRINJI"}], "liked_est": None}]
    near = edition.because({"like_vid": "like0000001", "via": ["Aliens - KIRINJI"]}, theirs)
    assert near == {"vid": "like0000001", "title": "Drifter", "artist": "KIRINJI", "at": "2024-03", "how": "near"}
    assert edition.because({"like_vid": None, "via": ["Aliens - KIRINJI"]}, theirs)["how"] == "from"
    assert edition.because({"via": ["Someone else - X"]}, theirs) is None


def _cand(vid, artist, support=1.0, familiar=0):
    return {"vid": vid, "title": f"Song {vid}", "artists": [{"name": artist}], "support": support, "via": [],
            "sources": ["radio"], "familiar": familiar, "knows": None}


LANE = {"key": "jazz", "name": "夜里的爵士", "english": "Late jazz", "sound": "brushed drums", "when": "night",
        "langs": ["en"], "energy": [1, 2], "avoid": ["big band"], "discovery": 0.5}


def test_the_shortlist_follows_the_screen_but_keeps_the_new_artist_share_and_two_an_artist():
    from zhiyin import candidates
    cands = {c["vid"]: c for c in [_cand("a", "Old", familiar=3), _cand("b", "Old", familiar=3), _cand("c", "Old", familiar=3),
                                   _cand("d", "New1"), _cand("e", "New2"), _cand("f", "Old2", familiar=1)]}
    out = candidates.shortlist(LANE, cands, k=4, order=["a", "b", "c", "f", "d", "e"])
    assert [c["vid"] for c in out] == ["d", "e", "a", "b"]          # two new (half of four), then the screen's best known
    assert [c["vid"] for c in candidates.shortlist(LANE, cands, k=4, order=["e"])] == ["e"]   # only what the screen kept


def test_the_screen_takes_turns_with_the_graph_and_falls_back_when_its_reads_fail(monkeypatch):
    from zhiyin import llm, rank
    pool = {f"v{i}": _cand(f"v{i}", f"A{i}", support=1 + i / 100) for i in range(80)}   # the graph puts v79 first
    reads = iter([{"ids": [0, 1, 2]}, {"ids": [2, 1, 0]}, {"ids": [2, 75]}])
    seen = []

    def call(prompt, system, schema, **k):
        seen.append(prompt)
        return next(reads)
    monkeypatch.setattr(llm, "call", call)
    monkeypatch.setattr(rank, "SCREEN_PASSES", 3)
    order = rank.screen(LANE, pool, ["- Blue in Green — Bill Evans (liked 2026-09)"], ["- X — Y: heard it through"])
    assert len(seen) == 3 and "Blue in Green" in seen[0] and "heard it through" in seen[0] and "[79]" in seen[0]
    # the graph's best, then the song every read put near the top; one far down the graph's order still gets in
    by_line = {}
    for line in seen[0].split("\n"):
        if line.startswith("["):
            by_line[int(line[1:line.index("]")])] = line.split("] ")[1].split(" — ")[0]
    assert order[:2] == ["v79", by_line[2].replace("Song ", "")] and by_line[75] == "Song v4" and "v4" in order
    assert len(order) == len(set(order)) == rank.SCREEN_K

    def fail(*a, **k):
        raise llm.LLMError("down")
    monkeypatch.setattr(llm, "call", fail)
    assert rank.screen(LANE, pool, [], []) is None
    assert rank.screen(LANE, dict(list(pool.items())[:40]), [], []) is None   # a small pool is read whole by the editor


def test_earlier_picks_tell_the_editor_only_real_verdicts():
    import time
    from zhiyin import rank, store
    con, now = store.db(), time.time()
    rows = [("p1", "start", 0, None, now - 50), ("p1", "done", 200, None, now - 40),
            ("p2", "start", 0, None, now - 30), ("p2", "skip", 4, None, now - 29),
            ("p3", "start", 0, None, now - 20), ("p3", "stop", 5, None, now - 19),
            ("p4", "start", 0, None, now - 10), ("p4", "done", 200, None, now - 9)]
    for vid, ev, pos, _, ts in rows:
        con.execute("insert into plays(vid, lane, ts, ev, pos, dur, uid, slot, title, artist) values (?,?,?,?,?,?,?,?,?,?)",
                    (vid, "jazz", ts, ev, pos, 200, store.uid(), 0, f"T{vid}", "Ar"))
    con.execute("insert into feedback(vid, action, lane, scope, reason, title, artist, ts, uid) values (?,?,?,?,?,?,?,?,?)",
                ("p4", "dislike", "jazz", "song", "太吵", "Tp4", "Ar", now - 5, store.uid()))
    con.execute("insert into feedback(vid, action, lane, scope, reason, title, artist, ts, uid) values (?,?,?,?,?,?,?,?,?)",
                ("p5", "like", "jazz", "song", None, "Tp5", "Ar", now - 1, store.uid()))
    con.execute("insert into feedback(vid, action, lane, scope, reason, title, artist, ts, uid) values (?,?,?,?,?,?,?,?,?)",
                ("p6", "dislike", "jazz", "song", "只是不該在這個電台", "Tp6", "Ar", now - 60, store.uid()))
    con.commit()
    assert rank.outcomes("jazz")[-1] == "- Tp6 — Ar: said it's fine but doesn't belong in this lane"
    assert rank.outcomes("jazz")[:-1] == ["- Tp5 — Ar: loved it (added to likes)", "- Tp4 — Ar: said it's not for them: 太吵",
                                     "- Tp2 — Ar: skipped it within seconds", "- Tp1 — Ar: heard it through"]
    assert rank.outcomes("other") == []


def test_a_lane_is_told_from_all_its_songs_newest_first():
    from zhiyin import rank, settings
    def t(r, vid, artist):
        return {"vid": vid, "rank": r, "long": False, "title": f"S{r}", "type": "ATV", "artists": [{"name": artist}],
                "liked_est": f"2026-0{9 - r}-01"}
    tracks = [t(2, "x2", "B"), t(0, "x0", "A"), t(1, "x1", "C"), t(3, "x3", "D")]
    prof = {"assign": {"x0": ["soul"], "x1": ["pop"], "x2": ["soul"], "x3": ["soul"]}, "set_aside": [{"ranks": [3]}]}
    loves = [{"vid": "l1", "title": "Often", "artists": [{"name": "E"}], "lane": ["soul"]}]
    s = settings.load()
    s["not_me"]["artists"] = ["b"]
    settings.save(s)
    try:
        assert rank.lane_story({**LANE, "key": "soul"}, tracks, prof, loves) == ["- S0 — A (liked 2026-09)", "- Often — E (played often, never liked)"]
    finally:
        s["not_me"]["artists"] = []
        settings.save(s)
