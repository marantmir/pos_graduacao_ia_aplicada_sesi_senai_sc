"""Coleta manual de fontes táticas: link direto, palavra-chave e APIs públicas.

Três modos, todos devolvendo cartões de fonte no mesmo formato usado pela busca
online (`online_search`), para que o material colete-se uma vez e apareca em
todas as telas:

- "link": recebe uma URL e faz scraping leve da propria pagina (title, meta
  description/OpenGraph) para registrar a fonte com contexto real.
- "keyword": busca web publica (DuckDuckGo HTML) pela palavra-chave, com
  fallback de consultas estruturadas quando a rede estiver bloqueada.
- "api": consulta APIs publicas gratuitas (Wikipedia REST e TheSportsDB) e
  transforma os resultados em fontes verificaveis.
"""
from __future__ import annotations

import html
import ipaddress
import json
import re
import urllib.parse
from datetime import datetime, timezone

from .online_search import (
    _dedupe_sources,
    _duckduckgo_lookup,
    _fetch_text,
    _group_sources,
    _guided_video_sources,
    _source,
)
from .web_search import fetch_page
from .wikipedia_lookup import fetch_team_wikipedia_profile
from .youtube_search import search_youtube_videos


COLLECT_MODES = ("link", "keyword", "api")
TIMEOUT_SECONDS = 6
MAX_HTML_BYTES = 512 * 1024
VIDEO_DOMAINS = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com")
ANALYSIS_HINTS = (
    # Português
    "análise", "tátic", "scout", "como joga", "desempenho", "formação",
    "saída de bola", "pressão", "defesa", "ataque", "transição",
    # English
    "tactic", "tactical", "scout", "scouting", "performance", "formation",
    "build-up", "pressure", "defense", "attack", "transition",
    # Español
    "táctica", "scout", "rendimiento", "formación", "presión",
)

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "0.0.0.0", "metadata.google.internal"}


def collect_sources(mode: str, value: str, team_name: str = "") -> dict:
    """Executa a coleta no modo pedido e devolve fontes + erros tratados."""
    cleaned_value = " ".join((value or "").strip().split())
    cleaned_team = " ".join((team_name or "").strip().split())
    errors: list[dict] = []

    if mode == "link":
        sources = _collect_from_link(cleaned_value, errors)
    elif mode == "keyword":
        sources = _collect_from_keyword(cleaned_value, cleaned_team, errors)
    elif mode == "api":
        sources = _collect_from_public_apis(cleaned_value or cleaned_team, errors)
    else:
        raise ValueError(f"Modo de coleta invalido: {mode}. Use: {', '.join(COLLECT_MODES)}.")

    sources = _dedupe_sources(sources)
    live_count = sum(1 for source in sources if source.get("origin") not in {"Busca sugerida", "Pesquisa sugerida"})
    return {
        "mode": mode,
        "value": cleaned_value,
        "team_name": cleaned_team,
        "status": "collected" if live_count else ("guided_fallback" if sources else "empty"),
        "sources": sources,
        "source_groups": _group_sources(sources),
        "live_count": live_count,
        "errors": errors[:6],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "note": _collect_note(mode, live_count, sources, errors),
    }


def merge_sources_into_payload(online: dict, new_sources: list[dict]) -> dict:
    """Mescla fontes coletadas manualmente no payload `online_search` de um
    perfil salvo, deduplicando e reagrupando por categoria."""
    combined = _dedupe_sources((online.get("sources") or []) + list(new_sources))
    groups = _group_sources(combined)
    merged = dict(online)
    merged["sources"] = combined
    merged["source_groups"] = groups
    merged["coverage"] = {key: len(items) for key, items in groups.items()}
    merged["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    if merged.get("status") in (None, "", "not_collected", "unavailable"):
        merged["status"] = "partial"
    return merged


def _collect_from_link(url: str, errors: list[dict]) -> list[dict]:
    if not url:
        raise ValueError("Informe o link da fonte (http:// ou https://).")
    if "://" in url and not re.match(r"^https?://", url, re.IGNORECASE):
        raise ValueError("Somente links http:// ou https:// sao aceitos.")
    normalized = url if re.match(r"^https?://", url, re.IGNORECASE) else f"https://{url}"
    _validate_public_url(normalized)

    title = ""
    description = ""
    site_name = ""
    try:
        page = _fetch_html_capped(normalized)
        # og:title evita sufixos de plataforma (ex.: "Titulo do video - YouTube").
        title = _extract_meta(page, "og:title") or _extract_title(page)
        description = _extract_meta(page, "description") or _extract_meta(page, "og:description")
        site_name = _extract_meta(page, "og:site_name")
    except Exception as error:
        errors.append({"source": "Leitura da pagina", "error": error.__class__.__name__})

    hostname = urllib.parse.urlparse(normalized).hostname or "fonte externa"
    category = _categorize_link(normalized, f"{title} {description}")
    return [
        _source(
            title=title or f"Fonte adicionada por link ({hostname})",
            origin=site_name or hostname,
            url=normalized,
            summary=description
            or "Link registrado manualmente; a pagina nao pode ser lida agora, valide o conteudo na revisao visual.",
            category=category,
            relevance="Alta" if title else "Media",
        )
    ]


def _collect_from_keyword(keyword: str, team_name: str, errors: list[dict]) -> list[dict]:
    if not keyword:
        raise ValueError("Informe a palavra-chave para a busca de fontes.")
    query = f"{team_name} {keyword}".strip()
    sources: list[dict] = []
    # Vídeos reais do YouTube pela palavra-chave, prontos para subir na análise.
    try:
        for video in search_youtube_videos(f"{query} futebol", limit=5):
            meta = " · ".join(
                part for part in (video.get("channel"), video.get("duration"), video.get("published")) if part
            )
            sources.append(
                _source(
                    title=video["title"],
                    origin="YouTube",
                    url=video["url"],
                    summary=f"Video encontrado por palavra-chave. {meta}".strip(),
                    category="match_videos",
                    relevance="Alta",
                    published_at=video.get("published") or "",
                )
            )
    except Exception as error:
        errors.append({"source": "YouTube (palavra-chave)", "error": error.__class__.__name__})

    for category, suffix in (
        ("analysis_videos", "análise tática"),
        ("team_form", ""),
    ):
        try:
            sources.extend(_duckduckgo_lookup(f"{query} {suffix}".strip(), category))
        except Exception as error:
            errors.append({"source": f"Busca por palavra-chave ({category})", "error": error.__class__.__name__})
    if not sources:
        sources = _guided_video_sources(query)
    return sources


def _collect_from_public_apis(query: str, errors: list[dict]) -> list[dict]:
    if not query:
        raise ValueError("Informe o nome do time ou termo para consultar as APIs publicas.")
    sources: list[dict] = []

    try:
        wikipedia = fetch_team_wikipedia_profile(query)
        if wikipedia:
            sources.append(
                _source(
                    title=wikipedia["title"],
                    origin="Wikipedia (API publica)",
                    url=wikipedia.get("page_url") or "",
                    summary=wikipedia["summary"],
                    category="team_form",
                    relevance="Alta",
                )
            )
    except Exception as error:
        errors.append({"source": "Wikipedia", "error": error.__class__.__name__})

    try:
        sources.extend(_thesportsdb_lookup(query))
    except Exception as error:
        errors.append({"source": "TheSportsDB", "error": error.__class__.__name__})

    return sources


def _thesportsdb_lookup(query: str) -> list[dict]:
    """TheSportsDB é uma API pública gratuita (chave de teste '3') com ficha
    de clubes: liga, país, estádio e descrição."""
    encoded = urllib.parse.quote(query)
    payload = json.loads(_fetch_text(f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={encoded}"))
    sources = []
    for team in (payload.get("teams") or [])[:3]:
        name = team.get("strTeam") or query
        description = (
            team.get("strDescriptionPT")
            or team.get("strDescriptionBR")
            or team.get("strDescriptionEN")
            or ""
        ).strip()
        facts = ", ".join(
            part
            for part in (
                team.get("strLeague"),
                team.get("strCountry"),
                team.get("strStadium"),
                f"fundado em {team['intFormedYear']}" if team.get("intFormedYear") else "",
            )
            if part
        )
        summary = " ".join(description.split())[:420] or f"Ficha publica do clube: {facts}."
        sources.append(
            _source(
                title=f"Ficha do clube: {name}",
                origin="TheSportsDB (API publica)",
                url=team.get("strWebsite") or f"https://www.thesportsdb.com/team/{team.get('idTeam') or ''}",
                summary=f"{summary} {facts}".strip(),
                category="team_form",
                relevance="Alta",
            )
        )
    return sources


def _fetch_html_capped(url: str) -> str:
    # Sites de video (YouTube, Vimeo, etc.) devolvem 403/HTTPError para um
    # user-agent "de robo"; um UA de navegador comum e o que evita o bloqueio
    # (mesma solucao ja usada em web_search/youtube_search).
    return fetch_page(url, timeout=TIMEOUT_SECONDS)


def _validate_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Somente links http:// ou https:// sao aceitos.")
    hostname = (parsed.hostname or "").casefold()
    if not hostname or hostname in _BLOCKED_HOSTNAMES:
        raise ValueError("Link invalido: informe uma URL publica.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Link invalido: enderecos internos/privados nao sao aceitos.")


def _categorize_link(url: str, text: str) -> str:
    lowered_url = url.casefold()
    lowered_text = text.casefold()
    if any(hint in lowered_text for hint in ANALYSIS_HINTS):
        return "analysis_videos"
    if any(domain in lowered_url for domain in VIDEO_DOMAINS):
        return "match_videos"
    return "team_form"


def _extract_title(page: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return " ".join(html.unescape(match.group(1)).split())[:180]


def _extract_meta(page: str, key: str) -> str:
    pattern = re.compile(
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(key)}["\'][^>]*content=["\'](?P<content>[^"\']*)["\']'
        rf'|<meta[^>]+content=["\'](?P<content2>[^"\']*)["\'][^>]*(?:name|property)=["\']{re.escape(key)}["\']',
        re.IGNORECASE,
    )
    match = pattern.search(page)
    if not match:
        return ""
    content = match.group("content") or match.group("content2") or ""
    return " ".join(html.unescape(content).split())[:420]


def _collect_note(mode: str, live_count: int, sources: list[dict], errors: list[dict]) -> str:
    if mode == "link":
        if live_count and not errors:
            return "Pagina lida com sucesso; titulo e resumo extraidos automaticamente."
        return "Link registrado; a leitura automatica da pagina falhou ou foi parcial, revise o resumo manualmente."
    if mode == "keyword":
        if live_count:
            return f"{live_count} fonte(s) ao vivo encontradas para a palavra-chave."
        return "Busca direta bloqueada neste ambiente; consultas estruturadas foram geradas para coleta manual."
    if live_count:
        return f"{live_count} resultado(s) de APIs publicas (Wikipedia/TheSportsDB)."
    return "APIs publicas sem resposta neste ambiente; tente novamente ou use o modo link/palavra-chave."
