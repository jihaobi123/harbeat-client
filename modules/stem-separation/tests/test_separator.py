import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_stem_separation.separator import StemSeparationError, StemSeparator, separation_result
from harbeat_stem_separation.runner import SubprocessDemucsRunner


class FakeRunner:
  def __init__(self, callback): self.callback=callback; self.calls=[]
  def run(self, source, output_root, model, timeout_sec):
    self.calls.append((source,output_root,model,timeout_sec)); self.callback(source,output_root,model)


class SeparatorTests(unittest.TestCase):
  def test_subprocess_runner_uses_explicit_model_repository(self):
    with tempfile.TemporaryDirectory() as td:
      root=Path(td); source=root/'song.wav'; source.write_bytes(b'audio')
      repository=root/'models'; repository.mkdir(); output=root/'out'
      runner=SubprocessDemucsRunner(interpreter='python',model_repo=repository)
      with patch('harbeat_stem_separation.runner.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
        runner.run(source,output,'htdemucs',120)
      command=run.call_args.args[0]
      self.assertEqual(command[command.index('--repo')+1],str(repository.resolve()))

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

  def test_injected_runner_publishes_four_stems(self):
    with tempfile.TemporaryDirectory() as td:
      source=Path(td)/'song.wav'; source.write_bytes(b'audio'); out=Path(td)/'stems'
      def create(source_path,root,model):
        target=root/model/source_path.stem; target.mkdir(parents=True)
        for name in ('vocals','drums','bass','other'):(target/f'{name}.wav').write_bytes(b'x')
      runner=FakeRunner(create)
      result=StemSeparator(runner=runner).separate(str(source),str(out))
      self.assertEqual(set(result),{'vocals','drums','bass','other'}); self.assertEqual(len(runner.calls),1)

  def test_safe_input_adapter_publishes_to_canonical_directory(self):
    with tempfile.TemporaryDirectory() as td:
      source=Path(td)/'non_ascii_song.wav'; source.write_bytes(b'audio'); out=Path(td)/'stems'
      def create_only_for_safe(source_path,root,model):
        if source_path.parent.name != '_inputs': return
        target=root/model/source_path.stem; target.mkdir(parents=True)
        for name in ('vocals','drums','bass','other'):(target/f'{name}.wav').write_bytes(b'x')
      runner=FakeRunner(create_only_for_safe)
      result=StemSeparator(runner=runner).separate(str(source),str(out))
      self.assertTrue(all(Path(path).parent.name == 'non_ascii_song' for path in result.values()))
      self.assertEqual(len(runner.calls),2)
      self.assertFalse(runner.calls[-1][0].exists())
