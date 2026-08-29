"""Cache distribuído com Redis e fallback em SQLite.

Estratégia:
1. Redis (preferido): rápido, TTL automático, distribuído
2. SQLite (fallback): sem dependência externa, ideal para dev local
3. Memory cache: para dev sem Redis/SQLite configurado

Cada entry no cache inclui:
- query_normalized: query padronizada (lowercase, trim)
- query_hash: SHA256 para deduplicação
- sources: array de fontes rankadas
- cached_at: timestamp UTC
- expires_at: timestamp UTC (now + 7 dias)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7
CACHE_TTL_SECONDS = CACHE_TTL_DAYS * 24 * 3600
BACKEND = os.getenv("TACTICAL_CACHE_BACKEND", "memory")  # "redis", "sqlite", "memory"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SQLITE_PATH = os.getenv("TACTICAL_CACHE_DB", "backend/data/tactical_search_cache.db")


def init_cache() -> None:
    """Inicializa backend de cache (cria tabelas SQLite, valida conexão Redis, etc)."""
    if BACKEND == "sqlite":
        os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tactical_search_cache (
                query_hash TEXT PRIMARY KEY,
                query_normalized TEXT NOT NULL,
                sources TEXT NOT NULL,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON tactical_search_cache(expires_at)")
        conn.commit()
        conn.close()
        logger.info(f"SQLite cache inicializado em {SQLITE_PATH}")
    elif BACKEND == "redis":
        try:
            import redis
            client = redis.from_url(REDIS_URL)
            client.ping()
            logger.info(f"Redis cache conectado: {REDIS_URL}")
        except Exception as e:
            logger.warning(f"Redis indisponível: {e}. Fallback para memory cache.")
    else:
        logger.info("Cache em memória inicializado")


def cache_get(query: str) -> dict | None:
    """Recupera resultado em cache para query normalizada.

    Returns:
        dict com {query_normalized, sources, cached_at, expires_at} ou None.
    """
    normalized = _normalize_query(query)
    query_hash = _hash_query(normalized)

    if BACKEND == "redis":
        return _redis_get(query_hash, normalized)
    elif BACKEND == "sqlite":
        return _sqlite_get(query_hash, normalized)
    else:
        return _memory_get(query_hash, normalized)


def cache_set(query: str, sources: list[dict]) -> None:
    """Persiste resultado em cache por 7 dias.

    Args:
        query: query original do usuário
        sources: array de fontes rankadas [{title, url, origin, tactical_score, ...}]
    """
    normalized = _normalize_query(query)
    query_hash = _hash_query(normalized)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=CACHE_TTL_DAYS)

    payload = {
        "query_normalized": normalized,
        "sources": sources,
        "cached_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    if BACKEND == "redis":
        _redis_set(query_hash, payload)
    elif BACKEND == "sqlite":
        _sqlite_set(query_hash, payload)
    else:
        _memory_set(query_hash, payload)


def cache_invalidate_team(team_name: str) -> None:
    """Invalida cache de todas as queries de um time específico."""
    if BACKEND == "redis":
        import redis
        client = redis.from_url(REDIS_URL)
        # Redis não suporta wildcard delete eficiente; em prod usar Redis Streams
        logger.info(f"Cache invalidate team {team_name}: manual cleanup recommended")
    elif BACKEND == "sqlite":
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute(
            "DELETE FROM tactical_search_cache WHERE query_normalized LIKE ?",
            (f"%{team_name}%",),
        )
        conn.commit()
        conn.close()
    logger.info(f"Cache invalidado para time: {team_name}")


def cache_prune_expired() -> int:
    """Remove entradas expiradas. Retorna count deletado."""
    if BACKEND == "sqlite":
        conn = sqlite3.connect(SQLITE_PATH)
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "DELETE FROM tactical_search_cache WHERE expires_at < ?",
            (now,),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(f"Cache prune: {deleted} entradas expiradas deletadas")
        return deleted
    elif BACKEND == "redis":
        # Redis TTL automático; nada a fazer
        return 0
    return 0


# ============================================================================
# Redis Backend
# ============================================================================

_redis_memory: dict[str, dict] = {}  # Fallback em memory se redis falhar


def _redis_get(query_hash: str, normalized: str) -> dict | None:
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True)
        data = client.get(query_hash)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Redis get falhou: {e}. Usando memory fallback.")
        return _redis_memory.get(query_hash)
    return None


def _redis_set(query_hash: str, payload: dict) -> None:
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True)
        client.setex(
            query_hash,
            CACHE_TTL_SECONDS,
            json.dumps(payload),
        )
    except Exception as e:
        logger.warning(f"Redis set falhou: {e}. Usando memory fallback.")
        _redis_memory[query_hash] = payload


# ============================================================================
# SQLite Backend
# ============================================================================

def _sqlite_get(query_hash: str, normalized: str) -> dict | None:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        cursor = conn.execute(
            "SELECT sources, cached_at, expires_at FROM tactical_search_cache WHERE query_hash = ?",
            (query_hash,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            sources, cached_at, expires_at = row
            # Validar TTL
            if datetime.fromisoformat(expires_at) > datetime.now(timezone.utc):
                return {
                    "query_normalized": normalized,
                    "sources": json.loads(sources),
                    "cached_at": cached_at,
                    "expires_at": expires_at,
                }
    except Exception as e:
        logger.warning(f"SQLite get falhou: {e}")
    return None


def _sqlite_set(query_hash: str, payload: dict) -> None:
    try:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.execute(
            """
            INSERT OR REPLACE INTO tactical_search_cache
            (query_hash, query_normalized, sources, cached_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                query_hash,
                payload["query_normalized"],
                json.dumps(payload["sources"]),
                payload["cached_at"],
                payload["expires_at"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"SQLite set falhou: {e}")


# ============================================================================
# Memory Backend (dev/test)
# ============================================================================

_memory_cache: dict[str, dict] = {}


def _memory_get(query_hash: str, normalized: str) -> dict | None:
    payload = _memory_cache.get(query_hash)
    if payload:
        # Validar TTL
        if datetime.fromisoformat(payload["expires_at"]) > datetime.now(timezone.utc):
            return payload
        else:
            del _memory_cache[query_hash]
    return None


def _memory_set(query_hash: str, payload: dict) -> None:
    _memory_cache[query_hash] = payload


# ============================================================================
# Utilities
# ============================================================================

def _normalize_query(query: str) -> str:
    """Normaliza query para comparação case-insensitive e trim."""
    return " ".join(query.strip().lower().split())


def _hash_query(normalized: str) -> str:
    """SHA256 hash para deduplicação e indexação."""
    return hashlib.sha256(normalized.encode()).hexdigest()
