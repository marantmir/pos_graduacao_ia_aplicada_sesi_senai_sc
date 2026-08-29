"""Testes para Feature Flags do Tactical Search Hub."""
import pytest
import os
from unittest.mock import patch

from backend.app.tactical_search.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    reset_feature_flags,
    cache_enabled,
    retry_enabled,
    parallel_enabled,
    llm_enrichment_enabled,
    recency_scoring_enabled,
    ab_test_enabled,
)


class TestFeatureFlagsBasic:
    def teardown_method(self):
        """Limpar global state após cada teste."""
        reset_feature_flags()

    def test_defaults_loaded(self):
        """Defaults são carregados corretamente."""
        flags = FeatureFlags()
        assert flags.is_enabled("cache_enabled") is True
        assert flags.is_enabled("retry_enabled") is True
        assert flags.is_enabled("parallel_enabled") is True

    def test_get_feature_flag(self):
        """Obter valor de feature flag."""
        flags = FeatureFlags()
        assert flags.get("retry_max_attempts") == 3
        assert flags.get("retry_base_delay") == 1.0
        assert flags.get("cache_ttl_days") == 7

    def test_set_feature_flag(self):
        """Configurar feature flag em runtime."""
        flags = FeatureFlags()
        flags.set("retry_max_attempts", 5)
        assert flags.get("retry_max_attempts") == 5

    def test_is_enabled(self):
        """Verificar se feature está habilitada."""
        flags = FeatureFlags()
        assert flags.is_enabled("cache_enabled") is True
        flags.set("cache_enabled", False)
        assert flags.is_enabled("cache_enabled") is False

    def test_get_config_snapshot(self):
        """Obter snapshot de configuração."""
        flags = FeatureFlags()
        snapshot = flags.get_config_snapshot()
        assert isinstance(snapshot, dict)
        assert "cache_enabled" in snapshot
        assert "retry_enabled" in snapshot


class TestEnvironmentVariables:
    def teardown_method(self):
        """Limpar environment e global state."""
        reset_feature_flags()
        # Limpar env vars setados no teste
        for key in list(os.environ.keys()):
            if key.startswith("FOOTBALL_INTEL_FEATURE_"):
                del os.environ[key]

    def test_env_var_boolean_true(self):
        """Environment variable booleana (true)."""
        os.environ["FOOTBALL_INTEL_FEATURE_CACHE_ENABLED"] = "true"
        flags = FeatureFlags()
        assert flags.is_enabled("cache_enabled") is True

    def test_env_var_boolean_false(self):
        """Environment variable booleana (false)."""
        os.environ["FOOTBALL_INTEL_FEATURE_CACHE_ENABLED"] = "false"
        flags = FeatureFlags()
        assert flags.is_enabled("cache_enabled") is False

    def test_env_var_numeric(self):
        """Environment variable numérica."""
        os.environ["FOOTBALL_INTEL_FEATURE_RETRY_MAX_ATTEMPTS"] = "5"
        flags = FeatureFlags()
        assert flags.get("retry_max_attempts") == 5

    def test_env_var_float(self):
        """Environment variable com ponto flutuante."""
        os.environ["FOOTBALL_INTEL_FEATURE_RETRY_BASE_DELAY"] = "2.5"
        flags = FeatureFlags()
        assert flags.get("retry_base_delay") == 2.5

    def test_env_var_string(self):
        """Environment variable como string."""
        os.environ["FOOTBALL_INTEL_FEATURE_CACHE_BACKEND"] = "redis"
        flags = FeatureFlags()
        assert flags.get("cache_backend") == "redis"

    def test_env_var_overrides_default(self):
        """Environment variable sobrescreve default."""
        assert FeatureFlags.DEFAULTS["cache_ttl_days"] == 7
        os.environ["FOOTBALL_INTEL_FEATURE_CACHE_TTL_DAYS"] = "14"
        flags = FeatureFlags()
        assert flags.get("cache_ttl_days") == 14


class TestRolloutPercentages:
    def test_rollout_pct_0_always_false(self):
        """Rollout 0% sempre retorna False."""
        flags = FeatureFlags()
        flags.set("llm_enrichment_rollout_pct", 0)
        assert flags.rollout_pct("llm_enrichment", "user1") is False
        assert flags.rollout_pct("llm_enrichment", "user2") is False

    def test_rollout_pct_100_always_true(self):
        """Rollout 100% sempre retorna True."""
        flags = FeatureFlags()
        flags.set("llm_enrichment_rollout_pct", 100)
        assert flags.rollout_pct("llm_enrichment", "user1") is True
        assert flags.rollout_pct("llm_enrichment", "user2") is True

    def test_rollout_pct_deterministic(self):
        """Mesmo user sempre recebe mesma decisão."""
        flags = FeatureFlags()
        flags.set("llm_enrichment_rollout_pct", 50)
        user_id = "consistent_user"
        result1 = flags.rollout_pct("llm_enrichment", user_id)
        result2 = flags.rollout_pct("llm_enrichment", user_id)
        assert result1 == result2

    def test_rollout_pct_without_user_id(self):
        """Rollout sem user_id usa randomização."""
        flags = FeatureFlags()
        flags.set("llm_enrichment_rollout_pct", 50)
        # Pode retornar True ou False, ambos são válidos
        result = flags.rollout_pct("llm_enrichment", None)
        assert isinstance(result, bool)


class TestValidation:
    def teardown_method(self):
        reset_feature_flags()

    def test_validation_passes(self):
        """Validação com defaults passa."""
        flags = FeatureFlags()
        warnings = flags.validate()
        # Pode ter alguns warnings, mas não deve quebrar
        assert isinstance(warnings, list)

    def test_validation_warns_cache_disabled(self):
        """Validação avisa se cache desabilitado."""
        flags = FeatureFlags()
        flags.set("cache_enabled", False)
        warnings = flags.validate()
        assert any("Cache desabilitado" in w for w in warnings)

    def test_validation_warns_invalid_rollout(self):
        """Validação avisa se rollout inválido."""
        flags = FeatureFlags()
        flags.set("llm_query_enrichment_rollout_pct", 150)
        warnings = flags.validate()
        assert any("deve estar entre 0-100" in w for w in warnings)


class TestConvenienceFunctions:
    def teardown_method(self):
        reset_feature_flags()

    def test_cache_enabled_function(self):
        """Função cache_enabled()."""
        assert cache_enabled() is True
        get_feature_flags().set("cache_enabled", False)
        assert cache_enabled() is False

    def test_retry_enabled_function(self):
        """Função retry_enabled()."""
        assert retry_enabled() is True

    def test_parallel_enabled_function(self):
        """Função parallel_enabled()."""
        assert parallel_enabled() is True

    def test_llm_enrichment_enabled_function(self):
        """Função llm_enrichment_enabled()."""
        # Por default desabilitado
        assert llm_enrichment_enabled() is False

        # Habilitar
        get_feature_flags().set("llm_query_enrichment_enabled", True)
        get_feature_flags().set("llm_query_enrichment_rollout_pct", 100)
        assert llm_enrichment_enabled() is True

    def test_recency_scoring_enabled_function(self):
        """Função recency_scoring_enabled()."""
        assert recency_scoring_enabled() is True

    def test_ab_test_enabled_function(self):
        """Função ab_test_enabled()."""
        # Por default desabilitado
        assert ab_test_enabled() is False


class TestGlobalSingleton:
    def teardown_method(self):
        reset_feature_flags()

    def test_get_feature_flags_singleton(self):
        """get_feature_flags() retorna singleton."""
        flags1 = get_feature_flags()
        flags2 = get_feature_flags()
        assert flags1 is flags2

    def test_reset_clears_singleton(self):
        """reset_feature_flags() limpa singleton."""
        flags1 = get_feature_flags()
        reset_feature_flags()
        flags2 = get_feature_flags()
        assert flags1 is not flags2

    def test_changes_persist_across_calls(self):
        """Mudanças persistem entre chamadas de get_feature_flags()."""
        get_feature_flags().set("retry_max_attempts", 10)
        retrieved = get_feature_flags().get("retry_max_attempts")
        assert retrieved == 10


class TestGradualRollout:
    def teardown_method(self):
        reset_feature_flags()

    def test_gradual_llm_rollout(self):
        """Simular rollout gradual de LLM."""
        flags = get_feature_flags()
        flags.set("llm_query_enrichment_enabled", True)

        # 0% rollout
        flags.set("llm_query_enrichment_rollout_pct", 0)
        assert flags.rollout_pct("llm_query_enrichment", "user1") is False

        # 50% rollout
        flags.set("llm_query_enrichment_rollout_pct", 50)
        # Some users get it, some don't
        result1 = flags.rollout_pct("llm_query_enrichment", "user1")
        result2 = flags.rollout_pct("llm_query_enrichment", "user2")
        # At least one should be consistent with itself
        assert flags.rollout_pct("llm_query_enrichment", "user1") == result1

        # 100% rollout
        flags.set("llm_query_enrichment_rollout_pct", 100)
        assert flags.rollout_pct("llm_query_enrichment", "user1") is True
        assert flags.rollout_pct("llm_query_enrichment", "user2") is True

    def test_ab_test_split(self):
        """A/B test com split 50/50."""
        flags = get_feature_flags()
        flags.set("ab_test_enabled", True)
        flags.set("ab_test_new_ranking_rollout_pct", 50)

        # Teste com múltiplos users
        users = [f"user{i}" for i in range(100)]
        new_ranking_users = sum(
            1 for u in users if flags.rollout_pct("ab_test_new_ranking", u)
        )

        # Com 100 users e 50% rollout, esperamos ~50 recebendo feature
        # (com variância normal de hashing)
        assert 30 < new_ranking_users < 70  # Permitir variância
