# Stack gratuita — Football Intelligence Platform

Esta variante foi preparada para iniciar sem custo de infraestrutura ou de LLM, respeitando os limites dos planos gratuitos.

## Arquitetura recomendada

```text
Navegador
  -> Render Free (Docker: React/Vite + FastAPI)
      -> Google Gemini Free Tier (padrao)
      -> OpenRouter Free (alternativa)
      -> Ollama local (alternativa sem API)
      -> regras deterministicas (fallback final)
      -> Wikipedia / busca web publica / YouTube publico / TheSportsDB
      -> OpenCV + NetworkX para visao e grafos
```

## IA sem custo

### 1. Google Gemini — padrao

- Provedor: `google_gemini`
- Modelo: `gemini-2.5-flash-lite`
- Variavel: `GEMINI_API_KEY`
- Indicado para o deploy gratuito por ter nivel sem custo financeiro sujeito a cotas do provedor.

### 2. OpenRouter Free — fallback hospedado

- Provedor: `openrouter_free`
- Modelo: `openrouter/free`
- Variavel: `OPENROUTER_API_KEY`
- O roteador escolhe entre modelos gratuitos disponiveis e pode variar ao longo do tempo.

### 3. Ollama — sem custo de API

- Provedor: `ollama_local`
- Nao exige chave.
- Padrao: `qwen3:4b-instruct`.
- Alternativas configuradas: `qwen3:4b`, `gemma3:4b`, `gemma3:1b`.

Exemplo:

```bash
ollama pull qwen3:4b-instruct
ollama serve
```

Depois configure:

```text
FOOTBALL_INTEL_LLM_PROVIDER=ollama_local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b-instruct
```

Ollama e ideal para uso local. O plano gratuito do Render nao possui memoria suficiente para hospedar esses modelos dentro do mesmo container.

## Fallback sem IA

Se nao houver chave, a cota acabar ou o provedor falhar, a plataforma continua funcionando com regras deterministicas. A IA enriquece a analise, mas nao e requisito para abrir dossies, consultar fontes, processar evidencias e produzir os insights basicos.

## Modo gratuito de video

Com `FOOTBALL_INTEL_FREE_MODE=1`:

- upload padrao limitado a 80 MB;
- ate 120 frames por analise por padrao;
- intervalo minimo de amostragem aumentado;
- timeout de processamento reduzido;
- o retorno informa quando o perfil economico foi aplicado.

Esses limites podem ser alterados por ambiente, por exemplo:

```text
FOOTBALL_INTEL_MAX_UPLOAD_MB=60
```

Para videos longos, a melhor estrategia e recortar os lances ou blocos de jogo que o treinador quer estudar.

## Fontes gratuitas usadas

- Wikipedia API para ficha basica e escudo quando disponivel;
- busca web publica best-effort via DuckDuckGo/Bing;
- pagina publica de resultados do YouTube para localizar videos, sem download automatico;
- TheSportsDB para dados publicos basicos;
- OpenCV para visao computacional;
- NetworkX para grafos e pesquisa operacional.

Fontes publicas podem alterar HTML, bloquear IPs de datacenter ou impor limites. O codigo trata essas integracoes como best-effort e mantem o fluxo mesmo quando uma delas falha.

## Deploy gratuito no Render

O `render.yaml` ja esta configurado para `plan: free` e modo economico.

1. Suba o repositorio para o GitHub.
2. No Render, crie um Blueprint a partir do repositorio.
3. Quando solicitado, informe `GEMINI_API_KEY` como segredo.
4. Aguarde o deploy e valide `/api/health`.
5. Abra `/future-ai` e use `Testar LLM`.

Se nao quiser criar uma chave Gemini, remova/ignore a chave: a aplicacao subira normalmente em fallback local.

## Persistencia no plano gratuito

O SQLite e os videos processados usam o filesystem da instancia. Em um servico gratuito do Render, o filesystem nao deve ser tratado como persistencia definitiva. Para um piloto isso e suficiente; para manter historico entre reinicios/deploys, a proxima evolucao recomendada e um banco externo gratuito, como Supabase Free, mantendo o backend FastAPI.

Os videos enviados sao temporarios durante o processamento. Evite usar o servidor gratuito como arquivo permanente de partidas.

## Estrategia de custo zero

1. Comecar com Render + Gemini Free Tier.
2. Manter `openrouter/free` como alternativa.
3. Para analises extensas de video, rodar localmente com Ollama e OpenCV.
4. Usar o servidor gratuito para dossie, fontes, insights e recortes curtos.
5. Adicionar banco externo somente quando a persistencia compartilhada se tornar necessaria.
