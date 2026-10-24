from zhiyin.ear import _times


def test_like_dates_fill_gaps_and_never_go_back_in_time():
    tracks = [{"liked_est": "2024-01-01"}, {"liked_est": None}, {"liked_est": "2025-06-01"}, {"liked_est": "2020-01-01"}]
    ts = _times(tracks)   # newest first
    assert all(a >= b for a, b in zip(ts, ts[1:]))
    assert 2020 <= ts[1] <= 2024
    assert ts[2] <= ts[0]   # an estimate newer than a later like is pulled back
