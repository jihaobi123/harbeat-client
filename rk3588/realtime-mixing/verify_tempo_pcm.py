"""Compare staged RK callback against original v4 FFmpeg tri crossfade, no sound device."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import soundfile as sf

BASE=Path('/home/cat/harbeat-mixing-v1')
sys.path.insert(0,'/home/cat/cypher/audio-engine')
sys.path.insert(0,str(BASE/'engine-patch'))
from engine import AudioEngineMVP
from mix_plan import normalize_mix_plan

data=json.loads((BASE/'reports/tempo_assets_v1.json').read_text())
out=BASE/'reports/tempo-pcm-comparison'
out.mkdir(exist_ok=True)
rows=[]
previous=data['starts'][data['order'][0]]
for i,(a,b) in enumerate(zip(data['order'],data['order'][1:])):
    pair=data['pairs'][a+'|'+b]
    incoming=pair['final_song_id'] if i==len(data['order'])-2 else pair['song_id']
    aa,bb=data['assets'][previous],data['assets'][incoming]
    assert hashlib.sha256(Path(aa['path']).read_bytes()).hexdigest()==aa['sha256']
    assert hashlib.sha256(Path(bb['path']).read_bytes()).hexdigest()==bb['sha256']
    rate=44100
    cue=round(45.123*rate)
    fade=round(pair['fade_sec']*rate)
    reference=out/f'{i+1:02d}_v4_reference.wav'
    # Same acrossfade=d:tri:tri as the supplied render_crossfaded_mix.
    filters=(f'[0:a]atrim=start_sample={cue-rate}:end_sample={cue+fade},asetpts=PTS-STARTPTS[a];'
             f'[1:a]atrim=end_sample={fade+rate},asetpts=PTS-STARTPTS[b];'
             f'[a][b]acrossfade=d={pair["fade_sec"]:.3f}:c1=tri:c2=tri[out]')
    subprocess.run(['ffmpeg','-y','-v','error','-i',aa['path'],'-i',bb['path'],
                    '-filter_complex',filters,'-map','[out]','-c:a','pcm_s16le',str(reference)],check=True)
    e=AudioEngineMVP(); e._ensure_stream=lambda:None
    e.play(previous,(cue-rate)/rate,load_stems=False)
    e._plan=normalize_mix_plan(dict(tracks=[previous,incoming],transitions=[dict(
        from_song_id=previous,to_song_id=incoming,from_at_sec=cue/rate,to_at_sec=0,
        fade_sec=pair['fade_sec'],fade_curve='linear',style='smooth')]))
    e._plan_enabled=True
    e.inactive_deck.load(incoming,0,load_stems=False)
    e._next_preloaded=True
    output=np.zeros((fade+2*rate,2),dtype=np.float32)
    for offset in range(0,len(output),512):
        block=output[offset:offset+512]
        e._callback(block,len(block),None,None)
    expected,sr=sf.read(str(reference),dtype='float32',always_2d=True)
    assert expected.shape==output.shape
    diff=output-expected
    result=dict(pair=i+1,from_track=a,to_track=b,entry_rate=pair['rate'],fade_sec=pair['fade_sec'],
        max_abs_error=float(np.max(np.abs(diff))),rms_error=float(np.sqrt(np.mean(diff**2))),
        callback_after_song=e.active_deck.song_id,callback_after_position=e.active_deck.pos_sec,
        source_assets_sha256=[aa['sha256'],bb['sha256']])
    result['passed']=result['max_abs_error']<0.00015 and e.active_deck.song_id==incoming and abs(e.active_deck.pos_sec-(pair['fade_sec']+1))<1/rate
    sf.write(str(out/f'{i+1:02d}_rk_callback.wav'),output,rate,subtype='PCM_16')
    rows.append(result)
    print(json.dumps(result),flush=True)
    previous=incoming
report=dict(status='passed' if all(r['passed'] for r in rows) else 'failed',checks=rows,
    source='v4 prepared segments vs FFmpeg tri acrossfade',physical_audio_verified=False,
    whole_set_bit_identical=False,created_at=time.time())
(BASE/'reports/tempo_pcm_comparison.json').write_text(json.dumps(report,indent=2))
assert report['status']=='passed',report
