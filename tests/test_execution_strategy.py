import unittest
from unittest.mock import patch
from metric_mix.strategy import strategy


class ExecutionStrategyTests(unittest.TestCase):
    def fixture(self,tid,note):
        track={'id':tid,'provenance':{'runId':'run-test','masterSha256':'a'*64,'reportSha256':'b'*64}}
        pitch=[0.]*12;pitch[note]=1.
        profile={'schema':'harbeat.execution-profile.v1','trackId':tid,'runId':'run-test',
                 'sourceSha256':'a'*64,'reportSha256':'b'*64,
                 'stems':{k:{'frames':[{'start':i*.125,'end':(i+1)*.125,'rmsDb':-20,'chroma':pitch} for i in range(32)]} for k in ['bass','other','vocals']}}
        return track,profile

    def test_data_only_plan_never_claims_waveform_checks(self):
        a,pa=self.fixture('a',0);b,pb=self.fixture('b',7)
        with patch('metric_mix.strategy.validated_plan',return_value={'start':0,'bStart':0,'duration':4,'rate':1}):
            result=strategy(a,b,'window',0,pa,pb)
        self.assertIsNone(result['renderedOutputStats'])
        self.assertTrue(result['execution']['peakProtectionRequired'])
        self.assertFalse(result['decision']['methods']['vocal']['eligible'])
        self.assertEqual(len(result['planId']),64)
        self.assertNotIn('assets',result)

    def test_stale_report_is_rejected_before_cue_validation(self):
        a,pa=self.fixture('a',0);b,pb=self.fixture('b',7);pb['reportSha256']='c'*64
        with patch('metric_mix.strategy.validated_plan') as validator:
            with self.assertRaisesRegex(ValueError,'binding mismatch'):strategy(a,b,'window',0,pa,pb)
            validator.assert_not_called()
