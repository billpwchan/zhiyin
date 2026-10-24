from zhiyin.text import display_title, is_version, song_key


def test_song_key_ignores_brackets_features_and_tails():
    assert song_key("Like I Do (with William Singe)") == song_key("Like I Do")
    assert song_key("渡我 (Official Video)") == song_key("渡我")
    assert song_key("Best Part (feat. H.E.R.)") == song_key("Best Part")


def test_display_title_drops_artist_and_promo():
    assert display_title("moon tang - 渡我 (official video)", [{"name": "moon tang"}]) == "渡我"
    assert display_title("Week End", [{"name": "Gen Hoshino"}]) == "Week End"


def test_versions_are_recognised():
    assert is_version("Fly Me to the Moon (Live)")
    assert is_version("Hype Boy - Sped Up")
    assert not is_version("Hype Boy")


def test_plain_title_restores_feat():
    from zhiyin.ytm import plain_title
    assert plain_title("Lovefool (合作演出：Haley Reinhart)") == "Lovefool (feat. Haley Reinhart)"
    assert plain_title("All About That Bass (合作演出：Morgan James、Kate Davis)") == "All About That Bass (feat. Morgan James, Kate Davis)"
    assert plain_title("可以不可以") == "可以不可以"
