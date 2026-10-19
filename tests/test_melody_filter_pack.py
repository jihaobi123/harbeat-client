import copy,hashlib
import numpy as np
import pytest
import soundfile as sf
from scripts.prepare_melody_filter import validate_bindings,checked_asset
def test_rejects_stale_other_manifest_report_or_swapped_track_binding():
 c={'sourceCaseId':'old','plan':{'from':'a','to':'b'},'sourceVerification':{'a':{'otherSha256':'o','manifestSha256':'m','reportSha256':'r'},'b':{'otherSha256':'ob','manifestSha256':'mb','reportSha256':'rb'}}};row={'id':'old','fromTrack':'a','toTrack':'b','bindings':copy.deepcopy(c['sourceVerification'])};validate_bindings(c,row)
 for key in ['otherSha256','manifestSha256','reportSha256']:
  bad=copy.deepcopy(row);bad['bindings']['a'][key]='changed'
  with pytest.raises(ValueError):validate_bindings(c,bad)
 with pytest.raises(ValueError):validate_bindings(c,dict(row,fromTrack='b'))
def test_rejects_changed_or_wrong_clock_cached_pcm(tmp_path):
 def asset(sr=44100):
  p=tmp_path/'a.wav';sf.write(p,np.zeros((sr,2),dtype='float32'),sr,subtype='FLOAT');return dict(url='/a.wav',bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 a=asset();assert checked_asset(tmp_path,a,1)==tmp_path/'a.wav'
 with pytest.raises(ValueError):checked_asset(tmp_path,dict(a,sha256='changed'),1)
 with pytest.raises(ValueError):checked_asset(tmp_path,a,2)
 with pytest.raises(ValueError):checked_asset(tmp_path,asset(48000),1)
 with pytest.raises(ValueError):checked_asset(tmp_path,dict(a,url='/../escape.wav'),1)
