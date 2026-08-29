"""Busca web pública resiliente com retry exponencial.

O motivo de existir: em produção a raspagem de um único endpoint do
DuckDuckGo falhava com URLError (bloqueio de user-agent de script, timeout ou
endpoint indisponível para IPs de datacenter). Este módulo tenta vários
motores em sequência até obter resultados, sempre com user-agent de navegador
comum, com retry exponencial e jitter.

Motores, em ordem:
1. DuckDuckGo HTML (html.duckduckgo.com) - markup estável de resultados
2. DuckDuckGo Lite (lite.duckduckgo.com) - markup minimalista, raramente bloqueado
3. Bing (www.bing.com/search) - fallback independente do DuckDuckGo
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

from .tactical_search.retry_policy import retry_with_backoff


# Motores de busca bloqueiam user-agents "de script"; um UA de navegador comum
# e o que os proprios navegadores enviam ao fazer a mesma consulta.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 8
MAX_PAGE_BYTES = 1536 * 1024


@retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=8.0, jitter=True)
def fetch_page(url: str, timeout: int = TIMEOUT_SECONDS, user_agent: str = BROWSER_USER_AGENT) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(MAX_PAGE_BYTES).decode("utf-8", errors="replace")


def search_web(query: str, max_results: int = 6) -> dict:
    """Tenta os motores em ordem e devolve os primeiros resultados obtidos.

    Retorno: {"results": [{title, url, snippet}], "engine": str | None,
    "errors": [{engine, error}]}. "results" vazio significa que todos os
    motores falharam ou nao encontraram nada.
    """
    errors: list[dict] = []
    for engine_name, engine in _ENGINES:
        try:
            results = engine(query, max_results)
        except Exception as error:
            errors.append({"engine": engine_name, "error": error.__class__.__name__})
            continue
        if results:
            return {"results": results[:max_results], "engine": engine_name, "errors": errors}
    return {"results": [], "engine": None, "errors": errors}


def _duckduckgo_html(query: str, max_results: int) -> list[dict]:
    page = fetch_page(f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}")
    return _parse_duckduckgo_html(page, max_results)


def _parse_duckduckgo_html(page: str, max_results: int) -> list[dict]:
    results = []
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippets = [_clean_text(match.group("snippet")) for match in snippet_pattern.finditer(page)]
    for index, match in enumerate(link_pattern.finditer(page)):
        url = unwrap_duckduckgo_url(html.unescape(match.group("href")))
        title = _clean_text(match.group("title"))
        if not url or not title:
            continue
        results.append({"title": title, "url": url, "snippet": snippets[index] if index < len(snippets) else ""})
        if len(results) >= max_results:
            break
    return results


def _duckduckgo_lite(query: str, max_results: int) -> list[dict]:
    page = fetch_page(f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}")
    results = []
    pattern = re.compile(
        r'<a[^>]+rel="nofollow"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(page):
        url = unwrap_duckduckgo_url(html.unescape(match.group("href")))
        title = _clean_text(match.group("title"))
        if not url or not title or not url.startswith("http"):
            continue
        results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= max_results:
            break
    return results


def _bing(query: str, max_results: int) -> list[dict]:
    page = fetch_page(f"https://www.bing.com/search?q={urllib.parse.quote(query)}&setlang=pt-BR")
    results = []
    pattern = re.compile(
        r'<li class="b_algo"[^>]*>.*?<h2[^>]*><a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(page):
        url = html.unescape(match.group("href"))
        title = _clean_text(match.group("title"))
        if not url.startswith("http") or not title:
            continue
        results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= max_results:
            break
    return results


_ENGINES = (
    ("DuckDuckGo", _duckduckgo_html),
    ("DuckDuckGo Lite", _duckduckgo_lite),
    ("Bing", _bing),
)


def unwrap_duckduckgo_url(url: str) -> str:
    if "uddg=" not in url:
        return url
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return params.get("uddg", [url])[0]


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(without_tags).split())
