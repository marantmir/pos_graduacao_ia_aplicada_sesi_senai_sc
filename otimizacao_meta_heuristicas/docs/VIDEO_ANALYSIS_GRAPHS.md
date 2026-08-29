# Video Analysis - Movement Graphs

Análise de vídeos de futebol com geração de **grafos de movimentação** mostrando rotas e conexões entre jogadores.

## Visão Geral

O módulo de Video Analysis processa dados de rastreamento de jogadores (provenientes de detecção YOLO + ByteTrack) e constrói grafos que mostram:

- 📊 **Rotas de Movimento**: Trajetórias dos jogadores transformadas para o plano do campo
- 🔗 **Conexões**: Arestas baseadas em proximidade entre jogadores
- ⭐ **Centralidade**: Scores indicando a importância tática de cada jogador
- 📍 **Formação**: Matriz de posições médias dos jogadores
- 🔥 **Heatmaps**: Densidade de atividade por zona do campo

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│ Video Input (MP4, AVI, etc)                             │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────▼────────────┐
         │  YOLO Player Detection │ (Roboflow sports)
         └───────────┬────────────┘
                     │
         ┌───────────▼────────────┐
         │  ByteTrack + Team Cls  │ (Player tracking)
         └───────────┬────────────┘
                     │
         ┌───────────▼────────────────────────┐
         │  ViewTransformer (Perspective Fix) │
         └───────────┬────────────────────────┘
                     │
         ┌───────────▼──────────────────┐
         │  MovementGraphBuilder        │ ◄─── Video Analysis
         │  (Create player tracks)      │
         └───────────┬──────────────────┘
                     │
         ┌───────────▼──────────────────┐
         │  MovementGraph               │
         │  (Player graph + statistics) │
         └───────────┬──────────────────┘
                     │
  ┌──────────────────┼──────────────────┐
  │                  │                  │
  ▼                  ▼                  ▼
GraphVisualizer  TacticalAnalysis  PerformanceMetrics
(Visualizations) (Tactical Stats)   (Distance, Speed)
```

## Componentes Principais

### 1. PlayerPosition
Representa a posição de um jogador em um frame específico.

```python
position = PlayerPosition(
    player_id=1,
    team_id=0,
    x=500.0,           # Coordenada no vídeo
    y=300.0,
    x_field=52.5,      # Coordenada no campo (após transformação)
    y_field=34.0,
    frame=120,
    confidence=0.95
)
```

### 2. PlayerTrack
Rastreamento completo de um jogador através de múltiplos frames.

```python
track = PlayerTrack(player_id=1, team_id=0)

# Adicionar posições ao longo do tempo
for frame in range(300):
    position = PlayerPosition(...)
    track.add_position(position)

# Obter estatísticas
distance = track.get_distance_traveled()  # em metros
avg_x, avg_y = track.get_average_position()
trajectory = track.get_trajectory()  # (n_frames, 2)
```

### 3. MovementEdge
Conexão entre dois jogadores baseada em proximidade.

```python
edge = MovementEdge(
    source_player_id=1,
    target_player_id=2,
    source_team=0,
    target_team=0
)

# Adicionar proximidades
edge.add_proximity(3.2)  # distância mínima em metros

# Obter força da interação (0-1)
strength = edge.get_interaction_strength()
```

### 4. MovementGraph
Grafo completo de movimentação de um time.

```python
graph = MovementGraph(
    team_id=0,
    team_name="Flamengo",
    period="1st_half"
)

# Adicionar jogadores
for track in tracks.values():
    graph.add_player(track)

# Construir arestas baseado em proximidade
graph.build_edges_from_proximity(
    min_distance=0.5,
    max_distance=15.0
)

# Obter estatísticas
centrality = graph.get_centrality_scores()
formation = graph.get_formation_matrix()
```

### 5. MovementGraphBuilder
Construtor de grafos a partir de dados de rastreamento.

```python
builder = MovementGraphBuilder(
    field_width=105.0,  # FIFA standard
    field_height=68.0   # FIFA standard
)

# Construir grafos por time
graphs = builder.build_from_tracks(
    tracks=player_tracks,
    team_mapping={1: 0, 2: 0, 3: 1, ...},  # player_id -> team_id
    team_names={0: "Flamengo", 1: "Botafogo"},
    period="1st_half"
)

# Ou em chunks de tempo
progressive_graphs = builder.build_progressive_graphs(
    tracks=player_tracks,
    team_mapping=team_mapping,
    team_names=team_names,
    chunk_size=300  # 10 segundos @ 30fps
)
```

## Visualizações

### GraphVisualizer
Visualiza grafos de movimentação em múltiplos modos.

```python
visualizer = GraphVisualizer(figsize=(16, 10))

# 1. Grafo de movimento com trajetórias
fig1 = visualizer.plot_movement_graph(
    graph=graph,
    show_edges=True,
    show_trajectories=True,
    edge_width_multiplier=2.0
)
fig1.savefig("movement_graph.png")

# 2. Heatmap de densidade
fig2 = visualizer.plot_heatmap(
    graph=graph,
    resolution=20  # Grid 20x20
)
fig2.savefig("heatmap.png")

# 3. Formação média
fig3 = visualizer.plot_formation(graph=graph)
fig3.savefig("formation.png")
```

### Interpretação das Visualizações

**Movement Graph**:
- **Nós**: Posição média de cada jogador
- **Tamanho do nó**: Centralidade do jogador (mais conexões = maior)
- **Arestas**: Proximidade entre jogadores
- **Largura da aresta**: Força da interação
- **Linhas finas**: Trajetórias dos jogadores

**Heatmap**:
- **Vermelho/Quente**: Alta densidade de movimento (zona de atividade)
- **Azul/Frio**: Baixa densidade (zona menos usada)
- Útil para identificar zonas táticas preferidas

**Formation**:
- **Zonas coloridas**: Defesa, Meio-campo, Ataque
- **Linhas conectadas**: Padrão de posicionamento
- Mostra estrutura tática média

## Estatísticas & Métricas

### Distância Percorrida
```python
distance = track.get_distance_traveled()  # em metros
# Para um jogador em 10 minutos @ 30fps: ~100-200m
```

### Centralidade do Jogador
```python
scores = graph.get_centrality_scores()
# Baseado em:
# - Número de conexões
# - Força das conexões
# - Posicionamento
```

### Cobertura de Área
```python
area = graph.get_player_coverage_area(player_id=1)  # m²
# Usa ConvexHull da trajetória
```

### Força de Interação
```python
strength = edge.get_interaction_strength()  # 0-1
# 1.0 = muito próximo e frequentemente próximo
# 0.0 = distante ou raramente próximo
```

## Integração com Roboflow Sports

O módulo é projetado para trabalhar com o pipeline Roboflow:

```python
import cv2
from ultralytics import YOLO
import supervision as sv
from sports.common.view import ViewTransformer
from sports.common.team import TeamClassifier

from backend.app.video_analysis.movement_graph import (
    PlayerPosition, PlayerTrack, MovementGraphBuilder
)

# 1. Detecção de jogadores (Roboflow YOLO)
player_model = YOLO("player_detection.pt")
tracker = sv.ByteTrack()

# 2. Transformação de perspectiva (campo)
transformer = ViewTransformer(source_points, target_points)

# 3. Classificação de times
team_classifier = TeamClassifier()

# 4. Rastreamento
tracks_dict = {}

for frame in video_frames:
    # Detectar
    detections = player_model(frame)
    detections = tracker.update_with_detections(detections)
    
    # Transformar para campo
    xy_field = transformer.transform_points(detections.get_anchors_coordinates())
    
    # Classificar time
    crops = sv.crop_image(frame, detections.xyxy)
    team_ids = team_classifier.predict(crops)
    
    # Construir posições
    for i, (player_id, (x_field, y_field), team_id) in enumerate(zip(
        detections.tracker_id, xy_field, team_ids
    )):
        position = PlayerPosition(
            player_id=player_id,
            team_id=team_id,
            x=detections.xyxy[i, 0],
            y=detections.xyxy[i, 1],
            x_field=x_field,
            y_field=y_field,
            frame=frame_idx
        )
        
        if player_id not in tracks_dict:
            tracks_dict[player_id] = PlayerTrack(
                player_id=player_id,
                team_id=team_id
            )
        tracks_dict[player_id].add_position(position)

# 5. Construir grafos
builder = MovementGraphBuilder()
graphs = builder.build_from_tracks(
    tracks=tracks_dict,
    team_mapping={i: tracks_dict[i].team_id for i in tracks_dict},
    team_names={0: "Team A", 1: "Team B"}
)

# 6. Visualizar
visualizer = GraphVisualizer()
for team_id, graph in graphs.items():
    fig = visualizer.plot_movement_graph(graph)
    fig.savefig(f"team_{team_id}_graph.png")
```

## Casos de Uso

### 1. Análise Tática
```python
# Identificar jogadores-chave
centrality = graph.get_centrality_scores()
key_players = sorted(
    centrality.items(),
    key=lambda x: x[1],
    reverse=True
)[:3]
```

### 2. Padrões de Movimento
```python
# Detectar zonas preferidas
heatmap = visualizer.plot_heatmap(graph)
# Identifica áreas de alta atividade
```

### 3. Comparação de Períodos
```python
# Grafo antes/depois de substituição
graphs_1st = builder.build_progressive_graphs(
    tracks, team_mapping, team_names, chunk_size=600
)[0][0]  # Primeiro time, primeiros 20s

graphs_2nd = builder.build_progressive_graphs(
    tracks, team_mapping, team_names, chunk_size=600
)[0][1]  # Primeiro time, próximos 20s

# Comparar distâncias percorridas
dist_1st = sum(t.get_distance_traveled() for t in graphs_1st.players.values())
dist_2nd = sum(t.get_distance_traveled() for t in graphs_2nd.players.values())
```

### 4. Formação Dinâmica
```python
# Monitorar mudanças de formação
formations = []
for graph in progressive_graphs:
    formation = graph.get_formation_matrix()
    formations.append(formation)

# Detectar mudanças significativas
```

## Parâmetros de Configuração

### ViewTransformer (Roboflow sports)
```python
# Pontos de origem (vídeo) para pontos de destino (campo)
source_points = np.array([
    [x1_video, y1_video],  # Canto inferior esquerdo
    [x2_video, y2_video],  # Canto inferior direito
    [x3_video, y3_video],  # Canto superior direito
    [x4_video, y4_video],  # Canto superior esquerdo
])

target_points = np.array([
    [0, 68],        # Canto inferior esquerdo do campo
    [105, 68],      # Canto inferior direito do campo
    [105, 0],       # Canto superior direito do campo
    [0, 0],         # Canto superior esquerdo do campo
])

transformer = ViewTransformer(source_points, target_points)
```

### Proximidade para Arestas
```python
# Distância mínima e máxima para considerar conexão
graph.build_edges_from_proximity(
    min_distance=0.5,    # Não considerar contato direto
    max_distance=15.0    # Máximo 15m de distância
)
```

### Densidade de Heatmap
```python
# Resolução do grid (maior = mais detalhe)
fig = visualizer.plot_heatmap(
    graph=graph,
    resolution=20  # Grid 20x20 (cada célula ~5m x 3.4m)
)
```

## Performance

- **Processamento**: ~1ms por frame para 11 jogadores
- **Memória**: ~10MB para grafo de 300 frames
- **Visualização**: ~2s para plotar completo grafo

## Requisitos

```
numpy
scipy (para ConvexHull)
networkx (para análise de grafo)
matplotlib (para visualizações, opcional)
```

## Exemplos

Ver `backend/app/video_analysis/example.py`:

```bash
python -m backend.app.video_analysis.example
```

## Testes

```bash
pytest backend/tests/test_video_analysis.py -v
# 20 testes, todos passando
```

## Roadmap

- [ ] Integração em tempo real com pipeline de vídeo
- [ ] Análise de passes (pass network graphs)
- [ ] Detecção de formações (k-means clustering)
- [ ] Métricas de pressão e espaço
- [ ] Export de dados (JSON, CSV)
- [ ] Dashboard web para visualização
- [ ] Comparação inter-jogo (benchmarking)

## Referências

- **Roboflow Sports**: https://github.com/roboflow/sports
- **Supervision**: https://github.com/roboflow/supervision
- **NetworkX**: https://networkx.org/
- **Matplotlib**: https://matplotlib.org/
