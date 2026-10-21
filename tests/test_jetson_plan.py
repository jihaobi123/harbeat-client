import copy
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from tests import test_metric_gateway as fixtures


class JetsonPlanBoundaryTests(unittest.TestCase):
    def test_version_rejected_before_source_audio_access(self):
        from analysis_platform.jetson_plan import prepare_plan
        a,b=fixtures.CueValidationTest().tracks()
        with patch('analysis_platform.jetson_plan.source_assets') as source:
            with self.assertRaisesRegex(ValueError,'version'):
                prepare_plan({'a':a,'b':b,'windowId':'w','start':4,'codeVersion':'0'*64,'plannerSha256':'1'*64,'jobId':'2'*64})
            source.assert_not_called()

    def test_fake_source_and_out_of_range_cue_do_not_reach_node(self):
        from analysis_platform.jetson_plan import prepare_plan,plan_runner_version
        from metric_mix.prepare import worker_version
        a,b=fixtures.CueValidationTest().tracks()
        base={'a':a,'b':b,'windowId':'w','start':4,'codeVersion':worker_version(),'runnerVersion':plan_runner_version(),'plannerSha256':'1'*64,'jobId':'2'*64}
        with patch('analysis_platform.jetson_plan.subprocess.run') as node:
            wrong=copy.deepcopy(base);wrong['a']['provenance']['masterSha256']='0'*64
            with self.assertRaises(ValueError):prepare_plan(wrong)
            wrong=copy.deepcopy(base);wrong['start']=29
            with self.assertRaises(ValueError):prepare_plan(wrong)
            node.assert_not_called()

    def test_source_paths_do_not_come_from_job_fields(self):
        from analysis_platform.jetson_plan import prepare_plan
        with self.assertRaises(ValueError):prepare_plan({'a':{},'b':{},'path':'/private/source.wav'})

    def test_main_pcm_and_optional_three_bar_prelude_use_exact_source_ranges(self):
        import numpy as np
        from analysis_platform.jetson_plan import cli_input
        from metric_mix.prepare import validated_plan
        a,b=fixtures.CueValidationTest().tracks()
        b['windows'][0].update(start=8.,end=16.)
        plan=validated_plan(a,b,'w',8.)
        job={'jobId':'1'*64,'plannerSha256':'2'*64,'windowId':'w','start':8.}
        proof={'trackId':'x'}
        seen=[]
        def read(source,start,duration):
            seen.append((source,start,duration))
            return np.zeros((round(duration*44100),2),dtype=np.float32)
        with tempfile.TemporaryDirectory() as temp,patch('analysis_platform.jetson_plan.read_segment',side_effect=read):
            root=pathlib.Path(temp)
            production=cli_input(job,a,b,plan,{'master':'a-source'},{'master':'b-source'},proof,proof,root)
            self.assertNotIn('prelude',production)
            data=cli_input(job,a,b,plan,{'master':'a-source'},{'master':'b-source'},proof,proof,root,include_body=True)
            self.assertEqual(data['pcm']['a']['start'],8)
            self.assertEqual(data['pcm']['b']['start'],8)
            self.assertAlmostEqual(data['pcm']['b']['duration'],8.008)
            self.assertEqual(data['prelude']['leadSeconds'],6)
            self.assertEqual(data['prelude']['fadeInSeconds'],2)
            self.assertEqual(data['prelude']['holdSeconds'],4)
            self.assertEqual(data['prelude']['pcm']['a']['start'],2)
            self.assertEqual(data['prelude']['pcm']['b']['start'],2)
            for part in [*data['pcm'].values(),*data['prelude']['pcm'].values()]:
                for path in part['files'].values():
                    self.assertEqual(pathlib.Path(path).stat().st_size,round(part['duration']*44100)*2*4)
                    self.assertEqual(pathlib.Path(path).stat().st_mode&0o777,0o600)
            plan['bStart']=0
            self.assertNotIn('prelude',cli_input(job,a,b,plan,{'master':'a-source'},{'master':'b-source'},proof,proof,root,include_body=True))

    def test_profile_only_index_is_valid_but_wrong_stem_or_profile_hash_is_not(self):
        import hashlib
        from analysis_platform.jetson_plan import profile_proof
        a,_=fixtures.CueValidationTest().tracks()
        proof={'runId':'run-1','manifestSha256':'d'*64,'reportSha256':'b'*64,'assets':{'master':{'sha256':'a'*64},**{stem:{'sha256':('c' if stem=='vocals' else 'e')*64} for stem in ('drums','bass','other','vocals')}}}
        identity={'trackId':a['id'],'runId':'run-1','sourceSha256':'a'*64,'reportSha256':'b'*64,'manifestSha256':'d'*64}
        profile={**identity,'schema':'harbeat.execution-profile.v1','stems':{stem:{'sourceSha256':value['sha256']} for stem,value in proof['assets'].items() if stem!='master'}}
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);(root/'profiles').mkdir()
            raw=json.dumps(profile).encode();checksum=hashlib.sha256(raw).hexdigest()
            (root/'profiles'/(checksum+'.json')).write_bytes(raw)
            entry={**identity,'assetsReady':False,'profile':{'sha256':checksum}}
            (root/'index.json').write_text(json.dumps({'schema':'harbeat.execution-library.v1','tracks':[entry]}))
            value=profile_proof(a,proof,root)
            self.assertEqual(value['profileSha256'],checksum)
            wrong=copy.deepcopy(proof);wrong['assets']['bass']['sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'stem mismatch'):profile_proof(a,wrong,root)
            (root/'profiles'/(checksum+'.json')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'fingerprint mismatch'):profile_proof(a,proof,root)

    def test_existing_37ms_main_phase_offset_is_preserved_in_prelude(self):
        import numpy as np
        from analysis_platform.jetson_plan import cli_input,DEFAULT_NODE
        from metric_mix.prepare import validated_plan
        a,b=fixtures.CueValidationTest().tracks()
        b['windows'][0].update(start=8.,end=16.)
        plan=validated_plan(a,b,'w',8.037)
        frozen=copy.deepcopy(plan)
        job={'jobId':'1'*64,'plannerSha256':'2'*64,'windowId':'w','start':8.037}
        with tempfile.TemporaryDirectory() as temp,patch('analysis_platform.jetson_plan.read_segment',side_effect=lambda source,start,duration:np.zeros((round(duration*44100),2),np.float32)):
            data=cli_input(job,a,b,plan,{'master':'a-source'},{'master':'b-source'},{},{},pathlib.Path(temp),include_body=True)
        self.assertEqual(plan,frozen,'prelude preparation must not change the main cue')
        self.assertEqual(data['plan']['start'],8.037)
        self.assertEqual(data['plan']['end'],16.037)
        self.assertAlmostEqual(data['prelude']['leadSeconds'],6)
        self.assertAlmostEqual(data['prelude']['pcm']['a']['start'],2.037)
        self.assertAlmostEqual(data['prelude']['pcm']['b']['start'],2)
        self.assertEqual(DEFAULT_NODE,'/usr/local/bin/node')

    def test_audition_body_is_native_b_continuation_and_absent_from_production(self):
        import numpy as np
        from analysis_platform.jetson_plan import cli_input
        from metric_mix.prepare import validated_plan
        a,b=fixtures.CueValidationTest().tracks();plan=validated_plan(a,b,'w',4.)
        job={'jobId':'1'*64,'plannerSha256':'2'*64,'windowId':'w','start':4.}
        observed=[]
        def read(source,start,duration):
            observed.append((source,start,duration))
            return np.zeros((round(duration*44100),2),np.float32)
        with tempfile.TemporaryDirectory() as temp,patch('analysis_platform.jetson_plan.read_segment',side_effect=read):
            folder=pathlib.Path(temp)
            args=(job,a,b,plan,{'master':'a-source'},{'master':'b-source'},{},{},folder)
            self.assertNotIn('body',cli_input(*args)['pcm'])
            data=cli_input(*args,include_body=True)
            body=data['pcm']['body']
            self.assertEqual(body['start'],plan['bEnd'])
            self.assertEqual(body['duration'],8)
            self.assertEqual(set(body['files']),{'master'})
            path=pathlib.Path(body['files']['master'])
            self.assertEqual(path.name,'b-body.f32le')
            self.assertEqual(path.stat().st_size,44100*8*2*4)
            self.assertEqual(observed[-1],('b-source',plan['bEnd'],8))

    def test_fixed_cli_reads_private_raw_pcm_then_temporary_sources_are_removed(self):
        import hashlib
        import numpy as np
        from types import SimpleNamespace
        from analysis_platform.jetson_plan import prepare_plan,plan_runner_version
        from metric_mix.prepare import worker_version
        a,b=fixtures.CueValidationTest().tracks()
        with tempfile.TemporaryDirectory() as temp:
            cli=pathlib.Path(temp)/'planner.cjs';cli.write_text('fixed test engine')
            engine=hashlib.sha256(cli.read_bytes()).hexdigest()
            job={'a':a,'b':b,'windowId':'w','start':4,'codeVersion':worker_version(),'runnerVersion':plan_runner_version(),'plannerSha256':engine,'jobId':'2'*64}
            job['executionBindings']={side:{'trackId':job[side]['id']} for side in ('a','b')}
            paths=[]
            audition=False
            def invoke(command,**kwargs):
                self.assertEqual(command,['/fixed/node',str(cli)]+(['--audition-output',str(pathlib.Path(temp)/'audition')] if audition else []))
                data=json.loads(kwargs['input'])
                self.assertEqual(data.get('auditionSingleMethod'),'filter' if audition else None)
                self.assertEqual('body' in data['pcm'],audition)
                self.assertEqual(data['pcm']['a']['start'],4)
                self.assertEqual(data['pcm']['b']['start'],0)
                for side in data['pcm'].values():
                    paths.extend(side['files'].values())
                self.assertTrue(all(pathlib.Path(path).is_file() for path in paths))
                result={'schema':'harbeat.jetson-mix-plan.v1','id':job['jobId'],'algorithmSha256':engine,'sourceProof':data['sourceProof']}
                return SimpleNamespace(stdout=json.dumps(result).encode())
            source=lambda track,*_:({'master':'verified-source'},{'trackId':track['id']})
            with patch('analysis_platform.jetson_plan.source_assets',side_effect=source),patch('analysis_platform.jetson_plan.profile_proof',side_effect=lambda t,p,r:p),patch('analysis_platform.jetson_plan.read_segment',side_effect=lambda path,start,duration:np.zeros((round(duration*44100),2),np.float32)),patch('analysis_platform.jetson_plan.subprocess.run',side_effect=invoke):
                forged=copy.deepcopy(job);forged['executionBindings']['a']['trackId']='different-source'
                with patch('analysis_platform.jetson_plan.read_segment') as audio:
                    with self.assertRaisesRegex(ValueError,'execution binding'):
                        prepare_plan(forged,cli=cli,node='/fixed/node')
                    audio.assert_not_called()
                missing=copy.deepcopy(job);missing.pop('executionBindings')
                with patch('analysis_platform.jetson_plan.read_segment') as audio:
                    with self.assertRaisesRegex(ValueError,'execution binding'):
                        prepare_plan(missing,cli=cli,node='/fixed/node')
                    audio.assert_not_called()
                result=prepare_plan(job,cli=cli,node='/fixed/node')
                paths.clear();audition=True
                result=prepare_plan(job,cli=cli,node='/fixed/node',audition_output=pathlib.Path(temp)/'audition',audition_single_method='filter')
            self.assertEqual(result['id'],job['jobId'])
            self.assertFalse(any(pathlib.Path(path).exists() for path in paths))
            self.assertEqual(list(pathlib.Path(temp).glob('*.wav')),[])

    def test_stale_cli_hash_is_rejected_before_nas_read(self):
        from analysis_platform.jetson_plan import prepare_plan,plan_runner_version
        from metric_mix.prepare import worker_version
        a,b=fixtures.CueValidationTest().tracks()
        with tempfile.TemporaryDirectory() as temp:
            cli=pathlib.Path(temp)/'planner.cjs';cli.write_text('another engine')
            job={'a':a,'b':b,'windowId':'w','start':4,'codeVersion':worker_version(),'runnerVersion':plan_runner_version(),'plannerSha256':'1'*64,'jobId':'2'*64}
            with patch('analysis_platform.jetson_plan.source_assets') as source:
                with self.assertRaisesRegex(ValueError,'engine version mismatch'):prepare_plan(job,cli=cli)
                source.assert_not_called()

    def test_node_failure_preserves_bounded_stderr_for_private_diagnostics(self):
        import subprocess
        from analysis_platform.jetson_plan import invoke_cli
        stderr=b'CONTROL_VALIDATION /mnt/nas/private-source\n'+b'x'*50000+b'\nLAST_STACK_FRAME'
        failure=subprocess.CalledProcessError(1,['/fixed/node','/fixed/cli'],stderr=stderr)
        with patch('analysis_platform.jetson_plan.subprocess.run',side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:invoke_cli(['/fixed/node','/fixed/cli'],b'{}')
        diagnostic=str(caught.exception)
        self.assertIn('CONTROL_VALIDATION',diagnostic)
        self.assertIn('LAST_STACK_FRAME',diagnostic)
        self.assertIn('stderr truncated',diagnostic)
        self.assertLess(len(diagnostic.encode()),8500)

    def test_single_method_override_is_internal_audition_only(self):
        from analysis_platform.jetson_plan import prepare_plan
        for kwargs in ({'audition_single_method':'bass'}, {'audition_output':'/private/audition','audition_single_method':'bass_filter'}):
            with self.assertRaisesRegex(ValueError,'internal audition'):prepare_plan({},**kwargs)
        with self.assertRaisesRegex(ValueError,'fixed planning request'):
            prepare_plan({'auditionSingleMethod':'bass'})



if __name__=='__main__':unittest.main()
