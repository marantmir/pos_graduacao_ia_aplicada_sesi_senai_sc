"""API Routes for Tactical Search Hub v2.4

Endpoints para busca tática integrada com cache, retry, paralelização e LLM.

GET /api/teams/search/tactical?team=Flamengo&formation=4-3-3&use_llm=true&use_recency=true
"""
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timezone

from ..tactical_search.integration import search_tactical_enhanced, enrich_online_search_result
from ..tactical_search.feature_flags import (
    get_feature_flags,
    cache_enabled,
    llm_enrichment_enabled,
    recency_scoring_enabled,
)
from ..tactical_search.monitoring import get_monitor
from ..online_search import search_public_team_info

router = APIRouter(prefix="/api/teams/search", tags=["tactical-search"])


@router.get("/tactical")
def search_tactical(
    team: str = Query(..., min_length=1, description="Nome do time"),
    formation: str | None = Query(None, description="Formação (ex: 4-3-3)"),
    use_cache: bool = Query(True, description="Usar cache Redis/SQLite"),
    use_llm: bool = Query(True, description="Usar enriquecimento LLM"),
    use_recency: bool = Query(True, description="Usar scoring de recência"),
    max_sources: int = Query(24, ge=1, le=100, description="Número máximo de fontes"),
):
    """Busca tática integrada com pipeline completo.

    Features:
    - Cache estratificado (Redis → SQLite → Memory)
    - Retry exponencial com jitter em falhas transitórias
    - Busca paralela (web, YouTube, Wikipedia)
    - Ranking tático (45% keywords, 20% quality, 20% authority, 15% category)
    - Enriquecimento LLM com explicações em PT-BR
    - Scoring de recência (view trends, decay temporal)

    Exemplo:
        GET /api/teams/search/tactical?team=Flamengo&formation=4-3-3&use_llm=true

    Returns:
        {
            "team_name": "Flamengo",
            "query": "Flamengo futebol",
            "formation": "4-3-3",
            "cached": false,
            "sources": [
                {
                    "title": "...",
                    "url": "...",
                    "score": 8.5,
                    "tactical_score": 8.2,
                    "recency_score": 7.8,
                    "combined_score": 8.1,
                    "category": "analysis_videos",
                    "views": "100K",
                    "published": "2 days ago"
                }
            ],
            "summary": "Coleta tática: 12 fontes (8 analysis_videos, 4 match_videos)",
            "explanations": {
                "summary": "Foram encontradas...",
                "highlights": [...],
                "next_actions": [...]
            },
            "status": "available | partial | guided_fallback",
            "errors": []
        }
    """
    try:
        # Get feature flag status
        flags = get_feature_flags()

        # Respect feature flags: disable features if not enabled
        cache_allowed = cache_enabled()
        llm_allowed = llm_enrichment_enabled()
        recency_allowed = recency_scoring_enabled()

        # Override user parameters if features are disabled
        effective_cache = use_cache and cache_allowed
        effective_llm = use_llm and llm_allowed
        effective_recency = use_recency and recency_allowed

        # Montar query com formação se fornecida
        query = team
        if formation:
            query = f"{team} {formation}"

        # Executar busca tática integrada
        result = search_tactical_enhanced(
            team_name=team,
            query=query,
            max_sources=max_sources,
            use_cache=effective_cache,
            use_llm_ranking=effective_llm,
            use_recency=effective_recency,
        )

        # Add feature flag status to response
        result["feature_flags"] = {
            "cache_enabled": cache_allowed,
            "llm_enrichment_enabled": llm_allowed,
            "recency_scoring_enabled": recency_allowed,
            "cache_used": effective_cache,
            "llm_used": effective_llm,
            "recency_used": effective_recency,
        }

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Tactical search failed: {str(e)}"
        )


@router.get("/tactical/enhanced")
def search_with_enrichment(
    team: str = Query(..., min_length=1, description="Nome do time"),
    enrichment: bool = Query(True, description="Aplicar enriquecimento adicional"),
):
    """Busca com enriquecimento retroativo da search_public_team_info.

    Use quando quiser compatibilidade com a busca existente mas com scoring
    tático avançado aplicado aos resultados.

    Exemplo:
        GET /api/teams/search/tactical/enhanced?team=Flamengo

    Returns:
        Resultado de search_public_team_info enriquecido com:
        - Scoring de recência em cada fonte
        - Formação detectada na query
        - Campo tactical_hub_enriched: true/false
    """
    try:
        # Usar busca existente
        online_result = search_public_team_info(team)

        # Enriquecer com Tactical Search Hub scoring
        if enrichment:
            enriched = enrich_online_search_result(
                online_result,
                apply_tactical_scoring=True,
            )
        else:
            enriched = online_result

        return enriched

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search enrichment failed: {str(e)}"
        )


@router.get("/tactical/compare")
def compare_search_methods(
    team: str = Query(..., min_length=1, description="Nome do time"),
):
    """Comparação entre busca tradicional e Tactical Search Hub.

    Útil para validar que o novo sistema melhora os resultados mantendo
    compatibilidade com a busca existente.

    Returns:
        {
            "team": "Flamengo",
            "traditional_search": {...},
            "tactical_search": {...},
            "comparison": {
                "source_count_difference": 5,
                "top_3_tactical_sources_average_score": 8.4,
                "cache_hit": false,
                "processing_time_ms": 245
            }
        }
    """
    try:
        import time

        start_time = time.time()

        # 1. Busca tradicional
        traditional = search_public_team_info(team)

        # 2. Busca tática
        tactical = search_tactical_enhanced(
            team_name=team,
            use_cache=False,  # Para comparação justa
            use_llm_ranking=True,
            use_recency=True,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        # 3. Comparação
        tactical_sources = tactical.get("sources", [])
        top_3_scores = [
            s.get("combined_score", s.get("score", 5.0))
            for s in tactical_sources[:3]
        ]
        avg_top_3 = sum(top_3_scores) / len(top_3_scores) if top_3_scores else 0

        return {
            "team": team,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "traditional_search": {
                "source_count": len(traditional.get("sources", [])),
                "status": traditional.get("status"),
                "has_wikipedia": traditional.get("wikipedia") is not None,
            },
            "tactical_search": {
                "source_count": len(tactical_sources),
                "status": tactical.get("status"),
                "formation": tactical.get("formation"),
                "cached": tactical.get("cached", False),
                "explanations": tactical.get("explanations") is not None,
            },
            "comparison": {
                "source_count_difference": len(tactical_sources) - len(traditional.get("sources", [])),
                "top_3_tactical_average_score": round(avg_top_3, 2),
                "processing_time_ms": round(elapsed_ms, 0),
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Comparison failed: {str(e)}"
        )


@router.get("/tactical/status")
def get_tactical_search_status():
    """Status da infraestrutura de Tactical Search Hub.

    Verifica:
    - Cache (Redis/SQLite/Memory)
    - LLM configuration
    - Performance metrics
    """
    try:
        from ..llm_assistant import llm_status
        from ..tactical_search.cache_layer import cache_get

        # Check cache
        test_key = "tactical_search_status_check"
        test_value = {"check": "ok"}
        try:
            from ..tactical_search.cache_layer import cache_set
            cache_set(test_key, test_value)
            cached = cache_get(test_key)
            cache_ok = cached == test_value
        except Exception:
            cache_ok = False

        # Check LLM
        llm_config = llm_status()

        # Get feature flags configuration
        flags = get_feature_flags()
        flag_snapshot = flags.get_config_snapshot()
        flag_warnings = flags.validate()

        return {
            "status": "operational" if cache_ok else "degraded",
            "tactical_search_hub": {
                "version": "2.4.0",
                "features": {
                    "cache": cache_ok,
                    "retry_policy": True,
                    "parallel_search": True,
                    "llm_integration": llm_config["enabled"],
                    "recency_scoring": True,
                },
                "cache": {
                    "available": cache_ok,
                    "backend": "Redis/SQLite/Memory",
                    "ttl_days": flags.get("cache_ttl_days", 7),
                },
                "llm": {
                    "available": llm_config["enabled"],
                    "provider": llm_config.get("provider", "none"),
                    "model": llm_config.get("model", "none"),
                },
            },
            "feature_flags": {
                "cache_enabled": flags.is_enabled("cache_enabled"),
                "llm_query_enrichment_enabled": flags.is_enabled("llm_query_enrichment_enabled"),
                "llm_semantic_ranking_enabled": flags.is_enabled("llm_semantic_ranking_enabled"),
                "recency_scoring_enabled": flags.is_enabled("recency_scoring_enabled"),
                "retry_enabled": flags.is_enabled("retry_enabled"),
                "parallel_enabled": flags.is_enabled("parallel_enabled"),
                "ab_test_enabled": flags.is_enabled("ab_test_enabled"),
                "warnings": flag_warnings,
            },
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/tactical/monitoring")
def get_monitoring_data():
    """Monitoring dashboard para Tactical Search Hub.

    Retorna estatísticas de performance:
    - Cache hit/miss rates por backend
    - Latência de queries (min/max/avg/p50/p95/p99)
    - Qualidade de ranking (score distribution)
    - Uso de features (LLM, recency, formation detection)
    - Erros e taxas de erro
    - Histórico recente de queries

    Exemplo:
        GET /api/teams/search/tactical/monitoring

    Returns:
        {
            "total_queries": 1523,
            "cache": {
                "redis": {
                    "hits": 850,
                    "misses": 673,
                    "hit_rate_percent": 55.8
                }
            },
            "latency": {
                "total": {
                    "min_ms": 45.2,
                    "max_ms": 2340.5,
                    "avg_ms": 340.7,
                    "p95_ms": 1200.3,
                    "p99_ms": 2000.1
                },
                "llm": {...}
            },
            "features": {
                "llm_enrichment_percent": 65.0,
                "recency_scoring_percent": 80.0
            },
            "errors": {...}
        }
    """
    try:
        monitor = get_monitor()
        summary = monitor.get_summary()
        return summary

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Monitoring query failed: {str(e)}"
        )


@router.get("/tactical/monitoring/recent")
def get_recent_monitoring_data(limit: int = Query(10, ge=1, le=100)):
    """Histórico recente de queries para debugging.

    Exemplo:
        GET /api/teams/search/tactical/monitoring/recent?limit=20
    """
    try:
        monitor = get_monitor()
        recent = monitor.get_recent_queries(limit=limit)
        return {
            "limit": limit,
            "count": len(recent),
            "queries": recent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Recent monitoring query failed: {str(e)}"
        )


__all__ = ["router"]
