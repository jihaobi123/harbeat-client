import copy
import numpy as np
import pytest
from scripts.prepare_third_drum import plan_accent,capture_accent,validate_original

def fixture():
 c={'pre':4,'post':8,'bpm':[120,120],'baselineBass':'reference','plan':{'from':'a','to':'b','start':8,'end':12,'duration':4,'rate':1,'window':{'start':20,'end':24}}}
 donor={'id':'donor','pre':4,'plan':{'from':'c','start':18,'end':26},'loop':{'sourceStart':20,'sourceEnd':22,'metrics':{'earlierBars':[{'start':20,'end':22,'beats':[20,20.5,21,21.5],'valid':True}]}}}
 bar={'start':10,'end':12,'beats':[10,10.5,11,11.5],'valid':True}
 return c,donor,bar

def test_one_distinct_bar_with_fixed_original_cues_and_bounded_beat_mapping():
 c,d,b=fixture();raw=copy.deepcopy(c);f=plan_accent(c,d,b);assert f['start']==6 and f['finish']==8 and f['frames']==88200;assert f['rate']==1 and f['relativeGain']==.25;assert c==raw
 for change in [lambda x:x[1]['plan'].update(**{'from':'a'}),lambda x:x[2].update(beats=[10,10.6,11,11.5]),lambda x:x[2].update(end=11.8),lambda x:x[1]['loop'].update(sourceEnd=22.3)]:
  args=copy.deepcopy([c,d,b]);change(args)
  with pytest.raises(ValueError):plan_accent(*args)

def test_capture_is_finite_frame_locked_declicked_and_keeps_input():
 c,d,b=fixture();f=plan_accent(c,d,b);pcm=np.ones((12*44100,2),dtype='float32')*.2;raw=pcm.copy();out=capture_accent(pcm,44100,f,lambda x,rate,n:x[:n].copy());assert out.shape==(88200,2);assert out[0,0]==0 and out[-1,0]==0 and out[1000,0]==pytest.approx(.2);np.testing.assert_array_equal(pcm,raw)

def test_original_schedule_and_exact_six_assets_are_immutable():
 c,_,_=fixture();c.update(aTitle='A',bTitle='B',planSha256='hash',sourceVerification={},assets={k:{'url':k} for k in ['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']});x=copy.deepcopy(c);validate_original(x,c)
 for k,v in [('bpm',[121,120]),('pre',5),('post',9),('planSha256','bad'),('assets',{})]:
  y=copy.deepcopy(x);y[k]=v
  with pytest.raises(ValueError):validate_original(y,c)

def test_changed_target_selection_and_rich_snapshot_are_rejected(tmp_path):
 import hashlib,json
 from scripts.prepare_third_drum import read_frozen_snapshots,validate_selection
 path=tmp_path/'track.json';path.write_text(json.dumps({'track':{'id':'a','alignment':{'bars':[1,2]}}}));f={'richSnapshots':[{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]};assert read_frozen_snapshots(f)['a']['id']=='a';path.write_text(json.dumps({'track':{'id':'a','alignment':{'bars':[1.02,2]}}}))
 with pytest.raises(ValueError):read_frozen_snapshots(f)
 expected={'cases':[{'accent':{'targetBar':{'start':1,'beats':[1,1.25,1.5,1.75]}}}]};mutated=copy.deepcopy(expected);mutated['cases'][0]['accent']['targetBar']['start']+=.02
 with pytest.raises(ValueError):validate_selection(mutated,expected)
