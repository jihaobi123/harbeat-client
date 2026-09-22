import unittest
from analysis_platform.mix_profiles import measure, style_evidence, inference_intervals, build_profiles

class ProfilesTest(unittest.TestCase):
    def test_power_average_and_gaps(self):
        rows=[{'start':0,'end':1,'rms_dbfs':-10},{'start':1,'end':2,'rms_dbfs':-20}]
        self.assertAlmostEqual(measure(rows,0,2)['dbfs'],-12.5963731,places=5)
        self.assertEqual(measure(rows,0,4)['status'],'missing')
        self.assertEqual(measure(rows+rows,0,4)['status'],'missing')

    def test_silence_and_invalid_are_distinct(self):
        self.assertEqual(measure([{'start':0,'end':4,'rms_dbfs':None}],0,4)['status'],'missing')
        self.assertEqual(measure([{'start':0,'end':4,'rms_dbfs':float('nan')}],0,4)['status'],'missing')

    def test_coarse_style_never_confirms_short_intro(self):
        segment={'start':0,'end':30,'top':[{'style':'Trap','score':.8}], 'patch_count':28}
        e=style_evidence([segment],0,6)
        self.assertEqual(e['status'],'needs_review')
        self.assertEqual(e['top'][0]['style'],'Trap')

    def test_direct_local_style_and_ambiguous_scores(self):
        seg={'start':8,'end':24,'top':[{'style':'Trap','score':.3},{'style':'Grime','score':.1}], 'patch_count':15}
        self.assertEqual(style_evidence([seg],8,24)['status'],'model_candidate')
        seg['top'][1]['score']=.295
        self.assertEqual(style_evidence([seg],8,24)['status'],'needs_review')

    def test_interval_validation(self):
        self.assertRaises(ValueError,inference_intervals,[{'start':0,'end':301}],200)
        self.assertRaises(ValueError,inference_intervals,[{'start':8,'end':2}],200)
        self.assertRaises(ValueError,inference_intervals,[{'start':0,'end':float('nan')}],200)
        self.assertEqual(inference_intervals([{'start':0,'end':6}],100),[])

    def test_geometry_and_report_identity(self):
        t={'duration':30,'reportId':'r','sections':[{'start':0,'end':15,'label':'intro'}],'windows':[], 'provenance':{'masterSha256':'original'}}
        r={'id':'r','documents':{'core':{'assets':{'master':{'sha256':'original'}},'analysis':{'sections':{'items':[{'start_ms':0,'end_ms':14000,'label':'intro'}]}}}},'extensions':{}}
        self.assertRaises(ValueError,build_profiles,r,t)
        r['id']='other'
        self.assertRaises(ValueError,build_profiles,r,t)

    def test_source_binding(self):
        t={'duration':30,'sections':[],'windows':[], 'provenance':{'masterSha256':'original'}}
        r={'id':'r','documents':{'core':{'assets':{'master':{'sha256':'original'}}}},'extensions':{'dj_signals':{'status':'ready','data':{'audio_sha256':'wrong'}}}}
        self.assertRaises(ValueError,build_profiles,r,t)

if __name__=='__main__':unittest.main()
