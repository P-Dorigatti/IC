# Próximas etapas

Ja fiz algumas séries para o E3, tenho uma do panorama de 200 dias dos nós externos; zoom de 10 dias entre 01/04 até 11/04 sem lacunas; outro zoom de 10 dias entre 05/03 até 15/03 com uma lacuna grande entre o fim do dia 08 até o meio do dia 09; a comparação entre temp e umi do solo e do ar do TCC Messias, de Junho a Setembro; um que mostra o desvio espacial máximo instantaneo dos nós externos para o Cluster Head (entre 10/04 até 17/04), com esse desvio ficando entre 3ºC e 4ºC durante boa parte do período, com um pico no fim do dia 13/04 batendo 7ºC.

Agora estou querendo aplicar os algoritmos de agregação, para isso, ja fiz a curva RMSE x TR% num período de 15 dias num dos nós externos (86811), com o algoritmo 2 e 4 praticamente empatados como as melhores escolhas, sendo que o 2 é um algoritmo bem mais simples.

=== MELHOR CONFIGURAÇÃO ENCONTRADA VIA GRID SEARCH PARA ALG 4 (ε=0.5°C, Thb=60m) ===

Parâmetros Ótimos: alpha=0.4, beta=0.15, deadband=0.008°C/min, damping_phi=0.88

Desempenho Alg 4 Otimizado: Pacotes=843 | TR=80.16% | MAE=0.1734°C | RMSE=0.2292°C | ErroMax=0.500°C

Não sei se testo os diferentes algoritmos em diferentes períodos, se faço uso apenas do 2 e do 4 que se mostraram melhores, ou só do 2. Preciso aplicá-los nos diferentes coortes também e fazer a simulação do Cluster Head direto... fazer reconstrução, extrair métricas de QoS, etc.

**Estratégia de Execução: Funil Experimental em 3 Fases (E4 e E5)**

Para fechar os entregáveis sem retrabalho e com rigor estatístico, estruture suas simulações neste formato de funil:

1. **Fase 1: Benchmark Completo e Estabilidade Temporal (Coorte 1 — Nó `86811`)**
    - **Ação:** Mantenha os **4 algoritmos** na curva Pareto ($\text{RMSE} \times TR\%$) da janela de 15 dias que você já gerou.
    - **Teste de Generalização (Validação Cruzada Temporal):** Não faça novo *Grid Search* para outros períodos. Congele os hiperparâmetros ótimos encontrados nesses 15 dias ($\alpha=0.4, \beta=0.15, \text{deadband}=0.008, \phi=0.88$ para o Alg 4; $\delta=0.5^\circ\text{C}, T_{\text{hb}}=60\text{m}$ para o Alg 2) e rode-os diretamente sobre os **200 dias completos** do `86811` (ou separando um mês de outono/primavera vs. um mês de inverno). Isso prova que os parâmetros não sofreram *overfitting* na janela de 15 dias e fecha a comparação dos 4 métodos.
2. **Fase 2: Aplicação Direcionada nos Coortes Específicos (Apenas Alg 2 vs. Alg 4 + Baseline $W=15\text{m}$)**
    - **Coorte 2 (`Agricola_Solo` — `TCC MESSIAS`, `86817`):** Aplique o Alg 2 e o Alg 4 na **temperatura/umidade do ar** versus **temperatura/umidade do solo**. Aqui o Alg 4 tem grande chance de desempatar a seu favor no **solo**: como a inércia térmica edáfica filtra o ruído de alta frequência e gera rampas lentas e monotônicas ao longo de horas, o preditor linear EWMA deve cravar um $TR\%$ altíssimo com erro quase nulo, enquanto no ar o Alg 2 reina pela simplicidade.
    - **Coorte 3 (`Indoor_Baseline` — `Lab 1006`, `1` e `86782`):** Rode o Alg 2 para demonstrar o limite superior assintótico de compressão ($TR\% \to 91.6\%$ quando limitado apenas pelo $T_{\text{hb}}=60\text{ min}$) em regime climatizado estável.
    - **Coorte 4 (`Cluster_Server` — `86795` com pico real de $51.2^\circ\text{C}$) + Injeção Sintética no `86811`:** Use este cenário para extrair a **Latência de Alerta ($\Delta t_{\text{alerta}}$)** e o **Erro de Pico**. Mostre que o Algoritmo 1 (Janela Fixa de $30$ ou $60\text{ min}$) atrasa a detecção do surto térmico em até meia hora e amortece o pico pela média, enquanto os Algoritmos 2 e 4 disparam o pacote instantaneamente no exato passo de $5\text{ min}$ em que o limiar é rompido ($\Delta t_{\text{alerta}} = 0\text{ min}$ em relação à resolução do rastro).
3. **Fase 3: Simulação do Cluster Head e Acoplamento Temporal + Espacial (`koala_cluster_externo_wide_5min.csv`)**
    - Como você já observou no gráfico do **E3** que o desvio espacial máximo ($\Delta_{\max}$) entre os nós externos fica basalmente entre **$3^\circ\text{C}$ e $4^\circ\text{C}$** (devido ao microclima das condensadoras e insolação diferencial na parede) e bate **$7^\circ\text{C}$** no dia 13/04, usar um limiar espacial pequeno ($\tau_{\text{espacial}} = 1.0^\circ\text{C}$) faria o Cluster Head reportar falsas anomalias em 100% do tempo.
    - **Calibração de $\tau_{\text{espacial}}$:** Varra $\tau_{\text{espacial}} \in \{2.0^\circ\text{C}, 3.5^\circ\text{C}, 5.0^\circ\text{C}\}$ na janela de 10/04 a 17/04. Com $\tau_{\text{espacial}} = 4.0^\circ\text{C}$ ou $4.5^\circ\text{C}$, você demonstrará que o Cluster Head absorve a heterogeneidade normal do "talhão" enviando apenas **1 pacote com a mediana $M_t$** durante 90%+ do tempo, mas detecta cirurgicamente o evento extremo de $7^\circ\text{C}$ no dia 13/04 (enviando a mediana + ID do nó discrepante).
    - **Simulação Conjunta (Nó-Folha + CH):** Em vez de alimentar o Cluster Head com os dados brutos a cada 5 min, alimente a matriz do Cluster Head com as **séries já reconstruídas pelo Algoritmo 2** ($\delta=0.5^\circ\text{C}$) de cada um dos 8 nós ativos. Assim você mede a redução composta: economia no rádio local (nó $\to$ CH) + economia de $8\times$ para $1\times$ no enlace longo LoRaWAN (CH $\to$ Gateway), além de testar como o Cluster Head lida automaticamente com o *Node Death* do nó `86812` em 15/05/2026.

**Fechamento dos Gráficos do E3 e Extrapolação LoRaWAN (E5-Bloco B)**
Seus 5 gráficos do **E3** já superam com folga o mínimo exigido pelo plano (que pedia 3 figuras básicas) e contam uma história impecável: visão macro (200d) $\to$ operação nominal (10d sem gaps) $\to$ diagnóstico de falha de infraestrutura (gap de 08–09/03) $\to$ contraste agrometeorológico ar vs. solo (Messias) $\to$ motivação para agregação espacial (divergência no CH). Para fechar a tabela do **E5-Bloco B**, basta pegar o $N_{\text{tx/dia}}$ resultante do Alg 2, do Alg 4 e do Cluster Head e aplicar diretamente a equação analítica de Time-on-Air ($\text{ToA}$ para SF7, SF9 e SF12 com payload de 12 bytes) e probabilidade de entrega sem colisão no canal ALOHA ($\text{PDR}_{\text{MAC}} = e^{-2G}$) variando de $M=100$ a $M=1000$ nós na fazenda de café.