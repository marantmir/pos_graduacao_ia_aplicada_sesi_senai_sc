"""Tests para Video Analysis Module."""
import pytest
import numpy as np
from backend.app.video_analysis.movement_graph import (
    PlayerPosition,
    PlayerTrack,
    MovementEdge,
    MovementGraph,
    MovementGraphBuilder,
)


class TestPlayerPosition:
    def test_create_position(self):
        """Criar posição de jogador."""
        pos = PlayerPosition(
            player_id=1,
            team_id=0,
            x=100.0,
            y=200.0,
            x_field=50.0,
            y_field=34.0,
            frame=10,
        )
        assert pos.player_id == 1
        assert pos.team_id == 0
        assert pos.frame == 10

    def test_position_confidence(self):
        """Confiança da detecção."""
        pos = PlayerPosition(
            player_id=1, team_id=0, x=100.0, y=200.0,
            x_field=50.0, y_field=34.0, frame=10, confidence=0.95
        )
        assert pos.confidence == 0.95


class TestPlayerTrack:
    def test_create_track(self):
        """Criar rastreamento de jogador."""
        track = PlayerTrack(player_id=1, team_id=0)
        assert track.player_id == 1
        assert len(track.positions) == 0

    def test_add_position(self):
        """Adicionar posição ao rastreamento."""
        track = PlayerTrack(player_id=1, team_id=0)
        pos = PlayerPosition(
            player_id=1, team_id=0, x=100.0, y=200.0,
            x_field=50.0, y_field=34.0, frame=10
        )
        track.add_position(pos)
        assert len(track.positions) == 1

    def test_get_trajectory(self):
        """Obter trajetória como array."""
        track = PlayerTrack(player_id=1, team_id=0)
        for i in range(5):
            pos = PlayerPosition(
                player_id=1, team_id=0, x=100.0+i, y=200.0+i,
                x_field=50.0+i, y_field=34.0+i, frame=i
            )
            track.add_position(pos)

        trajectory = track.get_trajectory()
        assert trajectory.shape == (5, 2)
        assert trajectory[0, 0] == 50.0

    def test_distance_traveled(self):
        """Calcular distância percorrida."""
        track = PlayerTrack(player_id=1, team_id=0)
        positions = [
            (50.0, 34.0),
            (51.0, 34.0),
            (52.0, 34.0),
            (52.0, 35.0),
        ]
        for i, (x, y) in enumerate(positions):
            pos = PlayerPosition(
                player_id=1, team_id=0, x=0, y=0,
                x_field=x, y_field=y, frame=i
            )
            track.add_position(pos)

        distance = track.get_distance_traveled()
        # Should be ~3m (2m right + 1m down)
        assert distance > 2.5
        assert distance < 3.5

    def test_average_position(self):
        """Posição média do jogador."""
        track = PlayerTrack(player_id=1, team_id=0)
        positions = [(50.0, 34.0), (52.0, 36.0), (54.0, 38.0)]
        for i, (x, y) in enumerate(positions):
            pos = PlayerPosition(
                player_id=1, team_id=0, x=0, y=0,
                x_field=x, y_field=y, frame=i
            )
            track.add_position(pos)

        avg_x, avg_y = track.get_average_position()
        assert avg_x == pytest.approx(52.0)
        assert avg_y == pytest.approx(36.0)


class TestMovementEdge:
    def test_create_edge(self):
        """Criar aresta de movimento."""
        edge = MovementEdge(
            source_player_id=1,
            target_player_id=2,
            source_team=0,
            target_team=0,
        )
        assert edge.source_player_id == 1
        assert edge.target_player_id == 2

    def test_add_proximity(self):
        """Adicionar medição de proximidade."""
        edge = MovementEdge(
            source_player_id=1,
            target_player_id=2,
            source_team=0,
            target_team=0,
        )
        edge.add_proximity(5.0)
        edge.add_proximity(6.0)
        assert len(edge.proximities) == 2

    def test_avg_proximity(self):
        """Distância média de proximidade."""
        edge = MovementEdge(
            source_player_id=1,
            target_player_id=2,
            source_team=0,
            target_team=0,
        )
        edge.proximities = [5.0, 6.0, 7.0]
        assert edge.get_avg_proximity() == pytest.approx(6.0)

    def test_interaction_strength(self):
        """Força da interação."""
        edge = MovementEdge(
            source_player_id=1,
            target_player_id=2,
            source_team=0,
            target_team=0,
        )
        edge.proximities = [2.0]  # Muito próximo
        strength = edge.get_interaction_strength()
        assert strength > 0.8

        edge.proximities = [15.0]  # Distante
        strength = edge.get_interaction_strength()
        assert strength == pytest.approx(0.0)


class TestMovementGraph:
    def test_create_graph(self):
        """Criar grafo de movimentação."""
        graph = MovementGraph(team_id=0, team_name="Team A", period="1st_half")
        assert graph.team_id == 0
        assert len(graph.players) == 0

    def test_add_player(self):
        """Adicionar jogador ao grafo."""
        graph = MovementGraph(team_id=0, team_name="Team A", period="1st_half")
        track = PlayerTrack(player_id=1, team_id=0)
        graph.add_player(track)
        assert len(graph.players) == 1
        assert 1 in graph.players

    def test_add_edge(self):
        """Adicionar aresta ao grafo."""
        graph = MovementGraph(team_id=0, team_name="Team A", period="1st_half")
        edge = MovementEdge(
            source_player_id=1, target_player_id=2,
            source_team=0, target_team=0
        )
        graph.add_edge(edge)
        assert len(graph.edges) == 1

    def test_get_formation_matrix(self):
        """Obter matriz de formação."""
        graph = MovementGraph(team_id=0, team_name="Team A", period="1st_half")

        # Adicionar 3 jogadores
        for player_id in [1, 2, 3]:
            track = PlayerTrack(player_id=player_id, team_id=0)
            for i in range(3):
                pos = PlayerPosition(
                    player_id=player_id, team_id=0, x=0, y=0,
                    x_field=50.0 + player_id*10, y_field=34.0,
                    frame=i
                )
                track.add_position(pos)
            graph.add_player(track)

        formation = graph.get_formation_matrix()
        assert formation.shape == (3, 2)

    def test_centrality_scores(self):
        """Calcular scores de centralidade."""
        graph = MovementGraph(team_id=0, team_name="Team A", period="1st_half")

        # Adicionar 2 jogadores
        for player_id in [1, 2]:
            track = PlayerTrack(player_id=player_id, team_id=0)
            pos = PlayerPosition(
                player_id=player_id, team_id=0, x=0, y=0,
                x_field=50.0, y_field=34.0, frame=0
            )
            track.add_position(pos)
            graph.add_player(track)

        # Adicionar aresta
        edge = MovementEdge(
            source_player_id=1, target_player_id=2,
            source_team=0, target_team=0
        )
        edge.proximities = [5.0]
        graph.add_edge(edge)

        scores = graph.get_centrality_scores()
        assert len(scores) == 2
        assert scores[1] > 0
        assert scores[2] > 0


class TestMovementGraphBuilder:
    def test_create_builder(self):
        """Criar builder de grafos."""
        builder = MovementGraphBuilder()
        assert builder.field_width == 105.0
        assert builder.field_height == 68.0

    def test_build_from_tracks(self):
        """Construir grafos a partir de rastreamentos."""
        builder = MovementGraphBuilder()

        # Criar rastreamentos simulados
        tracks = {}
        for player_id in range(1, 6):
            track = PlayerTrack(player_id=player_id, team_id=0)
            for frame in range(10):
                pos = PlayerPosition(
                    player_id=player_id, team_id=0, x=0, y=0,
                    x_field=50.0 + frame, y_field=34.0,
                    frame=frame
                )
                track.add_position(pos)
            tracks[player_id] = track

        team_mapping = {i: 0 for i in range(1, 6)}
        team_names = {0: "Team A"}

        graphs = builder.build_from_tracks(tracks, team_mapping, team_names)

        assert len(graphs) == 1
        assert 0 in graphs
        graph = graphs[0]
        assert len(graph.players) == 5

    def test_progressive_graphs(self):
        """Construir grafos em chunks de tempo."""
        builder = MovementGraphBuilder()

        # Criar rastreamentos com múltiplos frames
        tracks = {}
        for player_id in range(1, 4):
            track = PlayerTrack(player_id=player_id, team_id=0)
            for frame in range(600):  # 600 frames
                pos = PlayerPosition(
                    player_id=player_id, team_id=0, x=0, y=0,
                    x_field=50.0, y_field=34.0,
                    frame=frame
                )
                track.add_position(pos)
            tracks[player_id] = track

        team_mapping = {i: 0 for i in range(1, 4)}
        team_names = {0: "Team A"}

        graphs = builder.build_progressive_graphs(
            tracks, team_mapping, team_names, chunk_size=300
        )

        assert 0 in graphs
        assert len(graphs[0]) == 2  # Dois chunks


class TestEdgeBuilding:
    def test_build_edges_from_proximity(self):
        """Construir arestas baseado em proximidade."""
        graph = MovementGraph(team_id=0, team_name="Team A", period="1st_half")

        # Jogador 1: movimento na linha x=50
        track1 = PlayerTrack(player_id=1, team_id=0)
        for frame in range(10):
            pos = PlayerPosition(
                player_id=1, team_id=0, x=0, y=0,
                x_field=50.0, y_field=34.0,
                frame=frame
            )
            track1.add_position(pos)
        graph.add_player(track1)

        # Jogador 2: movimento próximo (x=52)
        track2 = PlayerTrack(player_id=2, team_id=0)
        for frame in range(10):
            pos = PlayerPosition(
                player_id=2, team_id=0, x=0, y=0,
                x_field=52.0, y_field=34.0,
                frame=frame
            )
            track2.add_position(pos)
        graph.add_player(track2)

        # Construir arestas
        graph.build_edges_from_proximity(max_distance=5.0)

        # Deve ter uma aresta
        assert len(graph.edges) == 1
        edge = graph.edges[(1, 2)]
        assert edge.co_occurrences > 0
