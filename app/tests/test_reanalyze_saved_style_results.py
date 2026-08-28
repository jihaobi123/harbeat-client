from pathlib import Path

import pytest

from scripts.reanalyze_saved_style_results import _reanalyze


def test_reanalyze_rejects_missing_saved_source_and_stems(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="source audio unavailable"):
        _reanalyze({"file": str(tmp_path / "missing.wav"), "stems": {}})


def test_reanalyze_reports_missing_stem_names(tmp_path: Path):
    source = tmp_path / "source.wav"
    source.touch()
    bass = tmp_path / "bass.wav"
    bass.touch()
    with pytest.raises(FileNotFoundError, match="vocals, drums, other"):
        _reanalyze({"file": str(source), "stems": {"bass": str(bass)}})
