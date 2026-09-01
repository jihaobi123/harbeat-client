from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy/instrument-analysis/install-jetson.sh"
SERVICE_CONFIG = ROOT / "deploy/instrument-analysis/harbeat-instrument-analysis.conf.example"
WRAPPER = ROOT / "deploy/instrument-analysis/instrument-analysis-python"


def test_installer_never_resolves_or_replaces_torch():
    script = INSTALLER.read_text()
    assert "--no-deps" in script
    assert "pip install torch" not in script
    assert "torch==" not in script


def test_installer_pins_sources_and_verifies_both_checkpoints():
    script = INSTALLER.read_text()
    assert 'ADTOF_REVISION="85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9"' in script
    assert 'PANNS_REVISION="d2f4b8c18eab44737fcc0de1248ae21eb43f6aa4"' in script
    assert "sha256sum -c" in script
    assert "70539c43c18b6a289b3199c503a82c5a" in script


def test_service_defaults_to_shadow_and_separate_directories():
    config = SERVICE_CONFIG.read_text()
    assert "INSTRUMENT_ANALYSIS_ENABLED=true" in config
    assert "INSTRUMENT_ANALYSIS_DEPLOYMENT_STATUS=shadow" in config
    assert "/data/harbeat/instrument-analysis" in config
    assert "/data/harbeat/bar-annotations" not in config


def test_wrapper_uses_existing_core_python_and_isolated_overlay():
    script = WRAPPER.read_text()
    assert "/opt/harbeat/current/venv/bin/python" in script
    assert "instrument-analysis-packages" in script
