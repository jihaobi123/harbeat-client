import numpy as np
import pytest,subprocess
from scripts.render_melody_yield import stretch_pair

def test_joint_four_channel_stretch_preserves_master_other_relation(tmp_path):
    sr=44100;t=np.arange(sr*2)/sr;other=(np.sin(2*np.pi*233*t)*.12).astype('<f4');paths=[]
    for name,factor in [('master',2),('other',1)]:
        p=tmp_path/(name+'.wav');pcm=np.column_stack([other*factor,other*factor])
        subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar',str(sr),'-ac','2','-i','pipe:0','-c:a','pcm_f32le',str(p)],input=pcm.astype('<f4').tobytes(),check=True);paths.append(p)
    x=stretch_pair(paths,.1,.8,1.03)
    assert x.shape==(round(.8*sr),4)
    assert np.max(np.abs(x[:,:2]-2*x[:,2:]))<1e-6
    assert np.sqrt(np.mean(x[:,2:]**2))>.05

def test_invalid_source_range_rejects_before_decoder():
    for args in [(-1,1,1),(0,0,1),(0,1,float('nan'))]:
        with pytest.raises(ValueError):stretch_pair([], *args)
