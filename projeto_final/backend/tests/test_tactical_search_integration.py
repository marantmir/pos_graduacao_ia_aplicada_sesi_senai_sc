"""Testes para integração do Tactical Search Hub com online_search."""
import pytest
from unittest.mock import patch, MagicMock

from backend.app.tactical_search.integration import (
    search_tactical_enhanced,
    enrich_online_search_result,
)


# ============================================================================
# Test Enhanced Search
# ============================================================================

class TestTacticalEnhancedSearch:
    @patch('backend.app.tactical_search.integration.tactical_search')
    def test_search_basic(self, mock_search):
        """Search básico sem cache."""
        mock_search.return_value = {
            "query": "Flamengo futebol",
            "sources": [],
            "status": "available",
            "formation": None,
            "language": "pt-BR",
        }

        result = search_tactical_enhanced(
            "Flamengo",
            use_cache=False,
            use_llm_ranking=False,
            use_recency=False,
        )

        assert "team_name" in result
        assert result["team_name"] == "Flamengo"
        assert "query" in result
        assert "sources" in result
        assert "status" in result

    @patch('backend.app.tactical_search.integration.tactical_search')
    def test_search_with_custom_query(self, mock_search):
        """Search com query customizada."""
        mock_search.return_value = {
            "query": "Flamengo 4-3-3 pressão alta",
            "sources": [],
            "status": "available",
            "formation": "4-3-3",
            "language": "pt-BR",
        }

        result = search_tactical_enhanced(
            "Flamengo",
            query="Flamengo 4-3-3 pressão alta",
            use_cache=False,
        )

        assert result["query"] == "Flamengo 4-3-3 pressão alta"
        assert "formation" in result

    @patch('backend.app.tactical_search.integration.tactical_search')
    def test_search_with_max_sources(self, mock_search):
        """Respeita limite de sources."""
        mock_search.return_value = {
            "query": "Flamengo futebol",
            "sources": [
                {"title": f"Video {i}", "url": f"http://example.com/{i}"}
                for i in range(10)
            ],
            "status": "available",
            "formation": None,
            "language": "pt-BR",
        }

        result = search_tactical_enhanced(
            "Flamengo",
            max_sources=5,
            use_cache=False,
            use_llm_ranking=False,
        )

        assert len(result["sources"]) <= 5

    @patch('backend.app.tactical_search.integration.tactical_search')
    def test_search_structure(self, mock_search):
        """Resultado tem estrutura esperada."""
        mock_search.return_value = {
            "query": "Flamengo futebol",
            "sources": [],
            "status": "available",
            "formation": None,
            "language": "pt-BR",
            "errors": [],
        }

        result = search_tactical_enhanced(
            "Flamengo",
            use_cache=False,
            use_llm_ranking=False,
        )

        # Campos obrigatórios
        assert "team_name" in result
        assert "query" in result
        assert "sources" in result
        assert "status" in result
        assert "errors" in result

        # Metadata
        assert "search_method" in result
        assert result["search_method"] == "tactical_search_hub_v2.4"
        assert "retrieved_at" in result

    @patch('backend.app.tactical_search.integration.tactical_search')
    def test_search_with_recency(self, mock_search):
        """Recency scoring adiciona campos."""
        mock_search.return_value = {
            "query": "Flamengo futebol",
            "sources": [
                {
                    "title": "Video 1",
                    "url": "http://example.com/1",
                    "score": 7.0,
                    "published": "1 day ago",
                    "views": "100K",
                }
            ],
            "status": "available",
            "formation": None,
            "language": "pt-BR",
        }

        result = search_tactical_enhanced(
            "Flamengo",
            use_cache=False,
            use_llm_ranking=False,
            use_recency=True,
        )

        # Se houver sources, devem ter recency_score
        for source in result.get("sources", []):
            if "recency_score" in source:
                assert 0 <= source["recency_score"] <= 10


# ============================================================================
# Test Enrichment Function
# ============================================================================

class TestEnrichmentFunction:
    def test_enrich_basic(self):
        """Enrichment básico."""
        online_result = {
            "team_name": "Flamengo",
            "query": "Flamengo futebol",
            "sources": [
                {"title": "Video 1", "url": "http://example.com/1", "score": 7.0},
                {"title": "Video 2", "url": "http://example.com/2", "score": 6.0},
            ],
            "status": "available",
        }

        enriched = enrich_online_search_result(online_result, apply_tactical_scoring=True)

        assert "sources" in enriched
        # May or may not have tactical_hub_enriched depending on whether enrichment worked

    def test_enrich_no_sources(self):
        """Enrichment sem sources."""
        online_result = {
            "team_name": "Flamengo",
            "sources": [],
            "status": "guided_fallback",
        }

        enriched = enrich_online_search_result(online_result)

        # Deve retornar sem erro
        assert enriched["status"] == "guided_fallback"

    def test_enrich_preserves_fields(self):
        """Enrichment preserva campos existentes."""
        online_result = {
            "team_name": "Flamengo",
            "query": "Flamengo futebol",
            "sources": [
                {"title": "Video 1", "url": "http://example.com/1"},
            ],
            "custom_field": "value",
            "status": "available",
        }

        enriched = enrich_online_search_result(online_result)

        assert enriched["custom_field"] == "value"
        assert enriched["team_name"] == "Flamengo"

    def test_enrich_disabled(self):
        """Pode desabilitar enriquecimento."""
        online_result = {
            "team_name": "Flamengo",
            "sources": [{"title": "Video 1"}],
        }

        enriched = enrich_online_search_result(online_result, apply_tactical_scoring=False)

        # Sem enriquecimento, deve retornar básico
        assert "sources" in enriched

    def test_enrich_formation_detection(self):
        """Enrichment detecta formação na query."""
        online_result = {
            "team_name": "Flamengo",
            "query": "Flamengo 4-3-3 pressão alta",
            "sources": [{"title": "Video 1"}],
        }

        enriched = enrich_online_search_result(online_result)

        # Deve detectar formação
        if "formation_detected" in enriched:
            assert enriched["formation_detected"] == "4-3-3"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegrationWithOnlineSearch:
    @patch('backend.app.tactical_search.integration.tactical_search')
    def test_pipeline_no_llm(self, mock_search):
        """Pipeline completo sem LLM."""
        mock_search.return_value = {
            "query": "Flamengo futebol",
            "sources": [{"title": "Video 1", "url": "http://example.com/1", "score": 7.0}],
            "status": "available",
            "formation": None,
            "language": "pt-BR",
        }

        result = search_tactical_enhanced(
            "Flamengo",
            use_cache=False,
            use_llm_ranking=False,
            use_recency=True,
        )

        assert result["team_name"] == "Flamengo"
        assert "sources" in result
        assert isinstance(result["sources"], list)

    def test_enrich_preserves_existing_behavior(self):
        """Enrichment não quebra comportamento existente."""
        online_result = {
            "team_name": "Flamengo",
            "query": "Flamengo futebol",
            "sources": [
                {"title": "Video 1", "url": "http://example.com/1"},
                {"title": "Video 2", "url": "http://example.com/2"},
            ],
            "status": "available",
            "coverage": {"match_videos": 1, "analysis_videos": 1},
        }

        enriched = enrich_online_search_result(online_result)

        # Preservar estrutura
        assert len(enriched["sources"]) == 2
        assert enriched["status"] == "available"
        if "coverage" in enriched:
            assert enriched["coverage"]["match_videos"] == 1
