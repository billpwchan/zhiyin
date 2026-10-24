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
