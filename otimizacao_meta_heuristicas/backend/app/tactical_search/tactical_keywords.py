"""Dicionários temáticos multi-idioma para reconhecimento de padrões táticos.

Suporta:
- PT-BR (português brasileiro)
- ES (español)
- EN (english)

Cada padrão tem keywords que indicam relevância tática:
1. Formação (4-3-3, 5-2-3, etc)
2. Defensivo (pressão, compactação, marcação)
3. Ofensivo (transição, progressão, criação)
4. Bola parada (escanteio, falta, cobrança)
5. Análise/Scout (tática, análise, como joga)
"""
from __future__ import annotations

import re
from typing import Literal

Language = Literal["pt-br", "es", "en"]


# ============================================================================
# Reconhecimento de Formações (4-3-3, 5-2-3, etc)
# ============================================================================

FORMATION_PATTERN = r'\b([3-5])-([1-4])-([1-3])\b'  # Match 4-3-3, 5-2-3, etc


def extract_formation(query: str) -> str | None:
    """Extrai formação da query (ex: "Flamengo 4-3-3 pressão" → "4-3-3")."""
    match = re.search(FORMATION_PATTERN, query)
    return match.group(0) if match else None


def parse_formation(formation: str) -> dict | None:
    """Parse formação em linhas defensivas/médias/ofensivas.

    Ex: "4-3-3" → {defense: 4, midfield: 3, attack: 3}
    """
    match = re.match(FORMATION_PATTERN, formation)
    if not match:
        return None
    return {
        "defense": int(match.group(1)),
        "midfield": int(match.group(2)),
        "attack": int(match.group(3)),
        "original": formation,
    }


# ============================================================================
# Dicionários Táticos Multi-Idioma
# ============================================================================

TACTICAL_KEYWORDS: dict[Language, dict[str, list[str]]] = {
    "pt-br": {
        "defensive": [
            "pressão", "pressão alta", "marcação", "compactação", "defesa",
            "zagueiro", "lateral", "volante", "proteção", "cobertura",
            "recomposição", "contrapressão", "bloqueio", "interceptação",
            "linha defensiva", "defensivo", "consolidação", "desarmador",
            "libero", "marcador", "ala defensivo", "lateral defensivo",
            "defesa de zona", "defesa por homem", "fechamento de espaços",
            "segurança defensiva", "bola fora", "afastamento", "tática defensiva",
        ],
        "offensive": [
            "ataque", "transição", "progressão", "criação", "finalização",
            "construção", "saída de bola", "toque curto", "combinação",
            "ala ofensivo", "meia ofensivo", "atacante", "ponta",
            "extremo", "ofensivo", "impulsionador", "desmarque",
            "infiltração", "profundidade", "terço final", "último terço",
            "chute", "remate", "cobrança", "velocidade de transição",
            "jogo direto", "jogo posicional", "abertura lateral", "cruzamento",
            "tabela", "combinação rápida", "contra-ataque", "amplitude",
        ],
        "set_pieces": [
            "bola parada", "escanteio", "falta", "cobrança", "lançamento",
            "cruzamento", "cabeceio", "marcação em bola parada",
            "tiro de meta", "arremesso", "livre", "pênalti",
            "set play", "bola inativa", "levantamento", "jogada ensaiada",
        ],
        "analysis": [
            "análise", "tática", "como joga", "modelo de jogo",
            "scout", "scouting", "performance", "padrão",
            "comportamento", "comportamental", "estudo", "revisão",
            "tendência", "estratégia", "estratégico", "leitura", "interpretação",
        ],
        "formation": [
            "4-3-3", "4-2-3-1", "3-5-2", "5-3-2", "3-4-3", "4-1-4-1",
            "5-4-1", "4-4-2", "3-1-4-2", "formação", "posicionamento",
            "linha defensiva", "linha média", "linha de ataque",
        ],
        "players": [
            "jogador", "jogadores", "número", "camisa", "posição",
            "zagueiro", "lateral-esquerdo", "lateral-direito", "goleiro",
            "volante", "meia", "meia-atacante", "ponta-esquerda", "ponta-direita",
            "centroavante", "atacante", "punta", "ala", "meia-campo",
            "rastreamento", "identificação", "desempenho individual",
        ],
        "performance": [
            "performance", "desempenho", "velocidade", "resistência", "precisão",
            "intensidade", "concentração", "leitura de jogo", "timing",
            "passes completados", "passes errados", "posse de bola",
            "agilidade", "força", "mobilidade", "dinâmica", "agressividade",
            "cobertura", "recuperação", "interceptação", "finalização",
        ],
    },
    "es": {
        "defensive": [
            "presión", "marcaje", "defensa", "defensivo", "cobertura",
            "compactación", "recomposición", "contraataque", "bloqueo",
            "zaguero", "lateral", "volante", "protección", "consolidación",
            "marca personal", "presión alta", "defensa de zona", "línea defensiva",
            "defensa por zonas", "cierre de espacios", "recuperación",
        ],
        "offensive": [
            "ataque", "ofensiva", "ofensivo", "transición", "progresión",
            "creación", "finalización", "construcción", "salida de balón",
            "tocatoque", "combinación", "extremo", "mediapunta", "delantero",
            "profundidad", "desmarque", "infiltración", "tercio final",
            "último tercio", "remate", "gol", "oportunidad", "juego rápido",
            "amplitud", "contraataque rápido",
        ],
        "set_pieces": [
            "balón parado", "córner", "falta", "lanzamiento", "saque",
            "cruce", "cabeceo", "tiro libre", "penalti", "marca en balón parado",
            "jugada ensayada", "estrategia de balón parado",
        ],
        "analysis": [
            "análisis", "táctica", "táctico", "como juega", "modelo de juego",
            "scout", "scouting", "performance", "patrón", "comportamiento",
            "estudio", "revisión", "tendencia", "estrategia", "estratégico",
            "lectura", "interpretación", "análisis táctico",
        ],
        "formation": [
            "4-3-3", "4-2-3-1", "3-5-2", "5-3-2", "3-4-3", "4-1-4-1",
            "5-4-1", "4-4-2", "3-1-4-2", "formación", "posicionamiento",
            "línea defensiva", "línea media", "línea de ataque",
        ],
        "players": [
            "jugador", "jugadores", "número", "camiseta", "posición",
            "zaguero", "lateral-izquierdo", "lateral-derecho", "portero",
            "volante", "mediocampista", "media", "delantero",
            "rastreo", "identificación", "desempeño individual",
        ],
        "performance": [
            "rendimiento", "desempeño", "velocidad", "resistencia", "precisión",
            "intensidad", "concentración", "lectura de juego",
            "pases completados", "pases errados", "posesión",
            "agilidad", "fuerza", "movilidad", "dinámica", "agresividad",
        ],
    },
    "en": {
        "defensive": [
            "pressure", "high press", "marking", "defense", "defensive",
            "coverage", "compaction", "recomposition", "counter", "block",
            "center-back", "fullback", "midfielder", "protection", "consolidation",
            "man-marking", "zonal defense", "defensive line", "tackle",
            "interception", "clearance", "goalkeeper", "back line",
            "defensive shape", "space closing", "recovery",
        ],
        "offensive": [
            "attack", "offensive", "transition", "progression", "creation",
            "finishing", "build-up", "possession", "short pass", "combination",
            "winger", "playmaker", "striker", "forward", "depth",
            "positioning", "run", "final third", "penetration", "shot",
            "chance", "space", "width", "diagonal", "overlap", "quick play",
            "direct play", "width play", "counter-attack",
        ],
        "set_pieces": [
            "set piece", "corner", "free kick", "throw-in", "cross",
            "header", "dead ball", "penalty", "direct kick", "kick off",
            "set play", "ball in play", "restart", "set-play routine",
        ],
        "analysis": [
            "analysis", "tactical", "tactics", "how they play", "playing style",
            "scout", "scouting", "performance", "pattern", "behavior",
            "study", "review", "trend", "strategy", "strategic",
            "reading", "interpretation", "tactical analysis", "game model",
        ],
        "formation": [
            "4-3-3", "4-2-3-1", "3-5-2", "5-3-2", "3-4-3", "4-1-4-1",
            "5-4-1", "4-4-2", "3-1-4-2", "formation", "positioning",
            "defensive line", "midfield line", "attacking line",
        ],
        "players": [
            "player", "players", "number", "jersey", "position",
            "center-back", "left-back", "right-back", "goalkeeper",
            "midfielder", "attacking midfielder", "winger", "striker",
            "tracking", "identification", "individual performance",
        ],
        "performance": [
            "performance", "pace", "stamina", "accuracy", "intensity",
            "concentration", "game reading", "timing",
            "successful passes", "pass accuracy", "possession",
            "agility", "strength", "mobility", "dynamics", "aggressiveness",
            "coverage", "recovery", "interception", "finishing",
        ],
    },
}


# ============================================================================
# Detecção de Idioma da Query
# ============================================================================

def detect_language(query: str) -> Language:
    """Best-effort detecção de idioma baseada em keywords.

    Defaults to pt-br se ambíguo.
    """
    query_lower = query.lower()

    # Keywords exclusivos de ES
    if any(kw in query_lower for kw in ["córner", "balón", "delantero", "equipo", "jugador"]):
        return "es"

    # Keywords exclusivos de EN
    if any(kw in query_lower for kw in ["corner", "football", "midfielder", "goalkeeper", "winger"]):
        return "en"

    # Default PT-BR
    return "pt-br"


# ============================================================================
# Scoring Tático
# ============================================================================

def get_tactical_keywords(language: Language | None = None) -> dict[str, list[str]]:
    """Retorna dicionário tático para idioma (default: auto-detect PT-BR)."""
    if language is None:
        language = "pt-br"
    return TACTICAL_KEYWORDS.get(language, TACTICAL_KEYWORDS["pt-br"])


def measure_tactical_relevance(text: str, language: Language = "pt-br") -> dict[str, float]:
    """Mede relevância tática de um texto retornando scores por categoria.

    Returns: {defensive: 0-1, offensive: 0-1, set_pieces: 0-1, analysis: 0-1}

    Score = (matches / total_words_in_text) * (1 + 0.5 * multiple_match_bonus)
    """
    text_lower = text.lower()
    keywords = get_tactical_keywords(language)
    scores = {}
    word_count = len(text_lower.split())

    for category, words in keywords.items():
        matches = sum(1 for word in words if word in text_lower)
        if word_count > 0:
            # Score baseado em densidade: matches / words + bonus por múltiplos matches
            base_score = min(1.0, matches / word_count * 10)
            bonus = 0.2 if matches > 3 else 0.1 if matches > 0 else 0.0
            scores[category] = min(1.0, base_score + bonus)
        else:
            scores[category] = 0.0

    return scores


def get_tactical_focus(text: str, language: Language = "pt-br") -> list[str]:
    """Extrai focus áreas táticas dominantes do texto.

    Returns: ["defensive", "offensive"] ordenado por relevância.
    """
    scores = measure_tactical_relevance(text, language)
    sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [cat for cat, score in sorted_categories if score > 0.2]
