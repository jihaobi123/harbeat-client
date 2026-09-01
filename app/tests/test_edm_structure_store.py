import pytest

from app.modules.edm_structure.schemas import EdmStructureAnalysisDocument
from app.modules.edm_structure.store import EdmStructureInvalid, EdmStructureStore
from app.tests.test_edm_structure_schema import document_payload


def test_store_round_trip_and_path_safety(tmp_path):
    store = EdmStructureStore(tmp_path / "edm-structure")
    document = EdmStructureAnalysisDocument.model_validate(document_payload())
    store.save(document)
    assert store.load("track-1") == document
    with pytest.raises(EdmStructureInvalid):
        store.load("../../etc/passwd")


def test_store_does_not_touch_songformer_or_human_sidecars(tmp_path):
    songformer = tmp_path / "songformer-sections" / "track-1.json"
    human = tmp_path / "bar-annotations" / "dataset" / "1" / "track-1.json"
    songformer.parent.mkdir(parents=True)
    human.parent.mkdir(parents=True)
    songformer.write_text("songformer")
    human.write_text("human")
    EdmStructureStore(tmp_path / "edm-structure").save(
        EdmStructureAnalysisDocument.model_validate(document_payload())
    )
    assert songformer.read_text() == "songformer"
    assert human.read_text() == "human"
