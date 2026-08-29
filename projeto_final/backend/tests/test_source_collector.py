import urllib.error

import pytest

from app import source_collector, web_search


SAMPLE_PAGE = """
<html>
  <head>
    <title>Palmeiras 3 x 0 - Melhores Momentos | Analise Tatica</title>
    <meta name="description" content="Compacto do jogo com leitura da pressao alta e saida de bola.">
    <meta property="og:site_name" content="Canal Tatico">
  </head>
  <body>conteudo</body>
</html>
"""

YOUTUBE_PAGE = """
<html>
  <head>
    <title>Palmeiras vence com gol no fim - YouTube</title>
    <meta property="og:title" content="Palmeiras vence com gol no fim">
    <meta property="og:description" content="Melhores momentos da partida com analise da pressao alta.">
    <meta property="og:site_name" content="YouTube">
  </head>
  <body>conteudo</body>
</html>
"""


def test_collect_from_link_extracts_title_and_description(monkeypatch):
    monkeypatch.setattr(source_collector, "_fetch_html_capped", lambda _url: SAMPLE_PAGE)

    result = source_collector.collect_sources("link", "https://youtube.com/watch?v=abc123")

    assert result["status"] == "collected"
    assert result["errors"] == []
    source = result["sources"][0]
    assert "Melhores Momentos" in source["title"]
    assert "pressao alta" in source["summary"]
    assert source["origin"] == "Canal Tatico"
    # Titulo menciona analise tatica, entao a categoria de analise vence a de video.
    assert source["category"] == "analysis_videos"


def test_collect_from_link_without_scheme_defaults_to_https(monkeypatch):
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return SAMPLE_PAGE

    monkeypatch.setattr(source_collector, "_fetch_html_capped", fake_fetch)

    source_collector.collect_sources("link", "canal-tatico.com/artigo")

    assert captured["url"] == "https://canal-tatico.com/artigo"


def test_collect_from_link_registers_source_even_when_fetch_fails(monkeypatch):
    def fake_fetch(_url):
        raise TimeoutError("sem rede")

    monkeypatch.setattr(source_collector, "_fetch_html_capped", fake_fetch)

    result = source_collector.collect_sources("link", "https://example.com/analise")

    assert len(result["sources"]) == 1
    assert result["sources"][0]["url"] == "https://example.com/analise"
    assert result["errors"][0]["error"] == "TimeoutError"


def test_collect_from_link_registers_source_when_site_blocks_bot_user_agent(monkeypatch):
    # Regressao: YouTube (e outros sites de video) devolvem 403 HTTPError
    # para um user-agent "de robo"; o link ainda deve ser registrado, com o
    # erro tratado reportado, em vez de deixar a excecao vazar.
    def fake_fetch(_url):
        raise urllib.error.HTTPError("https://youtu.be/CX91i5l296c", 403, "Forbidden", {}, None)

    monkeypatch.setattr(source_collector, "_fetch_html_capped", fake_fetch)

    result = source_collector.collect_sources("link", "https://youtu.be/CX91i5l296c")

    assert result["sources"][0]["url"] == "https://youtu.be/CX91i5l296c"
    assert result["errors"][0]["error"] == "HTTPError"
    assert result["sources"][0]["category"] == "match_videos"


def test_fetch_html_capped_uses_browser_user_agent_not_bot_ua(monkeypatch):
    # Regressao: _fetch_html_capped precisa delegar ao fetch_page com UA de
    # navegador (o mesmo que ja funciona para o YouTube em youtube_search.py),
    # em vez do UA de robo que o site rejeitava com 403.
    captured = {}

    def fake_fetch_page(url, timeout=8, user_agent=web_search.BROWSER_USER_AGENT):
        captured["url"] = url
        captured["user_agent"] = user_agent
        return SAMPLE_PAGE

    monkeypatch.setattr(source_collector, "fetch_page", fake_fetch_page)

    source_collector._fetch_html_capped("https://youtu.be/CX91i5l296c")

    assert captured["url"] == "https://youtu.be/CX91i5l296c"
    assert captured["user_agent"] == web_search.BROWSER_USER_AGENT
    assert "football-intelligence-platform" not in captured["user_agent"]


def test_collect_from_link_prefers_og_title_over_page_title(monkeypatch):
    # og:title evita sufixos de plataforma (ex.: "... - YouTube").
    monkeypatch.setattr(source_collector, "_fetch_html_capped", lambda _url: YOUTUBE_PAGE)

    result = source_collector.collect_sources("link", "https://youtu.be/CX91i5l296c")

    source = result["sources"][0]
    assert source["title"] == "Palmeiras vence com gol no fim"
    assert "YouTube" not in source["title"]
    assert source["origin"] == "YouTube"
    assert "pressao alta" in source["summary"]


@pytest.mark.parametrize(
    "bad_url",
    [
        "ftp://example.com/video.mp4",
        "http://localhost/admin",
        "http://127.0.0.1:8000/api",
        "http://192.168.0.10/paine",
    ],
)
def test_collect_from_link_rejects_non_public_urls(bad_url):
    with pytest.raises(ValueError):
        source_collector.collect_sources("link", bad_url)


def test_collect_from_keyword_falls_back_to_guided_sources(monkeypatch):
    def fail_lookup(_query, _category):
        raise OSError("rede bloqueada")

    monkeypatch.setattr(source_collector, "_duckduckgo_lookup", fail_lookup)

    result = source_collector.collect_sources("keyword", "pressao alta", team_name="Palmeiras")

    assert result["status"] == "guided_fallback"
    assert result["sources"], "fallback guiado deve gerar consultas estruturadas"
    assert all("Palmeiras" in source["title"] or "Palmeiras" in source["url"] for source in result["sources"])


def test_collect_from_public_apis_combines_wikipedia_and_thesportsdb(monkeypatch):
    monkeypatch.setattr(
        source_collector,
        "fetch_team_wikipedia_profile",
        lambda _name: {
            "title": "Sociedade Esportiva Palmeiras",
            "summary": "Clube brasileiro de futebol.",
            "page_url": "https://pt.wikipedia.org/wiki/Palmeiras",
        },
    )
    monkeypatch.setattr(
        source_collector,
        "_thesportsdb_lookup",
        lambda _query: [
            source_collector._source(
                title="Ficha do clube: Palmeiras",
                origin="TheSportsDB (API publica)",
                url="https://www.thesportsdb.com/team/134285",
                summary="Serie A, Brazil, Allianz Parque.",
                category="team_form",
                relevance="Alta",
            )
        ],
    )

    result = source_collector.collect_sources("api", "Palmeiras")

    assert result["status"] == "collected"
    origins = {source["origin"] for source in result["sources"]}
    assert "Wikipedia (API publica)" in origins
    assert "TheSportsDB (API publica)" in origins


def test_invalid_mode_raises_value_error():
    with pytest.raises(ValueError):
        source_collector.collect_sources("rss", "qualquer coisa")


def test_merge_sources_into_payload_dedupes_and_regroups():
    online = {
        "status": "not_collected",
        "sources": [
            source_collector._source(
                title="Fonte existente",
                origin="Busca web publica",
                url="https://example.com/a",
                summary="ja salva",
                category="team_form",
                relevance="Media",
            )
        ],
    }
    new_sources = [
        # Duplicada pela URL: nao deve ser contada duas vezes.
        source_collector._source(
            title="Fonte existente (repetida)",
            origin="Link manual",
            url="https://example.com/a",
            summary="duplicada",
            category="team_form",
            relevance="Media",
        ),
        source_collector._source(
            title="Video novo",
            origin="Link manual",
            url="https://youtube.com/watch?v=xyz",
            summary="video de jogo",
            category="match_videos",
            relevance="Alta",
        ),
    ]

    merged = source_collector.merge_sources_into_payload(online, new_sources)

    assert len(merged["sources"]) == 2
    assert merged["coverage"] == {"match_videos": 1, "analysis_videos": 0, "team_form": 1}
    assert merged["status"] == "partial"
