"""Minimal in-memory rate limiter (fixed window per client key).

No external dependency: the app runs as a single Uvicorn process, so a
per-process in-memory window is enough to blunt brute-force/abuse on the
costly video-vision upload routes without pulling in slowapi/redis.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._hits.clear()

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            retry_after = max(1, round(self.window_seconds - (now - hits[0])))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Limite de {self.max_requests} requisicoes a cada "
                    f"{int(self.window_seconds)}s excedido. Tente novamente em instantes."
                ),
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)


def _client_key(request: Request) -> str:
    # Atras de um proxy/load balancer (ex.: Render), request.client.host e o
    # IP do proxy - todos os usuarios cairiam na MESMA janela de rate limit.
    # Com FOOTBALL_INTEL_TRUST_PROXY=1 no deploy, usa o primeiro IP de X-Forwarded-For
    # (o cliente real). Fica desligado por padrao porque, com o app exposto
    # diretamente, o header e forjavel e permitiria burlar o limite.
    if os.getenv("FOOTBALL_INTEL_TRUST_PROXY", "").strip() in {"1", "true", "yes"}:
        forwarded = request.headers.get("X-Forwarded-For", "")
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    if request.client:
        return request.client.host
    return "unknown"


VIDEO_UPLOAD_MAX_REQUESTS = int(os.getenv("VIDEO_UPLOAD_RATE_LIMIT", "6"))
VIDEO_UPLOAD_WINDOW_SECONDS = float(os.getenv("VIDEO_UPLOAD_RATE_WINDOW_SECONDS", "300"))

video_upload_rate_limiter = RateLimiter(VIDEO_UPLOAD_MAX_REQUESTS, VIDEO_UPLOAD_WINDOW_SECONDS)


def enforce_video_upload_rate_limit(request: Request) -> None:
    video_upload_rate_limiter.check(_client_key(request))
