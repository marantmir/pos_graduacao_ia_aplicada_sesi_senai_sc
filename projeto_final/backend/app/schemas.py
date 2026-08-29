from typing import Literal

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    team_id: int | None = None
    team_name: str = Field(min_length=1)
    competition: str = Field(min_length=1)
    season: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    user_profile: str = Field(min_length=1)


class OnlineTeamProfileSave(BaseModel):
    team_name: str = Field(min_length=1)
    country: str | None = None
    league: str | None = None
    coach: str | None = None
    base_formation: str | None = None
    style: str | None = None
    confidence: str | None = None
    status: str | None = None
    category: str | None = None
    online_search: dict = Field(default_factory=dict)


class ReportCreate(BaseModel):
    team_id: int
    objective: str = Field(default="Relatorio para comissao tecnica")
    user_profile: str = Field(default="Analista de desempenho")


class OwnTeamSet(BaseModel):
    ref: str = Field(min_length=1)


class SourceCollectRequest(BaseModel):
    mode: Literal["link", "keyword", "api"]
    value: str = Field(min_length=1)
    team_name: str | None = None
    save: bool = False
    sources: list[dict] | None = None


class AccessUserCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    role: str = Field(default="Analista")
    status: str = Field(default="Ativo")
    areas: list[str] = Field(default_factory=list)


class AccessUserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    status: str | None = None
    areas: list[str] | None = None


class DetectedFormationSave(BaseModel):
    """Formacao estimada pela visao computacional (shape_analysis de um video
    processado), enviada para virar um registro real na colecao de formacoes
    do time - a forma mais assertiva de coleta, pois vem de rastreamento de
    jogadores em video real em vez de estimativa manual."""

    formation: str = Field(min_length=1)
    probability: int = Field(default=30, ge=0, le=100)
    context: str = ""
    advantages: str = ""
    risks: str = ""


class CollectionRecord(BaseModel):
    """Payload aberto para CRUD das colecoes de dados. A validacao de campos e
    tipos e feita no crud_store (por colecao), entao aqui aceitamos um dict
    livre e apenas garantimos que veio um objeto."""

    model_config = {"extra": "allow"}
