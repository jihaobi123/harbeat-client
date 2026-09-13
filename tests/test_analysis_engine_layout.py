"""Shared engines must stay independent of business API and DB initialization."""
import ast
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOVES = json.loads((ROOT / "docs/repository/moves-engines-20260913.json").read_text())["moves"]


def module_name(path):
    return path[:-3].replace("/", ".")


@pytest.mark.parametrize("move", MOVES, ids=lambda row: row["new_path"])
def test_old_import_is_same_object_and_has_no_implementation(move):
    tree = ast.parse((ROOT / move["old_path"]).read_text())
    assert not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   for n in ast.walk(tree))
    old = import_module(module_name(move["old_path"]))
    new = import_module(module_name(move["new_path"]))
    assert old is new


@pytest.mark.parametrize("move", MOVES, ids=lambda row: row["new_path"])
def test_engines_do_not_import_business_packages(move):
    tree = ast.parse((ROOT / move["new_path"]).read_text())
    for node in ast.walk(tree):
        imports = []
        if isinstance(node, ast.ImportFrom):
            imports = [node.module or ""]
        elif isinstance(node, ast.Import):
            imports = [a.name for a in node.names]
        assert not any(i.split(".")[0] in {"app", "fastapi", "sqlalchemy"} for i in imports)


def test_fresh_engine_import_does_not_initialize_app_or_database(tmp_path):
    code = "import sys, importlib; sys.path.insert(0, " + repr(str(ROOT)) + "); "
    code += "[importlib.import_module(m) for m in " + repr([module_name(m["new_path"]) for m in MOVES]) + "]; "
    code += "assert not any(m == 'app' or m.startswith('app.') or m == 'sqlalchemy' for m in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module,relative", [
    ("beat_model_validation", "model_validation/beat_tracking_v1.json"),
    ("tempo_model_validation", "model_validation/tempo_consensus_v1.json"),
    ("key_model_validation", "model_validation/key_estimation_v1.json"),
    ("bass_model_validation", "model_validation/bass_transcription_v1.json"),
    ("drum_model_validation", "model_validation/drum_transcription_v1.json"),
    ("feature_calibration", "feature_calibration/v1.json"),
])
def test_validation_files_still_resolve_to_repository_config(module, relative):
    path = import_module("preprocessing.engines." + module).DEFAULT_PATH
    assert path == ROOT / "config" / relative
    assert path.is_file()


def test_runtime_paths_and_shared_patch_identity(monkeypatch):
    old = import_module("app.modules.library.analysis")
    new = import_module("preprocessing.engines.analysis")
    monkeypatch.delenv("SECTION_SONGFORMER_WORK_DIR", raising=False)
    assert new._songformer_work_dir() == ROOT / ".runtime/songformer-analysis"
    marker = object()
    monkeypatch.setattr(old, "_BEAT_THIS_INFERENCE_LOCK", marker)
    assert new._BEAT_THIS_INFERENCE_LOCK is marker


def test_current_engines_do_not_select_historical_extractions():
    for folder in ("preprocessing", "music_analysis"):
        for path in (ROOT / folder).rglob("*.py"):
            source = path.read_text(encoding="utf-8-sig")
            assert "harbeat_stem_separation" not in source, path
            assert "harbeat_audio_preprocess" not in source, path


def test_publisher_imports_canonical_engines():
    source = (ROOT / "preprocessing/publisher.py").read_text()
    assert "from preprocessing.engines.analysis import analyze_audio_file" in source
    assert "from preprocessing.engines.stem_analysis import analyze_stem_files" in source
    assert "app.modules.library" not in source
