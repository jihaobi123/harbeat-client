from app.modules.library.external_metadata.normalizer import normalize_label


def test_normalizes_common_music_labels():
    assert normalize_label("Hip Hop") == "hiphop"
    assert normalize_label("hip-hop") == "hiphop"
    assert normalize_label("rap") == "hiphop"
    assert normalize_label("old school hip hop") == "hiphop_oldschool"
    assert normalize_label("electro funk") == "electro_funk"
    assert normalize_label("electro-funk") == "electro_funk"
    assert normalize_label("r&b") == "rnb"
    assert normalize_label("g-funk") == "g_funk"
