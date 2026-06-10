from types import SimpleNamespace
import asyncio

from app.modules.library.external_metadata.schemas import ExternalSourceResult
from app.modules.library.external_metadata.service import run_enrich_song_external_metadata


class FakeDb:
    def __init__(self):
        self.commits = 0

    def add(self, _obj):
        pass

    def commit(self):
        self.commits += 1

    def refresh(self, _obj):
        pass


def _song():
    return SimpleNamespace(
        id="song-1",
        title="More Bounce To The Ounce",
        artist="Zapp",
        bpm=100.0,
        energy=0.7,
        duration=240.0,
        beat_points=[i * 0.5 for i in range(480)],
        downbeats=[i * 2.0 for i in range(120)],
        phrase_map=[],
        genre_profile={"primary_genre": "funk", "genres": [{"name": "funk", "confidence": 0.7}]},
        music_features={"dj": {
            "bpm": 100.0,
            "energy": 0.7,
            "beat_density": 2.0,
            "four_on_floor": 0.4,
            "groove_complexity": 0.08,
            "bass_dominance": 0.42,
            "brass_likely": 0.36,
            "spectral_centroid": 1800.0,
        }},
        dance_style_scores={},
        dance_styles=[],
        dance_style_status="none",
        beat_confidence=0.8,
        tempo_stability=0.8,
        transition_windows=[{"start": 180, "end": 196}],
        intro_clean_score=0.7,
        outro_clean_score=0.7,
        stem_quality_score=0.7,
        analysis_status="completed",
    )


def fake_fetcher(**_kwargs):
    return {
        "discogs": ExternalSourceResult("discogs", "hit", ["Funk", "Electro", "Boogie"], 0.8),
        "lastfm": ExternalSourceResult("lastfm", "hit", ["funky", "old school"], 0.75),
        "musicbrainz": ExternalSourceResult("musicbrainz", "hit", ["electro-funk"], 0.7, mbid="mbid"),
    }


async def async_fake_fetcher(**_kwargs):
    await asyncio.sleep(0)
    return {
        "discogs": ExternalSourceResult("discogs", "hit", ["Hip-Hop/Rap", "Boom Bap"], 0.8),
        "lastfm": ExternalSourceResult("lastfm", "miss", [], 0.0),
        "musicbrainz": ExternalSourceResult("musicbrainz", "miss", [], 0.0),
    }


def test_external_enrichment_writes_style_evidence_and_scores():
    song = _song()
    db = FakeDb()

    result = run_enrich_song_external_metadata(db, song, force=True, fetcher=fake_fetcher)

    assert result.source_statuses()["discogs"] == "hit"
    assert song.genre_profile["sources"]["discogs"]["status"] == "hit"
    assert song.genre_profile["style_evidence_v1"]["popping"]["external_platform_score"] > 0.7
    assert song.dance_style_scores["popping"] > 0.6
    assert song.dance_style_status in {"ready", "partial"}
    assert db.commits >= 1


def test_sync_wrapper_can_run_inside_existing_event_loop():
    song = _song()
    db = FakeDb()

    async def run_inside_loop():
        return run_enrich_song_external_metadata(db, song, force=True, fetcher=async_fake_fetcher)

    result = asyncio.run(run_inside_loop())

    assert result.source_statuses()["discogs"] == "hit"
    assert song.genre_profile["sources"]["discogs"]["labels"] == ["hiphop", "boom_bap"]
    assert song.genre_profile["style_evidence_v1"]["hiphop"]["external_platform_score"] > 0.7
    assert song.dance_style_scores["hiphop"] > 0.5
