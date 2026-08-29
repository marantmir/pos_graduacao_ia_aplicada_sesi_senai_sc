"""Validação de qualidade e utilidade de vídeos.

Pontos de validação:
1. Duração (skip shorts <3min; priorizar completos >40min)
2. Resolução (prefer ≥720p)
3. Tipo de conteúdo (match vs analysis)
4. Autoridade da fonte (canais verificados YouTube)
5. Recência (videos recentes são preferidos)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# ============================================================================
# Parsing de Duração (YouTube, Vimeo, etc)
# ============================================================================

DURATION_PATTERNS = {
    # "5h 23m 12s"
    "long_form": r'(\d+)\s*h(?:ours?)?\s*(\d+)\s*m(?:in)?(?:utes?)?\s*(\d+)?\s*s(?:ec)?(?:onds?)?',
    # "23m 12s" or just "45m"
    "medium": r'(\d+)\s*m(?:in)?(?:utes?)?\s*(?:(\d+)\s*s(?:ec)?(?:onds?)?)?',
    # "5:23:12" or "23:12"
    "timestamp": r'(\d+):(\d+)(?::(\d+))?',
}


def parse_duration_to_seconds(duration_str: str) -> int | None:
    """Converte string de duração para segundos.

    Formatos suportados:
    - "5h 23m 12s" → 19392
    - "23m 12s" → 1392
    - "45m" → 2700
    - "5:23:12" → 19392
    - "23:12" → 1392
    - "5400" (segundos diretos) → 5400
    """
    if not duration_str:
        return None

    cleaned = duration_str.strip()

    # Tenta parsing numérico direto (segundos)
    try:
        return int(cleaned)
    except ValueError:
        pass

    # Tenta long_form PRIMEIRO ("5h 23m 12s")
    match = re.search(DURATION_PATTERNS["long_form"], cleaned)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    # Tenta medium ("23m 12s" ou "45m")
    match = re.search(DURATION_PATTERNS["medium"], cleaned)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2) or 0)
        return minutes * 60 + seconds

    # Tenta timestamp ("5:23:12" ou "23:12") POR ÚLTIMO
    match = re.search(DURATION_PATTERNS["timestamp"], cleaned)
    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        third = match.group(3)

        # Heuristic: if third component exists, must be hh:mm:ss
        if third is not None:
            return first * 3600 + second * 60 + int(third)
        # If only two components: first >= 60 is hh:mm, else mm:ss
        elif first >= 60:
            return first * 3600 + second * 60
        else:
            return first * 60 + second

    return None


# ============================================================================
# Validação de Qualidade de Vídeo
# ============================================================================

class VideoQualityScore:
    """Calcula score 0-10 de qualidade/utilidade de vídeo."""

    def __init__(
        self,
        duration_seconds: int | None = None,
        resolution: str | None = None,
        is_verified_channel: bool = False,
        published_at: str | None = None,
        view_count: int | None = None,
        content_type: str = "unknown",  # "match", "analysis", "unknown"
    ):
        self.duration_seconds = duration_seconds or 0
        self.resolution = resolution
        self.is_verified_channel = is_verified_channel
        self.published_at = published_at
        self.view_count = view_count or 0
        self.content_type = content_type

    def calculate(self) -> tuple[float, str]:
        """Calcula score 0-10 e retorna (score, reason).

        Critérios:
        - Duração: shorts (<3min) = 0; completos (>40min) = 10; análises (10-40min) = 8
        - Resolução: <480p = 2; 480-720p = 6; ≥1080p = 10
        - Canal verificado: +1.5 pontos
        - Recência: <1 semana = +1; <1 mês = +0.5
        - Views/autoridade: alto engajamento = +0.5
        """
        # Weighted average em vez de additive
        scores = []
        weights = []

        # Duração (40% do score)
        duration_score = self._score_duration()
        scores.append(duration_score)
        weights.append(0.40)

        # Resolução (25% do score)
        if self.resolution:
            resolution_score = self._score_resolution()
            scores.append(resolution_score)
            weights.append(0.25)
        else:
            weights.append(0.25)
            scores.append(5.0)  # Neutral

        # Canal verificado (5% bonus)
        verified_bonus = 1.5 if self.is_verified_channel else 0.0

        # Recência (15% do score com bonus)
        recency_score = self._score_recency() if self.published_at else 0.0

        # Views/autoridade (15% do score)
        authority_score = self._score_authority() if self.view_count else 0.0

        # Calcular weighted average base
        if weights:
            base_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights[:len(scores)])
        else:
            base_score = 5.0

        # Add bonuses (max 3 pontos)
        total_bonus = min(3.0, verified_bonus + recency_score + authority_score)
        final_score = base_score + total_bonus

        # Clamp 0-10
        final_score = max(0.0, min(10.0, final_score))

        reasons = [
            f"duration:{duration_score:.1f}",
            f"resolution:{self._score_resolution():.1f}" if self.resolution else "resolution:5.0",
            f"bonus:{total_bonus:.1f}",
        ]
        reason = " | ".join(reasons)

        return (round(final_score, 1), reason)

    def _score_duration(self) -> float:
        """Score 0-10 baseado em duração."""
        seconds = self.duration_seconds

        if seconds < 180:  # <3min: short form inútil
            return 0.5
        elif seconds < 600:  # 3-10min: pequeno, mas pode ser análise
            return 6.0
        elif seconds < 2400:  # 10-40min: análise típica
            return 8.5
        elif seconds < 2700:  # 40-45min: jogo completo ideal
            return 10.0
        else:  # >45min: completo mas pode ser com intervalo
            return 9.5

    def _score_resolution(self) -> float:
        """Score 0-10 baseado em resolução."""
        if not self.resolution:
            return 5.0

        res = self.resolution.lower()

        # Extract pixel count
        if "2160p" in res or "4k" in res:
            return 10.0
        elif "1440p" in res:
            return 10.0
        elif "1080p" in res:
            return 10.0
        elif "720p" in res:
            return 7.0
        elif "480p" in res:
            return 4.0
        elif "360p" in res:
            return 2.0
        else:
            return 5.0

    def _score_recency(self) -> float:
        """Score 0-1 baseado em recência (bonus)."""
        if not self.published_at:
            return 0.0

        try:
            published = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - published

            if age < timedelta(days=7):
                return 1.0  # <1 semana: bonus máximo
            elif age < timedelta(days=30):
                return 0.5  # <1 mês: meio bonus
            elif age < timedelta(days=365):
                return 0.2  # <1 ano: pequeno bonus
            else:
                return 0.0  # muito antigo
        except Exception:
            return 0.0

    def _score_authority(self) -> float:
        """Score 0-0.5 baseado em views/engajamento."""
        if self.view_count is None:
            return 0.0

        # Heuristic: >100k views = autoridade alta
        if self.view_count >= 100_000:
            return 0.5
        elif self.view_count >= 10_000:
            return 0.3
        elif self.view_count >= 1_000:
            return 0.1
        else:
            return 0.0


def validate_youtube_video(video: dict) -> dict:
    """Valida e enriquece vídeo YouTube com quality scores.

    Input: {id, title, url, channel, duration, published, views}
    Output: adiciona {quality_score, reason, video_seconds}
    """
    duration_seconds = parse_duration_to_seconds(video.get("duration") or "")
    views = _parse_view_count(video.get("views"))

    # Best-effort: detectar se é match (jogo) vs análise
    title_lower = video.get("title", "").lower()
    content_type = "analysis" if any(kw in title_lower for kw in ["análise", "tática", "scout", "comentário"]) else "match"

    validator = VideoQualityScore(
        duration_seconds=duration_seconds,
        resolution=_extract_resolution(video.get("title", "")),
        is_verified_channel=False,  # TODO: integrar com YouTube API
        published_at=video.get("published"),
        view_count=views,
        content_type=content_type,
    )

    score, reason = validator.calculate()

    return {
        **video,
        "quality_score": score,
        "quality_reason": reason,
        "video_seconds": duration_seconds,
        "content_type": content_type,
    }


def validate_source(source: dict) -> dict:
    """Valida source genérica (pode ser vídeo ou artigo).

    Se for vídeo YouTube, aplica validação específica.
    """
    if source.get("origin") == "YouTube":
        return validate_youtube_video(source)

    # Para sources genéricos: score estático baseado em categoria
    category = source.get("category", "team_form")
    if category == "match_videos":
        base_score = 8.0
    elif category == "analysis_videos":
        base_score = 8.5
    else:  # team_form
        base_score = 6.0

    return {
        **source,
        "quality_score": base_score,
        "quality_reason": f"category:{category}",
    }


# ============================================================================
# Utilities
# ============================================================================

def _parse_view_count(views_str: str | None) -> int | None:
    """Converte "1.2M", "500K", "3.5B" para inteiro."""
    if not views_str:
        return None

    cleaned = views_str.strip().lower().replace(",", "").replace(".", "")

    # "1.2M" → "12M"
    if "m" in cleaned:
        num = float(cleaned.replace("m", ""))
        return int(num * 1_000_000)
    elif "k" in cleaned:
        num = float(cleaned.replace("k", ""))
        return int(num * 1_000)
    elif "b" in cleaned:
        num = float(cleaned.replace("b", ""))
        return int(num * 1_000_000_000)
    else:
        try:
            return int(cleaned)
        except ValueError:
            return None


def _extract_resolution(text: str) -> str | None:
    """Extrai resolução de texto (ex: "Jogo completo 1080p" → "1080p")."""
    match = re.search(r'\b(4k|2160p|1440p|1080p|720p|480p|360p)\b', text.lower())
    return match.group(1) if match else None
