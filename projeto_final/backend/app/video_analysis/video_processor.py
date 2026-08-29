"""Real-time Video Processor - Processa vídeos frame-by-frame em tempo real

Streaming de dados de rastreamento com:
- Leitura de vídeo em tempo real
- Detecção de jogadores
- Transformação de perspectiva
- Construção incremental de grafos
- Emissão de eventos via WebSocket/SSE
"""
from __future__ import annotations

import logging
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Callable, Optional, Dict, List
from pathlib import Path
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class FrameData:
    """Dados de um frame processado."""
    frame_idx: int
    timestamp: float
    player_positions: Dict[int, tuple]  # {player_id: (x, y, team_id)}
    ball_position: Optional[tuple] = None  # (x, y)
    detections_count: int = 0
    processing_time_ms: float = 0.0


@dataclass
class VideoMetadata:
    """Metadados do vídeo."""
    filepath: str
    total_frames: int
    fps: float
    width: int
    height: int
    duration_seconds: float


class VideoStreamProcessor:
    """Processa vídeo em streaming, enviando dados frame-by-frame."""

    def __init__(self, buffer_size: int = 30):
        self.buffer_size = buffer_size
        self.frame_buffer: List[FrameData] = []
        self.current_tracks: Dict[int, List[tuple]] = defaultdict(list)

    def get_video_metadata(self, video_path: str) -> VideoMetadata:
        """Obter metadados do vídeo."""
        cap = cv2.VideoCapture(video_path)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        cap.release()

        return VideoMetadata(
            filepath=video_path,
            total_frames=total_frames,
            fps=fps,
            width=width,
            height=height,
            duration_seconds=total_frames / fps if fps > 0 else 0,
        )

    def process_video_streaming(
        self,
        video_path: str,
        frame_callback: Callable[[FrameData], None],
        detection_callback: Optional[Callable] = None,
        skip_frames: int = 1,
    ) -> VideoMetadata:
        """Processar vídeo e chamar callback para cada frame.

        Args:
            video_path: Caminho do vídeo
            frame_callback: Função chamada com FrameData para cada frame
            detection_callback: Callback para detecções (simulado)
            skip_frames: Pular frames (1 = todos, 2 = cada 2o frame, etc)

        Returns:
            Metadados do vídeo
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Não conseguiu abrir vídeo: {video_path}")

        metadata = self.get_video_metadata(video_path)
        logger.info(f"Processando vídeo: {metadata.duration_seconds:.1f}s @ {metadata.fps}fps")

        frame_idx = 0
        processed_frames = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Pular frames se solicitado
                if frame_idx % skip_frames != 0:
                    frame_idx += 1
                    continue

                # Simular detecção de jogadores
                player_positions = self._simulate_player_detection(frame, frame_idx)

                # Criar dados do frame
                frame_data = FrameData(
                    frame_idx=frame_idx,
                    timestamp=frame_idx / metadata.fps,
                    player_positions=player_positions,
                    detections_count=len(player_positions),
                )

                # Adicionar ao buffer
                self.frame_buffer.append(frame_data)
                if len(self.frame_buffer) > self.buffer_size:
                    self.frame_buffer.pop(0)

                # Chamar callback
                frame_callback(frame_data)

                # Log de progresso
                if processed_frames % 30 == 0:
                    progress = (frame_idx / metadata.total_frames) * 100
                    logger.debug(f"Processando... {progress:.1f}%")

                frame_idx += 1
                processed_frames += 1

        finally:
            cap.release()
            logger.info(f"Vídeo processado: {processed_frames} frames")

        return metadata

    def _simulate_player_detection(
        self,
        frame: np.ndarray,
        frame_idx: int,
    ) -> Dict[int, tuple]:
        """Simular detecção de jogadores (no futuro: YOLO real).

        Returns:
            {player_id: (x, y, team_id)}
        """
        h, w = frame.shape[:2]

        # Simular 11 jogadores por time
        positions = {}

        for team_id in [0, 1]:
            for player_in_team in range(11):
                player_id = team_id * 1000 + player_in_team

                # Posição simulada (movimento sinusoidal)
                base_x = (player_in_team % 5) * (w / 5)
                base_y = (player_in_team // 5) * (h / 3)

                # Adicionar movimento
                noise_x = np.sin(frame_idx / 20 + player_id) * 30
                noise_y = np.cos(frame_idx / 25 + player_id) * 20

                x = base_x + noise_x
                y = base_y + noise_y

                # Manter dentro dos limites
                x = np.clip(x, 0, w - 1)
                y = np.clip(y, 0, h - 1)

                positions[player_id] = (float(x), float(y), team_id)

        return positions

    async def process_video_async(
        self,
        video_path: str,
        frame_callback: Callable[[FrameData], None],
        skip_frames: int = 1,
    ):
        """Processar vídeo de forma assíncrona (para WebSocket)."""
        metadata = self.get_video_metadata(video_path)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Não conseguiu abrir vídeo: {video_path}")

        frame_idx = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % skip_frames != 0:
                    frame_idx += 1
                    continue

                # Simular detecção
                player_positions = self._simulate_player_detection(frame, frame_idx)

                # Criar dados do frame
                frame_data = FrameData(
                    frame_idx=frame_idx,
                    timestamp=frame_idx / metadata.fps,
                    player_positions=player_positions,
                    detections_count=len(player_positions),
                )

                # Chamar callback
                frame_callback(frame_data)

                # Dar tempo para processar
                await asyncio.sleep(0.001)

                frame_idx += 1

        finally:
            cap.release()


class RealTimeGraphBuilder:
    """Constrói grafos de movimento em tempo real."""

    def __init__(self, frame_window: int = 30):
        self.frame_window = frame_window  # Janela de frames para análise
        self.player_tracks: Dict[int, List[tuple]] = defaultdict(list)
        self.frame_history: List[FrameData] = []

    def update(self, frame_data: FrameData):
        """Atualizar com novo frame."""
        self.frame_history.append(frame_data)

        # Manter apenas últimos N frames
        if len(self.frame_history) > self.frame_window:
            self.frame_history.pop(0)

        # Adicionar posições aos tracks
        for player_id, (x, y, team_id) in frame_data.player_positions.items():
            self.player_tracks[player_id].append({
                'frame': frame_data.frame_idx,
                'x': x,
                'y': y,
                'team_id': team_id,
                'timestamp': frame_data.timestamp,
            })

            # Manter apenas últimas N posições
            if len(self.player_tracks[player_id]) > self.frame_window:
                self.player_tracks[player_id].pop(0)

    def get_current_graph_data(self) -> Dict:
        """Obter dados do grafo atual (últimos N frames)."""
        if not self.frame_history:
            return {}

        # Agrupar jogadores por time
        teams = defaultdict(list)

        for player_id, positions in self.player_tracks.items():
            if not positions:
                continue

            team_id = positions[-1]['team_id']
            current_pos = positions[-1]

            # Calcular distância do último frame
            distance_traveled = 0
            if len(positions) > 1:
                for i in range(1, len(positions)):
                    prev = positions[i - 1]
                    curr = positions[i]
                    dist = np.sqrt(
                        (curr['x'] - prev['x']) ** 2 +
                        (curr['y'] - prev['y']) ** 2
                    )
                    distance_traveled += dist

            teams[team_id].append({
                'player_id': player_id,
                'x': current_pos['x'],
                'y': current_pos['y'],
                'distance_traveled': distance_traveled,
                'trajectory': [(p['x'], p['y']) for p in positions[-10:]],  # Últimos 10 frames
            })

        return {
            'frame_idx': self.frame_history[-1].frame_idx,
            'timestamp': self.frame_history[-1].timestamp,
            'teams': dict(teams),
            'total_players': sum(len(players) for players in teams.values()),
        }

    def calculate_proximities(self) -> List[Dict]:
        """Calcular proximidades entre jogadores."""
        proximities = []

        player_ids = list(self.player_tracks.keys())

        for i, p1_id in enumerate(player_ids):
            for p2_id in player_ids[i + 1:]:
                pos1 = self.player_tracks[p1_id]
                pos2 = self.player_tracks[p2_id]

                if not pos1 or not pos2:
                    continue

                # Usar última posição
                x1, y1 = pos1[-1]['x'], pos1[-1]['y']
                x2, y2 = pos2[-1]['x'], pos2[-1]['y']

                distance = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

                # Se próximos (< 100 pixels), adicionar
                if distance < 100:
                    team1 = pos1[-1]['team_id']
                    team2 = pos2[-1]['team_id']

                    proximities.append({
                        'source': p1_id,
                        'target': p2_id,
                        'distance': float(distance),
                        'same_team': team1 == team2,
                    })

        return proximities


__all__ = [
    "FrameData",
    "VideoMetadata",
    "VideoStreamProcessor",
    "RealTimeGraphBuilder",
]
