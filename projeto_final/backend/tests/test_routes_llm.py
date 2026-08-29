from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_get_config_lists_all_supported_providers():
    response = client.get("/api/llm/config")

    assert response.status_code == 200
    payload = response.json()
    provider_values = {item["value"] for item in payload["options"]["providers"]}
    assert provider_values == {
        "google_gemini",
        "openrouter_free",
        "ollama_local",
        "openai_responses",
        "anthropic_messages",
        "xai_grok",
    }
    assert payload["config"]["provider"] == "google_gemini"  # default free-first


def test_update_config_switches_to_anthropic_and_persists():
    response = client.put("/api/llm/config", json={"provider": "anthropic_messages", "model": "claude-sonnet-5"})

    assert response.status_code == 200
    assert response.json()["config"]["provider"] == "anthropic_messages"
    assert response.json()["config"]["model"] == "claude-sonnet-5"

    # persistiu de fato (nao apenas ecoou o payload da resposta)
    reloaded = client.get("/api/llm/config").json()
    assert reloaded["config"]["provider"] == "anthropic_messages"


def test_update_config_switches_to_gemini_and_persists():
    response = client.put("/api/llm/config", json={"provider": "google_gemini"})

    assert response.status_code == 200
    assert response.json()["config"]["provider"] == "google_gemini"
    assert response.json()["config"]["model"] == "gemini-2.5-flash-lite"


def test_update_config_switches_to_grok_and_persists():
    response = client.put("/api/llm/config", json={"provider": "xai_grok"})

    assert response.status_code == 200
    assert response.json()["config"]["provider"] == "xai_grok"
    assert response.json()["config"]["model"] == "grok-4"


def test_options_expose_models_by_provider_and_env_var_names():
    response = client.get("/api/llm/config")

    options = response.json()["options"]
    assert "claude-sonnet-5" in [m["value"] for m in options["models_by_provider"]["anthropic_messages"]]
    assert "gemini-2.5-flash" in [m["value"] for m in options["models_by_provider"]["google_gemini"]]
    assert "grok-4" in [m["value"] for m in options["models_by_provider"]["xai_grok"]]
    providers_by_value = {item["value"]: item for item in options["providers"]}
    assert providers_by_value["anthropic_messages"]["env_api_key"] == "ANTHROPIC_API_KEY"
    assert providers_by_value["google_gemini"]["env_api_key"] == "GEMINI_API_KEY"
    assert providers_by_value["xai_grok"]["env_api_key"] == "XAI_API_KEY"


def test_update_config_rejects_unknown_provider_by_falling_back():
    response = client.put("/api/llm/config", json={"provider": "bogus_provider"})

    assert response.status_code == 200
    assert response.json()["config"]["provider"] == "google_gemini"


def test_test_endpoint_uses_local_fallback_without_api_key():
    response = client.post("/api/llm/test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["sample"]["status"] == "local_fallback"
