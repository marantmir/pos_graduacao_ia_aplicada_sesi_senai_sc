"""Tactical Search Hub: orquestrador central de buscas paralelas com cache e ranking.

Fluxo:
1. Query normalizada (lowercase, trim, extract formação)
2. Check cache Redis
3. Se hit → return cached + metadata
4. Se miss → parallelizar buscas (web, YouTube, Wikipedia, APIs)
5. Consolidar resultados
6. Validar qualidade (duração, resolução)
7. Ranking tático (relevância + qualidade + autoridade)
8. Dedupe + cache 7 dias
9. Return sorted sources
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .cache_layer import cache_get, cache_set
from .parallel_search import parallel_tactical_search, merge_search_results
from .tactical_keywords import detect_language, extract_formation, parse_formation
from .tactical_ranking import rank_sources as rank_sources_impl
from .video_validator import validate_source

logger = logging.getLogger(__name__)

# ============================================================================
# Search Hub (Main Orchestrator)
# ============================================================================


def tactical_search(
    query: str,
    max_sources: int = 24,
    use_cache: bool = True,
    parallel: bool = True,
) -> dict:
    """Busca tática integrada com cache, ranking e validação.

    Args:
        query: query do usuário (ex: "Flamengo 4-2-3-1 pressão alta")
        max_sources: limite de resultados
        use_cache: usar cache Redis/SQLite
        parallel: paralelizar buscas

    Returns:
        {
            "query": query original,
            "query_normalized": query normalizada,
            "formation": "4-2-3-1" ou None,
            "cached": True/False,
            "cached_at": timestamp ou None,
            "sources": [...]  # Ranked + validated
            "summary": "...",
            "status": "available" | "partial" | "guided_fallback",
            "errors": [...],
        }
    """
    logger.info(f"Tactical search: {query}")

    # 1. Normalizar query + extrair formação
    query_normalized = _normalize_query(query)
    formation = extract_formation(query)
    formation_parsed = parse_formation(formation) if formation else None
    language = detect_language(query)

    # 2. Check cache
    if use_cache:
        cached = cache_get(query_normalized)
        if cached:
            logger.info(f"Cache hit: {query_normalized}")
            return {
                "query": query,
                "query_normalized": query_normalized,
                "formation": formation,
                "formation_parsed": formation_parsed,
                "language": language,
                "cached": True,
                "cached_at": cached.get("cached_at"),
                "sources": cached.get("sources", []),
                "summary": _build_summary(cached.get("sources", [])),
                "status": _infer_status(cached.get("sources", [])),
                "errors": [],
            }

    # 3. Paralelizar buscas
    logger.info(f"Cache miss: {query_normalized}. Fetching sources...")
    if parallel:
        sources = _search_parallel(query_normalized, formation, language)
    else:
        sources = _search_sequential(query_normalized, formation, language)

    errors = sources.pop("errors", [])

    # 4. Validar qualidade
    validated_sources = [validate_source(s) for s in sources]

    # 5. Ranking tático
    ranked_sources = rank_sources_impl(
        validated_sources,
        query=query,
        target_formation=formation,
    )

    # 6. Dedupe + limit
    deduped = _dedupe_sources(ranked_sources)[:max_sources]

    # 7. Cache resultado
    if use_cache:
        cache_set(query_normalized, deduped)
        logger.info(f"Cached {len(deduped)} sources for: {query_normalized}")

    return {
        "query": query,
        "query_normalized": query_normalized,
        "formation": formation,
        "formation_parsed": formation_parsed,
        "language": language,
        "cached": False,
        "cached_at": None,
        "sources": deduped,
        "summary": _build_summary(deduped),
        "status": _infer_status(deduped),
        "errors": errors,
    }


# ============================================================================
# Parallel Search Orchestration
# ============================================================================

def _search_parallel(query: str, formation: str | None, language: str) -> dict:
    """Executa buscas em paralelo: web + YouTube + Wikipedia + APIs.

    Com timeout adaptativo: se uma fonte falhar, outras continuam.
    """
    from ..online_search import search_public_team_info

    try:
        # Use existing integrated search que já consolida tudo
        result = search_public_team_info(query)
        return {
            "sources": result.get("sources", []),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error(f"Parallel search failed: {e}")
        return {"sources": [], "errors": [{"source": "parallel_search", "error": str(e)}]}


def _search_sequential(query: str, formation: str | None, language: str) -> dict:
    """Executa buscas sequencialmente (fallback)."""
    from ..online_search import search_public_team_info

    try:
        result = search_public_team_info(query)
        return {
            "sources": result.get("sources", []),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error(f"Sequential search failed: {e}")
        return {"sources": [], "errors": [{"source": "search", "error": str(e)}]}


# ============================================================================
# Utilities
# ============================================================================

def _normalize_query(query: str) -> str:
    """Normaliza query: lowercase, trim, remove extras."""
    return " ".join(query.strip().lower().split())


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    """Remove duplicados por URL + título."""
    seen = set()
    deduped = []

    for source in sources:
        url = (source.get("url") or "").strip().lower()
        title = (source.get("title") or "").strip().lower()
        key = (url or title)

        if key and key not in seen:
            seen.add(key)
            deduped.append(source)

    return deduped


def _build_summary(sources: list[dict]) -> str:
    """Constrói sumário human-readable dos resultados."""
    if not sources:
        return "Nenhuma fonte encontrada."

    by_category = {}
    for source in sources:
        cat = source.get("category", "team_form")
        by_category.setdefault(cat, 0)
        by_category[cat] += 1

    parts = [f"{count} {cat}" for cat, count in by_category.items()]
    return f"Coleta tática: {len(sources)} fontes ({', '.join(parts)})."


def _infer_status(sources: list[dict]) -> str:
    """Inferência de status: available | partial | guided_fallback."""
    if not sources:
        return "guided_fallback"

    live_count = sum(
        1 for s in sources
        if s.get("origin") not in {"Busca sugerida", "Pesquisa sugerida"}
    )

    if live_count >= 5:
        return "available"
    elif live_count > 0:
        return "partial"
    else:
        return "guided_fallback"


# ============================================================================
# Export Search Hub API
# ============================================================================

__all__ = ["tactical_search"]
