from types import SimpleNamespace

import pytest

from harbeat_transition_planner.service import PlanningMode, PlanningRequest, TransitionPlanningService, validate_transition_plan


def valid_plan(source='dj_structure_precomputed_window_v2'):
    return {'pair_id':'pair-a-b','from_at_sec':14.0,'to_at_sec':8.0,'duration_sec':6.0,'default_mix':{'pair_id':'pair-a-b','from_at_sec':14.0,'to_at_sec':8.0,'duration_sec':6.0,'audio_feature_source':source}}


def test_dispatches_only_registered_mode_and_options():
    calls=[]
    def engine(previous,next_song,**options): calls.append((previous,next_song,options)); return valid_plan()
    service=TransitionPlanningService({PlanningMode.FAST:engine})
    result=service.plan(PlanningRequest(PlanningMode.FAST,'a','b',{'cursor_sec':10.0}))
    assert result['pair_id']=='pair-a-b'; assert calls==[('a','b',{'cursor_sec':10.0})]


def test_manual_modes_require_v2_and_reject_degraded_output():
    with pytest.raises(ValueError,match='precomputed v2'):
        validate_transition_plan(valid_plan('legacy'),PlanningMode.FAST)
    plan=valid_plan(); plan['default_mix']['fallback_used']=True
    with pytest.raises(ValueError,match='degraded or fallback'):
        validate_transition_plan(plan,PlanningMode.STYLE)


def test_rejects_incomplete_or_nonfinite_contract():
    with pytest.raises(ValueError,match='default_mix'):
        validate_transition_plan({},PlanningMode.DEFAULT)
    plan=valid_plan(); plan['from_at_sec']=float('nan')
    with pytest.raises(ValueError,match='from_at_sec'):
        validate_transition_plan(plan,PlanningMode.DEFAULT)
