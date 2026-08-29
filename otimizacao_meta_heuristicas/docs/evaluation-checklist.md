# Checklist da Avaliacao

## Endpoint Funcional

- [x] Backend FastAPI responde em `/api/health`.
- [x] Frontend React pode ser servido pelo build de producao.
- [x] Rotas de API funcionam com modo local quando a rede externa falha.
- [x] Dockerfile incluido para deploy.
- [ ] Inserir link publico apos publicacao.

## Complexidade e Ambicao

- [x] Problema real de analise tatica.
- [x] Mais de 5 telas navegaveis.
- [x] Busca local e publica por time.
- [x] Botao `Analisar` antes de salvar.
- [x] Pre-analise com fontes, grafo, visao computacional e pesquisa operacional.
- [x] Grafo visual de conexoes taticas.
- [x] Mapa visual de videos com calor, trilhas e eventos.
- [x] Plano de jogo e relatorio final.
- [x] Historico persistido em SQLite.
- [x] Nao e chatbot simples.

## GitHub

- [x] Estrutura clara de pastas.
- [x] `.gitignore` adequado.
- [x] README atualizado.
- [x] Pasta `docs`.
- [x] Repositorio Git local inicializado em `main`.
- [x] Remote `origin` configurado.
- [ ] Fazer push para o GitHub.

## Validacao Tecnica

- [x] Endpoints novos: `graph-analysis`, `video-vision`, `public-intelligence`.
- [x] Frontend consome as novas rotas.
- [x] Build Vite validado.
- [x] Code-splitting por rota (`React.lazy`/`Suspense`) no frontend.
- [x] CORS do FastAPI restrito por `ALLOWED_ORIGINS` (nao mais `*`).
- [x] Rate limiting nas rotas de upload de video (429 + `Retry-After`).
- [x] Logging estruturado em JSON com `request_id`/`X-Request-ID`.
- [x] Suite `pytest` cobrindo `graph_analysis`, `video_vision`, rate limiting, logging e rotas de `teams`/`analysis`.
- [x] Fluxo analisado no navegador local.
- [ ] Validar console no endpoint publicado.
