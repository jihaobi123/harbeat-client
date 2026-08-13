import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_stem_separation.cli import main
from harbeat_stem_separation.separator import StemSeparationError


class CliTests(unittest.TestCase):
  def test_cli_reports_complete_result(self):
    with tempfile.TemporaryDirectory() as td:
      stems={name:str(Path(td)/f'{name}.wav') for name in ('vocals','drums','bass','other')}
      output=StringIO()
      with patch('harbeat_stem_separation.cli.StemSeparator.separate',return_value=stems),redirect_stdout(output):
        code=main(['song.wav',td])
    self.assertEqual(code,0); self.assertTrue(json.loads(output.getvalue())['complete'])

  def test_cli_reports_typed_failure(self):
    output=StringIO()
    with patch('harbeat_stem_separation.cli.StemSeparator.separate',side_effect=StemSeparationError('failed')),redirect_stdout(output):
      code=main(['song.wav','out'])
    self.assertEqual(code,1); self.assertEqual(json.loads(output.getvalue())['error'],'failed')
