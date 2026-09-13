"""Source-layout contracts; no database, network or inference is required."""
import ast
from importlib import import_module
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
MOVES = json.loads((ROOT / "docs/repository/moves-20260913.json").read_text())["moves"]


@pytest.mark.parametrize("move", MOVES, ids=lambda row: row["new_path"])
def test_moved_implementation_and_old_entry_policy(move):
    assert (ROOT / move["new_path"]).is_file()
    ast.parse((ROOT / move["new_path"]).read_text())
    old = ROOT / move["old_path"]
    if move["old_entry"] == "forwarding_only":
        tree = ast.parse(old.read_text())
        assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                       for node in ast.walk(tree)), "old entry must not keep a second implementation"
    else:
        assert not old.exists()


@pytest.mark.parametrize("old,new", [
    ("app.modules.library.same_style_preprocess", "preprocessing.publisher"),
    ("app.modules.library.vocal_activity", "preprocessing.vocal_activity"),
    ("scripts.run_same_style_preprocess", "preprocessing.cli.run_same_style_preprocess"),
    ("scripts.import_same_style_library", "preprocessing.cli.import_same_style_library"),
    ("scripts.backfill_vocal_activity", "preprocessing.cli.backfill_vocal_activity"),
    ("scripts.validate_vocal_activity", "preprocessing.cli.validate_vocal_activity"),
    ("scripts.export_vocal_activity_bundle", "preprocessing.cli.export_vocal_activity_bundle"),
    ("scripts.finalize_vocal_activity", "preprocessing.cli.finalize_vocal_activity"),
])
def test_compatibility_import_uses_same_module_object(old, new):
    assert import_module(old) is import_module(new)


@pytest.mark.parametrize("script", [
    path for move in MOVES if move["new_path"].startswith("preprocessing/cli/")
    for path in (move["old_path"], move["new_path"])
])
def test_cli_help_from_unrelated_working_directory(script, tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / script), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable entrypoints")
@pytest.mark.parametrize("script", [
    "scripts/run_same_style_preprocess.py", "scripts/import_same_style_library.py",
    "preprocessing/cli/run_same_style_preprocess.py", "preprocessing/cli/import_same_style_library.py",
])
def test_executable_entrypoints_keep_shebang_and_permissions(script, tmp_path):
    path = ROOT / script
    assert path.read_text().startswith("#!/usr/bin/env python3\n")
    assert os.access(path, os.X_OK)
    environment = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    result = subprocess.run([str(path), "--help"], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_importing_publishers_does_not_load_models_or_database(tmp_path):
    code = (
        "import sys; sys.path.insert(0, " + repr(str(ROOT)) + "); "
        "import preprocessing.publisher, preprocessing.vocal_activity; "
        "assert 'torch' not in sys.modules; "
        "assert 'sqlalchemy' not in sys.modules; "
        "assert 'app.shared.database' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_active_sources_do_not_import_removed_research_paths():
    old_modules = {row["old_path"][:-3].replace("/", ".") for row in MOVES
                   if row["old_entry"] != "forwarding_only"}
    for directory in ("app", "preprocessing", "research", "scripts", "tests"):
        for path in (ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                imported = []
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported = [node.module or ""]
                    imported += [f"{node.module}.{alias.name}" for alias in node.names]
                assert not old_modules.intersection(imported), str(path)


def test_jetson_launchers_select_canonical_cli():
    expectations = {
        "run-same-style-preprocess": "preprocessing/cli/run_same_style_preprocess.py",
        "run-same-style-library-import": "preprocessing/cli/import_same_style_library.py",
        "run-vocal-activity-backfill": "preprocessing/cli/backfill_vocal_activity.py",
    }
    for filename, target in expectations.items():
        assert target in (ROOT / "deploy/jetson" / filename).read_text()


@pytest.mark.parametrize("module", [
    "preprocessing.cli.run_same_style_preprocess",
    "preprocessing.cli.backfill_vocal_activity",
    "preprocessing.cli.validate_vocal_activity",
    "preprocessing.cli.export_vocal_activity_bundle",
    "preprocessing.cli.finalize_vocal_activity",
])
def test_relocated_cli_keeps_schema_and_document_root(module):
    assert import_module(module).ROOT == ROOT
