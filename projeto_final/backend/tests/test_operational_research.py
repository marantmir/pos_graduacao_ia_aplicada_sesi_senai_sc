from app.operational_research import (
    build_operational_research,
    compare_formation_scenarios,
    optimize_lineup,
    parse_formation_slots,
)


def _player(name: str, position: str, score: float, **extra) -> dict:
    return {
        "id": hash(name) % 1000,
        "name": name,
        "position": position,
        "tactical_score": score,
        "influence": extra.get("influence", "Media"),
        "risk_level": extra.get("risk_level", "Medio"),
        "status": extra.get("status", "Titular"),
    }


def test_parse_formation_slots_4231_builds_expected_lines():
    slots = parse_formation_slots("4-2-3-1")

    positions = [slot["position"] for slot in slots]
    assert positions.count("GOL") == 1
    assert positions.count("LAT") == 2
    assert positions.count("ZAG") == 2
    assert positions.count("VOL") == 2
    assert positions.count("MEI") == 3
    assert positions.count("ATA") == 1
    assert len(slots) == 11


def test_parse_formation_slots_back_three_has_no_fullbacks():
    slots = parse_formation_slots("3-5-2")

    positions = [slot["position"] for slot in slots]
    assert positions.count("ZAG") == 3
    assert positions.count("LAT") == 0


def test_parse_formation_slots_falls_back_on_garbage_input():
    slots = parse_formation_slots("a definir")

    # Fallback 4-3-3: sempre devolve um onze jogavel em vez de quebrar.
    assert len(slots) == 11


def test_optimize_lineup_prefers_natural_positions():
    players = [
        _player("Goleiro", "GOL", 7.0),
        _player("Zagueiro A", "ZAG", 7.5),
        _player("Zagueiro B", "ZAG", 7.2),
        _player("Lateral A", "LAT", 7.0),
        _player("Lateral B", "LAT", 6.8),
        _player("Volante", "VOL", 7.4),
        _player("Meia A", "MEI", 8.0),
        _player("Meia B", "MEI", 7.6),
        _player("Atacante A", "ATA", 8.5),
        _player("Atacante B", "ATA", 8.0),
        _player("Atacante C", "ATA", 7.8),
    ]

    result = optimize_lineup(players, "4-3-3")

    assert result["status"] == "otimizado"
    goal_slot = next(item for item in result["assignments"] if item["position"] == "GOL")
    assert goal_slot["player"]["name"] == "Goleiro"
    natural_count = sum(1 for item in result["assignments"] if item["player"] and item["natural_position"])
    assert natural_count >= 9
    assert result["positional_coverage"] == 100.0


def test_optimize_lineup_is_globally_optimal_not_greedy():
    """Um guloso escalando o melhor jogador primeiro colocaria o Meia Estrela
    na vaga de MEI e deixaria a vaga de ATA para o reserva fraco. O otimo
    global adapta o Meia Estrela no ataque (afinidade 0.6) e mantem o
    especialista na vaga de MEI quando isso maximiza a soma."""
    players = [
        _player("Meia Estrela", "MEI", 9.0),
        _player("Meia Comum", "MEI", 7.0),
    ]

    result = optimize_lineup(players, "1-1")  # 1 linha defesa, 1 ataque + GOL
    filled = [item for item in result["assignments"] if item["player"]]

    # Ambos entram em campo: soma dos fits e maior usando os dois jogadores.
    assert len(filled) == 2


def test_optimize_lineup_reports_gaps_for_thin_squad():
    players = [_player("Atacante", "ATA", 8.0)]

    result = optimize_lineup(players, "4-4-2")

    assert result["positional_coverage"] < 20
    assert "GOL" in result["gaps"]


def test_optimize_lineup_without_players_returns_guidance():
    result = optimize_lineup([], "4-3-3")

    assert result["status"] == "sem_elenco"
    assert result["lineup_strength"] == 0.0


def test_compare_formation_scenarios_recommends_by_game_state():
    players = [
        _player("Goleiro", "GOL", 7.0),
        _player("Zagueiro A", "ZAG", 8.0),
        _player("Zagueiro B", "ZAG", 7.8),
        _player("Zagueiro C", "ZAG", 7.5),
        _player("Lateral A", "LAT", 6.5),
        _player("Lateral B", "LAT", 6.4),
        _player("Volante", "VOL", 7.2),
        _player("Meia", "MEI", 7.0),
        _player("Atacante A", "ATA", 8.8),
        _player("Atacante B", "ATA", 8.2),
        _player("Atacante C", "ATA", 8.0),
    ]
    formations = [
        {"formation": "5-3-2", "probability": 40, "context": "fechar o jogo", "risks": ""},
        {"formation": "4-3-3", "probability": 60, "context": "propor o jogo", "risks": ""},
    ]

    result = compare_formation_scenarios(players, formations)

    assert len(result["scenarios"]) == 2
    assert set(result["recommendations"]) == {"vencendo", "empatando", "perdendo"}
    for scenario in result["scenarios"]:
        assert scenario["utility"] > 0
        assert 0 <= scenario["defensive_index"] <= 10
        assert 0 <= scenario["offensive_index"] <= 10


def test_build_operational_research_uses_base_formation_when_no_records():
    team = {"name": "Time Teste", "base_formation": "4-2-3-1"}

    result = build_operational_research(team, [], [])

    assert result["target_formation"] == "4-2-3-1"
    assert result["formation_comparison"]["scenarios"][0]["formation"] == "4-2-3-1"


def test_build_operational_research_respects_requested_formation():
    team = {"name": "Time Teste", "base_formation": "4-3-3"}
    players = [_player("Atacante", "ATA", 8.0)]

    result = build_operational_research(team, players, [], requested_formation="3-5-2")

    assert result["target_formation"] == "3-5-2"
    assert result["lineup"]["formation"] == "3-5-2"
