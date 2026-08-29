import pytest

from app import web_search


def test_search_web_falls_back_to_next_engine_on_failure(monkeypatch):
    calls = []

    def fake_fetch(url, timeout=8, user_agent=web_search.BROWSER_USER_AGENT):
        calls.append(url)
        if "html.duckduckgo.com" in url:
            raise OSError("bloqueado")
        if "lite.duckduckgo.com" in url:
            return (
                '<a rel="nofollow" href="https://example.com/jogo">Jogo completo do time</a>'
            )
        raise AssertionError("nao deveria chegar ao Bing")

    monkeypatch.setattr(web_search, "fetch_page", fake_fetch)

    outcome = web_search.search_web("time futebol jogo", max_results=3)

    assert outcome["engine"] == "DuckDuckGo Lite"
    assert outcome["results"][0]["url"] == "https://example.com/jogo"
    assert outcome["errors"][0]["engine"] == "DuckDuckGo"
    # Parou no Lite; nao tentou o Bing.
    assert not any("bing.com" in url for url in calls)


def test_search_web_reports_all_errors_when_every_engine_fails(monkeypatch):
    def always_fail(url, timeout=8, user_agent=web_search.BROWSER_USER_AGENT):
        raise TimeoutError("sem rede")

    monkeypatch.setattr(web_search, "fetch_page", always_fail)

    outcome = web_search.search_web("time futebol")

    assert outcome["results"] == []
    assert outcome["engine"] is None
    assert {item["engine"] for item in outcome["errors"]} == {"DuckDuckGo", "DuckDuckGo Lite", "Bing"}


def test_parse_duckduckgo_html_pairs_titles_and_snippets():
    page = """
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Primeiro <b>resultado</b></a>
    <a class="result__snippet">Resumo do primeiro resultado tatico.</a>
    <a class="result__a" href="https://example.com/b">Segundo resultado</a>
    <a class="result__snippet">Resumo do segundo.</a>
    """

    results = web_search._parse_duckduckgo_html(page, max_results=5)

    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["title"] == "Primeiro resultado"
    assert results[0]["snippet"] == "Resumo do primeiro resultado tatico."
    assert results[1]["url"] == "https://example.com/b"


def test_unwrap_duckduckgo_url_decodes_redirect():
    wrapped = "/l/?uddg=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc&rut=xyz"
    assert web_search.unwrap_duckduckgo_url(wrapped) == "https://www.youtube.com/watch?v=abc"
