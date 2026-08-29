# Oportunidades de Qualidade e Performance

Registro do loop de análise (Agente de Qualidade e Performance) sobre o backend
FastAPI e o frontend React/Vite deste repositório. Cada oportunidade foi
analisada, implementada como PoC, validada e documentada conforme o contrato
`program.md`.

> Nota de adaptação ao stack: o projeto é Python (FastAPI) + JavaScript/JSX
> (React/Vite), não TypeScript. Os "Comandos de Verificação" do contrato foram
> mapeados para as ferramentas reais do repositório:
> - `npm run lint` → não há script de lint configurado neste repositório
>   (sem ESLint/Ruff commitado); usado `pyflakes` como ferramenta de análise
>   avulsa (não adicionada às dependências do projeto) para varrer código morto.
> - `npm run test` → `pytest` (backend, 51 testes) — não há suíte de testes
>   JS configurada no frontend.
> - `npm run build` → `python -m py_compile` (checagem de compilação do
>   backend) + `npm run build` real do frontend (Vite).

Baseline antes de qualquer mudança: **51 testes backend passando**, build do
frontend concluído sem erros (chunk principal `index-*.js` 252.34 kB / gzip
80.90 kB).

---

## Oportunidades validadas

### 1. `init_db()` redundante em toda chamada ao banco (performance)

**Módulo:** `backend/app/database.py`

**Problema encontrado:** `init_db()` — que abre uma conexão SQLite, executa
três `CREATE TABLE IF NOT EXISTS` e uma consulta `SELECT COUNT(*)` — já é
chamado uma única vez na inicialização da aplicação (`backend/app/main.py:71`,
evento `startup`). Apesar disso, as 8 funções de acesso a dados em
`database.py` (`create_analysis`, `list_history`, `get_online_profile_by_name`,
`get_online_profile_by_id`, `list_online_profiles`, `save_online_profile`,
`get_own_team_ref`, `set_own_team_ref`) chamavam `init_db()` novamente no
início de cada execução. Ou seja: **toda requisição HTTP que toca o banco
paga o custo de uma conexão extra + 3 DDLs + 1 query de contagem antes de
executar seu próprio trabalho.**

Confirmado que é seguro remover: `main.py` inicializa o banco no startup real
da aplicação, e `backend/tests/conftest.py` já chama `database_module.init_db()`
explicitamente em uma fixture `autouse` após apontar `DB_PATH` para um arquivo
temporário por teste — nenhum teste depende das chamadas redundantes dentro
das funções.

**PoC / mudança:** remoção das 8 chamadas redundantes de `init_db()`,
mantendo a chamada única no `startup` de `main.py` e a chamada explícita em
`conftest.py` (isolamento de testes).

```diff
 def create_analysis(payload: dict) -> dict:
-    init_db()
     selected_team = None
     ...
 def list_history() -> list[dict]:
-    init_db()
     with get_connection() as connection:
     ...
 def get_online_profile_by_name(team_name: str) -> dict | None:
-    init_db()
     normalized = normalize_team_name(team_name)
     ...
 def get_online_profile_by_id(profile_id: int) -> dict | None:
-    init_db()
     with get_connection() as connection:
     ...
 def list_online_profiles(query: str = "") -> list[dict]:
-    init_db()
     normalized = normalize_team_name(query)
     ...
 def save_online_profile(payload: dict) -> dict:
-    init_db()
     now = datetime.now(timezone.utc).isoformat()
     ...
 def get_own_team_ref() -> str | None:
-    init_db()
     with get_connection() as connection:
     ...
 def set_own_team_ref(ref: str) -> str:
-    init_db()
     now = datetime.now(timezone.utc).isoformat()
```

(diff completo reproduzível via `git diff backend/app/database.py` no commit
desta entrega)

**Medição (PoC, `timeit`, 2000 chamadas a `list_online_profiles("")`, banco
SQLite local em arquivo temporário):**

| Cenário | Tempo total | Tempo por chamada |
|---|---|---|
| Antes (com `init_db()` redundante) | 4.8328 s | 2.4164 ms |
| Depois (sem `init_db()` redundante) | 0.6290 s | 0.3145 ms |

**≈ 7.7x mais rápido por chamada** que toca o banco (economiza uma conexão
SQLite + 3 DDLs + 1 `COUNT(*)` por requisição). O ganho absoluto por
requisição é pequeno em termos humanos, mas é 100% desperdício estrutural que
se repete em endpoints de alto tráfego potencial: `GET /api/teams/options`,
`GET /api/teams/history`, `GET /api/teams/online-profiles`,
`GET/POST /api/teams/online-search`, `GET/PUT /api/teams/own-team`.

**Verificação:**
- `pytest`: 51 passed (igual ao baseline, 0 falhas)
- `python -m py_compile app/database.py`: OK
- Nenhuma mudança de comportamento observável (mesma saída, mesmos testes)

**Critério de aceite:** ✅ atendido — todos os comandos de verificação
passaram sem intervenção humana e a métrica alvo (tempo/complexidade)
melhorou de forma mensurável.

---

### 2. Cálculo duplicado de `_risk_lane` no grafo tático (complexidade)

**Módulo:** `backend/app/graph_analysis.py`

**Problema encontrado:** `build_tactical_graph` chamava
`_risk_lane(main_formation["risks"])` duas vezes — uma para preencher
`metrics.risk_lane` e outra, com o mesmo argumento, dentro da lista
`insights`. É trabalho redundante (ainda que barato) e uma fonte de
divergência futura caso alguém altere uma chamada e esqueça a outra.

**PoC / mudança:** calcular o valor uma vez em `risk_lane` e reutilizá-lo nos
dois lugares.

```diff
     main_formation = max(formations, key=lambda item: item["probability"])
     top_players = ordered_players[:3]
+    risk_lane = _risk_lane(main_formation["risks"])

     return {
         "formation": main_formation,
         "nodes": nodes,
         "edges": edges,
         "metrics": {
             "centrality_leader": top_players[0]["name"] if top_players else team["name"],
             "network_density": min(94, 54 + len(edges) * 5),
             "progression_lane": _progression_lane(team["style"]),
-            "risk_lane": _risk_lane(main_formation["risks"]),
+            "risk_lane": risk_lane,
         },
         "insights": [
             f"Rede prioritaria em {main_formation['formation']} com {main_formation['probability']}% de aderencia ao contexto informado.",
             f"Maior centralidade projetada: {top_players[0]['name']} ({top_players[0]['position']}).",
-            f"Zona critica observada: {_risk_lane(main_formation['risks'])}.",
+            f"Zona critica observada: {risk_lane}.",
         ],
     }
```

**Verificação:**
- `pytest`: 51 passed
- `python -m py_compile app/graph_analysis.py`: OK
- Saída idêntica (mesma string calculada, só uma vez)

**Critério de aceite:** ✅ atendido — mudança de baixo risco, elimina
duplicação de lógica, sem alteração de comportamento.

---

## Tentativas avaliadas e não implementadas (memória de melhoria)

### A. N+1 ao montar `GET /api/teams/options` (`backend/app/routes/teams.py`)

Ao montar a lista de times locais, o endpoint itera `teams()` e, para cada
time, chama `get_team_records(sources(), team["id"])`, que internamente
chama `get_team(team_id)` — reiterando a lista `teams()` já percorrida no
laço externo só para validar que o id existe (validação redundante, já que o
id veio da própria lista). Isso é um padrão O(N·(N+M)) em vez de O(N+M).

**Por que não foi implementado:** medi o tamanho real dos dados
(`backend/data/teams.json` = 10 times, `sources.json` = 30 registros) — o
custo real é irrelevante nessa escala (microssegundos) e uma refatoração
tocaria uma função central usada por várias rotas (`get_team_records`),
aumentando o risco de regressão para um ganho não mensurável hoje. Registrado
aqui como oportunidade condicional: revisitar se a base de dados local
crescer para centenas/milhares de times.

### B. Loop principal de visão computacional (`backend/app/video_vision.py`, `process_video`)

Arquivo mais extenso do backend (1424 linhas) e com o laço mais "quente" do
sistema (processamento frame a frame com OpenCV: subtração de fundo,
detecção de contornos, tracking por distância, classificação de uniforme).
Identifiquei candidatos a otimização (ex.: recriar
`cv2.getStructuringElement` a cada frame dentro do laço em vez de uma vez
fora dele), mas **não apliquei mudança**: qualquer alteração nesse módulo
exige validação visual/funcional do pipeline de vídeo (heatmap, trilhas,
grafo de proximidade, vídeo anotado), que este ambiente de desenvolvimento
não permite verificar além dos testes sintéticos existentes
(`tests/test_video_vision.py`). Risco de regressão silenciosa em qualidade de
detecção é maior que o ganho de performance esperado para uma mudança feita
sem observação visual do resultado. Recomendo tratar como item separado, com
vídeo de teste real e comparação visual antes/depois.

### C. Lint de frontend

Tentei rodar uma verificação de lint equivalente a `npm run lint`, mas o
projeto não tem ESLint configurado nem script `lint` no `package.json`.
Não foi instalada nenhuma ferramenta nova como dependência do projeto (fora
de escopo do contrato, que só permite alterar `package.json` para remover
dependência não utilizada). `pyflakes` (backend) não encontrou imports ou
variáveis mortas em `backend/app/`.

---

## Resumo

| # | Oportunidade | Tipo | Status | Resultado |
|---|---|---|---|---|
| 1 | `init_db()` redundante | Performance | ✅ Implementado | ~7.7x mais rápido por chamada ao banco; 51/51 testes OK |
| 2 | `_risk_lane` duplicado | Complexidade/duplicação | ✅ Implementado | Elimina cálculo redundante; 51/51 testes OK |
| A | N+1 em `team_options` | Performance | ⏸️ Não implementado | Impacto desprezível na escala atual (10 times) |
| B | Loop de `process_video` | Performance | ⏸️ Não implementado | Requer validação visual fora do escopo deste ambiente |
| C | Lint de frontend | Qualidade de código | ⏸️ Não aplicável | Sem ESLint configurado; fora de escopo adicionar dependência |

Testes finais: `pytest` 51 passed, 0 failed. `npm run build` (frontend)
concluído sem erros, bundle sem regressão de tamanho (nenhuma dependência
nova, nenhum código novo no frontend).
