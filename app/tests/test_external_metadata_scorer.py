from app.modules.library.external_metadata.scorer import (
    fuse_external_source_scores,
    score_external_tags_for_style,
)


def test_popping_tags_score_high_and_negative_tags_reduce():
    high = score_external_tags_for_style(["funk", "electro", "boogie"], "popping")
    low = score_external_tags_for_style(["ambient", "acoustic"], "popping")

    assert high > 0.7
    assert low < high


def test_external_source_weights_normalize_missing_sources():
    score = fuse_external_source_scores(
        {"discogs": 0.8, "lastfm": 0.6, "musicbrainz": None},
        {"discogs": 0.45, "lastfm": 0.35, "musicbrainz": 0.20},
    )

    assert score == round((0.45 * 0.8 + 0.35 * 0.6) / (0.45 + 0.35), 4)

