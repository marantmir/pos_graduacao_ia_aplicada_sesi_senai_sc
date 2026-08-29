"""Camada de escrita generica sobre as colecoes JSON (times, jogadores,
formacoes, fontes).

Os arquivos originais sao apenas-leitura via `data_store` (com cache). Este
modulo adiciona CRUD real: garante um `id` estavel por registro, escreve de
forma atomica (arquivo temporario + replace) e invalida o cache de leitura
para que todas as telas reflitam a alteracao imediatamente.

`players/formations/sources` nao tinham `id` na base original; ao listar pela
primeira vez, ids sequenciais sao atribuidos e persistidos (migracao unica),
para que editar/excluir por id seja estavel.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from fastapi import HTTPException

from . import data_store


DATA_DIR = data_store.DATA_DIR
_write_lock = threading.Lock()


# Campos aceitos e seus tipos por colecao. Campos numericos sao convertidos;
# os demais viram string. `id` e sempre gerado pelo servidor.
COLLECTIONS: dict[str, dict] = {
    "teams": {
        "file": "teams.json",
        "team_scoped": False,
        "required": ["name"],
        "fields": {
            "name": "str",
            "country": "str",
            "league": "str",
            "coach": "str",
            "base_formation": "str",
            "style": "str",
            "confidence": "str",
            "status": "str",
            "category": "str",
        },
        "defaults": {
            "country": "Brasil",
            "league": "A definir",
            "coach": "A definir",
            "base_formation": "A definir",
            "style": "",
            "confidence": "Medio",
            "status": "Analise disponivel",
            "category": "Masculino",
        },
    },
    "players": {
        "file": "players.json",
        "team_scoped": True,
        "required": ["team_id", "name"],
        "fields": {
            "team_id": "int",
            "name": "str",
            "position": "str",
            "age": "int",
            "minutes": "int",
            "goals": "int",
            "assists": "int",
            "tactical_score": "float",
            "influence": "str",
            "risk_level": "str",
            "status": "str",
            "highlight": "str",
        },
        "defaults": {
            "position": "",
            "age": 0,
            "minutes": 0,
            "goals": 0,
            "assists": 0,
            "tactical_score": 0.0,
            "influence": "Media",
            "risk_level": "Medio",
            "status": "Elenco",
            "highlight": "",
        },
    },
    "formations": {
        "file": "formations.json",
        "team_scoped": True,
        "required": ["team_id", "formation"],
        "fields": {
            "team_id": "int",
            "formation": "str",
            "probability": "int",
            "context": "str",
            "advantages": "str",
            "risks": "str",
        },
        "defaults": {
            "probability": 0,
            "context": "",
            "advantages": "",
            "risks": "",
        },
    },
    "sources": {
        "file": "sources.json",
        "team_scoped": True,
        "required": ["team_id", "title"],
        "fields": {
            "team_id": "int",
            "title": "str",
            "type": "str",
            "source": "str",
            "date": "str",
            "relevance": "str",
            "summary": "str",
        },
        "defaults": {
            "type": "Video",
            "source": "",
            "date": "",
            "relevance": "Media",
            "summary": "",
        },
    },
}


def collection_config(collection: str) -> dict:
    config = COLLECTIONS.get(collection)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Colecao '{collection}' nao existe. Use: {', '.join(sorted(COLLECTIONS))}.",
        )
    return config


def _path(collection: str) -> Path:
    return DATA_DIR / collection_config(collection)["file"]


def _read_raw(collection: str) -> list[dict]:
    path = _path(collection)
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _write_raw(collection: str, records: list[dict]) -> None:
    path = _path(collection)
    directory = path.parent
    handle, temp_name = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    # Invalida o cache de leitura para que data_store reflita a mudanca.
    data_store.load_json.cache_clear()


def _next_id(records: list[dict]) -> int:
    return max((int(record.get("id", 0)) for record in records), default=0) + 1


def _ensure_ids(collection: str) -> list[dict]:
    """Garante id em todos os registros; persiste a migracao se necessario."""
    records = _read_raw(collection)
    changed = False
    next_id = _next_id(records)
    for record in records:
        if "id" not in record or record["id"] in (None, ""):
            record["id"] = next_id
            next_id += 1
            changed = True
    if changed:
        _write_raw(collection, records)
    return records


def list_records(collection: str) -> list[dict]:
    collection_config(collection)
    return _ensure_ids(collection)


def _coerce(collection: str, payload: dict, *, partial: bool) -> dict:
    config = collection_config(collection)
    fields = config["fields"]
    cleaned: dict = {}
    for key, value in payload.items():
        if key not in fields:
            continue  # ignora campos desconhecidos (ex.: id, team_name)
        cleaned[key] = _coerce_value(key, value, fields[key])

    if not partial:
        for key, default in config.get("defaults", {}).items():
            cleaned.setdefault(key, default)

    missing = [field for field in config["required"] if _is_blank(cleaned.get(field)) and not partial]
    if missing:
        raise HTTPException(status_code=422, detail=f"Campos obrigatorios ausentes: {', '.join(missing)}.")

    if config["team_scoped"] and "team_id" in cleaned:
        data_store.get_team(int(cleaned["team_id"]))  # valida existencia (404 se nao existir)
    return cleaned


def _coerce_value(key: str, value, kind: str):
    if value is None or value == "":
        if kind in ("int", "float"):
            return 0 if kind == "int" else 0.0
        return ""
    try:
        if kind == "int":
            return int(float(value))
        if kind == "float":
            return round(float(value), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"Campo '{key}' deve ser numerico.") from None
    return str(value).strip()


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def create_record(collection: str, payload: dict) -> dict:
    with _write_lock:
        records = _ensure_ids(collection)
        data = _coerce(collection, payload, partial=False)
        data["id"] = _next_id(records)
        records.append(data)
        _write_raw(collection, records)
        return data


def update_record(collection: str, record_id: int, payload: dict) -> dict:
    with _write_lock:
        records = _ensure_ids(collection)
        for record in records:
            if int(record.get("id", 0)) == int(record_id):
                data = _coerce(collection, payload, partial=True)
                record.update(data)
                _write_raw(collection, records)
                return record
        raise HTTPException(status_code=404, detail="Registro nao encontrado.")


def delete_record(collection: str, record_id: int) -> dict:
    with _write_lock:
        records = _ensure_ids(collection)
        for index, record in enumerate(records):
            if int(record.get("id", 0)) == int(record_id):
                removed = records.pop(index)
                _write_raw(collection, records)
                if collection == "teams":
                    _delete_orphaned_team_scoped_records(record_id)
                return removed
        raise HTTPException(status_code=404, detail="Registro nao encontrado.")


def _delete_orphaned_team_scoped_records(team_id: int) -> None:
    """Ao excluir um time, remove tambem jogadores/formacoes/fontes desse
    time nas outras colecoes - sem isso, registros orfaos ficam acumulando
    silenciosamente (podem inclusive vazar para um time novo que reutilize o
    mesmo id, misturando dados de times diferentes)."""
    for other_collection, config in COLLECTIONS.items():
        if other_collection == "teams" or not config["team_scoped"]:
            continue
        records = _ensure_ids(other_collection)
        remaining = [record for record in records if int(record.get("team_id", -1)) != int(team_id)]
        if len(remaining) != len(records):
            _write_raw(other_collection, remaining)
