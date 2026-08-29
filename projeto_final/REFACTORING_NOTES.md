# Refatoração para Football Intelligence Platform

## Objetivo

Transformar a aplicação em uma plataforma neutra de inteligência para futebol, sem dependência de identidade visual ou técnica anterior, e aproximar a saída do sistema da linguagem de decisão usada por treinadores, analistas de desempenho e comissão técnica.

## Principais mudanças

### Identidade e infraestrutura

- Nome do produto alterado para `Football Intelligence Platform`.
- Logo proprietário removido; a interface usa um componente vetorial interno (`BrandMark.jsx`).
- Nome do banco alterado para `football_intelligence.db`.
- Logger alterado para `football_intelligence`.
- Chaves de `localStorage`, variáveis de ambiente, feature flags e configuração de deploy foram neutralizadas.
- URLs e instruções de repositório foram substituídas por placeholders genéricos.

### Inteligência para o treinador

Novo módulo: `backend/app/coach_intelligence.py`.

Ele consolida:

- formação provável e aderência;
- modelo ofensivo e defensivo;
- transição ofensiva e defensiva;
- corredor preferencial de progressão;
- zona crítica de risco;
- prioridades táticas;
- jogadores-chave e produção disponível;
- alertas de carga/risco cadastrados;
- bola parada;
- foco de treino;
- ajustes de formação por estado do jogo;
- qualidade da evidência e lacunas de dados.

Duas perspectivas estão disponíveis:

- `opponent`: preparação para enfrentar o time analisado;
- `own_team`: diagnóstico e desenvolvimento do próprio time.

Estados do jogo:

- `balanced`;
- `winning`;
- `drawing`;
- `losing`.

### Fluxo único por nome do time

Novo endpoint:

`GET /api/teams/intelligence?name=TIME&perspective=opponent&game_state=balanced`

O endpoint tenta, nesta ordem:

1. time local;
2. perfil online já salvo;
3. busca pública ao vivo.

A resposta reúne perfil, fontes e `coach_insights`.

### Endpoints de insight

- `GET /api/teams/{team_id}/coach-insights`
- `GET /api/teams/workspace/{team_ref}/coach-insights`

Parâmetros:

- `perspective=opponent|own_team`
- `game_state=balanced|winning|drawing|losing`

### Nova tela

Nova página React: `frontend/src/pages/CoachInsights.jsx`.

A tela permite alternar:

- enfrentar adversário / diagnóstico próprio;
- plano-base / vencendo / empatando / perdendo.

Ela exibe recomendações de forma executiva, mantendo a evidência ao lado da ação sugerida.

## Fontes e limites

A plataforma continua usando busca pública, Wikipedia, referências de vídeo, dados locais, visão computacional, grafos e pesquisa operacional. O motor não inventa estatísticas ausentes: quando faltam elenco, vídeo ou fontes, a resposta reduz a confiança e lista as lacunas.

Para performance profissional de alta precisão, o ponto natural de evolução é conectar provedores estruturados de eventos, tracking, disponibilidade médica e carga física ao mesmo modelo de dados. Essa integração deve ser feita por adaptadores, sem acoplar a lógica de decisão a um fornecedor específico.

## Validação executada

- Compilação Python (`compileall`) concluída sem erro.
- 92 testes críticos de backend passaram em conjunto após a refatoração.
- Testes específicos do novo motor de insights e do fluxo por nome passaram.
- O build do frontend não pôde ser concluído neste ambiente porque uma dependência npm não estava disponível em cache e o acesso ao registry expirou. O código JSX foi revisado estaticamente e o projeto mantém `package-lock.json` atualizado com o novo nome.
