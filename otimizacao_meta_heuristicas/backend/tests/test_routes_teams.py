import io
import json
import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.routes import teams as teams_routes


client = TestClient(app)

STUB_ONLINE_SEARCH = {
    "status": "unavailable",
    "query": "time futebol analise tatica videos",
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


def _stub_search_public_team_info(_team_name: str) -> dict:
    return STUB_ONLINE_SEARCH


def _mock_online_search(monkeypatch):
    monkeypatch.setattr(teams_routes, "search_public_team_info", _stub_search_public_team_info)


def test_list_teams_returns_seed_data():
    response = client.get("/api/teams")

    assert response.status_code == 200
    teams = response.json()
    assert len(teams) >= 1
    assert {"id", "name", "league"}.issubset(teams[0].keys())


def test_list_teams_are_tagged_with_category():
    response = client.get("/api/teams")

    assert response.status_code == 200
    teams = response.json()
    assert all(team["category"] == "Masculino" for team in teams)


def test_team_options_expose_category():
    response = client.get("/api/teams/options")

    assert response.status_code == 200
    options = response.json()["options"]
    assert options
    assert all("category" in option for option in options)


def test_search_filters_by_category():
    masculino = client.get("/api/teams/search", params={"category": "Masculino"})
    feminino = client.get("/api/teams/search", params={"category": "Feminino"})

    assert masculino.status_code == 200
    assert feminino.status_code == 200
    assert len(masculino.json()) >= 1
    assert feminino.json() == []


def test_save_online_profile_persists_explicit_category(monkeypatch):
    _mock_online_search(monkeypatch)

    response = client.post(
        "/api/teams/online-profiles",
        json={"team_name": "Corinthians Feminino", "category": "Feminino"},
    )

    assert response.status_code == 201
    assert response.json()["category"] == "Feminino"
    saved = client.get("/api/teams/online-profiles", params={"query": "Corinthians Feminino"}).json()
    assert saved[0]["category"] == "Feminino"


def test_save_online_profile_defaults_category_to_masculino(monkeypatch):
    _mock_online_search(monkeypatch)

    response = client.post("/api/teams/online-profiles", json={"team_name": "Botafogo"})

    assert response.status_code == 201
    assert response.json()["category"] == "Masculino"


def test_own_team_defaults_to_unset():
    response = client.get("/api/teams/own-team")

    assert response.status_code == 200
    assert response.json() == {"ref": None}


def test_own_team_can_be_set_to_a_local_team():
    response = client.put("/api/teams/own-team", json={"ref": "1"})

    assert response.status_code == 200
    assert response.json() == {"ref": "1"}
    assert client.get("/api/teams/own-team").json() == {"ref": "1"}


def test_own_team_rejects_unknown_ref():
    response = client.put("/api/teams/own-team", json={"ref": "999999"})

    assert response.status_code == 404


def test_team_detail_found():
    response = client.get("/api/teams/1")

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_team_detail_not_found_returns_404():
    response = client.get("/api/teams/999999")

    assert response.status_code == 404


def test_team_graph_analysis_returns_nodes_and_edges():
    response = client.get("/api/teams/1/graph-analysis")

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"]
    assert payload["edges"]


def test_team_operational_research_returns_optimized_lineup():
    response = client.get("/api/teams/1/operational-research")

    assert response.status_code == 200
    payload = response.json()
    assert payload["lineup"]["status"] in {"otimizado", "sem_elenco"}
    assert payload["formation_comparison"]["scenarios"]
    assert payload["target_formation"]


def test_team_operational_research_accepts_formation_override():
    response = client.get("/api/teams/1/operational-research?formation=3-5-2")

    assert response.status_code == 200
    assert response.json()["target_formation"] == "3-5-2"


def test_team_operational_research_unknown_team_returns_404():
    response = client.get("/api/teams/999999/operational-research")

    assert response.status_code == 404


def test_team_related_records_endpoints():
    for suffix in ("formations", "players", "sources", "tactical-analysis", "game-plan"):
        response = client.get(f"/api/teams/1/{suffix}")
        assert response.status_code == 200, suffix


def test_workspace_for_team_without_seed_data_falls_back_instead_of_404():
    # Time criado sem dossie/plano/formacoes semeados (ex.: via Administracao)
    # nao pode derrubar a tela inteira com 404 - regressao coberta aqui.
    # Dossie e plano caem em fallback textual; formacoes ficam genuinamente
    # vazias (sem placeholder mascarando a ausencia de coleta real).
    created = client.post("/api/admin/collections/teams", json={"name": "Time Sem Dados FC"})
    assert created.status_code == 201
    team_id = created.json()["id"]

    response = client.get(f"/api/teams/workspace/{team_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dossier"]["summary"]
    assert payload["plan"]["how_to_press"]
    assert payload["formations"] == []
    assert payload["graph"]["nodes"]  # grafo nao quebra com time sem elenco/formacao


def test_save_detected_formation_creates_record_and_appears_in_workspace():
    created = client.post("/api/admin/collections/teams", json={"name": "Time Video FC"})
    team_id = created.json()["id"]

    saved = client.post(
        f"/api/teams/{team_id}/formations/detected",
        json={
            "formation": "4-4-2 aproximado",
            "probability": 55,
            "context": "Detectado por visao computacional em 180 frames analisados (bloco compacto).",
            "advantages": "Estimativa baseada na distribuicao media dos rastros no campo 2D.",
            "risks": "Estimativa automatica; validar com mais videos.",
        },
    )
    assert saved.status_code == 201
    assert saved.json()["team_id"] == team_id

    formations_response = client.get(f"/api/teams/{team_id}/formations")
    assert len(formations_response.json()) == 1
    assert formations_response.json()[0]["formation"] == "4-4-2 aproximado"

    workspace = client.get(f"/api/teams/workspace/{team_id}")
    assert workspace.json()["formations"][0]["formation"] == "4-4-2 aproximado"


def test_save_detected_formation_for_missing_team_returns_404():
    response = client.post(
        "/api/teams/999999/formations/detected",
        json={"formation": "4-3-3"},
    )
    assert response.status_code == 404


def test_team_public_intelligence_uses_online_search(monkeypatch):
    _mock_online_search(monkeypatch)

    response = client.get("/api/teams/1/public-intelligence")

    assert response.status_code == 200
    assert response.json() == STUB_ONLINE_SEARCH


def _synthetic_video_bytes() -> bytes:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "clip.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (160, 120))
        for i in range(20):
            frame = np.full((120, 160, 3), (60, 160, 60), dtype=np.uint8)
            cv2.rectangle(frame, (10 + i * 3, 40), (30 + i * 3, 80), (20, 20, 200), -1)
            writer.write(frame)
        writer.release()
        return path.read_bytes()


def test_video_vision_upload_rejects_unsupported_extension():
    response = client.post(
        "/api/teams/1/video-vision/upload",
        files={"file": ("clip.txt", b"not a video", "text/plain")},
    )

    assert response.status_code == 400


def test_video_vision_upload_processes_synthetic_clip():
    video_bytes = _synthetic_video_bytes()

    response = client.post(
        "/api/teams/1/video-vision/upload",
        params={"max_frames": 60, "sample_every": 1, "team_filter": "all"},
        files={"file": ("clip.mp4", io.BytesIO(video_bytes), "video/mp4")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert payload["team"] == "Flamengo"
    assert payload["annotated_video_url"].startswith("/media/")


def test_video_vision_upload_is_rate_limited_per_client(monkeypatch):
    from app.rate_limit import video_upload_rate_limiter

    monkeypatch.setattr(video_upload_rate_limiter, "max_requests", 2)
    video_upload_rate_limiter.reset()

    for _ in range(2):
        response = client.post(
            "/api/teams/1/video-vision/upload",
            files={"file": ("clip.txt", b"not a video", "text/plain")},
        )
        assert response.status_code == 400

    blocked = client.post(
        "/api/teams/1/video-vision/upload",
        files={"file": ("clip.txt", b"not a video", "text/plain")},
    )

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_responses_carry_a_request_id_header():
    response = client.get("/api/teams")

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def _parse_sse_events(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


def test_video_vision_job_reports_progress_via_sse_and_completes():
    video_bytes = _synthetic_video_bytes()

    start = client.post(
        "/api/teams/1/video-vision/jobs",
        params={"max_frames": 60, "sample_every": 1, "team_filter": "all"},
        files={"file": ("clip.mp4", io.BytesIO(video_bytes), "video/mp4")},
    )
    assert start.status_code == 200
    job_id = start.json()["job_id"]
    assert job_id

    deadline = time.monotonic() + 10
    events: list[dict] = []
    while time.monotonic() < deadline:
        response = client.get(f"/api/teams/video-vision/jobs/{job_id}/events")
        assert response.status_code == 200
        events = _parse_sse_events(response.text)
        if events and events[-1]["status"] != "processing":
            break

    assert events, "expected at least one SSE event"
    assert events[-1]["status"] == "done"
    assert events[-1]["result"]["status"] == "processed"
    assert events[-1]["result"]["team"] == "Flamengo"


def test_video_vision_job_start_rejects_unsupported_extension():
    response = client.post(
        "/api/teams/1/video-vision/jobs",
        files={"file": ("clip.txt", b"not a video", "text/plain")},
    )

    assert response.status_code == 400


def test_video_vision_job_events_for_unknown_job_reports_error():
    response = client.get("/api/teams/video-vision/jobs/does-not-exist/events")

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[-1]["status"] == "error"


def test_video_vision_job_result_survives_reconnect():
    video_bytes = _synthetic_video_bytes()

    start = client.post(
        "/api/teams/1/video-vision/jobs",
        params={"max_frames": 60, "sample_every": 1, "team_filter": "all"},
        files={"file": ("clip.mp4", io.BytesIO(video_bytes), "video/mp4")},
    )
    assert start.status_code == 200
    job_id = start.json()["job_id"]

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        events = _parse_sse_events(client.get(f"/api/teams/video-vision/jobs/{job_id}/events").text)
        if events and events[-1]["status"] != "processing":
            break

    # Uma reconexao (segunda leitura do stream) ainda recebe o resultado final,
    # pois o job finalizado fica retido por um TTL curto em vez de descartado.
    reconnect = client.get(f"/api/teams/video-vision/jobs/{job_id}/events")
    assert reconnect.status_code == 200
    reconnect_events = _parse_sse_events(reconnect.text)
    assert reconnect_events[-1]["status"] == "done"
    assert reconnect_events[-1]["result"]["annotated_video_url"].startswith("/media/")


def test_collect_sources_by_link_via_route(monkeypatch):
    from app import source_collector

    monkeypatch.setattr(
        source_collector,
        "_fetch_html_capped",
        lambda _url: "<title>Compacto do jogo</title>",
    )

    response = client.post(
        "/api/teams/sources/collect",
        json={"mode": "link", "value": "https://youtube.com/watch?v=abc"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is False
    assert payload["sources"][0]["title"] == "Compacto do jogo"
    assert payload["sources"][0]["category"] == "match_videos"


def test_collect_sources_rejects_private_link_with_422():
    response = client.post(
        "/api/teams/sources/collect",
        json={"mode": "link", "value": "http://127.0.0.1/admin"},
    )

    assert response.status_code == 422


def test_collect_sources_save_merges_into_team_profile():
    sources = [
        {
            "title": "Video novo do adversario",
            "origin": "Link manual",
            "url": "https://youtube.com/watch?v=xyz",
            "summary": "compacto do ultimo jogo",
            "category": "match_videos",
            "relevance": "Alta",
            "published_at": "",
        }
    ]

    response = client.post(
        "/api/teams/sources/collect",
        json={
            "mode": "link",
            "value": "https://youtube.com/watch?v=xyz",
            "team_name": "Adversario Teste",
            "save": True,
            "sources": sources,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is True
    assert payload["profile"]["source_count"] == 1

    workspace = client.get(f"/api/teams/workspace/{payload['profile']['id']}")
    assert workspace.status_code == 200
    combined = workspace.json()["sources"]["combined"]
    assert any(card["title"] == "Video novo do adversario" for card in combined)


def test_collect_sources_save_requires_team_name(monkeypatch):
    response = client.post(
        "/api/teams/sources/collect",
        json={
            "mode": "link",
            "value": "https://youtube.com/watch?v=xyz",
            "save": True,
            "sources": [{"title": "x", "url": "https://youtube.com/watch?v=xyz", "category": "match_videos"}],
        },
    )

    assert response.status_code == 422


def test_video_vision_job_events_stream_disables_proxy_buffering():
    response = client.get("/api/teams/video-vision/jobs/does-not-exist/events")

    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_coach_insights_returns_actionable_sections():
    response = client.get("/api/teams/1/coach-insights")

    assert response.status_code == 200
    payload = response.json()
    assert payload["team"]["name"]
    assert payload["perspective"] == "opponent"
    assert payload["executive_summary"]
    assert payload["tactical_priorities"]
    assert payload["match_model"]["likely_formation"]
    assert "evidence" in payload


def test_coach_insights_supports_own_team_and_game_state():
    response = client.get(
        "/api/teams/1/coach-insights",
        params={"perspective": "own_team", "game_state": "losing"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["perspective"] == "own_team"
    assert payload["game_state"] == "losing"
    assert payload["in_match_adjustment"]["suggested_formation"]
    assert payload["training_focus"]


def test_coach_insights_rejects_invalid_perspective():
    response = client.get("/api/teams/1/coach-insights", params={"perspective": "invalid"})

    assert response.status_code == 422


def test_intelligence_by_name_builds_unsaved_online_team(monkeypatch):
    _mock_online_search(monkeypatch)

    response = client.get(
        "/api/teams/intelligence",
        params={"name": "Time Novo Intelligence FC", "perspective": "opponent"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Time Novo Intelligence FC"
    assert payload["team"]["name"] == "Time Novo Intelligence FC"
    assert payload["kind"] == "online"
    assert payload["coach_insights"]["executive_summary"]
    assert payload["coach_insights"]["evidence"]["gaps"]
