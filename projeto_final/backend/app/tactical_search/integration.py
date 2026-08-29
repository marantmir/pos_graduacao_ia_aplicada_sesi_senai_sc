"""Integration layer between Tactical Search Hub and online_search.

Conecta o pipeline completo de busca tática com o sistema de busca existente.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .search_hub import tactical_search
from .llm_tactical_enrichment import rank_sources_with_llm, explain_search_results
from .recency_scoring import boost_tactical_score_with_recency
from .monitoring import get_monitor, QueryMetrics, TimingContext
from .tactical_keywords import extract_formation

logger = logging.getLogger(__name__)


def search_tactical_enhanced(
    team_name: str,
    query: str | None = None,
    max_sources: int = 24,
    use_cache: bool = True,
    use_llm_ranking: bool = True,
    use_recency: bool = True,
) -> dict:
    """Search tática com pipeline completo: cache + retry + paralelo + LLM + recência.

    Args:
        team_name: Nome do time (ex: "Flamengo")
        query: Query custom (ex: "4-3-3 pressão alta"). Se None, auto-gera.
        max_sources: Limite de resultados
        use_cache: Usar cache Redis/SQLite
        use_llm_ranking: Re-ranking com LLM (se disponível)
        use_recency: Aplicar scoring de recência

    Returns:
        {
            "team_name": "...",
            "query": "...",
            "formation": "4-3-3" ou None,
            "cached": True/False,
            "sources": [
                {
                    "title": "...",
                    "url": "...",
                    "tactical_score": 8.2,
                    "recency_score": 7.8,
                    "combined_score": 8.1,
                    ...
                }
            ],
            "summary": "Coleta tática: 12 fontes",
            "explanations": {
                "summary": "...",
                "highlights": [...],
                "next_actions": [...]
            },
            "status": "available" | "partial" | "guided_fallback",
            "errors": []
        }
    """
    logger.info(f"Tactical search enhanced: {team_name}")
    total_start = time.monotonic()
    monitor = get_monitor()

    try:
        # 1. Usar query customizada ou gerar a partir do team_name
        search_query = query or f"{team_name} futebol"

        # 2. Executar pipeline tático completo
        with TimingContext("tactical_search") as search_timer:
            result = tactical_search(
                search_query,
                max_sources=max_sources,
                use_cache=use_cache,
                parallel=True,
            )

        # 3. Enriquecer com LLM se disponível e solicitado
        llm_duration = 0.0
        if use_llm_ranking and result["sources"]:
            logger.debug(f"Applying LLM ranking to {len(result['sources'])} sources")
            with TimingContext("llm_ranking") as llm_timer:
                try:
                    ranked_result = rank_sources_with_llm(
                        result["sources"],
                        search_query,
                        formation=result.get("formation"),
                        top_k=max_sources,
                    )
                    result["sources"] = [r["source"] for r in ranked_result.get("ranked", [])]
                    result["llm_ranking"] = ranked_result.get("status", "local_fallback")
                except Exception as e:
                    logger.warning(f"LLM ranking failed: {e}")
                    result["llm_ranking"] = "error"
                llm_duration = llm_timer.duration

        # 4. Aplicar scoring de recência se solicitado
        recency_duration = 0.0
        if use_recency and result["sources"]:
            logger.debug(f"Applying recency scoring to {len(result['sources'])} sources")
            with TimingContext("recency_scoring") as recency_timer:
                enhanced_sources = []
                for source in result["sources"][:max_sources]:
                    enhanced = boost_tactical_score_with_recency(
                        source,
                        source.get("score", 5.0),
                        recency_weight=0.20,
                    )
                    enhanced_sources.append(enhanced)
                result["sources"] = enhanced_sources
                recency_duration = recency_timer.duration

        # 5. Gerar explicações se houver fontes
        if result["sources"]:
            logger.debug("Generating search explanations")
            try:
                explanations = explain_search_results(
                    result["sources"],
                    search_query,
                    formation=result.get("formation"),
                    language=result.get("language", "pt-BR"),
                )
                result["explanations"] = explanations
            except Exception as e:
                logger.warning(f"Explanation generation failed: {e}")

        # 6. Adicionar metadata
        result["team_name"] = team_name
        result["search_method"] = "tactical_search_hub_v2.4"
        result["retrieved_at"] = datetime.now(timezone.utc).isoformat()

        # 7. Registrar métricas de monitoring
        total_duration = time.monotonic() - total_start
        formation = extract_formation(search_query)
        sources = result.get("sources", [])

        metrics = QueryMetrics(
            team_name=team_name,
            query=search_query,
            formation=formation,
            duration_total=total_duration,
            duration_search=search_timer.duration,
            duration_llm=llm_duration,
            duration_recency=recency_duration,
            cache_hit=result.get("cached", False),
            cache_backend=result.get("cache_backend", "none"),
            source_count=len(sources),
            top_score=sources[0].get("combined_score", sources[0].get("score", 0.0)) if sources else 0.0,
            avg_score=sum(s.get("combined_score", s.get("score", 5.0)) for s in sources) / len(sources) if sources else 0.0,
            llm_enabled=use_llm_ranking,
            llm_used=use_llm_ranking and len(sources) > 0,
            recency_enabled=use_recency,
            recency_used=use_recency and len(sources) > 0,
            formation_detected=formation is not None,
            status=result.get("status", "unknown"),
            error=None,
        )
        monitor.record_query(metrics)

        return result

    except Exception as e:
        # Record error in monitoring
        total_duration = time.monotonic() - total_start
        metrics = QueryMetrics(
            team_name=team_name,
            query=query or f"{team_name} futebol",
            duration_total=total_duration,
            status="error",
            error=str(e),
        )
        monitor.record_query(metrics)
        raise


def enrich_online_search_result(
    online_search_result: dict,
    apply_tactical_scoring: bool = True,
) -> dict:
    """Enriquece resultado de search_public_team_info() com scoring tático avançado.

    Este é um wrapper que permite integrar o Tactical Search Hub ao sistema
    existente de forma retroativa, sem quebrar a API existente.

    Args:
        online_search_result: Resultado de search_public_team_info()
        apply_tactical_scoring: Aplicar scoring tático avançado

    Returns:
        Resultado enriquecido
    """
    if not apply_tactical_scoring or not online_search_result.get("sources"):
        return online_search_result

    team_name = online_search_result.get("team_name")
    if not team_name:
        return online_search_result

    logger.info(f"Enriching search result for {team_name} with tactical scoring")

    try:
        # Extrair formação se possível da query
        from .tactical_keywords import extract_formation

        query = online_search_result.get("query", "")
        formation = extract_formation(query)

        # Aplicar scoring de recência aos sources existentes
        from .recency_scoring import apply_recency_bonus

        enriched_sources = []
        for source in online_search_result.get("sources", []):
            enhanced = apply_recency_bonus(source, source.get("score"))
            enriched_sources.append(enhanced)

        online_search_result["sources"] = enriched_sources
        online_search_result["tactical_hub_enriched"] = True
        online_search_result["formation_detected"] = formation

        logger.info(f"Enriched {len(enriched_sources)} sources with tactical scoring")
    except Exception as e:
        logger.warning(f"Enrichment failed: {e}")
        online_search_result["tactical_hub_enriched"] = False

    return online_search_result


# ============================================================================
# Export API
# ============================================================================

__all__ = [
    "search_tactical_enhanced",
    "enrich_online_search_result",
]
