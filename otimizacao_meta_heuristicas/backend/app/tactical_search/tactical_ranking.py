"""Ranking inteligente de fontes por relevância tática.

Score final é weighted average de:
1. Tactical relevance (título + descrição): 40%
2. Quality score (duração, resolução): 25%
3. Authority score (canal verificado, views): 20%
4. Category match (match_videos vs analysis_videos): 15%

Cada fonte retorna score 0-10 + explanation.
"""
from __future__ import annotations

from .tactical_keywords import (
    detect_language,
    extract_formation,
    get_tactical_focus,
    get_tactical_keywords,
    measure_tactical_relevance,
    parse_formation,
)

# ============================================================================
# Ranking Engine
# ============================================================================


class TacticalRanker:
    """Orquestrador de ranking com configurações customizáveis."""

    def __init__(
        self,
        tactical_weight: float = 0.45,
        quality_weight: float = 0.20,
        authority_weight: float = 0.20,
        category_weight: float = 0.15,
    ):
        # Validar pesos somam 1.0
        total = tactical_weight + quality_weight + authority_weight + category_weight
        assert abs(total - 1.0) < 0.01, f"Pesos devem somar 1.0, got {total}"

        self.tactical_weight = tactical_weight
        self.quality_weight = quality_weight
        self.authority_weight = authority_weight
        self.category_weight = category_weight

    def rank_sources(
        self,
        sources: list[dict],
        query: str | None = None,
        target_formation: str | None = None,
    ) -> list[dict]:
        """Rankeia sources e retorna ordenadas por score descending."""
        ranked = []
        for source in sources:
            score, explanation = self.score_source(source, query, target_formation)
            ranked.append({
                **source,
                "tactical_score": score,
                "ranking_reason": explanation,
            })

        # Sort by tactical_score DESC
        ranked.sort(key=lambda x: x["tactical_score"], reverse=True)
        return ranked

    def score_source(
        self,
        source: dict,
        query: str | None = None,
        target_formation: str | None = None,
    ) -> tuple[float, str]:
        """Calcula score 0-10 para uma source.

        Returns: (score, explanation)
        """
        title = source.get("title", "")
        summary = source.get("summary", "")
        category = source.get("category", "team_form")

        # Detecta idioma da query
        language = detect_language(query or "")

        # Scores parciais
        tactical_score = self._score_tactical_relevance(
            title, summary, query, target_formation, language
        )
        quality_score = source.get("quality_score", 5.0)
        authority_score = self._score_authority(source)
        category_score = self._score_category(category)

        # Weighted average
        final_score = (
            tactical_score * self.tactical_weight
            + quality_score * self.quality_weight
            + authority_score * self.authority_weight
            + category_score * self.category_weight
        )

        final_score = max(0.0, min(10.0, final_score))

        explanation = self._build_explanation(
            tactical_score,
            quality_score,
            authority_score,
            category_score,
            final_score,
            category,
        )

        return (round(final_score, 1), explanation)

    def _score_tactical_relevance(
        self,
        title: str,
        summary: str,
        query: str | None,
        target_formation: str | None,
        language: str,
    ) -> float:
        """Score 0-10 baseado em relevância tática.

        Critérios:
        1. Keyword match (defensivo, ofensivo, bola parada, análise)
        2. Formação match (se query mencionar formação)
        3. Comprimento de matches (mais matches = mais relevante)
        """
        combined_text = f"{title} {summary}".lower()
        keywords = get_tactical_keywords(language)

        # Measure by category
        relevance_scores = measure_tactical_relevance(combined_text, language)
        base_score = sum(relevance_scores.values()) / 4 * 10  # Average 0-10

        # Bonus: formação match
        if target_formation:
            if target_formation in combined_text:
                base_score = min(10.0, base_score + 2.0)

        # Bonus: múltiplas categorias táticas
        focus_areas = get_tactical_focus(combined_text, language)
        if len(focus_areas) >= 2:
            base_score = min(10.0, base_score + 1.0)

        return base_score

    def _score_authority(self, source: dict) -> float:
        """Score 0-10 baseado em autoridade da fonte.

        Critérios:
        1. Canal verificado (YouTube)
        2. Views altas (1M+ = 10)
        3. Origem confiável (Wikipedia, TheSportsDB = 9)
        """
        origin = source.get("origin", "")
        is_verified = source.get("is_verified_channel", False)
        views = source.get("view_count", 0) or 0

        base = 5.0

        if origin == "Wikipedia":
            base = 9.0
        elif origin == "TheSportsDB":
            base = 8.5
        elif origin == "YouTube":
            base = 6.0
            if is_verified:
                base += 2.0
            if views >= 1_000_000:
                base = min(10.0, base + 2.0)
            elif views >= 100_000:
                base = min(10.0, base + 1.0)

        return base

    def _score_category(self, category: str) -> float:
        """Score 0-10 baseado em categoria.

        match_videos = 9 (jogo real é ouro)
        analysis_videos = 8.5 (análise é premium)
        team_form = 6 (informação contextual)
        other = 5
        """
        if category == "match_videos":
            return 9.0
        elif category == "analysis_videos":
            return 8.5
        elif category == "team_form":
            return 6.0
        else:
            return 5.0

    def _build_explanation(
        self,
        tactical: float,
        quality: float,
        authority: float,
        category: float,
        final: float,
        category_type: str,
    ) -> str:
        """Constrói explicação human-readable do score."""
        parts = [
            f"tactical:{tactical:.1f}",
            f"quality:{quality:.1f}",
            f"authority:{authority:.1f}",
            f"category:{category:.1f}",
        ]

        if final >= 9.0:
            summary = "Excelente relevância tática"
        elif final >= 7.5:
            summary = "Boa relevância e qualidade"
        elif final >= 6.0:
            summary = "Relevância moderada"
        elif final >= 4.0:
            summary = "Relevância limitada"
        else:
            summary = "Baixa relevância"

        return f"{summary} ({' | '.join(parts)})"


# ============================================================================
# Helpers
# ============================================================================

def rank_sources(
    sources: list[dict],
    query: str | None = None,
    target_formation: str | None = None,
) -> list[dict]:
    """Convenience function com default ranker."""
    ranker = TacticalRanker()
    return ranker.rank_sources(sources, query, target_formation)


def score_source(
    source: dict,
    query: str | None = None,
    target_formation: str | None = None,
) -> tuple[float, str]:
    """Convenience function com default ranker."""
    ranker = TacticalRanker()
    return ranker.score_source(source, query, target_formation)
