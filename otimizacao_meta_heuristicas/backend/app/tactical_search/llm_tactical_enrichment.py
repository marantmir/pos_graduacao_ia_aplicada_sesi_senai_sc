"""Phase 2.3: LLM Integration para Tactical Search Hub.

Enriquecimento semântico de buscas táticas com explicações em português natural.

Funcionalidades:
- Geração de múltiplas variações de query (técnica → estratégia → vídeos)
- Re-ranking semântico baseado em similaridade de formação + tática
- Explicações naturais dos resultados (por que este vídeo é relevante)
- Validação de padrões com fallback determinístico
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from ..llm_assistant import (
    tactical_search_queries,
    _call_llm_json,
    _clean_text,
)

logger = logging.getLogger(__name__)


def enrich_tactical_search_queries(
    team_name: str,
    formation: str | None = None,
    language: str = "pt-BR",
    max_queries: int = 6,
) -> dict:
    """Gera múltiplas variações de query para busca tática.

    Usa LLM para criar queries semânticas:
    - Video de jogo completo com táticas
    - Análise profunda de formação (ex: 4-3-3)
    - Padrões de movimento + transição
    - Referências históricas de time
    - Comparativas com rivais táticos

    Args:
        team_name: Nome do time (ex: "Flamengo")
        formation: Formação detectada (ex: "4-3-3") ou None
        language: Idioma (pt-BR, es, en)
        max_queries: Número máximo de queries geradas

    Returns:
        {
            "base_queries": [{"label": "...", "query": "...", "category": "..."}],
            "enriched_queries": [{"label": "...", "query": "...", "category": "...", "rationale": "..."}],
            "formation_focused": [{"pattern": "4-3-3", "queries": [...]}],
            "status": "llm_enriched" | "local_fallback",
        }
    """
    # 1. Queries base (sempre disponível)
    base_queries = tactical_search_queries(team_name)

    # 2. Queries enriquecidas (se LLM disponível)
    enriched = _enrich_queries_with_llm(
        team_name,
        formation,
        base_queries,
        language,
    )

    # 3. Formation-focused queries
    formation_queries = _generate_formation_focused_queries(
        team_name,
        formation,
        language,
    ) if formation else []

    return {
        "base_queries": base_queries[:max_queries],
        "enriched_queries": enriched.get("enriched", [])[:max_queries],
        "formation_focused": formation_queries[:3],
        "status": enriched.get("status", "local_fallback"),
        "provider": enriched.get("provider", "deterministic_rules"),
    }


def rank_sources_with_llm(
    sources: list[dict],
    query: str,
    formation: str | None = None,
    language: str = "pt-BR",
    top_k: int = 10,
) -> dict:
    """Re-ranking semântico de fontes com explicações.

    O LLM avalia:
    - Relevância táctica (keywords + formação)
    - Qualidade visual (resolução, duração)
    - Autoridade (canal, views, verificação)
    - Pertinência ao contexto (histórico, competição)

    Args:
        sources: Lista de fontes encontradas
        query: Query original do usuário
        formation: Formação detectada
        language: Idioma para explicações
        top_k: Número de top sources com explicações

    Returns:
        {
            "ranked": [{"source": {...}, "score": 8.5, "explanation": "..."}],
            "summary": "Explicação geral dos resultados",
            "status": "llm_enriched" | "local_fallback",
        }
    """
    if not sources:
        return {
            "ranked": [],
            "summary": "Nenhuma fonte encontrada para análise.",
            "status": "local_fallback",
        }

    # 1. Ranking local (sempre disponível)
    local_ranked = _local_rank_with_scores(sources, formation)

    # 2. Re-ranking com LLM (se disponível)
    llm_ranked = _rerank_with_llm(
        local_ranked[:top_k],
        query,
        formation,
        language,
    )

    return llm_ranked


def explain_search_results(
    sources: list[dict],
    query: str,
    formation: str | None = None,
    language: str = "pt-BR",
) -> dict:
    """Gera explicação natural dos resultados da busca.

    Responde perguntas do usuário:
    - Por que este vídeo é relevante?
    - Qual é a melhor fonte para estudar a formação?
    - Há padrões consistentes entre os resultados?
    - Próximas ações recomendadas

    Args:
        sources: Fontes encontradas e ranqueadas
        query: Query do usuário
        formation: Formação detectada
        language: Idioma da explicação

    Returns:
        {
            "summary": "Resumo dos achados principais",
            "highlights": ["Padrão 1", "Padrão 2", ...],
            "next_actions": ["Ação 1", "Ação 2", ...],
            "caveats": ["Limitação 1", ...],
            "status": "llm_enriched" | "local_fallback",
        }
    """
    if not sources:
        fallback = _fallback_explanation(query, formation, language)
        fallback["status"] = "local_fallback"
        return fallback

    # 1. Explicação base (sempre disponível)
    fallback = _fallback_explanation(query, formation, language)

    # 2. Explicação com LLM
    return _explain_with_llm(sources, query, formation, language) or fallback


# ============================================================================
# Internal: LLM Calls
# ============================================================================


def _enrich_queries_with_llm(
    team_name: str,
    formation: str | None,
    base_queries: list[dict],
    language: str,
) -> dict:
    """Enriquece queries com variações semânticas usando LLM."""
    fallback = {
        "enriched": base_queries,
        "status": "local_fallback",
        "provider": "deterministic_rules",
    }

    payload = {
        "team_name": _clean_text(team_name),
        "formation": formation or "indefinida",
        "language": language,
        "base_queries": [
            {"label": q.get("label"), "category": q.get("category"), "query": q.get("query")}
            for q in base_queries
        ],
    }

    response = _call_llm_json(
        system=(
            "Você gera variações semânticas de queries de busca tática para futebol. "
            "Cada variação deve focar em um aspecto diferente: formação, padrões defensivos, "
            "saída de bola, transições ou análises comparativas. Mantenha queries concisas e "
            "em português natural."
        ),
        user=json.dumps(payload, ensure_ascii=False),
        fallback=fallback,
    )

    if response.get("status") == "llm_enriched":
        enriched_items = response.get("enriched_queries", [])
        cleaned = []
        for item in enriched_items or []:
            if isinstance(item, dict):
                cleaned.append({
                    "label": _clean_text(item.get("label")) or item.get("category", "Busca tática"),
                    "category": item.get("category", "team_form"),
                    "query": _clean_text(item.get("query")),
                    "rationale": _clean_text(item.get("rationale", "")),
                })
        if cleaned:
            response["enriched"] = cleaned
            return response

    return fallback


def _rerank_with_llm(
    sources: list[dict],
    query: str,
    formation: str | None,
    language: str,
) -> dict:
    """Re-ranking de top-K fontes com explicações via LLM."""
    fallback = {
        "ranked": [
            {"source": s, "score": s.get("score", 5.0), "explanation": "Fonte relevante para a busca."}
            for s in sources
        ],
        "summary": f"Encontrados {len(sources)} resultado(s) para '{query}'.",
        "status": "local_fallback",
    }

    compact_sources = [
        {
            "title": s.get("title"),
            "url": s.get("url"),
            "category": s.get("category"),
            "origin": s.get("origin"),
            "duration": s.get("duration"),
            "views": s.get("views"),
            "score": s.get("score"),
        }
        for s in sources
    ]

    payload = {
        "query": _clean_text(query),
        "formation": formation or "indefinida",
        "language": language,
        "sources": compact_sources,
    }

    response = _call_llm_json(
        system=(
            "Você classifica fontes de futebol por relevância tática. Para cada fonte, explique "
            "em 1-2 frases por que ela é útil para entender a formação ou tática solicitada. "
            "Marque score 0-10 refletindo relevância tática combinada com qualidade visual."
        ),
        user=json.dumps(payload, ensure_ascii=False),
        fallback=fallback,
    )

    if response.get("status") == "llm_enriched":
        ranked_items = response.get("ranked_sources", [])
        ranked_list = []
        for i, item in enumerate(ranked_items or []):
            if isinstance(item, dict) and i < len(sources):
                ranked_list.append({
                    "source": sources[i],
                    "score": float(item.get("score", sources[i].get("score", 5.0))),
                    "explanation": _clean_text(item.get("explanation", "")),
                })
        if ranked_list:
            response["ranked"] = ranked_list
            response["summary"] = _clean_text(response.get("summary", fallback["summary"]))
            return response

    return fallback


def _explain_with_llm(
    sources: list[dict],
    query: str,
    formation: str | None,
    language: str,
) -> dict:
    """Explicação natural dos resultados com LLM."""
    compact_sources = [
        {
            "title": s.get("title"),
            "category": s.get("category"),
            "views": s.get("views"),
            "score": s.get("score"),
        }
        for s in sources[:8]
    ]

    payload = {
        "query": _clean_text(query),
        "formation": formation or "indefinida",
        "language": language,
        "num_sources": len(sources),
        "top_sources": compact_sources,
    }

    response = _call_llm_json(
        system=(
            "Você explica resultados de busca tática em português natural e acessível. "
            "Identifique padrões, gaps, próximas ações. Seja conciso, específico e baseado "
            "nas evidências fornecidas."
        ),
        user=json.dumps(payload, ensure_ascii=False),
        fallback={},
    )

    if response.get("status") == "llm_enriched":
        return {
            "summary": _clean_text(response.get("summary", "")),
            "highlights": response.get("highlights", []) if isinstance(response.get("highlights"), list) else [],
            "next_actions": response.get("next_actions", []) if isinstance(response.get("next_actions"), list) else [],
            "caveats": response.get("caveats", []) if isinstance(response.get("caveats"), list) else [],
            "status": "llm_enriched",
            "provider": response.get("provider", "llm"),
        }

    return None


# ============================================================================
# Internal: Fallbacks e Determinístico
# ============================================================================


def _local_rank_with_scores(
    sources: list[dict],
    formation: str | None,
) -> list[dict]:
    """Ranking local usando scores já presentes nas fontes."""
    scored = []
    for source in sources:
        score = source.get("score", 5.0)

        # Bônus por categoria
        category = source.get("category", "")
        if category == "match_videos":
            score += 0.5
        elif category == "analysis_videos":
            score += 1.0

        # Bônus por formação
        if formation and formation.lower() in (source.get("title", "") or "").lower():
            score += 1.5

        scored.append({
            **source,
            "score": min(10.0, score),
        })

    return sorted(scored, key=lambda s: s.get("score", 0), reverse=True)


def _generate_formation_focused_queries(
    team_name: str,
    formation: str,
    language: str,
) -> list[dict]:
    """Queries focadas em formação específica (ex: 4-3-3)."""
    if not formation:
        return []

    formation_clean = formation.strip()
    queries = []

    formations_pt = {
        "4-3-3": "quatro-três-três",
        "4-2-3-1": "quatro-dois-três-um",
        "3-5-2": "três-cinco-dois",
        "5-3-2": "cinco-três-dois",
    }

    formation_name = formations_pt.get(formation_clean, formation_clean)
    team_clean = _clean_text(team_name)

    if language == "pt-BR":
        queries = [
            {
                "pattern": formation_clean,
                "queries": [
                    {
                        "label": f"Formação {formation_name}",
                        "category": "analysis_videos",
                        "query": f"{team_clean} formação {formation_name} como joga",
                    },
                    {
                        "label": f"Padrões defensivos {formation_name}",
                        "category": "analysis_videos",
                        "query": f"{team_clean} defesa {formation_name} bloqueio pressão alta",
                    },
                    {
                        "label": f"Saída de bola {formation_name}",
                        "category": "analysis_videos",
                        "query": f"{team_clean} saída de bola construção {formation_name}",
                    },
                ],
            }
        ]

    return queries


def _fallback_explanation(
    query: str,
    formation: str | None,
    language: str,
) -> dict:
    """Explicação determinística quando LLM não disponível."""
    query_clean = _clean_text(query)
    formation_info = f" na formação {formation}" if formation else ""

    if language == "pt-BR":
        return {
            "summary": (
                f"Foram encontradas fontes relacionadas à busca '{query_clean}'{formation_info}. "
                "Os resultados incluem vídeos de jogo, análises táticas e padrões de movimento."
            ),
            "highlights": [
                "Vídeos com resolução clara para rastreamento",
                "Análises táticas de formação e posicionamento",
                "Padrões de movimento e transição visíveis",
            ],
            "next_actions": [
                "Revisar os primeiros 3-5 resultados por relevância visual",
                "Validar duração e qualidade antes de enviar para análise de visão",
                "Cruzar padrões com a história recente do time",
            ],
            "caveats": [
                "Qualidade visual pode variar entre fontes",
                "Alguns vídeos podem ter cortes ou edições",
                "Disponibilidade depende de idioma e plataforma",
            ],
        }

    # English fallback
    return {
        "summary": (
            f"Found sources related to '{query_clean}'{formation_info}. "
            "Results include match videos, tactical analyses, and movement patterns."
        ),
        "highlights": [
            "Videos with clear resolution for tracking",
            "Tactical analyses of formation and positioning",
            "Visible movement and transition patterns",
        ],
        "next_actions": [
            "Review top 3-5 results for visual relevance",
            "Validate duration and quality before sending to vision analysis",
            "Cross-check patterns with team recent history",
        ],
        "caveats": [
            "Visual quality may vary between sources",
            "Some videos may have cuts or edits",
            "Availability depends on language and platform",
        ],
    }


# ============================================================================
# Export API
# ============================================================================

__all__ = [
    "enrich_tactical_search_queries",
    "rank_sources_with_llm",
    "explain_search_results",
]
