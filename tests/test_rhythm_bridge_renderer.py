import numpy as np
import pytest
from scripts.render_rhythm_bridge import describe_drums, validate_case

def test_measures_natural_drum_gain_without_synthesizing_loop():
    x=np.ones((44100*4,2),dtype=np.float32)*.1
    x[44100*3:]*=.2
    d=describe_drums(x,3)
    assert d['rms']>0
    assert d['beforeBridgeRms']==pytest.approx(.1)
    assert d['bridgeRms']==pytest.approx(.02)
    assert d['bridgeToEarlierRatio']==pytest.approx(.2)

@pytest.mark.parametrize('bridge',[-1,0,8,9,float('nan')])
def test_invalid_boundaries_reject_without_rendering(bridge):
    with pytest.raises(ValueError):validate_case({'pre':4,'post':8,'bridgeStart':bridge,'plan':{'start':20,'end':28,'duration':8,'rate':1,'window':{'start':40,'end':48}}})

@pytest.mark.parametrize('forged', ['report','manifest','drum'])
def test_rejects_forged_frozen_source_bindings_before_decoder(tmp_path,forged):
    import json,hashlib
    from scripts.render_rhythm_bridge import render
    sha=lambda data:hashlib.sha256(data).hexdigest()
    nas=tmp_path/'nas';run=nas/'published/tracks/track/runs/run';run.mkdir(parents=True)
    reports=tmp_path/'reports';reports.mkdir();report=b'{}';(reports/'report.json').write_bytes(report)
    master={'sha256':'master'};vocal={'sha256':'vocal'};drum={'sha256':'drum'}
    m=json.dumps({'track_id':'track','analysis_run_id':'run','assets':{'master':master,'stems':{'vocals':vocal,'drums':drum}}}).encode()
    (run/'manifest.json').write_bytes(m);(run/'_SUCCESS.json').write_text(json.dumps({'manifest_sha256':sha(m)}))
    t={'id':'track','title':'track','reportId':'report','provenance':{'runId':'run','reportSha256':sha(report),'masterSha256':'master','vocalSha256':'vocal'},'drumSha256':'drum','manifestSha256':sha(m)}
    if forged=='report':t['provenance']['reportSha256']='forged'
    elif forged=='manifest':t['manifestSha256']='forged'
    else:t['drumSha256']='forged'
    selection=tmp_path/'selection.json';selection.write_text(json.dumps({'tracks':[t]}))
    with pytest.raises(ValueError,match='frozen report|source binding'):render(selection,nas,reports,tmp_path/'output')
