"""Rotas de administracao: acesso (usuarios) e manutencao dos dados (CRUD).

- /api/admin/meta          -> opcoes (papeis, status, areas, colecoes, campos)
- /api/admin/users         -> GET (listar) / POST (criar)
- /api/admin/users/{id}    -> PUT (editar) / DELETE (excluir)
- /api/admin/collections/{collection}       -> GET (listar) / POST (criar)
- /api/admin/collections/{collection}/{id}  -> PUT (editar) / DELETE (excluir)

Colecoes suportadas: teams, players, formations, sources (ver crud_store).

Protecao opcional: com a variavel de ambiente FOOTBALL_INTEL_ADMIN_TOKEN definida no
deploy, todas as rotas de administracao passam a exigir o header
X-Admin-Token com o mesmo valor. Sem a variavel, o comportamento atual
(aberto, adequado a uso local) e mantido.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from ..crud_store import COLLECTIONS, create_record, delete_record, list_records, update_record
from ..data_store import teams
from ..database import (
    ACCESS_AREAS,
    ACCESS_ROLES,
    ACCESS_STATUSES,
    create_user,
    delete_user,
    list_users,
    update_user,
)
from ..schemas import AccessUserCreate, AccessUserUpdate


def require_admin_token(request: Request) -> None:
    expected = os.getenv("FOOTBALL_INTEL_ADMIN_TOKEN", "").strip()
    if not expected:
        return
    provided = request.headers.get("X-Admin-Token", "")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(
            status_code=401,
            detail="Acesso administrativo requer o header X-Admin-Token valido neste deploy.",
        )


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_token)])


@router.get("/meta")
def admin_meta():
    return {
        "roles": list(ACCESS_ROLES),
        "statuses": list(ACCESS_STATUSES),
        "areas": list(ACCESS_AREAS),
        "collections": [
            {
                "key": key,
                "team_scoped": config["team_scoped"],
                "required": config["required"],
                "fields": [{"name": name, "type": kind} for name, kind in config["fields"].items()],
            }
            for key, config in COLLECTIONS.items()
        ],
        "teams": [{"id": team["id"], "name": team["name"]} for team in teams()],
    }


@router.get("/users")
def admin_list_users():
    return list_users()


@router.post("/users", status_code=201)
def admin_create_user(payload: AccessUserCreate):
    return create_user(payload.model_dump())


@router.put("/users/{user_id}")
def admin_update_user(user_id: int, payload: AccessUserUpdate):
    return update_user(user_id, payload.model_dump(exclude_none=True))


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int):
    return delete_user(user_id)


@router.get("/collections/{collection}")
def admin_list_collection(collection: str):
    return list_records(collection)


@router.post("/collections/{collection}", status_code=201)
def admin_create_collection_record(collection: str, payload: dict):
    return create_record(collection, payload)


@router.put("/collections/{collection}/{record_id}")
def admin_update_collection_record(collection: str, record_id: int, payload: dict):
    return update_record(collection, record_id, payload)


@router.delete("/collections/{collection}/{record_id}")
def admin_delete_collection_record(collection: str, record_id: int):
    return delete_record(collection, record_id)
