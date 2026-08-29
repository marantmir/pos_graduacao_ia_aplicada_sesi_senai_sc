from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@lru_cache
def load_json(name: str):
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def teams() -> list[dict]:
    return load_json("teams.json")


def players() -> list[dict]:
    return load_json("players.json")


def tactical_analysis() -> list[dict]:
    return load_json("tactical_analysis.json")


def formations() -> list[dict]:
    return load_json("formations.json")


def sources() -> list[dict]:
    return load_json("sources.json")


def game_plans() -> list[dict]:
    return load_json("game_plans.json")


def get_team(team_id: int) -> dict:
    for team in teams():
        if team["id"] == team_id:
            return team
    raise HTTPException(status_code=404, detail="Time nao encontrado")


def find_team_by_name(name: str) -> dict | None:
    normalized = name.casefold().strip()
    for team in teams():
        if team["name"].casefold() == normalized:
            return team
    return None


def search_teams(query: str) -> list[dict]:
    normalized = query.casefold().strip()
    if not normalized:
        return teams()
    return [team for team in teams() if normalized in team["name"].casefold()]


def get_team_records(records: list[dict], team_id: int) -> list[dict]:
    get_team(team_id)
    return [record for record in records if record["team_id"] == team_id]


def get_single_team_record(records: list[dict], team_id: int, label: str) -> dict:
    get_team(team_id)
    for record in records:
        if record["team_id"] == team_id:
            return record
    raise HTTPException(status_code=404, detail=f"{label} nao encontrado")


def find_single_team_record(records: list[dict], team_id: int) -> dict | None:
    """Como get_single_team_record, mas devolve None em vez de 404 quando o
    time existe mas ainda nao tem o registro (ex.: time recem-cadastrado sem
    dossie/plano semeados). Usado onde a ausencia deve virar um fallback, nao
    um erro que derruba a tela inteira."""
    for record in records:
        if record["team_id"] == team_id:
            return record
    return None
