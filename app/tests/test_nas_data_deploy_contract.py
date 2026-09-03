from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "deploy" / "nas-data" / "harbeat-nas-data.conf.example"


def test_jetson_persistent_data_paths_live_on_nas():
    config = CONFIG.read_text(encoding="utf-8")

    assert "RequiresMountsFor=/mnt/nas/harbeat" in config
    expected = {
        "ANNOTATION_DIR": "/mnt/nas/harbeat/data/annotations",
        "BAR_ANNOTATION_DIR": "/mnt/nas/harbeat/data/bar-annotations",
        "SONGFORMER_SECTION_DIR": "/mnt/nas/harbeat/data/songformer-sections",
        "INSTRUMENT_ANALYSIS_DIR": "/mnt/nas/harbeat/data/instrument-analysis",
        "EDM_STRUCTURE_DIR": "/mnt/nas/harbeat/data/edm-structure",
    }
    for name, path in expected.items():
        assert f'Environment="{name}={path}"' in config
    assert "/data/harbeat/" not in config
