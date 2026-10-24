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
