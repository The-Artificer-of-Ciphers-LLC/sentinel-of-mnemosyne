from types import SimpleNamespace

from app.runtime_config import RuntimeConfig, runtime_config_from_settings


def test_runtime_config_from_settings_maps_required_fields():
    settings = SimpleNamespace(
        model_name="m1",
        ai_provider="lmstudio",
        lmstudio_base_url="http://lm",
        embedding_model="emb",
    )

    cfg = runtime_config_from_settings(settings)

    assert isinstance(cfg, RuntimeConfig)
    assert cfg.model_name == "m1"
    assert cfg.ai_provider == "lmstudio"
    assert cfg.lmstudio_base_url == "http://lm"
    assert cfg.embedding_model == "emb"
