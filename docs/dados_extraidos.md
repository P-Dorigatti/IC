# Documento de Handoff de Dados (Entregáveis E1, E2 e E5-Bloco A) — IC FAPESP

**Pesquisador:** Pedro Dorigatti Aureo Ferreira (Engenharia de Computação — ICMC/USP)  
**Orientador:** Prof. Dr. Julio Cezar Estrella (LaSDPC — ICMC/USP)  
**Status Atual:** Entregáveis **E1** (Extração), **E2** (Dataset Padronizado) e **E5-Bloco A** (Métricas de QoS Empírico) **100% concluídos**. Próximas etapas: **E3** (Gráficos Exploratórios) e **E4** (Implementação e Simulação dos Algoritmos de Agregação).

---

## 1. Descobertas Técnicas sobre o Banco do Testbed Koala e Decisões de Engenharia

Durante a sondagem e extração via API REST (`http://andromeda.lasdpc.icmc.usp.br:60106/datastream/filter`), identificamos particularidades críticas da infraestrutura que guiaram a construção do dataset:

1. **Resolução Temporal Mínima (`timeBucket = "5 minutes"`):**
   - O menor intervalo de agregação suportado nativamente pelo endpoint `/datastream/filter` sem erros é de **5 minutos** ($T_{\text{nominal}} = 5\text{ min}$).
   - A API retorna, para cada bloco de 5 minutos, as chaves `time_interval`, `avg_value`, `min_value` e `max_value`. Todos os três valores numéricos foram preservados no dataset mestre (`valor`, `valor_min`, `valor_max`), permitindo avaliar tanto a série temporal principal (`avg_value`) quanto a volatilidade intra-bloco.
   - **Impacto nos Algoritmos (Ajuste Metodológico Seção 3.2):** Como o passo discreto base é $\Delta t = 5\text{ min}$, o envio a cada 5 min representa o *Baseline Sem Supressão* ($TR = 0\%$). No **Algoritmo 1 (Janela Fixa)**, as janelas avaliadas são múltiplos inteiros da base: $W \in \{15, 30, 60, 120\}\text{ min}$ (agrupando 3, 6, 12 e 24 leituras). No **Algoritmo 3 (Janela Adaptativa Baseada em Variância)**, o limite inferior foi ajustado de $W_{\min} = 2\text{ min}$ para a resolução nativa do rastro ($W_{\min} = 5\text{ min}$ em transientes rápidos até $W_{\max} = 60\text{ min}$ em estabilidade).

2. **Falsos Negativos por Contaminantes `NaN` (IEEE 754):**
   - Na sondagem inicial, diversos sensores de umidade (`id_sensor = 2`) e de solo (`id_sensor = 14`) apresentavam média `nan` no Python.
   - **Causa diagnosticada:** O banco de dados retorna esporadicamente registros onde `avg_value` é um `NaN` numérico (serializado no JSON, diferente de `null`/`None`). Um único `NaN` em 2.300 blocos contaminava a soma em ponto flutuante.
   - **Solução aplicada:** Implementamos validação estrita (`not math.isnan(f) and not math.isinf(f)`) combinada com filtros de limites físicos de transdução antes da consolidação, revelando que os sensores possuíam, na realidade, **98,8% a 100% de leituras perfeitamente válidas**. Antes do descarte no CSV limpo, todos os `NaN`s e *outliers* foram contabilizados na tabela de auditoria de QoS para diferenciar **falha de leitura de hardware (ADC/transdutor)** de **perda de pacote em rede**.

3. **Mitigação de *Read Timeout* e Bug de Fuso Horário na Paginação:**
   - Consultas longas em resolução de 5 minutos causavam `ReadTimeout` no servidor. A extração foi paginada em **janelas curtas de 10 dias** com mecanismo de *retry* automático.
   - **Descoberta do truncamento de borda (6 horas):** Paginações sequenciais secas (`T00:00:00Z` a `T23:59:59Z`) geravam falsas lacunas de exatamente `360.0 min` (`00:00` às `06:00`) nas datas de fronteira devido à conversão interna de fuso horário (UTC vs. BRT) no backend.
   - **Solução aplicada:** Janelas deslizantes de 10 dias com **sobreposição (*overlap*) de 12 horas** entre requisições consecutivas, seguidas de desduplicação determinística pela chave primária `(timestamp, id_dispositivo, id_sensor)`. Isso eliminou 100% dos falsos gaps de paginação.

4. **Escolha Estratégica da Janela Temporal (`01/03/2026` a `16/09/2026` — 200 dias):**
   - A auditoria de lacunas revelou que o servidor central do laboratório sofreu uma interrupção prolongada de ~19,5 dias entre `30/09/2026` e `19/10/2026`, o que derrubava artificialmente o PDR global para `70,9%`.
   - Ao definir o recorte oficial de **01/03/2026 a 16/09/2026 (200 dias contínuos)**:
     - Capturamos todo o 1º semestre e inverno/início de primavera nos nós veteranos (~53.660 amostras válidas por sensor);
     - Capturamos os meses de operação plena da estação agrícola `TCC MESSIAS` e dos novos nós do `Cluster 1006` (ativos a partir de final de maio/início de julho até meados de setembro, com ~23.000 amostras por sensor);
     - Eliminamos o apagão de outubro, elevando o **PDR Global para ~93,2%** e o **PDR Ativo (descontando as 4 manutenções/quedas elétricas globais do prédio $> 12\text{h}$) para 99,0%**.

---

## 2. Coortes Experimentais e Dispositivos Selecionados (14 Dispositivos)

Os dispositivos extraídos foram organizados em **4 Coortes Experimentais** que cobrem todos os cenários exigidos pela IC (supressão temporal, agregação espacial via *Cluster Head*, inércia de solo vs. ar, regime estável e análise de falhas):

### Coorte 1: `Externo_Cluster` (Ambiente 4 — `Externo`)
- **Dispositivos (9 nós):**
  - Operação contínua (Mar–Set, ~53.650 amostras cada, PDR Global 93,1%, PDR Ativo 99,0%): `86809` (`1006EXT-TEMPHUM-01`), `86811` (`1006EXT-TEMPHUM-03`), `86813` (`1006EXT-TEMPHUM-05`), `86814` (`1008EXT-TEMPHUM-01`), `86784` (`1008EXT-TEMPHUM-03`), `86785` (`1008EXT-TEMPHUM-04`), `86783` (`1008EXT-TEMPHUM-05`), `46` (`1008EXT-TEMPHUM-06`).
  - Caso real de *Node Death* (falha permanente em 15/05/2026 após 20.479 amostras, PDR Global 94,2%, PDR Ativo 96,8%): `86812` (`1006EXT-TEMPHUM-04`).
- **Sensores extraídos:** `1` (`temperatura` em `C`) e `2` (`umidade` em `%`).
- **Papel Científico:** Fisicamente dispostos em linha (~1 m de distância entre si) na área externa, próximos às condensadoras de ar-condicionado. Representam um **transecto/talhão virtual** sujeito ao ciclo solar diurno/noturno real ($11,2^\circ\text{C}$ a $39,9^\circ\text{C}$ e $17,7\%$ a $100\%$) e a perturbações térmicas altamente localizadas (quando uma condensadora liga sobre parte da fila). É o cenário ideal para validar os 4 algoritmos temporais e a detecção de discrepância espacial do **Cluster Head (Seção 3.3)**.

### Coorte 2: `Agricola_Solo` (Ambiente 4 — `Externo`)
- **Dispositivo (1 nó multi-sensor):** `86817` (`TCC MESSIAS`).
- **Sensores extraídos (5 grandezas, ~22.650 a 23.058 amostras cada, PDR Ativo 96,0%–96,7%):**
  - `1`: `temperatura` do ar (`10,57 °C` a `32,48 °C`, média `20,31 °C`)
  - `2`: `umidade` relativa do ar (`31,89 %` a `100,00 %`, média `77,07 %`)
  - `13`: `umidade_solo` — Sensor Capacitivo V2 (`0,00 %` a `100,00 %`, 0 `NaN`s)
  - `14`: `temperatura_solo` (`13,54 °C` a `25,36 °C`, média `18,66 °C`)
  - `15`: `fluxo` — Sensor de vazão hídrica (`0,00` a `7,73 L/min`)
- **Papel Científico:** Estação agrometeorológica completa no testbed. Permite contrastar diretamente a taxa de compressão ($TR\%$) e o erro de reconstrução ($\text{MAE}/\text{RMSE}$) entre variáveis atmosféricas rápidas (temperatura/umidade do ar) e variáveis edáficas de alta inércia térmica e hídrica (temperatura e umidade do solo), enriquecendo a discussão agrícola para cafeicultura (**Entregável E6**).

### Coorte 3: `Indoor_Baseline` (Ambiente 1 — `Lab 1006`)
- **Dispositivos (2 nós):** `1` (`TEMP2`) e `86782` (`TEMP4`) — ~53.665 amostras por sensor, PDR Global 93,2%, PDR Ativo 99,0%, 0 `NaN`s.
- **Sensores extraídos:** `1` (`temperatura`), `2` (`umidade`) e `10` (`luminosidade` em `lux_adc`, variando de `0` na madrugada a `~3422` com iluminação/sol).
- **Papel Científico:** Ambiente interno climatizado e termicamente estável ($18,1^\circ\text{C}$ a $29,6^\circ\text{C}$). Serve como **Baseline de Regime Estável (Seção 3.4.1)** para demonstrar o limite superior de economia de energia ($TR\% > 90\%$) durante períodos noturnos/finais de semana e validar o comportamento dos algoritmos sob transientes de ar-condicionado e degraus de iluminação.

### Coorte 4: `Cluster_Server` (Ambiente 3 — `Cluster 1006`)
- **Dispositivos (2 nós):** `86794` (`1006CLUSTER-TEMPHUM-01`, 53.665 amostras) e `86795` (`1006CLUSTER-TEMPHUM-02`, 45.738 amostras).
- **Sensores extraídos:** `1` (`temperatura`) e `2` (`umidade`).
- **Papel Científico:** Sala de servidores refrigerada onde o nó `86795` registrou um evento real de anomalia térmica extrema (atingindo **$51,2^\circ\text{C}$** contra a média de $19,8^\circ\text{C}$). Permite avaliar a **Latência de Alerta ($\Delta t_{\text{alerta}}$)** em um surto térmico real do banco, complementando os testes com injeção de eventos climáticos sintéticos (geada/frente fria).

---

## 3. Estrutura Exata dos 4 Arquivos CSV Gerados (Pasta `dataset_koala_e2/`)

Qualquer script das etapas **E3 (Gráficos)**, **E4 (Algoritmos)** e **E5 (Tabelas de QoS)** deve ler diretamente os arquivos abaixo já gerados localmente:

### 3.1. `dataset_koala_e2/koala_dataset_mestre_5min.csv`
- **Volume:** `1.534.142` linhas (formato longo padronizado, ordenado por `timestamp`, sem `NaN`s e filtrado de *outliers*).
- **Colunas:**
  - `timestamp` (`str`, ex: `2026-03-01T00:00:00`)
  - `id_dispositivo` (`int`, ex: `86809`)
  - `nome_dispositivo` (`str`, ex: `1006EXT-TEMPHUM-01`)
  - `ambiente` (`str`: `Externo`, `1006`, `Cluster 1006`)
  - `coorte` (`str`: `Externo_Cluster`, `Agricola_Solo`, `Indoor_Baseline`, `Cluster_Server`)
  - `id_sensor` (`int`: `1, 2, 10, 13, 14, 15`)
  - `sensor` (`str`: `temperatura`, `umidade`, `luminosidade`, `umidade_solo`, `temperatura_solo`, `fluxo`)
  - `valor` (`float`: leitura média `avg_value` nos 5 min)
  - `valor_min` (`float`: leitura mínima `min_value` nos 5 min)
  - `valor_max` (`float`: leitura máxima `max_value` nos 5 min)
  - `unidade` (`str`: `C`, `%`, `lux_adc`, `L_min`)

### 3.2. `dataset_koala_e2/koala_cluster_externo_wide_5min.csv`
- **Volume:** `107.363` linhas (formato largo/pivotado, exclusivo da coorte `Externo_Cluster`).
- **Colunas:** `timestamp`, `sensor`, `unidade`, `1006EXT-TEMPHUM-01`, `1006EXT-TEMPHUM-03`, `1006EXT-TEMPHUM-04`, `1006EXT-TEMPHUM-05`, `1008EXT-TEMPHUM-01`, `1008EXT-TEMPHUM-03`, `1008EXT-TEMPHUM-04`, `1008EXT-TEMPHUM-05`, `1008EXT-TEMPHUM-06`.
- **Uso direto:** Simulação vetorizada do **Cluster Head (Seção 3.3)** calculando mediana espacial $M_t$ e desvio máximo $\Delta_{\max}$ linha a linha.

### 3.3. `dataset_koala_e2/koala_auditoria_qos_bruto.csv`
- **Volume:** `33` linhas (1 linha para cada par `[id_dispositivo, id_sensor]` extraído).
- **Colunas:** `id_dispositivo`, `nome_dispositivo`, `ambiente`, `coorte`, `id_sensor`, `sensor`, `inicio_serie`, `fim_serie`, `blocos_retornados_api`, `blocos_nan_hardware`, `blocos_outlier_fisico`, `amostras_validas_unicas`, `amostras_esperadas_5min`, `pdr_empirico_global_pct`, `pdr_sem_apagao_servidor_pct`, `intervalo_medio_min`, `jitter_std_min`, `qtd_lacunas_maior_15min`, `mttr_medio_lacunas_min`, `maior_lacuna_min`.
- **Nota sobre os Apagões Globais do Servidor:** A análise temporal provou que as 4 grandes lacunas simultâneas (`08/03` por 16h, `17/05` por 50h, `25/07` por 110h e `29/08` por 108h) ocorreram no coletor central do laboratório (afetando simultaneamente nós externos e internos). Por isso, a tabela reporta tanto a disponibilidade bruta (`pdr_empirico_global_pct` $\approx 93,2\%$) quanto a taxa de entrega intrínseca dos nós com o servidor ativo (`pdr_sem_apagao_servidor_pct` $\approx 99,0\%$).

### 3.4. `dataset_koala_e2/koala_dicionario_dispositivos.csv`
- **Colunas:** `id`, `nome`, `id_env`, `ambiente`, `coorte`, `sensores`.