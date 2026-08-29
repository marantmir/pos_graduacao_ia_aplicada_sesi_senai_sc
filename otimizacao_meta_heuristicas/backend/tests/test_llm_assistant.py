import json
import urllib.error

from app import llm_assistant, llm_config


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _enable(provider: str, model: str = "", api_key: str = "test-key"):
    llm_config.save_llm_config({"provider": provider, "model": model, "enabled": True, "api_key": api_key})


def test_call_llm_json_returns_fallback_without_api_key(monkeypatch):
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "")
    fallback = {"status": "local_fallback", "value": 1}

    result = llm_assistant._call_llm_json("system", "user", fallback)

    assert result == fallback


def test_call_llm_json_dispatches_to_openai_by_default(monkeypatch):
    _enable("openai_responses")
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "test-key")
    captured = {}

    def fake_openai(system, user, config, api_key, model):
        captured["called"] = True
        return json.dumps({"summary": "ok"})

    monkeypatch.setattr(
        llm_assistant,
        "_PROVIDER_CALLERS",
        {**llm_assistant._PROVIDER_CALLERS, "openai_responses": fake_openai},
    )

    result = llm_assistant._call_llm_json("system", "user", {"status": "local_fallback"})

    assert captured["called"] is True
    assert result["summary"] == "ok"
    assert result["provider"] == "openai_responses"


def test_call_llm_json_dispatches_to_anthropic(monkeypatch):
    _enable("anthropic_messages", model="claude-sonnet-5")
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "test-key")
    captured = {}

    def fake_anthropic(system, user, config, api_key, model):
        captured["model"] = model
        return json.dumps({"summary": "claude ok"})

    monkeypatch.setattr(
        llm_assistant,
        "_PROVIDER_CALLERS",
        {**llm_assistant._PROVIDER_CALLERS, "anthropic_messages": fake_anthropic},
    )

    result = llm_assistant._call_llm_json("system", "user", {"status": "local_fallback"})

    assert captured["model"] == "claude-sonnet-5"
    assert result["summary"] == "claude ok"
    assert result["provider"] == "anthropic_messages"


def test_call_llm_json_dispatches_to_gemini(monkeypatch):
    _enable("google_gemini", model="gemini-2.5-flash")
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "test-key")

    def fake_gemini(system, user, config, api_key, model):
        return json.dumps({"summary": "gemini ok"})

    monkeypatch.setattr(
        llm_assistant,
        "_PROVIDER_CALLERS",
        {**llm_assistant._PROVIDER_CALLERS, "google_gemini": fake_gemini},
    )

    result = llm_assistant._call_llm_json("system", "user", {"status": "local_fallback"})

    assert result["summary"] == "gemini ok"
    assert result["provider"] == "google_gemini"


def test_call_llm_json_dispatches_to_grok(monkeypatch):
    _enable("xai_grok", model="grok-4")
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "test-key")

    def fake_grok(system, user, config, api_key, model):
        return json.dumps({"summary": "grok ok"})

    monkeypatch.setattr(
        llm_assistant,
        "_PROVIDER_CALLERS",
        {**llm_assistant._PROVIDER_CALLERS, "xai_grok": fake_grok},
    )

    result = llm_assistant._call_llm_json("system", "user", {"status": "local_fallback"})

    assert result["summary"] == "grok ok"
    assert result["provider"] == "xai_grok"


def test_call_llm_json_falls_back_on_network_error_regardless_of_provider(monkeypatch):
    _enable("anthropic_messages")
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "test-key")

    def fake_fail(system, user, config, api_key, model):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(
        llm_assistant,
        "_PROVIDER_CALLERS",
        {**llm_assistant._PROVIDER_CALLERS, "anthropic_messages": fake_fail},
    )
    fallback = {"status": "local_fallback", "summary": "fallback summary"}

    result = llm_assistant._call_llm_json("system", "user", fallback)

    assert result["status"] == "local_fallback"
    assert result["provider"] == "deterministic_rules"
    assert result["llm_error"] == "URLError"
    assert result["summary"] == "fallback summary"


def test_openai_request_uses_bearer_auth_and_responses_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"output_text": json.dumps({"ok": True})})

    monkeypatch.setattr(llm_assistant.urllib.request, "urlopen", fake_urlopen)

    text = llm_assistant._call_openai_responses(
        "system prompt", "user prompt", {"temperature": 0.2, "max_output_tokens": 500}, "sk-test", "gpt-4.1-mini"
    )

    assert captured["url"] == llm_assistant.OPENAI_RESPONSES_URL
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "gpt-4.1-mini"
    assert json.loads(text) == {"ok": True}


def test_anthropic_request_uses_x_api_key_header_and_messages_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"content": [{"type": "text", "text": json.dumps({"ok": True})}]})

    monkeypatch.setattr(llm_assistant.urllib.request, "urlopen", fake_urlopen)

    text = llm_assistant._call_anthropic_messages(
        "system prompt", "user prompt", {"temperature": 0.2, "max_output_tokens": 500}, "sk-ant-test", "claude-sonnet-5"
    )

    assert captured["url"] == llm_assistant.ANTHROPIC_MESSAGES_URL
    assert captured["headers"]["X-api-key"] == "sk-ant-test"
    assert captured["headers"]["Anthropic-version"] == llm_assistant.ANTHROPIC_VERSION
    assert captured["body"]["system"].startswith("system prompt")
    assert captured["body"]["messages"] == [{"role": "user", "content": "user prompt"}]
    assert json.loads(text) == {"ok": True}


def test_gemini_request_puts_key_in_query_string_and_uses_model_in_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
        )

    monkeypatch.setattr(llm_assistant.urllib.request, "urlopen", fake_urlopen)

    text = llm_assistant._call_google_gemini(
        "system prompt", "user prompt", {"temperature": 0.2, "max_output_tokens": 500}, "AIza-test", "gemini-2.5-flash"
    )

    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIza-test"
    )
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert json.loads(text) == {"ok": True}


def test_gemini_request_returns_empty_text_when_no_candidates(monkeypatch):
    monkeypatch.setattr(
        llm_assistant.urllib.request, "urlopen", lambda *a, **k: _FakeResponse({"candidates": []})
    )

    text = llm_assistant._call_google_gemini("sys", "user", {}, "key", "gemini-2.5-flash")

    assert text == ""


def test_grok_request_uses_bearer_auth_and_chat_completions_shape(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"choices": [{"message": {"content": json.dumps({"ok": True})}}]})

    monkeypatch.setattr(llm_assistant.urllib.request, "urlopen", fake_urlopen)

    text = llm_assistant._call_xai_grok(
        "system prompt", "user prompt", {"temperature": 0.2, "max_output_tokens": 500}, "xai-test", "grok-4"
    )

    assert captured["url"] == llm_assistant.XAI_CHAT_COMPLETIONS_URL
    assert captured["headers"]["Authorization"] == "Bearer xai-test"
    assert captured["body"]["model"] == "grok-4"
    assert captured["body"]["messages"][1] == {"role": "user", "content": "user prompt"}
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert json.loads(text) == {"ok": True}


def test_grok_request_returns_empty_text_when_no_choices(monkeypatch):
    monkeypatch.setattr(
        llm_assistant.urllib.request, "urlopen", lambda *a, **k: _FakeResponse({"choices": []})
    )

    text = llm_assistant._call_xai_grok("sys", "user", {}, "key", "grok-4")

    assert text == ""


def test_extract_json_object_returns_clean_json_unchanged():
    clean = '{"a": 1, "b": [1, 2]}'
    assert llm_assistant._extract_json_object(clean) == clean


def test_extract_json_object_strips_surrounding_prose():
    wrapped = 'Aqui esta a analise: {"a": 1} Espero que ajude.'
    assert llm_assistant._extract_json_object(wrapped) == '{"a": 1}'


def test_extract_json_object_returns_original_when_no_json_found():
    assert llm_assistant._extract_json_object("nao ha json aqui") == "nao ha json aqui"


def test_llm_status_reports_configured_provider_when_enabled(monkeypatch):
    _enable("google_gemini", model="gemini-2.5-flash")
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "test-key")

    status = llm_assistant.llm_status()

    assert status["enabled"] is True
    assert status["provider"] == "google_gemini"
    assert status["model"] == "gemini-2.5-flash"


def test_llm_status_reports_local_fallback_when_disabled(monkeypatch):
    monkeypatch.setattr(llm_assistant, "_api_key", lambda: "")

    status = llm_assistant.llm_status()

    assert status["enabled"] is False
    assert status["provider"] == "local_fallback"
    assert status["model"] == "deterministic_rules"


def test_openrouter_free_request_uses_free_router_and_bearer_auth(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"choices": [{"message": {"content": json.dumps({"ok": True})}}]})

    monkeypatch.setattr(llm_assistant.urllib.request, "urlopen", fake_urlopen)

    text = llm_assistant._call_openrouter_free(
        "system prompt", "user prompt", {"temperature": 0.2, "max_output_tokens": 500}, "or-test", "openrouter/free"
    )

    assert captured["url"] == llm_assistant.OPENROUTER_CHAT_COMPLETIONS_URL
    assert captured["headers"]["Authorization"] == "Bearer or-test"
    assert captured["body"]["model"] == "openrouter/free"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert json.loads(text) == {"ok": True}


def test_ollama_local_request_does_not_need_api_key(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"message": {"content": json.dumps({"ok": True})}})

    monkeypatch.setattr(llm_assistant.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    text = llm_assistant._call_ollama_local(
        "system prompt", "user prompt", {"temperature": 0.2}, "", "qwen3:4b-instruct"
    )

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["format"] == "json"
    assert captured["body"]["stream"] is False
    assert json.loads(text) == {"ok": True}
