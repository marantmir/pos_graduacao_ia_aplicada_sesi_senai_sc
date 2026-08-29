# Arquitetura

## Visao Geral

O Football Intelligence Platform e uma aplicacao full stack com frontend React, backend FastAPI e persistencia local em SQLite.

```text
Usuario
  -> Frontend React/Vite
  -> Cliente HTTP
  -> Backend FastAPI
  -> Busca publica Wikimedia
  -> Data store JSON local
  -> Modulo de grafos taticos
  -> Modulo de leitura visual de videos
  -> SQLite para historico
```

## Backend

Arquivos principais em `backend/app`:

- `main.py`: inicializa FastAPI, CORS, rotas e frontend buildado.
- `database.py`: cria e consulta historico em SQLite.
- `data_store.py`: carrega dados locais em JSON.
- `online_search.py`: busca publica e fallback de modo local.
- `graph_analysis.py`: monta nos, arestas, metricas e insights de rede.
- `video_vision.py`: monta mapa de calor, trilhas, frames e eventos de video.
- `routes/teams.py`: endpoints de times, fontes, grafo, video e inteligencia publica.
- `routes/analysis.py`: pre-analise, criacao de analise e historico.
- `routes/reports.py`: relatorio final consolidado.

## Frontend

Principais telas:

- Dashboard
- Nova analise
- Busca de time
- Dossie tatico
- Formacoes com grafo visual
- Elenco
- Fontes, videos e leitura visual
- Plano de jogo
- Relatorio final
- Historico
- Inteligencia avancada

## Dados e Evidencias

Os dados locais ficam em `backend/data`. Eles sustentam a experiencia quando uma API externa nao esta disponivel e sao combinados com busca publica na pre-analise.

A busca publica retorna fontes quando a rede permite. Quando a consulta externa falha, o backend retorna `local_fallback` com uma fonte publica sugerida e mantem o fluxo de analise ativo.

## Deploy

O `Dockerfile` cria o build React e serve os arquivos estaticos pelo FastAPI. Assim, um unico endpoint publico abre a interface e responde as rotas `/api`.

## Extensoes

As proximas evolucoes naturais sao:

- Upload de video e extracao real de tracking.
- Integracao com APIs esportivas premium.
- Otimizacao numerica para formacao, estrategia e substituicoes.
- Relatorios exportados em PDF com evidencias anexadas.
