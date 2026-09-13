"""Guard module consolidation without exercising hardware or remote services."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.test_current_modules import GROUPS, command_for

ROOT = Path(__file__).resolve().parents[1]
CURRENT = json.loads((ROOT / "modules/CURRENT.json").read_text())


def test_only_selected_module_packages_remain():
    actual = {p.parent.name for p in (ROOT / "modules").glob("*/MODULE.yaml")}
    assert actual == {m["id"] for m in CURRENT["modules"]}
    for name in ("audio-preprocess", "stem-separation"):
        root = ROOT / "modules" / name
        assert (root / "README.md").exists()
        assert not list(root.rglob("*.py")), "retired package must not retain executable code"
        assert not (root / "MODULE.yaml").exists()
        assert not (root / "pyproject.toml").exists()
    assert not (ROOT / "modules/BASELINE-v0.1.0.json").exists()


def test_retained_code_matches_selected_remote_snapshot():
    # The only source differences permitted are text encoding/newline normalization.
    # README notices are deliberately excluded from this recorded text hash map.
    for path, expected in CURRENT["source_files_text_sha256"].items():
        text = (ROOT / path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").rstrip() + "\n"
        assert hashlib.sha256(text.encode()).hexdigest() == expected, path


def test_package_versions_are_recorded_without_confusing_them_with_module_versions():
    for module in CURRENT["modules"]:
        root = ROOT / "modules" / module["id"]
        assert f"version: {module['module_version']}" in (root / "MODULE.yaml").read_text()
        if (root / "pyproject.toml").exists():
            project = (root / "pyproject.toml").read_text().split("[project]\n", 1)[1].split("\n[", 1)[0]
            version = re.search(r'^version\s*=\s*"([^"]+)"', project, re.MULTILINE)
            assert version and version.group(1) == module["package_version"]


def test_test_runner_covers_retained_modules_and_canonical_preprocessing():
    assert set(GROUPS) == {m["id"] for m in CURRENT["modules"]} | {"preprocessing"}
    for group in GROUPS:
        assert command_for(group)


def test_retained_v1_modules_are_explicitly_pending_v2_decision():
    registry = (ROOT / "modules/REGISTRY.md").read_text()
    assert registry.count("待确认（不一定需要）") == len(CURRENT["modules"])
    for module in CURRENT["modules"]:
        assert module["product_generation"] == "v1"
        assert module["v2_adoption"] == "pending_confirmation"
        assert module["v2_required"] is None
        notice = (ROOT / "modules" / module["id"] / "README.md").read_text().split("\n\n", 2)[1]
        assert "第一版实现" in notice
        assert "第二版不一定需要" in notice
        assert "待确认" in notice


def test_test_runner_can_list_commands_from_another_directory(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/test_current_modules.py"), "--list"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "harbeat_stem_separation" not in result.stdout
    assert "test_same_style_preprocess_publisher.py" in result.stdout


def test_v5_feature_contract_is_available_outside_retired_module():
    schema = json.loads((ROOT / "contracts/schemas/analysis/pre-style-features-v5.schema.json").read_text())
    assert "feature" in schema["$defs"]


def test_formal_pipeline_does_not_import_retained_legacy_contracts():
    for path in (ROOT / "preprocessing").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("harbeat_"), path
