from fastapi import APIRouter

from ..database import create_analysis, get_online_profile_by_name, list_history
from ..data_store import (
    find_team_by_name,
    formations,
    game_plans,
    get_single_team_record,
    get_team,
    get_team_records,
    players,
    tactical_analysis,
)
from ..llm_assistant import enrich_pre_analysis
from ..online_search import search_public_team_info
from ..schemas import AnalysisCreate


router = APIRouter(tags=["analysis"])


@router.post("/api/analysis/preview")
def preview(payload: AnalysisCreate):
    selected_team = None
    if payload.team_id:
        selected_team = get_team(payload.team_id)
    if selected_team is None:
        selected_team = find_team_by_name(payload.team_name)

    saved_online_profile = None
    if selected_team is None:
        saved_online_profile = get_online_profile_by_name(payload.team_name)

    online = saved_online_profile["online_search"] if saved_online_profile else search_public_team_info(payload.team_name)
    if selected_team is None:
        if saved_online_profile:
            response = {
                "team_found": True,
                "team": saved_online_profile,
                "online_search": online,
                "pre_analysis": {
                    "summary": (
                        f"Pre-analise para {saved_online_profile['name']} baseada no perfil online salvo. "
                        "O dossie deve ser enriquecido com videos analisaveis antes da decisao final."
                    ),
                    "recommended_focus": [
                        f"Revisar fontes taticas salvas: {saved_online_profile['source_count']} referencia(s)",
                        "Coletar videos com camera aberta para homografia e tracking",
                        "Rastrear padroes de pressao, amplitude, profundidade e compactacao",
                    ],
                    "graph_insights": [
                        "Criar grafo inicial quando houver eventos de passe ou rastros do video",
                        "Priorizar conexoes recorrentes entre construcao, meia e ataque",
                        "Separar conexoes por fase: saida, progressao, ultimo terco e transicao",
                    ],
                    "computer_vision_insights": [
                        "Enviar videos para organizar trilhas, conexoes e heatmap por camada",
                        "Comparar amplitude, compactacao e ataques a profundidade por trecho",
                        "Usar eventos visuais para apoiar reuniao com comissao tecnica",
                    ],
                    "operational_research_insights": [
                        "Usar o perfil salvo como hipotese inicial, nao como decisao fechada",
                        "Otimizar formacao apos confirmar elenco disponivel e modelo recente",
                        "Comparar cenarios de risco por placar, mando, desgaste e estrategia adversaria",
                    ],
                },
                "save_ready": True,
            }
            return _with_llm_pre_analysis(payload, response)

        response = {
            "team_found": False,
            "team": {
                "name": payload.team_name,
                "league": payload.competition,
                "base_formation": "A definir",
                "confidence": "Baixo",
            },
            "online_search": online,
            "pre_analysis": {
                "summary": (
                    "Time nao encontrado na base local. A pre-analise usa busca tatica publica "
                    "e deve ser complementada com videos antes do relatorio final."
                ),
                "recommended_focus": [
                    "Separar videos por fase do jogo",
                    "Coletar trechos com boa visibilidade do campo",
                    "Mapear modelo tatico pelo comportamento visual antes de salvar",
                ],
                "graph_insights": [
                    "Criar grafo inicial de passes quando houver eventos de partida",
                    "Identificar jogadores centrais e conexoes recorrentes",
                ],
                "computer_vision_insights": [
                    "Coletar videos para futura deteccao de movimentacoes",
                    "Validar camera e qualidade de imagem antes de extrair tracking",
                ],
                "operational_research_insights": [
                    "Aguardar evidencias visuais suficientes para otimizar formacao",
                    "Definir objetivo tatico antes de comparar estrategias",
                ],
            },
            "save_ready": False,
        }
        return _with_llm_pre_analysis(payload, response)

    dossier = get_single_team_record(tactical_analysis(), selected_team["id"], "Dossie tatico")
    team_formations = get_team_records(formations(), selected_team["id"])
    team_players = get_team_records(players(), selected_team["id"])
    plan = get_single_team_record(game_plans(), selected_team["id"], "Plano de jogo")
    key_players = sorted(team_players, key=lambda item: item["tactical_score"], reverse=True)[:3]
    best_formation = max(team_formations, key=lambda item: item["probability"])

    response = {
        "team_found": True,
        "team": selected_team,
        "online_search": online,
        "pre_analysis": {
            "summary": (
                f"Pre-analise para {selected_team['name']} com foco em {payload.objective}. "
                f"A formacao mais provavel e {best_formation['formation']} e o nivel de confianca "
                f"do dossie e {dossier['confidence_level']}."
            ),
            "recommended_focus": [
                f"Priorizar estudo do modelo: {selected_team['style']}",
                f"Explorar: {', '.join(dossier['weaknesses'][:2])}",
                f"Neutralizar: {', '.join(player['name'] for player in key_players[:2])}",
            ],
            "graph_insights": [
                "Montar grafo de passes para medir conexoes entre volante, meia e extremos",
                "Usar centralidade para descobrir jogadores que sustentam a progressao",
                "Comparar densidade do grafo quando o adversario pressiona alto ou baixa bloco",
            ],
            "computer_vision_insights": [
                "Rastrear ocupacao dos cinco corredores e distancia entre linhas",
                "Detectar gatilhos de pressao, basculacao e ataques ao segundo pau",
                "Transformar movimentacoes em mapas de calor para a comissao tecnica",
            ],
            "operational_research_insights": [
                f"Testar {best_formation['formation']} como cenario-base pela maior aderencia ao contexto",
                "Otimizar estrategia ponderando risco defensivo, amplitude e jogadores disponiveis",
                "Comparar ajustes para vantagem, empate, desvantagem e queda fisica no segundo tempo",
            ],
            "best_formation": best_formation,
            "key_players": key_players,
            "game_plan_hint": plan["where_to_attack"],
        },
        "save_ready": True,
    }
    return _with_llm_pre_analysis(payload, response)


@router.post("/api/analysis", status_code=201)
def create(payload: AnalysisCreate):
    return create_analysis(payload.model_dump())


@router.get("/api/history")
def history():
    return list_history()


def _with_llm_pre_analysis(payload: AnalysisCreate, response: dict) -> dict:
    response["llm_pre_analysis"] = enrich_pre_analysis(
        payload.team_name,
        payload.objective,
        response.get("online_search") or {},
        response.get("pre_analysis") or {},
    )
    return response
