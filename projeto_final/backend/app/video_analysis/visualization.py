"""Visualization - Desenha grafos de movimentação em campo tático

Cria visualizações 2D de:
- Rotas de jogadores (trajetórias)
- Conexões de movimento (arestas)
- Heatmaps de cobertura
- Formação dinâmica
- Análise de posicionamento
"""
from __future__ import annotations

import logging
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx
import numpy as np
from typing import Optional, Tuple, Dict
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, Circle
from matplotlib.collections import LineCollection

from .movement_graph import MovementGraph, PlayerTrack

logger = logging.getLogger(__name__)


class FieldDrawer:
    """Desenha campo de futebol."""

    def __init__(self, ax, field_width: float = 105.0, field_height: float = 68.0):
        self.ax = ax
        self.field_width = field_width
        self.field_height = field_height

    def draw_field(self, line_color: str = 'white', background_color: str = 'green'):
        """Desenhar linhas do campo."""
        self.ax.set_xlim(0, self.field_width)
        self.ax.set_ylim(0, self.field_height)
        self.ax.set_aspect('equal')
        self.ax.invert_yaxis()  # Campo começa do topo
        self.ax.set_facecolor(background_color)

        # Linhas principais
        # Linha central
        self.ax.plot([self.field_width / 2, self.field_width / 2],
                     [0, self.field_height], color=line_color, linewidth=2)

        # Linhas das áreas
        self.ax.add_patch(patches.Rectangle(
            (0, self.field_height / 2 - 20.16), 16.5, 40.32,
            fill=False, edgecolor=line_color, linewidth=2))
        self.ax.add_patch(patches.Rectangle(
            (self.field_width - 16.5, self.field_height / 2 - 20.16), 16.5, 40.32,
            fill=False, edgecolor=line_color, linewidth=2))

        # Círculos de escanteio
        circle_radius = 9.15
        self.ax.add_patch(Circle((circle_radius, 0), circle_radius,
                                 fill=False, edgecolor=line_color, linewidth=2))
        self.ax.add_patch(Circle((self.field_width - circle_radius, 0), circle_radius,
                                 fill=False, edgecolor=line_color, linewidth=2))
        self.ax.add_patch(Circle((circle_radius, self.field_height), circle_radius,
                                 fill=False, edgecolor=line_color, linewidth=2))
        self.ax.add_patch(Circle((self.field_width - circle_radius, self.field_height), circle_radius,
                                 fill=False, edgecolor=line_color, linewidth=2))

        # Círculo central
        self.ax.add_patch(Circle((self.field_width / 2, self.field_height / 2), 9.15,
                                 fill=False, edgecolor=line_color, linewidth=2))

        self.ax.set_xlabel('Distance (m)')
        self.ax.set_ylabel('Distance (m)')

    def draw_goal_areas(self, line_color: str = 'white'):
        """Desenhar áreas de gol."""
        goal_area_width = 40.32
        goal_area_height = 16.5

        self.ax.add_patch(patches.Rectangle(
            (0, self.field_height / 2 - goal_area_width / 2),
            goal_area_height, goal_area_width,
            fill=False, edgecolor=line_color, linewidth=1, linestyle='--', alpha=0.5))
        self.ax.add_patch(patches.Rectangle(
            (self.field_width - goal_area_height, self.field_height / 2 - goal_area_width / 2),
            goal_area_height, goal_area_width,
            fill=False, edgecolor=line_color, linewidth=1, linestyle='--', alpha=0.5))


class GraphVisualizer:
    """Visualizador de grafos de movimentação."""

    def __init__(self, figsize: Tuple[int, int] = (16, 10)):
        self.figsize = figsize

    def plot_movement_graph(
        self,
        graph: MovementGraph,
        title: Optional[str] = None,
        show_edges: bool = True,
        show_trajectories: bool = True,
        edge_width_multiplier: float = 2.0,
    ) -> Figure:
        """Visualizar grafo de movimentação de um time.

        Args:
            graph: Grafo de movimentação
            title: Título da figura
            show_edges: Mostrar arestas (conexões)
            show_trajectories: Mostrar trajetórias dos jogadores
            edge_width_multiplier: Multiplicador da largura das arestas

        Returns:
            Figura matplotlib
        """
        fig, ax = plt.subplots(figsize=self.figsize, facecolor='#2a2a2a')

        # Desenhar campo
        field_drawer = FieldDrawer(ax, graph.field_width, graph.field_height)
        field_drawer.draw_field(line_color='white', background_color='#1a5c1a')
        field_drawer.draw_goal_areas()

        # Cores para visualização
        color_map = {0: '#FF1493', 1: '#00BFFF', 2: '#FFD700', 3: '#FF6347'}
        team_color = color_map.get(graph.team_id, '#FFFFFF')

        # Desenhar trajetórias
        if show_trajectories:
            for player_id, track in graph.players.items():
                trajectory = track.get_trajectory()
                if len(trajectory) > 1:
                    ax.plot(trajectory[:, 0], trajectory[:, 1],
                           color=team_color, alpha=0.3, linewidth=1, label='Trajectory' if player_id == 0 else '')

        # Criar grafo networkx para visualização
        G = nx.DiGraph() if not show_edges else nx.Graph()

        # Adicionar nós
        node_positions = {}
        for player_id, track in graph.players.items():
            avg_x, avg_y = track.get_average_position()
            node_positions[player_id] = (avg_x, avg_y)
            G.add_node(player_id)

        # Adicionar arestas
        if show_edges:
            for (src, dst), edge in graph.edges.items():
                strength = edge.get_interaction_strength()
                if strength > 0:
                    G.add_edge(src, dst, weight=strength)

        # Desenhar arestas
        if show_edges and len(G.edges()) > 0:
            edges = G.edges()
            weights = [G[u][v]['weight'] for u, v in edges]
            max_weight = max(weights) if weights else 1

            for (u, v), weight in zip(edges, weights):
                x_start, y_start = node_positions[u]
                x_end, y_end = node_positions[v]
                width = (weight / max_weight) * edge_width_multiplier

                ax.annotate('', xy=(x_end, y_end), xytext=(x_start, y_start),
                           arrowprops=dict(arrowstyle='->', lw=width,
                                         color=team_color, alpha=0.6))

        # Desenhar nós (jogadores)
        centrality = graph.get_centrality_scores()
        for player_id, (x, y) in node_positions.items():
            size = 200 + (centrality.get(player_id, 0) * 100)
            ax.scatter(x, y, s=size, c=team_color, edgecolors='white',
                      linewidth=2, alpha=0.8, zorder=10)
            ax.text(x, y, str(player_id), color='white', ha='center', va='center',
                   fontsize=8, fontweight='bold', zorder=11)

        # Título e labels
        team_name = graph.team_name
        if title is None:
            title = f'{team_name} - Movement Graph ({graph.period})'
        ax.set_title(title, color='white', fontsize=16, fontweight='bold', pad=20)

        # Estatísticas
        total_distance = sum(track.get_distance_traveled() for track in graph.players.values())
        avg_players = len(graph.players)
        total_connections = len(graph.edges)

        stats_text = f'Players: {avg_players} | Connections: {total_connections} | Total Distance: {total_distance:.0f}m'
        ax.text(0.5, -0.05, stats_text, transform=ax.transAxes,
               ha='center', color='white', fontsize=10, bbox=dict(boxstyle='round', facecolor='#1a1a1a', alpha=0.7))

        ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')

        plt.tight_layout()
        return fig

    def plot_heatmap(
        self,
        graph: MovementGraph,
        title: Optional[str] = None,
        resolution: int = 20,
    ) -> Figure:
        """Visualizar heatmap de densidade de movimento.

        Args:
            graph: Grafo de movimentação
            title: Título da figura
            resolution: Resolução do grid

        Returns:
            Figura matplotlib
        """
        fig, ax = plt.subplots(figsize=self.figsize, facecolor='#2a2a2a')

        # Desenhar campo
        field_drawer = FieldDrawer(ax, graph.field_width, graph.field_height)
        field_drawer.draw_field(line_color='white', background_color='#1a1a1a')

        # Coletar todos os pontos de posição
        all_points = []
        for track in graph.players.values():
            trajectory = track.get_trajectory()
            all_points.extend(trajectory)

        if not all_points:
            ax.set_title('No data', color='white')
            return fig

        all_points = np.array(all_points)

        # Criar heatmap
        heatmap, xedges, yedges = np.histogram2d(
            all_points[:, 0], all_points[:, 1],
            bins=resolution,
            range=[[0, graph.field_width], [0, graph.field_height]]
        )

        # Transpor para match com coordenadas
        heatmap = heatmap.T

        # Desenhar heatmap
        im = ax.imshow(heatmap, extent=[0, graph.field_width, graph.field_height, 0],
                       aspect='auto', cmap='hot', alpha=0.6, origin='upper')

        # Colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Activity Density', color='white')
        cbar.ax.tick_params(colors='white')

        # Título
        team_name = graph.team_name
        if title is None:
            title = f'{team_name} - Movement Density Heatmap'
        ax.set_title(title, color='white', fontsize=16, fontweight='bold')

        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')

        plt.tight_layout()
        return fig

    def plot_formation(
        self,
        graph: MovementGraph,
        title: Optional[str] = None,
    ) -> Figure:
        """Visualizar formação média dos jogadores.

        Args:
            graph: Grafo de movimentação
            title: Título da figura

        Returns:
            Figura matplotlib
        """
        fig, ax = plt.subplots(figsize=(14, 10), facecolor='#2a2a2a')

        # Desenhar campo
        field_drawer = FieldDrawer(ax, graph.field_width, graph.field_height)
        field_drawer.draw_field(line_color='white', background_color='#1a5c1a')

        # Cores
        color_map = {0: '#FF1493', 1: '#00BFFF', 2: '#FFD700', 3: '#FF6347'}
        team_color = color_map.get(graph.team_id, '#FFFFFF')

        # Plotar formação média
        formation_matrix = graph.get_formation_matrix()
        if len(formation_matrix) > 0:
            # Agrupar por zona (defesa, meio-campo, ataque)
            def_zone = formation_matrix[formation_matrix[:, 0] < 35]
            mid_zone = formation_matrix[(formation_matrix[:, 0] >= 35) & (formation_matrix[:, 0] < 70)]
            att_zone = formation_matrix[formation_matrix[:, 0] >= 70]

            # Desenhar zonas com cores diferentes
            for zone, alpha, label in [(def_zone, 0.3, 'Defense'),
                                       (mid_zone, 0.5, 'Midfield'),
                                       (att_zone, 0.7, 'Attack')]:
                if len(zone) > 0:
                    ax.scatter(zone[:, 0], zone[:, 1], s=300, c=team_color,
                             alpha=alpha, edgecolors='white', linewidth=2, label=label)

            # Conectar com linhas para mostrar padrão
            formation_matrix_sorted = formation_matrix[np.argsort(formation_matrix[:, 1])]
            for i in range(len(formation_matrix_sorted) - 1):
                ax.plot([formation_matrix_sorted[i, 0], formation_matrix_sorted[i+1, 0]],
                       [formation_matrix_sorted[i, 1], formation_matrix_sorted[i+1, 1]],
                       color=team_color, alpha=0.3, linewidth=1)

        # Título
        team_name = graph.team_name
        if title is None:
            title = f'{team_name} - Average Formation'
        ax.set_title(title, color='white', fontsize=16, fontweight='bold')
        ax.legend(loc='upper right', facecolor='#1a1a1a', edgecolor='white', labelcolor='white')

        ax.tick_params(colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')

        plt.tight_layout()
        return fig


__all__ = [
    "FieldDrawer",
    "GraphVisualizer",
]
