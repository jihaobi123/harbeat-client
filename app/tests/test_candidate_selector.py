"""Tests for C3 Candidate Selector (rule-based recommendation engine)."""
import unittest

from app.modules.session.schemas import SceneConfig, SceneType
from app.modules.session.candidate_selector import CandidateSelector


class CandidateSelectorTests(unittest.TestCase):
    def setUp(self):
        self.tracks = {
            "trk_house": {
                "bpm": 124.0, "key": "E minor", "camelot_key": "9A",
                "energy": 0.65, "beat_confidence": 0.95,
                "intro_is_clean": True, "outro_is_clean": True,
                "genre_profile": {"primary_genre": "house", "genres": [
                    {"name": "house", "confidence": 0.9},
                ]},
                "groove_profile": {"score": 0.82, "label": "groovy"},
                "dance_style_scores": {"house": 0.9, "hiphop": 0.3},
                "stem_activity": {"vocals": 0.2, "drums": 0.7, "bass": 0.5, "other": 0.3},
                "loudness_profile": {"clipping_risk": False},
            },
            "trk_hiphop": {
                "bpm": 95.0, "key": "D# minor", "camelot_key": "2A",
                "energy": 0.55, "beat_confidence": 0.92,
                "intro_is_clean": True, "outro_is_clean": True,
                "genre_profile": {"primary_genre": "hip-hop", "genres": [
                    {"name": "hip-hop", "confidence": 0.85},
                ]},
                "groove_profile": {"score": 0.78, "label": "groovy"},
                "dance_style_scores": {"hiphop": 0.85, "house": 0.2},
                "stem_activity": {"vocals": 0.6, "drums": 0.4, "bass": 0.5, "other": 0.2},
                "loudness_profile": {"clipping_risk": False},
            },
            "trk_techno": {
                "bpm": 132.0, "key": "F# minor", "camelot_key": "11A",
                "energy": 0.82, "beat_confidence": 0.90,
                "intro_is_clean": False, "outro_is_clean": True,
                "genre_profile": {"primary_genre": "techno", "genres": [
                    {"name": "techno", "confidence": 0.9},
                ]},
                "groove_profile": {"score": 0.75, "label": "steady"},
                "dance_style_scores": {"techno": 0.8, "house": 0.5},
                "stem_activity": {"vocals": 0.1, "drums": 0.8, "bass": 0.6, "other": 0.3},
                "loudness_profile": {"clipping_risk": True},
            },
            "trk_risky": {
                "bpm": 175.0, "key": "C major", "camelot_key": "8B",
                "energy": 0.9, "beat_confidence": 0.6,
                "intro_is_clean": False, "outro_is_clean": False,
                "genre_profile": {"primary_genre": "drum-and-bass", "genres": [
                    {"name": "drum-and-bass", "confidence": 0.8},
                ]},
                "groove_profile": {"score": 0.5, "label": "unstable"},
                "dance_style_scores": {},
                "stem_activity": {"vocals": 0.05, "drums": 0.9, "bass": 0.8, "other": 0.2},
                "loudness_profile": {"clipping_risk": True},
            },
            "trk_funk": {
                "bpm": 108.0, "key": "A minor", "camelot_key": "8A",
                "energy": 0.5, "beat_confidence": 0.88,
                "intro_is_clean": True, "outro_is_clean": True,
                "genre_profile": {"primary_genre": "funk", "genres": [
                    {"name": "funk", "confidence": 0.8},
                ]},
                "groove_profile": {"score": 0.85, "label": "groovy"},
                "dance_style_scores": {"locking": 0.8, "popping": 0.7},
                "stem_activity": {"vocals": 0.3, "drums": 0.5, "bass": 0.4, "other": 0.4},
                "loudness_profile": {"clipping_risk": False},
            },
        }
        self.selector = CandidateSelector(track_registry=self.tracks)

    # ── basic selection ──────────────────────────────────────────────────

    def test_select_returns_best_safe_diverse(self):
        result = self.selector.select_candidates(
            current_track_id="trk_house",
            session_state="build",
            target_energy=0.7,
            current_energy=0.65,
        )
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.safe)
        self.assertIsNotNone(result.diverse)
        self.assertGreater(len(result.candidates), 0)

    def test_current_track_excluded(self):
        result = self.selector.select_candidates(
            current_track_id="trk_house",
            session_state="build",
            target_energy=0.5,
        )
        ids = [c.track_id for c in result.candidates]
        self.assertNotIn("trk_house", ids)

    def test_avoid_ids_excluded(self):
        result = self.selector.select_candidates(
            current_track_id="trk_house",
            avoid_ids=["trk_hiphop", "trk_techno"],
            session_state="warmup",
            target_energy=0.5,
        )
        ids = [c.track_id for c in result.candidates]
        self.assertNotIn("trk_hiphop", ids)
        self.assertNotIn("trk_techno", ids)

    def test_empty_registry_returns_empty(self):
        empty = CandidateSelector(track_registry={})
        result = empty.select_candidates(target_energy=0.5)
        self.assertEqual(len(result.candidates), 0)

    # ── energy targeting ─────────────────────────────────────────────────

    def test_energy_up_prefers_higher_energy(self):
        """energy_up intent should prefer tracks with higher energy than current."""
        result = self.selector.select_candidates(
            current_track_id="trk_hiphop",  # energy=0.55
            session_state="build",
            target_energy=0.7,
            current_energy=0.55,
            intent="energy_up",
        )
        best = result.best
        self.assertIsNotNone(best)
        if best:
            best_energy = self.tracks[best.track_id]["energy"]
            self.assertGreater(best_energy, 0.55)

    def test_energy_down_prefers_lower_energy(self):
        """energy_down intent should prefer lower energy tracks."""
        result = self.selector.select_candidates(
            current_track_id="trk_techno",  # energy=0.82
            session_state="peak",
            target_energy=0.5,
            current_energy=0.82,
            intent="energy_down",
        )
        best = result.best
        self.assertIsNotNone(best)
        if best:
            best_energy = self.tracks[best.track_id]["energy"]
            self.assertLess(best_energy, 0.82)

    # ── scene configuration ──────────────────────────────────────────────

    def test_scene_hiphop_prefers_hiphop_tracks(self):
        scene = SceneConfig(
            scene=SceneType.cypher,
            dance_styles=["hiphop"],
        )
        result = self.selector.select_candidates(
            current_track_id="trk_techno",
            session_state="warmup",
            target_energy=0.5,
            scene=scene,
        )
        best = result.best
        self.assertIsNotNone(best)
        if best:
            # trk_hiphop should rank high for hiphop scene
            self.assertIn(best.track_id, ["trk_hiphop", "trk_funk"])

    def test_scene_house_prefers_house_tracks(self):
        scene = SceneConfig(
            scene=SceneType.party,
            dance_styles=["house"],
        )
        result = self.selector.select_candidates(
            current_track_id="trk_hiphop",
            session_state="build",
            target_energy=0.6,
            scene=scene,
        )
        best = result.best
        self.assertIsNotNone(best)
        if best:
            self.assertEqual(best.track_id, "trk_house")

    # ── safety ───────────────────────────────────────────────────────────

    def test_risky_track_not_selected_as_safe(self):
        result = self.selector.select_candidates(
            current_track_id="trk_house",
            session_state="peak",
            target_energy=0.9,
        )
        if result.safe:
            safe_track = self.tracks.get(result.safe.track_id, {})
            self.assertTrue(self.selector._is_safe(safe_track))

    def test_safe_track_has_high_beat_confidence(self):
        result = self.selector.select_candidates(
            current_track_id="trk_house",
            session_state="warmup",
            target_energy=0.5,
        )
        self.assertIsNotNone(result.safe)
        if result.safe:
            safe = self.tracks[result.safe.track_id]
            self.assertGreaterEqual(safe["beat_confidence"], 0.85)
            self.assertTrue(safe["intro_is_clean"])

    def test_explicit_danceability_score_overrides_groove_proxy(self):
        track = dict(self.tracks["trk_house"])
        track["danceability_score"] = 0.21
        _, breakdown = self.selector._score_track(
            track=track,
            current_track=None,
            target_energy=0.65,
            current_energy=0.65,
            session_state="warmup",
        )
        self.assertEqual(breakdown["danceability"], 0.21)

    def test_low_clean_intro_score_is_not_safe_when_score_is_available(self):
        track = dict(self.tracks["trk_house"])
        track["intro_clean_score"] = 0.42
        self.assertFalse(self.selector._is_safe(track))

    # ── transition compatibility ─────────────────────────────────────────

    def test_bpm_jump_detected_in_warnings(self):
        """175 BPM vs 124 BPM → warning."""
        result = self.selector.select_candidates(
            current_track_id="trk_house",  # 124 BPM
            session_state="peak",
            target_energy=0.9,
        )
        risky_cand = next(
            (c for c in result.candidates if c.track_id == "trk_risky"), None
        )
        self.assertIsNotNone(risky_cand)
        if risky_cand:
            self.assertTrue(
                any("bpm_jump" in w for w in risky_cand.warnings)
            )

    def test_key_clash_detected(self):
        """8B vs 9A → distance >= 4 → warning."""
        result = self.selector.select_candidates(
            current_track_id="trk_techno",  # 11A
            session_state="peak",
            target_energy=0.5,
        )
        risky = next(
            (c for c in result.candidates if c.track_id == "trk_risky"), None
        )
        self.assertIsNotNone(risky)
        if risky:
            self.assertTrue(
                any("key_clash" in w for w in risky.warnings)
            )

    def test_template_varies_by_bpm_ratio(self):
        """Close BPM → safe_blend, far BPM → style_change."""
        result = self.selector.select_candidates(
            current_track_id="trk_house",  # 124 BPM
            session_state="build",
            target_energy=0.5,
        )
        for c in result.candidates:
            track = self.tracks.get(c.track_id, {})
            ratio = c.bpm_ratio
            if ratio <= 1.03:
                self.assertEqual(c.template, "safe_blend")
            elif ratio > 1.12:
                self.assertEqual(c.template, "style_change")

    # ── diversity ────────────────────────────────────────────────────────

    def test_diverse_is_different_genre_from_best(self):
        result = self.selector.select_candidates(
            current_track_id="trk_techno",
            session_state="warmup",
            target_energy=0.5,
        )
        if result.best and result.diverse:
            best_genre = CandidateSelector._get_genre(
                self.tracks.get(result.best.track_id, {})
            )
            diverse_genre = CandidateSelector._get_genre(
                self.tracks.get(result.diverse.track_id, {})
            )
            self.assertNotEqual(best_genre, diverse_genre)

    # ── registry management ──────────────────────────────────────────────

    def test_register_and_remove_track(self):
        selector = CandidateSelector()
        self.assertEqual(selector.track_count, 0)
        selector.register_track("new_track", self.tracks["trk_house"])
        self.assertEqual(selector.track_count, 1)
        selector.remove_track("new_track")
        self.assertEqual(selector.track_count, 0)

    def test_register_batch(self):
        selector = CandidateSelector()
        selector.register_batch(self.tracks)
        self.assertEqual(selector.track_count, 5)

    # ── edge cases ───────────────────────────────────────────────────────

    def test_no_current_track_returns_neutral_results(self):
        result = self.selector.select_candidates(
            current_track_id="",
            session_state="setup",
            target_energy=0.5,
        )
        self.assertGreater(len(result.candidates), 0)

    def test_all_tracks_avoided_returns_empty(self):
        result = self.selector.select_candidates(
            avoid_ids=list(self.tracks.keys()),
            target_energy=0.5,
        )
        self.assertEqual(len(result.candidates), 0)
        self.assertEqual(result.fallback_track_id, "")

    def test_result_has_fallback(self):
        result = self.selector.select_candidates(
            current_track_id="trk_house",
            session_state="warmup",
            target_energy=0.5,
        )
        self.assertNotEqual(result.fallback_track_id, "")
        self.assertIn(result.fallback_track_id, self.tracks)

    def test_context_includes_session_info(self):
        result = self.selector.select_candidates(
            session_state="peak",
            target_energy=0.85,
            intent="hold",
        )
        self.assertEqual(result.context["session_state"], "peak")
        self.assertEqual(result.context["target_energy"], 0.85)
        self.assertEqual(result.context["intent"], "hold")


if __name__ == "__main__":
    unittest.main()
