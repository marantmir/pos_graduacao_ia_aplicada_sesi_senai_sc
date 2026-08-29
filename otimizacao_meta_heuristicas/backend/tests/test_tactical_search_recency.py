"""Testes para Tactical Search Hub Fase 2.4: Trending + Recency Scoring."""
import pytest
from datetime import datetime, timezone, timedelta

from backend.app.tactical_search.recency_scoring import (
    RecencyScorer,
    apply_recency_bonus,
    boost_tactical_score_with_recency,
)


# ============================================================================
# Test Parse Functions
# ============================================================================

class TestViewCountParsing:
    def test_parse_view_count_millions(self):
        """Parse views em milhões (1.2M)."""
        scorer = RecencyScorer()
        assert scorer._parse_view_count("1.2M") == 1_200_000
        assert scorer._parse_view_count("5M") == 5_000_000
        assert scorer._parse_view_count("0.5M") == 500_000

    def test_parse_view_count_thousands(self):
        """Parse views em milhares (500K)."""
        scorer = RecencyScorer()
        assert scorer._parse_view_count("500K") == 500_000
        assert scorer._parse_view_count("1.5K") == 1_500
        assert scorer._parse_view_count("100K") == 100_000

    def test_parse_view_count_numeric(self):
        """Parse views numéricos."""
        scorer = RecencyScorer()
        assert scorer._parse_view_count("1234567") == 1_234_567
        assert scorer._parse_view_count(1_234_567) == 1_234_567
        assert scorer._parse_view_count("1,234,567") == 1_234_567

    def test_parse_view_count_with_suffix(self):
        """Ignora 'views' e case-insensitive."""
        scorer = RecencyScorer()
        assert scorer._parse_view_count("1M views") == 1_000_000
        assert scorer._parse_view_count("500k VIEWS") == 500_000
        assert scorer._parse_view_count("1000 views") == 1000

    def test_parse_view_count_invalid(self):
        """Parse inválido retorna None."""
        scorer = RecencyScorer()
        assert scorer._parse_view_count(None) is None
        assert scorer._parse_view_count("") is None
        assert scorer._parse_view_count("abc") is None

    def test_parse_view_count_zero(self):
        """Parse zero views."""
        scorer = RecencyScorer()
        assert scorer._parse_view_count("0") == 0
        assert scorer._parse_view_count(0) == 0


class TestPublishedDateParsing:
    def test_parse_iso_format(self):
        """Parse ISO format dates."""
        scorer = RecencyScorer()
        result = scorer._parse_published_date("2024-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2024

    def test_parse_relative_days(self):
        """Parse 'X days ago' format."""
        scorer = RecencyScorer()
        result = scorer._parse_published_date("1 day ago")
        assert result is not None
        now = datetime.now(timezone.utc)
        delta = (now - result).days
        assert delta in [0, 1]  # Aproximado

    def test_parse_relative_weeks(self):
        """Parse 'X weeks ago' format."""
        scorer = RecencyScorer()
        result = scorer._parse_published_date("2 weeks ago")
        assert result is not None

    def test_parse_relative_months(self):
        """Parse 'X months ago' format."""
        scorer = RecencyScorer()
        result = scorer._parse_published_date("3 months ago")
        assert result is not None

    def test_parse_numeric_days(self):
        """Parse numeric days ago."""
        scorer = RecencyScorer()
        result = scorer._parse_published_date("7")
        assert result is not None
        now = datetime.now(timezone.utc)
        delta = (now - result).days
        assert delta in [6, 7, 8]  # Aproximado

    def test_parse_invalid_date(self):
        """Parse inválido retorna None."""
        scorer = RecencyScorer()
        assert scorer._parse_published_date(None) is None
        assert scorer._parse_published_date("") is None
        assert scorer._parse_published_date("invalid") is None


# ============================================================================
# Test Recency Scoring
# ============================================================================

class TestRecencyScoring:
    def test_score_recency_today(self):
        """Video de hoje tem score 10.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        score = scorer._score_recency(now_iso, now)
        assert score == 10.0

    def test_score_recency_one_week_ago(self):
        """Video de semana passada tem score entre 6-8."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)

        score = scorer._score_recency(one_week_ago.isoformat(), now)
        assert 6.0 <= score <= 8.0

    def test_score_recency_one_month_ago(self):
        """Video de mês passado tem score entre 4-6."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        one_month_ago = now - timedelta(days=30)

        score = scorer._score_recency(one_month_ago.isoformat(), now)
        assert 4.0 <= score <= 6.5

    def test_score_recency_old_video(self):
        """Video muito antigo tem score ≤ 2.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=365)

        score = scorer._score_recency(old.isoformat(), now)
        assert score <= 2.0

    def test_score_recency_unknown_date(self):
        """Data desconhecida retorna neutral 5.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)

        score = scorer._score_recency(None, now)
        assert score == 5.0


class TestViewTrendScoring:
    def test_score_view_trend_high_velocity(self):
        """Video com 1000+ views/dia tem score 10.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)

        score = scorer._score_view_trend("1000000", one_day_ago.isoformat(), now)
        assert score == 10.0

    def test_score_view_trend_medium_velocity(self):
        """Video com 100-500 views/dia tem score 6.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # 3000 views em 30 dias = 100 views/dia
        score = scorer._score_view_trend("3000", thirty_days_ago.isoformat(), now)
        assert score == 6.0

    def test_score_view_trend_low_velocity(self):
        """Video com <10 views/dia tem score 2.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        one_year_ago = now - timedelta(days=365)

        # 100 views em 1 ano = ~0.27 views/dia
        score = scorer._score_view_trend("100", one_year_ago.isoformat(), now)
        assert score == 2.0

    def test_score_view_trend_missing_data(self):
        """Dados faltando retorna neutral 5.0."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)

        score = scorer._score_view_trend(None, None, now)
        assert score == 5.0


class TestAbsoluteViewsScoring:
    def test_score_absolute_1_million(self):
        """1M+ views: score 10.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("1.2M") == 10.0
        assert scorer._score_absolute_views("5000000") == 10.0

    def test_score_absolute_500k(self):
        """500K-1M views: score 9.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("500K") == 9.0
        assert scorer._score_absolute_views("750K") == 9.0

    def test_score_absolute_100k(self):
        """100K-500K views: score 8.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("100K") == 8.0
        assert scorer._score_absolute_views("250K") == 8.0

    def test_score_absolute_50k(self):
        """50K-100K views: score 6.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("50K") == 6.0

    def test_score_absolute_10k(self):
        """10K-50K views: score 4.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("25K") == 4.0

    def test_score_absolute_1k(self):
        """1K-10K views: score 2.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("5K") == 2.0

    def test_score_absolute_low(self):
        """<1K views: score 1.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views("100") == 1.0

    def test_score_absolute_missing(self):
        """Views faltando: score neutral 5.0."""
        scorer = RecencyScorer()
        assert scorer._score_absolute_views(None) == 5.0


class TestAuthorityScoring:
    def test_score_authority_verified_channel(self):
        """Canal verificado: +2.0 bonus."""
        scorer = RecencyScorer()
        source = {"channel_verified": True}
        score = scorer._score_authority(source)
        assert score > 5.0  # Base 5.0 + 2.0

    def test_score_authority_official_source(self):
        """Fonte oficial (Wikipedia): +3.0 bonus."""
        scorer = RecencyScorer()
        source = {"origin": "Wikipedia"}
        score = scorer._score_authority(source)
        assert score > 5.0

    def test_score_authority_thesportsdb(self):
        """TheSportsDB: +3.0 bonus."""
        scorer = RecencyScorer()
        source = {"origin": "TheSportsDB"}
        score = scorer._score_authority(source)
        assert score > 5.0

    def test_score_authority_high_subscribers(self):
        """Canal com 100K+ subscribers: +1.0 bonus."""
        scorer = RecencyScorer()
        source = {"channel_subscribers": "500K"}
        score = scorer._score_authority(source)
        assert score > 5.0

    def test_score_authority_combined(self):
        """Múltiplos bonuses acumulam."""
        scorer = RecencyScorer()
        source = {
            "channel_verified": True,
            "origin": "Wikipedia",
            "channel_subscribers": "100K",
        }
        score = scorer._score_authority(source)
        assert score >= 10.0  # 5.0 + 2.0 + 3.0 + 1.0 = 11.0, capped at 10.0

    def test_score_authority_capped_at_10(self):
        """Score nunca excede 10.0."""
        scorer = RecencyScorer()
        source = {
            "channel_verified": True,
            "origin": "Wikipedia Official",
            "channel_subscribers": "1M",
        }
        score = scorer._score_authority(source)
        assert score <= 10.0


# ============================================================================
# Test Combined Scoring
# ============================================================================

class TestCombinedScoring:
    def test_score_recent_viral_video(self):
        """Video recente com muitas views tem score alto."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        source = {
            "published": yesterday.isoformat(),
            "views": "500K",
            "channel_verified": True,
            "origin": "Official Channel",
        }

        score = scorer.score(source, now)
        assert score > 8.0

    def test_score_old_video(self):
        """Video antigo com poucas views tem score baixo."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)
        one_year_ago = now - timedelta(days=365)

        source = {
            "published": one_year_ago.isoformat(),
            "views": "100",
            "channel_verified": False,
        }

        score = scorer.score(source, now)
        assert score < 4.0

    def test_score_range_0_to_10(self):
        """Score está sempre entre 0-10."""
        scorer = RecencyScorer()
        sources = [
            {"published": "2024-01-01T00:00:00Z", "views": "10M"},
            {"published": "1990-01-01T00:00:00Z", "views": "10"},
            {},
        ]

        for source in sources:
            score = scorer.score(source)
            assert 0.0 <= score <= 10.0


# ============================================================================
# Test Utility Functions
# ============================================================================

class TestUtilityFunctions:
    def test_apply_recency_bonus(self):
        """Apply bonus retorna source enriquecida."""
        source = {
            "title": "Video test",
            "published": "1 day ago",
            "views": "100K",
        }

        result = apply_recency_bonus(source)

        assert "recency_score" in result
        assert "recency_components" in result
        assert result["title"] == source["title"]
        assert 0 <= result["recency_score"] <= 10

    def test_boost_tactical_score(self):
        """Boost combina scores tático e recência."""
        source = {
            "title": "Video test",
            "published": "2 days ago",
            "views": "500K",
        }
        tactical_score = 7.5

        result = boost_tactical_score_with_recency(source, tactical_score, recency_weight=0.2)

        assert "tactical_score" in result
        assert "recency_score" in result
        assert "combined_score" in result
        assert result["tactical_score"] == 7.5
        assert 0 <= result["combined_score"] <= 10

    def test_boost_weight_distribution(self):
        """Boost respeita distribuição de pesos."""
        source = {
            "published": "10 years ago",  # Score recência: 1.0
            "views": "10",  # Sem views bonus
        }
        tactical_score = 10.0  # Score tático perfeito

        # Com 20% peso recência: (0.8 * 10.0) + (0.2 * recency_score)
        # Recency score includes multiple components, so it won't be exactly 1.0
        result = boost_tactical_score_with_recency(
            source,
            tactical_score,
            recency_weight=0.2,
        )

        # Combined score should be less than pure tactical score due to recency weight
        assert result["combined_score"] < tactical_score
        assert result["combined_score"] >= 6.0  # At least somewhat weighted toward tactical


# ============================================================================
# Integration Tests
# ============================================================================

class TestRecencyIntegration:
    def test_end_to_end_recency_scoring(self):
        """Scoring completo de múltiplas fontes."""
        scorer = RecencyScorer()
        now = datetime.now(timezone.utc)

        sources = [
            {
                "title": "Recent viral video",
                "published": (now - timedelta(days=1)).isoformat(),
                "views": "1.2M",
                "channel_verified": True,
            },
            {
                "title": "Popular classic",
                "published": (now - timedelta(days=180)).isoformat(),
                "views": "500K",
            },
            {
                "title": "Old obscure video",
                "published": (now - timedelta(days=365)).isoformat(),
                "views": "100",
            },
        ]

        scores = [scorer.score(s, now) for s in sources]

        # Ordem decrescente
        assert scores[0] > scores[1] > scores[2]

    def test_weight_customization(self):
        """Pesos customizados afetam scoring."""
        now = datetime.now(timezone.utc)
        source = {
            "published": (now - timedelta(days=90)).isoformat(),
            "views": "1M",
        }

        # Scorer com mais peso em views
        scorer_high_views = RecencyScorer(weights={"absolute_views": 0.7, "recency": 0.3})
        score_high = scorer_high_views.score(source, now)

        # Scorer com mais peso em recência
        scorer_high_recency = RecencyScorer(weights={"recency": 0.7, "absolute_views": 0.3})
        score_low = scorer_high_recency.score(source, now)

        # Com muito peso em views, o score deve ser maior
        assert score_high > score_low
