"""Phase 2.4: Trending + Recency Scoring para Tactical Search Hub.

Análise de tendência de views, bônus por recência, e scoring de autoridade.

Funcionalidades:
- Parse de metadata de views (1.2M, 500K, etc)
- Detecção de canais verificados
- Cálculo de recência (dias desde publicação)
- Scoring de trending baseado em taxa de crescimento
- Integração com ranking tático existente
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class RecencyScorer:
    """Scoring baseado em recência e tendência de views."""

    # Pesos para componentes de recência
    DEFAULT_WEIGHTS = {
        "recency": 0.35,          # Quão recente é o vídeo
        "view_trend": 0.25,       # Taxa de crescimento de views
        "absolute_views": 0.20,   # Volume absoluto de views
        "authority": 0.20,        # Verificação, autoridade de canal
    }

    def __init__(self, weights: dict | None = None):
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        # Normalizar pesos
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def score(self, source: dict, reference_date: datetime | None = None) -> float:
        """Calcula score de recência (0-10).

        Args:
            source: Fonte com metadata (published, views, channel_verified, etc)
            reference_date: Data de referência (default: agora)

        Returns:
            Score 0-10
        """
        if reference_date is None:
            reference_date = datetime.now(timezone.utc)

        scores = {}

        # Componente 1: Recência
        scores["recency"] = self._score_recency(source.get("published"), reference_date)

        # Componente 2: Tendência de views
        scores["view_trend"] = self._score_view_trend(
            source.get("views"),
            source.get("published"),
            reference_date,
        )

        # Componente 3: Volume absoluto
        scores["absolute_views"] = self._score_absolute_views(source.get("views"))

        # Componente 4: Autoridade
        scores["authority"] = self._score_authority(source)

        # Agregação ponderada
        total_score = sum(
            scores.get(key, 0) * self.weights.get(key, 0)
            for key in self.weights.keys()
        )

        return min(10.0, max(0.0, total_score))

    def _score_recency(self, published: str | None, reference_date: datetime) -> float:
        """Score de recência (0-10).

        - Hoje: 10.0
        - Semana passada: 8.0
        - Mês passado: 6.0
        - 3 meses atrás: 4.0
        - 6 meses atrás: 2.0
        - Older: 1.0
        """
        if not published:
            return 5.0  # Neutral se desconhecido

        try:
            pub_date = self._parse_published_date(published)
            if not pub_date:
                return 5.0
        except Exception:
            return 5.0

        days_ago = (reference_date - pub_date).days

        if days_ago <= 1:
            return 10.0
        elif days_ago <= 7:
            return 8.0 - (days_ago - 1) * 0.3  # Linear decay over week
        elif days_ago <= 30:
            return 6.0 - (days_ago - 7) * 0.05  # Slower decay over month
        elif days_ago <= 90:
            return 4.0 - (days_ago - 30) * 0.03  # Slower over 3 months
        elif days_ago <= 180:
            return 2.0 - (days_ago - 90) * 0.01  # Minimal impact after 3 months
        else:
            return 1.0

    def _score_view_trend(
        self,
        views: str | int | None,
        published: str | None,
        reference_date: datetime,
    ) -> float:
        """Score de tendência de views (0-10).

        Calcula views por dia como proxy de crescimento.

        - 1000+ views/dia: 10.0
        - 500-1000 views/dia: 8.0
        - 100-500 views/dia: 6.0
        - 10-100 views/dia: 4.0
        - <10 views/dia: 2.0
        """
        if not views or not published:
            return 5.0  # Neutral

        try:
            view_count = self._parse_view_count(views)
            pub_date = self._parse_published_date(published)
            if not view_count or not pub_date:
                return 5.0
        except Exception:
            return 5.0

        days_old = max(1, (reference_date - pub_date).days)
        views_per_day = view_count / days_old

        if views_per_day >= 1000:
            return 10.0
        elif views_per_day >= 500:
            return 8.0
        elif views_per_day >= 100:
            return 6.0
        elif views_per_day >= 10:
            return 4.0
        else:
            return 2.0

    def _score_absolute_views(self, views: str | int | None) -> float:
        """Score por volume absoluto de views (0-10).

        - 1M+: 10.0
        - 500K-1M: 9.0
        - 100K-500K: 8.0
        - 50K-100K: 6.0
        - 10K-50K: 4.0
        - 1K-10K: 2.0
        - <1K: 1.0
        """
        if not views:
            return 5.0

        try:
            view_count = self._parse_view_count(views)
            if not view_count:
                return 5.0
        except Exception:
            return 5.0

        if view_count >= 1_000_000:
            return 10.0
        elif view_count >= 500_000:
            return 9.0
        elif view_count >= 100_000:
            return 8.0
        elif view_count >= 50_000:
            return 6.0
        elif view_count >= 10_000:
            return 4.0
        elif view_count >= 1_000:
            return 2.0
        else:
            return 1.0

    def _score_authority(self, source: dict) -> float:
        """Score de autoridade do canal (0-10).

        - Canal verificado: +2.0
        - Fonte oficial (Wikipedia, TheSportsDB): +3.0
        - Canal com 100K+ subscribers: +1.0
        """
        score = 5.0  # Base neutral

        # Verificação do canal
        if source.get("channel_verified"):
            score += 2.0

        # Fontes oficiais
        origin = (source.get("origin") or "").lower()
        if "wikipedia" in origin or "thesportsdb" in origin:
            score += 3.0
        elif "official" in origin or "oficial" in origin:
            score += 2.0

        # Subscribers (se disponível)
        subscribers = source.get("channel_subscribers")
        if subscribers:
            try:
                sub_count = self._parse_view_count(str(subscribers))
                if sub_count >= 100_000:
                    score += 1.0
            except Exception:
                pass

        return min(10.0, score)

    @staticmethod
    def _parse_view_count(views: str | int | None) -> int | None:
        """Parse view count como integer.

        Suporta: "1.2M", "500K", "1234567", 1234567, etc
        """
        if views is None or views == "":
            return None

        if isinstance(views, int):
            return max(0, views)

        views_str = str(views).strip().upper()

        # Remover "views" e vírgulas
        views_str = views_str.replace("VIEWS", "").replace(",", "").strip()

        # Sufixos
        if views_str.endswith("M"):
            try:
                return int(float(views_str[:-1]) * 1_000_000)
            except (ValueError, IndexError):
                return None
        elif views_str.endswith("K"):
            try:
                return int(float(views_str[:-1]) * 1_000)
            except (ValueError, IndexError):
                return None
        else:
            try:
                return int(float(views_str))
            except ValueError:
                return None

    @staticmethod
    def _parse_published_date(published: str | None) -> datetime | None:
        """Parse published date em ISO format, relative strings, etc.

        Suporta:
        - ISO format: "2024-01-15T10:30:00Z"
        - Relative: "1 week ago", "3 days ago", "2 months ago"
        - Numeric: "7" (dias atrás), "-7" (dias atrás)
        """
        if not published:
            return None

        published = str(published).strip()

        # ISO format
        try:
            if "T" in published:
                # Remove Z se presente
                if published.endswith("Z"):
                    published = published[:-1] + "+00:00"
                return datetime.fromisoformat(published)
        except ValueError:
            pass

        # Relative format: "X days ago", "X weeks ago", "X months ago"
        relative_match = re.match(
            r"(\d+)\s+(day|week|month|year)s?\s+ago",
            published,
            re.IGNORECASE,
        )
        if relative_match:
            count = int(relative_match.group(1))
            unit = relative_match.group(2).lower()

            now = datetime.now(timezone.utc)
            if unit == "day":
                return now - timedelta(days=count)
            elif unit == "week":
                return now - timedelta(weeks=count)
            elif unit == "month":
                return now - timedelta(days=count * 30)  # Aproximado
            elif unit == "year":
                return now - timedelta(days=count * 365)

        # Numeric: "7" ou "-7"
        try:
            days_ago = int(published)
            return datetime.now(timezone.utc) - timedelta(days=abs(days_ago))
        except ValueError:
            pass

        return None


def apply_recency_bonus(source: dict, score: float | None = None) -> dict:
    """Aplica scoring de recência a uma fonte.

    Args:
        source: Fonte original
        score: Score existente (optional)

    Returns:
        Fonte com campos adicionados
    """
    scorer = RecencyScorer()
    recency_score = scorer.score(source)

    return {
        **source,
        "recency_score": round(recency_score, 2),
        "recency_components": {
            "recency": round(scorer._score_recency(source.get("published"), datetime.now(timezone.utc)), 2),
            "view_trend": round(scorer._score_view_trend(source.get("views"), source.get("published"), datetime.now(timezone.utc)), 2),
            "absolute_views": round(scorer._score_absolute_views(source.get("views")), 2),
            "authority": round(scorer._score_authority(source), 2),
        },
    }


def boost_tactical_score_with_recency(
    source: dict,
    tactical_score: float,
    recency_weight: float = 0.20,
) -> dict:
    """Combina score tático com recência.

    Fórmula: (0.8 * tactical_score) + (0.2 * recency_score)

    Args:
        source: Fonte com scores
        tactical_score: Score tático original (0-10)
        recency_weight: Peso da recência (default 0.20 = 20%)

    Returns:
        Fonte com score combinado
    """
    scorer = RecencyScorer()
    recency_score = scorer.score(source)

    tactical_weight = 1.0 - recency_weight
    combined = (tactical_weight * tactical_score) + (recency_weight * recency_score)

    return {
        **source,
        "tactical_score": round(tactical_score, 2),
        "recency_score": round(recency_score, 2),
        "combined_score": round(min(10.0, combined), 2),
    }


# ============================================================================
# Export API
# ============================================================================

__all__ = [
    "RecencyScorer",
    "apply_recency_bonus",
    "boost_tactical_score_with_recency",
]
