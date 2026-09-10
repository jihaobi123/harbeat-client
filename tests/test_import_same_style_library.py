from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import jsonschema

from scripts.import_same_style_library import _decoded_name, build_inventory


def _encoded_utf8_name(name: str) -> str:
    return name.encode("utf-8").decode("cp437")


def test_inventory_repairs_names_uses_parent_style_and_deduplicates(tmp_path: Path) -> None:
    first = tmp_path / "音乐风格参考曲库.zip"
    second = tmp_path / "KPOP.zip"
    content = b"fake-mp3-content"
    with ZipFile(first, "w") as archive:
        archive.writestr("音乐风格参考曲库/house/Artist - Track.mp3", content)
    with ZipFile(second, "w") as archive:
        archive.writestr("KPOP/Track - Artist.mp3", content)

    items = build_inventory([first, second], tmp_path / "import")

    assert len(items) == 1
    assert items[0]["style_labels"] == ["house", "KPOP"]
    assert items[0]["collection_labels"] == ["KPOP", "音乐风格参考曲库"]
    assert items[0]["original_filename"] == "Artist - Track.mp3"
    assert len(items[0]["duplicate_sources"]) == 1


def test_decoded_name_repairs_utf8_saved_without_flag() -> None:
    info = ZipInfo(_encoded_utf8_name("KPOP/怪火.mp3"))
    info.flag_bits = 0
    assert _decoded_name(info) == "KPOP/怪火.mp3"


def test_library_index_schema_accepts_prepared_inventory(tmp_path: Path) -> None:
    archive_path = tmp_path / "EDM.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("EDM/Artist - Track.mp3", b"fake-mp3-content")
    items = build_inventory([archive_path], tmp_path / "import")
    payload = {
        "schema_name": "same_style_library_index",
        "schema_version": "1.0.0",
        "generated_at": "2026-09-10T08:00:00Z",
        "source_collections": ["EDM"],
        "total_tracks": 1,
        "status_summary": {"pending": 1},
        "items": [{key: value for key, value in items[0].items() if key != "source_path"}],
    }
    schema = json.loads(
        (Path(__file__).parents[1] / "contracts/schemas/analysis/same-style-library-index-v1.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(payload)
