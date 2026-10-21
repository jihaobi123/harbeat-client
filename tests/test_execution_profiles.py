import unittest
import numpy as np
import json
import tempfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import soundfile as sf
from analysis_platform.execution_profiles import stem_profile, groove_profile, bar_evidence, compare_profiles, local_pair_evidence
from analysis_platform.device_export import export_track


class ExecutionProfileTests(unittest.TestCase):
    def test_silence_is_unknown_harmony_and_inactive(self):
        profile = stem_profile(np.zeros(16000), 8000)
        self.assertTrue(all(row['chroma'] is None for row in profile['frames']))
        self.assertTrue(all(not row['active'] for row in profile['frames']))

    def test_bass_pitch_is_local_and_level_independent(self):
        t = np.arange(16000) / 8000
        a = stem_profile(np.sin(2*np.pi*110*t)*.2, 8000)
        b = stem_profile(np.sin(2*np.pi*110*t)*.02, 8000)
        json.dumps(a,allow_nan=False)
        self.assertEqual(np.argmax(a['frames'][4]['chroma']), 9)
        np.testing.assert_allclose(a['frames'][4]['chroma'], b['frames'][4]['chroma'], atol=.001)

    def test_subbeat_events_are_not_odd_even_beat_intervals(self):
        sr = 8000
        x = np.zeros(sr*4)
        for at in [.0,.33,.5,.83,1,1.33,1.5,1.83,2,2.33,2.5,2.83,3,3.33,3.5,3.83]:
            offset = int(at*sr)
            x[offset:offset+80] += np.hanning(80)
        result = groove_profile(x, sr, list(np.arange(0,4.01,.5)))
        self.assertGreater(len(result['events']), 8)
        self.assertTrue(any(abs(e['phase']-.66)<.12 for e in result['events']))
        self.assertNotIn('swing_ratio',result)

    def test_incomplete_beats_are_unknown_not_perfect(self):
        result = bar_evidence({'alignment':{'bars':[{'start':0,'end':2,'beats':[0,.5,1],'valid':True}]}})
        self.assertFalse(result['bars'][0]['usable'])
        self.assertIsNone(result['bars'][0]['intervalRegularity'])

    def test_local_groove_comparison_respects_source_time_and_rate(self):
        left={'groove':{'events':[{'time':.13+i*.5,'band':'low','strength':1} for i in range(8)]}}
        right={'groove':{'events':[{'time':10+(.13+i*.5)*1.02,'band':'low','strength':1} for i in range(8)]}}
        result=local_pair_evidence(left,right,0,10,4,1.02)
        self.assertEqual(result['rhythm']['status'],'ready')
        self.assertLess(result['rhythm']['timingP95Ms'],.1)
        self.assertAlmostEqual(result['rhythm']['histogramCosine'],1)
        self.assertFalse(result['longBlendApproved'])
        self.assertIsNone(result['harmony']['other']['meanPitchDifference'])

    def test_missing_features_do_not_become_compatible(self):
        result = compare_profiles({}, {}, 0, 0, 4, 1)
        self.assertIsNone(result['bassDifference'])
        self.assertFalse(result['stemAvailable']['bass'])
        incomplete={'stems':{'bass':{'frames':[{'start':0,'end':.125,'rmsDb':-20,'chroma':[1]+[0]*11}]}}}
        partial=compare_profiles(incomplete,incomplete,0,0,4,1)
        self.assertIsNone(partial['bassDifference'])
        self.assertFalse(partial['stemAvailable']['bass'])

    def test_export_segments_share_source_timeline_and_hash_actual_bytes(self):
        from metric_mix.prepare import sha
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);x=np.zeros((18000,2));x[100:200]=.1
            paths={}
            for key in ['master','drums','bass','other','vocals']:
                paths[key]=root/(key+'.wav');sf.write(paths[key],x,8000,subtype='PCM_24')
            proof={'trackId':'track-test','runId':'run-test','manifestSha256':'a'*64,'reportSha256':'b'*64,
                   'assets':{k:{'sha256':sha(v)} for k,v in paths.items()}}
            with patch('analysis_platform.device_export.source_assets',return_value=(paths,proof)):
                result=export_track({'id':'track-test','reportId':'b'*64,'alignment':{'bars':[]}},root,root,root/'out',chunk_seconds=1)
            self.assertTrue(result['assetsReady'])
            track=json.loads((root/'out/tracks/track-test.json').read_text())
            for stem in track['stems'].values():
                self.assertEqual([(s['startFrame'],s['endFrame']) for s in stem['segments']],[(0,8000),(8000,16000),(16000,18000)])
                for segment in stem['segments']:
                    self.assertEqual(sha(root/'out/objects'/(segment['asset']['sha256']+'.flac')),segment['asset']['sha256'])
            self.assertNotIn(str(root),json.dumps(track))
            checksum=track['stems']['bass']['segments'][0]['asset']['sha256']
            corrupted=root/'out/objects'/(checksum+'.flac')
            corrupted.write_bytes(b'corrupted')
            with patch('analysis_platform.device_export.source_assets',return_value=(paths,proof)):
                export_track({'id':'track-test','reportId':'b'*64,'alignment':{'bars':[]}},root,root,root/'out',chunk_seconds=1)
            self.assertEqual(sha(corrupted),checksum)

    def test_master_sample_grid_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);paths={}
            for key in ['master','drums','bass','other','vocals']:
                paths[key]=root/(key+'.wav')
                sf.write(paths[key],np.zeros((8001 if key=='master' else 8000,2)),8000)
            with patch('analysis_platform.device_export.source_assets',return_value=(paths,{})):
                with self.assertRaisesRegex(ValueError,'identical sample durations'):
                    export_track({'id':'track-test','reportId':'b'*64},root,root,root/'out')

    def test_equal_rational_duration_allows_different_master_rate(self):
        from metric_mix.prepare import sha
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);paths={}
            for key in ['master','drums','bass','other','vocals']:
                paths[key]=root/(key+'.wav');rate=16000 if key=='master' else 8000
                sf.write(paths[key],np.zeros((rate,2)),rate)
            proof={'trackId':'track-test','runId':'run-test','manifestSha256':'a'*64,'reportSha256':'b'*64,
                   'assets':{k:{'sha256':sha(v)} for k,v in paths.items()}}
            with patch('analysis_platform.device_export.source_assets',return_value=(paths,proof)):
                export_track({'id':'track-test','reportId':'b'*64},root,root,root/'out')
            track=json.loads((root/'out/tracks/track-test.json').read_text())
            self.assertEqual(track['masterSampleGrid']['sampleRate'],16000)
            self.assertEqual(track['sampleRate'],8000)

    def test_failed_refresh_retires_old_ready_advertisement(self):
        from analysis_platform.device_export import main
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'out';(out/'tracks').mkdir(parents=True);(root/'details').mkdir()
            (root/'library.json').write_text(json.dumps({'tracks':[{'id':'track-test','detailUrl':'details/track-test.json'}]}))
            (root/'details/track-test.json').write_text(json.dumps({'track':{'id':'track-test'}}))
            (out/'index.json').write_text(json.dumps({'tracks':[{'trackId':'track-test','assetsReady':True}]}))
            (out/'tracks/track-test.json').write_text('{}')
            with patch('sys.argv',['export','--library',str(root),'--output',str(out)]):main()
            self.assertFalse((out/'tracks/track-test.json').exists())
            self.assertEqual(json.loads((out/'index.json').read_text())['tracks'],[])

    def test_two_requested_track_exports_do_not_lose_each_others_index_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'details').mkdir();out=root/'out'
            rows=[{'id':name,'detailUrl':'details/'+name+'.json'} for name in ['track-a','track-b']]
            (root/'library.json').write_text(json.dumps({'tracks':rows}))
            for row in rows:(root/row['detailUrl']).write_text(json.dumps({'track':{'id':row['id']}}))
            code='''import sys,time,pathlib
from analysis_platform import device_export as m
def fake(track,*args,**kwargs):
 time.sleep(.15)
 return {'trackId':track['id'],'assetsReady':False,'profile':{},'bytes':0}
m.export_track=fake
sys.argv=['export','--library',sys.argv[1],'--output',sys.argv[2],'--track-id',sys.argv[3]]
m.main()
'''
            workers=[subprocess.Popen([sys.executable,'-c',code,str(root),str(out),row['id']],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for row in rows]
            for worker in workers:
                stdout,stderr=worker.communicate(timeout=30)
                self.assertEqual(worker.returncode,0,stderr.decode())
            self.assertEqual({r['trackId'] for r in json.loads((out/'index.json').read_text())['tracks']},{'track-a','track-b'})

