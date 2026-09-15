import unittest
from control_api import API_VERSION,translate_event,route

class ContractTests(unittest.TestCase):
    def event(self,**fields):
        return dict(schema_version=API_VERSION,source='simulator',device_id='wrist',
                    boot_id='boot1',event_id='1',action='next',**fields)

    def test_deterministic_id(self):
        self.assertEqual(translate_event(self.event()),translate_event(self.event()))
    def test_boot_id_distinguishes_reboots(self):
        a=self.event(); b=dict(a,boot_id='boot2')
        self.assertNotEqual(translate_event(a)['request_id'],translate_event(b)['request_id'])
    def test_device_id_distinguishes_devices(self):
        a=self.event(); b=dict(a,device_id='other')
        self.assertNotEqual(translate_event(a)['request_id'],translate_event(b)['request_id'])
    def test_action_not_part_of_identity(self):
        a=self.event(); b=dict(a,action='pause')
        self.assertEqual(translate_event(a)['request_id'],translate_event(b)['request_id'])
    def test_unknown_action(self):
        with self.assertRaisesRegex(ValueError,'invalid_action'):
            translate_event(dict(self.event(),action='shutdown'))
    def test_no_parameter_injection(self):
        with self.assertRaisesRegex(ValueError,'unknown_parameter'):
            translate_event(self.event(params={'request_id':'override'}))
    def test_required_parameter(self):
        with self.assertRaisesRegex(ValueError,'missing_style_id'):
            translate_event(dict(self.event(),action='set_style'))
    def test_bad_version(self):
        with self.assertRaisesRegex(ValueError,'schema'):
            translate_event(dict(self.event(),schema_version='v2'))
    def test_non_dict(self):
        with self.assertRaises(ValueError):
            translate_event([])
    def test_stop_preserved(self):
        self.assertEqual(translate_event(dict(self.event(),action='stop'))['cmd'],'stop')
    def test_capabilities_honest(self):
        code,d=route('GET','/v1/capabilities',{},lambda m:None)
        self.assertEqual(code,200)
        self.assertFalse(d['tempo_stretch'])
        self.assertFalse(d['physical_input_implemented_here'])
    def test_capabilities_follow_running_tempo_mode(self):
        _,d=route('GET','/v1/capabilities',{},lambda m:{'mode':'live_dual_deck_vocal_v4_tempo'})
        self.assertTrue(d['tempo_stretch'])
        self.assertFalse(d['smooth_16_bar_restore'])
    def test_gesture_forwarded(self):
        seen=[]
        def backend(m):
            seen.append(m); return {'ok':True}
        route('POST','/v1/device-events',dict(self.event(),action='gesture',params={'gesture_id':'punch_forward'}),backend)
        self.assertEqual(seen[0]['cmd'],'gesture')
        self.assertEqual(seen[0]['gesture_id'],'punch_forward')
    def test_unknown_path(self):
        code,_=route('POST','/v1/erase',{},lambda m:None)
        self.assertEqual(code,404)

    def test_diagnostic_requires_id(self):
        with self.assertRaisesRegex(ValueError,'request_id_required'):
            route('POST','/v1/commands',{'cmd':'pause'},lambda m:None)

    def test_diagnostic_rejects_extra_params(self):
        with self.assertRaisesRegex(ValueError,'unknown_parameter'):
            route('POST','/v1/commands',{'cmd':'next','request_id':'1','unexpected':True},lambda m:None)

    def test_diagnostic_reset_valid(self):
        code,result=route('POST','/v1/commands',{'cmd':'reset_session','request_id':'1'},lambda m:{'ok':True})
        self.assertEqual(code,200)
        self.assertEqual(result['request_id'],'1')

if __name__=='__main__':
    unittest.main()
