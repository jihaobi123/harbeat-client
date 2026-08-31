import os
import sys

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.modules.library.background_tasks import _persistable_cue_points

if sys.version_info >= (3, 10):
    from app.modules.library.schemas import LibraryCuePoint
else:
    LibraryCuePoint = None


def _candidate_cue() -> dict:
    return {
        "time": 12.0,
        "end": 20.0,
        "label": "Instrumental",
        "raw_label": "inst",
        "color": "#06b6d4",
        "source": "songformer_functional_segment",
        "boundary_source": "songformer",
        "songformer_label": "inst",
        "structure_label_candidate": "instrumental",
        "structure_label_probabilities": {"instrumental": 0.8, "chorus": 0.2},
        "structure_label_confidence": 0.8,
        "structure_label_margin": 0.6,
        "mix_roles": ["instrumental_focus"],
        "mix_role_scores": {"instrumental_focus": 1.0},
        "label_status": "candidate",
        "label_evidence_status": "available",
        "label_contract_version": "songformer_label_contract_v2",
    }


def test_background_persistence_keeps_the_full_section_contract() -> None:
    saved = _persistable_cue_points([_candidate_cue()], song_id="song-42")

    assert saved[0]["id"] == "cue-song-42-0"
    for key, value in _candidate_cue().items():
        assert saved[0][key] == value


def test_library_cue_schema_accepts_new_and_legacy_shapes() -> None:
    if LibraryCuePoint is None:
        pytest.skip("API schema targets Python 3.12; local interpreter is older")
    candidate = LibraryCuePoint(id="cue-1", **_candidate_cue())
    assert candidate.structure_label_candidate == "instrumental"
    assert candidate.mix_roles == ["instrumental_focus"]

    legacy = LibraryCuePoint(
        id="cue-legacy",
        time=0.0,
        label="Intro",
        raw_label="intro",
        color="#22c55e",
    )
    assert legacy.structure_label_candidate is None
    assert legacy.mix_roles == []
