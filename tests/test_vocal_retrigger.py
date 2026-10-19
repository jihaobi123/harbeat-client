import copy
import numpy as np
import pytest
from analysis_platform.vocal_retrigger import plan_retrigger,capture_phrase
def fixture():
 source={'masterSha256':'m','vocalSha256':'v','manifestSha256':'s','runId':'r'}
 c={'pre':4,'post':8,'baselineBass':'reference','bpm':[120,121],'plan':{'start':10,'end':18,'duration':8,'rate':1,'window':{'start':20,'end':28}},'sourceVerification':{'a':source,'b':source}}
 a={'source':source,'selected':{'start':13,'tailEnd':15},'coverage':{'start':5,'end':29},'bars':[10,14,18,22],'vad':[[13,15]],'report':{'candidates':[{'start':13,'tailEnd':15}],'rejected':[]}}
 b={'source':source,'coverage':{'start':18,'end':32},'bars':[20,24,28,32],'vad':[],'report':{'candidates':[],'rejected':[]}}
 return c,a,b
def test_uses_whole_segment_and_exact_native_handoff_without_changing_plan():
 c,a,b=fixture();raw=copy.deepcopy(c);f=plan_retrigger(c,a,b);assert f['sourceStart']==12.97 and f['sourceEnd']==15.03;assert f['trigger']==12;assert f['count']==1;assert c==raw;assert f['incomingSupport']==pytest.approx([28,30.06]);assert f['status']=='requires-human-cut-review'
def test_rejects_unobserved_or_conflicting_replay_support_and_long_segment():
 c,a,b=fixture()
 for side,key,value in [('b','coverage',{'start':18,'end':30}),('a','coverage',{'start':5,'end':20}),('b','vad',[[29,29.3]]),('b','report',{'candidates':[],'rejected':[{'start':28.5,'tailEnd':29.2}]}),('a','selected',{'start':10,'tailEnd':15}),('a','source',{'vocalSha256':'changed'})]:
  aa,bb=copy.deepcopy(a),copy.deepcopy(b);(aa if side=='a' else bb)[key]=value
  with pytest.raises(ValueError):plan_retrigger(c,aa,bb)
def test_capture_preserves_original_gain_before_replay_and_input_pcm():
 c,a,b=fixture();f=plan_retrigger(c,a,b);sr=1000;x=np.ones((12000,2),dtype='float32')*.4;raw=x.copy();out=capture_phrase(x,sr,c,f);assert out.shape==(2060,2);assert out[0,0]==0;assert out[-1,0]==0;assert out[1000,0]==pytest.approx(.4*(18-(12.97+1))/8);np.testing.assert_array_equal(x,raw)
