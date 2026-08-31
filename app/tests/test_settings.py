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
