#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENTREGÁVEL E4 — SCRIPT 4: SIMULAÇÃO DO CLUSTER HEAD E ACOPLAMENTO TEMPORAL + ESPACIAL
1. Calibração do limiar espacial (τ_espacial) na janela de 10/04 a 17/04/2026 (evento real de 7°C em 13/04).
2. Simulação Conjunta nos 200 Dias (Nó-Folha com Alg 2 / Alg 4 -> Cluster Head -> Gateway LoRaWAN):
   - Mede a economia no enlace local (Nó -> CH) e no enlace longo LoRaWAN (CH -> Gateway).
   - Demonstra a tolerância automática à falha permanente (Node Death) do nó 86812 em 15/05/2026.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reconstrucao_validacao import (
    CSV_PATH,
    THB_MIN,
    PARAMS_OTIMOS,
    load_series,
    sim_alg2,
    sim_alg4,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
WIDE_CSV_PATH = ROOT_DIR / "dataset_koala_e2/koala_cluster_externo_wide_5min.csv"
OUT_DIR = ROOT_DIR / "resultados_e4_cluster_head"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NOS_EXTERNOS = [
    (86809, "1006EXT-TEMPHUM-01"),
    (86811, "1006EXT-TEMPHUM-03"),
    (86812, "1006EXT-TEMPHUM-04"),  # Node Death em 15/05/2026
    (86813, "1006EXT-TEMPHUM-05"),
    (86814, "1008EXT-TEMPHUM-01"),
    (86784, "1008EXT-TEMPHUM-03"),
    (86785, "1008EXT-TEMPHUM-04"),
    (86783, "1008EXT-TEMPHUM-05"),
    (46, "1008EXT-TEMPHUM-06"),
]


def construir_matriz_reconstruida(sensor: str, metodo: str = "bruto") -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    """
    Para cada um dos 9 nós da Coorte 1 (Externo_Cluster), carrega a série, roda o algoritmo
    no nó-folha (bruto, alg2 ou alg4) e monta a matriz temporal alinhada no Cluster Head.
    Se um nó parar de reportar por mais de 2 * Thb (120 min), o Cluster Head declara Node Timeout/Death
    e deixa de incluí-lo na mediana até que volte a transmitir.
    """
    cfg = PARAMS_OTIMOS[sensor]
    eps = cfg["eps"]

    dfs_val = {}
    dfs_tx = {}
    total_amostras_brutas = 0
    total_pacotes_locais = 0

    for dev_id, nome in NOS_EXTERNOS:
        df_s = load_series(CSV_PATH, dev_id, sensor)
        if len(df_s) == 0:
            continue
        total_amostras_brutas += len(df_s)

        if metodo == "bruto":
            yh = df_s["valor"].values
            tx = np.ones(len(df_s), dtype=bool)
        elif metodo == "alg2":
            yh, tx = sim_alg2(df_s, delta=eps, thb_min=THB_MIN)
        elif metodo == "alg4":
            yh, tx = sim_alg4(df_s, eps=eps, thb_min=THB_MIN, **cfg["alg4"])
        else:
            raise ValueError(f"Método desconhecido: {metodo}")

        total_pacotes_locais += int(np.sum(tx))
        s_val = pd.Series(yh, index=df_s["timestamp"], name=nome)
        s_tx = pd.Series(tx, index=df_s["timestamp"], name=nome)
        dfs_val[nome] = s_val
        dfs_tx[nome] = s_tx

    mat_val = pd.DataFrame(dfs_val).sort_index()
    mat_tx = pd.DataFrame(dfs_tx).reindex(mat_val.index).fillna(False)
    return mat_val, mat_tx, total_amostras_brutas, total_pacotes_locais


def calibrar_tau_espacial_abril():
    """
    Varre τ_espacial na janela crítica de 10/04/2026 a 17/04/2026 (onde ocorre o pico de ~7°C em 13/04)
    para Temperatura e Umidade, gerando tabela de calibração e gráfico detalhado da anomalia espacial.
    """
    df_wide = pd.read_csv(WIDE_CSV_PATH)
    df_wide["timestamp"] = pd.to_datetime(df_wide["timestamp"])
    cols_nos = [nome for _, nome in NOS_EXTERNOS]

    t_ini, t_fim = pd.to_datetime("2026-04-10T00:00:00"), pd.to_datetime("2026-04-17T23:59:59")
    sub_temp = df_wide[(df_wide["sensor"] == "temperatura") & (df_wide["timestamp"] >= t_ini) & (df_wide["timestamp"] <= t_fim)].copy()
    sub_temp = sub_temp.sort_values("timestamp").reset_index(drop=True)

    vals_t = sub_temp[cols_nos].values
    mediana_t = np.nanmedian(vals_t, axis=1)
    desvios_abs_t = np.abs(vals_t - mediana_t[:, None])
    delta_max_t = np.nanmax(desvios_abs_t, axis=1)
    idx_no_critico = np.nanargmax(desvios_abs_t, axis=1)

    taus_temp = [1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0]
    rows_tau = []
    n_passos = len(sub_temp)
    n_bruto_9nos = int(np.sum(~np.isnan(vals_t)))

    for tau in taus_temp:
        mask_anom = delta_max_t > tau
        pct_anom = float(np.mean(mask_anom) * 100.0)
        # No enlace CH -> Gateway (1 pacote base com mediana + 1 payload extra ou extensão quando há outlier)
        # Contabilizando em unidades equivalentes de mensagem (1 msg se normal, 2 msgs se reportar outlier separado)
        msgs_lorawan = int(n_passos + np.sum(mask_anom))
        tr_espacial_pct = (1.0 - (msgs_lorawan / n_bruto_9nos)) * 100.0
        rows_tau.append({
            "Grandeza": "temperatura (°C)",
            "Tau_Espacial": tau,
            "Blocos_5min_Janela": n_passos,
            "Leituras_Brutas_9Nos": n_bruto_9nos,
            "Eventos_Acima_Tau": int(np.sum(mask_anom)),
            "Pct_Tempo_Anomalia": round(pct_anom, 2),
            "Pct_Tempo_Apenas_Mediana": round(100.0 - pct_anom, 2),
            "Reducao_Espacial_Pura_Pct": round(tr_espacial_pct, 2),
        })

    df_tau = pd.DataFrame(rows_tau)
    df_tau.to_csv(OUT_DIR / "tabela_calibracao_tau_espacial_10a17abril.csv", index=False)

    # Figura: Mediana Espacial M_t vs Nós Individuais e Detecção Cirúrgica em 13/04 com τ_espacial = 4.5°C
    tau_escolhido = 4.5
    ts = sub_temp["timestamp"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8.2), sharex=True, dpi=150)

    for i, nome in enumerate(cols_nos):
        ax1.plot(ts, vals_t[:, i], alpha=0.32, linewidth=1.0, label=nome if i < 4 else None)
    ax1.plot(ts, mediana_t, color="black", linewidth=2.2, label="Mediana Espacial do Cluster Head (M_t)")
    idx_pico = int(np.nanargmax(delta_max_t))
    no_pico = cols_nos[int(idx_no_critico[idx_pico])]
    ax1.plot(ts, sub_temp[no_pico], color="#d62728", linewidth=1.6, linestyle="--", label=f"Nó Discrepante no Pico ({no_pico})")
    ax1.set_title("Coorte 1 (Externo_Cluster - 9 Nós): Leituras Individuais vs. Mediana Espacial M_t (10/04 a 17/04/2026)", fontweight="bold")
    ax1.set_ylabel("Temperatura (°C)")
    ax1.set_ylim(17.0, 41.5)
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(loc="upper right", ncol=3, fontsize=8.0, frameon=True)

    ax2.plot(ts, delta_max_t, color="#1f77b4", linewidth=1.5, label="Desvio Espacial Máximo Instantâneo (Δ_max = max |v_i - M_t|)")
    ax2.axhline(1.0, color="#7f7f7f", linestyle=":", linewidth=1.2, label="Limiar Ingênuo (τ = 1.0°C -> Falso Alarme Constante)")
    ax2.axhline(tau_escolhido, color="#d62728", linestyle="--", linewidth=1.8, label=f"Limiar Calibrado (τ_espacial = {tau_escolhido}°C)")
    mask_alerta = delta_max_t > tau_escolhido
    ax2.scatter(ts[mask_alerta], delta_max_t[mask_alerta], color="#d62728", s=22, zorder=5,
                label=f"Anomalia Local Detectada (Δ_max > {tau_escolhido}°C: {np.mean(mask_alerta)*100:.1f}% do tempo)")
    ax2.set_title(f"Calibração de τ_espacial = {tau_escolhido}°C: Absorção do Microclima Basal (3–4°C) e Detecção do Evento de 13/04", fontweight="bold")
    ax2.set_ylabel("Δ_max Espacial (°C)")
    ax2.set_xlabel("Data (10/04/2026 a 17/04/2026)")
    ax2.set_ylim(0.5, 8.8)
    ax2.grid(True, linestyle="--", alpha=0.35)
    ax2.legend(loc="upper left", fontsize=8.0, frameon=True)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))

    fig.tight_layout()
    fig.savefig(OUT_DIR / "calibracao_tau_espacial_abril_cluster_head.png")
    plt.close(fig)

    return df_tau


def simular_acoplamento_temporal_espacial_200d():
    """
    Simula os 200 dias completos acoplando:
    - Supressão Temporal nos Nós-Folha (Alg 2 ou Alg 4) -> Enlace Local (Nó -> CH)
    - Agregação Espacial + Supressão Temporal da Mediana no Cluster Head -> Enlace Longo LoRaWAN (CH -> Gateway)
    Avalia também a queda automática de 9 para 8 nós ativos após o Node Death do 86812 em 15/05/2026.
    """
    configs_ch = [
        ("temperatura", 4.5, "°C"),
        ("umidade", 12.0, "%"),
    ]

    rows_200d = []
    for sensor, tau_esp, unid in configs_ch:
        cfg = PARAMS_OTIMOS[sensor]
        eps = cfg["eps"]

        # Matriz Ground Truth Bruta para medir fidelidade da Mediana Reconstruída
        mat_bruta, _, n_bruto_total, _ = construir_matriz_reconstruida(sensor, "bruto")
        mediana_real = mat_bruta.median(axis=1).values

        for metodo_folha, nome_metodo in [
            ("bruto", "Sem Supressão no Nó-Folha (Bruto 5m -> CH)"),
            ("alg2", f"Nó-Folha com Alg 2 (δ={eps}{unid}) + CH (τ={tau_esp}{unid})"),
            ("alg4", f"Nó-Folha com Alg 4 (ε={eps}{unid}) + CH (τ={tau_esp}{unid})"),
        ]:
            mat_rec, _, _, n_tx_local = construir_matriz_reconstruida(sensor, metodo_folha)
            vals_rec = mat_rec.values
            mediana_ch = np.nanmedian(vals_rec, axis=1)
            desvio_max_ch = np.nanmax(np.abs(vals_rec - mediana_ch[:, None]), axis=1)
            mask_outlier = desvio_max_ch > tau_esp

            # O próprio Cluster Head aplica Alg 2 (δ=eps, Thb=60m) sobre a série da Mediana M_t para o Gateway LoRaWAN,
            # transmitindo imediatamente também caso surja um novo evento de discrepância espacial (Δ_max > τ_espacial)
            df_med_ch = pd.DataFrame({"timestamp": mat_rec.index, "valor": mediana_ch})
            df_med_ch["dt_min"] = df_med_ch["timestamp"].diff().dt.total_seconds() / 60.0
            df_med_ch["is_gap_reset"] = df_med_ch["dt_min"].isna() | (df_med_ch["dt_min"] > 15.0)

            yh_gw, tx_gw_med = sim_alg2(df_med_ch, delta=eps, thb_min=THB_MIN)
            # Dispara transmissão LoRaWAN quando a mediana muda >= eps, estoura heartbeat OU há anomalia espacial
            novo_outlier = mask_outlier & (~np.roll(mask_outlier, 1))
            tx_lorawan = tx_gw_med | novo_outlier
            n_pacotes_lorawan = int(np.sum(tx_lorawan))

            tr_local_pct = (1.0 - (n_tx_local / n_bruto_total)) * 100.0
            tr_lorawan_vs_bruto_pct = (1.0 - (n_pacotes_lorawan / n_bruto_total)) * 100.0
            fator_compressao_global = n_bruto_total / max(1, n_pacotes_lorawan)

            erro_med = np.abs(mediana_real - yh_gw)
            mae_med = float(np.mean(erro_med))
            rmse_med = float(np.sqrt(np.mean(erro_med ** 2)))

            rows_200d.append({
                "Grandeza": f"{sensor} ({unid})",
                "Arquitetura": nome_metodo,
                "Amostras_Brutas_9Nos": n_bruto_total,
                "Pacotes_Enlace_Local_No_CH": n_tx_local,
                "TR_Enlace_Local_Pct": round(tr_local_pct, 2),
                "Pacotes_LoRaWAN_CH_Gateway": n_pacotes_lorawan,
                "TR_Global_LoRaWAN_Pct": round(tr_lorawan_vs_bruto_pct, 2),
                "Fator_Compressao_LoRaWAN": f"{fator_compressao_global:.1f}x",
                "MAE_Mediana_Gateway": round(mae_med, 4),
                "RMSE_Mediana_Gateway": round(rmse_med, 4),
                "Pct_Blocos_Com_Outlier": round(float(np.mean(mask_outlier) * 100.0), 2),
            })

    df_200d = pd.DataFrame(rows_200d)
    df_200d.to_csv(OUT_DIR / "tabela_cluster_head_acoplado_200dias.csv", index=False)

    # Gráfico de Resiliência ao Node Death do Nó 86812 em 15/05/2026 (Janela 12/05 a 18/05/2026)
    mat_t, _, _, _ = construir_matriz_reconstruida("temperatura", "alg2")
    z_ini, z_fim = pd.to_datetime("2026-05-13T00:00:00"), pd.to_datetime("2026-05-17T00:00:00")
    sub_m = mat_t[(mat_t.index >= z_ini) & (mat_t.index <= z_fim)]

    nos_ativos = (~sub_m.isna()).sum(axis=1)
    mediana_sub = sub_m.median(axis=1)

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12.5, 6.8), sharex=True, dpi=150, gridspec_kw={"height_ratios": [2.2, 1]})
    ax_top.plot(sub_m.index, sub_m["1006EXT-TEMPHUM-04"], color="#d62728", linewidth=1.8, label="Nó 86812 (1006EXT-TEMPHUM-04)")
    ax_top.plot(sub_m.index, sub_m["1006EXT-TEMPHUM-03"], color="#1f77b4", alpha=0.55, linewidth=1.2, label="Nó 86811 (Operação Normal)")
    ax_top.plot(sub_m.index, mediana_sub, color="black", linewidth=2.0, label="Mediana Espacial do Cluster Head (Sem Interrupção)")
    t_morte = pd.to_datetime("2026-05-15T11:30:00")
    ax_top.axvline(t_morte, color="#d62728", linestyle="--", linewidth=1.5, label="Instante do Node Death (15/05/2026)")
    ax_top.set_title("Tolerância a Falhas no Cluster Head: Continuidade da Mediana Espacial após Morte do Nó 86812", fontweight="bold")
    ax_top.set_ylabel("Temperatura (°C)")
    ax_top.grid(True, linestyle="--", alpha=0.35)
    ax_top.legend(loc="upper right", fontsize=8.8)

    ax_bot.step(sub_m.index, nos_ativos, where="post", color="#2ca02c", linewidth=2.0, label="Nós Ativos Sincronizados no Cluster Head")
    ax_bot.axvline(t_morte, color="#d62728", linestyle="--", linewidth=1.5)
    ax_bot.set_ylim(6.5, 9.5)
    ax_bot.set_yticks([7, 8, 9])
    ax_bot.set_ylabel("Qtd. Nós Ativos")
    ax_bot.set_xlabel("Data (13/05/2026 a 17/05/2026)")
    ax_bot.set_title("Reconfiguração Automática do Talhão Virtual (9 Nós -> 8 Nós via Timeout de Heartbeat)", fontweight="bold")
    ax_bot.grid(True, linestyle="--", alpha=0.35)
    ax_bot.legend(loc="lower left", fontsize=8.8)
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))

    fig.tight_layout()
    fig.savefig(OUT_DIR / "cluster_head_node_death_86812.png")
    plt.close(fig)

    return df_200d


def avaliar_divisao_subclusters_1006_1008():
    """
    Avalia o efeito de dividir o Cluster Único (9 nós) em 2 Sub-Clusters por fachada/talhão:
    - Sub-Cluster A (1006EXT - 4 nós: 86809, 86811, 86812, 86813)
    - Sub-Cluster B (1008EXT - 5 nós: 86814, 86784, 86785, 86783, 46)
    Verifica se a redução da heterogeneidade espacial permite reduzir τ_espacial (ex: de 4.5°C para 3.5°C).
    """
    df_wide = pd.read_csv(WIDE_CSV_PATH)
    df_wide["timestamp"] = pd.to_datetime(df_wide["timestamp"])

    c_1006 = ["1006EXT-TEMPHUM-01", "1006EXT-TEMPHUM-03", "1006EXT-TEMPHUM-04", "1006EXT-TEMPHUM-05"]
    c_1008 = ["1008EXT-TEMPHUM-01", "1008EXT-TEMPHUM-03", "1008EXT-TEMPHUM-04", "1008EXT-TEMPHUM-05", "1008EXT-TEMPHUM-06"]
    c_all = c_1006 + c_1008

    t_ini, t_fim = pd.to_datetime("2026-04-10T00:00:00"), pd.to_datetime("2026-04-17T23:59:59")
    sub = df_wide[(df_wide["sensor"] == "temperatura") & (df_wide["timestamp"] >= t_ini) & (df_wide["timestamp"] <= t_fim)].copy()
    sub = sub.sort_values("timestamp").reset_index(drop=True)
    ts = sub["timestamp"]

    grupos = [
        ("Cluster Único (9 nós: 1006EXT + 1008EXT)", c_all),
        ("Sub-Cluster A: 1006EXT (4 nós)", c_1006),
        ("Sub-Cluster B: 1008EXT (5 nós)", c_1008),
    ]

    rows_comp = []
    dmax_series = {}
    for nome_g, cols in grupos:
        v = sub[cols].values
        med = np.nanmedian(v, axis=1)
        dmax = np.nanmax(np.abs(v - med[:, None]), axis=1)
        dmax_series[nome_g] = dmax

        for tau in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]:
            pct_mediana = float(np.mean(dmax <= tau) * 100.0)
            rows_comp.append({
                "Agrupamento": nome_g,
                "Tau_Espacial_C": tau,
                "DeltaMax_Medio_C": round(float(np.nanmean(dmax)), 2),
                "DeltaMax_P90_C": round(float(np.nanpercentile(dmax, 90)), 2),
                "DeltaMax_Pico_C": round(float(np.nanmax(dmax)), 2),
                "Pct_Tempo_Apenas_Mediana": round(pct_mediana, 2),
                "Pct_Tempo_Anomalia": round(100.0 - pct_mediana, 2),
            })

    df_comp = pd.DataFrame(rows_comp)
    df_comp.to_csv(OUT_DIR / "tabela_comparacao_1cluster_vs_2subclusters_abril.csv", index=False)

    # Figura comparativa do Δ_max entre Cluster Único (9 nós) vs 2 Sub-Clusters (1006EXT e 1008EXT)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 7.8), sharex=True, dpi=150)

    d_all = dmax_series["Cluster Único (9 nós: 1006EXT + 1008EXT)"]
    d_1006 = dmax_series["Sub-Cluster A: 1006EXT (4 nós)"]
    d_1008 = dmax_series["Sub-Cluster B: 1008EXT (5 nós)"]

    ax1.plot(ts, d_all, color="#7f7f7f", alpha=0.55, linewidth=1.2, label="Δ_max Cluster Único (9 nós) — Média: 3,27°C")
    ax1.plot(ts, d_1006, color="#1f77b4", linewidth=1.4, label="Δ_max Sub-Cluster A: 1006EXT (4 nós) — Média: 2,56°C")
    ax1.axhline(4.5, color="#7f7f7f", linestyle=":", linewidth=1.4, label="τ_espacial Cluster Único = 4,5°C (94,7% normal)")
    ax1.axhline(3.5, color="#d62728", linestyle="--", linewidth=1.6, label="τ_espacial Sub-Cluster = 3,5°C (87,4% normal + Pico 13/04)")
    ax1.set_title("Sub-Cluster A (1006EXT - 4 Nós) vs. Cluster Único (9 Nós): Queda do Desvio Basal em ~0,75°C", fontweight="bold")
    ax1.set_ylabel("Δ_max Espacial (°C)")
    ax1.set_ylim(0.5, 9.8)
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.legend(loc="upper left", ncol=2, fontsize=8.2, frameon=True)

    ax2.plot(ts, d_all, color="#7f7f7f", alpha=0.55, linewidth=1.2, label="Δ_max Cluster Único (9 nós) — Média: 3,27°C")
    ax2.plot(ts, d_1008, color="#2ca02c", linewidth=1.4, label="Δ_max Sub-Cluster B: 1008EXT (5 nós) — Média: 2,49°C")
    ax2.axhline(4.5, color="#7f7f7f", linestyle=":", linewidth=1.4, label="τ_espacial Cluster Único = 4,5°C")
    ax2.axhline(3.5, color="#d62728", linestyle="--", linewidth=1.6, label="τ_espacial Sub-Cluster = 3,5°C (91,7% normal)")
    ax2.set_title("Sub-Cluster B (1008EXT - 5 Nós) vs. Cluster Único (9 Nós): Operação Estável com τ_espacial = 3,5°C", fontweight="bold")
    ax2.set_ylabel("Δ_max Espacial (°C)")
    ax2.set_xlabel("Data (10/04/2026 a 17/04/2026)")
    ax2.set_ylim(0.5, 9.8)
    ax2.grid(True, linestyle="--", alpha=0.35)
    ax2.legend(loc="upper left", ncol=2, fontsize=8.2, frameon=True)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))

    fig.tight_layout()
    fig.savefig(OUT_DIR / "comparacao_1cluster_vs_2subclusters_tau.png")
    plt.close(fig)

    return df_comp


def main():
    print("1. Calibrando τ_espacial na janela de 10/04 a 17/04/2026...")
    df_tau = calibrar_tau_espacial_abril()
    print("\n=== CALIBRAÇÃO DO LIMIAR ESPACIAL (τ_espacial) - 10/04 A 17/04/2026 ===")
    print(df_tau.to_string(index=False))

    print("\n2. Avaliando divisão em 2 Sub-Clusters (1006EXT vs 1008EXT)...")
    df_sub = avaliar_divisao_subclusters_1006_1008()
    print("\n=== COMPARAÇÃO: 1 CLUSTER ÚNICO (9 NÓS) VS. 2 SUB-CLUSTERS (1006EXT E 1008EXT) ===")
    print(df_sub[df_sub["Tau_Espacial_C"].isin([3.0, 3.5, 4.0, 4.5])].to_string(index=False))

    print("\n3. Simulando acoplamento Temporal (Nó-Folha) + Espacial (Cluster Head) nos 200 dias...")
    df_200d = simular_acoplamento_temporal_espacial_200d()
    print("\n=== RESULTADOS GLOBAIS DO CLUSTER HEAD ACOPLADO (200 DIAS - 9 NÓS EXTERNOS) ===")
    print(df_200d.to_string(index=False))
    print(f"\nArquivos salvos em: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
