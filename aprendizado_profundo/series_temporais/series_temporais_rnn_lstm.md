---

# 📘 Séries Temporais, RNN, LSTM e GRU — Guia Completo para Pós-Graduação

📎 Baseado na aula: 

---

# 🎯 1. Objetivo deste material

Este material foi desenvolvido para:

* Explicar **séries temporais do zero**
* Evoluir até **Redes Recorrentes (RNN)**
* Mostrar limitações e soluções (**LSTM e GRU**)
* Conectar com **aplicações reais**

---

# 🧠 2. O que é uma Série Temporal?

Uma **série temporal** é um conjunto de dados ordenados no tempo.

## 📌 Exemplo simples:

| Tempo | Temperatura |
| ----- | ----------- |
| 08:00 | 22°C        |
| 09:00 | 23°C        |
| 10:00 | 25°C        |

👉 A característica principal:

> O valor atual depende dos valores anteriores

---

## ⚠️ Diferença para dados comuns

| Tipo de dado   | Exemplo             | Importante           |
| -------------- | ------------------- | -------------------- |
| Dados comuns   | Altura, idade       | Independentes        |
| Série temporal | Temperatura, vendas | Dependentes no tempo |

---

# 🔍 3. Por que estudar séries temporais?

Porque elas permitem:

* 📈 Previsão (forecasting)
* ⚠️ Detecção de anomalias
* 🤖 Aplicações de IA

## 💼 Exemplos reais:

* Previsão de vendas
* Detecção de falhas em servidores
* Monitoramento de saúde
* Consumo de energia

---

# 🧩 4. Componentes de uma Série Temporal

Toda série pode ser decomposta em:

---

## 📈 4.1 Tendência (Trend)

Direção de longo prazo

* Crescente 📊
* Decrescente 📉
* Estável ➖

---

## 🔁 4.2 Sazonalidade (Seasonality)

Padrões que se repetem

Exemplos:

* Vendas no Natal 🎄
* Consumo de energia no verão ☀️

---

## 🔄 4.3 Ciclos (Cycles)

Oscilações de longo prazo sem padrão fixo

Exemplo:

* Crises econômicas

---

## 🎲 4.4 Ruído (Noise)

Parte aleatória dos dados

👉 Não contém informação útil previsível

---

# ⚙️ 5. Pré-processamento (ETAPA CRÍTICA)

Antes de modelar, precisamos preparar os dados.

## 🛠️ Principais técnicas:

* Tratamento de valores faltantes
* Normalização
* Remoção de tendência (detrending)
* Ajuste sazonal
* Suavização (média móvel)
* Separação treino/teste temporal

👉 **Erro comum:** misturar ordem temporal → invalida o modelo

---

# 🔗 6. Dependência Temporal

## 💡 Conceito-chave:

> O passado influencia o futuro

Exemplo:

> “O carro parou porque o sinal estava vermelho”

Se ignorarmos o passado, perdemos o contexto.

---

# ❌ 7. Por que modelos tradicionais falham?

Modelos como redes densas (MLP):

* Não têm memória
* Não entendem sequência

👉 Eles tratam cada ponto como independente

---

# 🔁 8. Redes Neurais Recorrentes (RNN)

As RNNs foram criadas para resolver isso.

## 🧠 Ideia central:

* Receber entrada atual
* Usar memória passada
* Atualizar memória

---

## 🧮 Equação fundamental

h_t = f(W x_t + U h_{t-1} + b)

---

## 📌 Interpretação:

* `xₜ` → entrada atual
* `hₜ₋₁` → memória passada
* `hₜ` → nova memória

👉 A rede aprende padrões ao longo do tempo

---

# ⚠️ 9. Problemas das RNNs

---

## ❌ 9.1 Gradiente Desaparecendo (Vanishing Gradient)

### O que acontece:

* Gradientes ficam muito pequenos
* A rede para de aprender

### Consequência:

👉 Esquece o passado distante

---

## ❌ 9.2 Gradiente Explodindo (Exploding Gradient)

### O que acontece:

* Gradientes crescem demais
* Treinamento instável

### Consequência:

👉 Modelo diverge

---

# 🧠 10. LSTM (Long Short-Term Memory)

A LSTM resolve esses problemas.

---

## 💡 Ideia principal:

> Controlar o que lembrar e o que esquecer

---

## 🧠 Analogia:

Como um caderno:

* Escreve o importante ✏️
* Apaga o irrelevante 🧽
* Usa apenas o necessário 📖

---

# 🔐 11. Estrutura da LSTM

Possui 3 "portões":

---

## 🚫 11.1 Forget Gate

Decide o que esquecer

---

## ✏️ 11.2 Input Gate

Decide o que aprender

---

## 📤 11.3 Output Gate

Decide o que usar na saída

---

## 🎯 Resultado:

* Mantém memória de longo prazo
* Evita perda de informação

---

# ⚡ 12. GRU (Gated Recurrent Unit)

Versão simplificada da LSTM

---

## ✅ Vantagens:

* Mais rápida
* Menos parâmetros
* Mais fácil de treinar

---

## ❗ Diferença:

* Menos controle de memória
* Mas desempenho similar

---

# 📊 13. Avaliação de Modelos

---

## 📏 MAE (Erro Absoluto Médio)

* Fácil de interpretar
* Média dos erros

---

## 📉 RMSE

* Penaliza erros grandes

---

## 📊 MAPE

* Erro percentual

---

## 🎯 R²

* Explicação do modelo

---

# 🧪 14. Alternativa prática (muito usada)

Nem sempre usamos RNN/LSTM.

---

## 💡 Estratégia:

Transformar série temporal em tabela

---

## 📌 Exemplo:

| t-3  | t-2  | t-1  | t    |
| ---- | ---- | ---- | ---- |
| 24.5 | 24.7 | 25.0 | 25.2 |

---

👉 Isso permite usar:

* Random Forest
* XGBoost
* Regressão

---

# 🚀 15. Aplicações reais

---

## 💼 Negócios

* Previsão de vendas
* Planejamento financeiro

---

## 🖥️ TI / DataOps

* Previsão de incidentes
* Monitoramento de sistemas

---

## ⚙️ Indústria

* Manutenção preditiva

---

## 🏥 Saúde

* Monitoramento de pacientes

---

# 🎯 16. Resumo Final

---

## 📌 Conceitos-chave:

* Série temporal = dados com dependência no tempo
* RNN = primeira abordagem com memória
* LSTM = solução robusta
* GRU = versão simplificada
* Pré-processamento = etapa crítica

---

## 🧠 Insight mais importante:

> O sucesso em séries temporais depende mais da preparação dos dados do que do modelo

---

# 🧭 17. Próximo passo recomendado

Para evoluir de verdade:

* Implementar em Python
* Comparar:

  * LSTM
  * XGBoost
* Criar dashboard

---

Só me diga: **vamos para a parte prática?**
