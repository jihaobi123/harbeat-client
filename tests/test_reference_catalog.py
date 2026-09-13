"""Guard reference notices without running models, services or migrations."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "docs/repository/reference-areas.json").read_text())


def test_reference_entries_are_explicit_about_rewrite():
    assert CATALOG["v2_default_reuse_of_reference_code"] is False
    assert CATALOG["new_apk_source_verified"] is False
    assert CATALOG["online_changed"] is False
    for path in CATALOG["reference_entrypoints"]:
        content = (ROOT / path).read_text()
        assert "<!-- harbeat:reference-only -->" in content, path
        assert "第一版" in content, path
        assert "重构" in content, path


def test_historical_document_bodies_are_preserved():
    for entry in CATALOG["preserved_document_notices"]:
        data = (ROOT / entry["path"]).read_bytes()
        notice = (
            "\n<!-- harbeat:reference-only -->\n"
            "> **第一版历史参考 / 旧方案。第二版后续重构，预计不直接使用；个别内容如需复用，须重新确认。**\n"
            "> 下文的“正式开工”“已完成”、接口字段和部署命令只描述历史版本，不是第二版实现要求或上线依据。请先读 [参考代码与重构边界]("
            + entry["guide_link"] + ")。\n"
        ).encode()
        assert data.count(notice) == 1, entry["path"]
        restored = data.replace(notice, b"", 1)
        assert hashlib.sha256(restored).hexdigest() == entry["original_sha256"], entry["path"]


def test_active_and_research_paths_are_preserved():
    for path in CATALOG["active_paths"] + CATALOG["research_paths"]:
        assert (ROOT / path).is_dir(), path
    for path in CATALOG["active_paths"]:
        assert "<!-- harbeat:reference-only -->" not in (ROOT / path / "README.md").read_text(), path


def test_navigation_targets_exist():
    pages = CATALOG["reference_entrypoints"] + [
        "HARBEAT_V2_START_HERE.md", "docs/repository/reference-code.md",
        "docs/README.md", "deploy/README.md", "deploy/jetson/README.md",
        "contracts/README.md", "scripts/README.md", "reports/README.md",
    ]
    for path in pages:
        source = ROOT / path
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", source.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            assert (source.parent / target.split("#", 1)[0]).exists(), (path, target)
