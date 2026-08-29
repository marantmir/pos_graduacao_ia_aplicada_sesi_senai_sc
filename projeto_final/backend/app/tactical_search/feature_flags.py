"""Feature flags for Tactical Search Hub v2.4.

Controla ativação/desativação de features para deployment seguro:
- Cache layer (Redis/SQLite/Memory)
- Retry policy (exponencial backoff)
- Parallel search (concurrent execution)
- LLM integration (query enrichment, re-ranking)
- Recency scoring (view trends, temporal decay)

Suporta:
- Environment variables (FOOTBALL_INTEL_FEATURE_*)
- Runtime configuration (em memória)
- A/B testing (rollout percentages)
- Gradual feature enablement
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class FeatureFlags:
    """Feature flag manager para Tactical Search Hub."""

    # Defaults - pode ser sobrescrito por env vars ou runtime config
    DEFAULTS = {
        # Core features
        "cache_enabled": True,
        "cache_ttl_days": 7,
        "cache_backend": "auto",  # "redis", "sqlite", "memory", "auto"

        # Resilience
        "retry_enabled": True,
        "retry_max_attempts": 3,
        "retry_base_delay": 1.0,
        "retry_max_delay": 8.0,
        "retry_jitter_pct": 20,

        # Parallelization
        "parallel_enabled": True,
        "parallel_max_workers": 4,
        "parallel_individual_timeout": 10,
        "parallel_total_timeout": 15,

        # LLM Integration
        "llm_query_enrichment_enabled": False,  # Disabled by default, opt-in
        "llm_query_enrichment_rollout_pct": 50,  # Gradual rollout (0-100%)
        "llm_semantic_ranking_enabled": False,  # Disabled by default, opt-in
        "llm_semantic_ranking_rollout_pct": 50,  # Gradual rollout (0-100%)
        "llm_explanations_enabled": True,       # Enabled if LLM available

        # Recency Scoring
        "recency_scoring_enabled": True,
        "recency_weight": 0.20,
        "recency_view_trend_enabled": True,
        "recency_temporal_decay_enabled": True,
        "recency_authority_enabled": True,

        # A/B Testing
        "ab_test_enabled": False,
        "ab_test_new_ranking_rollout_pct": 50,

        # Performance
        "ranking_top_k": 24,
        "max_sources_limit": 100,

        # Monitoring
        "metrics_enabled": True,
        "detailed_logging_enabled": False,
    }

    def __init__(self):
        self._config = {}
        self._load_from_env()
        self._load_defaults()

    def _load_defaults(self):
        """Carrega defaults não sobrescritos por env vars."""
        for key, value in self.DEFAULTS.items():
            if key not in self._config:
                self._config[key] = value

    def _load_from_env(self):
        """Carrega feature flags de environment variables (FOOTBALL_INTEL_FEATURE_*)."""
        for key in self.DEFAULTS.keys():
            env_key = f"FOOTBALL_INTEL_FEATURE_{key.upper()}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                # Parse boolean values
                if env_value.lower() in ("true", "1", "yes", "on"):
                    self._config[key] = True
                elif env_value.lower() in ("false", "0", "no", "off"):
                    self._config[key] = False
                else:
                    # Try parsing as number
                    try:
                        if "." in env_value:
                            self._config[key] = float(env_value)
                        else:
                            self._config[key] = int(env_value)
                    except ValueError:
                        # Keep as string
                        self._config[key] = env_value
                logger.info(f"Loaded feature flag from env: {key}={self._config[key]}")

    def get(self, key: str, default: Any = None) -> Any:
        """Obter valor de feature flag."""
        return self._config.get(key, default or self.DEFAULTS.get(key))

    def is_enabled(self, key: str) -> bool:
        """Verifica se feature está habilitada."""
        value = self.get(key)
        return bool(value)

    def set(self, key: str, value: Any) -> None:
        """Configurar feature flag em runtime."""
        self._config[key] = value
        logger.info(f"Feature flag set: {key}={value}")

    def rollout_pct(self, feature: str, user_id: str | None = None) -> bool:
        """Verifica rollout percentual com hashing do user_id.

        Permite rollout gradual: se rollout_pct=50, metade dos users
        recebe a feature. O mesmo user sempre recebe a mesma decisão.
        """
        rollout_key = f"{feature}_rollout_pct"
        pct = self.get(rollout_key, 0)

        if pct >= 100:
            return True
        if pct <= 0:
            return False

        # Usar hash do user_id para decisão determinística
        if user_id:
            hash_value = hash(f"{user_id}_{feature}") % 100
            return hash_value < pct

        # Sem user_id, usar randomização
        import random
        return random.randint(0, 100) < pct

    def get_config_snapshot(self) -> dict:
        """Retorna snapshot da configuração atual (para logging/debugging)."""
        return dict(self._config)

    def validate(self) -> list[str]:
        """Valida configuração e retorna lista de warnings."""
        warnings = []

        # Cache validations
        if not self.is_enabled("cache_enabled"):
            warnings.append("Cache desabilitado: performance pode sofrer")

        # Retry validations
        if self.is_enabled("retry_enabled"):
            max_attempts = self.get("retry_max_attempts")
            if max_attempts < 1:
                warnings.append("retry_max_attempts deve ser >= 1")

        # Parallel validations
        if self.is_enabled("parallel_enabled"):
            workers = self.get("parallel_max_workers")
            if workers < 1:
                warnings.append("parallel_max_workers deve ser >= 1")

        # LLM validations
        if self.is_enabled("llm_query_enrichment_enabled"):
            from ..llm_assistant import llm_status
            status = llm_status()
            if not status.get("enabled"):
                warnings.append("LLM enrichment habilitado mas LLM não configurado")

        # Rollout validations
        llm_enrichment_rollout = self.get("llm_query_enrichment_rollout_pct", 0)
        if llm_enrichment_rollout < 0 or llm_enrichment_rollout > 100:
            warnings.append(f"llm_query_enrichment_rollout_pct deve estar entre 0-100, recebido {llm_enrichment_rollout}")

        llm_ranking_rollout = self.get("llm_semantic_ranking_rollout_pct", 0)
        if llm_ranking_rollout < 0 or llm_ranking_rollout > 100:
            warnings.append(f"llm_semantic_ranking_rollout_pct deve estar entre 0-100, recebido {llm_ranking_rollout}")

        ab_test_pct = self.get("ab_test_new_ranking_rollout_pct", 0)
        if ab_test_pct < 0 or ab_test_pct > 100:
            warnings.append(f"ab_test_new_ranking_rollout_pct deve estar entre 0-100, recebido {ab_test_pct}")

        return warnings


# Global instance
_flags_instance: FeatureFlags | None = None


def get_feature_flags() -> FeatureFlags:
    """Obter instância global de feature flags (singleton)."""
    global _flags_instance
    if _flags_instance is None:
        _flags_instance = FeatureFlags()
        warnings = _flags_instance.validate()
        for warning in warnings:
            logger.warning(f"Feature flag validation: {warning}")
    return _flags_instance


def reset_feature_flags() -> None:
    """Reset global instance (para testes)."""
    global _flags_instance
    _flags_instance = None


# ============================================================================
# Convenience functions
# ============================================================================

def cache_enabled() -> bool:
    """Cache está habilitado?"""
    return get_feature_flags().is_enabled("cache_enabled")


def retry_enabled() -> bool:
    """Retry está habilitado?"""
    return get_feature_flags().is_enabled("retry_enabled")


def parallel_enabled() -> bool:
    """Busca paralela está habilitada?"""
    return get_feature_flags().is_enabled("parallel_enabled")


def llm_enrichment_enabled(user_id: str | None = None) -> bool:
    """LLM query enrichment está habilitado?"""
    flags = get_feature_flags()
    if not flags.is_enabled("llm_query_enrichment_enabled"):
        return False
    return flags.rollout_pct("llm_query_enrichment", user_id)


def llm_semantic_ranking_enabled(user_id: str | None = None) -> bool:
    """LLM semantic ranking está habilitado?"""
    flags = get_feature_flags()
    if not flags.is_enabled("llm_semantic_ranking_enabled"):
        return False
    return flags.rollout_pct("llm_semantic_ranking", user_id)


def recency_scoring_enabled() -> bool:
    """Recency scoring está habilitado?"""
    return get_feature_flags().is_enabled("recency_scoring_enabled")


def ab_test_enabled(user_id: str | None = None) -> bool:
    """A/B test está habilitado?"""
    flags = get_feature_flags()
    if not flags.is_enabled("ab_test_enabled"):
        return False
    return flags.rollout_pct("ab_test_new_ranking", user_id)


# ============================================================================
# Export API
# ============================================================================

__all__ = [
    "FeatureFlags",
    "get_feature_flags",
    "reset_feature_flags",
    "cache_enabled",
    "retry_enabled",
    "parallel_enabled",
    "llm_enrichment_enabled",
    "llm_semantic_ranking_enabled",
    "recency_scoring_enabled",
    "ab_test_enabled",
]
