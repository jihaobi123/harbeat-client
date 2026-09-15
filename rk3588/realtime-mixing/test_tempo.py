import unittest
from prepare_tempo import source_time, playback_time

class TimelineTests(unittest.TestCase):
    def test_roundtrip_fast_and_slow(self):
        for rate in (0.85,1.08):
            a=dict(entry_sec=6,head_end_sec=6+16*rate,head_output_frames=16*44100)
            for t in (0,5,15.9,16,16.1,100):
                self.assertAlmostEqual(playback_time(a,source_time(a,t)),t)
    def test_original_tail_offset(self):
        a=dict(entry_sec=20,head_end_sec=38,head_output_frames=16*44100)
        self.assertEqual(source_time(a,30),52)
        self.assertEqual(playback_time(a,52),30)
    def test_no_tempo_still_accounts_for_entry_crop(self):
        a=dict(entry_sec=12,head_end_sec=12,head_output_frames=0)
        self.assertEqual(source_time(a,20),32)
        self.assertEqual(playback_time(a,32),20)
    def test_actual_head_duration_used_not_nominal_overlap(self):
        a=dict(entry_sec=0,head_end_sec=15,head_output_frames=16*44100+123)
        self.assertAlmostEqual(playback_time(a,15),16+123/44100)

if __name__=='__main__':
    unittest.main()
