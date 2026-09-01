import hashlib
from pathlib import Path

import pytest

from app.modules.instrument_analysis.schemas import InstrumentAnalysisDocument
from app.modules.instrument_analysis.store import (
    InstrumentAnalysisInvalid,
    InstrumentAnalysisStore,
)
from app.tests.test_instrument_analysis_schema import ready_payload


def directory_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def ready_document() -> InstrumentAnalysisDocument:
    return InstrumentAnalysisDocument.model_validate(ready_payload())


def test_store_rejects_unsafe_track_id(tmp_path):
    with pytest.raises(InstrumentAnalysisInvalid):
        InstrumentAnalysisStore(tmp_path).load("../../etc/passwd")


def test_store_round_trip_does_not_touch_human_annotation_root(tmp_path):
    human = tmp_path / "bar-annotations"
    human.mkdir()
    (human / "existing.json").write_text('{"human": true}\n')
    before = directory_hash(human)
    store = InstrumentAnalysisStore(tmp_path / "instrument-analysis")
    document = ready_document()
    store.save(document)
    assert store.load("track_001") == document
    assert directory_hash(human) == before


def test_store_rejects_track_id_mismatch(tmp_path):
    root = tmp_path / "instrument-analysis"
    root.mkdir()
    payload = ready_payload()
    payload["track_id"] = "another_track"
    (root / "track_001.json").write_text(__import__("json").dumps(payload))
    with pytest.raises(InstrumentAnalysisInvalid):
        InstrumentAnalysisStore(root).load("track_001")
