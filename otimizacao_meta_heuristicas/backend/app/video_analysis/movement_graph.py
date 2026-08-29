"""Movement Graph Builder - Constrói grafos de movimentação de jogadores

Processa dados de rastreamento para criar estruturas de grafo que mostram:
- Rotas e trajetórias dos jogadores
- Conexões (passes, proximidade)
- Padrões de movimento por time
- Análise de formação dinâmica
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class PlayerPosition:
    """Posição de um jogador em um frame."""
    player_id: int
    team_id: int
    x: float  # Coordenada x no vídeo
    y: float  # Coordenada y no vídeo
    x_field: float  # Coordenada x no campo (após transformação)
    y_field: float  # Coordenada y no campo (após transformação)
    frame: int
    confidence: float = 1.0


@dataclass
class PlayerTrack:
    """Rastreamento completo de um jogador através de múltiplos frames."""
    player_id: int
    team_id: int
    positions: List[PlayerPosition] = field(default_factory=list)

    def add_position(self, position: PlayerPosition):
        """Adicionar posição ao rastreamento."""
        self.positions.append(position)

    def get_trajectory(self) -> np.ndarray:
        """Retorna trajetória como array (n_frames, 2)."""
        return np.array([
            [p.x_field, p.y_field] for p in self.positions
        ])

    def get_distance_traveled(self) -> float:
        """Calcular distância total percorrida."""
        if len(self.positions) < 2:
            return 0.0
        trajectory = self.get_trajectory()
        distances = np.linalg.norm(np.diff(trajectory, axis=0), axis=1)
        return float(np.sum(distances))

    def get_average_position(self) -> Tuple[float, float]:
        """Posição média do jogador."""
        trajectory = self.get_trajectory()
        return float(trajectory[:, 0].mean()), float(trajectory[:, 1].mean())


@dataclass
class MovementEdge:
    """Aresta no grafo de movimentação - conexão entre dois jogadores."""
    source_player_id: int
    target_player_id: int
    source_team: int
    target_team: int

    # Estatísticas da conexão
    proximities: List[float] = field(default_factory=list)  # Distâncias mínimas
    co_occurrences: int = 0  # Quantos frames estavam próximos

    def add_proximity(self, distance: float):
        """Adicionar medição de proximidade."""
        self.proximities.append(distance)

    def get_avg_proximity(self) -> float:
        """Distância média mínima entre jogadores."""
        if not self.proximities:
            return float('inf')
        return np.mean(self.proximities)

    def get_interaction_strength(self) -> float:
        """Força da interação (0-1)."""
        if not self.proximities:
            return 0.0
        # Normalizar para 0-1 (campo 105m x 68m, distância mínima interessante ~5m)
        avg_proximity = self.get_avg_proximity()
        max_distance = 15.0  # Distância máxima considerada "conexão"
        return max(0, 1.0 - (avg_proximity / max_distance))


@dataclass
class MovementGraph:
    """Grafo de movimentação de um time."""
    team_id: int
    team_name: str
    period: str  # "1st_half", "2nd_half", etc

    players: Dict[int, PlayerTrack] = field(default_factory=dict)
    edges: Dict[Tuple[int, int], MovementEdge] = field(default_factory=dict)

    # Estatísticas do grafo
    total_frames: int = 0
    field_width: float = 105.0  # Standard FIFA
    field_height: float = 68.0  # Standard FIFA

    def add_player(self, track: PlayerTrack):
        """Adicionar jogador ao grafo."""
        self.players[track.player_id] = track

    def add_edge(self, edge: MovementEdge):
        """Adicionar conexão entre dois jogadores."""
        key = (edge.source_player_id, edge.target_player_id)
        self.edges[key] = edge

    def build_edges_from_proximity(self, min_distance: float = 5.0, max_distance: float = 15.0):
        """Construir arestas baseado em proximidade entre jogadores."""
        player_ids = list(self.players.keys())

        for i, p1_id in enumerate(player_ids):
            for p2_id in player_ids[i+1:]:
                track1 = self.players[p1_id]
                track2 = self.players[p2_id]

                if len(track1.positions) == 0 or len(track2.positions) == 0:
                    continue

                traj1 = track1.get_trajectory()
                traj2 = track2.get_trajectory()

                # Interpolar para mesmo número de pontos
                min_len = min(len(traj1), len(traj2))
                if min_len < 2:
                    continue

                traj1_resampled = traj1[:min_len]
                traj2_resampled = traj2[:min_len]

                # Calcular distâncias entre pontos correspondentes
                distances = np.linalg.norm(traj1_resampled - traj2_resampled, axis=1)
                min_dist = float(np.min(distances))

                # Criar aresta se estiveram próximos
                if min_dist <= max_distance:
                    edge = MovementEdge(
                        source_player_id=p1_id,
                        target_player_id=p2_id,
                        source_team=track1.team_id,
                        target_team=track2.team_id,
                    )
                    edge.proximities = distances[distances <= max_distance].tolist()
                    edge.co_occurrences = len(edge.proximities)

                    self.add_edge(edge)

    def get_formation_matrix(self) -> np.ndarray:
        """Matriz de posições médias dos jogadores (formação)."""
        if not self.players:
            return np.array([])

        positions = []
        for player_id in sorted(self.players.keys()):
            avg_x, avg_y = self.players[player_id].get_average_position()
            positions.append([avg_x, avg_y])

        return np.array(positions)

    def get_player_coverage_area(self, player_id: int) -> float:
        """Área coberta por um jogador (em m²)."""
        if player_id not in self.players:
            return 0.0

        trajectory = self.players[player_id].get_trajectory()
        if len(trajectory) < 3:
            return 0.0

        # Usar convex hull para estimar área
        from scipy.spatial import ConvexHull
        try:
            hull = ConvexHull(trajectory)
            return float(hull.volume)  # 2D: volume é área
        except:
            return 0.0

    def get_centrality_scores(self) -> Dict[int, float]:
        """Scores de centralidade dos jogadores no grafo."""
        scores = {}

        for player_id in self.players.keys():
            # Contar arestas
            outgoing = sum(1 for (src, _) in self.edges.keys() if src == player_id)
            incoming = sum(1 for (_, dst) in self.edges.keys() if dst == player_id)
            total_connections = outgoing + incoming

            # Força média das conexões
            avg_strength = 0.0
            if total_connections > 0:
                strengths = [
                    self.edges[e].get_interaction_strength()
                    for e in self.edges.keys()
                    if player_id in e
                ]
                avg_strength = np.mean(strengths) if strengths else 0.0

            # Score combinado
            scores[player_id] = (total_connections * 0.5) + (avg_strength * 10)

        return scores


class MovementGraphBuilder:
    """Construtor de grafos de movimentação."""

    def __init__(self, field_width: float = 105.0, field_height: float = 68.0):
        self.field_width = field_width
        self.field_height = field_height

    def build_from_tracks(
        self,
        tracks: Dict[int, PlayerTrack],
        team_mapping: Dict[int, int],
        team_names: Dict[int, str],
        period: str = "full_match",
    ) -> Dict[int, MovementGraph]:
        """Construir grafos de movimentação para cada time.

        Args:
            tracks: Dicionário de rastreamentos {player_id: PlayerTrack}
            team_mapping: Mapeamento {player_id: team_id}
            team_names: Nomes dos times {team_id: name}
            period: Período do jogo

        Returns:
            Grafos por time {team_id: MovementGraph}
        """
        # Separar por time
        teams_tracks = defaultdict(dict)
        for player_id, track in tracks.items():
            team_id = team_mapping.get(player_id, track.team_id)
            teams_tracks[team_id][player_id] = track

        # Construir grafo para cada time
        graphs = {}
        for team_id, team_tracks in teams_tracks.items():
            graph = MovementGraph(
                team_id=team_id,
                team_name=team_names.get(team_id, f"Team {team_id}"),
                period=period,
                field_width=self.field_width,
                field_height=self.field_height,
            )

            # Adicionar jogadores
            for player_id, track in team_tracks.items():
                graph.add_player(track)

            # Calcular estatísticas
            if team_tracks:
                graph.total_frames = max(
                    len(track.positions) for track in team_tracks.values()
                )

            # Construir arestas
            graph.build_edges_from_proximity()

            graphs[team_id] = graph

        logger.info(f"Construídos grafos para {len(graphs)} times")
        return graphs

    def build_progressive_graphs(
        self,
        tracks: Dict[int, PlayerTrack],
        team_mapping: Dict[int, int],
        team_names: Dict[int, str],
        chunk_size: int = 300,  # 10 seconds @ 30fps
    ) -> Dict[int, List[MovementGraph]]:
        """Construir grafos de movimentação em chunks de tempo.

        Args:
            tracks: Dicionário de rastreamentos
            team_mapping: Mapeamento de times
            team_names: Nomes dos times
            chunk_size: Tamanho do chunk em frames

        Returns:
            Grafos por time e período {team_id: [graphs]}
        """
        # Encontrar intervalo de frames
        all_frames = []
        for track in tracks.values():
            all_frames.extend([p.frame for p in track.positions])

        if not all_frames:
            return {}

        min_frame = min(all_frames)
        max_frame = max(all_frames)

        # Dividir em chunks
        chunks = []
        for start_frame in range(min_frame, max_frame, chunk_size):
            end_frame = min(start_frame + chunk_size, max_frame)
            chunks.append((start_frame, end_frame))

        # Construir grafo para cada chunk
        result = defaultdict(list)

        for chunk_idx, (start_frame, end_frame) in enumerate(chunks):
            # Filtrar tracks para este chunk
            chunk_tracks = {}
            for player_id, track in tracks.items():
                chunk_positions = [
                    p for p in track.positions
                    if start_frame <= p.frame <= end_frame
                ]
                if chunk_positions:
                    chunk_track = PlayerTrack(
                        player_id=track.player_id,
                        team_id=track.team_id,
                        positions=chunk_positions,
                    )
                    chunk_tracks[player_id] = chunk_track

            # Construir grafo
            graphs = self.build_from_tracks(
                chunk_tracks,
                team_mapping,
                team_names,
                period=f"chunk_{chunk_idx}",
            )

            for team_id, graph in graphs.items():
                result[team_id].append(graph)

        return dict(result)


__all__ = [
    "PlayerPosition",
    "PlayerTrack",
    "MovementEdge",
    "MovementGraph",
    "MovementGraphBuilder",
]
