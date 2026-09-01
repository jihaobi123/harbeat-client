from app.shared.config import Settings


def test_settings_accepts_deployment_only_environment_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "PUBLIC_ASSET_BASE_URL=http://127.0.0.1:8000",
                "ENABLE_STARTUP_ANALYSIS=0",
                "ENABLE_EXTERNAL_STYLE_ENRICHMENT=false",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.annotation_dir == "./data/annotations"
    assert settings.presence_dataset_version == "bar-presence-pilot-1.0.0"
    assert settings.songformer_section_dir == "./data/songformer-sections"
    assert settings.songformer_work_dir == "./data/songformer-cache"
    assert settings.songformer_command == ""
    assert settings.songformer_timeout_sec == 1800
    assert settings.songformer_enabled is False
    assert settings.instrument_analysis_enabled is False
    assert settings.instrument_analysis_dir == "./data/instrument-analysis"
    assert settings.instrument_analysis_work_dir == "./data/instrument-analysis-cache"
    assert settings.instrument_analysis_command == ""
    assert settings.instrument_analysis_timeout_sec == 1800
