from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import re
import urllib.parse
import urllib.request

from .llm_assistant import enrich_team_search, tactical_search_queries
from .web_search import search_web
from .wikipedia_lookup import fetch_team_wikipedia_profile
from .youtube_search import search_youtube_videos


USER_AGENT = "football-intelligence-platform/0.3 tactical-video-intelligence"
TIMEOUT_SECONDS = 5
MAX_SOURCES = 24

# Keywords that indicate a scraped result is about a *different* sport than
# football/soccer, so it can be dropped even though the team name matched.
NON_FOOTBALL_KEYWORDS = (
    "basquete", "basketball", "nba",
    "volei", "vôlei", "voleibol", "volleyball",
    "handebol", "handball",
    "rugby", "rúgbi",
    "hoquei", "hóquei", "hockey", "nhl",
    "tenis", "tênis", "tennis",
    "mma", "ufc", "boxe", "boxing",
    "formula 1", "fórmula 1", "motogp", "nascar",
    "nfl", "futebol americano", "american football",
    "beisebol", "baseball", "mlb",
    "atletismo", "ciclismo", "cycling", "natacao", "natação", "swimming", "golfe", "golf",
    # Localização - filtros adicionais para evitar cidades/estados
    "história", "turismo", "cidade", "município", "região", "estado",
    "população", "clima", "economia", "cultura", "arquitetura", "gastronomia",
    "mapa", "distância", "viagem", "transportes", "cartografia",
)

# Keywords that confirm a result is about football/soccer
FOOTBALL_KEYWORDS = (
    "futebol", "football", "soccer", "time", "equipe", "jogador", "jogo",
    "gol", "gols", "pênalti", "escanteio", "falta", "cartão", "vermelho",
    "formação", "tática", "estratégia", "defesa", "ataque", "meia",
    "zagueiro", "lateral", "volante", "meia", "ponta", "atacante",
    "técnico", "treinador", "técnica", "scouting", "análise tática",
    "performance", "velocidade", "resistência", "passes", "chutes",
)

# Keywords that indicate the team/club is from women's football, used as a
# best-effort default when the caller does not state the category explicitly.
FEMALE_FOOTBALL_KEYWORDS = (
    "futebol feminino", "feminino", "femenino", "femenina",
    "women's", "womens", "women", "female", "ladies",
)


def _looks_like_football(*texts: str) -> bool:
    """Best-effort filter: reject scraped results that are clearly about a
    different sport or location/city, ensuring only football/soccer content
    is returned. Verifies it's NOT about other sports AND contains football context."""
    combined = " ".join(text or "" for text in texts).casefold()

    # Reject if it's clearly about another sport or location
    if any(keyword in combined for keyword in NON_FOOTBALL_KEYWORDS):
        return False

    # Accept if contains strong football/soccer indicators
    if any(keyword in combined for keyword in FOOTBALL_KEYWORDS):
        return True

    # If ambiguous (e.g., just team name), require football context or reject
    # to avoid false positives for cities/places
    return False


def detect_team_category(*texts: str) -> str:
    """Best-effort men's/women's classification from free text (team name,
    wikipedia description/summary, scraped titles). Defaults to "Masculino"
    when no women's-football indicator is found - reviewable/editable by the
    analyst afterwards, same as every other auto-collected field in the app."""
    combined = " ".join(text or "" for text in texts).casefold()
    if any(keyword in combined for keyword in FEMALE_FOOTBALL_KEYWORDS):
        return "Feminino"
    return "Masculino"


def _fetch_text(url: str, timeout: int = TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, timeout: int = TIMEOUT_SECONDS) -> dict | list:
    return json.loads(_fetch_text(url, timeout=timeout))


def search_public_team_info(team_name: str) -> dict:
    """Best-effort tactical source lookup.

    This intentionally avoids institutional team data. The goal is to find
    videos, tactical breakdowns and match-footage references that can feed the
    visual analysis pipeline.
    """
    cleaned_name = " ".join(team_name.strip().split())
    query_text = f"{cleaned_name} futebol análise tática vídeos"
    errors: list[dict] = []
    sources: list[dict] = []

    search_queries = tactical_search_queries(cleaned_name)
    for item in search_queries:
        sources.extend(
            _try_collect(
                item["label"],
                lambda item=item: _duckduckgo_lookup(item["query"], item["category"]),
                errors,
            )
        )
    # Vídeos reais do YouTube (sem chave de API) para alimentar diretamente a
    # análise visual; se falhar, o fallback guiado abaixo garante os links.
    sources.extend(_try_collect("YouTube videos", lambda: _youtube_video_sources(cleaned_name), errors))
    sources.extend(_guided_video_sources(cleaned_name))

    wikipedia = _try_collect_one("Wikipedia", lambda: fetch_team_wikipedia_profile(cleaned_name), errors)
    if wikipedia and not _looks_like_football(wikipedia.get("description")):
        # Same name, wrong subject (e.g. a person, city or company page) -
        # discard rather than attach mismatched club data.
        wikipedia = None
    if wikipedia:
        sources.append(
            _source(
                title=wikipedia["title"],
                origin="Wikipedia",
                url=wikipedia.get("page_url") or "",
                summary=wikipedia["summary"],
                category="team_form",
                relevance="Alta",
            )
        )

    team_category = detect_team_category(
        cleaned_name,
        wikipedia.get("description") if wikipedia else "",
        wikipedia.get("summary") if wikipedia else "",
    )

    sources = _dedupe_sources(sources)[:MAX_SOURCES]
    source_groups = _group_sources(sources)
    coverage = {key: len(value) for key, value in source_groups.items()}
    live_count = sum(1 for source in sources if source.get("origin") not in {"Busca sugerida", "Pesquisa sugerida"})
    status = _status_from(live_count, errors)

    result = {
        "status": status,
        "query": query_text,
        "llm_query_plan": search_queries,
        "summary": _build_summary(cleaned_name, sources, coverage, live_count),
        "sources": sources,
        "source_groups": source_groups,
        "coverage": coverage,
        "analysis_focus": _analysis_focus(cleaned_name, source_groups),
        "collection_plan": _collection_plan(cleaned_name),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "errors": errors[:6],
        "note": _build_note(status, live_count, errors),
        "wikipedia": wikipedia,
        "crest_url": wikipedia.get("crest_url") if wikipedia else None,
        "category": team_category,
    }
    result["llm_search"] = enrich_team_search(cleaned_name, result)
    return result


def _try_collect(label: str, collect, errors: list[dict]) -> list[dict]:
    try:
        return collect()
    except Exception as error:
        errors.append({"source": label, "error": error.__class__.__name__})
        return []


def _try_collect_one(label: str, collect, errors: list[dict]):
    try:
        return collect()
    except Exception as error:
        errors.append({"source": label, "error": error.__class__.__name__})
        return None


def _duckduckgo_lookup(query: str, category: str) -> list[dict]:
    """Busca web publica resiliente: tenta varios motores (DuckDuckGo HTML,
    DuckDuckGo Lite e Bing) ate obter resultados, com user-agent de navegador.
    Isso substitui o endpoint unico que falhava com URLError em producao."""
    outcome = search_web(query, max_results=6)
    sources = []
    for result in outcome["results"]:
        title = result.get("title") or ""
        url = result.get("url") or ""
        if not title or not url:
            continue
        if not _looks_like_football(title, result.get("snippet", "")):
            continue
        sources.append(
            _source(
                title=title,
                origin="Busca web publica",
                url=url,
                summary=result.get("snippet")
                or f"Referencia publica para revisar padroes taticos e material visual: {query}",
                category=category,
                relevance="Media",
            )
        )
    if not sources and outcome["errors"]:
        # Propaga a falha para que o chamador registre o motivo (todos os
        # motores caíram), mantendo o fallback guiado como rede de seguranca.
        engines = ", ".join(item["engine"] for item in outcome["errors"])
        raise RuntimeError(f"Motores de busca indisponiveis: {engines}")
    return sources


def _youtube_video_sources(team_name: str) -> list[dict]:
    """Vídeos reais do YouTube (título, canal, duração) para jogo completo,
    melhores momentos e análise tática - prontos para o analista escolher e
    subir no pipeline de visão computacional."""
    queries = [
        ("match_videos", f"{team_name} futebol jogo completo", "Jogo completo / melhores momentos"),
        ("analysis_videos", f"{team_name} análise tática como joga", "Análise tática / modelo de jogo"),
    ]
    sources: list[dict] = []
    for category, query, label in queries:
        for video in search_youtube_videos(query, limit=4):
            meta = " · ".join(
                part for part in (video.get("channel"), video.get("duration"), video.get("published")) if part
            )
            sources.append(
                _source(
                    title=video["title"],
                    origin="YouTube",
                    url=video["url"],
                    summary=f"{label}. {meta}".strip(),
                    category=category,
                    relevance="Alta",
                    published_at=video.get("published") or "",
                )
            )
    return sources


def _guided_video_sources(team_name: str) -> list[dict]:
    # No video platform offers a free API to download match footage in bulk,
    # and scraping/downloading from them would breach their Terms of Service.
    # So instead of fetching video files automatically, this widens the net of
    # free, no-key search entry points across "varios lugares" (several video
    # sources) the analyst can open and manually upload from into the
    # computer-vision pipeline.
    searches = [
        (
            "match_videos",
            "YouTube melhores momentos",
            "Vídeos de jogo e melhores momentos",
            "youtube.com/results",
            f"{team_name} futebol melhores momentos jogo completo análise",
            "Alta",
        ),
        (
            "analysis_videos",
            "YouTube análise tática",
            "Análises táticas e comentários sobre o modelo de jogo",
            "youtube.com/results",
            f"{team_name} análise tática como joga",
            "Alta",
        ),
        (
            "match_videos",
            "DuckDuckGo vídeos",
            "Busca de vídeos agregando várias fontes",
            "duckduckgo.com/videos",
            f"{team_name} futebol jogo completo melhores momentos",
            "Alta",
        ),
        (
            "match_videos",
            "Vimeo",
            "Videos de jogo em canais e producoes independentes",
            "vimeo.com/search",
            f"{team_name} futebol jogo",
            "Media",
        ),
        (
            "analysis_videos",
            "Dailymotion",
            "Vídeos de jogo e análise em outra plataforma gratuita",
            "dailymotion.com/search",
            f"{team_name} futebol análise tática",
            "Média",
        ),
        (
            "team_form",
            "Busca web tática",
            "Padrões de jogo e comportamento coletivo",
            "google.com/search",
            f"{team_name} futebol padrões táticos saída de bola pressão transição",
            "Média",
        ),
    ]
    sources = []
    for category, origin, title, domain, query, relevance in searches:
        sources.append(
            _source(
                title=f"{title}: {team_name}",
                origin="Busca sugerida",
                url=_search_url(domain, query),
                summary=(
                    "Consulta estruturada para coletar material visual e tatico quando a busca direta "
                    "do ambiente estiver bloqueada ou incompleta."
                ),
                category=category,
                relevance=relevance,
            )
        )
    return sources


def _search_url(domain: str, query: str) -> str:
    encoded = urllib.parse.quote(query)
    if domain == "youtube.com/results":
        return f"https://www.youtube.com/results?search_query={encoded}"
    if domain == "duckduckgo.com/videos":
        return f"https://duckduckgo.com/?q={encoded}&iar=videos&ia=videos"
    if domain == "vimeo.com/search":
        return f"https://vimeo.com/search?q={encoded}"
    if domain == "dailymotion.com/search":
        return f"https://www.dailymotion.com/search/{encoded}"
    return f"https://www.google.com/search?q={encoded}"


def _source(
    *,
    title: str,
    origin: str,
    url: str,
    summary: str,
    category: str,
    relevance: str,
    published_at: str = "",
) -> dict:
    return {
        "title": title,
        "origin": origin,
        "url": url,
        "summary": summary,
        "category": category,
        "relevance": relevance,
        "published_at": published_at,
    }


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for source in sources:
        key = (source.get("url") or source.get("title") or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _group_sources(sources: list[dict]) -> dict[str, list[dict]]:
    groups = {
        "match_videos": [],
        "analysis_videos": [],
        "team_form": [],
    }
    for source in sources:
        groups.setdefault(source.get("category") or "team_form", []).append(source)
    return groups


def _status_from(live_count: int, errors: list[dict]) -> str:
    if live_count > 0 and errors:
        return "partial"
    if live_count > 0:
        return "available"
    return "guided_fallback"


def _build_summary(team_name: str, sources: list[dict], coverage: dict, live_count: int) -> str:
    if live_count:
        return (
            f"Coleta tática para {team_name}: {len(sources)} referências organizadas, "
            f"incluindo {coverage.get('match_videos', 0)} referências de vídeo, "
            f"{coverage.get('analysis_videos', 0)} análises táticas e "
            f"{coverage.get('team_form', 0)} fontes sobre padrões de jogo."
        )
    return (
        f"A busca direta não retornou fontes ao vivo neste ambiente. Mesmo assim, o dossiê de {team_name} "
        "foi preparado com consultas estruturadas para vídeos de jogos e análises táticas."
    )


def _analysis_focus(team_name: str, groups: dict[str, list[dict]]) -> list[str]:
    focus = [
        f"Comparar vídeos de {team_name} para separar posse, pressão, transições e último terço.",
        "Separar vídeos por jogo: saída de bola, pressão, transições, bola parada e último terço.",
        "Priorizar trechos com câmera aberta para melhorar tracking, homografia e leitura coletiva.",
    ]
    if groups.get("analysis_videos"):
        focus.append("Priorizar vídeos de análise tática para validar padrões observados no rastreamento.")
    return focus


def _collection_plan(team_name: str) -> list[dict]:
    return [
        {
            "stage": "Videos de jogos",
            "action": f"Coletar melhores momentos e jogos completos recentes de {team_name}.",
        },
        {
            "stage": "Recortes taticos",
            "action": "Separar trechos de ataque posicional, transicao, pressao e bola parada.",
        },
        {
            "stage": "Analise visual",
            "action": "Subir os vídeos no painel para extrair trilhas, heatmap, conexões e eventos táticos.",
        },
        {
            "stage": "Decisão",
            "action": "Combinar grafo, visão computacional e explicação tática do vídeo.",
        },
    ]


def _build_note(status: str, live_count: int, errors: list[dict]) -> str:
    if status == "available":
        return "Busca pública restrita a material tático e vídeos analisáveis."
    if status == "partial":
        failed = ", ".join(error["source"] for error in errors[:3])
        return f"Busca tática parcial: {live_count} fonte(s) ao vivo; falhas tratadas em {failed}."
    return "Busca direta bloqueada ou sem resposta; links estruturados foram gerados para coleta manual."


def _unwrap_duckduckgo_url(url: str) -> str:
    if "uddg=" not in url:
        return url
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return params.get("uddg", [url])[0]


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value or "").split())
