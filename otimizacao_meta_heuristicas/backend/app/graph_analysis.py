from __future__ import annotations


POSITION_ZONE = {
    "GOL": {"x": 50, "y": 90, "zone": "Saida curta"},
    "ZAG": {"x": 44, "y": 73, "zone": "Primeira construcao"},
    "LAT": {"x": 24, "y": 64, "zone": "Corredor lateral"},
    "VOL": {"x": 48, "y": 52, "zone": "Base do meio"},
    "MEI": {"x": 52, "y": 36, "zone": "Entrelinhas"},
    "ATA": {"x": 58, "y": 18, "zone": "Ultimo terco"},
}


def build_tactical_graph(team: dict, players: list[dict], formations: list[dict]) -> dict:
    ordered_players = sorted(players, key=lambda item: item["tactical_score"], reverse=True)
    nodes = [
        {
            "id": "team",
            "label": team["name"],
            "type": "team",
            "x": 50,
            "y": 50,
            "score": 10,
            "zone": "Modelo coletivo",
        }
    ]

    for index, player in enumerate(ordered_players):
        position = POSITION_ZONE.get(player["position"], POSITION_ZONE["MEI"])
        offset = (index % 3 - 1) * 7
        nodes.append(
            {
                "id": f"player-{index}",
                "label": player["name"],
                "type": "player",
                "position": player["position"],
                "x": max(12, min(88, position["x"] + offset)),
                "y": max(10, min(92, position["y"] + index * 2)),
                "score": player["tactical_score"],
                "zone": position["zone"],
                "influence": player["influence"],
            }
        )

    edges = []
    for index, player in enumerate(ordered_players):
        edges.append(
            {
                "source": "team",
                "target": f"player-{index}",
                "weight": round(player["tactical_score"], 1),
                "label": player["highlight"],
            }
        )

    for index in range(len(ordered_players) - 1):
        current = ordered_players[index]
        next_player = ordered_players[index + 1]
        edges.append(
            {
                "source": f"player-{index}",
                "target": f"player-{index + 1}",
                "weight": round((current["tactical_score"] + next_player["tactical_score"]) / 2, 1),
                "label": "conexao funcional",
            }
        )

    # Time recem-cadastrado pode ainda nao ter formacao/elenco coletados; sem
    # essa guarda, um time vazio derrubava a montagem do grafo inteiro.
    main_formation = (
        max(formations, key=lambda item: item["probability"])
        if formations
        else {"formation": "A definir", "probability": 0, "context": "", "advantages": "", "risks": ""}
    )
    top_players = ordered_players[:3]
    risk_lane = _risk_lane(main_formation["risks"])

    insights = [
        f"Rede prioritaria em {main_formation['formation']} com {main_formation['probability']}% de aderencia ao contexto informado.",
    ]
    if top_players:
        insights.append(f"Maior centralidade projetada: {top_players[0]['name']} ({top_players[0]['position']}).")
    else:
        insights.append("Elenco ainda nao cadastrado para projetar centralidade.")
    insights.append(f"Zona critica observada: {risk_lane}.")

    return {
        "formation": main_formation,
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "centrality_leader": top_players[0]["name"] if top_players else team["name"],
            "network_density": min(94, 54 + len(edges) * 5),
            "progression_lane": _progression_lane(team["style"]),
            "risk_lane": risk_lane,
        },
        "insights": insights,
    }


def _progression_lane(style: str) -> str:
    normalized = style.casefold()
    if "amplitude" in normalized or "corredor" in normalized:
        return "corredores externos"
    if "vertical" in normalized or "transicao" in normalized:
        return "ataque vertical"
    if "posse" in normalized or "centro" in normalized:
        return "corredor central"
    return "organizacao mista"


def _risk_lane(risks: str) -> str:
    normalized = risks.casefold()
    if "lateral" in normalized or "costas" in normalized:
        return "costas dos laterais"
    if "central" in normalized or "volante" in normalized:
        return "entrada da area"
    if "transicao" in normalized:
        return "perda e contra-ataque"
    return "ajuste de compactacao"
