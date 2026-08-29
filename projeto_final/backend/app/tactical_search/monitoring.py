"""Monitoring and analytics for Tactical Search Hub v2.4

Tracks:
- Cache performance (hit rate, miss rate, invalidation events)
- Query latency (search, LLM enrichment, ranking, total)
- Ranking quality (score distribution, top-k improvements)
- Feature usage (LLM enabled, recency enabled, A/B test assignment)
- Error rates and types
"""
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Any
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Metrics for a single tactical search query."""
    team_name: str
    query: str
    formation: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Timing (seconds)
    duration_total: float = 0.0
    duration_cache_check: float = 0.0
    duration_search: float = 0.0
    duration_ranking: float = 0.0
    duration_llm: float = 0.0
    duration_recency: float = 0.0

    # Cache
    cache_hit: bool = False
    cache_backend: str = "none"

    # Results
    source_count: int = 0
    top_score: float = 0.0
    avg_score: float = 0.0

    # Features
    llm_enabled: bool = False
    llm_used: bool = False
    recency_enabled: bool = False
    recency_used: bool = False
    formation_detected: bool = False

    # Status
    status: str = "available"
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class TacticalSearchMonitor:
    """Singleton monitor for Tactical Search Hub metrics."""

    def __init__(self, max_metrics: int = 1000):
        self.metrics: list[QueryMetrics] = []
        self.max_metrics = max_metrics
        self.cache_stats = defaultdict(lambda: {"hits": 0, "misses": 0})
        self.error_counts = defaultdict(int)
        self.feature_usage = defaultdict(int)

    def record_query(self, metrics: QueryMetrics) -> None:
        """Record metrics from a tactical search query."""
        self.metrics.append(metrics)

        # Keep only recent metrics to avoid memory bloat
        if len(self.metrics) > self.max_metrics:
            self.metrics = self.metrics[-self.max_metrics:]

        # Update cache stats
        backend = metrics.cache_backend or "none"
        if metrics.cache_hit:
            self.cache_stats[backend]["hits"] += 1
        else:
            self.cache_stats[backend]["misses"] += 1

        # Track errors
        if metrics.error:
            self.error_counts[metrics.error] += 1

        # Track feature usage
        if metrics.llm_used:
            self.feature_usage["llm_enrichment"] += 1
        if metrics.recency_used:
            self.feature_usage["recency_scoring"] += 1
        if metrics.formation_detected:
            self.feature_usage["formation_detection"] += 1

    def get_cache_stats(self) -> dict:
        """Get cache hit/miss statistics."""
        stats = {}
        for backend, data in self.cache_stats.items():
            total = data["hits"] + data["misses"]
            hit_rate = (data["hits"] / total * 100) if total > 0 else 0.0
            stats[backend] = {
                "hits": data["hits"],
                "misses": data["misses"],
                "total": total,
                "hit_rate_percent": round(hit_rate, 2),
            }
        return stats

    def get_latency_stats(self) -> dict:
        """Get query latency statistics (ms)."""
        if not self.metrics:
            return {}

        durations = [m.duration_total for m in self.metrics]
        search_times = [m.duration_search for m in self.metrics if m.duration_search > 0]
        llm_times = [m.duration_llm for m in self.metrics if m.duration_llm > 0]
        recency_times = [m.duration_recency for m in self.metrics if m.duration_recency > 0]

        def calc_stats(times):
            if not times:
                return None
            times_sorted = sorted(times)
            return {
                "min_ms": round(min(times) * 1000, 2),
                "max_ms": round(max(times) * 1000, 2),
                "avg_ms": round(sum(times) / len(times) * 1000, 2),
                "p50_ms": round(times_sorted[len(times) // 2] * 1000, 2),
                "p95_ms": round(times_sorted[int(len(times) * 0.95)] * 1000, 2),
                "p99_ms": round(times_sorted[int(len(times) * 0.99)] * 1000, 2),
                "count": len(times),
            }

        return {
            "total": calc_stats(durations),
            "search": calc_stats(search_times),
            "llm": calc_stats(llm_times),
            "recency": calc_stats(recency_times),
        }

    def get_ranking_stats(self) -> dict:
        """Get ranking quality statistics."""
        if not self.metrics:
            return {}

        scores = [m.top_score for m in self.metrics if m.top_score > 0]
        avg_scores = [m.avg_score for m in self.metrics if m.avg_score > 0]

        return {
            "top_score": {
                "min": round(min(scores), 2) if scores else 0,
                "max": round(max(scores), 2) if scores else 0,
                "avg": round(sum(scores) / len(scores), 2) if scores else 0,
                "count": len(scores),
            },
            "avg_score": {
                "min": round(min(avg_scores), 2) if avg_scores else 0,
                "max": round(max(avg_scores), 2) if avg_scores else 0,
                "avg": round(sum(avg_scores) / len(avg_scores), 2) if avg_scores else 0,
                "count": len(avg_scores),
            },
        }

    def get_feature_usage(self) -> dict:
        """Get feature usage statistics."""
        total_queries = len(self.metrics)
        return {
            "total_queries": total_queries,
            "llm_enrichment_count": self.feature_usage.get("llm_enrichment", 0),
            "llm_enrichment_percent": round(
                self.feature_usage.get("llm_enrichment", 0) / total_queries * 100, 2
            ) if total_queries > 0 else 0,
            "recency_scoring_count": self.feature_usage.get("recency_scoring", 0),
            "recency_scoring_percent": round(
                self.feature_usage.get("recency_scoring", 0) / total_queries * 100, 2
            ) if total_queries > 0 else 0,
            "formation_detection_count": self.feature_usage.get("formation_detection", 0),
            "formation_detection_percent": round(
                self.feature_usage.get("formation_detection", 0) / total_queries * 100, 2
            ) if total_queries > 0 else 0,
        }

    def get_error_stats(self) -> dict:
        """Get error statistics."""
        return {
            "total_errors": sum(self.error_counts.values()),
            "errors_by_type": dict(self.error_counts),
        }

    def get_summary(self) -> dict:
        """Get comprehensive monitoring summary."""
        return {
            "total_queries": len(self.metrics),
            "cache": self.get_cache_stats(),
            "latency": self.get_latency_stats(),
            "ranking": self.get_ranking_stats(),
            "features": self.get_feature_usage(),
            "errors": self.get_error_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_recent_queries(self, limit: int = 10) -> list[dict]:
        """Get recent queries for debugging."""
        return [m.to_dict() for m in self.metrics[-limit:]]

    def reset(self) -> None:
        """Reset all monitoring data."""
        self.metrics = []
        self.cache_stats = defaultdict(lambda: {"hits": 0, "misses": 0})
        self.error_counts = defaultdict(int)
        self.feature_usage = defaultdict(int)


# Global monitor instance
_monitor_instance: TacticalSearchMonitor | None = None


def get_monitor() -> TacticalSearchMonitor:
    """Get or create global monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = TacticalSearchMonitor()
    return _monitor_instance


def reset_monitor() -> None:
    """Reset global monitor (for testing)."""
    global _monitor_instance
    _monitor_instance = None


# Timing context manager for measuring operations
class TimingContext:
    """Context manager for measuring operation duration."""

    def __init__(self, name: str = "operation"):
        self.name = name
        self.duration = 0.0
        self.start_time = None

    def __enter__(self):
        self.start_time = time.monotonic()
        return self

    def __exit__(self, *args):
        self.duration = time.monotonic() - self.start_time
        logger.debug(f"{self.name} took {self.duration * 1000:.2f}ms")


__all__ = [
    "QueryMetrics",
    "TacticalSearchMonitor",
    "get_monitor",
    "reset_monitor",
    "TimingContext",
]
