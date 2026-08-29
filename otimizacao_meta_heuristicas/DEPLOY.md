# Deploy gratuito — Football Intelligence Platform

O caminho recomendado para o piloto é um unico container no Render Free, usando o `Dockerfile` existente. O frontend React/Vite e compilado no build e servido pelo FastAPI.

## Configuracao pronta

O `render.yaml` inclui:

```text
plan=free
FOOTBALL_INTEL_FREE_MODE=1
FOOTBALL_INTEL_MAX_UPLOAD_MB=80
FOOTBALL_INTEL_LLM_ENABLED=1
FOOTBALL_INTEL_LLM_PROVIDER=google_gemini
GEMINI_MODEL=gemini-2.5-flash-lite
```

A unica credencial recomendada para iniciar e:

```text
GEMINI_API_KEY=<segredo>
```

A chave nao deve ser colocada no Git.

## Passos

1. Publique este projeto em um repositorio GitHub.
2. No Render, crie um novo `Blueprint` apontando para o repositorio.
3. O Render le o `render.yaml` e cria o servico Docker gratuito.
4. Informe `GEMINI_API_KEY` quando o Blueprint solicitar o segredo.
5. Finalize o deploy.
6. Valide `GET /api/health`.
7. Abra `/future-ai` e clique em `Testar LLM`.

## Sem chave de IA

A aplicacao nao depende da LLM para iniciar. Se `GEMINI_API_KEY` estiver vazia, ela usa as regras deterministicas existentes e continua oferecendo busca publica, dossie, grafos, pesquisa operacional e insights baseados nos dados disponiveis.

## Trocar para OpenRouter Free

No ambiente do Render:

```text
FOOTBALL_INTEL_LLM_PROVIDER=openrouter_free
OPENROUTER_API_KEY=<segredo>
OPENROUTER_MODEL=openrouter/free
```

O roteador gratuito escolhe um modelo gratuito disponivel. A disponibilidade e os limites pertencem ao provedor e podem mudar.

## Usar Ollama local

Ollama e a opcao sem custo de API para rodar no computador do analista/treinador:

```bash
ollama pull qwen3:4b-instruct
ollama serve
```

Variaveis:

```text
FOOTBALL_INTEL_LLM_PROVIDER=ollama_local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b-instruct
```

Nao e recomendado executar um modelo Ollama no mesmo container do Render Free por limite de memoria/CPU.

## Video no plano gratuito

O modo gratuito reduz automaticamente a carga:

- upload padrao: 80 MB;
- 120 frames por analise por padrao;
- amostragem mais espaçada;
- timeout de visao computacional reduzido.

Para partidas inteiras, recorte o trecho relevante antes de enviar. O objetivo do deploy gratuito e apoiar scouting e preparacao de jogo, nao servir como cluster de processamento de video.

## Persistencia

O projeto ainda usa SQLite e arquivos locais. Em hospedagem gratuita, trate esse armazenamento como temporario. Para manter historico entre reinicios/deploys, migre a persistencia para um banco externo gratuito. A opcao sugerida para a proxima fase e Supabase Free.

## Rodar local sem custo

Backend:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Com Ollama, nenhuma chave externa e necessaria.

Mais detalhes: `docs/FREE_STACK.md`.
