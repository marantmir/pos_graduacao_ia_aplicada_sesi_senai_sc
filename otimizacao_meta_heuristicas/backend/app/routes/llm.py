from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..llm_assistant import enrich_pre_analysis, llm_status
from ..llm_config import (
    PROVIDER_ENV_API_KEY,
    PROVIDER_LABELS,
    PROVIDER_MODEL_SUGGESTIONS,
    PROVIDER_REQUIRES_API_KEY,
    SUPPORTED_PROVIDERS,
    public_llm_config,
    save_llm_config,
)


router = APIRouter(prefix="/api/llm", tags=["llm"])


class LLMConfigUpdate(BaseModel):
    enabled: bool | None = None
    provider: str | None = Field(default="google_gemini")
    model: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=3, le=90)
    temperature: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, ge=200, le=6000)
    language: str | None = None
    analysis_depth: str | None = None
    search_scope: str | None = None
    identity_mode: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False


@router.get("/config")
def get_config():
    return {
        "config": public_llm_config(),
        "status": llm_status(),
        "options": _options(),
    }


@router.put("/config")
def update_config(payload: LLMConfigUpdate):
    config = save_llm_config(payload.model_dump(exclude_unset=True))
    return {
        "config": config,
        "status": llm_status(),
        "options": _options(),
    }


@router.post("/test")
def test_config():
    status = llm_status()
    sample = enrich_pre_analysis(
        "Time de teste",
        "Validar configuracao LLM",
        {"summary": "Teste de integracao sem fontes externas.", "coverage": {}},
        {"summary": "Teste tecnico da camada LLM."},
    )
    return {
        "status": llm_status(),
        "configured_before_test": status,
        "sample": sample,
        "ok": sample.get("status") == "llm_enriched",
    }


def _options() -> dict:
    return {
        "providers": [
            {
                "value": provider,
                "label": PROVIDER_LABELS[provider],
                "env_api_key": PROVIDER_ENV_API_KEY[provider],
                "requires_api_key": PROVIDER_REQUIRES_API_KEY.get(provider, True),
                "free": provider in {"google_gemini", "openrouter_free", "ollama_local"},
            }
            for provider in SUPPORTED_PROVIDERS
        ],
        "models_by_provider": {
            provider: [{"value": model, "label": model} for model in models]
            for provider, models in PROVIDER_MODEL_SUGGESTIONS.items()
        },
        "analysis_depth": [
            {"value": "objetiva", "label": "Objetiva"},
            {"value": "profunda", "label": "Profunda"},
            {"value": "comissao_tecnica", "label": "Comissao tecnica"},
        ],
        "search_scope": [
            {"value": "tactical_visual_only", "label": "Somente material tatico e visual"},
            {"value": "video_first", "label": "Priorizar videos e analises de jogo"},
            {"value": "broad_tactical", "label": "Busca tatica mais ampla"},
        ],
        "identity_mode": [
            {"value": "strict_visual_evidence", "label": "Estrito por evidencia visual"},
            {"value": "ocr_assisted", "label": "OCR assistido por LLM"},
            {"value": "roster_when_available", "label": "Cruzar elenco quando fornecido"},
        ],
        "languages": [
            {"value": "pt-BR", "label": "Portugues do Brasil"},
            {"value": "en-US", "label": "English"},
            {"value": "es", "label": "Espanol"},
        ],
    }
