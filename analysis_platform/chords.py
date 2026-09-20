"""Isolated madmom DeepChroma + CRF timeline; no aesthetic or mix score."""
import json
import sys
from pathlib import Path


def normalize_segments(raw,duration):
    out=[];cursor=0.
    for start,end,label in raw:
        start=max(cursor,float(start));end=min(duration,float(end))
        if end<=start:continue
        if start>cursor+1e-6:out.append({'start':cursor,'end':start,'label':'unknown','confidence':None})
        out.append({'start':start,'end':end,'label':str(label),'confidence':None});cursor=end
    if cursor<duration:out.append({'start':cursor,'end':duration,'label':'unknown','confidence':None})
    return out


def recognize(path,base,config):
    # madmom 0.16.1 predates Python 3.10's collections migration.
    import collections,collections.abc
    for name in ['MutableSequence','MutableMapping','Mapping','Sequence']:
        if not hasattr(collections,name):setattr(collections,name,getattr(collections.abc,name))
    import hashlib
    import soundfile as sf
    import madmom
    from madmom.audio.chroma import DeepChromaProcessor
    from madmom.features.chords import DeepChromaChordRecognitionProcessor
    from madmom import models
    duration=sf.info(str(path)).duration
    if duration<.5 or duration>7200:raise ValueError('audio duration outside supported range')
    raw=DeepChromaChordRecognitionProcessor()(DeepChromaProcessor()(str(path)))
    segments=normalize_segments(raw,duration)
    labels={s['label'] for s in segments if s['label'] not in ('N','unknown')}
    model_paths=[*models.CHROMA_DNN,*models.CHORDS_DCCRF]
    model_hashes={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in model_paths}
    sha=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):sha.update(block)
    valid_seconds=sum(s['end']-s['start'] for s in segments if s['label']!='unknown')
    return {'method':'madmom_deepchroma_crf_v1','madmom_version':madmom.__version__,'audio_sha256':sha.hexdigest(),
        'model_files':model_hashes,'segments':segments,'duration':duration,'covered_seconds':valid_seconds,
        'distinct_chords':len(labels),'no_chord_seconds':sum(s['end']-s['start'] for s in segments if s['label']=='N'),
        'parameters':{'frames_per_second':10,'vocabulary':'24_major_minor_plus_N'},
        'definition':'24 major/minor triads + N; confidence unavailable. Unknown denotes uncovered audio.',
        'license':'madmom code BSD; bundled models CC-BY-NC-SA-4.0',
        'limitations':['not seventh/extended chord transcription','no listener validation on target library','not a pairwise harmonic-mix score']}


if __name__=='__main__':
    try:
        request=json.loads(Path(sys.argv[2]).read_text())
        result={'status':'ready','data':recognize(request['audio'],request['base'],request['config'])}
    except ImportError as exc:result={'status':'unavailable','reason':str(exc)}
    except Exception as exc:result={'status':'failed','reason':f'{type(exc).__name__}: {exc}'}
    Path(sys.argv[3]).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
