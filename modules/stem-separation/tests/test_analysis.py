import os
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_stem_separation.analysis import analyze_stem_files

class AnalysisTests(unittest.TestCase):
  def test_complete_stems_have_activity_and_reconstruction_quality(self):
    sr=1000; n=8000; t=np.arange(n)/sr
    drums=.35*np.sin(2*np.pi*4*t); bass=.25*np.sin(2*np.pi*60*t); vocals=np.zeros(n); vocals[2000:]=.45*np.sin(2*np.pi*220*t[2000:]); other=.12*np.sin(2*np.pi*440*t); original=drums+bass+vocals+other
    with tempfile.TemporaryDirectory() as td:
      paths={}
      for name,audio in {"vocals":vocals,"drums":drums,"bass":bass,"other":other}.items():
        p=os.path.join(td,name+'.wav'); sf.write(p,audio,sr); paths[name]=p
      original_path=os.path.join(td,'original.wav'); sf.write(original_path,original,sr)
      result=analyze_stem_files(paths,original_path=original_path,window_sec=2.0)
    self.assertTrue(result['has_complete_stems']); self.assertTrue(result['intro_is_clean']); self.assertGreater(result['stem_quality_score'],.9)
    self.assertIn('drum_analysis', result)
    self.assertEqual(result['drum_analysis']['version'], 'drum_transcription_consensus_v2')
    self.assertIn('tom', result['drum_analysis']['events'])
    self.assertIn('cymbal', result['drum_analysis']['events'])

  def test_missing_stem_is_incomplete(self):
    with tempfile.TemporaryDirectory() as td:
      p=os.path.join(td,'vocals.wav'); sf.write(p,np.zeros(2000),1000)
      result=analyze_stem_files({'vocals':p})
    self.assertFalse(result['has_complete_stems']); self.assertEqual(result['stem_quality_profile']['completeness'],.25)
    self.assertEqual(result['drum_analysis']['status'], 'unavailable')
