import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..database import (
    get_online_profile_by_id,
    get_online_profile_by_name,
    get_own_team_ref,
    list_history,
    list_online_profiles,
    save_online_profile,
    set_own_team_ref,
)
from ..graph_analysis import build_tactical_graph
from ..data_store import (
    find_single_team_record,
    find_team_by_name,
    formations,
    game_plans,
    get_single_team_record,
    get_team,
    get_team_records,
    players,
    search_teams,
    sources,
    tactical_analysis,
    teams,
)
from ..crud_store import create_record
from ..coach_intelligence import build_coach_insights
from ..llm_assistant import analyze_video_tactics, identify_players_from_tracks
from ..online_search import search_public_team_info
from ..operational_research import build_operational_research
from ..rate_limit import enforce_video_upload_rate_limit
from ..schemas import DetectedFormationSave, OnlineTeamProfileSave, OwnTeamSet, SourceCollectRequest
from ..source_collector import collect_sources, merge_sources_into_payload
from ..video_jobs import video_jobs
from ..video_vision import process_video
from ..wikipedia_lookup import fetch_team_wikipedia_profile


router = APIRouter(prefix="/api/teams", tags=["teams"])

MEDIA_DIR = Path(__file__).resolve().parents[2] / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_VIDEO_TYPES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
FREE_MODE = os.getenv("FOOTBALL_INTEL_FREE_MODE", "0").strip().casefold() in {"1", "true", "yes", "on"}
DEFAULT_MAX_UPLOAD_MB = 80 if FREE_MODE else 300
MAX_UPLOAD_MB = max(10, int(os.getenv("FOOTBALL_INTEL_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
DEFAULT_VIDEO_MAX_FRAMES = 120 if FREE_MODE else 240
DEFAULT_VIDEO_SAMPLE_EVERY = 4 if FREE_MODE else 3
MAX_VIDEO_FRAMES = 360 if FREE_MODE else 1200
VIDEO_PROCESSING_TIMEOUT_SECONDS = 25 if FREE_MODE else 35
# O processamento inclui a etapa de LLM depois do ultimo frame, entao a guarda
# de travamento precisa ser bem maior que o timeout de visao computacional.
VIDEO_JOB_STALL_SECONDS = 180
VIDEO_JOB_KEEPALIVE_SECONDS = 10


@router.get("")
@router.get("/")
def list_teams():
    return teams()


@router.get("/search")
def search(query: str = Query(default=""), category: str | None = Query(default=None)):
    local_results = search_teams(query)
    saved_profiles = list_online_profiles(query) if query.strip() else []
    if query.strip() and not local_results:
        online = search_public_team_info(query)
        profile = _online_profile_from_search(query, online)
        saved = get_online_profile_by_name(query)
        if saved:
            profile = saved
        results = [profile]
    else:
        local_names = {team["name"].casefold() for team in local_results}
        saved_without_duplicates = [
            profile for profile in saved_profiles if profile["name"].casefold() not in local_names
        ]
        results = local_results + saved_without_duplicates

    if category:
        results = [team for team in results if team.get("category", "Masculino").casefold() == category.casefold()]
    return results


@router.get("/online-search")
def search_online_by_name(name: str = Query(min_length=1)):
    online = search_public_team_info(name)
    saved = get_online_profile_by_name(name)
    profile = saved or _online_profile_from_search(name, online)
    return {
        "query": name.strip(),
        "saved": saved is not None,
        "profile": profile,
        "online_search": online,
    }


@router.get("/intelligence")
def team_intelligence_by_name(
    name: str = Query(min_length=1),
    perspective: str = Query(default="opponent", pattern="^(opponent|own_team)$"),
    game_state: str = Query(default="balanced", pattern="^(balanced|winning|drawing|losing)$"),
):
    """Fluxo único por nome: resolve base local/perfil salvo ou faz busca pública
    e devolve contexto do time + fontes + insights para a comissão técnica.
    """
    cleaned = " ".join(name.strip().split())
    local_team = find_team_by_name(cleaned)
    if local_team:
        workspace = _local_team_workspace(local_team)
    else:
        saved = get_online_profile_by_name(cleaned)
        if saved:
            workspace = _online_team_workspace(saved)
        else:
            online = search_public_team_info(cleaned)
            temporary_profile = _online_profile_from_search(cleaned, online)
            workspace = _online_team_workspace(temporary_profile)

    team = workspace["team"]
    operational = {}
    if workspace["kind"] == "local" and team.get("local_id"):
        operational = build_operational_research(team, workspace["players"], workspace["formations"])
    insights = build_coach_insights(
        team,
        workspace["dossier"],
        workspace["players"],
        workspace["formations"],
        workspace["plan"],
        workspace["graph"],
        workspace["public_intelligence"],
        operational,
        perspective=perspective,
        game_state=game_state,
    )
    return {
        "query": cleaned,
        "team": team,
        "kind": workspace["kind"],
        "sources": workspace["sources"],
        "public_intelligence": workspace["public_intelligence"],
        "coach_insights": insights,
    }


@router.get("/online-profiles")
def saved_online_profiles(query: str = Query(default="")):
    return list_online_profiles(query)


@router.post("/online-profiles", status_code=201)
def save_online_team_profile(payload: OnlineTeamProfileSave):
    online = payload.online_search or search_public_team_info(payload.team_name)
    return save_online_profile(
        {
            "team_name": payload.team_name,
            "country": payload.country,
            "league": payload.league,
            "coach": payload.coach,
            "base_formation": payload.base_formation,
            "style": payload.style,
            "confidence": payload.confidence,
            "status": payload.status,
            "category": payload.category or online.get("category"),
            "online_search": online,
        }
    )


@router.post("/sources/collect")
def collect_team_sources(payload: SourceCollectRequest):
    """Coleta fontes por link direto (scraping leve), palavra-chave (busca web
    publica) ou APIs publicas. Com save=true, mescla as fontes na coleta salva
    do time para que aparecam em todas as telas."""
    if payload.save and payload.sources:
        result = {
            "mode": payload.mode,
            "value": payload.value,
            "team_name": (payload.team_name or "").strip(),
            "status": "collected",
            "sources": payload.sources,
            "errors": [],
            "note": "Fontes já coletadas foram salvas na coleta do time.",
        }
    else:
        try:
            result = collect_sources(payload.mode, payload.value, payload.team_name or "")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    if payload.save and result["sources"]:
        team_name = (payload.team_name or "").strip()
        if not team_name:
            raise HTTPException(status_code=422, detail="Informe o time para salvar as fontes coletadas.")
        saved_profile = get_online_profile_by_name(team_name)
        online = (
            saved_profile["online_search"]
            if saved_profile and saved_profile.get("online_search")
            else _pending_tactical_collection(team_name)
        )
        merged = merge_sources_into_payload(online, result["sources"])
        profile = save_online_profile(
            {
                "team_name": team_name,
                "country": saved_profile.get("country") if saved_profile else None,
                "league": saved_profile.get("league") if saved_profile else None,
                "coach": saved_profile.get("coach") if saved_profile else None,
                "base_formation": saved_profile.get("base_formation") if saved_profile else None,
                "style": saved_profile.get("style") if saved_profile else None,
                "confidence": saved_profile.get("confidence") if saved_profile else None,
                "status": saved_profile.get("status") if saved_profile else "Coleta manual de fontes",
                "online_search": merged,
            }
        )
        result["saved"] = True
        result["profile"] = profile
    else:
        result["saved"] = False

    return result


@router.get("/options")
def team_options():
    local_options = [
        {
            "ref": str(team["id"]),
            "id": team["id"],
            "name": team["name"],
            "league": team["league"],
            "kind": "local",
            "status": team["status"],
            "confidence": team["confidence"],
            "category": team.get("category", "Masculino"),
            "source_count": len(get_team_records(sources(), team["id"])),
        }
        for team in teams()
    ]
    saved_options = [
        {
            "ref": f"online-{profile['online_profile_id']}",
            "id": profile["id"],
            "name": profile["name"],
            "league": profile["league"],
            "kind": "saved",
            "status": profile["status"],
            "confidence": profile["confidence"],
            "category": profile.get("category", "Masculino"),
            "source_count": profile["source_count"],
        }
        for profile in list_online_profiles()
    ]
    return {
        "default_ref": local_options[0]["ref"] if local_options else None,
        "options": local_options + saved_options,
    }


@router.get("/workspace/{team_ref}")
def team_workspace(team_ref: str):
    resolved = _resolve_team_reference(team_ref)
    if resolved["kind"] == "local":
        return _local_team_workspace(resolved["team"])
    return _online_team_workspace(resolved["profile"])


@router.get("/workspace/{team_ref}/coach-insights")
def workspace_coach_insights(
    team_ref: str,
    perspective: str = Query(default="opponent", pattern="^(opponent|own_team)$"),
    game_state: str = Query(default="balanced", pattern="^(balanced|winning|drawing|losing)$"),
):
    workspace = team_workspace(team_ref)
    team = workspace["team"]
    operational = {}
    if workspace["kind"] == "local" and team.get("local_id"):
        operational = build_operational_research(team, workspace["players"], workspace["formations"])
    return build_coach_insights(
        team,
        workspace["dossier"],
        workspace["players"],
        workspace["formations"],
        workspace["plan"],
        workspace["graph"],
        workspace["public_intelligence"],
        operational,
        perspective=perspective,
        game_state=game_state,
    )


@router.get("/own-team")
def get_own_team():
    return {"ref": get_own_team_ref()}


@router.put("/own-team")
def set_own_team(payload: OwnTeamSet):
    _resolve_team_reference(payload.ref)
    return {"ref": set_own_team_ref(payload.ref)}


@router.post("/video-vision/upload", dependencies=[Depends(enforce_video_upload_rate_limit)])
async def team_video_vision_upload_by_name(
    file: UploadFile = File(...),
    jersey_refs: list[UploadFile] | None = File(default=None),
    team_name: str = Query(min_length=1),
    max_frames: int = Query(default=DEFAULT_VIDEO_MAX_FRAMES, ge=60, le=MAX_VIDEO_FRAMES),
    sample_every: int = Query(default=DEFAULT_VIDEO_SAMPLE_EVERY, ge=1, le=30),
    team_filter: str = Query(default="auto"),
):
    return await _process_uploaded_video(
        file=file,
        team_name=team_name,
        max_frames=max_frames,
        sample_every=sample_every,
        team_filter=team_filter,
        jersey_refs=jersey_refs,
    )


@router.post("/video-vision/jobs", dependencies=[Depends(enforce_video_upload_rate_limit)])
async def team_video_vision_start_job_by_name(
    file: UploadFile = File(...),
    jersey_refs: list[UploadFile] | None = File(default=None),
    team_name: str = Query(min_length=1),
    max_frames: int = Query(default=DEFAULT_VIDEO_MAX_FRAMES, ge=60, le=MAX_VIDEO_FRAMES),
    sample_every: int = Query(default=DEFAULT_VIDEO_SAMPLE_EVERY, ge=1, le=30),
    team_filter: str = Query(default="auto"),
):
    return await _start_video_vision_job(
        file=file,
        team_name=team_name,
        max_frames=max_frames,
        sample_every=sample_every,
        team_filter=team_filter,
        jersey_refs=jersey_refs,
    )


@router.get("/video-vision/jobs/{job_id}/events")
async def team_video_vision_job_events(job_id: str):
    return StreamingResponse(
        _video_job_event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{team_id}")
def detail(team_id: int):
    return get_team(team_id)


@router.get("/{team_id}/tactical-analysis")
def team_tactical_analysis(team_id: int):
    return get_single_team_record(tactical_analysis(), team_id, "Dossie tatico")


@router.get("/{team_id}/formations")
def team_formations(team_id: int):
    return get_team_records(formations(), team_id)


@router.post("/{team_id}/formations/detected", status_code=201)
def save_detected_formation(team_id: int, payload: DetectedFormationSave):
    """Persiste como formação real do time uma estimativa vinda da visão
    computacional (shape_analysis de um video processado). E a via mais
    assertiva de coleta: em vez de cadastro manual, a formação nasce do
    rastreamento de jogadores em video de jogo de verdade."""
    get_team(team_id)  # 404 se o time não existir
    return create_record(
        "formations",
        {
            "team_id": team_id,
            "formation": payload.formation,
            "probability": payload.probability,
            "context": payload.context,
            "advantages": payload.advantages,
            "risks": payload.risks,
        },
    )


@router.get("/{team_id}/players")
def team_players(team_id: int):
    return get_team_records(players(), team_id)


@router.get("/{team_id}/sources")
def team_sources(team_id: int):
    return get_team_records(sources(), team_id)


@router.get("/{team_id}/operational-research")
def team_operational_research(team_id: int, formation: str | None = Query(default=None)):
    """Pesquisa operacional real sobre o elenco cadastrado: escalação ótima
    (problema de atribuição resolvido de forma exata) para a formação alvo e
    comparação de cenários entre as formações conhecidas do time."""
    team = get_team(team_id)
    return build_operational_research(
        team,
        get_team_records(players(), team_id),
        get_team_records(formations(), team_id),
        requested_formation=formation,
    )


@router.get("/{team_id}/graph-analysis")
def team_graph_analysis(team_id: int):
    team = get_team(team_id)
    return build_tactical_graph(team, get_team_records(players(), team_id), get_team_records(formations(), team_id))


@router.get("/{team_id}/coach-insights")
def team_coach_insights(
    team_id: int,
    perspective: str = Query(default="opponent", pattern="^(opponent|own_team)$"),
    game_state: str = Query(default="balanced", pattern="^(balanced|winning|drawing|losing)$"),
):
    """Consolida dados do time em recomendações explicáveis para treinador.

    perspective=opponent prepara o plano para enfrentar o time; own_team gera
    diagnóstico do próprio time. game_state adapta a recomendação ao placar.
    """
    team = get_team(team_id)
    team_players = get_team_records(players(), team_id)
    team_formations = get_team_records(formations(), team_id)
    dossier = find_single_team_record(tactical_analysis(), team_id) or _fallback_dossier(team, {})
    plan = find_single_team_record(game_plans(), team_id) or _fallback_plan(_collection_plan(team["name"]))
    saved_profile = get_online_profile_by_name(team["name"])
    online = saved_profile["online_search"] if saved_profile else _pending_tactical_collection(team["name"])
    graph = build_tactical_graph(team, team_players, team_formations)
    operational = build_operational_research(team, team_players, team_formations)
    return build_coach_insights(
        team,
        dossier,
        team_players,
        team_formations,
        plan,
        graph,
        online,
        operational,
        perspective=perspective,
        game_state=game_state,
    )


@router.post("/{team_id}/video-vision/upload", dependencies=[Depends(enforce_video_upload_rate_limit)])
async def team_video_vision_upload(
    team_id: int,
    file: UploadFile = File(...),
    jersey_refs: list[UploadFile] | None = File(default=None),
    max_frames: int = Query(default=DEFAULT_VIDEO_MAX_FRAMES, ge=60, le=MAX_VIDEO_FRAMES),
    sample_every: int = Query(default=DEFAULT_VIDEO_SAMPLE_EVERY, ge=1, le=30),
    team_filter: str = Query(default="auto"),
):
    """Recebe um video real do jogo, processa com visao computacional
    (OpenCV: deteccao de movimento + tracking) e devolve trilhas, heatmap,
    grafo de proximidade real e a URL do video anotado para reproducao."""
    team = get_team(team_id)
    return await _process_uploaded_video(
        file=file,
        team_name=team["name"],
        max_frames=max_frames,
        sample_every=sample_every,
        team_filter=team_filter,
        jersey_refs=jersey_refs,
    )


@router.post("/{team_id}/video-vision/jobs", dependencies=[Depends(enforce_video_upload_rate_limit)])
async def team_video_vision_start_job(
    team_id: int,
    file: UploadFile = File(...),
    jersey_refs: list[UploadFile] | None = File(default=None),
    max_frames: int = Query(default=DEFAULT_VIDEO_MAX_FRAMES, ge=60, le=MAX_VIDEO_FRAMES),
    sample_every: int = Query(default=DEFAULT_VIDEO_SAMPLE_EVERY, ge=1, le=30),
    team_filter: str = Query(default="auto"),
):
    """Inicia o processamento em segundo plano e devolve um job_id imediatamente.
    O progresso e acompanhado via GET /video-vision/jobs/{job_id}/events (SSE)."""
    team = get_team(team_id)
    return await _start_video_vision_job(
        file=file,
        team_name=team["name"],
        max_frames=max_frames,
        sample_every=sample_every,
        team_filter=team_filter,
        jersey_refs=jersey_refs,
    )


async def _save_uploaded_video(file: UploadFile) -> tuple[Path, int, str]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado ({extension}). Use: {', '.join(sorted(ALLOWED_VIDEO_TYPES))}.",
        )

    upload_name = f"upload_{uuid.uuid4().hex}{extension}"
    upload_path = MEDIA_DIR / upload_name

    size = 0
    with upload_path.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                buffer.close()
                upload_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Video excede o limite de {MAX_UPLOAD_MB}MB deste ambiente.")
            buffer.write(chunk)

    return upload_path, size, extension


def _build_video_result(result: dict, team_name: str) -> dict:
    result["team"] = team_name
    result["annotated_video_url"] = f"/media/{result['annotated_video_file']}"
    result["llm_analysis"] = analyze_video_tactics(team_name, result)
    result["llm_identity"] = identify_players_from_tracks(team_name, result)
    return result


async def _process_uploaded_video(
    *,
    file: UploadFile,
    team_name: str,
    max_frames: int,
    sample_every: int,
    team_filter: str,
    jersey_refs: list[UploadFile] | None,
):
    upload_path, size, extension = await _save_uploaded_video(file)

    effective_max_frames, effective_sample_every, upload_profile = _video_processing_profile(
        extension,
        size,
        max_frames,
        sample_every,
    )

    try:
        jersey_references = await _read_jersey_references(jersey_refs or [])
        result = process_video(
            str(upload_path),
            max_frames=effective_max_frames,
            sample_every=effective_sample_every,
            team_filter=team_filter,
            jersey_references=jersey_references,
            max_processing_seconds=VIDEO_PROCESSING_TIMEOUT_SECONDS,
        )
    except ValueError as error:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=(
                "Falha ao processar o video no pipeline de visao computacional. "
                "Tente reduzir frames, aumentar o intervalo entre frames ou enviar um recorte menor."
            ),
        ) from error
    finally:
        upload_path.unlink(missing_ok=True)

    result["upload_profile"] = upload_profile
    return _build_video_result(result, team_name)


async def _start_video_vision_job(
    *,
    file: UploadFile,
    team_name: str,
    max_frames: int,
    sample_every: int,
    team_filter: str,
    jersey_refs: list[UploadFile] | None,
) -> dict:
    upload_path, size, extension = await _save_uploaded_video(file)

    effective_max_frames, effective_sample_every, upload_profile = _video_processing_profile(
        extension,
        size,
        max_frames,
        sample_every,
    )
    jersey_references = await _read_jersey_references(jersey_refs or [])
    job = video_jobs.create(max_frames=effective_max_frames)

    def run_job() -> None:
        try:
            result = process_video(
                str(upload_path),
                max_frames=effective_max_frames,
                sample_every=effective_sample_every,
                team_filter=team_filter,
                jersey_references=jersey_references,
                max_processing_seconds=VIDEO_PROCESSING_TIMEOUT_SECONDS,
                on_progress=lambda processed, _total: video_jobs.update_progress(job.id, processed),
            )
            result["upload_profile"] = upload_profile
            video_jobs.complete(job.id, _build_video_result(result, team_name))
        except ValueError as error:
            video_jobs.fail(job.id, str(error))
        except Exception:
            video_jobs.fail(
                job.id,
                "Falha ao processar o video no pipeline de visao computacional. "
                "Tente reduzir frames, aumentar o intervalo entre frames ou enviar um recorte menor.",
            )
        finally:
            upload_path.unlink(missing_ok=True)

    threading.Thread(target=run_job, daemon=True).start()
    return {"job_id": job.id, "upload_profile": upload_profile}


async def _video_job_event_stream(job_id: str):
    last_processed = -1
    last_emit = time.monotonic()
    while True:
        job = video_jobs.get(job_id)
        if job is None:
            yield _sse_event({"status": "error", "message": "Job de processamento não encontrado ou já finalizado."})
            return

        if job.status == "processing":
            now = time.monotonic()
            if now - job.updated_at > VIDEO_JOB_STALL_SECONDS:
                video_jobs.fail(
                    job_id,
                    "O processamento parou de reportar progresso e foi encerrado. "
                    "Envie o video novamente, de preferencia um recorte menor.",
                )
                continue
            if job.processed != last_processed:
                last_processed = job.processed
                last_emit = now
                yield _sse_event(
                    {
                        "status": "processing",
                        "processed": job.processed,
                        "max_frames": job.max_frames,
                    }
                )
            elif now - last_emit > VIDEO_JOB_KEEPALIVE_SECONDS:
                # Comentario SSE: mantem proxies/load balancers sem derrubar a
                # conexao em trechos longos sem novo progresso (ex.: etapa LLM).
                last_emit = now
                yield ": keepalive\n\n"
            await asyncio.sleep(0.4)
            continue

        # O job finalizado NAO e descartado aqui: fica retido por um TTL curto
        # (video_jobs.FINISHED_JOB_TTL_SECONDS) para que uma reconexao do
        # navegador ainda receba o resultado se a conexao caiu no final.
        if job.status == "done":
            yield _sse_event({"status": "done", "result": job.result})
        else:
            yield _sse_event({"status": "error", "message": job.error})
        return


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _video_processing_profile(
    extension: str,
    size_bytes: int,
    requested_max_frames: int,
    requested_sample_every: int,
) -> tuple[int, int, dict]:
    size_mb = round(size_bytes / (1024 * 1024), 1)
    max_frames = requested_max_frames
    sample_every = requested_sample_every
    reasons = []

    if FREE_MODE:
        max_frames = min(max_frames, 120)
        sample_every = max(sample_every, 4)
        reasons.append("Modo gratuito ativo: processamento reduzido para economizar CPU e memoria.")

    if extension == ".mkv":
        max_frames = min(max_frames, 360)
        sample_every = max(sample_every, 3)
        reasons.append("MKV pode exigir mais decodificação; perfil seguro aplicado.")

    if size_bytes >= 180 * 1024 * 1024:
        max_frames = min(max_frames, 240)
        sample_every = max(sample_every, 4)
        reasons.append("Video acima de 180MB; processamento reduzido para evitar timeout.")
    elif size_bytes >= 100 * 1024 * 1024:
        max_frames = min(max_frames, 360)
        sample_every = max(sample_every, 3)
        reasons.append("Video acima de 100MB; amostragem ajustada para resposta mais estavel.")

    return (
        max_frames,
        sample_every,
        {
            "filename_profile": extension.removeprefix(".") or "video",
            "size_mb": size_mb,
            "requested_max_frames": requested_max_frames,
            "requested_sample_every": requested_sample_every,
            "effective_max_frames": max_frames,
            "effective_sample_every": sample_every,
            "timeout_seconds": VIDEO_PROCESSING_TIMEOUT_SECONDS,
            "safe_mode_applied": bool(reasons),
            "reasons": reasons,
        },
    )


async def _read_jersey_references(jersey_refs: list[UploadFile]) -> list[dict]:
    references = []
    for upload in jersey_refs[:6]:
        content_type = upload.content_type or ""
        suffix = Path(upload.filename or "").suffix.lower()
        if content_type and not content_type.startswith("image/"):
            continue
        if suffix and suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            continue
        content = await upload.read()
        if content:
            references.append({"filename": upload.filename or "camisa", "content": content})
    return references


@router.get("/{team_id}/public-intelligence")
def team_public_intelligence(team_id: int):
    team = get_team(team_id)
    return search_public_team_info(team["name"])


@router.get("/{team_id}/game-plan")
def team_game_plan(team_id: int):
    return get_single_team_record(game_plans(), team_id, "Plano de jogo")


def _team_crest_url(team_name: str, saved_profile: dict | None) -> str | None:
    if saved_profile and saved_profile.get("crest_url"):
        return saved_profile["crest_url"]
    wikipedia = fetch_team_wikipedia_profile(team_name)
    return wikipedia.get("crest_url") if wikipedia else None


def _online_profile_from_search(team_name: str, online: dict) -> dict:
    confidence = "Medio" if online.get("status") == "available" else "Baixo"
    return {
        "id": 0,
        "profile_type": "online",
        "name": team_name.strip(),
        "country": "Nao aplicado ao escopo visual",
        "league": "Fontes taticas e videos",
        "coach": "Nao coletado",
        "base_formation": "Detectar pelo video",
        "style": online.get("summary") or "Fontes taticas encontradas para revisao visual.",
        "confidence": confidence,
        "status": "Perfil tatico para pre-analise visual",
        "source_count": len(online.get("sources") or []),
        "category": online.get("category") or "Masculino",
        "crest_url": online.get("crest_url"),
        "online_search": online,
    }


def _resolve_team_reference(team_ref: str) -> dict:
    cleaned = str(team_ref).strip()
    if cleaned.isdigit():
        return {"kind": "local", "team": get_team(int(cleaned))}
    if cleaned.startswith("online-"):
        profile_id = cleaned.removeprefix("online-")
        if profile_id.isdigit():
            profile = get_online_profile_by_id(int(profile_id))
            if profile:
                return {"kind": "online", "profile": profile}
    profile = get_online_profile_by_name(cleaned)
    if profile:
        return {"kind": "online", "profile": profile}
    raise HTTPException(status_code=404, detail="Time ou fonte tática salva não encontrado.")


def _local_team_workspace(team: dict) -> dict:
    team_id = team["id"]
    saved_profile = get_online_profile_by_name(team["name"])
    online = saved_profile["online_search"] if saved_profile else _pending_tactical_collection(team["name"])
    local_sources = get_team_records(sources(), team_id)
    saved_sources = _online_sources_as_cards(online)
    # Time cadastrado sem dossiê/plano semeados (ex.: criado agora pela
    # Administração) não pode derrubar a tela inteira com 404: cai no mesmo
    # fallback usado para perfis online, até haver coleta real. Formações
    # ficam de fato vazias quando não há coleta - a tela mostra um estado
    # vazio acionavel em vez de um card generico "A definir" mascarando a
    # ausencia de dado real.
    dossier = find_single_team_record(tactical_analysis(), team_id) or _fallback_dossier(team, online)
    team_formations = get_team_records(formations(), team_id)
    team_players = get_team_records(players(), team_id)
    plan = find_single_team_record(game_plans(), team_id) or _fallback_plan(_collection_plan(team["name"]))
    history = [
        record
        for record in list_history()
        if record.get("team_id") == team_id or record.get("team_name", "").casefold() == team["name"].casefold()
    ]
    crest_url = _team_crest_url(team["name"], saved_profile)
    graph = build_tactical_graph(team, team_players, team_formations)
    operational = build_operational_research(team, team_players, team_formations)
    coach_insights = build_coach_insights(
        team, dossier, team_players, team_formations, plan, graph, online, operational
    )

    return {
        "ref": str(team_id),
        "kind": "local",
        "team": {**team, "ref": str(team_id), "local_id": team_id, "crest_url": crest_url},
        "saved_profile": saved_profile,
        "dossier": dossier,
        "formations": team_formations,
        "players": team_players,
        "sources": {
            "local": local_sources,
            "saved": saved_sources,
            "combined": local_sources + saved_sources,
        },
        "public_intelligence": online,
        "graph": graph,
        "plan": plan,
        "coach_insights": coach_insights,
        "history": history,
        "collection": _collection_status(local_sources, saved_sources, online, history),
    }


def _online_team_workspace(profile: dict) -> dict:
    online = profile.get("online_search") or _pending_tactical_collection(profile["name"])
    saved_sources = _online_sources_as_cards(online)
    collection_plan = online.get("collection_plan") or _collection_plan(profile["name"])
    history = [
        record
        for record in list_history()
        if record.get("team_name", "").casefold() == profile["name"].casefold()
    ]
    team = {
        "id": profile["id"],
        "ref": (
            f"online-{profile['online_profile_id']}"
            if profile.get("online_profile_id")
            else f"search-{profile['name'].strip().casefold().replace(' ', '-')}"
        ),
        "local_id": None,
        "profile_type": "online",
        "name": profile["name"],
        "country": profile["country"],
        "league": profile["league"],
        "coach": profile["coach"],
        "base_formation": profile["base_formation"],
        "style": profile["style"],
        "confidence": profile["confidence"],
        "status": profile["status"],
        "category": profile.get("category", "Masculino"),
        "crest_url": profile.get("crest_url"),
    }
    dossier = _fallback_dossier(profile, online)
    plan = _fallback_plan(collection_plan)
    fallback_formations = _fallback_formations(profile)
    graph = _source_graph(profile, online)
    coach_insights = build_coach_insights(
        team, dossier, [], fallback_formations, plan, graph, online, {}
    )

    return {
        "ref": team["ref"],
        "kind": "saved" if profile.get("online_profile_id") else "online",
        "team": team,
        "saved_profile": profile,
        "dossier": dossier,
        "formations": fallback_formations,
        "players": [],
        "sources": {
            "local": [],
            "saved": saved_sources,
            "combined": saved_sources,
        },
        "public_intelligence": online,
        "graph": graph,
        "plan": plan,
        "coach_insights": coach_insights,
        "history": history,
        "collection": _collection_status([], saved_sources, online, history),
    }


def _online_sources_as_cards(online: dict) -> list[dict]:
    retrieved_at = online.get("retrieved_at") or "2026-01-01T00:00:00+00:00"
    cards = []
    for source in online.get("sources") or []:
        cards.append(
            {
                "title": source.get("title") or "Fonte tatica",
                "type": source.get("origin") or "Fonte tatica",
                "source": source.get("url") or source.get("origin") or "Fonte salva",
                "date": retrieved_at,
                "relevance": source.get("relevance") or "Media",
                "summary": source.get("summary") or "Fonte salva para validação visual.",
                "category": source.get("category") or "team_form",
            }
        )
    return cards


def _collection_status(local_sources: list[dict], saved_sources: list[dict], online: dict, history: list[dict]) -> dict:
    coverage = online.get("coverage") or {}
    return {
        "local_source_count": len(local_sources),
        "saved_source_count": len(saved_sources),
        "history_count": len(history),
        "video_reference_count": coverage.get("match_videos", 0) + coverage.get("analysis_videos", 0),
        "pattern_reference_count": coverage.get("team_form", 0),
        "status": "com_coleta_salva" if saved_sources else "pendente_de_coleta",
        "to_collect": online.get("collection_plan") or [],
        "focus": online.get("analysis_focus") or [],
    }


def _pending_tactical_collection(team_name: str) -> dict:
    return {
        "status": "not_collected",
        "query": f"{team_name} futebol analise tatica videos",
        "summary": (
            f"Ainda não há fontes táticas salvas para {team_name}. Use a busca online ou envie vídeos "
            "para iniciar a coleta visual."
        ),
        "sources": [],
        "source_groups": {"match_videos": [], "analysis_videos": [], "team_form": []},
        "coverage": {"match_videos": 0, "analysis_videos": 0, "team_form": 0},
        "analysis_focus": [
            "Coletar vídeos com câmera aberta para rastrear linhas, bola e movimentação coletiva.",
            "Separar trechos por fase: posse, pressao, transicao, ultimo terco e bola parada.",
            "Salvar fontes taticas para que todas as telas usem o mesmo material de apoio.",
        ],
        "collection_plan": _collection_plan(team_name),
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "errors": [],
        "note": "Sem fonte tatica salva para este time.",
    }


def _collection_plan(team_name: str) -> list[dict]:
    return [
        {"stage": "Videos", "action": f"Buscar jogos completos e melhores momentos recentes de {team_name}."},
        {"stage": "Recortes", "action": "Separar lances de pressão, construção, transição e finalização."},
        {"stage": "Visao computacional", "action": "Enviar videos para gerar tracking, heatmap, grafo e eventos."},
        {"stage": "Revisao", "action": "Salvar fontes e comparar os achados nas telas de dossie, fontes e relatorio."},
    ]


def _fallback_dossier(profile: dict, online: dict) -> dict:
    focus = online.get("analysis_focus") or []
    return {
        "confidence_level": profile.get("confidence") or "Baixo",
        "summary": profile.get("style") or online.get("summary") or "Dossie visual ainda em coleta.",
        "offensive_model": focus[0] if focus else "Modelo ofensivo deve ser extraido dos videos salvos/enviados.",
        "defensive_model": "Mapear bloco, distancia entre linhas e gatilhos de pressao por visao computacional.",
        "offensive_transition": "Identificar progressão após recuperação pela trilha da bola e dos rastros.",
        "defensive_transition": "Detectar recomposição, contrapressão e compactação após perda.",
        "set_pieces": "Coletar recortes de bola parada para analise separada.",
        "formation_variations": [profile.get("base_formation") or "Detectar pelo video"],
        "strengths": focus[:3] or ["Fontes taticas salvas para orientar a revisao visual."],
        "weaknesses": [
            "Ainda faltam eventos extraidos de video para confirmar padroes.",
            "Formação e funções dependem de tracking e homografia por partida.",
        ],
    }


def _fallback_formations(profile: dict, team_id: int = 0) -> list[dict]:
    formation = profile.get("base_formation") or "Detectar pelo video"
    return [
        {
            "team_id": team_id,
            "formation": formation,
            "probability": 40 if formation != "Detectar pelo video" else 20,
            "context": "Hipotese inicial ate haver videos processados.",
            "advantages": "Permite organizar a revisão, mas não substitui a leitura visual.",
            "risks": "Baixa confianca sem tracking, bola e homografia do video.",
        }
    ]


def _fallback_plan(collection_plan: list[dict]) -> dict:
    actions = [item["action"] for item in collection_plan]
    return {
        "how_to_press": "Definir apos observar gatilhos reais de pressao nos videos.",
        "where_to_attack": "Definir após mapa de ocupação, bola e rede de conexões.",
        "players_to_neutralize": ["A identificar por centralidade visual"],
        "weaknesses_to_exploit": ["A confirmar por recorrencia de padroes nos videos"],
        "training_suggestions": actions[:3],
        "plan_risks": ["Plano ainda depende de evidencias visuais suficientes."],
        "in_match_adjustments": ["Revisar grafo, heatmap e eventos antes da decisao final."],
    }


def _source_graph(profile: dict, online: dict) -> dict:
    sources_by_category = online.get("source_groups") or {}
    nodes = [
        {"id": "team", "label": profile["name"], "type": "team", "x": 50, "y": 50, "score": 70},
    ]
    categories = [
        ("match_videos", "Videos de jogos", 22, 30),
        ("analysis_videos", "Analises taticas", 78, 30),
        ("team_form", "Padroes de jogo", 50, 78),
    ]
    edges = []
    for key, label, x, y in categories:
        count = len(sources_by_category.get(key) or [])
        nodes.append({"id": key, "label": label, "type": "source", "x": x, "y": y, "score": count})
        if count:
            edges.append({"source": "team", "target": key, "weight": max(12, count * 12), "label": "fonte salva"})

    return {
        "formation": {"formation": profile.get("base_formation") or "Detectar pelo video"},
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "centrality_leader": profile["name"],
            "network_density": round(len(edges) / 3 * 100, 1),
            "progression_lane": "A detectar por video",
            "risk_lane": "A confirmar",
        },
        "insights": [
            "O grafo atual mostra fontes coletadas por categoria.",
            "Envie videos para substituir esta rede de fontes por conexoes reais de movimento.",
            "Use as fontes salvas como fila de coleta e validacao visual.",
        ],
    }
