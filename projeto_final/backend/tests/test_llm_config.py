from app import llm_config


def test_save_llm_config_keeps_a_non_openai_provider():
    # Regressao: save_llm_config forcava o provedor de volta para
    # "openai_responses" mesmo quando o usuario escolhia outro valido.
    saved = llm_config.save_llm_config({"provider": "anthropic_messages"})

    assert saved["provider"] == "anthropic_messages"


def test_save_llm_config_falls_back_to_default_for_unknown_provider():
    saved = llm_config.save_llm_config({"provider": "totally_made_up"})

    assert saved["provider"] == llm_config.DEFAULT_LLM_CONFIG["provider"]


def test_save_llm_config_applies_default_model_per_provider_when_empty():
    saved = llm_config.save_llm_config({"provider": "google_gemini", "model": ""})

    assert saved["model"] == llm_config.PROVIDER_DEFAULT_MODELS["google_gemini"]


def test_save_llm_config_preserves_explicit_model_choice():
    saved = llm_config.save_llm_config({"provider": "anthropic_messages", "model": "claude-opus-4-8"})

    assert saved["model"] == "claude-opus-4-8"


def test_save_llm_config_persists_across_reads():
    llm_config.save_llm_config({"provider": "anthropic_messages", "enabled": True})

    reloaded = llm_config.public_llm_config()

    assert reloaded["provider"] == "anthropic_messages"
    assert reloaded["enabled"] is True


def test_get_llm_runtime_config_reads_provider_specific_env_api_key(monkeypatch):
    llm_config.save_llm_config({"provider": "anthropic_messages"})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")

    config = llm_config.get_llm_runtime_config()

    assert config["api_key"] == "sk-ant-from-env"
    assert config["api_key_source"] == "env"


def test_get_llm_runtime_config_ignores_other_providers_env_var(monkeypatch):
    # Provedor configurado e OpenAI; uma ANTHROPIC_API_KEY no ambiente nao
    # deve vazar para essa configuracao.
    llm_config.save_llm_config({"provider": "openai_responses"})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")

    config = llm_config.get_llm_runtime_config()

    assert config["api_key"] == ""
    assert config["api_key_source"] == "missing"


def test_public_llm_config_masks_saved_api_key():
    llm_config.save_llm_config({"provider": "google_gemini", "api_key": "AIzaSyABCDEFGHIJKLMNOP"})

    config = llm_config.public_llm_config()

    assert config["has_api_key"] is True
    assert "ABCDEFGHIJKLMNOP" not in config["api_key_mask"]


def test_clear_api_key_removes_saved_key():
    llm_config.save_llm_config({"provider": "openai_responses", "api_key": "sk-test-123"})
    cleared = llm_config.save_llm_config({"clear_api_key": True})

    assert cleared["has_api_key"] is False


def test_default_max_output_tokens_is_a_valid_step_value():
    # Regressao: o campo "Maximo de tokens" no formulario usa min=200 step=100.
    # O padrao precisa ser um multiplo valido de step a partir de min, senao a
    # validacao HTML5 bloqueia o botao "Salvar" silenciosamente (sem erro
    # visivel) - foi exatamente o que aconteceu com o padrao antigo (min=256).
    default = llm_config.DEFAULT_LLM_CONFIG["max_output_tokens"]
    floor = 200
    step = 100
    assert (default - floor) % step == 0


def test_ollama_local_does_not_require_api_key(monkeypatch):
    llm_config.save_llm_config({"provider": "ollama_local", "enabled": True, "clear_api_key": True})
    monkeypatch.delenv("FOOTBALL_INTEL_LLM_PROVIDER", raising=False)

    config = llm_config.get_llm_runtime_config()

    assert config["provider"] == "ollama_local"
    assert config["api_key_source"] == "not_required"


def test_env_can_force_free_provider(monkeypatch):
    llm_config.save_llm_config({"provider": "openai_responses"})
    monkeypatch.setenv("FOOTBALL_INTEL_LLM_PROVIDER", "openrouter_free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-env-key")

    config = llm_config.get_llm_runtime_config()

    assert config["provider"] == "openrouter_free"
    assert config["api_key"] == "or-env-key"
