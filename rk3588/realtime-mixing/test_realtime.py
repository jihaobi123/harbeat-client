import unittest
from realtime import exit_candidates, Controller


def manifest(windows=None):
    return {'source': {'duration_ms': 120000}, 'analysis': {
        'transition_windows': windows if windows is not None else [
            {'role': 'out', 'start_ms': 10000, 'end_ms': 20000},
            {'role': 'both', 'start_ms': 40000, 'end_ms': 60000}],
        'sections': {'items': [{'end_ms': 30000}, {'end_ms': 80000}]}}}


class CandidateTests(unittest.TestCase):
    def test_nearest_not_125_seconds(self):
        p = exit_candidates(manifest(), range(0, 120000, 2000), 11)
        self.assertEqual(p[0], (14, 'out_window'))

    def test_multiple_points_per_window(self):
        p = exit_candidates(manifest(), range(0, 120000, 2000), 0)
        self.assertEqual([x[0] for x in p[:6]], [10,12,14,16,18,20])

    def test_passed_points_excluded(self):
        p = exit_candidates(manifest(), range(0, 120000, 2000), 21)
        self.assertEqual(p[0][0], 40)

    def test_no_snap_outside_window(self):
        m = manifest([{'role':'out','start_ms':11000,'end_ms':11500}])
        p = exit_candidates(m, range(0,120000,2000), 0)
        self.assertEqual(p[0][1], 'section_bar_fallback')

    def test_near_end_no_unsafe_cue(self):
        self.assertEqual(exit_candidates(manifest(), range(0,120000,2000), 108), [])

    def test_in_only_not_exit(self):
        m = manifest([{'role':'in','start_ms':0,'end_ms':20000}])
        self.assertEqual(exit_candidates(m, range(0,120000,2000),0)[0][1], 'section_bar_fallback')


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.engine = dict(ok=True, playing=True, paused=False, in_transition=False, current_song_id='r1')
        def call(msg):
            self.calls.append(msg)
            if msg['cmd'] == 'state':
                return dict(self.engine)
            return {'ok':True}
        self.c = Controller({'t1': {'song_id':'r1'}}, None, call)
        self.c.active = True

    def test_stop_means_pause(self):
        self.c.command({'cmd':'stop','request_id':'1'})
        self.assertEqual(self.calls[-1]['cmd'], 'pause')

    def test_resume_not_replay(self):
        self.c.command({'cmd':'start','request_id':'1'})
        self.assertEqual(self.calls[-1]['cmd'], 'resume')

    def test_duplicate_only_executes_once(self):
        m = {'cmd':'pause','request_id':'1'}
        self.c.command(m)
        self.c.command(m)
        self.assertEqual(len(self.calls),1)

    def test_request_id_conflict(self):
        self.c.command({'cmd':'pause','request_id':'1'})
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.c.command({'cmd':'start','request_id':'1'})

    def test_style_unavailable_does_not_stop(self):
        with self.assertRaisesRegex(ValueError,'style_assets'):
            self.c.command({'cmd':'set_style','style_id':'KPOP','request_id':'1'})
        self.assertEqual(self.calls,[])

    def test_gesture_is_explicitly_software(self):
        r = self.c.command({'cmd':'gesture','gesture_id':'flick_up','request_id':'1'})
        self.assertFalse(r['physical_gesture_verified'])
        self.assertEqual(self.calls[-1]['effect'], 'air_horn')

    def test_gesture_rejected_while_paused(self):
        self.engine['playing'] = False
        with self.assertRaisesRegex(ValueError,'paused'):
            self.c.command({'cmd':'gesture','gesture_id':'flick_up','request_id':'1'})

    def test_next_during_fade_rejected(self):
        self.engine['in_transition'] = True
        with self.assertRaisesRegex(ValueError,'busy'):
            self.c.command({'cmd':'next','request_id':'1'})

    def test_prefetch_flag_not_just_rpc_ok(self):
        self.c.call = lambda msg: {'ok':True,'all_ready':False,'failed':['r1']}
        with self.assertRaisesRegex(ValueError,'prefetch'):
            self.c.prepare(['t1'])


if __name__ == '__main__':
    unittest.main()
