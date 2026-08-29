from app.graph_analysis import build_tactical_graph


def _sample_team():
    return {"id": 1, "name": "Flamengo", "style": "Posse de bola com amplitude e pressao pos-perda"}


def _sample_players():
    return [
        {"name": "Jogador A", "position": "ZAG", "tactical_score": 8.4, "influence": "Alta", "highlight": "Saida de bola"},
        {"name": "Jogador B", "position": "VOL", "tactical_score": 7.9, "influence": "Alta", "highlight": "Recomposicao"},
        {"name": "Jogador C", "position": "MEI", "tactical_score": 9.1, "influence": "Alta", "highlight": "Ultimo passe"},
        {"name": "Jogador D", "position": "ATA", "tactical_score": 8.7, "influence": "Media", "highlight": "Finalizacao"},
    ]


def _sample_formations():
    return [
        {"formation": "4-3-3", "probability": 62, "risks": "Costas dos laterais"},
        {"formation": "4-2-3-1", "probability": 38, "risks": "Entrada da area"},
    ]


def test_build_tactical_graph_picks_highest_probability_formation():
    graph = build_tactical_graph(_sample_team(), _sample_players(), _sample_formations())

    assert graph["formation"]["formation"] == "4-3-3"


def test_build_tactical_graph_orders_players_by_tactical_score():
    graph = build_tactical_graph(_sample_team(), _sample_players(), _sample_formations())

    player_nodes = [node for node in graph["nodes"] if node["type"] == "player"]
    scores = [node["score"] for node in player_nodes]

    assert scores == sorted(scores, reverse=True)
    assert graph["nodes"][0]["type"] == "team"


def test_build_tactical_graph_connects_team_node_to_every_player():
    graph = build_tactical_graph(_sample_team(), _sample_players(), _sample_formations())

    team_edges = [edge for edge in graph["edges"] if edge["source"] == "team"]

    assert len(team_edges) == len(_sample_players())
    assert graph["metrics"]["centrality_leader"] == "Jogador C"


def test_build_tactical_graph_handles_single_player_without_chain_edges():
    single_player = _sample_players()[:1]

    graph = build_tactical_graph(_sample_team(), single_player, _sample_formations())

    assert len(graph["edges"]) == 1
    assert graph["insights"][1].startswith("Maior centralidade")


def test_progression_and_risk_lane_reflect_style_and_risks():
    graph = build_tactical_graph(_sample_team(), _sample_players(), _sample_formations())

    assert graph["metrics"]["progression_lane"] == "corredores externos"
    assert graph["metrics"]["risk_lane"] == "costas dos laterais"


def test_build_tactical_graph_handles_team_without_players_or_formations():
    # Time recem-cadastrado (ex.: via Administracao) pode nao ter elenco nem
    # formacao ainda; o grafo deve degradar graciosamente, nao quebrar.
    graph = build_tactical_graph(_sample_team(), [], [])

    assert graph["nodes"] == [
        {"id": "team", "label": "Flamengo", "type": "team", "x": 50, "y": 50, "score": 10, "zone": "Modelo coletivo"}
    ]
    assert graph["edges"] == []
    assert graph["formation"]["formation"] == "A definir"
    assert graph["metrics"]["centrality_leader"] == "Flamengo"
    assert "Elenco ainda nao cadastrado" in graph["insights"][1]
