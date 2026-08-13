import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_stem_separation.separator import StemSeparationError, StemSeparator, separation_result

class SeparatorTests(unittest.TestCase):
  def test_reuses_complete_existing_output_without_invoking_demucs(self):
    with tempfile.TemporaryDirectory() as td:
      source=Path(td)/'song.wav'; source.write_bytes(b'audio')
      out=Path(td)/'stems'
      canonical=out/'htdemucs'/'song'; canonical.mkdir(parents=True)
      for name in ('vocals','drums','bass','other'):(canonical/f'{name}.wav').write_bytes(b'x')
      with patch.object(StemSeparator,'_invoke') as invoke:
        result=StemSeparator().separate(str(source),str(out))
      invoke.assert_not_called(); self.assertEqual(set(result),{'vocals','drums','bass','other'})

  def test_result_marks_partial_output_failed(self):
    result=separation_result('separated',{'vocals':'v.wav'})
    self.assertFalse(result['complete']); self.assertEqual(result['status'],'failed')

  def test_missing_source_fails_before_process(self):
    with self.assertRaises(StemSeparationError): StemSeparator().separate('missing.wav','out')
