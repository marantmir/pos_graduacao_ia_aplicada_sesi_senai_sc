"""Orquestração de buscas paralelas com timeout compartilhado.

Executa múltiplas fontes em paralelo (web, YouTube, Wikipedia, APIs):
- ThreadPoolExecutor para I/O bound
- Timeout individual per operação (10s)
- Timeout total (15s) para all operations
- Error collection + logging

Resultado: primeiras respostas ganham, timeouts acumulados sinalizam degradação.
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Timeouts em segundos
INDIVIDUAL_TIMEOUT = 10  # Por operação
TOTAL_TIMEOUT = 15  # Total de todas as operações


class ParallelSearchExecutor:
    """Executa múltiplas buscas em paralelo com timeout compartilhado."""

    def __init__(self, max_workers: int = 4, total_timeout: int = TOTAL_TIMEOUT):
        self.max_workers = max_workers
        self.total_timeout = total_timeout
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def execute(self, tasks: list[dict]) -> dict:
        """Executa lista de tarefas em paralelo.

        Args:
            tasks: list[{
                "name": "web_search",
                "func": callable,
                "args": (...),
                "kwargs": {...},
            }]

        Returns:
            {
                "results": {name: result},
                "errors": [{name, error, traceback}],
                "duration": float,
            }
        """
        start_time = time.time()
        results = {}
        errors = []
        futures = {}

        try:
            # Submeter todas as tarefas
            for task in tasks:
                name = task["name"]
                func = task["func"]
                args = task.get("args", ())
                kwargs = task.get("kwargs", {})

                future = self.executor.submit(func, *args, **kwargs)
                futures[future] = name
                logger.debug(f"Submitted task: {name}")

            # Aguardar resultados com timeout
            for future in concurrent.futures.as_completed(
                futures.keys(), timeout=self.total_timeout
            ):
                name = futures[future]
                try:
                    result = future.result(timeout=INDIVIDUAL_TIMEOUT)
                    results[name] = result
                    logger.debug(f"Task completed: {name}")
                except concurrent.futures.TimeoutError:
                    errors.append({
                        "name": name,
                        "error": "TimeoutError",
                        "message": f"Operação excedeu {INDIVIDUAL_TIMEOUT}s",
                    })
                    logger.warning(f"Task timeout: {name}")
                except Exception as e:
                    errors.append({
                        "name": name,
                        "error": type(e).__name__,
                        "message": str(e),
                    })
                    logger.warning(f"Task failed: {name} - {e}")

        except concurrent.futures.TimeoutError:
            logger.warning(f"Total timeout ({self.total_timeout}s) exceeded")
            # Cancelar tasks pendentes
            for future in futures.keys():
                future.cancel()

        duration = time.time() - start_time

        return {
            "results": results,
            "errors": errors,
            "duration": round(duration, 2),
            "completed": len(results),
            "failed": len(errors),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.executor.shutdown(wait=False)


def parallel_tactical_search(
    query: str,
    web_search_fn: Callable,
    youtube_search_fn: Callable,
    wikipedia_fn: Callable | None = None,
    api_search_fn: Callable | None = None,
    max_workers: int = 4,
) -> dict:
    """Busca tática paralela: web + YouTube + Wikipedia + APIs.

    Args:
        query: query de busca
        web_search_fn: função de busca web
        youtube_search_fn: função de busca YouTube
        wikipedia_fn: função opcional de lookup Wikipedia
        api_search_fn: função opcional de busca em APIs
        max_workers: número de workers paralelos

    Returns:
        {
            "web": [...],
            "youtube": [...],
            "wikipedia": {...} ou None,
            "apis": [...],
            "errors": [...],
            "duration": float,
        }
    """
    tasks = [
        {
            "name": "web_search",
            "func": web_search_fn,
            "kwargs": {"query": query},
        },
        {
            "name": "youtube_search",
            "func": youtube_search_fn,
            "kwargs": {"query": query},
        },
    ]

    if wikipedia_fn:
        tasks.append({
            "name": "wikipedia",
            "func": wikipedia_fn,
            "kwargs": {"query": query},
        })

    if api_search_fn:
        tasks.append({
            "name": "api_search",
            "func": api_search_fn,
            "kwargs": {"query": query},
        })

    with ParallelSearchExecutor(max_workers=max_workers) as executor:
        execution = executor.execute(tasks)

    # Consolidar resultados
    return {
        "query": query,
        "web": execution["results"].get("web_search", {}).get("results", []),
        "youtube": execution["results"].get("youtube_search", []),
        "wikipedia": execution["results"].get("wikipedia"),
        "apis": execution["results"].get("api_search", []),
        "errors": execution["errors"],
        "duration": execution["duration"],
        "status": "success" if not execution["errors"] else "partial",
    }


# ============================================================================
# Utilities
# ============================================================================

def merge_search_results(sources_list: list[list[dict]]) -> list[dict]:
    """Mescla resultados de múltiplas buscas removendo duplicados.

    Args:
        sources_list: lista de listas de sources

    Returns:
        sources merged e dedupligadas
    """
    all_sources = []
    for sources in sources_list:
        if sources and isinstance(sources, list):
            all_sources.extend(sources)

    # Dedupe por URL
    seen_urls = set()
    deduped = []
    for source in all_sources:
        url = (source.get("url") or "").strip().lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(source)
        elif not url:  # Sem URL, adicionar mesmo assim
            deduped.append(source)

    return deduped
