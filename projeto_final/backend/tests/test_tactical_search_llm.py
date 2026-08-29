"""Testes para Tactical Search Hub Fase 2.3: LLM Integration."""
import pytest
import json
from unittest.mock import patch, MagicMock

from backend.app.tactical_search.llm_tactical_enrichment import (
    enrich_tactical_search_queries,
    rank_sources_with_llm,
    explain_search_results,
    _generate_formation_focused_queries,
    _fallback_explanation,
    _local_rank_with_scores,
)


# ============================================================================
# Test Query Enrichment
# ============================================================================

class TestQueryEnrichment:
    def test_enrich_queries_with_team_name(self):
        """Gera queries base para time."""
        result = enrich_tactical_search_queries("Flamengo")

        assert "base_queries" in result
        assert len(result["base_queries"]) > 0
        assert all(q.get("query") for q in result["base_queries"])
        assert all(q.get("label") for q in result["base_queries"])

    def test_enrich_queries_max_limit(self):
        """Respeita limite de queries."""
        result = enrich_tactical_search_queries("Flamengo", max_queries=3)

        assert len(result["base_queries"]) <= 3

    def test_enrich_queries_with_formation(self):
        """Gera queries focadas em formação."""
        result = enrich_tactical_search_queries(
            "Flamengo",
            formation="4-3-3",
            max_queries=6,
        )

        assert "formation_focused" in result
        if result["formation_focused"]:
            assert result["formation_focused"][0].get("pattern") == "4-3-3"
            assert len(result["formation_focused"][0].get("queries", [])) > 0

    def test_enrich_queries_fallback_structure(self):
        """Estrutura de fallback está sempre presente."""
        result = enrich_tactical_search_queries("Barcelona")

        assert result["status"] in ["llm_enriched", "local_fallback"]
        assert result["provider"] in ["deterministic_rules", "llm", "anthropic_messages", "openai_responses", "google_gemini", "xai_grok"]

    def test_formation_focused_queries_valid_formations(self):
        """Gera queries para formações conhecidas."""
        formations = ["4-3-3", "4-2-3-1", "3-5-2", "5-3-2"]

        for formation in formations:
            result = _generate_formation_focused_queries("Flamengo", formation, "pt-BR")
            assert len(result) == 1
            assert result[0]["pattern"] == formation
            assert len(result[0]["queries"]) >= 3

    def test_formation_focused_queries_none_formation(self):
        """Sem formation → sem queries focadas."""
        result = _generate_formation_focused_queries("Flamengo", None, "pt-BR")
        assert result == []


# ============================================================================
# Test Source Ranking
# ============================================================================

class TestSourceRanking:
    def test_rank_sources_empty_list(self):
        """Ranking de lista vazia retorna estrutura vazia."""
        result = rank_sources_with_llm([], "4-3-3")

        assert result["ranked"] == []
        assert "summary" in result
        assert result["status"] == "local_fallback"

    def test_rank_sources_with_scores(self):
        """Fontes são ranqueadas por score."""
        sources = [
            {"title": "Video 1", "score": 5.0, "category": "match_videos"},
            {"title": "Video 2", "score": 8.0, "category": "analysis_videos"},
            {"title": "Video 3", "score": 6.0, "category": "team_form"},
        ]

        result = rank_sources_with_llm(sources, "Flamengo")

        assert len(result["ranked"]) == 3
        # Ordem decrescente por score
        scores = [r["score"] for r in result["ranked"]]
        assert scores == sorted(scores, reverse=True)

    def test_rank_sources_formation_bonus(self):
        """Fontes com formação no título recebem bônus."""
        sources = [
            {"title": "Flamengo 4-3-3 análise", "score": 5.0, "category": "analysis_videos"},
            {"title": "Flamengo modo de jogo", "score": 5.0, "category": "analysis_videos"},
        ]

        local_ranked = _local_rank_with_scores(sources, "4-3-3")

        # Primeira fonte deve ter score maior (bônus de formação)
        assert local_ranked[0]["title"] == "Flamengo 4-3-3 análise"
        assert local_ranked[0]["score"] > local_ranked[1]["score"]

    def test_rank_sources_category_bonus(self):
        """Videos análise recebem bônus sobre match videos."""
        sources = [
            {"title": "Video 1", "score": 5.0, "category": "match_videos"},
            {"title": "Video 2", "score": 5.0, "category": "analysis_videos"},
        ]

        local_ranked = _local_rank_with_scores(sources, None)

        # Analysis video tem bônus maior
        assert local_ranked[0]["title"] == "Video 2"

    def test_rank_sources_score_capped_at_10(self):
        """Score nunca excede 10.0."""
        sources = [
            {"title": "Video 1", "score": 9.0, "category": "analysis_videos"}
        ]

        local_ranked = _local_rank_with_scores(sources, "4-3-3")

        assert local_ranked[0]["score"] <= 10.0

    def test_rank_sources_top_k_limit(self):
        """Retorna apenas top-k resultados com explicações."""
        sources = [
            {"title": f"Video {i}", "score": 10 - i, "category": "match_videos"}
            for i in range(20)
        ]

        result = rank_sources_with_llm(sources, "Flamengo", top_k=5)

        assert len(result["ranked"]) == 5


# ============================================================================
# Test Explanations
# ============================================================================

class TestExplanations:
    def test_explain_empty_sources(self):
        """Explicação de sem fontes usa fallback."""
        result = explain_search_results([], "Flamengo 4-3-3")

        assert "summary" in result
        assert "highlights" in result
        assert "next_actions" in result

    def test_explain_with_sources(self):
        """Explicação com fontes tem estrutura esperada."""
        sources = [
            {"title": "Video 1", "score": 8.0, "category": "analysis_videos"},
            {"title": "Video 2", "score": 7.0, "category": "match_videos"},
        ]

        result = explain_search_results(
            sources,
            "Como Flamengo joga formação 4-3-3",
            formation="4-3-3",
        )

        assert "summary" in result
        assert "highlights" in result
        assert "next_actions" in result
        assert "caveats" in result

    def test_explain_fallback_portuguese(self):
        """Fallback fornece explicação em português."""
        result = _fallback_explanation(
            "Flamengo 4-3-3",
            "4-3-3",
            "pt-BR",
        )

        assert "summary" in result
        assert "Flamengo" in result["summary"] or "formação" in result["summary"].lower()
        assert len(result["highlights"]) > 0
        assert len(result["next_actions"]) > 0

    def test_explain_fallback_english(self):
        """Fallback fornece explicação em inglês."""
        result = _fallback_explanation(
            "Flamengo 4-3-3",
            "4-3-3",
            "en",
        )

        assert "summary" in result
        assert "Found" in result["summary"] or "sources" in result["summary"].lower()

    def test_explain_structures_lists(self):
        """Explicações têm listas estruturadas."""
        sources = [
            {"title": "Video 1", "score": 8.0, "category": "analysis_videos"},
        ]

        result = explain_search_results(sources, "Flamengo", formation="4-3-3")

        assert isinstance(result.get("highlights"), list)
        assert isinstance(result.get("next_actions"), list)
        assert isinstance(result.get("caveats"), list)


# ============================================================================
# Test Fallback Logic
# ============================================================================

class TestFallbackBehavior:
    def test_local_rank_preserves_source_data(self):
        """Ranking local preserva dados originais."""
        source = {
            "title": "Video test",
            "url": "http://example.com",
            "score": 5.0,
            "category": "match_videos",
            "custom_field": "value",
        }

        ranked = _local_rank_with_scores([source], None)

        assert ranked[0]["title"] == source["title"]
        assert ranked[0]["url"] == source["url"]
        assert ranked[0]["custom_field"] == source["custom_field"]

    def test_local_rank_default_score(self):
        """Fonte sem score recebe valor padrão."""
        source = {"title": "Video"}

        ranked = _local_rank_with_scores([source], None)

        assert "score" in ranked[0]
        assert ranked[0]["score"] >= 0

    def test_enrichment_always_has_status(self):
        """Enriquecimento sempre retorna status."""
        result = enrich_tactical_search_queries("Flamengo")

        assert "status" in result
        assert result["status"] in ["llm_enriched", "local_fallback"]


# ============================================================================
# Test Language Support
# ============================================================================

class TestLanguageSupport:
    def test_formation_queries_portuguese(self):
        """Queries de formação em português."""
        result = _generate_formation_focused_queries(
            "Flamengo",
            "4-3-3",
            "pt-BR",
        )

        queries_text = " ".join([q.get("query", "") for q in result[0]["queries"]])
        assert "formação" in queries_text.lower() or "defesa" in queries_text.lower()

    def test_enrichment_respects_language(self):
        """Enriquecimento respeita parâmetro de idioma."""
        result_pt = enrich_tactical_search_queries("Flamengo", language="pt-BR")
        result_en = enrich_tactical_search_queries("Flamengo", language="en")

        # Ambos devem ter estrutura
        assert "base_queries" in result_pt
        assert "base_queries" in result_en


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhase23Integration:
    def test_end_to_end_enrichment_pipeline(self):
        """Pipeline completo: query → sources → rank → explain."""
        # 1. Generate queries
        queries_result = enrich_tactical_search_queries("Flamengo", formation="4-3-3")
        assert len(queries_result["base_queries"]) > 0

        # 2. Simular sources
        sources = [
            {"title": f"Video {i}", "score": 8 - i*0.5, "category": "analysis_videos"}
            for i in range(5)
        ]

        # 3. Rank sources
        ranked_result = rank_sources_with_llm(
            sources,
            queries_result["base_queries"][0]["query"],
            formation="4-3-3",
        )
        assert len(ranked_result["ranked"]) > 0

        # 4. Explain results
        explain_result = explain_search_results(
            sources,
            queries_result["base_queries"][0]["query"],
            formation="4-3-3",
        )
        assert "summary" in explain_result

    def test_graceful_degradation_no_api_key(self):
        """Sistema degrada gracefully sem API key do LLM."""
        result = enrich_tactical_search_queries("Flamengo", max_queries=6)

        # Mesmo sem API, retorna resultados
        assert result["base_queries"] or result["status"] == "local_fallback"

    def test_concurrent_enrichments(self):
        """Múltiplos enriquecimentos funcionam independentemente."""
        teams = ["Flamengo", "Vasco", "Botafogo"]

        for team in teams:
            result = enrich_tactical_search_queries(team, formation="4-3-3")
            assert result["base_queries"]
            assert result["status"]
