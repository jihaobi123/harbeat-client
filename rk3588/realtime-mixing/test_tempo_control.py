import unittest
from types import SimpleNamespace
from tempo_control import TempoController


class TempoControlTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.s=dict(ok=True,current_song_id='rtv2-start-a',position_sec=30,
                    in_transition=False,playing=True,paused=False)
        def call(msg):
            self.calls.append(msg)
            if msg['cmd']=='state':
                return dict(self.s)
            return dict(ok=True,all_ready=True)
        def asset(t):
            return dict(track_id=t,entry_sec=10,head_end_sec=26,head_output_frames=16*44100,
                        frames=110*44100,sha256='verified')
        assets={}; starts={}; pairs={}; catalog={}
        for t in 'abc':
            sid='rtv2-start-'+t; starts[t]=sid; assets[sid]=asset(t)
            catalog[t]=dict(song_id=sid,manifest_sha256=t,intervals=[],bars=list(range(0,120000,2000)),
                manifest={'source':{'duration_ms':120000},'analysis':{
                    'transition_windows':[{'role':'out','start_ms':20000,'end_ms':110000}],
                    'sections':{'items':[]}}})
        for a in 'abc':
            for b in 'abc':
                if a==b: continue
                sid='rtv2-'+a+b; assets[sid]=asset(b); assets[sid+'-final']=asset(b)
                pairs[a+'|'+b]=dict(song_id=sid,final_song_id=sid+'-final',rate=0.96,fade_sec=16,
                    method='mix_blend',tempo_relation='direct',restore_mode='v4_head_then_original_tail')
        index=dict(order=list('abc'),starts=starts,pairs=pairs,assets=assets,manifests={t:t for t in 'abc'})
        v4=SimpleNamespace(choose_exit_cue=lambda *a,**k:SimpleNamespace(time_ms=80000))
        self.c=TempoController(catalog,v4,call,index)
        self.c.active=True; self.c.visited=['a']

    def test_original_time_converted_for_engine(self):
        p=self.c.schedule('one')['pending']
        self.assertEqual(p['from_at_sec'],44)
        self.assertEqual(p['from_playback_at_sec'],34)
        self.assertEqual(p['to_at_sec'],10)
        self.assertEqual(p['to_playback_at_sec'],0)
        self.assertEqual(p['entry_rate'],0.96)
        self.assertEqual(self.calls[-1]['mix_plan']['transitions'][0]['from_at_sec'],34)

    def test_final_variant_for_last_remaining_song(self):
        self.c.visited=['a','b']
        self.assertTrue(self.c.schedule('last')['pending']['incoming_song_id'].endswith('-final'))

    def test_default_order_matches_index(self):
        self.assertEqual(self.c.schedule('one')['pending']['to_track_id'],'b')

    def test_explicit_next(self):
        self.assertEqual(self.c.schedule('one',target='c')['pending']['to_track_id'],'c')

    def test_auto_prefers_original_v4_cue(self):
        self.assertEqual(self.c.schedule('one',auto=True)['pending']['from_at_sec'],80)

    def test_state_source_time(self):
        self.assertEqual(self.c.state()['source_position_sec'],40)

    def test_end_has_no_unsafe_candidate(self):
        self.s['position_sec']=100
        with self.assertRaisesRegex(ValueError,'no_future'):
            self.c.schedule('one')

    def test_busy_rejected(self):
        self.s['in_transition']=True
        with self.assertRaisesRegex(ValueError,'busy'):
            self.c.schedule('one')

    def test_idempotent_pending(self):
        first=self.c.schedule('one')['pending']
        again=self.c.schedule('two')
        self.assertEqual(again['status'],'already_scheduled')
        self.assertEqual(again['pending'],first)

    def test_entrance_speed_phase_not_interrupted(self):
        self.s['position_sec']=0
        self.assertGreaterEqual(self.c.schedule('one')['pending']['from_at_sec'],26)


if __name__=='__main__':
    unittest.main()
