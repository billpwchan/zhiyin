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


def test_a_pick_is_shown_next_to_a_real_like_of_theirs():
    from zhiyin import edition
    theirs = [{"vid": "like0000001", "title": "Drifter", "artists": [{"name": "KIRINJI"}], "liked_est": "2024-03-02"},
              {"vid": "like0000002", "title": "Aliens", "artists": [{"name": "KIRINJI"}], "liked_est": None}]
    near = edition.because({"like_vid": "like0000001", "via": ["Aliens - KIRINJI"]}, theirs)
    assert near == {"vid": "like0000001", "title": "Drifter", "artist": "KIRINJI", "at": "2024-03", "how": "near"}
    assert edition.because({"like_vid": None, "via": ["Aliens - KIRINJI"]}, theirs)["how"] == "from"
    assert edition.because({"via": ["Someone else - X"]}, theirs) is None
