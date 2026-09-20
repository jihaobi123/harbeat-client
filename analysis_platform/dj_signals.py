"""Bounded-memory DJ measurements. K-weighted windows are ungated, not integrated LUFS."""
import math
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import soundfile as sf
from scipy.signal import lfilter, butter, sosfilt
from .runner import Unavailable


def db(power):
    return float(10*np.log10(power)) if power>1e-15 else None


def ranges(rows,flags):
    out=[]
    for row,active in zip(rows,flags):
        if not active:continue
        if out and abs(out[-1]['end']-row['start'])<1e-6:out[-1]['end']=row['end']
        else:out.append({'start':row['start'],'end':row['end']})
    return out


def read_power(path,k_weight=False):
    try:
        result=_read_power(path,k_weight)
        decoder='libsndfile'
    except sf.LibsndfileError:
        original=sf.info(path)
        if not .5<=original.duration<=7200 or original.channels not in (1,2) or original.samplerate<8000:
            raise Unavailable('音频超出接歌解码范围')
        with tempfile.TemporaryDirectory(prefix='harbeat-dj-decode-') as directory:
            decoded=Path(directory)/'decoded.wav'
            command=['ffmpeg','-v','error','-xerror','-err_detect','explode','-i',str(path),
                     '-map','0:a:0','-vn','-c:a','pcm_f32le','-fs','4294967296',str(decoded)]
            process=subprocess.run(command,capture_output=True,text=True,timeout=180)
            if process.returncode:raise RuntimeError('strict fallback decoder failed: '+process.stderr[-1000:])
            actual=sf.info(decoded)
            if abs(actual.duration-original.duration)>1/original.samplerate or actual.samplerate!=original.samplerate or actual.channels!=original.channels:
                raise ValueError('fallback decoded duration / sample rate / channels differ from source')
            result=_read_power(decoded,k_weight)
        decoder='ffmpeg_pcm_f32le_strict'
    rows,info,peak,step,high=result
    metadata=SimpleNamespace(duration=info.duration,samplerate=info.samplerate,channels=info.channels,decoder=decoder)
    return rows,metadata,peak,step,high


def _read_power(path,k_weight=False):
    import pyloudnorm as pyln
    info=sf.info(path);sr=info.samplerate;channels=info.channels
    if not .5<=info.duration<=7200 or channels not in (1,2) or sr<8000:
        raise Unavailable('接歌预处理支持 0.5 秒–2 小时、采样率不低于 8kHz 的单/双声道音频')
    hop=max(1,round(sr*.05));rows=[];peak=0.;offset=0
    filters=list(pyln.Meter(sr)._filters.values()) if k_weight else []
    state=[np.zeros((2,channels)) for _ in filters]
    high=min(4000,sr*.45)
    bands={name:butter(2,cut,btype=kind,fs=sr,output='sos') for name,cut,kind in
           [('low',250,'lowpass'),('mid',[250,high],'bandpass'),('high',high,'highpass')]} if k_weight else {}
    band_states={name:np.zeros((len(sos),2,channels)) for name,sos in bands.items()}
    for chunk in sf.blocks(path,blocksize=hop*20,dtype='float64',always_2d=True):
        if not np.isfinite(chunk).all():raise ValueError('音频包含非有限采样值')
        peak=max(peak,float(np.max(np.abs(chunk))))
        weighted=chunk
        for i,f in enumerate(filters):weighted,state[i]=lfilter(f.b,f.a,weighted,axis=0,zi=state[i])
        band_audio={}
        for name,sos in bands.items():band_audio[name],band_states[name]=sosfilt(sos,chunk,axis=0,zi=band_states[name])
        for pos in range(0,len(chunk),hop):
            count=min(hop,len(chunk)-pos);part=chunk[pos:pos+count]
            row={'start':(offset+pos)/sr,'end':(offset+pos+count)/sr,'rms_dbfs':db(float(np.mean(part**2))),
                 '_frames':count,'_k_sum':float(np.sum(weighted[pos:pos+count]**2))}
            if k_weight:row['bands_dbfs']={name:db(float(np.mean(v[pos:pos+count]**2))) for name,v in band_audio.items()}
            rows.append(row)
        offset+=len(chunk)
    if offset!=info.frames:raise ValueError('decoded frame count differs from source header')
    return rows,info,peak,hop/sr,high


def windows(rows,width,stride):
    out=[]
    for i in range(0,max(0,len(rows)-width+1),stride):
        group=rows[i:i+width]
        # Last partial analysis frame cannot count as a full-width loudness window.
        if group[-1]['_frames']!=group[0]['_frames']:continue
        power=sum(p['_k_sum'] for p in group)/sum(p['_frames'] for p in group)
        level=db(power)
        out.append({'start':group[0]['start'],'end':group[-1]['end'],'lufs':level-.691 if level is not None else None})
    return out


def analyze(path,base,config):
    rows,info,peak,step,high=read_power(path,True)
    local=windows(rows,60,10);momentary=windows(rows,8,2)
    silence=ranges(rows,[p['rms_dbfs'] is None or p['rms_dbfs']<-60 for p in rows])
    vocals={'status':'unavailable','source':None,'intervals':None,'reason':base.get('stem_unavailable_reason') or '没有可读取的分离人声'}
    vp=(base.get('stem_paths') or {}).get('vocals')
    if vp:
        try:
            vr,vi,_,vstep,_=read_power(vp)
            if abs(vi.duration-info.duration)>.05:raise ValueError('人声与原曲时长相差超过 50ms，需确认对齐')
            levels=[p['rms_dbfs'] for p in vr if p['rms_dbfs'] is not None]
            enter=max(-60,min(-35,float(np.percentile(levels,95))-30)) if levels else -60
            leave=enter-6;active=False;flags=[]
            for p in vr:
                level=p['rms_dbfs']
                active=level is not None and level>(leave if active else enter);flags.append(active)
            candidates=[]
            for v in ranges(vr,flags):
                if candidates and v['start']-candidates[-1]['end']<=.100001:candidates[-1]['end']=v['end']
                else:candidates.append(v)
            candidates=[v for v in candidates if v['end']-v['start']>=.0999]
            vocals={'status':'candidate','source':'separated_vocal_rms_hysteresis_v1',
                'intervals':candidates,'coverage_sec':vi.duration,'confirmed':False,
                'asset':(base.get('stem_assets') or {}).get('vocals'),
                'parameters':{'enter_dbfs':enter,'exit_dbfs':leave,'frame_sec':vstep,'min_active_sec':.1,'merge_gap_sec':.1},
                'points':[{k:v for k,v in p.items() if not k.startswith('_')} for p in vr],
                'limitations':['能量活动不是经过校准的歌声识别；泄漏、伴唱和气声需要试听核对','时长一致不证明无固定延迟，人工确认时需核对与原曲的对齐']}
        except (ValueError,OSError,RuntimeError) as exc:vocals={'status':'unavailable','intervals':None,'reason':str(exc)}
    return {'method':'streamed_dj_signals_v1','audio_sha256':base.get('audio_sha256'),
        'decoder':info.decoder,
        'vocal_asset_id':(base.get('stem_assets') or {}).get('vocals',{}).get('id'),
        'duration':info.duration,'sample_rate':info.samplerate,'channels':info.channels,
        'time_origin':'master_audio_start','window_sec_actual':step,
        'sample_peak_dbfs':20*math.log10(peak) if peak>0 else None,'true_peak_dbTP':None,
        'local_loudness':local,'momentary_loudness':momentary,
        'rms_points':[{k:v for k,v in p.items() if not k.startswith('_')} for p in rows],
        'silence_intervals':silence,'silence_threshold_dbfs':-60,'vocals':vocals,
        'definitions':{'loudness':'K-weighted ungated channel-summed power; nominal 400ms / 3s windows, not gated integrated LUFS',
                       'bands':f'2nd-order filtered RMS: low <250Hz; mid 250–{high:g}Hz; high >{high:g}Hz; filter bands overlap',
                       'peak':'sample peak only; true peak must be measured after rendering',
                       'resolution':'50ms analysis frames; not a claim of vocal boundary accuracy'}}
