from pathlib import Path
import importlib.util
import pytest
ROOT=Path(__file__).resolve().parents[1]
def module():
 p=ROOT/'scripts/build_realtime_assets.py'
 assert p.is_file(), 'realtime source adapter missing'
 spec=importlib.util.spec_from_file_location('rtassets',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_windows_use_recorded_bars_and_never_extrapolate():
 m=module();bars=[10,12.4,14.8,17.2,19.6,22,24.4,26.8,29.2,31.6,34,36.4,38.8]
 ws=m.windows(bars,[{'start':0,'end':14,'label':'intro'},{'start':14,'end':100,'label':'verse'}],100)
 assert ws and all(w['start'] in bars and w['end'] in bars for w in ws)
 assert all(w['start']>=10 for w in ws)
 assert all(w['end']+12<=100 for w in ws)

def test_vocal_binding_rejects_wrong_run_and_unknown_status():
 m=module();core={'track_id':'a','analysis_run_id':'run','assets':{'stems':{'vocals':{'sha256':'s'}}}}
 vocal={'source':{'track_id':'a','analysis_run_id':'other','vocal_sha256':'s'},'status':'ready','intervals':[]}
 with pytest.raises(ValueError):m.verify_vocals(core,vocal)
 vocal['source']['analysis_run_id']='run';assert m.verify_vocals(core,vocal)==[]

def test_encoder_recovers_incomplete_asset_and_keeps_exact_duration(tmp_path):
 import numpy as np
 import soundfile as sf
 m=module();source=tmp_path/'source.wav';dest=tmp_path/'asset.flac'
 sf.write(source,np.zeros((44100,2)),44100);dest.write_bytes(b'failed previous run')
 result=m.encode(source,dest,'atrim=end=0.3,asetpts=PTS-STARTPTS',[])
 assert result['frames']==13230 and result['sha256']==m.sha(dest)


def test_encoder_rebuilds_when_filter_or_source_changes(tmp_path):
 import numpy as np
 import soundfile as sf
 m=module();source=tmp_path/'source.wav';dest=tmp_path/'asset.flac';commands=[]
 sf.write(source,np.zeros((44100,2)),44100)
 first=m.encode(source,dest,'atrim=end=0.3',commands)
 same=m.encode(source,dest,'atrim=end=0.3',commands)
 assert commands[-1]['reused'] and first['sha256']==same['sha256']
 changed=m.encode(source,dest,'atrim=end=0.5',commands)
 assert changed['frames']==22050 and not commands[-1]['reused']
 sf.write(source,np.ones((44100,2))*.2,44100)
 replaced=m.encode(source,dest,'atrim=end=0.5',commands)
 assert replaced['sha256']!=changed['sha256'] and not commands[-1]['reused']
