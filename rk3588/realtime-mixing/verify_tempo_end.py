"""After the eight-track integration test, verify the final fade reaches EOF."""
import json
import time
from realtime import BASE, CONTROL, rpc

state=rpc({'cmd':'get_state'},path=CONTROL)
assert state['active_asset']['final_track']
assert state['engine']['paused'] and not state['engine']['in_transition']
before=state['engine']['audio_xrun_count']
rpc({'cmd':'seek','sec':state['engine']['duration_sec']-9})
rpc({'cmd':'start','request_id':'end-test-'+str(time.time_ns())},path=CONTROL)
deadline=time.monotonic()+12
while time.monotonic()<deadline:
    state=rpc({'cmd':'get_state'},path=CONTROL)
    if not state['active'] and not state['engine']['playing']:
        break
    time.sleep(0.1)
report=dict(ended=not state['active'] and not state['engine']['playing'],
    final_track=state['active_asset']['final_track'],xrun_delta=state['engine']['audio_xrun_count']-before,
    diagnostic_seek=True,physical_audio_verified=False,at=time.time())
report['status']='passed' if report['ended'] and report['xrun_delta']==0 else 'failed'
(BASE/'reports/tempo_end_test.json').write_text(json.dumps(report,indent=2))
rpc({'cmd':'reset_session','request_id':'end-cleanup-'+str(time.time_ns())},path=CONTROL)
print(json.dumps(report))
assert report['status']=='passed'
