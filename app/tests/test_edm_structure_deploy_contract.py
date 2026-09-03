from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_installer_pins_upstream_and_does_not_replace_jetson_torch():
    installer = (PROJECT_ROOT / "deploy/edmformer/install-jetson.sh").read_text()
    assert "2dd942f2f9e71ffd826346828eeaba1dd3ece56a" in installer
    assert "1412e207645e9a71adc09777714dd251ce7805cada9bf19518d2e455a977e165" in installer
    assert "218b483a0256ddef736267425fabb166fd97008983696bb9270def464b47bded" in installer
    assert "pip install -e" not in installer
    assert "install_inference_deps.sh" not in installer
    assert "--no-deps" in installer
    assert "expected NVIDIA Jetson torch" in installer


def test_installer_preserves_virtualenv_python_path():
    installer = (PROJECT_ROOT / "deploy/edmformer/install-jetson.sh").read_text()
    assert 'CORE_PYTHON="$(realpath -m "$3")"' in installer
    assert 'CORE_PYTHON="$(realpath "$3")"' not in installer


def test_installer_reuses_songformer_feature_assets():
    installer = (PROJECT_ROOT / "deploy/edmformer/install-jetson.sh").read_text()
    assert 'SONGFORMER_ROOT="$MODEL_ROOT/SongFormer"' in installer
    assert 'MUQ_ROOT="$MODEL_ROOT/MuQ-large-msd-iter"' in installer
    assert "pretrained_msd.pt" in installer
    assert "msd_stats.json" in installer
    assert "at least 3 GiB free" in installer


def test_service_configuration_keeps_edmformer_in_shadow_mode():
    config = (
        PROJECT_ROOT / "deploy/edmformer/harbeat-edmformer.conf.example"
    ).read_text()
    assert 'Environment="EDM_STRUCTURE_ENABLED=true"' in config
    assert 'Environment="EDM_STRUCTURE_DEPLOYMENT_STATUS=shadow"' in config
    assert "run_edmformer_isolated.py" in config
    assert "--muq-model /opt/harbeat/models/MuQ-large-msd-iter" in config


def test_verifier_runs_a_real_track_and_keeps_eight_gib_free():
    verifier = (PROJECT_ROOT / "deploy/edmformer/verify-runtime.sh").read_text()
    assert "run_edmformer_isolated.py" in verifier
    assert "edmformer_label_probabilities" not in verifier
    assert "probabilities" in verifier
    assert "8388608" in verifier
    assert "deploy/songformer/verify-runtime.sh" in verifier
