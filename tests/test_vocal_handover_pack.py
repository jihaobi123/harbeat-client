from scripts.prepare_vocal_handover import choose_candidates

def fixture():
    cases=[];contexts=[]
    for n in range(3):
        a,b='a'+str(n),'b'+str(n)
        source=dict(vocalSha256='v',masterSha256='m',runId='r',manifestSha256='f')
        cases.append(dict(id=str(n),aTitle=a,bTitle=b,plan=dict(start=10,end=18,duration=8,window=dict(start=20,end=28),rate=1,**{'from':a,'to':b})))
        contexts.extend([dict(id=a,cueStart=10,cueEnd=18,selected=dict(tailEnd=16,fadeStart=16.5,fadeEnd=16.7,nextOnset=20),coverage=dict(start=6,end=23),source=source,report=dict(candidates=[],rejected=[])),dict(id=b,cueStart=20,cueEnd=28,selected=None,coverage=dict(start=19,end=30),source=source,report=dict(candidates=[],rejected=[]))])
    return dict(cases=cases),dict(contexts=contexts)

def test_fixed_candidate_order_and_limit_preserve_every_audit_row():
    selection,analysis=fixture();cases,audit=choose_candidates(selection,analysis)
    assert [c['id'] for c in cases]==['0','1']
    assert len(audit)==3
    assert audit[2]['eligible'] and not audit[2]['accepted']
    assert selection['cases'][0]['plan']['start']==10

def test_rejected_tail_and_incoming_activity_are_retained_without_new_cues():
    selection,analysis=fixture();analysis['contexts'][0]['selected']=None
    analysis['contexts'][3]['report']['rejected']=[dict(start=27,tailEnd=29)]
    cases,audit=choose_candidates(selection,analysis)
    assert [c['id'] for c in cases]==['2']
    assert 'actual model rejected probe' in audit[0]['reasonCode']
    assert 'incoming model activity' in audit[1]['reasonCode']
    assert audit[0]['plan']==selection['cases'][0]['plan']

def test_missing_observation_and_changed_cue_cannot_enter_pack():
    selection,analysis=fixture();analysis['contexts'][0]['coverage']['end']=17
    analysis['contexts'][2]['cueStart']=11
    cases,audit=choose_candidates(selection,analysis)
    assert [c['id'] for c in cases]==['2']
    assert 'coverage' in audit[0]['reasonCode']
    assert 'outgoing cue differs' in audit[1]['reasonCode']

def test_unavailable_context_is_a_failed_case_rather_than_silent_or_batch_failure():
    selection,analysis=fixture();analysis['contexts']=[c for c in analysis['contexts'] if c['id']!='a0']
    cases,audit=choose_candidates(selection,analysis)
    assert [c['id'] for c in cases]==['1','2']
    assert not audit[0]['eligible']
    assert audit[0]['reasonCode']=='missing-validated-context'

def test_rendered_selection_cannot_change_same_id_plan_or_gain_inputs():
    import copy
    from scripts import prepare_vocal_handover as module
    selection,_=fixture();expected=selection['cases']
    for c in expected:c.update(pre=4,post=8,relay={},timing={},baselineBass='reference',planSha256='frozen')
    check=module.validate_rendered_selection
    check(expected,copy.deepcopy(expected))
    for field in ['plan','relay','timing','pre','post','baselineBass','planSha256']:
        rendered=copy.deepcopy(expected)
        rendered[0][field]={'changed':True} if isinstance(rendered[0][field],dict) else 'changed'
        import pytest
        with pytest.raises(ValueError):check(expected,rendered)

def test_anchor_cannot_drift_from_bound_historical_case(tmp_path):
    import json,hashlib,pytest
    from scripts import prepare_vocal_handover as module
    pack=tmp_path/'pack.json';pack.write_text(json.dumps({'cases':[{'id':'anchor','baselineBass':'reference'}]}))
    reference=dict(sourcePackSha256=hashlib.sha256(pack.read_bytes()).hexdigest(),case={'id':'anchor','baselineBass':'reference'})
    check=module.bound_anchor
    assert check(tmp_path,reference)==reference['case']
    pack.write_text(json.dumps({'cases':[{'id':'anchor','baselineBass':'stem'}]}))
    with pytest.raises(ValueError):check(tmp_path,reference)
