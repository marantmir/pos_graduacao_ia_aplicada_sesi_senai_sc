"""Example Usage - Análise de Movimentações com Grafos

Demonstra como usar o módulo de Video Analysis para criar
e visualizar grafos de movimento de jogadores.
"""
import numpy as np
from .movement_graph import PlayerPosition, PlayerTrack, MovementGraphBuilder

try:
    from .visualization import GraphVisualizer
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def example_create_movement_graph():
    """Exemplo: Criar grafo de movimentação."""

    # Simular rastreamento de 11 jogadores (um time)
    tracks = {}

    for player_id in range(1, 12):
        track = PlayerTrack(player_id=player_id, team_id=0)

        # Simular movimento durante 300 frames (~10 segundos @ 30fps)
        for frame in range(300):
            # Posição simulada no vídeo
            x = 100 + player_id * 50 + np.sin(frame / 30) * 100
            y = 200 + player_id * 20 + np.cos(frame / 40) * 50

            # Transformar para coordenadas do campo
            # (Normalmente viria de ViewTransformer)
            x_field = (x / 1920) * 105  # Normalizar para 105m
            y_field = (y / 1080) * 68   # Normalizar para 68m

            position = PlayerPosition(
                player_id=player_id,
                team_id=0,
                x=x,
                y=y,
                x_field=x_field,
                y_field=y_field,
                frame=frame,
                confidence=0.9,
            )
            track.add_position(position)

        tracks[player_id] = track

    # Construir grafo
    builder = MovementGraphBuilder()
    team_mapping = {i: 0 for i in range(1, 12)}
    team_names = {0: "Flamengo"}

    graphs = builder.build_from_tracks(
        tracks=tracks,
        team_mapping=team_mapping,
        team_names=team_names,
        period="1st_half",
    )

    return graphs[0]


def example_visualize_graph():
    """Exemplo: Visualizar grafo de movimentação."""

    # Criar grafo
    graph = example_create_movement_graph()

    # Visualizar
    visualizer = GraphVisualizer(figsize=(16, 10))

    # 1. Grafo de movimento com arestas e trajetórias
    fig1 = visualizer.plot_movement_graph(
        graph=graph,
        title="Flamengo - Movement Graph (1st Half)",
        show_edges=True,
        show_trajectories=True,
    )
    fig1.savefig("movement_graph.png", dpi=150, facecolor='#2a2a2a')
    print("✓ Saved: movement_graph.png")

    # 2. Heatmap de densidade
    fig2 = visualizer.plot_heatmap(
        graph=graph,
        title="Flamengo - Movement Density Heatmap",
        resolution=15,
    )
    fig2.savefig("heatmap.png", dpi=150, facecolor='#2a2a2a')
    print("✓ Saved: heatmap.png")

    # 3. Formação média
    fig3 = visualizer.plot_formation(
        graph=graph,
        title="Flamengo - Average Formation",
    )
    fig3.savefig("formation.png", dpi=150, facecolor='#2a2a2a')
    print("✓ Saved: formation.png")


def example_analyze_graph():
    """Exemplo: Analisar estatísticas do grafo."""

    # Criar grafo
    graph = example_create_movement_graph()

    print("\n📊 Movement Graph Analysis")
    print("=" * 50)
    print(f"Team: {graph.team_name}")
    print(f"Period: {graph.period}")
    print(f"Players: {len(graph.players)}")
    print(f"Connections: {len(graph.edges)}")
    print(f"Total Frames: {graph.total_frames}")

    print("\n🏃 Player Statistics:")
    print("-" * 50)
    for player_id in sorted(graph.players.keys()):
        track = graph.players[player_id]
        distance = track.get_distance_traveled()
        avg_x, avg_y = track.get_average_position()
        print(f"  Player {player_id:2d}: {distance:6.1f}m distance | "
              f"Avg pos: ({avg_x:5.1f}, {avg_y:5.1f})")

    print("\n🔗 Connection Strength:")
    print("-" * 50)
    for (src, dst), edge in list(graph.edges.items())[:5]:
        strength = edge.get_interaction_strength()
        co_occ = edge.co_occurrences
        print(f"  Player {src} <-> {dst}: "
              f"strength={strength:.2f}, co-occurrence={co_occ}")

    print("\n⭐ Centrality Scores:")
    print("-" * 50)
    centrality = graph.get_centrality_scores()
    for player_id in sorted(centrality.keys(),
                           key=lambda x: centrality[x],
                           reverse=True)[:5]:
        score = centrality[player_id]
        print(f"  Player {player_id:2d}: {score:6.2f}")

    print("\n📍 Formation:")
    print("-" * 50)
    formation = graph.get_formation_matrix()
    print(f"  Positions shape: {formation.shape}")
    print(f"  X range: [{formation[:, 0].min():.1f}, {formation[:, 0].max():.1f}]")
    print(f"  Y range: [{formation[:, 1].min():.1f}, {formation[:, 1].max():.1f}]")

    print("\n✅ Analysis complete!\n")


if __name__ == "__main__":
    # Executar exemplos
    print("🎬 Video Analysis - Movement Graph Examples\n")

    # Analisar grafo
    example_analyze_graph()

    # Visualizar (comentado para não salvar imagens)
    # example_visualize_graph()
