from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from .data_store import find_team_by_name, get_team


DB_PATH = Path(__file__).resolve().parents[1] / "football_intelligence.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                competition TEXT NOT NULL,
                season TEXT NOT NULL,
                objective TEXT NOT NULL,
                user_profile TEXT NOT NULL,
                base_formation TEXT NOT NULL,
                confidence TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS online_team_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_name TEXT NOT NULL UNIQUE,
                team_name TEXT NOT NULL,
                country TEXT NOT NULL,
                league TEXT NOT NULL,
                coach TEXT NOT NULL,
                base_formation TEXT NOT NULL,
                style TEXT NOT NULL,
                confidence TEXT NOT NULL,
                status TEXT NOT NULL,
                search_status TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                online_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Masculino'
            )
            """
        )
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(online_team_profiles)")
        }
        if "category" not in existing_columns:
            connection.execute(
                "ALTER TABLE online_team_profiles ADD COLUMN category TEXT NOT NULL DEFAULT 'Masculino'"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS own_team_setting (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ref TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS access_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                areas TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0]
        if count == 0:
            seed_history(connection)
        users_count = connection.execute("SELECT COUNT(*) FROM access_users").fetchone()[0]
        if users_count == 0:
            seed_users(connection)


def seed_history(connection: sqlite3.Connection) -> None:
    samples = [
        (1, "Analise de adversario", "Analista de desempenho", "Concluida"),
        (2, "Preparacao de jogo", "Treinador", "Concluida"),
        (6, "Relatorio para comissao tecnica", "Coordenador tecnico", "Em revisao"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    for team_id, objective, user_profile, status in samples:
        team = get_team(team_id)
        connection.execute(
            """
            INSERT INTO analysis_history (
                team_id, team_name, competition, season, objective, user_profile,
                base_formation, confidence, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                team["name"],
                team["league"],
                "2026",
                objective,
                user_profile,
                team["base_formation"],
                team["confidence"],
                status,
                now,
            ),
        )


def create_analysis(payload: dict) -> dict:
    selected_team = None
    online_profile = None
    if payload.get("team_id") is not None:
        selected_team = get_team(int(payload["team_id"]))
    if selected_team is None:
        selected_team = find_team_by_name(payload["team_name"])
    if selected_team is None:
        online_profile = get_online_profile_by_name(payload["team_name"])
    if selected_team is None:
        if online_profile is None:
            raise HTTPException(
                status_code=422,
                detail="Time nao encontrado na base local. Salve o perfil online antes de registrar a analise.",
            )
        selected_team = {
            "id": 0,
            "name": online_profile["name"],
            "league": online_profile["league"],
            "base_formation": online_profile["base_formation"],
            "confidence": online_profile["confidence"],
        }

    created_at = datetime.now(timezone.utc).isoformat()
    status = "Concluida" if selected_team["id"] else "Concluida - perfil online"
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_history (
                team_id, team_name, competition, season, objective, user_profile,
                base_formation, confidence, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selected_team["id"],
                selected_team["name"],
                payload["competition"],
                payload["season"],
                payload["objective"],
                payload["user_profile"],
                selected_team["base_formation"],
                selected_team["confidence"],
                status,
                created_at,
            ),
        )
        record_id = cursor.lastrowid

    return {
        "id": record_id,
        "team_id": selected_team["id"],
        "team_name": selected_team["name"],
        "competition": payload["competition"],
        "season": payload["season"],
        "objective": payload["objective"],
        "user_profile": payload["user_profile"],
        "base_formation": selected_team["base_formation"],
        "confidence": selected_team["confidence"],
        "status": status,
        "created_at": created_at,
    }


def list_history() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM analysis_history
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def normalize_team_name(name: str) -> str:
    return " ".join(name.casefold().strip().split())


def get_online_profile_by_name(team_name: str) -> dict | None:
    normalized = normalize_team_name(team_name)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM online_team_profiles
            WHERE normalized_name = ?
            """,
            (normalized,),
        ).fetchone()
    return _online_profile_from_row(row) if row else None


def get_online_profile_by_id(profile_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM online_team_profiles
            WHERE id = ?
            """,
            (profile_id,),
        ).fetchone()
    return _online_profile_from_row(row) if row else None


def list_online_profiles(query: str = "") -> list[dict]:
    normalized = normalize_team_name(query)
    with get_connection() as connection:
        if normalized:
            rows = connection.execute(
                """
                SELECT *
                FROM online_team_profiles
                WHERE normalized_name LIKE ?
                ORDER BY datetime(updated_at) DESC, id DESC
                """,
                (f"%{normalized}%",),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM online_team_profiles
                ORDER BY datetime(updated_at) DESC, id DESC
                """
            ).fetchall()
    return [_online_profile_from_row(row) for row in rows]


def save_online_profile(payload: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    team_name = payload["team_name"].strip()
    normalized = normalize_team_name(team_name)
    online_payload = payload.get("online_search") or {}
    sources = online_payload.get("sources") or []
    summary = payload.get("style") or online_payload.get("summary") or "Fonte tatica salva para revisao futura."

    values = {
        "normalized_name": normalized,
        "team_name": team_name,
        "country": payload.get("country") or "A confirmar",
        "league": payload.get("league") or "Fonte publica",
        "coach": payload.get("coach") or "A confirmar",
        "base_formation": payload.get("base_formation") or "A definir",
        "style": summary,
        "confidence": payload.get("confidence") or ("Medio" if online_payload.get("status") == "available" else "Baixo"),
        "status": payload.get("status") or "Perfil online salvo",
        "search_status": online_payload.get("status") or "saved",
        "source_count": len(sources),
        "online_payload": json.dumps(online_payload, ensure_ascii=False),
        "category": payload.get("category") or online_payload.get("category") or "Masculino",
    }

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id, created_at FROM online_team_profiles WHERE normalized_name = ?",
            (normalized,),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE online_team_profiles
                SET team_name = ?, country = ?, league = ?, coach = ?, base_formation = ?,
                    style = ?, confidence = ?, status = ?, search_status = ?, source_count = ?,
                    online_payload = ?, category = ?, updated_at = ?
                WHERE normalized_name = ?
                """,
                (
                    values["team_name"],
                    values["country"],
                    values["league"],
                    values["coach"],
                    values["base_formation"],
                    values["style"],
                    values["confidence"],
                    values["status"],
                    values["search_status"],
                    values["source_count"],
                    values["online_payload"],
                    values["category"],
                    now,
                    normalized,
                ),
            )
            profile_id = existing["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO online_team_profiles (
                    normalized_name, team_name, country, league, coach, base_formation,
                    style, confidence, status, search_status, source_count, online_payload,
                    category, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["normalized_name"],
                    values["team_name"],
                    values["country"],
                    values["league"],
                    values["coach"],
                    values["base_formation"],
                    values["style"],
                    values["confidence"],
                    values["status"],
                    values["search_status"],
                    values["source_count"],
                    values["online_payload"],
                    values["category"],
                    now,
                    now,
                ),
            )
            profile_id = cursor.lastrowid

    saved = get_online_profile_by_name(team_name)
    if saved:
        return saved
    return {"id": profile_id, **values, "created_at": now, "updated_at": now}


def _online_profile_from_row(row: sqlite3.Row) -> dict:
    payload = json.loads(row["online_payload"] or "{}")
    return {
        "id": f"online-{row['id']}",
        "online_profile_id": row["id"],
        "profile_type": "online",
        "name": row["team_name"],
        "country": row["country"],
        "league": row["league"],
        "coach": row["coach"],
        "base_formation": row["base_formation"],
        "style": row["style"],
        "confidence": row["confidence"],
        "status": row["status"],
        "search_status": row["search_status"],
        "source_count": row["source_count"],
        "category": row["category"],
        "crest_url": payload.get("crest_url"),
        "online_search": payload,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_own_team_ref() -> str | None:
    with get_connection() as connection:
        row = connection.execute("SELECT ref FROM own_team_setting WHERE id = 1").fetchone()
    return row["ref"] if row else None


def set_own_team_ref(ref: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO own_team_setting (id, ref, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET ref = excluded.ref, updated_at = excluded.updated_at
            """,
            (ref, now),
        )
    return ref


# ---------------------------------------------------------------------------
# Administracao de acesso: usuarios (nome, email, papel, status, areas)
# ---------------------------------------------------------------------------
ACCESS_ROLES = ("Administrador", "Analista", "Treinador", "Scout", "Gestor")
ACCESS_STATUSES = ("Ativo", "Inativo")
ACCESS_AREAS = ("Dossie", "Formacoes", "Elenco", "Fontes", "Plano", "Relatorio", "Administracao")


def seed_users(connection: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO access_users (name, email, role, status, areas, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Administrador da Plataforma",
            "admin@football-intelligence.local",
            "Administrador",
            "Ativo",
            json.dumps(list(ACCESS_AREAS), ensure_ascii=False),
            now,
            now,
        ),
    )


def _user_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "status": row["status"],
        "areas": json.loads(row["areas"] or "[]"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_users() -> list[dict]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM access_users ORDER BY name COLLATE NOCASE ASC, id ASC"
        ).fetchall()
    return [_user_from_row(row) for row in rows]


def get_user(user_id: int) -> dict | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    init_db()
    normalized = (email or "").strip().casefold()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM access_users WHERE lower(email) = ?", (normalized,)
        ).fetchone()
    return _user_from_row(row) if row else None


def create_user(payload: dict) -> dict:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    values = _normalize_user_payload(payload)
    if get_user_by_email(values["email"]):
        raise HTTPException(status_code=409, detail="Ja existe um usuario com este email.")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO access_users (name, email, role, status, areas, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["name"],
                values["email"],
                values["role"],
                values["status"],
                json.dumps(values["areas"], ensure_ascii=False),
                now,
                now,
            ),
        )
        user_id = cursor.lastrowid
    return get_user(user_id)


def update_user(user_id: int, payload: dict) -> dict:
    init_db()
    existing = get_user(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    values = _normalize_user_payload({**existing, **payload})
    duplicate = get_user_by_email(values["email"])
    if duplicate and duplicate["id"] != user_id:
        raise HTTPException(status_code=409, detail="Ja existe outro usuario com este email.")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE access_users
            SET name = ?, email = ?, role = ?, status = ?, areas = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                values["name"],
                values["email"],
                values["role"],
                values["status"],
                json.dumps(values["areas"], ensure_ascii=False),
                now,
                user_id,
            ),
        )
    return get_user(user_id)


def delete_user(user_id: int) -> dict:
    init_db()
    existing = get_user(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    if existing["role"] == "Administrador" and _active_admin_count() <= 1:
        raise HTTPException(
            status_code=409,
            detail="Nao e possivel excluir o unico administrador ativo. Crie outro admin antes.",
        )
    with get_connection() as connection:
        connection.execute("DELETE FROM access_users WHERE id = ?", (user_id,))
    return existing


def _active_admin_count() -> int:
    with get_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM access_users WHERE role = 'Administrador' AND status = 'Ativo'"
        ).fetchone()[0]


def _normalize_user_payload(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Informe o nome do usuario.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Informe um email valido.")
    role = str(payload.get("role") or "Analista").strip()
    if role not in ACCESS_ROLES:
        raise HTTPException(status_code=422, detail=f"Papel invalido. Use: {', '.join(ACCESS_ROLES)}.")
    status = str(payload.get("status") or "Ativo").strip()
    if status not in ACCESS_STATUSES:
        raise HTTPException(status_code=422, detail=f"Status invalido. Use: {', '.join(ACCESS_STATUSES)}.")
    areas_raw = payload.get("areas") or []
    if isinstance(areas_raw, str):
        areas_raw = [part.strip() for part in areas_raw.split(",")]
    areas = [area for area in areas_raw if area in ACCESS_AREAS]
    return {"name": name, "email": email, "role": role, "status": status, "areas": areas}
