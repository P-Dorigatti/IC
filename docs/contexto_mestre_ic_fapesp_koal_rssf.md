# contexto_mestre_e_prompt_de_handoff_ic_fapesp_koala_rssf

# Documento de Contexto Mestre (Handoff para IA) — Projeto de IC FAPESP

---

## 1. Papel e Diretrizes para a IA Assistente

Você está atuando como co-orientador técnico e especialista em **Engenharia de Computação, Redes de Sensores Sem Fio (RSSF / WSN), IoT (LoRa/LoRaWAN, MQTT, CoAP) e Ciência de Dados aplicada a Séries Temporais**.

- **Pesquisador:** Pedro Dorigatti Aureo Ferreira (Engenharia de Computação — ICMC/USP São Carlos).
- **Orientador:** Prof. Dr. Julio Cezar Estrella (LaSDPC — Laboratório de Sistemas Distribuídos e Programação Concorrente, ICMC/USP).
- **Projeto FAPESP:** *Rede de Sensores Sem Fio na Agricultura de Precisão: Desenvolvimento de Dispositivos IoT para Coleta de Dados em Lavouras Cafeeiras do Brasil*.
- **Prazo Final Crítico de Resultados:** **17/12/2026** (Relatório FAPESP até **15/01/2027**).

---

## 2. Histórico do Projeto e o Pivô Metodológico (Contexto Crucial)

### 2.1. Proposta Inicial e Artigo do 34º SIICUSP

Originalmente, o projeto previa a construção física e validação em campo de nós sensores sem fio para lavouras de café. Na primeira fase (publicada no 34º SIICUSP sob o título *“Analysis and Selection of Communication Technologies for Sensor Networks in Precision Agriculture”*), concluiu-se que:

1. **Tecnologia Ideal de Longo Alcance:** **LoRa / LoRaWAN** (modulação CSS resiliente a folhagens densas, alcance de quilômetros no meio rural e topologia *star-of-stars*).
2. **Gargalo Identificado:** O consumo de energia e as colisões de pacotes no gateway LoRaWAN aumentam drasticamente conforme a frequência de transmissão cresce (*Time-on-Air* elevado).
3. **Estratégia Inicial Proposta:** Um algoritmo de **duty-cycle híbrido orientado a eventos** (envio por limiar de variação $\delta$ + *heartbeat* máximo $T_{\text{hb}}$ para manter a observabilidade da rede).

### 2.2. Mudança Estratégica (Uso do Testbed Koala — *Trace-Driven Simulation*)

Devido a restrições de cronograma, o orientador definiu que **o tema da IC permanece sendo RSSF para Agricultura de Precisão (Cafeicultura)**, mas a validação experimental será feita por **Simulação Orientada a Rastro (*Trace-Driven Simulation*)** utilizando a plataforma **Koala** como **testbed experimental controlado do LaSDPC**.

- **O que é o Koala:** Uma infraestrutura IoT real em operação no laboratório (originalmente voltada a *smart buildings*), composta por múltiplos nós sensores (temperatura, umidade, etc.), protocolos M2M (MQTT/CoAP/ESP-NOW), backend, API e banco de dados de séries temporais.
- **Regra de Ouro para Relatórios e Textos:** O Koala **nunca** deve ser descrito como uma mudança de tema para prédios inteligentes. Ele deve ser enquadrado como **infraestrutura experimental controlada** usada para reduzir risco, garantir reprodutibilidade científica e fornecer séries temporais reais com ruído, *jitter* e falhas de rede reais, a partir das quais os algoritmos de agregação e economia de energia são validados e extrapolados matematicamente para o cenário de lavouras cafeeiras (LoRaWAN).

---

## 3. Arquitetura Experimental e Algoritmos Selecionados para Validação

A validação é 100% baseada nos dados históricos já coletados no banco do Koala (e na injeção controlada de anomalias/eventos climáticos sobre esses rastros reais).

### 3.1. Formato Padronizado do Dataset Mestre (Entregável E2)

A recomendação dada pelo orientador é converter os dados brutos do Koala para um formato tabular (`CSV` ou `JSON`) padronizado contendo, mas dependendo da estrutura isso pode ser mudado:

- `timestamp` (ISO 8601 / datetime ordenado cronologicamente)
- `id_dispositivo` (identificador único do nó sensor)
- `ambiente` (sala/localização física para agrupamento espacial)
- `sensor` (grandeza medida: ex. `temperatura`, `umidade`)
- `valor` (float filtrado de *outliers* absurdos de hardware)
- `unidade` (ex.: `C`, `%`)

### 3.2. Algoritmos de Agregação e Supressão Temporal (Nível Nó Sensor — E4)

O objetivo é comparar 4 abordagens aplicadas sobre a série bruta $y_t$:

1. **Algoritmo 1 — Agregação por Janela Temporal Fixa (*Baseline*):**
    - Amostra localmente e envia $1$ pacote a cada janela fixa $W \in \{5, 15, 30, 60\}\text{ min}$ contendo `[média, min, max, std]`.
2. **Algoritmo 2 — *Duty-Cycle* Híbrido por Limiar Estático (Proposta SIICUSP):**
    - Mantém o último valor enviado ($y_{\text{last}}$) e o instante do último envio ($t_{\text{last}}$).
    - Transmite se e somente se:
        
        $$
        |y_t - y_{\text{last}}| \ge \delta \quad \text{OU} \quad (t - t_{\text{last}}) \ge T_{\text{hb}}
        $$
        
    - Parâmetros: $\delta \in \{0.2^\circ\text{C}, 0.5^\circ\text{C}, 1.0^\circ\text{C}\}$ (Temperatura), $\delta \in \{1\%, 2\%, 5\%\}$ (Umidade) e $T_{\text{hb}} \in \{30, 60\}\text{ min}$.
3. **Algoritmo 3 — Janela Adaptativa Baseada em Variância (*Adaptive Windowing*):**
    - Calcula o desvio padrão móvel ($\sigma_k$) das últimas $k$ leituras.
    - Ajusta dinamicamente o tamanho da janela de envio $W_{\text{atual}} \in [W_{\min}, W_{\max}]$ de forma inversamente proporcional a $\sigma_k$: em períodos estáveis (madrugada, $\sigma_k \le \sigma_{\text{baixo}}$), estica a janela para $W_{\max} = 60\text{ min}$; em mudanças rápidas ($\sigma_k \ge \sigma_{\text{alto}}$), contrai para $W_{\min} = 2\text{ min}$.
4. **Algoritmo 4 — Predição Dupla Linear / EWMA (*Dual Prediction Scheme*):**
    - Tanto o nó sensor quanto o servidor rodam o mesmo preditor linear:
        
        $$
        \hat{y}_t = y_{\text{last}} + \hat{m} \cdot (t - t_{\text{last}})
        $$
        
    - Enquanto o erro de predição $|y_t - \hat{y}_t| < \epsilon$, o nó não transmite nada (mesmo que a temperatura esteja subindo ou descendo em rampa constante). Quando $|y_t - \hat{y}_t| \ge \epsilon$ (ou estoura $T_{\text{hb}}$), transmite $(y_t, \hat{m}_{\text{novo}})$, onde a inclinação $\hat{m}_{\text{novo}}$ é atualizada via EWMA.

### 3.3. Simulação de *Cluster Head* (Agregação Espacial Multi-Sensor)

- Agrupa $3$ a $4$ sensores do mesmo `ambiente` do Koala como um “talhão virtual de café”.
- Os nós-folha reportam para o *Cluster Head* (simulando enlace local curto).
- O *Cluster Head* calcula a mediana $M$ do grupo e o desvio máximo $\Delta_{\max} = \max_i |v_i - M|$.
    - Se $\Delta_{\max} \le \tau_{\text{espacial}}$: transmite apenas $1$ pacote de longo alcance (LoRaWAN) com a mediana do talhão.
    - Se $\Delta_{\max} > \tau_{\text{espacial}}$: transmite a mediana + identificação e leitura do sensor discrepante (detecção de anomalia local ou falha de sensor).

### 3.4. Teste de Resposta a Eventos Climáticos Extremos

Como o ambiente interno de laboratório é termicamente estável, os algoritmos devem ser testados em dois regimes:

1. **Rastro Original (Regime Estável + Transientes de Ar-Condicionado/Ocupação):** Avalia a compressão máxima.
2. **Rastro com Injeção de Evento Climático Sintético (*Trace + Synthetic Event Injection*):** Soma-se matematicamente uma rampa abrupta (ex.: queda de $-6^\circ\text{C}$ em $20\text{ min}$ simulando frente fria/geada no café, ou salto de $+25\%$ de umidade simulando chuva/irrigação) sobre o rastro real para medir a **Latência de Alerta** e o **Erro de Pico**.

---

## 4. Métricas de Validação e QoS (Entregável E5 e Extrapolação E6)

Sempre que gerarmos tabelas de resultados, devemos calcular dois blocos de métricas:

### Bloco A — QoS Empírico da Infraestrutura (Dados Brutos do Koala)

1. **Completude / PDR Empírico (%):** $\frac{N_{\text{recebido\_único}}}{N_{\text{esperado}}} \times 100$, baseado na periodicidade nominal $T_{\text{nominal}}$.
2. **Estabilidade Temporal (*Jitter*):** Média e desvio padrão dos intervalos entre chegadas ($\sigma_{\Delta t}$) excluindo quedas severas.
3. **Análise de Lacunas (*Gaps / Downtime*):** Contagem de eventos onde $\Delta t > 3 \times T_{\text{nominal}}$, duração média (MTTR) e maior período sem dados.

### Bloco B — Desempenho dos Algoritmos e QoS Projetado para LoRaWAN Agrícola

1. **Taxa de Redução de Transmissões ($TR\%$):**
    
    $$
    TR(\%) = \left(1 - \frac{N_{\text{tx}}}{N_{\text{bruto}}}\right) \times 100
    $$
    
2. **Fidelidade de Reconstrução no Servidor ($\text{MAE}$ e $\text{RMSE}$):**
Comparação ponto a ponto entre a série original $y_t$ e a série reconstruída no servidor $\hat{y}_t^{\text{serv}}$ (via *Zero-Order Hold / Forward Fill* para limiares ou extrapolação linear para Predição Dupla).
3. **Latência de Alerta ($\Delta t_{\text{alerta}}$ / *Age of Information*):** Tempo decorrido entre o instante em que a grandeza física cruza um limiar crítico de emergência climática e o instante em que o algoritmo efetivamente dispara o pacote.
4. **Redução de *Time-on-Air* ($\text{ToA}_{\text{total}}$) e Consumo Energético:**
(Considerando *Spreading Factors* típicos do campo, ex.: SF7 a SF12).
    
    $$
    \text{ToA}_{\text{dia}} = N_{\text{tx/dia}} \times \text{ToA}_{\text{pacote\_LoRa}}
    $$
    
5. **PDR Projetado em Escala na Camada MAC ($\text{PDR}_{\text{MAC}}$):**
Usando o modelo de colisão ALOHA para LoRaWAN com $M$ nós em uma fazenda (ex.: $M \in [100, 1000]$):
    
    $$
    \text{PDR}_{\text{MAC}} = e^{-2G}, \quad \text{onde } G = M \times \lambda_{\text{tx/s}} \times \text{ToA}_{\text{pacote}}
    $$
    

---

## 5. Lista Oficial de Entregáveis e Cronograma (Referência Rápida)

- **E1 — Acesso aos dados:** Script/procedimento de extração do Koala + `README.md` curto.
- **E2 — Dataset organizado:** Arquivo `CSV`/`JSON` padronizado + dicionário de campos.
- **E3 — Gráficos básicos:** Mínimo de 3 gráficos exploratórios (séries temporais, média móvel e identificação visual de lacunas/ausências).
- **E4 — Regras de agregação:** Scripts e gráficos comparando dado bruto vs. dado agregado/reduzido (Janela Fixa, Limiar Híbrido, Janela Adaptativa, Predição Dupla e Cluster Head).
- **E5 — Métricas de QoS/dados:** Tabela consolidada de métricas (empíricas + projetadas) com interpretação técnica.
- **E6 — Discussão agrícola:** Texto técnico (2 a 4 páginas) conectando os resultados experimentais ao cenário de lavouras cafeeiras e LoRaWAN.
- **E7 — Pacote final (Até 17/12/2026):** Pasta única organizada com scripts, dados, figuras, tabelas, `README` e texto do relatório.

---