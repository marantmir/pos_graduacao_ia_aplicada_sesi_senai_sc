"""Testes para Tactical Search Hub Fase 2: Retry + Paralelização."""
import pytest
import time
from unittest.mock import Mock, patch

from backend.app.tactical_search.retry_policy import (
    calculate_backoff, add_jitter, retry_with_backoff,
)
from backend.app.tactical_search.parallel_search import (
    ParallelSearchExecutor, parallel_tactical_search, merge_search_results,
)


# ============================================================================
# Test Retry Policy
# ============================================================================

class TestRetryPolicy:
    def test_calculate_backoff_exponential(self):
        """Calcula exponential backoff corretamente."""
        assert calculate_backoff(1, base_delay=1.0) == 1.0
        assert calculate_backoff(2, base_delay=1.0) == 2.0
        assert calculate_backoff(3, base_delay=1.0) == 4.0
        assert calculate_backoff(4, base_delay=1.0) == 8.0
        assert calculate_backoff(5, base_delay=1.0) == 16.0

    def test_calculate_backoff_capped(self):
        """Respeita delay máximo."""
        assert calculate_backoff(10, base_delay=1.0, max_delay=8.0) == 8.0
        assert calculate_backoff(5, base_delay=2.0, max_delay=10.0) == 10.0

    def test_add_jitter(self):
        """Adiciona jitter ±20%."""
        base_delay = 10.0
        for _ in range(10):
            jittered = add_jitter(base_delay, jitter_pct=20)
            assert 8.0 <= jittered <= 12.0  # ±20%

    def test_retry_decorator_success_first_attempt(self):
        """Sucesso na primeira tentativa, sem retry."""
        call_count = 0

        @retry_with_backoff(max_attempts=3)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()
        assert result == "success"
        assert call_count == 1  # Sem retries

    def test_retry_decorator_success_after_retry(self):
        """Sucesso após falhas transitórias."""
        call_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3  # 2 falhas + 1 sucesso

    def test_retry_decorator_max_attempts_exceeded(self):
        """Falha permanente após N tentativas."""
        call_count = 0

        @retry_with_backoff(max_attempts=2, base_delay=0.01)
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent error")

        with pytest.raises(ValueError):
            failing_func()

        assert call_count == 2  # Max attempts


# ============================================================================
# Test Parallel Search
# ============================================================================

class TestParallelSearch:
    def test_parallel_executor_success(self):
        """Executa tarefas em paralelo com sucesso."""
        def task1():
            return "result1"

        def task2():
            return "result2"

        executor = ParallelSearchExecutor(max_workers=2)
        result = executor.execute([
            {"name": "task1", "func": task1},
            {"name": "task2", "func": task2},
        ])

        assert result["completed"] == 2
        assert result["failed"] == 0
        assert result["results"]["task1"] == "result1"
        assert result["results"]["task2"] == "result2"

    def test_parallel_executor_partial_failure(self):
        """Continua com sucesso mesmo se uma tarefa falha."""
        def success_task():
            return "success"

        def failure_task():
            raise ValueError("Error")

        executor = ParallelSearchExecutor(max_workers=2)
        result = executor.execute([
            {"name": "success", "func": success_task},
            {"name": "failure", "func": failure_task},
        ])

        assert result["completed"] == 1
        assert result["failed"] == 1
        assert "success" in result["results"]
        assert len(result["errors"]) == 1

    def test_parallel_executor_timeout(self):
        """Timeout aplica aos workers individuais."""
        def slow_task():
            time.sleep(15)  # Excede timeout individual
            return "done"

        executor = ParallelSearchExecutor(max_workers=1, total_timeout=2)
        result = executor.execute([
            {"name": "slow", "func": slow_task},
        ])

        # Deve ter timeout ou não concluir
        assert result["completed"] == 0 or "slow" not in result["results"]

    def test_merge_search_results_deduplication(self):
        """Remove duplicados por URL."""
        sources1 = [
            {"url": "https://example.com/1", "title": "Source 1"},
            {"url": "https://example.com/2", "title": "Source 2"},
        ]
        sources2 = [
            {"url": "https://example.com/2", "title": "Source 2 Dup"},  # Dup
            {"url": "https://example.com/3", "title": "Source 3"},
        ]

        merged = merge_search_results([sources1, sources2])

        assert len(merged) == 3  # 1, 2, 3 (2 dedup)
        urls = [s["url"] for s in merged]
        assert len(set(urls)) == 3  # Todos únicos

    def test_merge_search_results_empty_lists(self):
        """Handle listas vazias gracefully."""
        merged = merge_search_results([[], None, []])
        assert merged == []

    def test_parallel_tactical_search_mock(self):
        """Busca tática paralela com mocks."""
        def mock_web_search(query):
            return {"results": [{"title": "Web result", "url": "http://web.com"}]}

        def mock_youtube_search(query):
            return [{"title": "YouTube video", "url": "http://youtube.com"}]

        result = parallel_tactical_search(
            "Flamengo 4-3-3",
            web_search_fn=mock_web_search,
            youtube_search_fn=mock_youtube_search,
        )

        assert result["query"] == "Flamengo 4-3-3"
        assert len(result["web"]) == 1
        assert len(result["youtube"]) == 1
        assert result["status"] in ["success", "partial"]


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhase2Integration:
    def test_retry_improves_reliability(self):
        """Retry exponencial melhora taxa de sucesso."""
        attempt_count = 0

        @retry_with_backoff(max_attempts=3, base_delay=0.01)
        def eventually_succeeds():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ConnectionError("Temp error")
            return "ok"

        result = eventually_succeeds()
        assert result == "ok"
        assert attempt_count == 2  # Retry funcionou

    def test_parallel_timeout_respected(self):
        """Timeout total é respeitado even com múltiplas tarefas."""
        def slow_task_1():
            time.sleep(20)
            return "1"

        def slow_task_2():
            time.sleep(20)
            return "2"

        executor = ParallelSearchExecutor(max_workers=2, total_timeout=3)
        start = time.time()
        result = executor.execute([
            {"name": "t1", "func": slow_task_1},
            {"name": "t2", "func": slow_task_2},
        ])
        elapsed = time.time() - start

        # Deve completar em ~3s, não 40s
        assert elapsed < 6.0, f"Took {elapsed}s, expected <6s"
        assert result["completed"] == 0  # Nenhuma completou
