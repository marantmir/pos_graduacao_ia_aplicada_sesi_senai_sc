"""Camada de inteligência para comissão técnica.

Consolida evidências já disponíveis na plataforma (dossiê, formações, elenco,
grafo, plano de jogo, fontes públicas e pesquisa operacional) em recomendações
acionáveis. O motor é determinístico e explicável: cada insight inclui a
origem/evidência que o sustenta e não inventa estatísticas ausentes.
"""
from __future__ import annotations

from typing import Literal

Perspective = Literal["opponent", "own_team"]
GameState = Literal["balanced", "winning", "drawing", "losing"]


def build_coach_insights(
    team: dict,
    dossier: dict,
    players: list[dict],
    formations: list[dict],
    plan: dict,
    graph: dict,
    public_intelligence: dict | None = None,
    operational_research: dict | None = None,
    *,
    perspective: Perspective = "opponent",
    game_state: GameState = "balanced",
) -> dict:
    """Gera uma leitura de jogo pronta para treinador/comissão.

    ``perspective=opponent`` interpreta o time como adversário a ser enfrentado.
    ``perspective=own_team`` interpreta os mesmos dados como diagnóstico do
    próprio time. ``game_state`` altera os ajustes recomendados em jogo.
    """
    public_intelligence = public_intelligence or {}
    operational_research = operational_research or {}

    main_formation = _main_formation(team, formations)
    key_players = sorted(players, key=_player_priority, reverse=True)[:5]
    strengths = _as_list(dossier.get("strengths"))
    weaknesses = _as_list(dossier.get("weaknesses"))
    graph_metrics = graph.get("metrics") or {}
    collection = public_intelligence.get("coverage") or {}

    tactical_priorities = _tactical_priorities(
        perspective=perspective,
        dossier=dossier,
        plan=plan,
        graph_metrics=graph_metrics,
        strengths=strengths,
        weaknesses=weaknesses,
    )

    performance = _performance_reading(key_players, perspective)
    match_adjustment = _game_state_adjustment(
        game_state, perspective, plan, operational_research, main_formation
    )
    training_focus = _training_focus(plan, weaknesses, perspective)
    set_piece = _set_piece_reading(dossier, perspective)

    evidence_count = (
        len(players)
        + len(formations)
        + int(collection.get("match_videos") or 0)
        + int(collection.get("analysis_videos") or 0)
        + int(collection.get("team_form") or 0)
    )
    confidence = _confidence_label(dossier.get("confidence_level") or team.get("confidence"), evidence_count)

    if perspective == "opponent":
        headline = (
            f"Plano contra {team.get('name')}: controlar {graph_metrics.get('progression_lane') or 'a progressão principal'}, "
            f"proteger {graph_metrics.get('risk_lane') or 'a zona crítica'} e atacar as fragilidades confirmadas."
        )
    else:
        headline = (
            f"Diagnóstico de {team.get('name')}: potencializar {strengths[0] if strengths else 'o modelo coletivo'}, "
            f"corrigir {weaknesses[0] if weaknesses else 'as lacunas de compactação'} e ajustar o plano ao estado do jogo."
        )

    return {
        "team": {
            "id": team.get("id"),
            "name": team.get("name"),
            "league": team.get("league"),
            "base_formation": team.get("base_formation"),
            "style": team.get("style"),
        },
        "perspective": perspective,
        "game_state": game_state,
        "confidence": confidence,
        "executive_summary": headline,
        "match_model": {
            "likely_formation": main_formation.get("formation"),
            "formation_probability": main_formation.get("probability"),
            "offensive_model": dossier.get("offensive_model") or "Não confirmado.",
            "defensive_model": dossier.get("defensive_model") or "Não confirmado.",
            "offensive_transition": dossier.get("offensive_transition") or "Não confirmado.",
            "defensive_transition": dossier.get("defensive_transition") or "Não confirmado.",
            "progression_lane": graph_metrics.get("progression_lane") or "Não confirmado",
            "risk_lane": graph_metrics.get("risk_lane") or "Não confirmado",
        },
        "tactical_priorities": tactical_priorities,
        "performance": performance,
        "set_pieces": set_piece,
        "in_match_adjustment": match_adjustment,
        "training_focus": training_focus,
        "key_players": [
            {
                "name": item.get("name"),
                "position": item.get("position"),
                "tactical_score": item.get("tactical_score"),
                "minutes": item.get("minutes"),
                "goals": item.get("goals"),
                "assists": item.get("assists"),
                "influence": item.get("influence"),
                "risk_level": item.get("risk_level"),
                "why_it_matters": _player_reason(item, perspective),
            }
            for item in key_players
        ],
        "evidence": {
            "players_available": len(players),
            "formations_available": len(formations),
            "public_sources": len(public_intelligence.get("sources") or []),
            "match_video_refs": int(collection.get("match_videos") or 0),
            "analysis_video_refs": int(collection.get("analysis_videos") or 0),
            "pattern_refs": int(collection.get("team_form") or 0),
            "gaps": _data_gaps(players, formations, public_intelligence),
            "note": (
                "Insights são apoio à decisão. Recomendações com pouca evidência devem ser validadas "
                "com vídeo recente, contexto da partida, disponibilidade do elenco e observação da comissão técnica."
            ),
        },
    }


def _main_formation(team: dict, formations: list[dict]) -> dict:
    if formations:
        return max(formations, key=lambda item: float(item.get("probability") or 0))
    return {
        "formation": team.get("base_formation") or "A definir",
        "probability": 0,
        "context": "Formação cadastrada sem amostra comparativa.",
        "risks": "",
    }


def _player_priority(player: dict) -> tuple[float, float, float]:
    tactical = float(player.get("tactical_score") or 0)
    production = float(player.get("goals") or 0) * 1.5 + float(player.get("assists") or 0)
    influence = 2.0 if str(player.get("influence", "")).casefold() == "alta" else 1.0
    return tactical, production, influence


def _tactical_priorities(
    *,
    perspective: Perspective,
    dossier: dict,
    plan: dict,
    graph_metrics: dict,
    strengths: list[str],
    weaknesses: list[str],
) -> list[dict]:
    items: list[dict] = []
    if perspective == "opponent":
        if plan.get("how_to_press"):
            items.append({
                "priority": "Pressão e saída adversária",
                "action": plan["how_to_press"],
                "why": dossier.get("offensive_model") or "Reduzir a qualidade da primeira construção.",
            })
        if plan.get("where_to_attack"):
            items.append({
                "priority": "Zona para atacar",
                "action": plan["where_to_attack"],
                "why": weaknesses[0] if weaknesses else graph_metrics.get("risk_lane") or "Fragilidade ainda em validação.",
            })
        neutralize = _as_list(plan.get("players_to_neutralize"))
        if neutralize:
            items.append({
                "priority": "Jogadores a neutralizar",
                "action": "Reduzir tempo e espaço de " + ", ".join(neutralize[:3]) + ".",
                "why": "São referências cadastradas no plano de jogo e devem ser validadas no vídeo mais recente.",
            })
    else:
        if strengths:
            items.append({
                "priority": "Potencializar identidade",
                "action": f"Criar condições para repetir {strengths[0].lower()} sem perder equilíbrio após a perda.",
                "why": dossier.get("offensive_model") or "Ponto forte registrado no dossiê.",
            })
        if weaknesses:
            items.append({
                "priority": "Corrigir vulnerabilidade",
                "action": f"Treinar mecanismos específicos para reduzir {weaknesses[0].lower()}.",
                "why": dossier.get("defensive_transition") or "Fragilidade registrada no dossiê.",
            })
        items.append({
            "priority": "Controle de risco",
            "action": f"Garantir cobertura na zona {graph_metrics.get('risk_lane') or 'crítica'} durante a fase ofensiva.",
            "why": "A estrutura deve preservar rest-defense e reação à perda.",
        })

    return items[:4]


def _performance_reading(players: list[dict], perspective: Perspective) -> dict:
    if not players:
        return {
            "summary": "Não há elenco/estatísticas individuais suficientes para leitura de performance.",
            "alerts": ["Importar minutos, participação ofensiva, posição e disponibilidade para melhorar a recomendação."],
        }

    highest_minutes = max(players, key=lambda item: float(item.get("minutes") or 0))
    highest_output = max(players, key=lambda item: float(item.get("goals") or 0) + float(item.get("assists") or 0))
    high_risk = [p for p in players if str(p.get("risk_level", "")).casefold() == "alto"]
    if perspective == "opponent":
        summary = (
            f"{highest_output.get('name')} concentra a maior produção G+A entre os jogadores disponíveis; "
            f"{highest_minutes.get('name')} possui a maior carga de minutos da amostra."
        )
    else:
        summary = (
            f"Monitorar carga de {highest_minutes.get('name')} e manter mecanismos para potencializar "
            f"{highest_output.get('name')}, maior produção G+A da amostra."
        )
    alerts = []
    if high_risk:
        alerts.append("Risco alto cadastrado: " + ", ".join(p.get("name", "") for p in high_risk[:3]) + ".")
    alerts.append("Minutos e produção são indicadores parciais; contexto, intensidade e disponibilidade precisam ser confirmados.")
    return {"summary": summary, "alerts": alerts}


def _set_piece_reading(dossier: dict, perspective: Perspective) -> dict:
    pattern = dossier.get("set_pieces") or "Sem padrão de bola parada confirmado."
    action = (
        "Preparar marcação e segunda bola especificamente para o padrão observado."
        if perspective == "opponent"
        else "Revisar execução, ocupação da área e proteção da transição após a cobrança."
    )
    return {"observed_pattern": pattern, "coach_action": action}


def _game_state_adjustment(
    game_state: GameState,
    perspective: Perspective,
    plan: dict,
    operational_research: dict,
    main_formation: dict,
) -> dict:
    recommendations = ((operational_research.get("formation_comparison") or {}).get("recommendations") or {})
    mapping = {"winning": "vencendo", "drawing": "empatando", "losing": "perdendo"}
    state_key = mapping.get(game_state)
    formation_rec = recommendations.get(state_key) if state_key else None
    adjustments = _as_list(plan.get("in_match_adjustments"))

    if game_state == "winning":
        principle = "Reduzir exposição sem abandonar a ameaça de transição."
    elif game_state == "losing":
        principle = "Aumentar presença ofensiva com cobertura preparada para perdas."
    elif game_state == "drawing":
        principle = "Preservar equilíbrio e acelerar apenas quando o gatilho de vantagem estiver claro."
    else:
        principle = "Começar com o plano-base e atualizar decisões após os primeiros padrões reais do jogo."

    if perspective == "opponent":
        principle += " Observar rapidamente se o adversário alterou altura de bloco, saída ou corredor preferencial."

    return {
        "state": game_state,
        "principle": principle,
        "suggested_formation": (formation_rec or {}).get("formation") or main_formation.get("formation"),
        "formation_reason": (formation_rec or {}).get("reason") or "Sem comparação otimizada suficiente para este estado.",
        "bench_triggers": adjustments[:3],
    }


def _training_focus(plan: dict, weaknesses: list[str], perspective: Perspective) -> list[str]:
    suggestions = _as_list(plan.get("training_suggestions"))[:4]
    if suggestions:
        return suggestions
    if weaknesses:
        prefix = "Simular a fragilidade do adversário" if perspective == "opponent" else "Corrigir em treino"
        return [f"{prefix}: {item}." for item in weaknesses[:3]]
    return [
        "Treinar construção sob pressão e reação imediata à perda.",
        "Ensaiar ocupação de área, segunda bola e proteção contra transição.",
    ]


def _player_reason(player: dict, perspective: Perspective) -> str:
    production = int(player.get("goals") or 0) + int(player.get("assists") or 0)
    if perspective == "opponent":
        return (
            f"Influência {player.get('influence') or 'não informada'}, nota tática {player.get('tactical_score') or 0} "
            f"e {production} participações diretas em gol na amostra cadastrada."
        )
    return (
        f"Nota tática {player.get('tactical_score') or 0}, influência {player.get('influence') or 'não informada'} "
        f"e {production} participações diretas em gol na amostra cadastrada."
    )


def _data_gaps(players: list[dict], formations: list[dict], public_intelligence: dict) -> list[str]:
    gaps = []
    if not players:
        gaps.append("Elenco e métricas individuais não disponíveis.")
    if not formations:
        gaps.append("Sem formações observadas/comparadas.")
    coverage = public_intelligence.get("coverage") or {}
    if not (int(coverage.get("match_videos") or 0) + int(coverage.get("analysis_videos") or 0)):
        gaps.append("Sem referência de vídeo público registrada para validação recente.")
    if not public_intelligence.get("sources"):
        gaps.append("Sem fontes públicas salvas para triangulação.")
    return gaps


def _confidence_label(base: object, evidence_count: int) -> str:
    normalized = str(base or "").casefold()
    if normalized in {"alto", "alta", "high"} and evidence_count >= 5:
        return "Alta"
    if normalized in {"medio", "médio", "media", "média", "medium", "alto", "alta"} and evidence_count >= 2:
        return "Média"
    return "Baixa"


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
