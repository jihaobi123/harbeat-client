import unittest

from analysis_platform.transition_policy import select_transition
from analysis_platform.transition_policy_cli import supplement_intro


class TransitionPolicyTest(unittest.TestCase):
    def test_intro_supplement_keeps_current_analysis_and_rejects_stale_version(self):
        provenance = {"masterSha256": "source", "reportSha256": "report", "runId": "run"}
        tail = [{"start": 5, "end": 9, "beats": [5, 6, 7, 8], "valid": True}]
        track = {"id": "b", "provenance": provenance, "alignment": {"bars": tail}}
        intro = [{"start": 1, "end": 5, "beats": [1, 2, 3, 4], "valid": True}]
        proof = {"schema": "harbeat.intro-beat-evidence.v1", "producer": "jetson",
                 "trackId": "b", **provenance, "drumSupported": 5, "beatCount": 5, "bars": intro}
        self.assertEqual(supplement_intro(track, proof)["alignment"]["bars"], intro + tail)
        self.assertEqual(track["alignment"]["bars"], tail)
        with self.assertRaisesRegex(ValueError, "analysis run"):
            supplement_intro(track, {**proof, "runId": "stale"})
        with self.assertRaisesRegex(ValueError, "overwrite"):
            supplement_intro(track, {**proof, "bars": [{**intro[0], "end": 6}]})

    def test_requires_render_evidence_and_preserves_fallback(self):
        candidates = [{"method": "intro-beatmix", "verified": False}]
        self.assertEqual(select_transition(candidates, {"method": "dynamic-eq"})["method"], "dynamic-eq")

    def test_keeps_a_good_original_over_an_optional_lyric_cut(self):
        candidates = [{"method": "lyric-handover-eq", "verified": True}]
        self.assertEqual(select_transition(candidates, {"method": "dynamic-eq"})["method"], "dynamic-eq")
        self.assertEqual(select_transition(candidates, {"method": "dynamic-eq"},
                                           entry_in_lyric=True)["method"], "lyric-handover-eq")

    def test_structure_can_win_when_both_parts_are_verified(self):
        candidates = [{"method": "lyric-handover-eq", "verified": True},
                      {"method": "intro-beatmix", "verified": True}]
        self.assertEqual(select_transition(candidates, {"method": "phrase-crossfade"})["method"],
                         "intro-beatmix")
