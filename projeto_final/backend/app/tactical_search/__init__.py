"""Tactical Search Hub: Sistema de busca tática integrado para futebol.

Pipeline completo de busca com cache, retry, paralelização, LLM e scoring temporal:

Fluxo:
1. Normalizar query + detectar formação + idioma
2. Check cache (Redis/SQLite com TTL 7 dias)
3. Se miss → buscar em paralelo (web, YouTube, Wikipedia)
4. Aplicar retry exponencial com jitter em falhas
5. Validar qualidade de vídeos (duração, resolução)
6. Ranking tático (palavras-chave + formação + autoridade)
7. Enriquecimento semântico via LLM (se disponível)
8. Scoring de recência (tendência de views, autoridade, temporal)
9. Dedupe + cache + return ranked sources

Componentes:
- cache_layer.py: Cache abstrato com fallback chain (Redis/SQLite/Memory)
- tactical_keywords.py: 200+ keywords em 3 idiomas + formação (4-3-3, 5-2-3, etc)
- video_validator.py: Parse de duração, resolução, qualidade (7 formatos)
- tactical_ranking.py: Ranking ponderado (45% tática, 20% qualidade, 20% autoridade, 15% categoria)
- retry_policy.py: Exponential backoff com jitter (1s→2s→4s→8s→16s capped, ±20%)
- parallel_search.py: Executor paralelo com timeout cascade (10s individual, 15s total)
- llm_tactical_enrichment.py: Query enrichment + re-ranking semântico multi-provider
- recency_scoring.py: 4 componentes (35% recency, 25% trend, 20% views, 20% authority)
- search_hub.py: Orquestrador central
- feature_flags.py: Controle de features via env vars com rollout gradual (0-100%)
- monitoring.py: Métricas de performance, cache, latência, qualidade, features

Feature Flags:
- Cache enable/disable via FOOTBALL_INTEL_FEATURE_CACHE_ENABLED
- LLM enrichment enable/disable via FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ENABLED
- Recency scoring enable/disable via FOOTBALL_INTEL_FEATURE_RECENCY_SCORING_ENABLED
- Rollout gradual (0-100%) com deterministic hashing per user_id
- Runtime configuration changes via get_feature_flags().set()

Monitoring:
- Cache hit/miss rates por backend
- Latência por componente (p50, p95, p99)
- Qualidade de ranking (score distribution)
- Uso de features (adoption percentages)
- Erros e tipos de erro
- Histórico recente para debugging

Requisitos:
- Python 3.11+
- redis (opcional, fallback para SQLite/Memory)
- urllib.request (built-in)

Exemplo de uso:

    from backend.app.tactical_search.search_hub import tactical_search

    result = tactical_search("Flamengo 4-3-3 pressão alta", max_sources=24)

    # result = {
    #     "query": "Flamengo 4-3-3 pressão alta",
    #     "formation": "4-3-3",
    #     "cached": False,
    #     "sources": [
    #         {
    #             "title": "...",
    #             "url": "...",
    #             "score": 8.5,
    #             "category": "analysis_videos",
    #             "tactical_score": 8.2,
    #             "recency_score": 7.8,
    #             "combined_score": 8.1,
    #             ...
    #         },
    #         ...
    #     ],
    #     "summary": "Coleta tática: 12 fontes (8 analysis_videos, 4 match_videos)",
    #     "status": "available",
    #     "errors": []
    # }

Controle de Features:

    from backend.app.tactical_search.feature_flags import get_feature_flags

    flags = get_feature_flags()

    # Verificar se feature está habilitada
    if flags.is_enabled("llm_query_enrichment_enabled"):
        # usar LLM
        pass

    # Rollout gradual para user específico (0-100%)
    if flags.rollout_pct("llm_query_enrichment", user_id="user123"):
        # dar feature para este user
        pass

    # Configurar em runtime
    flags.set("cache_ttl_days", 14)
    flags.set("retry_max_attempts", 5)

Monitoring:

    from backend.app.tactical_search.monitoring import get_monitor

    monitor = get_monitor()

    # Ver resumo de performance
    summary = monitor.get_summary()
    print(f"Cache hit rate: {summary['cache']}")
    print(f"Latência p95: {summary['latency']['total']['p95_ms']}ms")

    # Acesso via API
    # GET /api/teams/search/tactical/monitoring
    # GET /api/teams/search/tactical/monitoring/recent?limit=10
"""
from .search_hub import tactical_search
from .feature_flags import get_feature_flags
from .monitoring import get_monitor

__all__ = ["tactical_search", "get_feature_flags", "get_monitor"]
__version__ = "2.4.0"
