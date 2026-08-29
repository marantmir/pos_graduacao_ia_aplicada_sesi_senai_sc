from fastapi.testclient import TestClient

from app.main import app
from app.routes import analysis as analysis_routes


client = TestClient(app)


def _stub_search_public_team_info(_team_name: str) -> dict:
    return {
        "status": "unavailable",
        "query": "stub",
        "summary": "Busca offline nos testes.",
        "sources": [],
        "source_groups": {"match_videos": [], "analysis_videos": [], "team_form": []},
        "coverage": {"match_videos": 0, "analysis_videos": 0, "team_form": 0},
        "analysis_focus": [],
        "collection_plan": [],
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "errors": [],
        "note": "stub",
    }


def _mock_online_search(monkeypatch):
    monkeypatch.setattr(analysis_routes, "search_public_team_info", _stub_search_public_team_info)


def test_preview_known_team_is_save_ready(monkeypatch):
    _mock_online_search(monkeypatch)

    response = client.post(
        "/api/analysis/preview",
        json={
            "team_name": "Flamengo",
            "competition": "Brasileirao Serie A",
            "season": "2026",
            "objective": "Analise de adversario",
            "user_profile": "Analista de desempenho",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["team_found"] is True
    assert payload["save_ready"] is True
    assert payload["team"]["name"] == "Flamengo"


def test_preview_unknown_team_is_not_save_ready(monkeypatch):
    _mock_online_search(monkeypatch)

    response = client.post(
        "/api/analysis/preview",
        json={
            "team_name": "Time Totalmente Inexistente XYZ",
            "competition": "Liga Desconhecida",
            "season": "2026",
            "objective": "Analise de adversario",
            "user_profile": "Analista de desempenho",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["team_found"] is False
    assert payload["save_ready"] is False


def test_create_analysis_for_known_team_appears_in_history():
    response = client.post(
        "/api/analysis",
        json={
            "team_id": 1,
            "team_name": "Flamengo",
            "competition": "Brasileirao Serie A",
            "season": "2026",
            "objective": "Analise de adversario",
            "user_profile": "Analista de desempenho",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["team_id"] == 1

    history = client.get("/api/history").json()
    assert any(record["id"] == created["id"] for record in history)


def test_create_analysis_for_unknown_team_without_saved_profile_fails():
    response = client.post(
        "/api/analysis",
        json={
            "team_name": "Time Totalmente Inexistente XYZ",
            "competition": "Liga Desconhecida",
            "season": "2026",
            "objective": "Analise de adversario",
            "user_profile": "Analista de desempenho",
        },
    )

    assert response.status_code == 422
