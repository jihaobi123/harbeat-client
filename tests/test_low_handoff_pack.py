import copy
import pytest
from scripts.prepare_low_handoff import select_handoff

def fixture():
 return {'pre':4,'post':8,'bpm':[120,120],'baselineBass':'reference','plan':{'start':10,'end':18,'duration':8,'rate':1,'window':{'start':20,'end':28}},'evidence':{'analysis':{'bars':[8,10,12,14,16,18,20]}}}

def test_first_and_last_complete_bars_preserve_plan_and_settings():
 c=fixture();raw=copy.deepcopy(c);h=select_handoff(c);assert h=={'frequency':140,'maxCutDb':18,'rampBeats':1,'earlySource':10,'lateSource':16,'bars':[8,10,12,14,16,18,20]};assert c==raw

def test_rejects_missing_final_anchor_short_overlap_or_changed_original_clock():
 for mutate in [lambda c:c['evidence']['analysis'].update(bars=[10,18]),lambda c:c['evidence']['analysis'].update(bars=[10,12,14,16,17.9]),lambda c:c['plan'].update(end=19),lambda c:c.update(baselineBass='swap')]:
  c=fixture();mutate(c)
  with pytest.raises(ValueError):select_handoff(c)

def test_package_rejects_changed_schedule_metadata_or_missing_vocal_clips():
 from scripts.prepare_low_handoff import validate_frozen
 ref=fixture();ref.update(planSha256='frozen',sourceVerification={},assets={k:{'url':k} for k in ['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']})
 case=copy.deepcopy(ref);case['handoff']=select_handoff(ref);validate_frozen(case,ref)
 for key,value in [('bpm',[121,120]),('pre',5),('post',9),('baselineBass','swap'),('planSha256','changed'),('assets',{'aMaster':{'url':'aMaster'}})]:
  bad=copy.deepcopy(case);bad[key]=value
  with pytest.raises(ValueError):validate_frozen(bad,ref)
