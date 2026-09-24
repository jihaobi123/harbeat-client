"""Continuous corpus contracts: accounting, source identity and exact media recipes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import shutil
import unittest
from unittest.mock import patch
import copy
import hashlib

SPEC = importlib.util.spec_from_file_location('continuous_library', Path(__file__).parents[1] / 'scripts/build_continuous_library.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class ContinuousLibraryTests(unittest.TestCase):
    def test_runtime_section_end_clips_only_millisecond_representation_error(self):
        rows=[{'start_ms':0,'end_ms':193788,'label':'outro'}]
        duration=193.7879365079365
        original=copy.deepcopy(rows)
        result=MODULE.runtime_sections(rows,duration)
        self.assertEqual(result[0]['end'],duration)
        self.assertEqual(rows,original)
        self.assertEqual(MODULE.runtime_sections([{'start_ms':0,'end_ms':193800,'label':'bad'}],duration)[0]['end'],193.8)

    def test_alignment_scope_uses_observed_vocal_coverage_only_within_one_sample(self):
        track={'duration':126.77420833333333}
        signals={'vocals':{'coverage_sec':126.77419501133786}}
        self.assertEqual(MODULE.alignment_duration(track,signals),signals['vocals']['coverage_sec'])
        self.assertEqual(MODULE.alignment_duration(track,{'vocals':{'coverage_sec':120}}),track['duration'])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
    def test_48khz_source_is_sample_bound_after_native_resampling(self):
        import soundfile as sf
        import numpy as np
        class Registry:
            def register(self,path,sha):return {'id':sha}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.wav';out=root/'out';out.mkdir()
            frames=48_000*151+17
            samples=np.sin(np.arange(frames)*2*np.pi*439/48000)*.3
            sf.write(source,np.column_stack([samples,samples]),48000,subtype='PCM_16')
            reference=root/'reference.wav'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(source),'-ar','44100','-ac','2','-c:a','pcm_s16le',str(reference)],check=True)
            track={'id':'b','duration':frames/48000,'bpm':120,'mixStatus':'unavailable','provenance':{'masterSha256':MODULE.file_sha(source)},'windows':[]}
            result,_=MODULE.build_track(track,source,[],MODULE.Renderer(out,Registry()),out)
            self.assertEqual(result['playStatus'],'ready')
            self.assertEqual(result['duration'],sf.info(reference).duration)
            by_hash={json.loads(path.read_text())['sha256']:path.with_suffix('.flac') for path in (out/'media').glob('*.json')}
            self.assertEqual(len(result['audioSegments']),6)
            rendered=np.concatenate([sf.read(by_hash[s['asset']['sha256']],dtype='int16')[0] for s in result['audioSegments']])
            np.testing.assert_array_equal(rendered,sf.read(reference,dtype='int16')[0])

    def test_segments_cover_full_sample_timeline_without_rounding_gaps(self):
        frames = 193 * 44100 + 123
        rows = MODULE.segment_bounds(frames, 44100)
        self.assertEqual(rows[0], (0, 30 * 44100))
        self.assertEqual(rows[-1][1], frames)
        self.assertEqual(rows[1][0], rows[0][1])
        self.assertTrue(all(b > a for a,b in rows))
        self.assertEqual(sum(b-a for a,b in rows), frames)
        self.assertEqual(MODULE.segment_bounds(74*44100,44100), [(0,30*44100),(30*44100,60*44100),(60*44100,74*44100)])

    def test_all_entries_remain_and_manual_labels_are_not_model_style(self):
        items=[{'track_id':'one','title':'One','source_collection':'KPOP','style_labels':['manual-pop']},
               {'track_id':'two','title':'Two','source_collection':'EDM','style_labels':['manual-edm']}]
        tracks={'one': {'id':'one','title':'One','bpm':100,'duration':201,'style':'House','mixStatus':'ready','playStatus':'ready'}}
        index=MODULE.library_index(items,tracks,{'two':'missing source'},'/details/')
        self.assertEqual(len(index['tracks']),2)
        a,b=index['tracks'];self.assertEqual(a['style'],'House');self.assertEqual(a['collection'],'KPOP')
        self.assertEqual(a['styleLabels'],['manual-pop']);self.assertEqual(b['mixStatus'],'unavailable')
        self.assertEqual(b['reason'],'missing source');self.assertEqual(index['coverage']['indexed'],2)

    def test_null_optional_genre_keeps_track_and_original_report_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'master.wav';source.write_bytes(b'verified-master')
            item={'track_id':'one','analysis_run_id':'run1','title':'One','source_collection':'KPOP','style_labels':['KPOP']}
            core={'track_id':'one','analysis_run_id':'run1','assets':{'master':{'storage_key':'master.wav','sha256':MODULE.file_sha(source),'duration_ms':20000},'stems':{'vocals':{'sha256':'vocals'}}},
                'analysis':{'tempo':{'bpm':120},'beat_grid':{'bars_ms':list(range(0,20001,2000))},
                    'sections':{'source':'model','items':[{'start_ms':0,'end_ms':20000,'label':'verse'}]},
                    'energy':{'curve':[{'start_ms':0,'end_ms':20000,'value':.5}]}}}
            vad={'status':'ready','unit':'ms','time_origin':'master_audio_start','intervals':[{'start_ms':1000,'end_ms':2000}],
                 'source':{'track_id':'one','analysis_run_id':'run1','vocal_sha256':'vocals'}}
            report={'id':'report1','documents':{'core':core,'vocal_activity':vad},
                'extensions':{'genre':{'status':'failed','data':None},'dj_signals':{'status':'ready','data':{'duration':20,'vocals':{}}}}}
            original=copy.deepcopy(report);raw=json.dumps(report).encode()
            with patch('analysis_platform.phrase_alignment.analyze_alignment',return_value={'status':'candidate','bandFrames':[{'start':0,'end':20}]}):
                track,_=MODULE.prepare_track(item,copy.deepcopy(core),raw,report,root,root/'out','/public/')
            self.assertEqual(report,original)
            self.assertEqual(track['provenance']['reportSha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(track['preprocessing']['reportSha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(track['preprocessing']['genre'],{})
            self.assertEqual(track['mixStatus'],'ready');self.assertEqual(track['style'],'unknown:one')

    def test_failed_native_retains_metadata_without_ready_count_or_detail_link(self):
        item={'track_id':'one','title':'One','source_collection':'KPOP','style_labels':['KPOP']}
        prepared={'one':{'id':'one','title':'One','duration':200,'bpm':120,'style':'unknown:one','mixStatus':'ready','playStatus':'unavailable'}}
        index=MODULE.library_index([item],{}, {'one':'native output unavailable'},'/details/',prepared=prepared)
        row=index['tracks'][0]
        self.assertEqual(row['duration'],200);self.assertEqual(row['bpm'],120);self.assertIsNone(row['detailUrl'])
        self.assertEqual(row['playStatus'],'unavailable');self.assertEqual(row['mixStatus'],'unavailable')
        self.assertEqual(index['coverage']['playable'],0);self.assertEqual(index['coverage']['mixReady'],0)
        self.assertEqual(row['reason'],'native output unavailable')

    def test_latest_report_must_match_master_and_analysis_run(self):
        item={'track_id':'one','analysis_run_id':'run1'}
        manifest={'track_id':'one','analysis_run_id':'run1','assets':{'master':{'sha256':'a'}}}
        good={'id':'good','created_at':'2020','audio':{'catalog_track_id':'one','sha256':'a'}}
        wrong={'id':'wrong','created_at':'2030','audio':{'catalog_track_id':'one','sha256':'b'}}
        self.assertEqual(MODULE.report_candidates(item,manifest,{'good':good,'wrong':wrong}),[good])
        with self.assertRaisesRegex(ValueError,'run'):
            MODULE.bind_core(item,manifest,{'track_id':'one','analysis_run_id':'run2','assets':{'master':{'sha256':'a'}}})

    def test_recipe_deduplicates_equal_bpms_but_not_sources(self):
        w={'start':10.,'end':14.,'bars':2}
        recipe_a=MODULE.variant_recipe('sha1',w,120.)
        recipe_b=MODULE.variant_recipe('sha1',w,120.)
        self.assertEqual(recipe_a,recipe_b)
        self.assertNotEqual(MODULE.recipe_key(recipe_a),MODULE.recipe_key(MODULE.variant_recipe('sha2',w,120.)))
        self.assertIn('atempo=1.000000000',recipe_a['filter'])
        self.assertIn('apad=whole_dur=4.000000000,atrim=end=4.000000000',recipe_a['filter'])

    def test_cached_asset_requires_recipe_size_and_hash(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'asset.flac';path.write_bytes(b'good');recipe={'x':1}
            meta={'recipe':recipe,'bytes':4,'sha256':MODULE.file_sha(path),'duration':1}
            path.with_suffix('.json').write_text(json.dumps(meta))
            self.assertEqual(MODULE.cached_asset(path,recipe),meta)
            path.write_bytes(b'evil');self.assertIsNone(MODULE.cached_asset(path,recipe))
            path.write_bytes(b'good');self.assertIsNone(MODULE.cached_asset(path,{'x':2}))

    def test_ordinary_windows_must_leave_body_in_native_prefix(self):
        track={'duration':400,'nativeDuration':150,'bars':list(range(0,401,2)),
               'sections':[{'start':0,'end':60,'label':'intro'},{'start':88,'end':400,'label':'verse'}]}
        rows=MODULE.entry_windows(track)
        self.assertTrue(rows)
        self.assertTrue(all(w['start'] < 90 and w['end']+12 <= 150 for w in rows))
        self.assertEqual({w['bars'] for w in rows},{2,4})

    def test_native_playback_survives_entry_render_failure(self):
        import soundfile as sf
        import numpy as np
        class Renderer:
            calls=0
            def render(self,source,recipes):
                self.calls+=1
                if self.calls==2:raise ValueError('entry output unavailable')
                return {MODULE.recipe_key(r):{'url':'/native','sha256':'n','bytes':100,'duration':20,'recipe':r} for r in recipes}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.wav';sf.write(source,np.zeros((20*44100,2)),44100,subtype='PCM_16')
            track={'id':'b','duration':20,'bpm':120,'mixStatus':'ready','provenance':{'masterSha256':'source'},
                'windows':[{'start':0,'end':4,'bars':2,'variants':{}}]}
            result,timing=MODULE.build_track(track,source,[{'id':'a','bpm':120}],Renderer(),root)
            self.assertEqual(result['playStatus'],'ready');self.assertEqual(result['mixStatus'],'unavailable')
            self.assertIn('entry output unavailable',result['reason']);self.assertEqual(result['windows'],[])
            self.assertEqual(result['audioSegments'][0]['end'],20)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
    def test_batch_matches_accepted_atempo_samples(self):
        import soundfile as sf
        import numpy as np
        class Registry:
            def register(self,path,sha):return {'id':sha}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mp3=root/'source.mp3';decoded=root/'decoded.wav'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
                'sine=frequency=439:sample_rate=44100:duration=9','-ac','2','-c:a','libmp3lame',str(mp3)],check=True)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(mp3),'-c:a','pcm_s16le',str(decoded)],check=True)
            recipes=[MODULE.variant_recipe(MODULE.file_sha(mp3),{'start':1.123,'end':5.427,'bars':2},bpm) for bpm in (100.,110.,120.)]
            output=root/'output';output.mkdir()
            renderer=MODULE.Renderer(output,Registry());assets=renderer.render(mp3,[*recipes,recipes[0]])
            self.assertEqual(len(assets),3);self.assertEqual(renderer.built,3)
            for i,recipe in enumerate(recipes):
                direct=root/('direct'+str(i)+'.flac')
                subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(mp3),'-af',recipe['filter'],
                    '-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16','-frame_size','4096',str(direct)],check=True)
                result=output/'media'/(MODULE.recipe_key(recipe)+'.flac')
                np.testing.assert_array_equal(sf.read(direct,dtype='int16')[0],sf.read(result,dtype='int16')[0])
            renderer.render(mp3,recipes);self.assertEqual(renderer.built,3)

if __name__ == '__main__':unittest.main()
