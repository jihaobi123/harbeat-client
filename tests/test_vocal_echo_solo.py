import numpy as np
import pytest
from scripts.prepare_vocal_echo_solo import original_send_gain, render_original_send

def test_send_uses_original_fade_and_does_not_extend_dry_vocal():
    t=np.array([0,4,6,10,12,13],dtype=float)
    assert np.allclose(original_send_gain(t,4,8),[1,1,.75,.25,0,0])

@pytest.mark.parametrize('pre,duration', [(-1,8),(4,0),(float('nan'),8)])
def test_invalid_original_send_clock_rejects(pre,duration):
    with pytest.raises(ValueError):original_send_gain(np.array([0.]),pre,duration)

def test_wet_render_applies_gain_before_the_delay_without_touching_input():
    from analysis_platform.stem_effects import render_vocal_echo
    sr=16000;t=np.arange(sr*12)/sr;x=np.column_stack([np.sin(2*np.pi*500*t)*.2]*2).astype('float32');before=x.copy()
    fx=dict(sendStart=9.5,sendEnd=10,wetStart=9.75,wetEnd=10.79,taps=[dict(delaySeconds=.25,gain=.26),dict(delaySeconds=.5,gain=.117),dict(delaySeconds=.75,gain=.052)],edgeSeconds=.01,highpassHz=180,lowpassHz=5000)
    y=render_original_send(x,sr,4,8,fx);expected=render_vocal_echo(x*original_send_gain(t,4,8)[:,None],sr,fx)
    np.testing.assert_array_equal(x,before);np.testing.assert_allclose(y,expected,atol=1e-7)
    assert np.max(abs(y))>.001
    assert not y[:int(fx['wetStart']*sr)-1].any()
    assert not y[int(fx['wetEnd']*sr)+1:].any()
