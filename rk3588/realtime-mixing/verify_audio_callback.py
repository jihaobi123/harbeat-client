"""Same deployed DSP callback, isolated engine instance, no sound device opened.

Produces evidence of nonzero audio/FX, NOT proof of microphone/earphone sound.
"""
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,'/home/cat/cypher/audio-engine')
from engine import AudioEngineMVP
from config import SAMPLE_RATE

base=Path('/home/cat/harbeat-mixing-v1')
e=AudioEngineMVP()
e._ensure_stream=lambda:None
sid=json.loads((base/'reports/realtime_aliases.json').read_text())[0]['song_id']
e.play(sid,10,load_stems=False)
results=[]
def render(n):
    out=np.zeros((n,2),dtype=np.float32)
    for pos in range(0,n,512):
        e._callback(out[pos:pos+512],len(out[pos:pos+512]),None,None)
    return out

a=render(44100)
results.append({'check':'music_nonzero','passed':float(np.max(np.abs(a)))>0.01})
e.pause()
b=render(44100)
results.append({'check':'paused_pcm_silent','passed':float(np.max(np.abs(b)))==0})
e.resume()
results.append({'check':'resumed_pcm_nonzero','passed':float(np.max(np.abs(render(44100))))>0.01})
for effect in ('snare_impact','air_horn','beat_stutter','bass_drop'):
    sample=e.ring_samples[effect]
    result=e.trigger_effect(effect)
    audio=render(44100)
    results.append({'check':'effect_'+effect,'passed':result.get('action')=='one_shot' and
                    float(np.max(np.abs(sample)))>0.01 and np.isfinite(audio).all().item(),
                    'sample_peak':float(np.max(np.abs(sample)))})
    e._one_shot_keys.clear()
report={'status':'passed' if all(i['passed'] for i in results) else 'failed','checks':results,
        'test_mode':'isolated_actual_callback_no_physical_output','physical_gesture_verified':False}
(base/'reports/realtime_pcm_test.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
assert report['status']=='passed'
