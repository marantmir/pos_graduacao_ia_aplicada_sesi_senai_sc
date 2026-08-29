from fastapi import APIRouter

from ..data_store import (
    get_single_team_record,
    get_team,
    get_team_records,
    players,
    sources,
    tactical_analysis,
    game_plans,
)
from ..schemas import ReportCreate


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("")
@router.post("/")
def generate_report(payload: ReportCreate):
    team = get_team(payload.team_id)
    dossier = get_single_team_record(tactical_analysis(), payload.team_id, "Dossie tatico")
    plan = get_single_team_record(game_plans(), payload.team_id, "Plano de jogo")
    team_players = get_team_records(players(), payload.team_id)
    team_sources = get_team_records(sources(), payload.team_id)
    key_players = sorted(
        team_players,
        key=lambda player: player["tactical_score"],
        reverse=True,
    )[:3]

    return {
        "team": team,
        "objective": payload.objective,
        "user_profile": payload.user_profile,
        "executive_summary": (
            f"Relatorio para {team['name']} com foco em {payload.objective}. "
            "A leitura combina base local, fontes publicas, grafo tatico, videos e validacao "
            "manual da comissao tecnica."
        ),
        "opponent_profile": dossier["summary"],
        "probable_formation": team["base_formation"],
        "key_players": key_players,
        "strengths": dossier["strengths"],
        "weaknesses": dossier["weaknesses"],
        "recommended_strategy": plan["where_to_attack"],
        "training_suggestions": plan["training_suggestions"],
        "evidence_sources": team_sources[:4],
        "confidence": dossier["confidence_level"],
        "pdf_message": "Exportacao PDF preparada para consolidar evidencias e recomendacoes.",
    }
