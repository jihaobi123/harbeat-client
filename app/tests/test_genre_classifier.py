"""Tests for multi-source genre classifier."""
import json
import unittest
from unittest.mock import patch

from app.modules.library.genre_classifier import (
    _classify_from_features,
    _map_discogs_labels_to_dj,
    _map_spotify_genres_to_dj,
    classify_genre,
)


class GenreClassifierTests(unittest.TestCase):
    def test_hiphop_bpm_and_stems(self):
        """90 BPM + vocal-heavy stems → hip-hop."""
        result = _classify_from_features(
            bpm=95.0,
            stem_activity={"vocals": 0.7, "drums": 0.4, "bass": 0.6, "other": 0.2},
            groove_profile={"score": 0.5, "label": "groovy"},
            dj_features={"spectral_centroid": 1800, "sub_bass_score": 0.5},
            energy=0.6,
        )
        self.assertEqual(result["primary_genre"], "hip-hop")
        self.assertGreater(result["primary_confidence"], 0.3)
        self.assertGreater(len(result["genres"]), 1)

    def test_house_4_on_floor(self):
        """124 BPM + four-on-floor + moderate stems → house."""
        result = _classify_from_features(
            bpm=124.0,
            stem_activity={"vocals": 0.2, "drums": 0.7, "bass": 0.5, "other": 0.3},
            groove_profile={"score": 0.6, "label": "groovy"},
            dj_features={"spectral_centroid": 3500, "four_on_floor": 0.85},
            energy=0.65,
        )
        self.assertEqual(result["primary_genre"], "house")
        self.assertGreater(result["primary_confidence"], 0.3)

    def test_dnb_high_bpm(self):
        """175 BPM → drum-and-bass."""
        result = _classify_from_features(
            bpm=174.0,
            stem_activity={"vocals": 0.05, "drums": 0.8, "bass": 0.7, "other": 0.2},
            groove_profile={"score": 0.4, "label": "steady"},
            dj_features={"spectral_centroid": 2500, "sub_bass_score": 0.5},
            energy=0.85,
        )
        self.assertEqual(result["primary_genre"], "drum-and-bass")

    def test_no_stems_still_classifies(self):
        """Without stem data, BPM alone should still work."""
        result = _classify_from_features(
            bpm=128.0,
            stem_activity=None,
            groove_profile={"score": 0.6, "label": "groovy"},
            dj_features={"spectral_centroid": 4000, "four_on_floor": 0.9},
            energy=0.7,
        )
        self.assertGreater(len(result["genres"]), 0)
        # BPM 128 + high spectral → likely house or techno
        self.assertIn(result["primary_genre"], ("house", "techno", "trance", "electronic"))
        self.assertEqual(result["method"], "audio_features")

    def test_no_data_returns_unknown(self):
        result = _classify_from_features(bpm=0.0, stem_activity=None,
                                          groove_profile=None, dj_features=None, energy=0.0)
        self.assertEqual(result["primary_genre"], "unknown")
        self.assertEqual(result["method"], "no_data")

    def test_spotify_genre_mapping(self):
        """Spotify microgenres map to broad DJ genres."""
        spotify = ["deep house", "tech house", "minimal techno"]
        mapped = _map_spotify_genres_to_dj(spotify)
        names = {g["name"] for g in mapped}
        self.assertIn("house", names)
        self.assertIn("techno", names)
        # House should have higher confidence (2 tags vs 1)
        house_conf = next(g["confidence"] for g in mapped if g["name"] == "house")
        techno_conf = next(g["confidence"] for g in mapped if g["name"] == "techno")
        self.assertGreater(house_conf, techno_conf)

    def test_manual_style_overrides_everything(self):
        result = classify_genre(
            bpm=124.0,
            title="Test Song",
            artist="Test Artist",
            manual_style="hip-hop / trap",
        )
        self.assertEqual(result["primary_genre"], "hip-hop / trap")
        self.assertEqual(result["method"], "manual")
        self.assertEqual(result["primary_confidence"], 1.0)

    def test_json_serializable(self):
        result = classify_genre(
            bpm=100.0,
            stem_activity={"vocals": 0.5, "drums": 0.5, "bass": 0.4, "other": 0.3},
            groove_profile={"score": 0.6, "label": "groovy"},
            dj_features=None,
            energy=0.5,
            title="Something",
            artist="Someone",
        )
        json.dumps(result)

    def test_ambient_detected_from_low_drums_and_energy(self):
        """Low drums + low energy → ambient."""
        result = _classify_from_features(
            bpm=85.0,
            stem_activity={"vocals": 0.1, "drums": 0.1, "bass": 0.1, "other": 0.5},
            groove_profile={"score": 0.3, "label": "unstable"},
            dj_features={"spectral_centroid": 1500},
            energy=0.2,
        )
        # ambient or lo-fi should be high
        genres = {g["name"] for g in result["genres"][:3]}
        self.assertTrue(any(g in ("ambient", "lo-fi", "downtempo") for g in genres))


class SpotifyMappingTests(unittest.TestCase):
    def test_empty_spotify_genres(self):
        self.assertEqual(_map_spotify_genres_to_dj([]), [])

    def test_unknown_spotify_genre_ignored(self):
        """Unmapped genres are silently dropped."""
        mapped = _map_spotify_genres_to_dj(["some-obscure-microgenre-xyz"])
        self.assertEqual(mapped, [])

    def test_partial_match_works(self):
        """'deep house uk' should still map to 'house'."""
        mapped = _map_spotify_genres_to_dj(["deep house uk"])
        self.assertTrue(any(g["name"] == "house" for g in mapped))


class DiscogsMappingTests(unittest.TestCase):
    def test_discogs_styles_map_to_dj_taxonomy(self):
        mapped = _map_discogs_labels_to_dj(["Electronic", "Deep House", "Drum n Bass"])
        names = {g["name"] for g in mapped}
        self.assertIn("house", names)
        self.assertIn("drum-and-bass", names)

    @patch("app.modules.library.genre_classifier._enrich_from_spotify", return_value=None)
    @patch(
        "app.modules.library.genre_classifier._enrich_from_discogs",
        return_value={
            "genres": [{"name": "funk", "confidence": 0.8, "source": "discogs"}],
            "discogs_id": 123,
            "discogs_labels_raw": ["Funk / Soul", "Boogie"],
            "source": "discogs",
        },
    )
    def test_discogs_enrichment_merges_with_audio(self, _discogs, _spotify):
        result = classify_genre(
            bpm=105.0,
            stem_activity={"vocals": 0.2, "drums": 0.5, "bass": 0.4, "other": 0.4},
            groove_profile={"score": 0.7, "label": "groovy"},
            dj_features={"brass_likely": 0.5},
            energy=0.7,
            title="Test",
            artist="Artist",
        )
        self.assertEqual(result["primary_genre"], "funk")
        self.assertEqual(result["method"], "discogs_audio_merged")
        self.assertEqual(result["discogs_id"], 123)


if __name__ == "__main__":
    unittest.main()
