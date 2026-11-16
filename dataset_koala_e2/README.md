# Dataset Mestre e Procedimento de Extração — Testbed Experimental Koala (IC FAPESP)

**Pesquisador:** Pedro Dorigatti Aureo Ferreira (ICMC/USP)  
**Orientador:** Prof. Dr. Julio Cezar Estrella (LaSDPC — ICMC/USP)  
**Projeto FAPESP:** Rede de Sensores Sem Fio na Agricultura de Precisão: Desenvolvimento de Dispositivos IoT para Coleta de Dados em Lavouras Cafeeiras do Brasil  

---

## 1. Visão Geral e Enquadramento Metodológico (Entregável E1)

Este diretório contém o pipeline de extração (`extrator_koala_e1_e2.py`) e os conjuntos de dados temporais padronizados obtidos a partir do **Testbed Experimental Controlado Koala** (LaSDPC/ICMC-USP). Os rastros reais coletados nesta infraestrutura fornecem séries temporais empíricas sujeitas a ruído de transdução, *jitter* de rede, perda de pacotes e eventos microclimáticos reais, servindo como base para a **Simulação Orientada a Rastro (*Trace-Driven Simulation*)** dos algoritmos de economia de energia, supressão temporal e agregação espacial (*Cluster Head*) projetados para redes LoRaWAN em lavouras cafeeiras.

### Parâmetros da Extração
- **Período de Coleta:** `2026-03-01 00:00:00` a `2026-09-16 23:59:59` (200 dias contínuos).
- **Resolução Temporal Base ($T_{\text{nominal}}$):** `5 minutos` (`timeBucket = "5 minutes"`).
- **Estratégia de Paginação:** Janelas deslizantes de 10 dias com sobreposição (*overlap*) de 12 horas e desduplicação por chave primária `(timestamp, id_dispositivo, id_sensor)`, prevenindo truncamentos de fuso horário (UTC/BRT) e *Read Timeouts* na API REST (`/datastream/filter`).
- **Total de Registros Válidos Consolidados:** `1.534.142` observações.

---

## 2. Arquitetura dos Arquivos e Dicionário de Dados (Entregável E2)

### 2.1. `koala_dataset_mestre_5min.csv` (Formato Longo Padronizado)
Arquivo principal contendo todas as séries temporais higienizadas (filtradas de valores `NaN` de hardware e *outliers* fora dos limites físicos de operação dos transdutores).

| Campo | Tipo | Descrição Técnica | Exemplo |
| :--- | :--- | :--- | :--- |
| `timestamp` | `string` (ISO 8601) | Instante da janela de agregação de 5 minutos ordenado cronologicamente. | `2026-03-01T00:00:00` |
| `id_dispositivo` | `int` | Identificador único do nó sensor no banco de dados do testbed. | `86809` |
| `nome_dispositivo` | `string` | Nome identificador da topologia física do nó sensor. | `1006EXT-TEMPHUM-01` |
| `ambiente` | `string` | Localização física de instalação no testbed (`Externo`, `1006`, `Cluster 1006`). | `Externo` |
| `coorte` | `string` | Papel experimental do nó (`Externo_Cluster`, `Agricola_Solo`, `Indoor_Baseline`, `Cluster_Server`). | `Externo_Cluster` |
| `id_sensor` | `int` | Identificador numérico do tipo de transdutor na API (`1, 2, 10, 13, 14, 15`). | `1` |
| `sensor` | `string` | Grandeza física medida (`temperatura`, `umidade`, `luminosidade`, `umidade_solo`, `temperatura_solo`, `fluxo`). | `temperatura` |
| `valor` | `float` | Leitura média (`avg_value`) consolidada no intervalo de 5 minutos. | `24.62` |
| `valor_min` | `float` | Leitura mínima (`min_value`) registrada dentro do intervalo de 5 minutos. | `24.50` |
| `valor_max` | `float` | Leitura máxima (`max_value`) registrada dentro do intervalo de 5 minutos. | `24.80` |
| `unidade` | `string` | Unidade física de medida (`C`, `%`, `lux_adc`, `L_min`). | `C` |

### 2.2. `koala_cluster_externo_wide_5min.csv` (Formato Pivotado / Alinhamento Espacial)
Matriz temporal alinhada pelo `timestamp` contendo os 9 nós sensores da coorte `Externo_Cluster` (`107.363` linhas). Estruturada especificamente para a validação direta do algoritmo de **Cluster Head (Agregação Espacial Multi-Sensor)** via cálculo vetorizado da mediana espacial $M_t$ e do desvio máximo intra-grupo $\Delta_{\max}$.

### 2.3. `koala_auditoria_qos_bruto.csv` (Métricas Empíricas de Rede — Bloco A / E5)
Tabela consolidada gerada antes da remoção de falhas, documentando para cada série:
- Contagem de blocos `NaN` de transdutor vs. *outliers* físicos descartados;
- **PDR Empírico Global (%)** e **PDR Ativo (%)** (descontando interrupções globais do servidor central $> 12\text{h}$);
- **Estabilidade Temporal (*Jitter*):** Intervalo médio entre pacotes e desvio padrão ($\sigma_{\Delta t}$);
- **Análise de Lacunas (*Downtime*):** Contagem de falhas ($\Delta t > 15\text{ min}$), duração média de recuperação (MTTR) e maior período inativo.

### 2.4. `koala_dicionario_dispositivos.csv`
Catálogo estático mapeando os 14 dispositivos selecionados, seus ambientes, coortes experimentais e lista de sensores acoplados.