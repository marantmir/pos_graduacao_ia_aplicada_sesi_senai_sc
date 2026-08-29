from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ------------------------ Protecao opcional por token ------------------------

def test_admin_routes_open_by_default(monkeypatch):
    monkeypatch.delenv("FOOTBALL_INTEL_ADMIN_TOKEN", raising=False)

    assert client.get("/api/admin/meta").status_code == 200


def test_admin_routes_require_token_when_configured(monkeypatch):
    monkeypatch.setenv("FOOTBALL_INTEL_ADMIN_TOKEN", "segredo-do-deploy")

    without_token = client.get("/api/admin/meta")
    wrong_token = client.get("/api/admin/meta", headers={"X-Admin-Token": "errado"})
    with_token = client.get("/api/admin/meta", headers={"X-Admin-Token": "segredo-do-deploy"})

    assert without_token.status_code == 401
    assert wrong_token.status_code == 401
    assert with_token.status_code == 200


# --------------------------- Usuarios (acesso) ---------------------------

def test_seed_admin_user_exists():
    users = client.get("/api/admin/users").json()
    assert any(u["role"] == "Administrador" and u["status"] == "Ativo" for u in users)


def test_create_edit_delete_user_flow():
    created = client.post(
        "/api/admin/users",
        json={
            "name": "Ana Analista",
            "email": "ana@football-intelligence.local",
            "role": "Analista",
            "status": "Ativo",
            "areas": ["Dossie", "Fontes", "Invalida"],
        },
    )
    assert created.status_code == 201
    user = created.json()
    assert user["id"]
    assert user["areas"] == ["Dossie", "Fontes"]  # area invalida foi descartada

    edited = client.put(f"/api/admin/users/{user['id']}", json={"status": "Inativo", "role": "Treinador"})
    assert edited.status_code == 200
    assert edited.json()["status"] == "Inativo"
    assert edited.json()["role"] == "Treinador"
    assert edited.json()["email"] == "ana@football-intelligence.local"  # inalterado

    deleted = client.delete(f"/api/admin/users/{user['id']}")
    assert deleted.status_code == 200
    assert all(u["id"] != user["id"] for u in client.get("/api/admin/users").json())


def test_create_user_rejects_duplicate_email():
    payload = {"name": "Um", "email": "dup@football-intelligence.local", "role": "Scout", "status": "Ativo"}
    assert client.post("/api/admin/users", json=payload).status_code == 201
    conflict = client.post("/api/admin/users", json={**payload, "name": "Dois"})
    assert conflict.status_code == 409


def test_create_user_rejects_invalid_email_and_role():
    assert client.post("/api/admin/users", json={"name": "X", "email": "sem-arroba"}).status_code == 422
    assert (
        client.post(
            "/api/admin/users",
            json={"name": "X", "email": "x@football-intelligence.local", "role": "Rei"},
        ).status_code
        == 422
    )


def test_cannot_delete_last_active_admin():
    users = client.get("/api/admin/users").json()
    admin = next(u for u in users if u["role"] == "Administrador")
    blocked = client.delete(f"/api/admin/users/{admin['id']}")
    assert blocked.status_code == 409


# --------------------------- Colecoes (CRUD dados) ---------------------------

def test_meta_lists_collections_and_teams():
    meta = client.get("/api/admin/meta").json()
    keys = {c["key"] for c in meta["collections"]}
    assert {"teams", "players", "formations", "sources"} <= keys
    assert meta["teams"]
    assert "Administrador" in meta["roles"]


def test_team_crud_roundtrip():
    created = client.post(
        "/api/admin/collections/teams",
        json={"name": "Time Novo FC", "league": "Serie B", "category": "Masculino"},
    )
    assert created.status_code == 201
    team = created.json()
    assert team["id"]
    assert team["confidence"] == "Medio"  # default aplicado

    # aparece na listagem publica de times (cache invalidado)
    assert any(t["name"] == "Time Novo FC" for t in client.get("/api/teams").json())

    edited = client.put(f"/api/admin/collections/teams/{team['id']}", json={"style": "Pressao alta"})
    assert edited.status_code == 200
    assert edited.json()["style"] == "Pressao alta"

    assert client.delete(f"/api/admin/collections/teams/{team['id']}").status_code == 200
    assert all(t["id"] != team["id"] for t in client.get("/api/teams").json())


def test_player_requires_team_and_coerces_numbers():
    created = client.post(
        "/api/admin/collections/players",
        json={"team_id": 1, "name": "Novo Jogador", "goals": "7", "tactical_score": "8.25"},
    )
    assert created.status_code == 201
    player = created.json()
    assert player["goals"] == 7
    assert player["tactical_score"] == 8.25
    assert player["team_id"] == 1

    # aparece no endpoint de jogadores do time
    assert any(p["name"] == "Novo Jogador" for p in client.get("/api/teams/1/players").json())


def test_record_for_missing_team_returns_404():
    resp = client.post(
        "/api/admin/collections/players",
        json={"team_id": 999999, "name": "Fantasma"},
    )
    assert resp.status_code == 404


def test_missing_required_field_returns_422():
    resp = client.post("/api/admin/collections/teams", json={"league": "Sem nome"})
    assert resp.status_code == 422


def test_unknown_collection_returns_404():
    assert client.get("/api/admin/collections/inexistente").status_code == 404


def test_deleting_a_team_cascades_to_players_formations_and_sources():
    team = client.post("/api/admin/collections/teams", json={"name": "Time Cascata FC"}).json()
    team_id = team["id"]
    client.post("/api/admin/collections/players", json={"team_id": team_id, "name": "Jogador Orfao"})
    client.post(
        "/api/admin/collections/formations", json={"team_id": team_id, "formation": "4-4-2"}
    )
    client.post(
        "/api/admin/collections/sources", json={"team_id": team_id, "title": "Fonte do time"}
    )

    assert client.delete(f"/api/admin/collections/teams/{team_id}").status_code == 200

    assert client.get(f"/api/teams/{team_id}/players").status_code == 404  # time nao existe mais
    remaining_players = [p for p in client.get("/api/admin/collections/players").json() if p["team_id"] == team_id]
    remaining_formations = [
        f for f in client.get("/api/admin/collections/formations").json() if f["team_id"] == team_id
    ]
    remaining_sources = [s for s in client.get("/api/admin/collections/sources").json() if s["team_id"] == team_id]
    assert remaining_players == []
    assert remaining_formations == []
    assert remaining_sources == []


def test_new_team_reusing_deleted_id_does_not_inherit_orphaned_records():
    first = client.post("/api/admin/collections/teams", json={"name": "Primeiro Time FC"}).json()
    client.post(
        "/api/admin/collections/formations", json={"team_id": first["id"], "formation": "4-3-3"}
    )
    client.delete(f"/api/admin/collections/teams/{first['id']}")

    second = client.post("/api/admin/collections/teams", json={"name": "Segundo Time FC"}).json()
    assert second["id"] == first["id"]  # id reaproveitado (max+1 apos a exclusao)

    workspace = client.get(f"/api/teams/workspace/{second['id']}")
    assert workspace.status_code == 200
    assert workspace.json()["formations"] == []


def test_ids_are_assigned_to_legacy_records():
    players = client.get("/api/admin/collections/players").json()
    assert players
    assert all(isinstance(p.get("id"), int) for p in players)
    assert len({p["id"] for p in players}) == len(players)  # ids unicos
