"""Busca de vídeos no YouTube sem chave de API, com retry exponencial.

A página pública de resultados do YouTube embute um JSON (ytInitialData) com
título, canal, duração, data e visualizações de cada vídeo. Este módulo lê
esse JSON e devolve um catálogo estruturado de vídeos reais - título, link,
canal e duração - para o analista revisar, escolher o trecho certo e subir no
pipeline de visão computacional.

Importante: nenhum vídeo é baixado automaticamente (isso violaria os Termos
de Serviço do YouTube). O objetivo é eliminar a etapa manual de "procurar o
vídeo certo", entregando resultados reais em vez de apenas links de busca.
"""
from __future__ import annotations

import json
import logging
import urllib.parse

from .tactical_search.retry_policy import retry_with_backoff
from .web_search import fetch_page

logger = logging.getLogger(__name__)


MAX_RESULTS = 8


@retry_with_backoff(max_attempts=2, base_delay=1.0, max_delay=4.0, jitter=True)
def search_youtube_videos(query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Devolve vídeos reais do YouTube para a consulta: [{title, url, channel,
    duration, published, views}]. Lança exceção em falha de rede/parse - o
    chamador trata como best-effort.

    Com retry exponencial: falhas temporárias em bloqueios de rate limit
    são recuperadas automaticamente.
    """
    encoded = urllib.parse.quote(query)
    page = fetch_page(f"https://www.youtube.com/results?search_query={encoded}&hl=pt")
    data = _extract_yt_initial_data(page)
    videos = []
    seen_ids: set[str] = set()
    for renderer in _walk_video_renderers(data):
        video = _video_from_renderer(renderer)
        if not video or video["id"] in seen_ids:
            continue
        seen_ids.add(video["id"])
        videos.append(video)
        if len(videos) >= limit:
            break
    return videos


def _extract_yt_initial_data(page: str) -> dict:
    marker = "ytInitialData"
    start = page.find(marker)
    if start == -1:
        raise ValueError("Pagina de resultados sem ytInitialData.")
    brace = page.find("{", start)
    if brace == -1:
        raise ValueError("JSON de resultados nao encontrado.")
    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(page[brace:])
    return data


def _walk_video_renderers(node):
    if isinstance(node, dict):
        renderer = node.get("videoRenderer")
        if isinstance(renderer, dict) and renderer.get("videoId"):
            yield renderer
        for value in node.values():
            yield from _walk_video_renderers(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_video_renderers(item)


def _video_from_renderer(renderer: dict) -> dict | None:
    video_id = renderer.get("videoId")
    title = _runs_text(renderer.get("title")) or _simple_text(renderer.get("title"))
    if not video_id or not title:
        return None
    return {
        "id": video_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": _runs_text(renderer.get("ownerText")) or _runs_text(renderer.get("longBylineText")),
        "duration": _simple_text(renderer.get("lengthText")),
        "published": _simple_text(renderer.get("publishedTimeText")),
        "views": _simple_text(renderer.get("viewCountText")) or _simple_text(renderer.get("shortViewCountText")),
    }


def _runs_text(node) -> str:
    if not isinstance(node, dict):
        return ""
    runs = node.get("runs")
    if not isinstance(runs, list):
        return ""
    return " ".join(str(run.get("text", "")) for run in runs if isinstance(run, dict)).strip()


def _simple_text(node) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("simpleText", "")).strip()
