"""Testes para Tactical Search Hub (Fase 1: Fundação)."""
import json
import pytest
from datetime import datetime, timedelta, timezone

from backend.app.tactical_search.cache_layer import (
    cache_get, cache_set, cache_prune_expired, cache_invalidate_team,
    _normalize_query, _hash_query,
)
from backend.app.tactical_search.tactical_keywords import (
    extract_formation, parse_formation, detect_language, measure_tactical_relevance,
    get_tactical_focus, get_tactical_keywords,
)
from backend.app.tactical_search.video_validator import (
    parse_duration_to_seconds, VideoQualityScore, validate_youtube_video, validate_source,
)
from backend.app.tactical_search.tactical_ranking import TacticalRanker, score_source


# ============================================================================
# Test Cache Layer
# ============================================================================

class TestCacheLayer:
    def test_normalize_query(self):
        """Normaliza query com lowercase, trim e whitespace."""
        assert _normalize_query("  Flamengo  4-3-3  PRESSÃO  ") == "flamengo 4-3-3 pressão"
        assert _normalize_query("São Paulo 5-2-3") == "são paulo 5-2-3"

    def test_cache_roundtrip(self):
        """Cache set/get funciona."""
        query = "Flamengo 4-3-3 pressão alta"
        sources = [
            {"title": "Jogo 1", "url": "https://example.com/1", "tactical_score": 9.0}
        ]

        cache_set(query, sources)
        result = cache_get(query)

        assert result is not None
        assert len(result["sources"]) == 1
        assert result["sources"][0]["title"] == "Jogo 1"
        assert result["query_normalized"] == "flamengo 4-3-3 pressão alta"

    def test_cache_miss(self):
        """Cache miss retorna None."""
        result = cache_get("nonexistent-query-12345")
        assert result is None

    def test_query_hash_consistency(self):
        """Hash é consistente para query normalizada."""
        hash1 = _hash_query("flamengo 4-3-3")
        hash2 = _hash_query("flamengo 4-3-3")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256


# ============================================================================
# Test Tactical Keywords
# ============================================================================

class TestTacticalKeywords:
    def test_extract_formation(self):
        """Extrai formação de query."""
        assert extract_formation("Flamengo 4-3-3 pressão") == "4-3-3"
        assert extract_formation("time 5-2-3 construção") == "5-2-3"
        assert extract_formation("sem formação aqui") is None

    def test_parse_formation(self):
        """Parse formação em linhas defensivas/médias/ofensivas."""
        parsed = parse_formation("4-3-3")
        assert parsed["defense"] == 4
        assert parsed["midfield"] == 3
        assert parsed["attack"] == 3

        assert parse_formation("5-2-3") == {
            "defense": 5,
            "midfield": 2,
            "attack": 3,
            "original": "5-2-3",
        }

    def test_detect_language(self):
        """Detecta idioma de query."""
        assert detect_language("Flamengo 4-3-3 pressão alta") == "pt-br"
        assert detect_language("Barcelona córner balón") == "es"
        assert detect_language("Manchester United corner football") == "en"

    def test_measure_tactical_relevance(self):
        """Mede relevância tática por categoria."""
        text = "pressão alta compactação defesa marcação"
        scores = measure_tactical_relevance(text, "pt-br")

        assert "defensive" in scores
        assert scores["defensive"] > 0.5  # Muito conteúdo defensivo
        assert scores["offensive"] < 0.2  # Pouco ofensivo

    def test_get_tactical_focus(self):
        """Extrai focos táticos dominantes."""
        text = "análise pressão alta transição ofensiva"
        focus = get_tactical_focus(text, "pt-br")

        assert len(focus) > 0
        # Deve ter analysis e defensive como dominantes
        assert "analysis" in focus or "defensive" in focus


# ============================================================================
# Test Video Validator
# ============================================================================

class TestVideoValidator:
    def test_parse_duration_long_form(self):
        """Parse duração no formato "5h 23m 12s"."""
        assert parse_duration_to_seconds("5h 23m 12s") == 19392
        assert parse_duration_to_seconds("1h 0m 0s") == 3600
        assert parse_duration_to_seconds("0h 30m 45s") == 1845

    def test_parse_duration_medium(self):
        """Parse duração no formato "23m 12s"."""
        assert parse_duration_to_seconds("23m 12s") == 1392
        assert parse_duration_to_seconds("45m") == 2700

    def test_parse_duration_timestamp(self):
        """Parse duração em timestamp "HH:MM:SS" ou "MM:SS"."""
        assert parse_duration_to_seconds("5:23:12") == 19392
        assert parse_duration_to_seconds("23:12") == 1392
        assert parse_duration_to_seconds("1:30:00") == 5400

    def test_parse_duration_numeric(self):
        """Parse duração como número direto (segundos)."""
        assert parse_duration_to_seconds("5400") == 5400
        assert parse_duration_to_seconds("1800") == 1800

    def test_quality_score_duration(self):
        """Score de duração: shorts <3min → baixo; completos >40min → alto."""
        # Curto demais
        validator = VideoQualityScore(duration_seconds=120)
        score, reason = validator.calculate()
        assert score < 4.0, f"Shorts devem ter score baixo, got {score}"

        # Análise típica (10-40min)
        validator = VideoQualityScore(duration_seconds=1200)
        score, reason = validator.calculate()
        assert 6.5 <= score <= 9.0, f"Análise deve ter score médio-alto, got {score}"

        # Jogo completo (40-45min)
        validator = VideoQualityScore(duration_seconds=2700)
        score, reason = validator.calculate()
        assert score >= 7.0, f"Jogo completo deve ter score alto, got {score}"

    def test_quality_score_resolution(self):
        """Score de resolução: 1080p > 720p > 480p."""
        validator_1080 = VideoQualityScore(resolution="1080p")
        validator_720 = VideoQualityScore(resolution="720p")
        validator_480 = VideoQualityScore(resolution="480p")

        score_1080, _ = validator_1080.calculate()
        score_720, _ = validator_720.calculate()
        score_480, _ = validator_480.calculate()

        assert score_1080 > score_720 > score_480

    def test_validate_youtube_video(self):
        """Validação completa de vídeo YouTube."""
        video = {
            "id": "abc123",
            "title": "Flamengo vs Botafogo 1080p análise tática",
            "url": "https://youtube.com/watch?v=abc123",
            "channel": "Tático Sports",
            "duration": "45m 30s",
            "published": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            "views": "150K",
        }

        validated = validate_youtube_video(video)

        assert "quality_score" in validated
        assert "quality_reason" in validated
        assert "video_seconds" in validated
        assert validated["video_seconds"] == 2730
        assert validated["content_type"] == "analysis"  # Tem "análise" no título


# ============================================================================
# Test Tactical Ranking
# ============================================================================

class TestTacticalRanking:
    def test_ranker_weights_sum_to_one(self):
        """Pesos do ranker devem somar 1.0."""
        ranker = TacticalRanker(
            tactical_weight=0.40,
            quality_weight=0.25,
            authority_weight=0.20,
            category_weight=0.15,
        )
        total = (
            ranker.tactical_weight
            + ranker.quality_weight
            + ranker.authority_weight
            + ranker.category_weight
        )
        assert abs(total - 1.0) < 0.01

    def test_score_source_with_tactical_keywords(self):
        """Source com keywords táticos recebe score alto."""
        source = {
            "title": "Flamengo pressão alta 4-3-3",
            "summary": "Análise de como o Flamengo executa marcação e compactação defensiva",
            "category": "analysis_videos",
            "origin": "YouTube",
            "quality_score": 8.0,
        }

        score, reason = score_source(source, query="Flamengo 4-3-3 pressão alta")
        assert score >= 6.5, f"Keywords táticos devem dar score alto, got {score}"

    def test_score_source_category_weight(self):
        """match_videos > analysis_videos > team_form (com bom content)."""
        # Use sources com conteúdo tático para que diferenças apareçam
        base_source = {
            "title": "Análise tática pressão",
            "summary": "Descrição com keywords defensivos",
            "origin": "YouTube",
            "quality_score": 7.0,
        }

        match_video = {**base_source, "category": "match_videos"}
        analysis_video = {**base_source, "category": "analysis_videos"}
        team_form = {**base_source, "category": "team_form"}

        score_match, _ = score_source(match_video)
        score_analysis, _ = score_source(analysis_video)
        score_form, _ = score_source(team_form)

        # match_videos > analysis_videos (ambos > team_form)
        assert score_match > score_form, f"match {score_match} should > team_form {score_form}"
        assert score_analysis > score_form, f"analysis {score_analysis} should > team_form {score_form}"

    def test_rank_sources_ordered(self):
        """Rank ordena sources por score descending."""
        sources = [
            {
                "title": "Low score source",
                "summary": "Generic content",
                "category": "team_form",
                "quality_score": 3.0,
            },
            {
                "title": "Flamengo pressão alta análise tática",
                "summary": "Descrição com keywords táticos completa",
                "category": "analysis_videos",
                "quality_score": 8.0,
            },
        ]

        ranked = TacticalRanker().rank_sources(sources, query="Flamengo pressão")

        # Primeira deve ser a com keywords táticos
        assert "pressão" in ranked[0]["title"].lower()
        assert ranked[0]["tactical_score"] > ranked[1]["tactical_score"]


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    def test_query_normalization_consistency(self):
        """Mesma query normalizada retorna mesmo hash."""
        query1 = "  FLAMENGO  4-3-3  Pressão  "
        query2 = "flamengo 4-3-3 pressão"

        norm1 = _normalize_query(query1)
        norm2 = _normalize_query(query2)

        assert norm1 == norm2
        assert _hash_query(norm1) == _hash_query(norm2)

    def test_formation_extraction_and_parsing(self):
        """Extrai e parseia formação corretamente."""
        query = "Como o Flamengo joga 4-3-3 com pressão alta?"
        formation = extract_formation(query)
        parsed = parse_formation(formation)

        assert formation == "4-3-3"
        assert parsed["defense"] == 4
        assert parsed["midfield"] == 3
        assert parsed["attack"] == 3
