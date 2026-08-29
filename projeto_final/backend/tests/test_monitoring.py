"""Tests for monitoring and analytics module."""
import pytest
import time
from backend.app.tactical_search.monitoring import (
    QueryMetrics,
    TacticalSearchMonitor,
    get_monitor,
    reset_monitor,
    TimingContext,
)


class TestQueryMetrics:
    def test_query_metrics_creation(self):
        """Criar QueryMetrics com valores padrão."""
        metrics = QueryMetrics(team_name="Flamengo", query="Flamengo tactics")
        assert metrics.team_name == "Flamengo"
        assert metrics.query == "Flamengo tactics"
        assert metrics.duration_total == 0.0
        assert metrics.cache_hit is False
        assert metrics.status == "available"

    def test_query_metrics_with_timings(self):
        """QueryMetrics com tempos de operação."""
        metrics = QueryMetrics(
            team_name="Flamengo",
            query="Flamengo tactics",
            duration_total=1.5,
            duration_search=0.8,
            duration_llm=0.6,
            duration_recency=0.1,
        )
        assert metrics.duration_total == 1.5
        assert metrics.duration_search == 0.8
        assert metrics.duration_llm == 0.6

    def test_query_metrics_to_dict(self):
        """Converter QueryMetrics para dict."""
        metrics = QueryMetrics(
            team_name="Flamengo",
            query="Flamengo tactics",
            cache_hit=True,
            source_count=12,
        )
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert d["team_name"] == "Flamengo"
        assert d["cache_hit"] is True
        assert d["source_count"] == 12


class TestMonitorBasics:
    def teardown_method(self):
        reset_monitor()

    def test_monitor_singleton(self):
        """get_monitor() retorna singleton."""
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2

    def test_monitor_reset(self):
        """reset_monitor() limpa singleton."""
        m1 = get_monitor()
        reset_monitor()
        m2 = get_monitor()
        assert m1 is not m2

    def test_record_query(self):
        """Registrar métrica de query."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Flamengo",
            query="Flamengo tactics",
            duration_total=1.0,
        )
        monitor.record_query(metrics)
        assert len(monitor.metrics) == 1
        assert monitor.metrics[0].team_name == "Flamengo"

    def test_max_metrics_limit(self):
        """Limitar quantidade de métricas em memória."""
        monitor = TacticalSearchMonitor(max_metrics=10)
        for i in range(20):
            metrics = QueryMetrics(
                team_name=f"Team{i}",
                query=f"Query {i}",
            )
            monitor.record_query(metrics)
        assert len(monitor.metrics) == 10
        # Verify it kept the most recent ones
        assert monitor.metrics[0].team_name == "Team10"
        assert monitor.metrics[-1].team_name == "Team19"


class TestCacheStats:
    def teardown_method(self):
        reset_monitor()

    def test_cache_hit_recorded(self):
        """Cache hit é registrado."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Flamengo",
            query="Flamengo",
            cache_hit=True,
            cache_backend="redis",
        )
        monitor.record_query(metrics)
        stats = monitor.get_cache_stats()
        assert stats["redis"]["hits"] == 1
        assert stats["redis"]["misses"] == 0
        assert stats["redis"]["hit_rate_percent"] == 100.0

    def test_cache_miss_recorded(self):
        """Cache miss é registrado."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Flamengo",
            query="Flamengo",
            cache_hit=False,
            cache_backend="sqlite",
        )
        monitor.record_query(metrics)
        stats = monitor.get_cache_stats()
        assert stats["sqlite"]["hits"] == 0
        assert stats["sqlite"]["misses"] == 1
        assert stats["sqlite"]["hit_rate_percent"] == 0.0

    def test_cache_hit_rate_calculation(self):
        """Cálculo de hit rate com múltiplas queries."""
        monitor = get_monitor()
        for i in range(10):
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                cache_hit=(i % 2 == 0),  # 50% hit rate
                cache_backend="redis",
            )
            monitor.record_query(metrics)
        stats = monitor.get_cache_stats()
        assert stats["redis"]["hits"] == 5
        assert stats["redis"]["misses"] == 5
        assert stats["redis"]["hit_rate_percent"] == 50.0


class TestLatencyStats:
    def teardown_method(self):
        reset_monitor()

    def test_total_duration_stats(self):
        """Estatísticas de duração total."""
        monitor = get_monitor()
        for duration in [0.1, 0.2, 0.3]:
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                duration_total=duration,
            )
            monitor.record_query(metrics)

        stats = monitor.get_latency_stats()
        assert stats["total"]["min_ms"] == 100.0
        assert stats["total"]["max_ms"] == 300.0
        assert stats["total"]["avg_ms"] == 200.0
        assert stats["total"]["count"] == 3

    def test_component_timing_stats(self):
        """Estatísticas de tempo por componente."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Team",
            query="Query",
            duration_search=0.5,
            duration_llm=0.3,
            duration_recency=0.2,
        )
        monitor.record_query(metrics)

        stats = monitor.get_latency_stats()
        assert stats["search"]["count"] == 1
        assert stats["search"]["min_ms"] == 500.0
        assert stats["llm"]["count"] == 1
        assert stats["llm"]["min_ms"] == 300.0
        assert stats["recency"]["count"] == 1
        assert stats["recency"]["min_ms"] == 200.0

    def test_percentile_calculation(self):
        """Cálculo de percentis."""
        monitor = get_monitor()
        # Create 100 queries with varying durations
        for i in range(100):
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                duration_total=i * 0.01,  # 0.0 to 0.99 seconds
            )
            monitor.record_query(metrics)

        stats = monitor.get_latency_stats()
        assert "p50_ms" in stats["total"]
        assert "p95_ms" in stats["total"]
        assert "p99_ms" in stats["total"]
        # p50 should be around 50ms (middle value)
        assert 400 < stats["total"]["p50_ms"] < 600


class TestRankingStats:
    def teardown_method(self):
        reset_monitor()

    def test_ranking_score_stats(self):
        """Estatísticas de scores de ranking."""
        monitor = get_monitor()
        for score in [7.5, 8.0, 8.5, 9.0]:
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                top_score=score,
                avg_score=score - 0.5,
            )
            monitor.record_query(metrics)

        stats = monitor.get_ranking_stats()
        assert stats["top_score"]["min"] == 7.5
        assert stats["top_score"]["max"] == 9.0
        assert stats["top_score"]["avg"] == 8.25
        assert stats["top_score"]["count"] == 4

    def test_ranking_with_no_scores(self):
        """Ranking stats com zero scores."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Team",
            query="Query",
            top_score=0,
            avg_score=0,
        )
        monitor.record_query(metrics)

        stats = monitor.get_ranking_stats()
        assert stats["top_score"]["count"] == 0
        assert stats["avg_score"]["count"] == 0


class TestFeatureUsage:
    def teardown_method(self):
        reset_monitor()

    def test_llm_usage_tracking(self):
        """Rastreamento de uso de LLM."""
        monitor = get_monitor()
        for i in range(10):
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                llm_used=(i < 5),  # First 5 use LLM
            )
            monitor.record_query(metrics)

        usage = monitor.get_feature_usage()
        assert usage["total_queries"] == 10
        assert usage["llm_enrichment_count"] == 5
        assert usage["llm_enrichment_percent"] == 50.0

    def test_recency_usage_tracking(self):
        """Rastreamento de uso de recency scoring."""
        monitor = get_monitor()
        for i in range(10):
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                recency_used=(i < 7),  # First 7 use recency
            )
            monitor.record_query(metrics)

        usage = monitor.get_feature_usage()
        assert usage["recency_scoring_count"] == 7
        assert usage["recency_scoring_percent"] == 70.0

    def test_formation_detection_tracking(self):
        """Rastreamento de detecção de formação."""
        monitor = get_monitor()
        for i in range(10):
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                formation_detected=(i % 2 == 0),  # 50% have formation
            )
            monitor.record_query(metrics)

        usage = monitor.get_feature_usage()
        assert usage["formation_detection_count"] == 5
        assert usage["formation_detection_percent"] == 50.0


class TestErrorStats:
    def teardown_method(self):
        reset_monitor()

    def test_error_tracking(self):
        """Rastreamento de erros."""
        monitor = get_monitor()
        errors = ["LLM API timeout", "Cache backend unavailable", "LLM API timeout"]
        for error in errors:
            metrics = QueryMetrics(
                team_name="Team",
                query="Query",
                error=error,
            )
            monitor.record_query(metrics)

        stats = monitor.get_error_stats()
        assert stats["total_errors"] == 3
        assert stats["errors_by_type"]["LLM API timeout"] == 2
        assert stats["errors_by_type"]["Cache backend unavailable"] == 1

    def test_no_errors(self):
        """Sem erros registrados."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Team",
            query="Query",
            error=None,
        )
        monitor.record_query(metrics)

        stats = monitor.get_error_stats()
        assert stats["total_errors"] == 0
        assert len(stats["errors_by_type"]) == 0


class TestMonitorSummary:
    def teardown_method(self):
        reset_monitor()

    def test_summary_structure(self):
        """Estrutura do resumo monitoramento."""
        monitor = get_monitor()
        metrics = QueryMetrics(
            team_name="Flamengo",
            query="Flamengo tactics",
            cache_hit=True,
            cache_backend="redis",
            duration_total=1.0,
            top_score=8.5,
            llm_used=True,
        )
        monitor.record_query(metrics)

        summary = monitor.get_summary()
        assert summary["total_queries"] == 1
        assert "cache" in summary
        assert "latency" in summary
        assert "ranking" in summary
        assert "features" in summary
        assert "errors" in summary
        assert "timestamp" in summary

    def test_recent_queries(self):
        """Obter queries recentes."""
        monitor = get_monitor()
        for i in range(15):
            metrics = QueryMetrics(
                team_name=f"Team{i}",
                query=f"Query {i}",
            )
            monitor.record_query(metrics)

        recent = monitor.get_recent_queries(limit=5)
        assert len(recent) == 5
        assert recent[-1]["team_name"] == "Team14"
        assert recent[0]["team_name"] == "Team10"

    def test_recent_queries_empty(self):
        """Queries recentes sem histórico."""
        monitor = get_monitor()
        recent = monitor.get_recent_queries(limit=5)
        assert len(recent) == 0


class TestTimingContext:
    def test_timing_context_measurement(self):
        """Medir duração com TimingContext."""
        with TimingContext("test_operation") as ctx:
            time.sleep(0.05)
        assert ctx.duration >= 0.05
        assert ctx.duration < 0.1  # Should be fast

    def test_timing_context_zero_duration(self):
        """TimingContext com operação instantânea."""
        with TimingContext("instant") as ctx:
            pass
        assert ctx.duration >= 0.0
        assert ctx.duration < 0.01

    def test_timing_context_access_outside(self):
        """Acessar duração fora do contexto."""
        ctx = TimingContext("test")
        with ctx:
            time.sleep(0.02)
        # Duration should be accessible after exit
        assert ctx.duration > 0


class TestMonitorReset:
    def test_reset_clears_data(self):
        """reset_monitor() limpa todos os dados."""
        monitor = get_monitor()
        for i in range(5):
            metrics = QueryMetrics(
                team_name=f"Team{i}",
                query=f"Query {i}",
                cache_hit=True,
                cache_backend="redis",
                llm_used=True,
                error="Test error" if i == 0 else None,
            )
            monitor.record_query(metrics)

        assert len(monitor.metrics) == 5
        assert len(monitor.cache_stats) > 0
        assert len(monitor.error_counts) > 0

        reset_monitor()
        new_monitor = get_monitor()
        assert len(new_monitor.metrics) == 0
        assert len(new_monitor.cache_stats) == 0
        assert len(new_monitor.error_counts) == 0
