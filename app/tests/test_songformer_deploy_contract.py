from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_jetson_installer_preserves_cuda_torch_and_uses_official_muq_model() -> None:
    installer = (PROJECT_ROOT / "deploy/songformer/install-jetson.sh").read_text(
        encoding="utf-8"
    )

    assert "--no-deps" in installer
    assert "OpenMuQ/MuQ-large-msd-iter" in installer
    assert "MuQ-MuLan-large" not in installer
    assert "model.safetensors" in installer
    assert "pytorch_model.bin" not in installer


def test_jetson_installer_supports_mainland_mirrors_and_pinned_submodules() -> None:
    installer = (PROJECT_ROOT / "deploy/songformer/install-jetson.sh").read_text(
        encoding="utf-8"
    )

    assert "hf-mirror.com" in installer
    assert "28847ea50cd31ac4b8b6a7dacc051ad7d1c7606a" in installer
    assert "b83ebedb401bcef639b26b05c0c8bee1dc2dfe71" in installer


def test_service_template_uses_correct_muq_model_and_mirror() -> None:
    template = (
        PROJECT_ROOT / "deploy/songformer/harbeat-songformer.conf.example"
    ).read_text(encoding="utf-8")

    assert "--muq-model /opt/harbeat/models/MuQ-large-msd-iter" in template
    assert 'Environment="HF_ENDPOINT=https://hf-mirror.com"' in template
    assert 'Environment="SECTION_RELABELER_ENABLED=false"' in template


def test_cli_registers_all_orm_models_before_database_lookup() -> None:
    script = (
        PROJECT_ROOT / "scripts/generate_songformer_annotation_blocks.py"
    ).read_text(encoding="utf-8")

    all_models_import = "from app.modules import models as _all_models"
    library_model_import = "from app.modules.library.models import LibrarySong"
    assert all_models_import in script
    assert script.index(all_models_import) < script.index(library_model_import)
