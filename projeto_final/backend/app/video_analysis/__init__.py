"""Video Analysis Module for Football Intelligence Platform

Análise de vídeos de futebol com rastreamento de jogadores e grafos de movimentações.

Componentes:
- player_tracking.py: Detecção e rastreamento de jogadores via YOLO + ByteTrack
- team_classifier.py: Classificação de times baseada em cores de uniforme
- movement_graph.py: Construção de grafos de movimentação dos jogadores
- field_transformer.py: Transformação de perspectiva (vídeo → campo 2D)
- visualization.py: Visualização de grafos e heatmaps de movimentação

Exemplo de uso:

    from backend.app.video_analysis.player_tracking import PlayerTracker
    from backend.app.video_analysis.movement_graph import MovementGraphBuilder
    from backend.app.video_analysis.visualization import GraphVisualizer

    # Rastrear jogadores em vídeo
    tracker = PlayerTracker(model_path="models/player_detection.pt")
    tracks = tracker.process_video("video.mp4")

    # Construir grafos de movimentação
    graph_builder = MovementGraphBuilder()
    graphs = graph_builder.build_from_tracks(tracks)

    # Visualizar grafos
    visualizer = GraphVisualizer()
    visualizer.plot_movement_graph(graphs[0], team="Flamengo")
"""

__version__ = "1.0.0"
