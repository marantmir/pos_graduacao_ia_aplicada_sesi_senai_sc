# Tactical Search Hub v2.4 - Operations Guide

Complete guide for deploying, configuring, and monitoring the Tactical Search Hub in production.

## Quick Start

### Enable/Disable Features via Environment Variables

```bash
# Enable cache (default: true)
export FOOTBALL_INTEL_FEATURE_CACHE_ENABLED=true
export FOOTBALL_INTEL_FEATURE_CACHE_TTL_DAYS=7

# Enable LLM enrichment (default: false)
export FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ENABLED=true
export FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ROLLOUT_PCT=50  # 50% gradual rollout

# Enable recency scoring (default: true)
export FOOTBALL_INTEL_FEATURE_RECENCY_SCORING_ENABLED=true

# Enable retry policy (default: true)
export FOOTBALL_INTEL_FEATURE_RETRY_ENABLED=true
export FOOTBALL_INTEL_FEATURE_RETRY_MAX_ATTEMPTS=3
export FOOTBALL_INTEL_FEATURE_RETRY_BASE_DELAY=1.0

# Enable parallel search (default: true)
export FOOTBALL_INTEL_FEATURE_PARALLEL_ENABLED=true
export FOOTBALL_INTEL_FEATURE_PARALLEL_MAX_WORKERS=4

# A/B Testing (default: false)
export FOOTBALL_INTEL_FEATURE_AB_TEST_ENABLED=true
export FOOTBALL_INTEL_FEATURE_AB_TEST_NEW_RANKING_ROLLOUT_PCT=50  # 50% of users
```

## Configuration Management

### Runtime Configuration

```python
from backend.app.tactical_search.feature_flags import get_feature_flags

flags = get_feature_flags()

# Check if feature is enabled
if flags.is_enabled("cache_enabled"):
    print("Cache is enabled")

# Get configuration value
cache_ttl = flags.get("cache_ttl_days")  # Returns 7 by default

# Change configuration at runtime
flags.set("cache_ttl_days", 14)
flags.set("retry_max_attempts", 5)

# Get full configuration snapshot
config = flags.get_config_snapshot()
print(config)

# Validate configuration
warnings = flags.validate()
for warning in warnings:
    print(f"Warning: {warning}")
```

### Gradual Feature Rollout

Use deterministic hashing to gradually roll out features to subsets of users:

```python
from backend.app.tactical_search.feature_flags import get_feature_flags

flags = get_feature_flags()

# Set rollout percentage (0-100%)
flags.set("llm_query_enrichment_rollout_pct", 50)  # 50% of users

# Check if specific user gets the feature (deterministic per user)
user_id = "user_123"
if flags.rollout_pct("llm_query_enrichment", user_id):
    # This user gets LLM enrichment
    # Same user will always get same result
    pass
```

### Gradual Rollout Strategy

1. **Phase 1**: 0% - Test in staging only
2. **Phase 2**: 5-10% - Canary release to small user base
3. **Phase 3**: 25-50% - Wider rollout, monitor metrics
4. **Phase 4**: 100% - Full rollout when confident

Example rollout schedule:

```bash
# Day 1: Enable for 10% of users
export FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ROLLOUT_PCT=10

# Day 3: Expand to 25% (after monitoring stable)
export FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ROLLOUT_PCT=25

# Day 7: Expand to 50%
export FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ROLLOUT_PCT=50

# Day 14: Full rollout
export FOOTBALL_INTEL_FEATURE_LLM_QUERY_ENRICHMENT_ROLLOUT_PCT=100
```

## Monitoring

### Real-time Monitoring Dashboard

Access the monitoring dashboard via HTTP:

```bash
# Full monitoring summary
curl http://localhost:8000/api/teams/search/tactical/monitoring

# Recent queries (last 10)
curl http://localhost:8000/api/teams/search/tactical/monitoring/recent?limit=10

# Last 50 queries
curl http://localhost:8000/api/teams/search/tactical/monitoring/recent?limit=50
```

### Monitoring Metrics

#### Cache Statistics

```json
{
  "cache": {
    "redis": {
      "hits": 850,
      "misses": 673,
      "total": 1523,
      "hit_rate_percent": 55.8
    }
  }
}
```

**Healthy levels**:
- Hit rate: 50-80% (depends on query patterns)
- Redis hits indicate good cache backend performance

#### Latency Statistics (milliseconds)

```json
{
  "latency": {
    "total": {
      "min_ms": 45.2,
      "max_ms": 2340.5,
      "avg_ms": 340.7,
      "p50_ms": 280.0,
      "p95_ms": 1200.3,
      "p99_ms": 2000.1,
      "count": 1523
    },
    "search": {
      "min_ms": 40.0,
      "max_ms": 2200.0,
      "avg_ms": 300.0,
      ...
    },
    "llm": {
      "min_ms": 100.0,
      "max_ms": 500.0,
      "avg_ms": 250.0,
      ...
    },
    "recency": {
      "min_ms": 5.0,
      "max_ms": 50.0,
      "avg_ms": 15.0,
      ...
    }
  }
}
```

**Healthy levels**:
- p95 latency: < 1000ms
- p99 latency: < 2000ms
- Search component: 60-70% of total time
- LLM component: 20-30% when enabled

#### Feature Usage

```json
{
  "features": {
    "total_queries": 1523,
    "llm_enrichment_count": 761,
    "llm_enrichment_percent": 50.0,
    "recency_scoring_count": 1500,
    "recency_scoring_percent": 98.5,
    "formation_detection_count": 456,
    "formation_detection_percent": 29.9
  }
}
```

**Interpretation**:
- `llm_enrichment_percent`: Reflects rollout percentage and enabled status
- `recency_scoring_percent`: Should be ~100% if enabled
- `formation_detection_percent`: Varies with query patterns (20-40% typical)

#### Ranking Quality

```json
{
  "ranking": {
    "top_score": {
      "min": 5.0,
      "max": 10.0,
      "avg": 8.2,
      "count": 1523
    },
    "avg_score": {
      "min": 4.5,
      "max": 9.8,
      "avg": 7.1,
      "count": 1523
    }
  }
}
```

**Healthy levels**:
- Top score avg: > 7.5 (good ranking quality)
- Avg score avg: > 6.5 (consistent quality across results)

#### Errors

```json
{
  "errors": {
    "total_errors": 23,
    "errors_by_type": {
      "LLM API timeout": 15,
      "Cache backend unavailable": 5,
      "Network error": 3
    }
  }
}
```

**Action items**:
- Error rate > 1%: Investigate component health
- LLM timeouts increasing: Consider scaling LLM infrastructure
- Cache errors: Check Redis/SQLite availability

### Programmatic Monitoring Access

```python
from backend.app.tactical_search.monitoring import get_monitor

monitor = get_monitor()

# Get comprehensive summary
summary = monitor.get_summary()

# Access specific metrics
cache_stats = monitor.get_cache_stats()
latency_stats = monitor.get_latency_stats()
ranking_stats = monitor.get_ranking_stats()
feature_usage = monitor.get_feature_usage()
error_stats = monitor.get_error_stats()

# Recent queries for debugging
recent = monitor.get_recent_queries(limit=20)
for query in recent:
    print(f"Team: {query['team_name']}, Latency: {query['duration_total']*1000:.0f}ms")

# Example: Alert if p95 latency exceeds threshold
p95_latency_ms = latency_stats["total"]["p95_ms"]
if p95_latency_ms > 1500:
    send_alert(f"Latency degradation: p95={p95_latency_ms}ms")

# Example: Alert if cache hit rate drops
redis_hit_rate = cache_stats["redis"]["hit_rate_percent"]
if redis_hit_rate < 40:
    send_alert(f"Cache hit rate low: {redis_hit_rate}%")
```

## Performance Tuning

### Cache Backend Selection

```bash
# Auto-detect (recommended)
export FOOTBALL_INTEL_FEATURE_CACHE_BACKEND=auto

# Force Redis (if available)
export FOOTBALL_INTEL_FEATURE_CACHE_BACKEND=redis

# Use SQLite (if Redis unavailable)
export FOOTBALL_INTEL_FEATURE_CACHE_BACKEND=sqlite

# Use in-memory (for single-instance testing)
export FOOTBALL_INTEL_FEATURE_CACHE_BACKEND=memory
```

### Parallel Search Tuning

```bash
# Number of concurrent threads (4 default, 8 recommended)
export FOOTBALL_INTEL_FEATURE_PARALLEL_MAX_WORKERS=8

# Individual task timeout (10s default)
export FOOTBALL_INTEL_FEATURE_PARALLEL_INDIVIDUAL_TIMEOUT=15

# Total search timeout (15s default)
export FOOTBALL_INTEL_FEATURE_PARALLEL_TOTAL_TIMEOUT=20
```

### Retry Policy Tuning

```bash
# Maximum retry attempts (3 default)
export FOOTBALL_INTEL_FEATURE_RETRY_MAX_ATTEMPTS=5

# Base delay between retries in seconds (1.0 default)
export FOOTBALL_INTEL_FEATURE_RETRY_BASE_DELAY=2.0

# Maximum delay cap (8.0 default)
export FOOTBALL_INTEL_FEATURE_RETRY_MAX_DELAY=16.0

# Jitter percentage (20 default = ±20%)
export FOOTBALL_INTEL_FEATURE_RETRY_JITTER_PCT=30
```

### Recency Scoring Tuning

```bash
# Overall recency weight (0.0-1.0, 0.20 default)
export FOOTBALL_INTEL_FEATURE_RECENCY_WEIGHT=0.25

# Component weights (adjust in code via feature_flags.py)
# Default: 35% recency, 25% trend, 20% views, 20% authority
```

## Production Checklist

- [ ] Cache backend verified working (Redis recommended for production)
- [ ] LLM integration configured and API keys set
- [ ] Monitoring endpoints accessible to operations team
- [ ] Alerting configured for:
  - [ ] Cache hit rate drops below 40%
  - [ ] p95 latency exceeds 1500ms
  - [ ] Error rate exceeds 1%
  - [ ] LLM API timeouts increasing
- [ ] Feature rollout plan created for new features
- [ ] Initial rollout at 5-10% with monitoring for 24h minimum
- [ ] Gradual expansion to 100% over 1-2 weeks
- [ ] Rollback plan prepared for quick disabling via flags

## Troubleshooting

### High Latency

```python
from backend.app.tactical_search.monitoring import get_monitor

monitor = get_monitor()
latency = monitor.get_latency_stats()

# Check which component is slow
if latency["search"]["avg_ms"] > 500:
    # Search itself is slow - check web scraping
    pass

if latency["llm"]["avg_ms"] > 400:
    # LLM enrichment is slow - check API latency
    pass

if latency["recency"]["avg_ms"] > 100:
    # Recency scoring is slow - check calculations
    pass
```

### Low Cache Hit Rate

```python
monitor = get_monitor()
cache_stats = monitor.get_cache_stats()

redis_hit_rate = cache_stats["redis"]["hit_rate_percent"]

if redis_hit_rate < 40:
    # Possible causes:
    # 1. Cache TTL too short - increase FOOTBALL_INTEL_FEATURE_CACHE_TTL_DAYS
    # 2. Query patterns too diverse - enable LLM query normalization
    # 3. Cache backend issues - check Redis availability
    pass
```

### High Error Rate

```python
monitor = get_monitor()
error_stats = monitor.get_error_stats()

if error_stats["total_errors"] > 0:
    for error_type, count in error_stats["errors_by_type"].items():
        if "LLM" in error_type:
            # LLM issues - disable LLM via feature flag, investigate API
            pass
        elif "Cache" in error_type:
            # Cache issues - check backend availability
            pass
```

### Formation Detection Not Working

```python
from backend.app.tactical_search.tactical_keywords import extract_formation

# Test formation extraction
formations = ["4-3-3", "3-5-2", "4-2-3-1"]
for formation_str in formations:
    detected = extract_formation(f"Team {formation_str}")
    print(f"'{formation_str}': {detected}")

# Supported patterns: [3-5]-[1-4]-[1-3]
# Examples: 4-3-3, 4-2-3-1, 3-5-2, 5-2-3, 3-4-3
```

## API Endpoints Reference

### Search Endpoints

```bash
# Main tactical search
GET /api/teams/search/tactical?team=Flamengo&formation=4-3-3&use_llm=true&use_recency=true

# Enhanced search (with enrichment of traditional results)
GET /api/teams/search/tactical/enhanced?team=Flamengo&enrichment=true

# Comparison (traditional vs tactical)
GET /api/teams/search/tactical/compare?team=Flamengo

# Status check
GET /api/teams/search/tactical/status
```

### Monitoring Endpoints

```bash
# Full monitoring dashboard
GET /api/teams/search/tactical/monitoring

# Recent query history
GET /api/teams/search/tactical/monitoring/recent?limit=10
```

## Support & Documentation

- **Feature Flags**: See `backend/app/tactical_search/feature_flags.py`
- **Monitoring**: See `backend/app/tactical_search/monitoring.py`
- **Integration**: See `backend/app/tactical_search/integration.py`
- **Module Docs**: See `backend/app/tactical_search/__init__.py`

## Version History

- v2.4.0: Added feature flags, monitoring, gradual rollout
- v2.3.0: Added recency scoring with 4 components
- v2.2.0: Added LLM integration and semantic ranking
- v2.1.0: Added retry policy and parallelization
- v2.0.0: Initial Tactical Search Hub release
