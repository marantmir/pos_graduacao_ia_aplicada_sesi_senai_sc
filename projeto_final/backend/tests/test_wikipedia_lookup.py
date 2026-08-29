import json
import urllib.error

from app import wikipedia_lookup


def _summary_payload(**overrides):
    payload = {
        "title": "Flamengo",
        "description": "Clube de futebol brasileiro",
        "extract": "O Clube de Regatas do Flamengo e um clube brasileiro sediado no Rio de Janeiro.",
        "thumbnail": {"source": "https://upload.wikimedia.org/flamengo-crest.png"},
        "content_urls": {"desktop": {"page": "https://pt.wikipedia.org/wiki/Flamengo"}},
    }
    payload.update(overrides)
    return payload


def test_fetch_team_wikipedia_profile_returns_summary(monkeypatch):
    wikipedia_lookup.fetch_team_wikipedia_profile.cache_clear()
    monkeypatch.setattr(wikipedia_lookup, "_fetch_summary", lambda lang, title: _summary_payload())

    profile = wikipedia_lookup.fetch_team_wikipedia_profile("Flamengo")

    assert profile["title"] == "Flamengo"
    assert profile["crest_url"] == "https://upload.wikimedia.org/flamengo-crest.png"
    assert profile["page_url"] == "https://pt.wikipedia.org/wiki/Flamengo"
    assert profile["lang"] == "pt"


def test_fetch_team_wikipedia_profile_falls_back_to_english(monkeypatch):
    wikipedia_lookup.fetch_team_wikipedia_profile.cache_clear()

    def fake_fetch(lang, title):
        if lang == "pt":
            return None
        return _summary_payload(title="Some Team FC")

    monkeypatch.setattr(wikipedia_lookup, "_fetch_summary", fake_fetch)

    profile = wikipedia_lookup.fetch_team_wikipedia_profile("Some Team FC")

    assert profile["lang"] == "en"
    assert profile["title"] == "Some Team FC"


def test_fetch_team_wikipedia_profile_skips_disambiguation_pages(monkeypatch):
    wikipedia_lookup.fetch_team_wikipedia_profile.cache_clear()

    def fake_fetch(lang, title):
        if lang == "pt":
            return _summary_payload(type="disambiguation")
        return None

    monkeypatch.setattr(wikipedia_lookup, "_fetch_summary", fake_fetch)

    profile = wikipedia_lookup.fetch_team_wikipedia_profile("Ambiguous Name")

    assert profile is None


def test_fetch_team_wikipedia_profile_returns_none_when_no_page_found(monkeypatch):
    wikipedia_lookup.fetch_team_wikipedia_profile.cache_clear()
    monkeypatch.setattr(wikipedia_lookup, "_fetch_summary", lambda lang, title: None)

    profile = wikipedia_lookup.fetch_team_wikipedia_profile("Time Totalmente Inexistente")

    assert profile is None


def test_fetch_team_wikipedia_profile_returns_none_for_empty_name():
    wikipedia_lookup.fetch_team_wikipedia_profile.cache_clear()

    assert wikipedia_lookup.fetch_team_wikipedia_profile("   ") is None


def test_fetch_summary_returns_none_on_network_error(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("blocked")

    monkeypatch.setattr(wikipedia_lookup.urllib.request, "urlopen", fake_urlopen)

    assert wikipedia_lookup._fetch_summary("pt", "Flamengo") is None


def test_fetch_summary_parses_real_response_shape(monkeypatch):
    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_summary_payload()).encode("utf-8")

    monkeypatch.setattr(wikipedia_lookup.urllib.request, "urlopen", lambda *a, **k: _FakeResponse())

    data = wikipedia_lookup._fetch_summary("pt", "Flamengo")

    assert data["title"] == "Flamengo"
