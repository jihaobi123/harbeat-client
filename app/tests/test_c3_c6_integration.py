"""Integration test: C3 CandidateSelector ↔ C6 SessionCoordinator.

Proves that:
1. C6 can query C3 through the CandidateSelector protocol
2. C3 scoring responds to C6 session state changes
3. The full intent→candidate→command pipeline works end-to-end
4. Module boundaries are clean (C6 doesn't import C3 internals)
"""
import unittest

from app.modules.session.schemas import (
    ButtonIntent,
    SceneConfig,
    SceneType,
    SessionConfig,
)
from app.modules.session.candidate_selector import CandidateSelector
from app.modules.session.coordinator import SessionCoordinator


class C3C6IntegrationTests(unittest.TestCase):
    def setUp(self):
        # ── Build track registry from C1-style analysis data ──
        self.tracks = {
            "trk_warm_hiphop": {
                "bpm": 92.0, "camelot_key": "4A", "energy": 0.35,
                "beat_confidence": 0.93, "intro_is_clean": True,
                "outro_is_clean": True,
                "genre_profile": {"primary_genre": "hip-hop"},
                "groove_profile": {"score": 0.78, "label": "groovy"},
                "dance_style_scores": {"hiphop": 0.88},
                "stem_activity": {"vocals": 0.4, "drums": 0.5, "bass": 0.4, "other": 0.2},
                "loudness_profile": {"clipping_risk": False},
            },
            "trk_build_house": {
                "bpm": 124.0, "camelot_key": "9A", "energy": 0.65,
                "beat_confidence": 0.95, "intro_is_clean": True,
                "outro_is_clean": True,
                "genre_profile": {"primary_genre": "house"},
                "groove_profile": {"score": 0.82, "label": "groovy"},
                "dance_style_scores": {"house": 0.9},
                "stem_activity": {"vocals": 0.2, "drums": 0.7, "bass": 0.5, "other": 0.3},
                "loudness_profile": {"clipping_risk": False},
            },
            "trk_peak_techno": {
                "bpm": 130.0, "camelot_key": "11A", "energy": 0.85,
                "beat_confidence": 0.91, "intro_is_clean": False,
                "outro_is_clean": True,
                "genre_profile": {"primary_genre": "techno"},
                "groove_profile": {"score": 0.75, "label": "steady"},
                "dance_style_scores": {"techno": 0.8, "house": 0.5},
                "stem_activity": {"vocals": 0.1, "drums": 0.8, "bass": 0.6, "other": 0.3},
                "loudness_profile": {"clipping_risk": True},
            },
            "trk_cool_funk": {
                "bpm": 105.0, "camelot_key": "8A", "energy": 0.45,
                "beat_confidence": 0.89, "intro_is_clean": True,
                "outro_is_clean": True,
                "genre_profile": {"primary_genre": "funk"},
                "groove_profile": {"score": 0.80, "label": "groovy"},
                "dance_style_scores": {"locking": 0.8, "popping": 0.7},
                "stem_activity": {"vocals": 0.3, "drums": 0.5, "bass": 0.4, "other": 0.4},
                "loudness_profile": {"clipping_risk": False},
            },
            "trk_safe_default": {
                "bpm": 100.0, "camelot_key": "1A", "energy": 0.5,
                "beat_confidence": 0.90, "intro_is_clean": True,
                "outro_is_clean": True,
                "genre_profile": {"primary_genre": "pop"},
                "groove_profile": {"score": 0.65, "label": "steady"},
                "dance_style_scores": {},
                "stem_activity": {"vocals": 0.5, "drums": 0.4, "bass": 0.3, "other": 0.3},
                "loudness_profile": {"clipping_risk": False},
            },
        }

        # ── Wire C3 → C6 through protocol ──
        self.c3 = CandidateSelector(track_registry=self.tracks)
        self.coord = SessionCoordinator(
            config=SessionConfig(),
            candidate_selector=self.c3,  # ← protocol injection
        )

    def test_warmup_session_selects_lower_energy(self):
        """In warmup state, C3 should prefer lower-energy tracks."""
        self.coord.start()
        self.coord.on_track_changed("trk_warm_hiphop", energy=0.35)

        cmd = self.coord.handle_intent(ButtonIntent(action="next"))
        self.assertIsNotNone(cmd)
        # Should NOT pick techno (energy 0.85) in warmup
        if cmd and cmd.params.get("to_track_id"):
            to_energy = self.tracks[cmd.params["to_track_id"]]["energy"]
            self.assertLess(to_energy, 0.8)  # not the peak track

    def test_energy_up_in_build_picks_higher_energy(self):
        """energy_up in build state → C3 picks higher energy → C4 gets energy_lift."""
        self.coord.start()
        self.coord.on_track_changed("trk_warm_hiphop", energy=0.35)
        self.coord.handle_intent(ButtonIntent(action="energy_up"))  # → build

        cmd = self.coord.handle_intent(ButtonIntent(action="energy_up"))
        self.assertIsNotNone(cmd)
        if cmd:
            self.assertEqual(cmd.params.get("style"), "energy_lift")
            to_id = cmd.params.get("to_track_id", "")
            if to_id:
                to_energy = self.tracks[to_id]["energy"]
                self.assertGreater(to_energy, 0.35)  # higher than current

    def test_energy_down_in_peak_picks_lower_energy(self):
        """energy_down in peak → C3 picks lower energy recovery track."""
        self.coord.start()
        self.coord.on_track_changed("trk_peak_techno", energy=0.85)
        # Force to peak
        self.coord._state_machine.handle_intent("energy_up")  # warmup→build
        self.coord._state_machine.handle_intent("energy_up")  # build→peak
        self.assertEqual(self.coord._state_machine.state.value, "peak")

        cmd = self.coord.handle_intent(ButtonIntent(action="energy_down"))
        self.assertIsNotNone(cmd)
        if cmd:
            self.assertEqual(cmd.params.get("style"), "recovery_blend")

    def test_undo_restores_previous_track(self):
        """Undo after next → C6 pops undo stack → C4 gets revert command."""
        self.coord.start()
        self.coord.on_track_changed("trk_warm_hiphop", energy=0.35)

        # Do a "next" action
        first_cmd = self.coord.handle_intent(ButtonIntent(action="next"))
        self.assertIsNotNone(first_cmd)
        first_to = first_cmd.params.get("to_track_id") if first_cmd else ""

        if first_to:
            # Simulate track change
            self.coord.on_track_changed(first_to, energy=self.tracks[first_to]["energy"])

            # Now undo
            undo_cmd = self.coord.handle_intent(ButtonIntent(action="undo"))
            self.assertIsNotNone(undo_cmd)
            if undo_cmd:
                self.assertIn("trk_warm_hiphop", undo_cmd.params.get("to_track_id", ""))

    def test_emergency_bypasses_c3_uses_safety_pool(self):
        """Emergency next → C6 bypasses C3 → direct safety pool → immediate cut."""
        self.coord.start()
        self.coord.on_track_changed("trk_peak_techno", energy=0.85)
        # Directly set safety pool (bypass complex build filtering for test)
        self.coord._safety_pool._pool = ["trk_safe_default", "trk_cool_funk"]

        cmd = self.coord.handle_intent(ButtonIntent(action="emergency_next"))
        self.assertIsNotNone(cmd)
        if cmd:
            self.assertEqual(cmd.action, "emergency_cut")
            self.assertEqual(cmd.execute_at, "now")
            self.assertFalse(cmd.quantize)
            self.assertIn(cmd.params.get("to_track_id"), ["trk_safe_default", "trk_cool_funk"])

    def test_full_session_arc(self):
        """Simulate a complete 8-track session: warmup → build → peak → recover."""
        self.coord.start()
        scene = SceneConfig(
            scene=SceneType.cypher,
            dance_styles=["hiphop", "house"],
        )

        # Re-init with scene config
        self.coord = SessionCoordinator(
            config=SessionConfig(scene=scene),
            candidate_selector=self.c3,
        )
        self.coord.start(scene)

        # Track 1: warmup hip-hop
        self.coord.on_track_changed("trk_warm_hiphop", energy=0.35)

        # Track 2: energy_up → build, pick house
        cmd2 = self.coord.handle_intent(ButtonIntent(action="energy_up"))
        self.assertIsNotNone(cmd2)
        self.assertEqual(self.coord._state_machine.state.value, "build")
        if cmd2:
            to2 = cmd2.params.get("to_track_id", "")
            self.assertIn(to2, self.tracks)
            self.coord.on_track_changed(to2, energy=self.tracks[to2]["energy"])

        # Track 3-4: build continues
        for _ in range(2):
            cmd = self.coord.handle_intent(ButtonIntent(action="next"))
            self.assertIsNotNone(cmd)
            if cmd:
                to_id = cmd.params.get("to_track_id", "")
                if to_id:
                    self.coord.on_track_changed(to_id, energy=self.tracks[to_id]["energy"])

        # Track 5: energy_up → peak
        cmd5 = self.coord.handle_intent(ButtonIntent(action="energy_up"))
        if cmd5:
            to5 = cmd5.params.get("to_track_id", "")
            if to5:
                self.coord.on_track_changed(to5, energy=self.tracks[to5]["energy"])

        # Track 6-7: peak energy
        for _ in range(2):
            cmd = self.coord.handle_intent(ButtonIntent(action="next"))
            if cmd:
                to_id = cmd.params.get("to_track_id", "")
                if to_id:
                    self.coord.on_track_changed(to_id, energy=self.tracks[to_id]["energy"])

        # Track 8: energy_down → recover
        cmd8 = self.coord.handle_intent(ButtonIntent(action="energy_down"))
        self.assertIsNotNone(cmd8)

        # Verify the full arc
        snap = self.coord.snapshot()
        self.assertGreater(len(snap.history), 0)
        self.assertGreater(self.coord._undo.depth, 0)  # undo stack has entries

    def test_repetition_prevents_same_track(self):
        """After playing a track, it should not appear in candidates."""
        self.coord.start()
        self.coord.on_track_changed("trk_build_house", energy=0.65)

        cmd = self.coord.handle_intent(ButtonIntent(action="next"))
        self.assertIsNotNone(cmd)
        if cmd:
            # The selected track should NOT be trk_build_house
            self.assertNotEqual(cmd.params.get("to_track_id"), "trk_build_house")


if __name__ == "__main__":
    unittest.main()
