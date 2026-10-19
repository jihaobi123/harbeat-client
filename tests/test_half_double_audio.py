import numpy as np
import pytest
from scripts.half_double_audio import validate_map,warp_shared

def test_map_has_identical_source_and_output_cues_and_safe_monotonic_local_rates():
 x=np.array([0,.5,1,1.5,2]);y=np.array([0,.53,1.04,1.52,2]);validate_map(x,y,2)
 for bad in [[.1,.5,1,1.5,2],[0,.5,.4,1.5,2],[0,.5,1,1.5,2.1],[0,.5,float('nan'),1.5,2]]:
  with pytest.raises(ValueError):validate_map(x,np.array(bad),2)
 with pytest.raises(ValueError):validate_map(x,np.array([0,.2,1,1.5,2]),2)

def test_joint_wsola_keeps_channels_coherent_and_exact_end_samples_without_normalization():
 sr=8000;t=np.arange(sr*3)/sr;a=np.sin(2*np.pi*220*t)*.3;pcm=np.column_stack([a,a*.5,a*.2,a*.1]).astype('float32');x=[0,1,2,3];y=[0,1.04,1.98,3]
 out=warp_shared(pcm,sr,x,y);assert out.shape==pcm.shape;assert np.isfinite(out).all();np.testing.assert_allclose(out[:,1],out[:,0]*.5,atol=1e-6);np.testing.assert_allclose(out[:,2],out[:,0]*.2,atol=1e-6);np.testing.assert_array_equal(out[:8],pcm[:8]);np.testing.assert_array_equal(out[-8:],pcm[-8:]);assert .8<np.sqrt(np.mean(out**2))/np.sqrt(np.mean(pcm**2))<1.2

def test_observed_impulses_move_to_mapped_pulses_and_identity_does_not_process_audio():
 sr=8000;pcm=np.zeros((sr*3,4),dtype='float32');x=np.array([0,.5,1,1.5,2,2.5,3]);y=np.array([0,.52,1.04,1.54,2.02,2.5,3]);
 for t in x[1:-1]:pcm[round(t*sr):round(t*sr)+8]=.4
 np.testing.assert_array_equal(warp_shared(pcm,sr,x,x),pcm)
 out=warp_shared(pcm,sr,x,y)
 for t in y[1:-1]:
  lo=round((t-.025)*sr);hi=round((t+.025)*sr);peak=lo+np.argmax(out[lo:hi,0]);assert abs(peak/sr-t)<.018

def test_native_clips_preserve_impulse_timing_and_adjacent_entry_body_samples(tmp_path):
 import soundfile as sf
 from scripts.render_half_double_sources import native_layers
 sr=44100;x=np.zeros((sr*4,2),dtype='float32');x[::22050]=.6;x[1::22050]=.2
 paths=[]
 for i in range(3):
  p=tmp_path/(str(i)+'.wav');sf.write(p,x*(i+1)/3,sr,subtype='FLOAT');paths.append(p)
 a=native_layers(paths,.5,2,1);body=native_layers(paths,2.5,.5,1)
 assert a.shape==(sr*2,6)
 expected=np.concatenate([x[22050:110250]*(i+1)/3 for i in range(3)],axis=1)
 np.testing.assert_array_equal(a,expected)
 np.testing.assert_array_equal(body,np.concatenate([x[110250:132300]*(i+1)/3 for i in range(3)],axis=1))
 with pytest.raises(ValueError):native_layers(paths,.5,2,1.001)

def test_native_resampling_uses_one_absolute_source_clock_not_independent_seek_filters(tmp_path):
 import soundfile as sf
 from scripts.render_half_double_sources import native_layers
 rng=np.random.default_rng(43);x=rng.normal(0,.1,(48000*3,2)).astype('float32');paths=[]
 for i in range(2):
  p=tmp_path/(str(i)+'-48.wav');sf.write(p,x,48000,subtype='FLOAT');paths.append(p)
 full=native_layers(paths,0,2,1);clip=native_layers(paths,.5013,.4997,1);start=round(.5013*44100)
 np.testing.assert_array_equal(clip,full[start:start+round(.4997*44100)])

def test_local_wsola_preserves_tonal_pitch_including_anti_phase_stereo():
 sr=8000;t=np.arange(sr*4)/sr;a=np.sin(2*np.pi*220*t)*.3;pcm=np.column_stack([a,-a,a*.2,-a*.2]).astype('float32');out=warp_shared(pcm,sr,[0,1,2,3,4],[0,1.04,1.99,3.03,4]);v=out[sr:-sr,0];spectrum=abs(np.fft.rfft(v*np.hanning(len(v))));freq=np.fft.rfftfreq(len(v),1/sr)[np.argmax(spectrum)]
 assert abs(freq-220)<=1
 assert np.sqrt(np.mean(v*v))>.9*np.sqrt(np.mean(a[sr:-sr]**2))
