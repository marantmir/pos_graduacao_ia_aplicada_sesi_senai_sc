# Coach Intelligence

A camada `coach_intelligence` transforma dados técnicos em decisões auditáveis para a comissão.

## Princípio

Cada recomendação deve responder três perguntas:

1. **O que fazer?** — ação tática ou operacional.
2. **Por quê?** — evidência que sustenta a ação.
3. **Quão confiável é?** — qualidade e quantidade dos dados disponíveis.

## Entradas consolidadas

- perfil do time;
- dossiê tático;
- formações;
- elenco e métricas cadastradas;
- grafo tático;
- plano de jogo;
- pesquisa operacional;
- fontes públicas;
- referências de vídeo.

## Saída

A resposta contém:

- `executive_summary`;
- `match_model`;
- `tactical_priorities`;
- `performance`;
- `key_players`;
- `set_pieces`;
- `in_match_adjustment`;
- `training_focus`;
- `evidence`.

## Filosofia de segurança analítica

Uma fonte pública isolada não deve virar verdade tática. Informações recentes de vídeo, contexto da partida e disponibilidade do elenco devem prevalecer sobre hipóteses antigas. Quando faltam dados, o sistema deve declarar a lacuna e reduzir confiança em vez de preencher o vazio com uma inferência não verificável.
