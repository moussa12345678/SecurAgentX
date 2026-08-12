from pathlib import Path

import yaml

from tools.config_wizard import ConfigWizard


def _provider(wizard: ConfigWizard, name: str):
    return next(provider for provider in wizard.AI_PROVIDERS if provider.name == name)


def test_configuring_openrouter_sets_it_as_runtime_active_provider(tmp_path, monkeypatch):
    config_path = Path(tmp_path) / "config.yaml"
    config_path.write_text(
        "ai:\n  active_provider: gemini\n  providers:\n    gemini:\n      model: gemini-1.5-flash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACTIVE_AI_PROVIDER", "gemini")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")

    wizard = ConfigWizard(Path(tmp_path))
    wizard._activate_provider(_provider(wizard, "OpenRouter"))

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["ai"]["active_provider"] == "openrouter"

    import tools.ai_config as ai_config

    monkeypatch.setattr(ai_config, "find_config", lambda: config_path)
    ai_config.reset_config_cache()
    assert ai_config.get_active_provider() == "openrouter"
    assert saved["ai"]["providers"]["openrouter"]["model"] == "openai/gpt-oss-20b:free"
    assert wizard.env_file.read_text(encoding="utf-8").splitlines() == [
        "ACTIVE_AI_PROVIDER=openrouter"
    ]
    assert __import__("os").environ["ACTIVE_AI_PROVIDER"] == "openrouter"


def test_configuring_local_provider_uses_ollama_model_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    wizard = ConfigWizard(Path(tmp_path))

    wizard._activate_provider(_provider(wizard, "Ollama (Local)"))

    saved = yaml.safe_load((Path(tmp_path) / "config.yaml").read_text(encoding="utf-8"))
    assert saved["ai"]["active_provider"] == "ollama"
    assert saved["ai"]["providers"]["ollama"]["model"] == "llama3.2"


def test_default_wizard_uses_securagentx_home(monkeypatch, tmp_path):
    import tools.config_wizard as config_wizard

    monkeypatch.setattr(config_wizard, "SECURAGENTX_HOME", Path(tmp_path))
    wizard = config_wizard.ConfigWizard()

    assert wizard.config_dir == Path(tmp_path)
    assert wizard.env_file == Path(tmp_path) / ".env"
