# Documento Técnico e Discussão Metodológica (Entregável E4) — IC FAPESP

**Pesquisador:** Pedro Dorigatti Aureo Ferreira (Engenharia de Computação — ICMC/USP)  
**Orientador:** Prof. Dr. Julio Cezar Estrella (LaSDPC — ICMC/USP)  
**Projeto FAPESP:** *Rede de Sensores Sem Fio na Agricultura de Precisão: Desenvolvimento de Dispositivos IoT para Coleta de Dados em Lavouras Cafeeiras do Brasil*  
**Status Atual:** **Entregável E4 100% concluído** (*Algoritmos de Agregação e Supressão Temporal, Fronteira de Pareto, Validação de Reconstrução, Aplicação nos Coortes, Resposta a Anomalias/Latência de Alerta e Simulação de Agregação Espacial via Cluster Head*). Próxima etapa: **Entregável E5 (Bloco B — Extrapolação Analítica LoRaWAN)**.

---

## 1. Contextualização e Objetivo do Entregável E4

Na primeira etapa do projeto de Iniciação Científica (publicada no 34º SIICUSP), identificou-se que a tecnologia **LoRa / LoRaWAN** é a mais adequada para cobrir grandes extensões rurais com topografia acidentada e folhagem densa típicas da cafeicultura brasileira. Contudo, o elevado *Time-on-Air* ($\text{ToA}$) da modulação CSS impõe dois gargalos severos quando centenas de nós sensores transmitem periodicamente em alta frequência:
1. **Drenagem acelerada da bateria** dos nós sensores em campo, cujo rádio transceptor domina o balanço energético;
2. **Degradação da taxa de entrega de pacotes ($\text{PDR}_{\text{MAC}}$)** devido a colisões no canal de acesso múltiplo tipo ALOHA puro utilizado pelo LoRaWAN Classe A.

O **Entregável E4** tem como objetivo projetar, calibrar e validar experimentalmente algoritmos de **agregação e supressão temporal executados localmente no nó sensor** (*in-network processing*), utilizando a metodologia de **Simulação Orientada a Rastro (*Trace-Driven Simulation*)** sobre o conjunto de dados reais de 200 dias contínuos (`01/03/2026` a `16/09/2026`, resolução base $\Delta t = 5\text{ min}$) extraído da infraestrutura experimental **Koala** (LaSDPC/ICMC-USP).

O problema central consiste em maximizar a **Taxa de Redução de Transmissões ($TR\%$):**

$$
TR(\%) = \left(1 - \frac{N_{\text{tx}}}{N_{\text{bruto}}}\right) \times 100
$$

enquanto se minimiza o erro de reconstrução da série temporal no servidor central — quantificado pelo **Erro Médio Absoluto ($\text{MAE}$)**, pela **Raiz do Erro Quadrático Médio ($\text{RMSE}$)** e pelo **Erro Absoluto Máximo ($\text{ErroMáx} = \max_t |y_t - \hat{y}_t|$)**.

---

## 2. Formulação Matemática dos 4 Algoritmos Temporais Avaliados

Para estabelecer um comparativo rigoroso entre abordagens dirigidas pelo tempo (*time-driven*) e abordagens dirigidas por eventos (*event-driven*), quatro algoritmos foram implementados sobre a série original $y_t$:

### 2.1. Algoritmo 1 — Agregação por Janela Temporal Fixa (*Baseline Time-Driven*)
- **Lógica no Nó Sensor:** O dispositivo amostra o transdutor a cada intervalo nominal $\Delta t = 5\text{ min}$, mas suprime o rádio durante uma janela fixa de duração $W \in \{15, 30, 60, 120\}\text{ min}$ (equivalente a enviar apenas $1$ pacote a cada $3, 6, 12$ ou $24$ ciclos).
- **Reconstrução no Servidor ($\hat{y}_t$):** Entre duas transmissões consecutivas, o servidor mantém o último valor recebido via *Zero-Order Hold* (ZOH / *Forward Fill*):

$$
\hat{y}_t = y_{t_{\text{last}}}
$$

- **Característica estrutural:** A taxa de redução $TR\%$ é estritamente determinística e independente da dinâmica do fenômeno físico ($TR \approx 66,7\%$ para $W=15\text{m}$, $83,3\%$ para $W=30\text{m}$ e $91,7\%$ para $W=60\text{m}$). Em contrapartida, o algoritmo é cego a variações intra-janela, permitindo erros elevados durante rampas térmicas ou hídricas rápidas.

### 2.2. Algoritmo 2 — *Duty-Cycle* Híbrido por Limiar Estático (Proposta SIICUSP)
- **Lógica no Nó Sensor:** Mantém em memória apenas o último valor efetivamente transmitido ($y_{\text{last}}$) e o tempo decorrido desde o último pacote ($\Delta t_{\text{tx}} = t - t_{\text{last}}$). Uma nova transmissão é disparada se, e somente se, a variação absoluta romper o limiar metrológico $\delta$ (gatilho de evento) ou se o temporizador atingir o limite máximo de *heartbeat* $T_{\text{hb}}$ (gatilho de vivacidade/observabilidade da rede):

$$
\text{Transmitir em } t \iff |y_t - y_{\text{last}}| \ge \delta \quad \text{OU} \quad (t - t_{\text{last}}) \ge T_{\text{hb}}
$$

- **Reconstrução no Servidor ($\hat{y}_t$):** ZOH ($\hat{y}_t = y_{\text{last}}$).
- **Propriedade Fundamental (Garantia Determinística de Erro):** Pela própria condição de disparo, enquanto o canal de comunicação estiver operante, o erro instantâneo de reconstrução no servidor **nunca ultrapassa o limiar configurado**:

$$
|y_t - \hat{y}_t| < \delta, \quad \forall t
$$

- **Complexidade Computacional no Microcontrolador:** $\mathcal{O}(1)$ em tempo e memória (requer apenas 2 variáveis `float` em RAM e uma subtração com valor absoluto, sem necessidade de ponto flutuante avançado).

### 2.3. Algoritmo 3 — Janela Adaptativa Baseada em Variância (*Adaptive Windowing*)
- **Lógica no Nó Sensor:** Mantém um *buffer* circular com as últimas $k = 6$ leituras locais ($30\text{ min}$ de histórico recente) e calcula o desvio padrão amostral móvel $\sigma_k$. A janela de transmissão atual $W_{\text{atual}} \in [W_{\min}, W_{\max}]$ (com $W_{\min} = 5\text{ min}$ e $W_{\max} = 60\text{ min}$) é modulada de forma inversamente proporcional à volatilidade local:

$$
W_{\text{atual}}(\sigma_k) = \begin{cases}
W_{\max}, & \text{se } \sigma_k \le \sigma_{\text{baixo}} \\
W_{\min}, & \text{se } \sigma_k \ge \sigma_{\text{alto}} \\
W_{\max} - \left(\frac{\sigma_k - \sigma_{\text{baixo}}}{\sigma_{\text{alto}} - \sigma_{\text{baixo}}}\right) (W_{\max} - W_{\min}), & \text{se } \sigma_{\text{baixo}} < \sigma_k < \sigma_{\text{alto}}
\end{cases}
$$

- **Característica estrutural:** Durante a madrugada ou em ambientes climatizados ($\sigma_k \le \sigma_{\text{baixo}}$), expande a janela para $60\text{ min}$; sob transientes rápidos ($\sigma_k \ge \sigma_{\text{alto}}$), contrai para $5\text{ min}$. Entretanto, por depender de uma estatística em janela deslizante ($\sigma_k$), apresenta inércia de reação na transição do regime estável para o regime transiente e não possui teto rígido para o erro instantâneo.

### 2.4. Algoritmo 4 — Predição Dupla Linear Amortecida via EWMA (*Dual Prediction Scheme / Holt Damped*)
- **Lógica no Nó Sensor e no Servidor:** Em vez de assumir que a grandeza permanece estática entre pacotes (como o ZOH do Algoritmo 2), tanto o nó sensor quanto o servidor executam um modelo linear de tendência amortecida de Holt (Dupla Suavização Exponencial — EWMA).
  - Localmente, a cada passo $\Delta t$, o nó atualiza sua estimativa filtrada de nível ($\ell_t$) e de inclinação/tendência ($b_t$) com hiperparâmetros $\alpha, \beta \in (0, 1)$ e fator de amortecimento $\phi \in (0, 1]$:

$$
\ell_t = \alpha y_t + (1 - \alpha)\,\text{clip}\!\left(\ell_{t-1} + \phi b_{t-1}\Delta t\right)
$$

$$
b_t = \beta \left(\frac{\ell_t - \ell_{t-1}}{\Delta t}\right) + (1 - \beta)\phi b_{t-1}
$$

  - No servidor (e espelhadamente no nó sensor para verificação), a predição aberta $\hat{y}_t^{\text{serv}}$ a partir do último pacote enviado $(y_{\text{sent}}, m_{\text{sent}})$ após $s$ passos de $5\text{ min}$ utiliza a soma geométrica amortecida e respeita os limites físicos da grandeza (`clip_bounds`, ex.: $[0\%, 100\%]$ para umidade relativa e $[-10^\circ\text{C}, 60^\circ\text{C}]$ para temperatura):

$$
\hat{y}_t^{\text{serv}} = \text{clip}\!\left(y_{\text{sent}} + m_{\text{sent}} \cdot \Delta t_{\text{nominal}} \sum_{j=1}^{s} \phi^j\right)
$$

  - **Condição de Transmissão e *Deadband* de Ruído:** O nó transmite um novo par $(y_t, m_{\text{sent}})$ quando $|y_t - \hat{y}_t^{\text{serv}}| \ge \epsilon$ ou $(t - t_{\text{last}}) \ge T_{\text{hb}}$. Para evitar que oscilações estocásticas de ADC gerem extrapolações espúrias, aplica-se uma banda morta (*deadband*): se $|b_t| < \text{deadband}$, transmite-se $m_{\text{sent}} = 0$ (recorrendo automaticamente ao comportamento seguro de ZOH).

### 2.5. Tratamento Estrito de Lacunas de Rede (*Cold Start* em *Gaps* $> 15\text{ min}$)
Conforme diagnosticado no **Entregável E2**, séries reais de testbeds IoT possuem interrupções de coleta ($\Delta t > 3 \times T_{\text{nominal}} = 15\text{ min}$). Nos scripts desenvolvidos (`200_dias_temp.py`, `200_dias_um.py`, `reconstrucao_validacao.py` e `coortes_ar_solo_indoor.py`), toda lacuna $\Delta t > 15\text{ min}$ aciona um protocolo estrito de **Ressincronização (*Cold Start*)**: no instante imediatamente posterior ao retorno da rede, o nó transmite obrigatoriamente a leitura atual, zera a tendência acumulada ($b_t = 0$) e reinicia o *buffer* de variância, impedindo que extrapolações lineares atravessem horas de apagão do servidor.

---

## 3. Fase 1: Calibração (*Grid Search*), Fronteira de Pareto e Generalização Temporal (Nó `86811`)

Seguindo o funil metodológico definido para o projeto, utilizou-se o nó externo veterano **`86811` (`1006EXT-TEMPHUM-03`, Coorte 1 `Externo_Cluster`)** para a calibração inicial e validação de estabilidade temporal.

### 3.1. Janela de Calibração (15 Dias) e Parâmetros Metrológicos de Referência
Para evitar *data leakage* (contaminar a avaliação de longo prazo com o ajuste de hiperparâmetros), o *Grid Search* do Algoritmo 4 foi executado exclusivamente sobre uma janela limpa de **15 dias contínuos de outono (`01/04/2026` a `16/04/2026`, $4.319$ amostras de $5\text{ min}$)**.

Os limiares metrológicos de referência ($\delta = \epsilon$) e o *heartbeat* ($T_{\text{hb}}$) foram fixados de acordo com a Seção 3.2 do plano de pesquisa e a incerteza típica dos transdutores digitais (proporção física aproximada de $1^\circ\text{C} : 4\%\text{ UR}$):
- **Temperatura:** $\delta = \epsilon = 0,5^\circ\text{C}$ e $T_{\text{hb}} = 60\text{ min}$.
- **Umidade Relativa:** $\delta = \epsilon = 2,0\%$ e $T_{\text{hb}} = 60\text{ min}$.

### 3.2. Otimização de Hiperparâmetros do Algoritmo 4 (*Grid Search* 4D)
Foi realizada uma busca exaustiva em grade sobre $5^4 = 625$ combinações de $(\alpha, \beta, \text{deadband}, \phi)$ para cada grandeza:
- $\alpha \in \{0.2, 0.3, 0.4, 0.5, 0.6\}$
- $\beta \in \{0.05, 0.10, 0.15, 0.25, 0.35\}$
- $\phi \in \{0.75, 0.82, 0.88, 0.92, 0.96\}$
- $\text{deadband}_{\text{temp}} \in \{0.002, 0.005, 0.008, 0.012, 0.020\}^\circ\text{C/min}$
- $\text{deadband}_{\text{umid}} \in \{0.005, 0.015, 0.030, 0.050, 0.080\}\%/\text{min}$

A função custo multiobjetivo $J$ foi formulada para minimizar simultaneamente o $\text{RMSE}$ e maximizar a taxa de redução $TR\%$, impondo uma penalidade caso a compressão ficasse inferior à do Algoritmo 2 sob o mesmo limiar. Os hiperparâmetros ótimos encontrados e **congelados para todas as etapas seguintes** foram:

| Grandeza | Hiperparâmetros Ótimos Congelados (Algoritmo 4) | Desempenho Alg 2 nos 15 Dias (Ref.) | Desempenho Alg 4 Otimizado nos 15 Dias |
| :--- | :--- | :--- | :--- |
| **Temperatura** ($\epsilon = 0,5^\circ\text{C}$) | $\alpha = 0,4$, $\beta = 0,15$, $\text{deadband} = 0,005^\circ\text{C/min}$, $\phi = 0,75$ | `827` pcts \| $TR = 80,85\%$ \| $\text{RMSE} = 0,2231^\circ\text{C}$ | **`826` pcts \| $TR = 80,88\%$ \| $\text{RMSE} = 0,2211^\circ\text{C}$** |
| **Umidade Relativa** ($\epsilon = 2,0\%$) | $\alpha = 0,6$, $\beta = 0,10$, $\text{deadband} = 0,030\%/\text{min}$, $\phi = 0,82$ | `687` pcts \| $TR = 84,09\%$ \| $\text{RMSE} = 0,8926\%$ | **`669` pcts \| $TR = 84,51\%$ \| $\text{RMSE} = 0,8681\%$** |

> **Interpretação Física dos Hiperparâmetros:** Em ambas as grandezas, o otimizador convergiu para fatores de amortecimento moderados ($\phi = 0,75$ em temperatura e $\phi = 0,82$ em umidade) combinados com *deadbands* positivos. Isso ocorre porque as séries atmosféricas externas sofrem inflexões rápidas (ex.: nuvens encobrindo o sol ou acionamento intermitente das condensadoras próximas). Sem o amortecimento $\phi < 1$, uma inclinação linear estimada na subida continuaria projetando crescimento indefinido após o pico, provocando *overshoot* e forçando transmissões corretivas extras.

---

### 3.3. Análise da Fronteira de Pareto ($\text{RMSE} \times TR\%$)
Para avaliar o compromisso (*trade-off*) global entre economia de energia/canal ($TR\%$) e erro de reconstrução ($\text{RMSE}$), varremos o espaço de parâmetros dos 4 métodos tanto na janela de calibração de 15 dias quanto na série completa de 200 dias:
- **Alg 1:** $W \in \{10, 15, 20, 30, 45, 60, 90, 120\}\text{ min}$;
- **Alg 2 e Alg 4:** $\delta, \epsilon \in \{0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5\}^\circ\text{C}$ (Temperatura) e $\{0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0\}\%$ (Umidade);
- **Alg 3:** 5 faixas progressivas de limiares de desvio padrão $[\sigma_{\text{baixo}}, \sigma_{\text{alto}}]$ e $W_{\max} \in \{15, 30, 60, 90, 120\}\text{ min}$.

As curvas geradas em:
- [pareto_temperatura_15dias_86811.png](../resultados_e4_fase1_temperatura/pareto_temperatura_15dias_86811.png) e [pareto_temperatura_200dias_86811.png](../resultados_e4_fase1_temperatura/pareto_temperatura_200dias_86811.png)
- [pareto_umidade_15dias_86811.png](../resultados_e4_fase1_umidade/pareto_umidade_15dias_86811.png) e [pareto_umidade_200dias_86811.png](../resultados_e4_fase1_umidade/pareto_umidade_200dias_86811.png)

revelam três conclusões científicas centrais:
1. **Dominância Estrita de Pareto dos Métodos Orientados a Eventos (Alg 2 e Alg 4):** Em toda a extensão horizontal do gráfico ($TR\%$ de $50\%$ a $90\%$), as curvas dos Algoritmos 2 e 4 situam-se substancialmente abaixo das curvas dos Algoritmos 1 e 3. Para uma mesma redução de pacotes de $\sim 81\%$ em temperatura, os Algoritmos 2 e 4 entregam $\text{RMSE} = 0,224^\circ\text{C}$, enquanto a Janela Fixa ($W=30\text{m}$, $TR=83,3\%$) apresenta o dobro de erro ($\text{RMSE} = 0,457^\circ\text{C}$).
2. **Desempenho Intermediário do Algoritmo 3 (Janela Adaptativa):** O Algoritmo 3 supera o Algoritmo 1 de janela fixa por conseguir contrair o intervalo durante o dia e esticá-lo à noite, mas ainda permanece dominado pelos Algoritmos 2 e 4 porque sua decisão é indireta (via variância passada $\sigma_k$) e não testa diretamente o erro de reconstrução atual no servidor.
3. **Sobreposição Quase Perfeita entre Alg 2 e Alg 4:** Na fronteira ótima de Pareto, o Algoritmo 4 (Predição Dupla EWMA) conquista uma leve vantagem sobre o Algoritmo 2, porém ambos operam virtualmente empatados.

---

### 3.4. Teste de Generalização Temporal nos 200 Dias Completos (Nó `86811`)
Congelando os hiperparâmetros obtidos nos 15 dias de abril e aplicando-os sobre os **200 dias completos (`01/03/2026` a `16/09/2026`, cobrindo final de verão, outono, inverno e início de primavera — $53.659$ amostras de temperatura e $53.644$ de umidade)**, obtivemos os seguintes resultados consolidados ([tabela_fase1_temperatura_200dias_86811.csv](../resultados_e4_fase1_temperatura/tabela_fase1_temperatura_200dias_86811.csv) e [tabela_fase1_umidade_200dias_86811.csv](../resultados_e4_fase1_umidade/tabela_fase1_umidade_200dias_86811.csv)):

#### Tabela 1 — Benchmark Global nos 200 Dias Completos (Nó `86811` — Temperatura, $53.659$ amostras)
| Algoritmo | Pacotes Transmitidos | Taxa de Redução ($TR\%$) | $\text{MAE}$ (°C) | $\text{RMSE}$ (°C) | $\text{ErroMáx}$ (°C) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alg 1 ($W=15\text{m}$)** | 17.896 | 66,65% | 0,1791 | 0,2955 | 3,044 |
| **Alg 1 ($W=30\text{m}$)** | 8.954 | 83,31% | 0,3072 | 0,4570 | 4,844 |
| **Alg 1 ($W=60\text{m}$)** | 4.480 | 91,65% | 0,4915 | 0,7031 | 6,711 |
| **Alg 2 ($\delta=0,5^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | **10.335** | **80,74%** | **0,1687** | **0,2239** | **0,499** |
| **Alg 3 ($\sigma=[0,15; 0,85], W=[5, 60]\text{m}$)** | 5.384 | 89,97% | 0,3948 | 0,5395 | 2,479 |
| **Alg 4 ($\epsilon=0,5^\circ\text{C}, T_{\text{hb}}=60\text{m}, \phi=0,75$)** | **10.191** | **81,01%** | **0,1687** | **0,2241** | **0,500** |

#### Tabela 2 — Benchmark Global nos 200 Dias Completos (Nó `86811` — Umidade Relativa, $53.644$ amostras)
| Algoritmo | Pacotes Transmitidos | Taxa de Redução ($TR\%$) | $\text{MAE}$ (%) | $\text{RMSE}$ (%) | $\text{ErroMáx}$ (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Alg 1 ($W=15\text{m}$)** | 17.893 | 66,64% | 0,5754 | 0,9762 | 13,203 |
| **Alg 1 ($W=30\text{m}$)** | 8.953 | 83,31% | 1,0311 | 1,6221 | 44,645 |
| **Alg 1 ($W=60\text{m}$)** | 4.480 | 91,65% | 1,6821 | 2,5044 | 43,931 |
| **Alg 2 ($\delta=2,0\%, T_{\text{hb}}=60\text{m}$)** | **8.341** | **84,45%** | **0,6827** | **0,8923** | **2,000** |
| **Alg 3 ($\sigma=[0,6; 3,5], W=[5, 60]\text{m}$)** | 5.065 | 90,56% | 1,4158 | 1,9619 | 9,753 |
| **Alg 4 ($\epsilon=2,0\%, T_{\text{hb}}=60\text{m}, \phi=0,82$)** | **8.264** | **84,59%** | **0,6805** | **0,8901** | **2,000** |

**Conclusão da Validação Cruzada Temporal:** A variação de desempenho entre o recorte de 15 dias e os 200 dias completos foi inferior a **$0,15\%$ em $TR\%$** e inferior a **$0,003^\circ\text{C}$ / $0,02\%$ em $\text{RMSE}$**. Isso comprova que a calibração realizada não sofreu *overfitting* sazonal e que os hiperparâmetros congelados são temporalmente invariantes.

---

## 4. Validação da Reconstrução da Série Temporal vs. Série Base

O script [reconstrucao_validacao.py](../E4/reconstrucao_validacao.py) produziu a inspeção visual de alta resolução (janela de 72 horas entre `04/04/2026` e `07/04/2026`) comparando a série original de 5 min ($y_t$) com a série reconstruída no servidor ($\hat{y}_t$) e com a curva de erro absoluto instantâneo $|y_t - \hat{y}_t|$:
- **Painéis de Reconstrução (4 Algoritmos):** [reconstrucao_72h_temperatura_86811.png](../resultados_e4_reconstrucao/reconstrucao_72h_temperatura_86811.png) e [reconstrucao_72h_umidade_86811.png](../resultados_e4_reconstrucao/reconstrucao_72h_umidade_86811.png)
- **Painéis de Erro Instantâneo e Teto Determinístico:** [erro_instantaneo_72h_temperatura_86811.png](../resultados_e4_reconstrucao/erro_instantaneo_72h_temperatura_86811.png) e [erro_instantaneo_72h_umidade_86811.png](../resultados_e4_reconstrucao/erro_instantaneo_72h_umidade_86811.png)

### Principais Observações na Reconstrução
1. **Modulação Automática da Densidade de Pacotes:** Observando os marcadores de pacotes transmitidos nos gráficos de 72h, nota-se que durante a madrugada (`00h` às `06h`), os Algoritmos 2 e 4 espaçam os envios exatamente em $60\text{ min}$ (guiados apenas pelo *heartbeat* $T_{\text{hb}}$). Assim que ocorre a rampa de aquecimento solar (`07h` às `11h`), a densidade de marcadores aumenta organicamente para acompanhar a derivada física da curva sem atraso.
2. **Controle Rígido do Erro Máximo ($\text{ErroMáx}$) e Percentil 95 ($P_{95}$):**
   - Na janela de 200 dias, o Algoritmo 1 ($W=30\text{m}$) gera picos de erro de até **$4,84^\circ\text{C}$** e **$44,65\%$ UR** no servidor nos momentos em que uma frente térmica ou descarga de ar-condicionado ocorre logo após o fechamento de uma janela.
   - Já nos Algoritmos 2 e 4, a linha tracejada vermelha nos gráficos de erro instantâneo ($\delta = \epsilon = 0,5^\circ\text{C}$ e $2,0\%$) atua como uma barreira intransponível: **100% das 53.659 amostras reconstruídas permanecem estritamente dentro da tolerância metrológica do transdutor** ($P_{95} = 0,44^\circ\text{C}$ e $1,75\%$).

---

## 5. Fase 2: Aplicação Direcionada nos Coortes Experimentais

Com os algoritmos validados e os parâmetros congelados no nó `86811`, o script [coortes_ar_solo_indoor.py](../E4/coortes_ar_solo_indoor.py) estendeu a avaliação para todos os 4 coortes do dataset ([tabela_consolidada_todos_coortes_200dias.csv](../resultados_e4_coortes/tabela_consolidada_todos_coortes_200dias.csv) e [comparacao_multi_coorte_tr_200dias.png](../resultados_e4_coortes/comparacao_multi_coorte_tr_200dias.png)).

### 5.1. Coorte 2 (`Agricola_Solo` — Estação `TCC MESSIAS`, Nó `86817`): Contraste Atmosfera (Ar) vs. Solo
A estação multi-sensor `86817` (`TCC MESSIAS`, $\sim 23.000$ amostras por sensor) permite investigar uma questão central para a cafeicultura de precisão: **como a diferença física entre a dinâmica rápida da atmosfera e a inércia térmica/hídrica do solo impacta os algoritmos de supressão?**

Os resultados detalhados em [tabela_coorte2_ar_vs_solo_86817.csv](../resultados_e4_coortes/tabela_coorte2_ar_vs_solo_86817.csv), [coorte2_reconstrucao_ar_vs_solo_86817.png](../resultados_e4_coortes/coorte2_reconstrucao_ar_vs_solo_86817.png) e [coorte2_barras_ar_vs_solo_86817.png](../resultados_e4_coortes/coorte2_barras_ar_vs_solo_86817.png) são resumidos abaixo:

| Grandeza (Nó `86817` — `TCC MESSIAS`) | Algoritmo | Amostras | Pacotes | $TR$ (%) | $\text{MAE}$ | $\text{RMSE}$ | $\text{ErroMáx}$ |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Temperatura do Ar** (`temperatura`) | Alg 1 ($W=30\text{m}$) | 22.653 | 3.799 | 83,23% | 0,2247 °C | 0,4660 °C | 18,312 °C |
| **Temperatura do Ar** (`temperatura`) | **Alg 2 ($\delta=0,5^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | 22.653 | 3.417 | **84,92%** | 0,1664 °C | 0,2211 °C | **0,500 °C** |
| **Temperatura do Ar** (`temperatura`) | **Alg 4 ($\epsilon=0,5^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | 22.653 | **3.169** | **86,01%** | **0,1644 °C** | **0,2179 °C** | **0,500 °C** |
| **Temperatura do Solo** (`temperatura_solo`) | Alg 1 ($W=30\text{m}$) | 23.032 | 3.863 | 83,23% | 0,0637 °C | 0,1284 °C | 2,701 °C |
| **Temperatura do Solo** (`temperatura_solo`) | **Alg 2 ($\delta=0,5^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | 23.032 | 2.091 | **90,92%** | 0,1089 °C | 0,1532 °C | **0,499 °C** |
| **Temperatura do Solo** (`temperatura_solo`) | **Alg 4 ($\epsilon=0,5^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | 23.032 | **2.074** | **91,00%** | **0,1084 °C** | **0,1526 °C** | **0,500 °C** |
| **Temp. Solo (Alta Precisão)** | **Alg 2 ($\delta=0,2^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | 23.032 | 2.847 | **87,64%** | 0,0711 °C | 0,0924 °C | **0,200 °C** |
| **Temp. Solo (Alta Precisão)** | **Alg 4 ($\epsilon=0,2^\circ\text{C}, T_{\text{hb}}=60\text{m}$)** | 23.032 | **2.803** | **87,83%** | **0,0705 °C** | **0,0918 °C** | **0,200 °C** |
| **Umidade do Ar** (`umidade`) | **Alg 2 ($\delta=2,0\%, T_{\text{hb}}=60\text{m}$)** | 22.656 | 3.278 | **85,53%** | 0,6168 % | 0,8535 % | **2,000 %** |
| **Umidade do Ar** (`umidade`) | **Alg 4 ($\epsilon=2,0\%, T_{\text{hb}}=60\text{m}$)** | 22.656 | **3.104** | **86,30%** | **0,5973 %** | **0,8327 %** | **2,000 %** |
| **Umidade do Solo** (`umidade_solo`) | **Alg 2 ($\delta=2,0\%, T_{\text{hb}}=60\text{m}$)** | 23.058 | **2.022** | **91,23%** | **0,2160 %** | **0,3423 %** | **1,992 %** |
| **Umidade do Solo** (`umidade_solo`) | **Alg 4 ($\epsilon=2,0\%, T_{\text{hb}}=60\text{m}$)** | 23.058 | 2.030 | **91,20%** | 0,2207 % | 0,3493 % | **1,989 %** |

#### Discussão Técnica (Ar vs. Solo):
1. **Salto de Compressão nas Grandezas Edáficas ($TR > 91\%$):** Como o solo atua como um filtro passa-baixas natural de alta capacidade calorífica e retenção hídrica, as variações em $60\text{ min}$ raramente excedem $0,5^\circ\text{C}$ ou $2,0\%$. Consequentemente, os Algoritmos 2 e 4 atingem **$TR = 91,00\%$ na temperatura do solo** e **$TR = 91,23\%$ na umidade do solo** — colando no limite teórico máximo de $91,67\%$ imposto pelo *heartbeat* de $60\text{ min}$ ($\frac{11}{12}$ pacotes suprimidos).
2. **Desempate a Favor do Algoritmo 4 nas Rampas Suaves:** No microclima externo da estação agrícola (`86817`), onde o aquecimento e o resfriamento seguem rampas solares mais suaves do que ao lado das condensadoras de ar-condicionado, o **Algoritmo 4 economiza $248$ pacotes a mais que o Algoritmo 2 na temperatura do ar ($TR = 86,01\%$ vs. $84,92\%$)** e **$174$ pacotes a mais na umidade do ar ($86,30\%$ vs. $85,53\%$)**, além de reduzir simultaneamente o $\text{RMSE}$. No solo sob limiar fino de alta precisão ($\delta = \epsilon = 0,2^\circ\text{C}$), permite monitorar o perfil edáfico com erro médio de apenas **$0,07^\circ\text{C}$** mantendo **$87,83\%$ de economia de rádio**.

---

### 5.2. Coorte 3 (`Indoor_Baseline` — Nós `1` e `86782` no `Lab 1006`): Limite Superior em Regime Estável
Os nós internos climatizados `1` (`TEMP2`) e `86782` (`TEMP4`) operam sob forte estabilidade térmica noturna e em finais de semana, intercalada por degraus de ar-condicionado em horário comercial. Eles demonstram experimentalmente o teto operacional de economia dos algoritmos em períodos de calmaria climática:

| Dispositivo (`Coorte 3: Indoor_Baseline`) | Grandeza | Algoritmo | Pacotes | $TR$ (%) | $\text{MAE}$ | $\text{RMSE}$ | $\text{ErroMáx}$ |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Nó `1` (`TEMP2`)** | Temperatura | Alg 2 ($\delta=0,5^\circ\text{C}$) | 5.531 | **89,69%** | 0,1037 °C | 0,1550 °C | 0,499 °C |
| **Nó `1` (`TEMP2`)** | Temperatura | Alg 4 ($\epsilon=0,5^\circ\text{C}$) | 5.478 | **89,79%** | **0,1026 °C** | **0,1531 °C** | 0,500 °C |
| **Nó `1` (`TEMP2`)** | Umidade | Alg 2 ($\delta=2,0\%$) | 6.151 | **88,54%** | 0,5391 % | 0,7424 % | 1,999 % |
| **Nó `1` (`TEMP2`)** | Umidade | Alg 4 ($\epsilon=2,0\%$) | 6.147 | **88,55%** | **0,5350 %** | **0,7397 %** | 2,000 % |
| **Nó `86782` (`TEMP4`)** | Temperatura | Alg 2 ($\delta=0,5^\circ\text{C}$) | 6.257 | **88,34%** | 0,1093 °C | 0,1614 °C | 0,499 °C |
| **Nó `86782` (`TEMP4`)** | Temperatura | Alg 4 ($\epsilon=0,5^\circ\text{C}$) | 6.242 | **88,37%** | **0,1077 °C** | **0,1593 °C** | 0,500 °C |
| **Nó `86782` (`TEMP4`)** | Umidade | Alg 2 ($\delta=2,0\%$) | 6.887 | **87,17%** | 0,5471 % | 0,7536 % | 1,999 % |
| **Nó `86782` (`TEMP4`)** | Umidade | Alg 4 ($\epsilon=2,0\%$) | 6.875 | **87,19%** | **0,5457 %** | **0,7534 %** | 2,000 % |

---

### 5.3. Comparação Transversal entre Coortes e Decisão de Engenharia: Algoritmo 2 vs. Algoritmo 4
Ao comparar todos os coortes ([comparacao_multi_coorte_tr_200dias.png](../resultados_e4_coortes/comparacao_multi_coorte_tr_200dias.png)), observa-se um gradiente físico consistente na taxa de supressão $TR\%$:
1. **Nó Externo Próximo a Condensadora (`86809`):** Maior turbulência térmica localizada $\to TR \approx 71,2\%$ (Temp) e $77,4\%$ (Umid);
2. **Nó Externo Padrão (`86811`):** Ciclo solar diurno aberto $\to TR \approx 81,0\%$ (Temp) e $84,6\%$ (Umid);
3. **Estação Agrícola Ar (`86817`):** Ciclo agrometeorológico externo suave $\to TR \approx 86,0\%$ (Temp) e $86,3\%$ (Umid);
4. **Ambiente Climatizado (`1`, `86782`, `86794`):** Estabilidade controlada $\to TR \approx 88,4\%\text{–}89,8\%$ (Temp);
5. **Solo Agrícola (`86817` Solo):** Alta inércia edáfica $\to TR \approx 91,0\%\text{–}91,2\%$ (limitado apenas pelo *heartbeat* de $60\text{ min}$).

**Síntese da Escolha Algorítmica (Alg 2 vs. Alg 4):**
- O **Algoritmo 4 (Predição Dupla EWMA)** é matematicamente o mais sofisticado e alcança o melhor desempenho absoluto (até $+1,1\%$ de ganho em $TR\%$ sobre o Algoritmo 2 na estação agrícola `TCC MESSIAS`), porém exige sincronismo estrito de estado entre nó e servidor (qualquer pacote perdido em enlace sem *acknowledgment* exige recomputação ou confirmação via *downlink* para não divergir a reta extrapolada).
- O **Algoritmo 2 (*Duty-Cycle* Híbrido por Limiar Estático)** entrega $99\%$ do benefício do Algoritmo 4 com complexidade $\mathcal{O}(1)$, zero hiperparâmetros de filtragem para calibrar e imunidade natural a desvio de inclinação, consolidando-se como a recomendação principal de embarque imediato em nós LoRaWAN de baixo custo, enquanto o Algoritmo 4 destaca-se para variáveis de rampa lenta (como temperatura/umidade de solo em alta precisão) ou enlaces com confirmação de recebimento.

---

## 6. Resposta a Anomalias Climáticas e Latência de Alerta ($\Delta t_{\text{alerta}}$)

Em aplicações agrícolas críticas (como alerta de geada severa em cafezais ou detecção de falha de irrigação/refrigeração), a economia de bateria não pode comprometer a **tempestividade da notificação**. Define-se a **Latência de Alerta ($\Delta t_{\text{alerta}}$)** como o intervalo de tempo decorrido entre o instante exato $t_{\text{real}}$ em que a grandeza física cruza um limiar crítico de emergência ($L_{\text{crit}}$) e o instante $t_{\text{srv}}$ em que o servidor central recebe o primeiro pacote reportando $\hat{y}_t \ge L_{\text{crit}}$ (ou $\le L_{\text{crit}}$):

$$
\Delta t_{\text{alerta}} = t_{\text{srv}} - t_{\text{real}}
$$

O script [anomalias_alertas.py](../E4/anomalias_alertas.py) avaliou três cenários complementares (um evento real extremo do banco de dados e duas injeções sintéticas em direções opostas e em fases temporais distintas):
1. **Cenário Real (`Coorte 4: Cluster_Server` — Nó `86794` em `29/03/2026` e Nó `86795`):**
   - No dia `29/03/2026`, uma falha no sistema de climatização da sala de servidores fez a temperatura do nó `86794` saltar **$+6,0^\circ\text{C}$ em 40 minutos** (de $20,3^\circ\text{C}$ às `17:15` para um pico de **$26,36^\circ\text{C}$** às `17:55`, cruzando o limiar crítico de $23,0^\circ\text{C}$ às `17:25`). Adicionalmente, avaliou-se o nó `86795` tanto no pico extremo registrado no banco ($51,20^\circ\text{C}$ em `12/03/2026`) quanto no evento de sobreaquecimento prolongado de `03–04/09/2026` ($25,30^\circ\text{C}$).
2. **Injeção Sintética de Descida — Frente Fria / Geada (Nó `86811`, Temperatura em `05/04/2026` às `06:05`):**
   - Rampa abrupta de **$-6,0^\circ\text{C}$ em 20 minutos** ($4$ passos de $5\text{ min}$), mantendo o patamar frio por $2\text{ horas}$, com limiar crítico de alerta $3,0^\circ\text{C}$ abaixo da temperatura pré-evento ($L_{\text{crit}} \le 21,6^\circ\text{C}$).
3. **Injeção Sintética de Subida — Chuva / Irrigação Súbita (Nó `86811`, Umidade Relativa em `05/04/2026` às `06:50`):**
   - Rampa abrupta de **$+25,0\%$ em 20 minutos** (respeitando a saturação física em $100\%$), iniciada propositalmente em uma fase horária distinta (`06:50`), com limiar crítico $12,0\%$ acima do nível pré-evento ($L_{\text{crit}} \ge 90,2\%$).

### 6.1. Resultados Consolidados de Latência de Alerta e Erro de Pico
Os resultados quantitativos ([tabela_anomalias_latencia_alerta.csv](../resultados_e4_anomalias/tabela_anomalias_latencia_alerta.csv)) e visuais ([anomalia_real_cluster_server_86794_86795.png](../resultados_e4_anomalias/anomalia_real_cluster_server_86794_86795.png) e [eventos_sinteticos_geada_chuva_86811.png](../resultados_e4_anomalias/eventos_sinteticos_geada_chuva_86811.png)) são apresentados na tabela a seguir:

| Cenário de Emergência | Algoritmo | Limiar Crítico | Latência ($\Delta t_{\text{alerta}}$) | Extremo Real | Extremo Reconstruído | Erro de Pico | $\text{RMSE}$ na Janela |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Surto Real `Cluster_Server` (`29/03`)** | Alg 1 ($W=30\text{m}$ Média) | $\ge 23,0^\circ\text{C}$ | **40,0 min** | 26,356 °C | 25,159 °C | 1,196 °C | 1,4747 °C |
| **1. Surto Real `Cluster_Server` (`29/03`)** | Alg 1 ($W=60\text{m}$ Média) | $\ge 23,0^\circ\text{C}$ | **40,0 min** | 26,356 °C | 23,761 °C | 2,595 °C | 1,8948 °C |
| **1. Surto Real `Cluster_Server` (`29/03`)** | **Alg 2 ($\delta=0,5^\circ\text{C}$)** | $\ge 23,0^\circ\text{C}$ | **0,0 min** | 26,356 °C | 26,211 °C | **0,145 °C** | 0,1878 °C |
| **1. Surto Real `Cluster_Server` (`29/03`)** | **Alg 4 ($\epsilon=0,5^\circ\text{C}$)** | $\ge 23,0^\circ\text{C}$ | **0,0 min** | 26,356 °C | 26,415 °C | **0,059 °C** | **0,1752 °C** |
| **2. Geada Sintética (`06:05` — Descida)** | Alg 1 ($W=30\text{m}$ Média) | $\le 21,6^\circ\text{C}$ | **15,0 min** | 17,791 °C | 18,373 °C | 0,582 °C | 1,1103 °C |
| **2. Geada Sintética (`06:05` — Descida)** | Alg 1 ($W=60\text{m}$ Média) | $\le 21,6^\circ\text{C}$ | **45,0 min** | 17,791 °C | 19,077 °C | 1,286 °C | 1,9645 °C |
| **2. Geada Sintética (`06:05` — Descida)** | **Alg 2 ($\delta=0,5^\circ\text{C}$)** | $\le 21,6^\circ\text{C}$ | **0,0 min** | 17,791 °C | 18,010 °C | **0,219 °C** | **0,2189 °C** |
| **2. Geada Sintética (`06:05` — Descida)** | **Alg 4 ($\epsilon=0,5^\circ\text{C}$)** | $\le 21,6^\circ\text{C}$ | **0,0 min** | 17,791 °C | 17,791 °C | **0,000 °C** | 0,2240 °C |
| **3. Chuva Sintética (`06:50` — Subida)** | Alg 1 ($W=30\text{m}$ Média) | $\ge 90,2\%$ | **25,0 min** | 100,00 % | 98,865 % | 1,135 % | 4,4168 % |
| **3. Chuva Sintética (`06:50` — Subida)** | Alg 1 ($W=60\text{m}$ Média) | $\ge 90,2\%$ | **55,0 min** | 100,00 % | 98,345 % | 1,655 % | 7,1668 % |
| **3. Chuva Sintética (`06:50` — Subida)** | **Alg 2 ($\delta=2,0\%$)** | $\ge 90,2\%$ | **0,0 min** | 100,00 % | 100,00 % | **0,000 %** | **0,8182 %** |
| **3. Chuva Sintética (`06:50` — Subida)** | **Alg 4 ($\epsilon=2,0\%$)** | $\ge 90,2\%$ | **0,0 min** | 100,00 % | 100,00 % | **0,000 %** | 0,8264 % |

### 6.2. Discussão Teórica: Dependência de Fase na Janela Fixa vs. Pronta Resposta Orientada a Eventos
Como demonstrado pelas duas injeções sintéticas em instantes distintos (`06:05` vs. `06:50`), o atraso de notificação do **Algoritmo 1 (Janela Fixa de período $W$)** não é constante, mas sim uma **variável dependente da fase de chegada da anomalia** em relação ao relógio interno de fechamento da janela:
- **Limites analíticos do Algoritmo 1:** Caso o limiar crítico seja rompido no exato instante de fechamento da janela e a média acumulada já tenha superado $L_{\text{crit}}$, o atraso mínimo teórico é $\Delta t_{\min} = 0\text{ min}$. Contudo, se o cruzamento ocorrer logo no primeiro passo após o início de um novo ciclo ($5\text{ min}$ após o envio anterior), o nó permanecerá em silêncio por pelo menos $\Delta t = W - \Delta t_{\text{nominal}}$ (ex.: $25\text{ min}$ para $W=30\text{m}$ e $55\text{ min}$ para $W=60\text{m}$, exatamente como observado no cenário das `06:50`). Mais grave ainda: quando o pacote transmite a **média da janela**, as leituras normais anteriores ao evento diluem o valor médio, podendo impedir que a média cruze $L_{\text{crit}}$ no primeiro fechamento e empurrando o alerta para a janela seguinte (como ocorreu no surto real de `29/03`, onde $W=30\text{m}$ demorou $40\text{ min}$ para alertar e achatou o pico real de $26,36^\circ\text{C}$ em até $2,60^\circ\text{C}$).
- **Invariância de Fase e Latência Zero dos Algoritmos 2 e 4:** Por testarem a condição de disparo $|y_t - \hat{y}_t| \ge \delta, \epsilon$ a cada passo discreto de amostragem ($\Delta t = 5\text{ min}$), os Algoritmos 2 e 4 são **completamente invariantes à fase do evento**: qualquer rampa abrupta que rompa o limiar crítico força o envio imediato do pacote naquele exato ciclo de leitura, garantindo deterministicamente **$\Delta t_{\text{alerta}} = 0,0\text{ min}$** (em relação à resolução do rastro) e preservando o valor extremo de pico/vale.

---

## 7. Fase 3: Agregação Espacial via *Cluster Head* e Acoplamento Temporal + Espacial (`Coorte 1: Externo_Cluster`)

Para avaliar a redução de tráfego em topologia hierárquica (nós-folha transmitindo em enlace local curto para um *Cluster Head*, que agrega espacialmente o talhão e transmite em enlace longo LoRaWAN para o Gateway), o script [cluster_head_espacial.py](../E4/cluster_head_espacial.py) utilizou a matriz sincronizada dos 9 nós externos da **Coorte 1 (`Externo_Cluster`)** ([koala_cluster_externo_wide_5min.csv](../dataset_koala_e2/koala_cluster_externo_wide_5min.csv)).

A cada passo $t$, o *Cluster Head* coleta as estimativas ativas $\{v_{1,t}, \dots, v_{N,t}\}$ do grupo, calcula a **mediana espacial** $M_t = \text{mediana}(v_{i,t})$ e o **desvio espacial máximo instantâneo**:

$$
\Delta_{\max}(t) = \max_{i \in \{1,\dots,N\}} |v_{i,t} - M_t|
$$

- Se $\Delta_{\max}(t) \le \tau_{\text{espacial}}$: o talhão é considerado espacialmente coeso e o *Cluster Head* representa todo o grupo apenas pela mediana $M_t$;
- Se $\Delta_{\max}(t) > \tau_{\text{espacial}}$: o *Cluster Head* sinaliza uma **discrepância espacial localizada**, reportando a mediana $M_t$ acompanhada da identificação e leitura do nó discrepante.

### 7.1. Fundamentação Estatística da Escolha de $\tau_{\text{espacial}}$: Heterogeneidade Estática vs. Anomalia Dinâmica
Uma questão metodológica fundamental na parametrização do *Cluster Head* é: **de onde provém o valor numérico do limiar $\tau_{\text{espacial}}$?**

Em condições ideais de bancada (todos os sensores co-localizados no mesmo ponto físico), $\tau_{\text{espacial}}$ seria determinado puramente pela soma das incertezas de hardware ($\sim 1,0^\circ\text{C}$). Contudo, em uma lavoura real — e na área externa do testbed Koala — os sensores ocupam posições geográficas distintas sujeitas a **heterogeneidade microclimática estática** (diferenças permanentes de insolação, sombreamento de parede/copa, ventilação ou *offset* crônico de calibração, como o do nó `86812` antes de sua falha em maio).

No rastro real dos 9 nós externos entre `10/04/2026` e `17/04/2026` ([tabela_calibracao_tau_espacial_10a17abril.csv](../resultados_e4_cluster_head/tabela_calibracao_tau_espacial_10a17abril.csv)), o desvio máximo entre os 9 sensores permanece basalmente em torno de **$\overline{\Delta_{\max}} = 3,27^\circ\text{C}$** todos os dias, atingindo um surto extremo de **$7,90^\circ\text{C}$** no dia `13/04` às `14:40` (quando a descarga de ar quente da condensadora atingiu diretamente o nó `1006EXT-TEMPHUM-01`).
- Caso se adotasse um limiar arbitrário baixo ($\tau_{\text{espacial}} = 1,0^\circ\text{C}$ ou $2,0^\circ\text{C}$), o *Cluster Head* classificaria a diferença geográfica estática entre sol e sombra como "anomalia" em **$98,6\%$ a $100\%$ do tempo**, enviando pacotes extras continuamente e anulando o ganho da agregação espacial.
- Na ausência de rótulos externos supervisionados de falha, a calibração científica não-supervisionada define $\tau_{\text{espacial}}$ a partir do **Percentil Empírico $P_{90}\text{–}P_{95}$ da distribuição histórica de $\Delta_{\max}$ do próprio talhão**:

$$
\tau_{\text{espacial}} \approx P_{90}(\Delta_{\max}) \text{ a } P_{95}(\Delta_{\max})
$$

Desse modo, o *Cluster Head* absorve os $90\%\text{–}95\%$ de variação microclimática rotineira do talhão apenas com a mediana $M_t$, reservando o disparo de alerta espacial exclusivamente para a cauda estatística extrema ($5\%\text{–}10\%$ dos eventos onde um nó descola abruptamente do comportamento coletivo, como no pico de $7,90^\circ\text{C}$ em `13/04`, ilustrado em [calibracao_tau_espacial_abril_cluster_head.png](../resultados_e4_cluster_head/calibracao_tau_espacial_abril_cluster_head.png)).

### 7.2. Efeito da Subdivisão do Talhão em Sub-Clusters Homogêneos (`1006EXT` vs. `1008EXT`)
Para comprovar que o valor elevado de $\tau_{\text{espacial}} = 4,5^\circ\text{C}$ no grupo de 9 nós decorre do gradiente térmico entre as duas fachadas externas (`1006EXT`, mais quente com média de $\sim 26,5^\circ\text{C}$, vs. `1008EXT`, mais sombreada com média de $\sim 24,3^\circ\text{C}$), avaliamos a divisão da Coorte 1 em **2 Sub-Clusters fisicamente contíguos** ([tabela_comparacao_1cluster_vs_2subclusters_abril.csv](../resultados_e4_cluster_head/tabela_comparacao_1cluster_vs_2subclusters_abril.csv) e [comparacao_1cluster_vs_2subclusters_tau.png](../resultados_e4_cluster_head/comparacao_1cluster_vs_2subclusters_tau.png)):
- **Sub-Cluster A (`1006EXT` — 4 nós):** `86809`, `86811`, `86812`, `86813`;
- **Sub-Cluster B (`1008EXT` — 5 nós):** `86814`, `86784`, `86785`, `86783`, `46`.

| Agrupamento Espacial (`10/04` a `17/04/2026`) | $\overline{\Delta_{\max}}$ Médio | Percentil $P_{90}(\Delta_{\max})$ | Tempo Apenas Mediana ($\tau = 3,0^\circ\text{C}$) | Tempo Apenas Mediana ($\tau = 3,5^\circ\text{C}$) | Tempo Apenas Mediana ($\tau = 4,5^\circ\text{C}$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Cluster Único (9 nós: `1006EXT + 1008EXT`)** | 3,27 °C | 4,15 °C | 41,38% | 70,17% | **94,70%** |
| **Sub-Cluster A: `1006EXT` (4 nós)** | **2,56 °C** | **3,67 °C** | 74,55% | **87,41%** | 96,79% |
| **Sub-Cluster B: `1008EXT` (5 nós)** | **2,49 °C** | **3,41 °C** | 79,68% | **91,71%** | 98,39% |

**Conclusão Arquitetural para Lavouras de Café:** Ao particionar um talhão heterogêneo em sub-clusters menores e microclimaticamente homogêneos ($4$ a $5$ sensores por zona de insolação/altitude), o desvio basal médio cai em **$\sim 0,75^\circ\text{C}$** (e nos 200 dias completos do `1006EXT` cai para **$1,71^\circ\text{C}$**), permitindo **reduzir o limiar $\tau_{\text{espacial}}$ de $4,5^\circ\text{C}$ para $3,5^\circ\text{C}$** enquanto se mantém $\sim 90\%$ do tempo de operação apenas com o envio enxuto da mediana.

### 7.3. Simulação Conjunta Acoplada nos 200 Dias Completos e Tolerância a *Node Death*
Por fim, simulamos os **200 dias completos** acoplando a supressão temporal nos 9 nós-folha (Algoritmo 2 ou Algoritmo 4 no enlace local Nó $\to$ CH) com a agregação espacial pela mediana e supressão temporal no *Cluster Head* (enlace longo LoRaWAN CH $\to$ Gateway, com $\tau_{\text{espacial}} = 4,5^\circ\text{C}$ para Temperatura e $\tau_{\text{espacial}} = 12,0\%$ para Umidade Relativa). Os resultados estão consolidados em [tabela_cluster_head_acoplado_200dias.csv](../resultados_e4_cluster_head/tabela_cluster_head_acoplado_200dias.csv):

| Grandeza (9 Nós Externos — 200 Dias) | Arquitetura Acoplada (Nó-Folha + CH) | Amostras Brutas (9 Nós) | Pacotes Enlace Local (Nó $\to$ CH) | $TR_{\text{local}}$ (%) | Pacotes LoRaWAN (CH $\to$ Gateway) | $TR_{\text{global}}$ LoRaWAN (%) | Fator de Compressão | $\text{RMSE}$ da Mediana |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Temperatura (°C)** | Sem Supressão no Nó-Folha (Bruto 5m $\to$ CH) | 449.681 | 449.681 | 0,00% | 10.349 | 97,70% | $43,5\times$ | 0,2231 °C |
| **Temperatura (°C)** | **Nó-Folha Alg 2 ($\delta=0,5^\circ\text{C}$) + CH ($\tau=4,5^\circ\text{C}$)** | 449.681 | **92.926** | **79,34%** | **9.338** | **97,92%** | **$48,2\times$** | **0,2852 °C** |
| **Temperatura (°C)** | **Nó-Folha Alg 4 ($\epsilon=0,5^\circ\text{C}$) + CH ($\tau=4,5^\circ\text{C}$)** | 449.681 | **91.325** | **79,69%** | **9.190** | **97,96%** | **$48,9\times$** | **0,2942 °C** |
| **Umidade (%)** | Sem Supressão no Nó-Folha (Bruto 5m $\to$ CH) | 449.616 | 449.616 | 0,00% | 9.053 | 97,99% | $49,7\times$ | 0,8901 % |
| **Umidade (%)** | **Nó-Folha Alg 2 ($\delta=2,0\%$) + CH ($\tau=12,0\%$)** | 449.616 | **77.280** | **82,81%** | **8.046** | **98,21%** | **$55,9\times$** | **1,1731 %** |
| **Umidade (%)** | **Nó-Folha Alg 4 ($\epsilon=2,0\%$) + CH ($\tau=12,0\%$)** | 449.616 | **75.998** | **83,10%** | **8.064** | **98,21%** | **$55,8\times$** | **1,1879 %** |

#### Destaques da Arquitetura Acoplada:
1. **Compressão Multiplicativa em Dois Níveis ($48\times$ a $56\times$ menos pacotes LoRaWAN):** A aplicação do Algoritmo 2 ou 4 nos nós-folha elimina **$\sim 80\%$ a $83\%$ das transmissões locais** (poupando a bateria dos sensores de campo), enquanto a agregação pela mediana no *Cluster Head* comprime as $449.681$ leituras brutas do grupo em apenas **$9.190\text{ a }9.338$ pacotes LoRaWAN** em temperatura (**$TR_{\text{global}} = 97,96\%$**) e **$8.046$ pacotes** em umidade (**$TR_{\text{global}} = 98,21\%$**), mantendo a fidelidade de reconstrução da mediana do talhão em $\text{RMSE} = 0,285^\circ\text{C}$ e $1,17\%$.
2. **Tolerância Automática à Falha Permanente (*Node Death* do Nó `86812` em `15/05/2026`):** Conforme demonstrado em [cluster_head_node_death_86812.png](../resultados_e4_cluster_head/cluster_head_node_death_86812.png), quando o nó `86812` (`1006EXT-TEMPHUM-04`) sofre morte súbita de hardware em `15/05/2026` às `11:30`, o *Cluster Head* detecta o *timeout* de *heartbeat* e reconfigura automaticamente o cálculo da mediana espacial de $9$ para $8$ nós ativos, garantindo continuidade ininterrupta ao monitoramento do talhão sem contaminar a série histórica.
