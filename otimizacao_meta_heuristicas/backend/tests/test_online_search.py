from app import online_search


def _stub_wikipedia_profile(**overrides):
    profile = {
        "title": "Flamengo",
        "description": "Clube de futebol brasileiro",
        "summary": "Resumo do Flamengo vindo da Wikipedia.",
        "crest_url": "https://upload.wikimedia.org/flamengo-crest.png",
        "page_url": "https://pt.wikipedia.org/wiki/Flamengo",
        "lang": "pt",
    }
    profile.update(overrides)
    return profile


def test_search_public_team_info_includes_wikipedia_profile(monkeypatch):
    monkeypatch.setattr(online_search, "_duckduckgo_lookup", lambda query, category: [])
    monkeypatch.setattr(online_search, "fetch_team_wikipedia_profile", lambda name: _stub_wikipedia_profile())

    result = online_search.search_public_team_info("Flamengo")

    assert result["crest_url"] == "https://upload.wikimedia.org/flamengo-crest.png"
    assert result["wikipedia"]["title"] == "Flamengo"
    wikipedia_sources = [source for source in result["sources"] if source["origin"] == "Wikipedia"]
    assert len(wikipedia_sources) == 1
    assert wikipedia_sources[0]["url"] == "https://pt.wikipedia.org/wiki/Flamengo"


def test_search_public_team_info_handles_missing_wikipedia_profile(monkeypatch):
    monkeypatch.setattr(online_search, "_duckduckgo_lookup", lambda query, category: [])
    monkeypatch.setattr(online_search, "fetch_team_wikipedia_profile", lambda name: None)

    result = online_search.search_public_team_info("Time Totalmente Inexistente")

    assert result["crest_url"] is None
    assert result["wikipedia"] is None
    assert not any(source["origin"] == "Wikipedia" for source in result["sources"])


def test_search_public_team_info_survives_wikipedia_lookup_raising(monkeypatch):
    def boom(name):
        raise RuntimeError("network blocked")

    monkeypatch.setattr(online_search, "_duckduckgo_lookup", lambda query, category: [])
    monkeypatch.setattr(online_search, "fetch_team_wikipedia_profile", boom)

    result = online_search.search_public_team_info("Flamengo")

    assert result["crest_url"] is None
    assert any(error["source"] == "Wikipedia" for error in result["errors"])


def test_detect_team_category_defaults_to_masculino():
    assert online_search.detect_team_category("Flamengo", "Clube de futebol brasileiro") == "Masculino"


def test_detect_team_category_detects_female_football():
    assert online_search.detect_team_category("Corinthians", "Time de futebol feminino brasileiro") == "Feminino"
    assert online_search.detect_team_category("Arsenal Women", "") == "Feminino"


def test_search_public_team_info_defaults_category_to_masculino(monkeypatch):
    monkeypatch.setattr(online_search, "_duckduckgo_lookup", lambda query, category: [])
    monkeypatch.setattr(online_search, "fetch_team_wikipedia_profile", lambda name: _stub_wikipedia_profile())

    result = online_search.search_public_team_info("Flamengo")

    assert result["category"] == "Masculino"


def test_search_public_team_info_detects_feminino_from_wikipedia_summary(monkeypatch):
    monkeypatch.setattr(online_search, "_duckduckgo_lookup", lambda query, category: [])
    monkeypatch.setattr(
        online_search,
        "fetch_team_wikipedia_profile",
        lambda name: _stub_wikipedia_profile(summary="Clube de futebol feminino de Sao Paulo."),
    )

    result = online_search.search_public_team_info("Corinthians")

    assert result["category"] == "Feminino"


def test_looks_like_football_rejects_other_sports():
    assert online_search._looks_like_football("Flamengo vence jogo de futebol") is True
    assert online_search._looks_like_football("Flamengo vence jogo de basquete pela NBA") is False


def test_duckduckgo_lookup_filters_out_non_football_results(monkeypatch):
    web_results = {
        "results": [
            {"title": "Flamengo vence jogo de futebol", "url": "https://example.com/futebol", "snippet": ""},
            {"title": "Flamengo perde jogo de basquete da NBA", "url": "https://example.com/basquete", "snippet": ""},
        ],
        "engine": "DuckDuckGo",
        "errors": [],
    }
    monkeypatch.setattr(online_search, "search_web", lambda query, max_results=6: web_results)

    results = online_search._duckduckgo_lookup("Flamengo futebol", "team_form")

    assert len(results) == 1
    assert "basquete" not in results[0]["title"].casefold()
