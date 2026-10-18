import copy
import pytest
from scripts.prepare_cut_handover import validate_cut_boundary

def example():
 return dict(pre=4,post=8,baselineBass='reference',endpoint=dict(tailEnd=6.2,nextOnset=10),plan=dict(start=10,end=18,duration=8,rate=1,window=dict(start=20,end=28),decision=dict(cues=dict(aExit=dict(nearestRawBar=dict(sourceSec=18,distanceSec=0))))))

def test_original_raw_bar_and_vocal_gap_accept_without_moving_inputs():
 c=example();before=copy.deepcopy(c);validate_cut_boundary(c,dict(bars=[10,12,14,16,18]),.005);assert c==before

@pytest.mark.parametrize('mutation', ['rawbar','tail','reentry','bass','clock'])
def test_rejects_unbound_bar_or_unsafe_voice_before_packaging(mutation):
 c=example();a=dict(bars=[10,12,14,16,18])
 if mutation=='rawbar':a['bars']=[10,12,14,16]
 elif mutation=='tail':c['endpoint']['tailEnd']=7.98
 elif mutation=='reentry':c['endpoint']['nextOnset']=8.02
 elif mutation=='bass':c['baselineBass']='stem'
 else:c['plan']['end']=18.2
 with pytest.raises(ValueError):validate_cut_boundary(c,a,.005)
