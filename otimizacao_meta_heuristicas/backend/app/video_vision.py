"""
Visão computacional real sobre vídeo enviado pelo usuário.

Pipeline:
1. Lê o vídeo com OpenCV, amostrando frames distribuídos do início ao fim
   (via seek). A duração real é obtida por sondagem direta no decodificador
   (busca exponencial + binária), não apenas pelos metadados do container
   (CAP_PROP_FRAME_COUNT), que podem ser 0/errados em gravações de celular
   ou webm não finalizado - assim a análise representa o vídeo completo
   enviado e não apenas os primeiros segundos.
2. Detecta objetos em movimento por Background Subtraction (MOG2).
3. Faz tracking simples por centróide (nearest-neighbor entre frames).
4. Acumula heatmap real de ocupação (grid normalizado 0-100).
5. Gera vídeo anotado (bounding boxes + ID + trilha) em MP4.
6. Constrói grafo de proximidade real (networkx) entre os tracks:
   nos = jogadores/objetos detectados, arestas = coocorrencia espacial
   (ficaram proximos no campo durante o video), peso = frequencia.
7. Detecta "eventos" como picos de velocidade (sprints/mudancas bruscas).

Sem chamadas a API externa paga: usa apenas algoritmos classicos de CV
(cv2.createBackgroundSubtractorMOG2 + contornos), entao roda offline,
sem depender de modelo pre-treinado baixado da internet.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
import math
import time
import uuid
from pathlib import Path

import cv2
import networkx as nx
import numpy as np

MEDIA_DIR = Path(__file__).resolve().parents[1] / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

GRID_W, GRID_H = 100, 100
MAX_TRACK_DISTANCE = 80
MIN_CONTOUR_AREA = 350
MIN_TRACK_DISTANCE = 35
MAX_MOVEMENT_TRACKS = 18
PROXIMITY_THRESHOLD = 90
# Rastro sem correspondencia por este numero de frames processados deixa de
# concorrer no matching: um jogador que saiu do enquadramento nao pode
# "roubar" a deteccao de quem entrou perto da ultima posicao dele.
MAX_TRACK_MISSES = 10
# Amortecimento da predicao por velocidade constante (0 = sem predicao,
# 1 = extrapolacao completa do ultimo deslocamento).
VELOCITY_PREDICTION_DAMPING = 0.8
# A bola nao teleporta: candidato muito distante da ultima posicao conhecida
# so e aceito depois que a bola fica alguns frames sem deteccao.
BALL_MAX_JUMP_PX_RATIO = 0.22
BALL_MISS_TOLERANCE = 6
PITCH_W, PITCH_H = 105, 68
DEFAULT_PROCESSING_TIMEOUT_SECONDS = 35
MAX_PLAYER_BOX_WIDTH_RATIO = 0.18
MAX_PLAYER_BOX_HEIGHT_RATIO = 0.62
MIN_PLAYER_BOX_HEIGHT_RATIO = 0.025
TEAM_FILTER_OPTIONS = [
    {"key": "reference", "label": "Camisas enviadas"},
    {"key": "auto", "label": "Automatico - uniforme dominante"},
    {"key": "all", "label": "Todas as equipes"},
    {"key": "light", "label": "Uniforme claro em campo"},
    {"key": "dark", "label": "Uniforme escuro"},
    {"key": "red", "label": "Uniforme vermelho"},
    {"key": "blue", "label": "Uniforme azul"},
    {"key": "green", "label": "Uniforme verde"},
    {"key": "yellow", "label": "Uniforme amarelo"},
    {"key": "orange", "label": "Uniforme laranja"},
    {"key": "purple", "label": "Uniforme roxo"},
]
TEAM_FILTER_KEYS = {option["key"] for option in TEAM_FILTER_OPTIONS}
TEAM_COLOR_BGR = {
    "light": (245, 245, 245),
    "dark": (20, 24, 32),
    "red": (42, 58, 220),
    "blue": (220, 112, 40),
    "green": (86, 172, 68),
    "yellow": (54, 190, 240),
    "orange": (36, 132, 235),
    "purple": (190, 84, 170),
    "reference": (58, 162, 216),
    "unknown": (190, 190, 190),
}
EVENT_TARGETS = [
    {
        "key": "probable_pass",
        "label": "Passe provavel",
        "description": "Bola se desloca entre zonas proximas a dois jogadores/objetos rastreados.",
    },
    {
        "key": "probable_shot",
        "label": "Finalizacao provavel",
        "description": "Bola acelera em direcao a zona de gol ou ultimo terco.",
    },
    {
        "key": "carry_or_dribble",
        "label": "Drible/conducao",
        "description": "Mesmo jogador/objeto progride com movimento continuo em velocidade relevante.",
    },
    {
        "key": "tackle_or_duel",
        "label": "Desarme/disputa",
        "description": "Dois ou mais rastros ficam muito proximos em trecho curto.",
    },
    {
        "key": "potential_foul",
        "label": "Falta potencial",
        "description": "Disputa seguida de queda brusca de movimento ou aglomeracao local.",
    },
    {
        "key": "counter_press",
        "label": "Pressao pos-perda",
        "description": "Aglomeracao e aceleracao coletiva imediatamente apos deslocamento da bola.",
    },
]


class _Track:
    __slots__ = ("id", "points", "pitch_points", "boxes", "team_counts", "last_seen", "missed")

    def __init__(
        self,
        track_id: int,
        x: float,
        y: float,
        frame_idx: int,
        pitch_x: float,
        pitch_y: float,
        box: tuple[int, int, int, int],
    ):
        self.id = track_id
        self.points: list[tuple[int, float, float]] = [(frame_idx, x, y)]
        self.pitch_points: list[tuple[int, float, float]] = [(frame_idx, pitch_x, pitch_y)]
        self.boxes: list[tuple[int, int, int, int]] = [box]
        self.team_counts: Counter[str] = Counter()
        self.last_seen = frame_idx
        self.missed = 0

    @property
    def last_pos(self) -> tuple[float, float]:
        return self.points[-1][1], self.points[-1][2]

    @property
    def predicted_pos(self) -> tuple[float, float]:
        """Posicao esperada no proximo frame processado (modelo de velocidade
        constante amortecido, como no SORT). Reduz trocas de ID quando dois
        jogadores se cruzam: cada rastro procura a deteccao na direcao em que
        ja vinha se movendo, nao apenas a mais proxima da ultima posicao."""
        if len(self.points) < 2:
            return self.last_pos
        _, x1, y1 = self.points[-2]
        _, x2, y2 = self.points[-1]
        return (
            x2 + (x2 - x1) * VELOCITY_PREDICTION_DAMPING,
            y2 + (y2 - y1) * VELOCITY_PREDICTION_DAMPING,
        )


def _probe_total_frames(capture, reported_total_frames: int) -> int:
    """Find the real number of readable frames via direct seek+read probing.

    Container/codec frame-count metadata (CAP_PROP_FRAME_COUNT) is frequently
    wrong or absent for phone recordings and browser-captured video (VFR,
    unfinalized moov atom, etc.). Trusting it caused long uploads to only be
    analyzed up to whatever (possibly too-short) frame count the metadata
    claimed. This does an exponential-then-binary search directly against the
    decoder instead, so coverage is correct regardless of metadata quality.
    Returns -1 if the capture does not support seeking at all (rare), which
    signals the caller to fall back to plain sequential reading.
    """

    def can_read_at(index: int) -> bool:
        if index < 0:
            return False
        if not capture.set(cv2.CAP_PROP_POS_FRAMES, float(index)):
            return False
        ok, _ = capture.read()
        return ok

    if not can_read_at(0):
        return -1

    hi = max(reported_total_frames, 1)
    if not can_read_at(hi - 1):
        # Metadata overestimated (or was 0/unknown): binary search downward
        # for the last readable frame within [0, hi).
        lo, bound = 0, hi
        while lo < bound:
            mid = (lo + bound) // 2
            if can_read_at(mid):
                lo = mid + 1
            else:
                bound = mid
        return max(lo, 1)

    # Metadata frame is readable - probe further in case it underestimated
    # the real length (exponential search for the true end).
    probe = hi
    while probe < 5_000_000 and can_read_at(probe * 2 - 1):
        probe *= 2
    lo, bound = probe, probe * 2
    while lo < bound:
        mid = (lo + bound + 1) // 2
        if can_read_at(mid - 1):
            lo = mid
        else:
            bound = mid - 1
    return lo


def process_video(
    video_path: str,
    max_frames: int = 600,
    sample_every: int = 2,
    team_filter: str = "auto",
    jersey_references: list[dict] | None = None,
    max_processing_seconds: int | None = DEFAULT_PROCESSING_TIMEOUT_SECONDS,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    started_at = time.monotonic()
    stopped_by_timeout = False
    requested_team_filter = _normalize_team_filter(team_filter)
    jersey_reference_profiles = _build_jersey_reference_profiles(jersey_references or [])
    if jersey_reference_profiles and requested_team_filter == "auto":
        requested_team_filter = "reference"
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("Nao foi possivel abrir o arquivo de video enviado.")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 360

    requested_sample_every = sample_every
    reported_total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    probed_total_frames = _probe_total_frames(capture, reported_total_frames)
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    full_video_coverage = probed_total_frames > 0
    source_total_frames = probed_total_frames if full_video_coverage else 0
    if full_video_coverage and source_total_frames > max_frames:
        # Spread the sampled frames across the whole video (seek-based) instead of
        # only reading sequentially from the start, so long matches are analyzed
        # end to end rather than just their first few seconds.
        sample_every = max(sample_every, -(-source_total_frames // max_frames))

    bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=32, detectShadows=False)

    output_fps = max(1.0, fps / sample_every)
    writer, output_name, _, output_mime, output_codec = _open_browser_video_writer(width, height, output_fps)

    tracks: dict[int, _Track] = {}
    next_track_id = 0
    heat_grid = [[0 for _ in range(GRID_W)] for _ in range(GRID_H)]
    ball_grid = [[0 for _ in range(GRID_W)] for _ in range(GRID_H)]
    proximity_counts: dict[tuple[int, int], int] = {}
    events: list[dict] = []
    tactical_events: list[dict] = []
    ball_track: list[dict] = []
    tactic_counts: Counter[str] = Counter()
    last_tactic: str | None = None
    field_samples = 0
    uniform_counts: Counter[str] = Counter()
    candidate_rejections: Counter[str] = Counter()
    last_field_model = _default_field_model(width, height)

    frame_idx = 0
    processed = 0
    colors: dict[int, tuple[int, int, int]] = {}
    last_ball_px: tuple[float, float] | None = None
    ball_misses = 0

    while processed < max_frames:
        if max_processing_seconds and time.monotonic() - started_at >= max_processing_seconds:
            stopped_by_timeout = True
            break

        if full_video_coverage:
            if frame_idx >= source_total_frames:
                break
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

        ok, frame = capture.read()
        if not ok:
            break
        if not full_video_coverage and frame_idx % sample_every != 0:
            frame_idx += 1
            continue

        field_model = _detect_field_model(frame, width, height) or last_field_model
        if field_model["detected"]:
            field_samples += 1
            last_field_model = field_model
        ball = _detect_ball(frame, field_model, last_ball_px if ball_misses <= BALL_MISS_TOLERANCE else None, width)
        if ball:
            last_ball_px = (ball["x"], ball["y"])
            ball_misses = 0
            ball_track.append(
                {
                    "frame": frame_idx,
                    "time_s": round(frame_idx / fps, 1),
                    "x": ball["pitch_x"],
                    "y": ball["pitch_y"],
                    "confidence": ball["confidence"],
                }
            )
            grid_x = min(GRID_W - 1, int(ball["pitch_x"] / 100 * GRID_W))
            grid_y = min(GRID_H - 1, int(ball["pitch_y"] / 100 * GRID_H))
            ball_grid[grid_y][grid_x] += 1
        else:
            ball_misses += 1

        mask = bg_subtractor.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        mask = cv2.dilate(mask, None, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < MIN_CONTOUR_AREA:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            cx, cy = x + w / 2, y + h / 2
            field_gate = _field_candidate_gate(x, y, w, h, width, height, field_model)
            if not field_gate["accepted"]:
                candidate_rejections[field_gate["reason"]] += 1
                continue
            uniform = _classify_uniform_color(frame, (x, y, w, h), jersey_reference_profiles)
            detections.append((cx, cy, x, y, w, h, uniform))
            if uniform["key"] != "unknown":
                uniform_counts[uniform["key"]] += 1

        # Atribuicao global deteccao<->rastro: todos os pares candidatos sao
        # ordenados por distancia a posicao PREVISTA do rastro e consumidos do
        # menor para o maior. Isso remove o vies de ordem do matching guloso
        # por deteccao (a primeira deteccao da lista "roubava" o rastro mais
        # proximo mesmo quando outra deteccao combinava melhor com ele).
        matchable_tracks = {
            track_id: track for track_id, track in tracks.items() if track.missed <= MAX_TRACK_MISSES
        }
        candidate_pairs = []
        for det_index, (cx, cy, *_rest) in enumerate(detections):
            for track_id, track in matchable_tracks.items():
                px, py = track.predicted_pos
                dist = math.hypot(cx - px, cy - py)
                if dist < MAX_TRACK_DISTANCE:
                    candidate_pairs.append((dist, det_index, track_id))
        candidate_pairs.sort(key=lambda item: item[0])

        detection_to_track: dict[int, int] = {}
        assigned_tracks: set[int] = set()
        for _, det_index, track_id in candidate_pairs:
            if det_index in detection_to_track or track_id in assigned_tracks:
                continue
            detection_to_track[det_index] = track_id
            assigned_tracks.add(track_id)

        frame_active_tracks = []
        for det_index, (cx, cy, x, y, w, h, uniform) in enumerate(detections):
            pitch_x, pitch_y = _map_to_pitch(cx, cy, field_model)
            best_id = detection_to_track.get(det_index)

            if best_id is None:
                best_id = next_track_id
                next_track_id += 1
                tracks[best_id] = _Track(best_id, cx, cy, frame_idx, pitch_x, pitch_y, (x, y, w, h))
                colors[best_id] = _color_for(best_id)
            else:
                prev_x, prev_y = tracks[best_id].last_pos
                speed = math.hypot(cx - prev_x, cy - prev_y)
                if speed > 40:
                    events.append(
                        {
                            "frame": frame_idx,
                            "time_s": round(frame_idx / fps, 1),
                            "track_id": best_id,
                            "type": "carry_or_dribble",
                            "label": "Drible/conducao",
                            "speed_px_frame": round(speed, 1),
                            "confidence": "Media",
                            "explanation": (
                                "Rastro acelerou com continuidade. Pode indicar conducao, drible, "
                                "ataque ao espaco ou disputa em velocidade."
                            ),
                        }
                    )
                tracks[best_id].points.append((frame_idx, cx, cy))
                tracks[best_id].pitch_points.append((frame_idx, pitch_x, pitch_y))
                tracks[best_id].boxes.append((x, y, w, h))
                tracks[best_id].last_seen = frame_idx

            tracks[best_id].missed = 0
            tracks[best_id].team_counts[uniform["key"]] += 1
            track_team_key = _track_team_key(tracks[best_id])
            frame_active_tracks.append((best_id, cx, cy, x, y, w, h, pitch_x, pitch_y, track_team_key))

        for track_id, track in matchable_tracks.items():
            if track_id not in assigned_tracks:
                track.missed += 1

        current_target_key = _selected_team_key(requested_team_filter, uniform_counts)
        frame_target_tracks = [
            track
            for track in frame_active_tracks
            if _track_matches_team(tracks[track[0]], requested_team_filter, current_target_key)
        ]

        for _, _, _, _, _, _, _, pitch_x, pitch_y, _ in frame_target_tracks:
            grid_x = min(GRID_W - 1, int(pitch_x / 100 * GRID_W))
            grid_y = min(GRID_H - 1, int(pitch_y / 100 * GRID_H))
            heat_grid[grid_y][grid_x] += 1

        for i in range(len(frame_target_tracks)):
            for j in range(i + 1, len(frame_target_tracks)):
                id_a, xa, ya = frame_target_tracks[i][0:3]
                id_b, xb, yb = frame_target_tracks[j][0:3]
                distance = math.hypot(xa - xb, ya - yb)
                if distance <= PROXIMITY_THRESHOLD:
                    key = (min(id_a, id_b), max(id_a, id_b))
                    proximity_counts[key] = proximity_counts.get(key, 0) + 1
                if distance <= PROXIMITY_THRESHOLD * 0.42 and processed % 18 == 0:
                    events.append(
                        {
                            "frame": frame_idx,
                            "time_s": round(frame_idx / fps, 1),
                            "track_id": id_a,
                            "type": "tackle_or_duel",
                            "label": "Desarme/disputa",
                            "confidence": "Baixa",
                            "explanation": (
                                "Dois rastros ficaram muito proximos. Sem modelo de pose/arbitragem, "
                                "classificacao permanece como disputa potencial."
                            ),
                        }
                    )

        tactic = _classify_tactic(frame_target_tracks, width, height)
        if frame_target_tracks:
            tactic_counts[tactic] += 1
            if tactic != last_tactic or processed % 45 == 0:
                tactical_events.append(
                    {
                        "time_s": round(frame_idx / fps, 1),
                        "type": tactic,
                        "active_tracks": len(frame_target_tracks),
                        "finding": _tactic_finding(tactic),
                    }
                )
                last_tactic = tactic

        _draw_tactical_overlay(
            frame,
            width,
            height,
            tactic,
            field_model,
            ball,
            _team_filter_label(current_target_key or requested_team_filter),
        )

        for track_id, cx, cy, x, y, w, h, _, _, track_team_key in frame_target_tracks:
            color = TEAM_COLOR_BGR.get(track_team_key, colors[track_id])
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame,
                f"ID {track_id} {_team_filter_label(track_team_key)}",
                (x, max(0, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )
            trail = list(tracks[track_id].points[-30:])
            for k in range(1, len(trail)):
                _, x1, y1 = trail[k - 1]
                _, x2, y2 = trail[k]
                cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

        writer.write(frame)
        processed += 1
        frame_idx += sample_every if full_video_coverage else 1
        if on_progress:
            on_progress(processed, max_frames)

    capture.release()
    writer.release()

    track_stats = [
        (tid, track, _track_distance(track))
        for tid, track in tracks.items()
        if len(track.points) >= 5 and _track_distance(track) >= MIN_TRACK_DISTANCE
    ]
    if not track_stats:
        track_stats = [
            (tid, track, _track_distance(track))
            for tid, track in tracks.items()
            if len(track.points) >= 5
        ]

    final_target_key = _selected_team_key(requested_team_filter, uniform_counts)
    target_track_stats = [
        (tid, track, distance)
        for tid, track, distance in track_stats
        if _track_matches_team(track, requested_team_filter, final_target_key)
    ]
    valid_tracks = {tid: track for tid, track, _ in target_track_stats}
    top_tracks = sorted(target_track_stats, key=lambda item: (item[2], len(item[1].points)), reverse=True)[
        :MAX_MOVEMENT_TRACKS
    ]

    movement_tracks = [
        {
            "id": tid,
            "label": f"Jogador/objeto {tid}",
            "points": [
                {"x": round(px / width * 100, 1), "y": round(py / height * 100, 1)}
                for _, px, py in track.points[::max(1, len(track.points) // 40)]
            ],
            "pitch_points": [
                {"x": round(px, 1), "y": round(py, 1)}
                for _, px, py in track.pitch_points[::max(1, len(track.pitch_points) // 40)]
            ],
            "total_samples": len(track.points),
            "distance_px": round(distance, 1),
            "role_hint": _role_hint(track),
            "team_key": _track_team_key(track),
            "team_label": _team_filter_label(_track_team_key(track)),
            "team_confidence": _track_team_confidence(track),
        }
        for tid, track, distance in top_tracks
    ]

    heatmap = _grid_to_points(heat_grid)
    ball_heatmap = _grid_to_points(ball_grid)
    events.extend(_infer_ball_events(ball_track, valid_tracks))
    events = [event for event in events if event.get("track_id") in valid_tracks or event.get("track_id") is None]
    graph = _build_proximity_graph(valid_tracks, proximity_counts)
    shape_analysis = _build_shape_analysis(valid_tracks)
    team_focus = _build_team_focus(
        requested_team_filter,
        final_target_key,
        uniform_counts,
        track_stats,
        valid_tracks,
        candidate_rejections,
    )
    processing_time_seconds = round(time.monotonic() - started_at, 2)

    return {
        "status": "processed",
        "processing_mode": "batch_local_opencv",
        "processing_config": {
            "max_frames": max_frames,
            "sample_every": sample_every,
            "requested_sample_every": requested_sample_every,
            "source_total_frames": source_total_frames,
            "full_video_coverage": full_video_coverage,
            "coverage_mode": "uniforme_video_completo" if full_video_coverage else "sequencial_desde_inicio",
            "team_filter": requested_team_filter,
            "selected_team_key": final_target_key,
            "min_contour_area": MIN_CONTOUR_AREA,
            "event_targets": [target["key"] for target in EVENT_TARGETS],
            "max_processing_seconds": max_processing_seconds,
            "processing_time_seconds": processing_time_seconds,
            "stopped_by_timeout": stopped_by_timeout,
        },
        "team_focus_options": TEAM_FILTER_OPTIONS,
        "team_focus": team_focus,
        "jersey_reference": {
            "enabled": bool(jersey_reference_profiles),
            "count": len(jersey_reference_profiles),
            "profiles": [
                {
                    "label": profile["label"],
                    "key": profile["key"],
                    "confidence_base": profile["confidence_base"],
                }
                for profile in jersey_reference_profiles
            ],
            "note": (
                "As imagens de camisa viram uma assinatura HSV e sao combinadas com o filtro dentro do campo. "
                "Use fotos/crops da camisa sem fundo, torcida ou placas para maior precisao."
            ),
        },
        "field_candidate_filter": {
            "enabled_when_field_detected": True,
            "rejections": dict(candidate_rejections),
            "strategy": (
                "Antes da cor do uniforme, o detector exige caixa plausivel de jogador e base do rastro dentro "
                "do poligono/homografia do campo quando o gramado e detectado."
            ),
        },
        "event_targets": EVENT_TARGETS,
        "source_fps": round(fps, 1),
        "output_fps": round(output_fps, 1),
        "frames_analyzed": processed,
        "video_width": width,
        "video_height": height,
        "annotated_video_file": output_name,
        "annotated_video_mime": output_mime,
        "annotated_video_codec": output_codec,
        "tracks_detected": len(valid_tracks),
        "movement_tracks_shown": len(movement_tracks),
        "movement_tracks": movement_tracks,
        "heatmap": heatmap,
        "ball_track": ball_track[::max(1, len(ball_track) // 80)] if ball_track else [],
        "ball_heatmap": ball_heatmap,
        "events": sorted(events, key=lambda e: e["time_s"])[:50],
        "graph": graph,
        "field_model": {
            **last_field_model,
            "samples_detected": field_samples,
            "detection_rate": round(field_samples / max(1, processed) * 100, 1),
        },
        "shape_analysis": shape_analysis,
        "visual_report": {
            "output_format": "dashboard_interativo_com_overlay_de_video_e_campo_2d",
            "scope": (
                "Analise restrita ao conteudo visual do video: estilo de jogo, padroes taticos, "
                "movimentacao coletiva/individual e funcao espacial dos rastros."
            ),
            "processing_note": (
                "Processamento local em batch com OpenCV em CPU. Para maior precisao, conectar YOLO/Ultralytics "
                "para deteccao supervisionada, ByteTrack/DeepSORT para tracking robusto e calibracao de campo "
                "por linhas oficiais."
            ),
            "event_detection_note": (
                "Eventos sao inferencias visuais heuristicas, nao dados institucionais nem scouting externo."
            ),
        },
        "player_identity_strategy": _player_identity_strategy(),
        "tactical_summary": _build_tactical_summary(tactic_counts, processed),
        "tactical_events": tactical_events[:12],
        "pattern_explanations": _build_pattern_explanations(tactic_counts, shape_analysis, graph, ball_track),
        "summary": (
            f"Video processado com deteccao real de movimento (MOG2 + tracking por centroide): "
            f"{len(valid_tracks)} rastros da equipe acompanhada em {processed} frames analisados."
            + (
                " Amostragem distribuida do inicio ao fim do video enviado."
                if full_video_coverage
                else " Duracao do video nao pode ser determinada; leitura sequencial a partir do inicio."
            )
            + (" Analise parcial: limite seguro de processamento atingido." if stopped_by_timeout else "")
        ),
    }


def _open_browser_video_writer(width: int, height: int, fps: float):
    candidates = [
        ("webm", "VP80", "video/webm", "VP8"),
        ("webm", "VP90", "video/webm", "VP9"),
        ("mp4", "mp4v", "video/mp4", "MPEG-4 Part 2"),
    ]

    for extension, fourcc_name, mime, codec_label in candidates:
        output_name = f"annotated_{uuid.uuid4().hex}.{extension}"
        output_path = MEDIA_DIR / output_name
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*fourcc_name),
            fps,
            (width, height),
        )
        if writer.isOpened():
            return writer, output_name, output_path, mime, codec_label
        writer.release()
        output_path.unlink(missing_ok=True)

    raise ValueError("Nao foi possivel criar o video anotado em formato compativel com o navegador.")


def _default_field_model(width: int, height: int) -> dict:
    return {
        "detected": False,
        "confidence": "Baixa",
        "method": "normalizacao_por_frame",
        "polygon": [
            {"x": 0, "y": 0},
            {"x": width, "y": 0},
            {"x": width, "y": height},
            {"x": 0, "y": height},
        ],
        "homography": None,
        "explanation": "Campo nao isolado; coordenadas 2D usam normalizacao direta do frame.",
    }


def _detect_field_model(frame, width: int, height: int) -> dict | None:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_green = np.array([28, 35, 35])
    upper_green = np.array([95, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    if area < width * height * 0.18:
        return None

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect).astype("float32")
    ordered = _order_quad(box)
    destination = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype="float32")
    homography = cv2.getPerspectiveTransform(ordered, destination)
    return {
        "detected": True,
        "confidence": "Media" if area < width * height * 0.45 else "Alta",
        "method": "mascara_verde_homografia_aproximada",
        "polygon": [{"x": round(float(x), 1), "y": round(float(y), 1)} for x, y in ordered],
        "homography": homography.tolist(),
        "explanation": (
            "Campo estimado por area verde dominante. A homografia e aproximada e deve ser refinada "
            "com linhas do campo/modelo calibrado para metricas oficiais."
        ),
    }


def _order_quad(points) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1)
    rect[0] = points[np.argmin(sums)]
    rect[2] = points[np.argmax(sums)]
    rect[1] = points[np.argmin(diffs)]
    rect[3] = points[np.argmax(diffs)]
    return rect


def _map_to_pitch(x: float, y: float, field_model: dict) -> tuple[float, float]:
    homography = field_model.get("homography")
    if homography:
        point = np.array([[[x, y]]], dtype="float32")
        mapped = cv2.perspectiveTransform(point, np.array(homography, dtype="float32"))[0][0]
        return float(np.clip(mapped[0], 0, 100)), float(np.clip(mapped[1], 0, 100))
    polygon = field_model.get("polygon") or []
    max_x = max((point["x"] for point in polygon), default=1)
    max_y = max((point["y"] for point in polygon), default=1)
    return float(np.clip(x / max(1, max_x) * 100, 0, 100)), float(np.clip(y / max(1, max_y) * 100, 0, 100))


def _field_candidate_gate(
    x: int,
    y: int,
    w: int,
    h: int,
    frame_width: int,
    frame_height: int,
    field_model: dict,
) -> dict:
    if h < frame_height * MIN_PLAYER_BOX_HEIGHT_RATIO:
        return {"accepted": False, "reason": "muito_pequeno"}
    if h > frame_height * MAX_PLAYER_BOX_HEIGHT_RATIO:
        return {"accepted": False, "reason": "muito_alto"}
    if w > frame_width * MAX_PLAYER_BOX_WIDTH_RATIO and h < frame_height * 0.24:
        return {"accepted": False, "reason": "faixa_larga"}
    aspect = w / max(1, h)
    if aspect > 1.55:
        return {"accepted": False, "reason": "aspecto_nao_jogador"}

    if not field_model.get("detected"):
        return {"accepted": True, "reason": "sem_campo_detectado"}

    foot_x = float(x + w / 2)
    foot_y = float(y + h * 0.92)
    polygon = field_model.get("polygon") or []
    if len(polygon) >= 4:
        contour = np.array(
            [[float(point["x"]), float(point["y"])] for point in polygon],
            dtype=np.float32,
        )
        inside = cv2.pointPolygonTest(contour, (foot_x, foot_y), False)
        if inside < 0:
            return {"accepted": False, "reason": "fora_do_campo"}

    pitch_x, pitch_y = _map_to_pitch(foot_x, foot_y, field_model)
    if not (0 <= pitch_x <= 100 and 0 <= pitch_y <= 100):
        return {"accepted": False, "reason": "fora_da_homografia"}
    return {"accepted": True, "reason": "dentro_do_campo"}


def _detect_ball(
    frame,
    field_model: dict,
    previous_ball_px: tuple[float, float] | None = None,
    frame_width: int | None = None,
) -> dict | None:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 160])
    upper_white = np.array([180, 70, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    max_jump = (frame_width or frame.shape[1]) * BALL_MAX_JUMP_PX_RATIO
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 6 or area > 260:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        if circularity < 0.36:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / max(1, h)
        if aspect < 0.55 or aspect > 1.8:
            continue
        cx, cy = x + w / 2, y + h / 2
        # Consistencia temporal: com bola vista recentemente, candidatos alem
        # do salto maximo sao descartados (linhas do campo, meiao e placas
        # brancas pontuam bem em circularidade mas aparecem longe da bola) e
        # os demais sao ranqueados tambem pela proximidade da ultima posicao.
        proximity_score = 1.0
        if previous_ball_px is not None:
            jump = math.hypot(cx - previous_ball_px[0], cy - previous_ball_px[1])
            if jump > max_jump:
                continue
            proximity_score = 1.0 - jump / max(1.0, max_jump)
        pitch_x, pitch_y = _map_to_pitch(cx, cy, field_model)
        candidates.append((area, circularity, proximity_score, cx, cy, pitch_x, pitch_y))

    if not candidates:
        return None

    area, circularity, _, cx, cy, pitch_x, pitch_y = max(
        candidates, key=lambda item: (item[1] * 0.6 + item[2] * 0.4, -item[0])
    )
    return {
        "x": cx,
        "y": cy,
        "pitch_x": round(pitch_x, 1),
        "pitch_y": round(pitch_y, 1),
        "confidence": "Media" if circularity > 0.58 else "Baixa",
    }


def _normalize_team_filter(team_filter: str) -> str:
    normalized = (team_filter or "auto").strip().casefold()
    return normalized if normalized in TEAM_FILTER_KEYS else "auto"


def _build_jersey_reference_profiles(jersey_references: list[dict]) -> list[dict]:
    profiles = []
    for index, reference in enumerate(jersey_references[:6]):
        content = reference.get("content") or b""
        filename = reference.get("filename") or f"camisa-{index + 1}"
        if not content:
            continue
        array = np.frombuffer(content, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            continue
        signature = _uniform_signature(image)
        if signature["key"] == "unknown":
            continue
        profiles.append(
            {
                "label": filename,
                "key": signature["key"],
                "hue": signature["hue"],
                "saturation": signature["saturation"],
                "value": signature["value"],
                "confidence_base": signature["confidence"],
                "samples": signature["samples"],
            }
        )
    return profiles


def _classify_uniform_color(
    frame,
    box: tuple[int, int, int, int],
    jersey_reference_profiles: list[dict] | None = None,
) -> dict:
    x, y, w, h = box
    height, width = frame.shape[:2]
    x1 = max(0, int(x + w * 0.24))
    x2 = min(width, int(x + w * 0.76))
    y1 = max(0, int(y + h * 0.14))
    y2 = min(height, int(y + h * 0.62))
    if x2 <= x1 or y2 <= y1:
        return _uniform_result("unknown", "Baixa")

    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return _uniform_result("unknown", "Baixa")

    signature = _uniform_signature(roi)
    if jersey_reference_profiles:
        match = _match_jersey_reference(signature, jersey_reference_profiles)
        if match["score"] >= 0.62:
            confidence = "Alta" if match["score"] >= 0.76 else "Media"
            result = _uniform_result("reference", confidence)
            result["reference_score"] = round(match["score"], 3)
            result["reference_label"] = match["label"]
            result["base_uniform_key"] = signature["key"]
            return result

    return _uniform_result(signature["key"], signature["confidence"])


def _uniform_signature(roi) -> dict:
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    saturation = hsv[:, 1]
    value = hsv[:, 2]
    valid = (value > 35) & ((saturation > 45) | (value > 170) | (value < 95))
    if int(valid.sum()) < 12:
        return _signature("unknown", 0, 0, 0, "Baixa", int(valid.sum()))

    sample = hsv[valid]
    median_s = float(np.median(sample[:, 1]))
    median_v = float(np.median(sample[:, 2]))
    saturated = sample[sample[:, 1] > 48]

    if median_v >= 170 and median_s <= 58:
        return _signature("light", 0, median_s, median_v, "Media", int(valid.sum()))
    if median_v <= 82:
        return _signature("dark", 0, median_s, median_v, "Media", int(valid.sum()))
    if len(saturated) < 8:
        if median_v >= 145:
            return _signature("light", 0, median_s, median_v, "Baixa", int(valid.sum()))
        if median_v <= 105:
            return _signature("dark", 0, median_s, median_v, "Baixa", int(valid.sum()))
        return _signature("unknown", 0, median_s, median_v, "Baixa", int(valid.sum()))

    hue = float(np.median(saturated[:, 0]))
    if hue <= 7 or hue >= 168:
        return _signature("red", hue, median_s, median_v, "Media", int(valid.sum()))
    if 8 <= hue <= 19:
        return _signature("orange", hue, median_s, median_v, "Media", int(valid.sum()))
    if 20 <= hue <= 38:
        return _signature("yellow", hue, median_s, median_v, "Media", int(valid.sum()))
    if 39 <= hue <= 85:
        return _signature("green", hue, median_s, median_v, "Media", int(valid.sum()))
    if 86 <= hue <= 130:
        return _signature("blue", hue, median_s, median_v, "Media", int(valid.sum()))
    if 131 <= hue <= 167:
        return _signature("purple", hue, median_s, median_v, "Media", int(valid.sum()))
    return _signature("unknown", hue, median_s, median_v, "Baixa", int(valid.sum()))


def _signature(key: str, hue: float, saturation: float, value: float, confidence: str, samples: int) -> dict:
    return {
        "key": key,
        "hue": float(hue),
        "saturation": float(saturation),
        "value": float(value),
        "confidence": confidence,
        "samples": samples,
    }


def _match_jersey_reference(signature: dict, profiles: list[dict]) -> dict:
    best = {"score": 0.0, "label": ""}
    if signature["key"] == "unknown":
        return best
    for profile in profiles:
        if profile["key"] in {"light", "dark"} or signature["key"] in {"light", "dark"}:
            key_bonus = 0.28 if profile["key"] == signature["key"] else -0.24
            saturation_score = max(0.0, 1.0 - abs(profile["saturation"] - signature["saturation"]) / 95)
            value_score = max(0.0, 1.0 - abs(profile["value"] - signature["value"]) / 130)
            score = max(0.0, min(1.0, 0.42 * saturation_score + 0.44 * value_score + key_bonus))
        else:
            hue_score = max(0.0, 1.0 - _hue_distance(profile["hue"], signature["hue"]) / 48)
            saturation_score = max(0.0, 1.0 - abs(profile["saturation"] - signature["saturation"]) / 130)
            value_score = max(0.0, 1.0 - abs(profile["value"] - signature["value"]) / 150)
            key_bonus = 0.16 if profile["key"] == signature["key"] else 0
            score = max(0.0, min(1.0, 0.54 * hue_score + 0.22 * saturation_score + 0.14 * value_score + key_bonus))
        if score > best["score"]:
            best = {"score": score, "label": profile["label"]}
    return best


def _hue_distance(a: float, b: float) -> float:
    diff = abs(float(a) - float(b))
    return min(diff, 180 - diff)


def _uniform_result(key: str, confidence: str) -> dict:
    return {
        "key": key,
        "label": _team_filter_label(key),
        "confidence": confidence,
        "color": TEAM_COLOR_BGR.get(key, TEAM_COLOR_BGR["unknown"]),
    }


def _selected_team_key(requested_team_filter: str, uniform_counts: Counter[str]) -> str | None:
    if requested_team_filter == "all":
        return "all"
    if requested_team_filter == "reference":
        return "reference" if uniform_counts.get("reference", 0) > 0 else None
    if requested_team_filter != "auto":
        return requested_team_filter
    ranked = [
        (key, count)
        for key, count in uniform_counts.most_common()
        if key not in {"unknown", "all", "auto"} and count > 0
    ]
    return ranked[0][0] if ranked else None


def _track_team_key(track: _Track) -> str:
    ranked = [
        (key, count)
        for key, count in track.team_counts.most_common()
        if key not in {"unknown", "all", "auto"} and count > 0
    ]
    if ranked:
        return ranked[0][0]
    return "unknown"


def _track_team_confidence(track: _Track) -> str:
    total = sum(track.team_counts.values())
    if total <= 0:
        return "Baixa"
    key = _track_team_key(track)
    share = track.team_counts.get(key, 0) / total
    if share >= 0.72:
        return "Alta"
    if share >= 0.48:
        return "Media"
    return "Baixa"


def _track_matches_team(track: _Track, requested_team_filter: str, selected_team_key: str | None) -> bool:
    if requested_team_filter == "all":
        return True
    if not selected_team_key:
        return False
    return _track_team_key(track) == selected_team_key


def _team_filter_label(key: str | None) -> str:
    labels = {option["key"]: option["label"] for option in TEAM_FILTER_OPTIONS}
    if key == "unknown":
        return "Uniforme indefinido"
    return labels.get(key or "", "Uniforme indefinido")


def _build_team_focus(
    requested_team_filter: str,
    selected_team_key: str | None,
    uniform_counts: Counter[str],
    track_stats: list[tuple[int, _Track, float]],
    valid_tracks: dict[int, _Track],
    candidate_rejections: Counter[str],
) -> dict:
    track_group_counts = Counter(_track_team_key(track) for _, track, _ in track_stats)
    groups = []
    keys = sorted(
        {key for key in uniform_counts if key != "unknown"} | {key for key in track_group_counts if key != "unknown"}
    )
    for key in keys:
        groups.append(
            {
                "key": key,
                "label": _team_filter_label(key),
                "samples": uniform_counts.get(key, 0),
                "tracks": track_group_counts.get(key, 0),
                "selected": key == selected_team_key,
            }
        )

    return {
        "requested_key": requested_team_filter,
        "requested_label": _team_filter_label(requested_team_filter),
        "selected_key": selected_team_key,
        "selected_label": _team_filter_label(selected_team_key),
        "mode": (
            "referencia_por_camisas"
            if requested_team_filter == "reference"
            else "automatico_por_uniforme_dominante" if requested_team_filter == "auto" else "manual"
        ),
        "total_candidate_tracks": len(track_stats),
        "target_tracks": len(valid_tracks),
        "available_groups": sorted(groups, key=lambda item: item["samples"], reverse=True),
        "candidate_rejections": dict(candidate_rejections),
        "note": (
            "Filtro combina base do rastro dentro do campo, tamanho/formato plausivel de jogador e cor do uniforme. "
            "Para separar equipes com uniformes parecidos, use o seletor manual ou um recorte de video com maior visibilidade."
        ),
    }


def _color_for(track_id: int) -> tuple[int, int, int]:
    palette = [
        (66, 135, 245), (245, 66, 90), (66, 245, 152), (245, 197, 66),
        (197, 66, 245), (66, 245, 230), (245, 130, 66), (150, 66, 245),
    ]
    return palette[track_id % len(palette)]


def _track_distance(track: _Track) -> float:
    distance = 0.0
    for index in range(1, len(track.points)):
        _, x1, y1 = track.points[index - 1]
        _, x2, y2 = track.points[index]
        distance += math.hypot(x2 - x1, y2 - y1)
    return distance


def _role_hint(track: _Track) -> str:
    if not track.pitch_points:
        return "Funcao indefinida"
    avg_y = sum(point[2] for point in track.pitch_points) / len(track.pitch_points)
    avg_x = sum(point[1] for point in track.pitch_points) / len(track.pitch_points)
    if avg_y < 28:
        line = "linha ofensiva"
    elif avg_y < 58:
        line = "zona de meio"
    else:
        line = "linha defensiva"
    if avg_x < 25:
        lane = "corredor esquerdo"
    elif avg_x > 75:
        lane = "corredor direito"
    else:
        lane = "corredor central"
    return f"{line}, {lane}"


def _infer_ball_events(ball_track: list[dict], tracks: dict[int, _Track]) -> list[dict]:
    if len(ball_track) < 3 or not tracks:
        return []

    inferred = []
    previous_owner = None
    previous_ball = ball_track[0]
    for ball in ball_track[1:]:
        owner = _nearest_track_to_ball(ball, tracks)
        ball_speed = math.hypot(ball["x"] - previous_ball["x"], ball["y"] - previous_ball["y"])
        if owner is not None and previous_owner is not None and owner != previous_owner and ball_speed > 7:
            inferred.append(
                {
                    "frame": ball["frame"],
                    "time_s": ball["time_s"],
                    "track_id": owner,
                    "type": "probable_pass",
                    "label": "Passe provavel",
                    "confidence": "Baixa",
                    "explanation": (
                        "A posse aparente mudou de um rastro para outro apos deslocamento da bola. "
                        "Sem detector supervisionado, tratar como indicio de passe."
                    ),
                }
            )
        if ball_speed > 12 and (ball["y"] < 18 or ball["y"] > 82):
            inferred.append(
                {
                    "frame": ball["frame"],
                    "time_s": ball["time_s"],
                    "track_id": owner,
                    "type": "probable_shot",
                    "label": "Finalizacao provavel",
                    "confidence": "Baixa",
                    "explanation": (
                        "Bola acelerou em direcao a uma zona extrema do campo. Pode representar chute, "
                        "cruzamento ou lancamento longo."
                    ),
                }
            )
        if owner is not None:
            previous_owner = owner
        previous_ball = ball
    return inferred[:30]


def _nearest_track_to_ball(ball: dict, tracks: dict[int, _Track]) -> int | None:
    best_id, best_distance = None, 8.5
    for track_id, track in tracks.items():
        point = _nearest_pitch_point(track, ball["frame"])
        if not point:
            continue
        _, x, y = point
        distance = math.hypot(ball["x"] - x, ball["y"] - y)
        if distance < best_distance:
            best_id, best_distance = track_id, distance
    return best_id


def _nearest_pitch_point(track: _Track, frame: int) -> tuple[int, float, float] | None:
    if not track.pitch_points:
        return None
    return min(track.pitch_points, key=lambda point: abs(point[0] - frame))


def _build_shape_analysis(tracks: dict[int, _Track]) -> dict:
    if not tracks:
        return {
            "formation_guess": "Indefinida",
            "confidence": "Baixa",
            "block": "Sem trilhas suficientes",
            "explanation": "Nao ha rastros suficientes para estimar linhas coletivas.",
        }

    positions = []
    for track in tracks.values():
        if not track.pitch_points:
            continue
        avg_x = sum(point[1] for point in track.pitch_points[-20:]) / min(20, len(track.pitch_points))
        avg_y = sum(point[2] for point in track.pitch_points[-20:]) / min(20, len(track.pitch_points))
        positions.append((avg_x, avg_y))

    if len(positions) < 6:
        return {
            "formation_guess": "Indefinida",
            "confidence": "Baixa",
            "block": "Amostra curta",
            "explanation": "Poucos jogadores/objetos persistentes para estimar formacao.",
        }

    defensive = sum(1 for _, y in positions if y >= 62)
    midfield = sum(1 for _, y in positions if 34 <= y < 62)
    offensive = sum(1 for _, y in positions if y < 34)
    spread_x = max(x for x, _ in positions) - min(x for x, _ in positions)
    spread_y = max(y for _, y in positions) - min(y for _, y in positions)
    formation = _formation_from_lines(defensive, midfield, offensive)
    block = "bloco compacto" if spread_y < 42 else "bloco alongado"
    if spread_x > 70:
        block += " com amplitude alta"
    elif spread_x < 45:
        block += " com pouca largura"

    return {
        "formation_guess": formation,
        "line_counts": {"defensive": defensive, "midfield": midfield, "offensive": offensive},
        "confidence": "Media" if len(positions) >= 10 else "Baixa",
        "block": block,
        "width_index": round(spread_x, 1),
        "depth_index": round(spread_y, 1),
        "explanation": (
            "Estimativa baseada na distribuicao media dos rastros no campo 2D. "
            "Para formacao oficial, e necessario classificar equipes, camisas e goleiros."
        ),
    }


def _formation_from_lines(defensive: int, midfield: int, offensive: int) -> str:
    if defensive >= 5 and midfield >= 3:
        return "5-3-2 / 5-4-1 aproximado"
    if defensive >= 4 and midfield >= 4:
        return "4-4-2 aproximado"
    if defensive >= 4 and midfield == 3 and offensive >= 3:
        return "4-3-3 aproximado"
    if defensive >= 4 and midfield >= 2 and offensive >= 3:
        return "4-2-3-1 aproximado"
    if midfield >= defensive and midfield >= offensive:
        return "bloco com superioridade no meio"
    return "estrutura coletiva aproximada"


def _build_pattern_explanations(
    tactic_counts: Counter[str],
    shape_analysis: dict,
    graph: dict,
    ball_track: list[dict],
) -> list[dict]:
    explanations = []
    if tactic_counts:
        tactic, count = tactic_counts.most_common(1)[0]
        explanations.append(
            {
                "title": tactic,
                "why_it_matters": _tactic_finding(tactic),
                "evidence": f"Padrao apareceu em {count} frames processados com movimento relevante.",
            }
        )
    explanations.append(
        {
            "title": shape_analysis.get("formation_guess", "Estrutura coletiva"),
            "why_it_matters": shape_analysis.get("explanation", ""),
            "evidence": f"Bloco detectado: {shape_analysis.get('block', 'indefinido')}.",
        }
    )
    metrics = graph.get("metrics", {})
    if metrics:
        explanations.append(
            {
                "title": "Rede de proximidade",
                "why_it_matters": (
                    "Conexoes recorrentes indicam jogadores/zonas que compartilham espaco, "
                    "pressionam juntos ou sustentam circulacao."
                ),
                "evidence": (
                    f"Densidade {metrics.get('network_density', 0)}%; "
                    f"lider: {metrics.get('centrality_leader') or 'N/A'}."
                ),
            }
        )
    if ball_track:
        explanations.append(
            {
                "title": "Circulacao de bola",
                "why_it_matters": "A trilha da bola ajuda a diferenciar ocupacao sem bola de progressao real.",
                "evidence": f"{len(ball_track)} pontos provaveis de bola detectados.",
            }
        )
    return explanations


def _player_identity_strategy() -> dict:
    return {
        "status": "tecnica_recomendada",
        "summary": (
            "Numero e nome exigem recorte da camisa com resolucao suficiente. O caminho correto e combinar "
            "tracking do jogador, deteccao de orientacao corporal, recorte de costas/peito e OCR especializado."
        ),
        "steps": [
            "1. Manter o mesmo jogador por tracking ao longo do lance.",
            "2. Detectar frames em que costas ou peito estejam visiveis e a camisa ocupe area suficiente.",
            "3. Recortar tronco/camisa, estabilizar o crop e aumentar resolucao antes do OCR.",
            "4. Aplicar OCR para numero e nome com EasyOCR, PaddleOCR ou detector treinado para uniformes.",
            "5. Validar o numero em multiplos frames antes de vincular identidade ao rastro.",
        ],
        "requirements": [
            "Camera com resolucao suficiente",
            "Frames com camisa legivel e pouco borrada",
            "Tabela elenco/numero para reconciliar OCR com nomes reais",
            "Modelo OCR ou detector de digitos/letras treinado para futebol",
        ],
    }


def _classify_tactic(frame_active_tracks: list[tuple], width: int, height: int) -> str:
    if not frame_active_tracks:
        return "Sem deteccao dominante"

    xs = [track[1] / width for track in frame_active_tracks]
    ys = [track[2] / height for track in frame_active_tracks]
    spread_x = max(xs) - min(xs) if xs else 0
    avg_y = sum(ys) / len(ys)

    if len(frame_active_tracks) >= 18 and spread_x < 0.56:
        return "Bloco compacto / pressao"
    if spread_x >= 0.68:
        return "Amplitude pelos corredores"
    if avg_y < 0.38:
        return "Ataque a profundidade"
    if avg_y > 0.66:
        return "Recomposicao defensiva"
    return "Circulacao e apoios"


def _tactic_finding(tactic: str) -> str:
    findings = {
        "Bloco compacto / pressao": "Muitos rastros em zona curta; indica pressao, disputa ou bloco concentrado.",
        "Amplitude pelos corredores": "Ocupacao horizontal larga; avaliar viradas de jogo e isolamento pelos lados.",
        "Ataque a profundidade": "Movimento predominante no terco ofensivo; observar ataques nas costas da linha.",
        "Recomposicao defensiva": "Rastros concentrados em zona baixa; indica retorno defensivo ou protecao da area.",
        "Circulacao e apoios": "Movimento distribuido no meio; observar apoios, triangulos e conexoes interiores.",
    }
    return findings.get(tactic, "Sem padrao coletivo dominante neste trecho.")


def _draw_tactical_overlay(
    frame,
    width: int,
    height: int,
    tactic: str,
    field_model: dict,
    ball: dict | None,
    team_focus_label: str,
) -> None:
    overlay = frame.copy()
    gold = (58, 162, 216)
    blue = (96, 42, 10)
    white = (245, 245, 245)

    for ratio in (0.2, 0.4, 0.6, 0.8):
        x = int(width * ratio)
        cv2.line(overlay, (x, 0), (x, height), gold, 1)
    for ratio in (1 / 3, 2 / 3):
        y = int(height * ratio)
        cv2.line(overlay, (0, y), (width, y), gold, 1)

    if field_model.get("detected"):
        polygon = np.array(
            [[int(point["x"]), int(point["y"])] for point in field_model.get("polygon", [])],
            dtype=np.int32,
        )
        if len(polygon) == 4:
            cv2.polylines(overlay, [polygon], True, (120, 210, 255), 2)

    cv2.rectangle(overlay, (12, 12), (min(width - 12, 520), 74), blue, -1)
    cv2.addWeighted(overlay, 0.24, frame, 0.76, 0, frame)
    cv2.putText(frame, "Leitura tática", (24, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, white, 2)
    cv2.putText(frame, f"{tactic} | {team_focus_label}", (24, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.58, gold, 2)
    if ball:
        center = (int(ball["x"]), int(ball["y"]))
        cv2.circle(frame, center, 7, (255, 255, 255), 2)
        cv2.circle(frame, center, 3, (58, 162, 216), -1)
        cv2.putText(frame, "bola", (center[0] + 9, center[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, white, 1)


def _build_tactical_summary(tactic_counts: Counter[str], processed: int) -> str:
    if not tactic_counts:
        return "Nao houve rastros suficientes para classificar um padrao tatico dominante."

    dominant, frames = tactic_counts.most_common(1)[0]
    share = round(frames / max(1, processed) * 100, 1)
    return f"Padrao dominante detectado: {dominant} em {share}% dos frames analisados com movimento relevante."


def _grid_to_points(heat_grid: list[list[int]]) -> list[dict]:
    max_value = max((max(row) for row in heat_grid), default=0)
    if max_value == 0:
        return []
    points = []
    step = 8
    for gy in range(0, GRID_H, step):
        for gx in range(0, GRID_W, step):
            cell_sum = sum(
                heat_grid[y][x]
                for y in range(gy, min(gy + step, GRID_H))
                for x in range(gx, min(gx + step, GRID_W))
            )
            if cell_sum == 0:
                continue
            intensity = round(cell_sum / max_value * 100, 1)
            if intensity < 10:
                continue
            points.append(
                {
                    "x": round(gx / GRID_W * 100, 1),
                    "y": round(gy / GRID_H * 100, 1),
                    "intensity": intensity,
                }
            )
    return sorted(points, key=lambda point: point["intensity"], reverse=True)[:90]


def _build_proximity_graph(tracks: dict[int, _Track], proximity_counts: dict[tuple[int, int], int]) -> dict:
    graph = nx.Graph()
    for tid in tracks:
        graph.add_node(tid)
    for (a, b), weight in proximity_counts.items():
        if a in tracks and b in tracks:
            graph.add_edge(a, b, weight=weight)

    if graph.number_of_nodes() == 0:
        return {"nodes": [], "edges": [], "metrics": {}}

    centrality = nx.degree_centrality(graph)
    density = nx.density(graph) if graph.number_of_nodes() > 1 else 0.0

    nodes = sorted(
        [
            {
                "id": tid,
                "label": f"Jogador/objeto {tid}",
                "centrality": round(centrality.get(tid, 0.0), 3),
                "samples": len(track.points),
            }
            for tid, track in tracks.items()
        ],
        key=lambda node: (node["centrality"], node["samples"]),
        reverse=True,
    )
    edges = sorted(
        [
            {
                "source": a,
                "target": b,
                "weight": w,
                "label": "proximidade recorrente",
            }
            for (a, b), w in proximity_counts.items()
            if a in tracks and b in tracks
        ],
        key=lambda edge: edge["weight"],
        reverse=True,
    )

    leader = max(nodes, key=lambda n: n["centrality"]) if nodes else None

    return {
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "network_density": round(density * 100, 1),
            "centrality_leader": leader["label"] if leader else None,
            "total_proximity_events": sum(proximity_counts.values()),
        },
    }
