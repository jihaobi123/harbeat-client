"""Guard the small entry-point archive without importing heavyweight models."""

import ast
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_archived_entrypoints_are_not_default_scripts():
    for old, new in (
        ("experiments/run_allinone_isolated.py", "archive/analysis-v1/run_allinone_isolated.py"),
        ("scripts/backfill_vocal_events.py", "archive/analysis-v1/backfill_vocal_events.py"),
    ):
        assert not (ROOT / old).exists()
        assert (ROOT / new).is_file()
        ast.parse((ROOT / new).read_text(encoding="utf-8"))


def test_archived_vocal_script_still_resolves_repository_root():
    previous_path = sys.path[:]
    try:
        module = runpy.run_path(str(ROOT / "archive/analysis-v1/backfill_vocal_events.py"))
        assert module["ROOT"] == ROOT
        assert callable(module["backfill_vocal_events"])
    finally:
        sys.path[:] = previous_path


def test_production_songformer_entry_is_retained():
    assert (ROOT / "preprocessing/runners/songformer.py").is_file()
    analysis = (ROOT / "preprocessing/engines/analysis.py").read_text(encoding="utf-8")
    deployment = (ROOT / "deploy/jetson/run-same-style-preprocess").read_text(encoding="utf-8")
    assert '"preprocessing" / "runners" / "songformer.py"' in analysis
    assert "preprocessing/runners/songformer.py" in deployment
    assert (ROOT / "experiments/run_songformer_isolated.py").is_file()


def test_new_vocal_entry_and_old_referenced_implementation_are_retained():
    assert (ROOT / "preprocessing/cli/backfill_vocal_activity.py").is_file()
    assert (ROOT / "app/modules/library/analysis_vocal_patch_gpu.py").is_file()
    source = (ROOT / "preprocessing/cli/run_same_style_preprocess.py").read_text(encoding="utf-8")
    assert "publish_vocal_activity" in source


def test_current_source_does_not_reference_archived_entrypoints():
    forbidden = ("run_allinone_isolated", "backfill_vocal_events")
    for directory in ("app", "deploy", "scripts", "music_analysis", "preprocessing"):
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".sh", ".service", ""):
                continue
            source = path.read_text(encoding="utf-8")
            for name in forbidden:
                assert name not in source, f"{path} still references {name}"
