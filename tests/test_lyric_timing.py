import unittest

from analysis_platform.lyric_timing import assess_entry, build_lyric_timeline, match_lrclib, parse_lrc


class LyricTimingTest(unittest.TestCase):
    def test_line_tags_words_repeats_and_credits(self):
        lines = parse_lrc(
            "[00:00.000]作词 : Test\n[00:01.00]混⾳ : Test\n"
            "[00:03.37]<00:03.42>春<00:03.61>天\n"
            "[00:07.00][00:11.000]第二句\n[00:13.00] ",
            15_000,
        )
        self.assertEqual([line["startMs"] for line in lines], [3370, 7000, 11000])
        self.assertEqual(lines[0]["wordStartsMs"], [3420, 3610])
        self.assertEqual(lines[0]["text"], "春天")
        self.assertEqual(lines[-1]["nextMarkMs"], 13000)
        self.assertNotIn("endMs", lines[-1])

    def test_acoustic_evidence_and_partial_entry(self):
        timeline = build_lyric_timeline(
            "[00:03.370]春天到了\n[00:05.450]还有很远\n[00:08.000]明天见",
            10_000, [{"start_ms": 3420, "end_ms": 6800}],
        )
        self.assertEqual(timeline["lines"][0]["acousticOnsetMs"], 3420)
        self.assertIsNone(timeline["lines"][1]["acousticOnsetMs"])
        self.assertEqual(timeline["lines"][2]["evidence"], "no_detected_vocal")
        self.assertEqual(assess_entry(timeline, 4050)["kind"], "mid_line")
        self.assertEqual(assess_entry(timeline, 2400)["kind"], "before_line")
        self.assertEqual(assess_entry(timeline, 7200)["kind"], "unverified")

    def test_ambiguity_and_unlisted_voice_stay_visible(self):
        timeline = build_lyric_timeline(
            "[00:03.00]第一句\n[00:03.00]translation\n[00:06.00]第二句",
            10_000, [{"start_ms": 500, "end_ms": 1900}, {"start_ms": 3050, "end_ms": 4200}],
        )
        self.assertEqual(timeline["lines"][0]["evidence"], "ambiguous_text")
        self.assertEqual(timeline["voiceBeforeFirstLineMs"], 1400)
        self.assertEqual(assess_entry(timeline, 3200)["kind"], "unverified")

    def test_upcoming_line_does_not_hide_current_partial_line(self):
        timeline = build_lyric_timeline(
            "[00:03]第一句\n[00:05]第二句",
            10_000, [{"start_ms": 3040, "end_ms": 4500}, {"start_ms": 5020, "end_ms": 6500}],
        )
        self.assertEqual(assess_entry(timeline, 4000)["kind"], "mid_line")

    def test_lrclib_record_identity_includes_album_and_duration(self):
        result = dict(id=5, trackName="Song", artistName="Singer", albumName="Album",
                      duration=100, syncedLyrics="[00:02.00]Test")
        self.assertTrue(match_lrclib(result, "SONG", "Singer", "Album", 101.5))
        self.assertFalse(match_lrclib(result, "Song", "Singer", "Live", 100))
        self.assertFalse(match_lrclib(result, "Song", "Singer", "Album", 103))
        self.assertFalse(match_lrclib({**result, "syncedLyrics": None}, "Song", "Singer", "Album", 100))
