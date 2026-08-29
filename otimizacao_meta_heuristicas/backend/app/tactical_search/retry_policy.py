"""Política de retry exponencial com jitter para operações de rede.

Estratégia:
1. Exponential backoff: 1s → 2s → 4s → 8s → 16s
2. Random jitter: ±20% para evitar thundering herd
3. Max attempts: 3-4 retries por operação
4. Timeout adaptativo: aumenta com tentativas posteriores

Uso:
  @retry_with_backoff(max_attempts=3, base_delay=1.0)
  def fetch_data(url):
      ...
"""
from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ============================================================================
# Retry Decorator
# ============================================================================


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    jitter: bool = True,
) -> Callable:
    """Decorator para retry exponencial com jitter.

    Args:
        max_attempts: número máximo de tentativas (1-5)
        base_delay: delay inicial em segundos
        max_delay: delay máximo após capping
        jitter: adicionar jitter ±20%

    Exemplo:
        @retry_with_backoff(max_attempts=3, base_delay=1.0)
        def fetch(url):
            return urllib.request.urlopen(url)

        result = fetch("https://...")
    """
    if max_attempts < 1 or max_attempts > 5:
        raise ValueError("max_attempts deve estar entre 1-5")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_attempts:
                        # Última tentativa: lançar exceção
                        logger.error(
                            f"{func.__name__} falhou após {max_attempts} tentativas: {e}"
                        )
                        raise

                    # Calcular delay com exponential backoff
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))

                    # Adicionar jitter
                    if jitter:
                        jitter_factor = 1.0 + random.uniform(-0.2, 0.2)
                        delay *= jitter_factor

                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} falhou: {e}. "
                        f"Retrying em {delay:.1f}s..."
                    )
                    time.sleep(delay)

            # Nunca deve chegar aqui
            raise last_exception or RuntimeError("Retry loop failed")

        return wrapper

    return decorator


def retry_with_backoff_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    jitter: bool = True,
) -> Callable:
    """Decorator async para retry exponencial com jitter.

    Uso com async/await:
        @retry_with_backoff_async(max_attempts=3)
        async def fetch(url):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    return await resp.text()

        result = await fetch("https://...")
    """
    if max_attempts < 1 or max_attempts > 5:
        raise ValueError("max_attempts deve estar entre 1-5")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} falhou após {max_attempts} tentativas: {e}"
                        )
                        raise

                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    if jitter:
                        jitter_factor = 1.0 + random.uniform(-0.2, 0.2)
                        delay *= jitter_factor

                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} falhou: {e}. "
                        f"Retrying em {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

            raise last_exception or RuntimeError("Retry loop failed")

        return wrapper

    return decorator


# ============================================================================
# Helper Functions
# ============================================================================


def calculate_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 16.0) -> float:
    """Calcula delay para tentativa N com exponential backoff.

    Args:
        attempt: número da tentativa (1-indexed)
        base_delay: delay inicial
        max_delay: delay máximo

    Returns:
        Delay em segundos (sem jitter)

    Exemplo:
        attempt 1 → 1s
        attempt 2 → 2s
        attempt 3 → 4s
        attempt 4 → 8s
        attempt 5 → 16s (capped)
    """
    if attempt < 1:
        return 0.0
    return min(max_delay, base_delay * (2 ** (attempt - 1)))


def add_jitter(delay: float, jitter_pct: float = 20) -> float:
    """Adiciona jitter aleatório a um delay.

    Args:
        delay: delay base em segundos
        jitter_pct: percentual de jitter (default 20%)

    Returns:
        delay ± jitter
    """
    factor = 1.0 + random.uniform(-jitter_pct / 100, jitter_pct / 100)
    return delay * factor
