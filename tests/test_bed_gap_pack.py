import copy
import pytest
from scripts.prepare_bed_gap import validate_gap_boundary

def example():
 return dict(pre=4,post=8,bpm=[120,120],baselineBass='reference',endpoint=dict(tailEnd=6.2,nextOnset=10),plan=dict(start=10,end=18,duration=8,rate=1,window=dict(start=20,end=28),decision=dict(cues=dict(aExit=dict(nearestRawBar=dict(sourceSec=18,distanceSec=0))))))

def test_halfbeat_gap_uses_original_bpm_and_leaves_frozen_inputs_unchanged():
 c=example();before=copy.deepcopy(c);assert validate_gap_boundary(c,dict(bars=[10,12,14,16,18]),.005,.5)==.25;assert c==before

@pytest.mark.parametrize('mutation',['late-tail','reentry','no-bar','bad-bpm','changed-clock','extra-bass'])
def test_rejects_unsafe_or_unbound_pause_without_recue(mutation):
 c=example();a=dict(bars=[10,12,14,16,18])
 if mutation=='late-tail':c['endpoint']['tailEnd']=7.8
 elif mutation=='reentry':c['endpoint']['nextOnset']=8.01
 elif mutation=='no-bar':a['bars']=[10,12,14,16]
 elif mutation=='bad-bpm':c['bpm'][0]=float('nan')
 elif mutation=='changed-clock':c['plan']['end']=18.2
 else:c['baselineBass']='stem'
 with pytest.raises(ValueError):validate_gap_boundary(c,a,.005,.5)
