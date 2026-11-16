#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENTREGÁVEL E4 — SCRIPT 2: APLICAÇÃO NOS COORTES ESPECÍFICOS (AR vs. SOLO E REGIME INDOOR)
1. Coorte 2 (Agricola_Solo - Nó 86817 TCC MESSIAS):
   Compara diretamente Temperatura/Umidade do Ar vs. Temperatura/Umidade do Solo,
   avaliando o impacto da inércia térmica e hídrica edáfica na compressão (TR%) e erro (RMSE).
2. Coorte 3 (Indoor_Baseline - Nós 1 e 86782 Lab 1006):
   Demonstra o limite superior assintótico de economia de transmissões (TR% -> ~91.6%)
   em regime climatizado estável.
3. Tabela síntese multi-coorte (Coortes 1, 2, 3 e 4) com os hiperparâmetros congelados.
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
    slice_window,
    eval_metrics,
    sim_alg1,
    sim_alg2,
    sim_alg3,
    sim_alg4,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "resultados_e4_coortes"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Configuração para grandezas do solo (herdam os mesmos hiperparâmetros congelados de temp/umidade)
PARAMS_SOLO = {
    "temperatura_solo": PARAMS_OTIMOS["temperatura"],
    "umidade_solo": PARAMS_OTIMOS["umidade"],
}


def avaliar_serie_completa(df: pd.DataFrame, coorte: str, device_id: int, nome_disp: str, sensor: str, cfg: dict) -> list[dict]:
    unid = cfg["unidade"]
    eps = cfg["eps"]
    p_alg3 = cfg["alg3"]
    p_alg4 = cfg["alg4"]
    y_true = df["valor"].values

    yh1_15, tx1_15 = sim_alg1(df, 15.0)
    yh1_30, tx1_30 = sim_alg1(df, 30.0)
    yh1_60, tx1_60 = sim_alg1(df, 60.0)
    yh2, tx2 = sim_alg2(df, delta=eps, thb_min=THB_MIN)
    yh3, tx3, _ = sim_alg3(df, **p_alg3)
    yh4, tx4 = sim_alg4(df, eps=eps, thb_min=THB_MIN, **p_alg4)

    runs = [
        ("Alg 1 (W=15m)", yh1_15, tx1_15),
        ("Alg 1 (W=30m)", yh1_30, tx1_30),
        ("Alg 1 (W=60m)", yh1_60, tx1_60),
        (f"Alg 2 (δ={eps}{unid}, Thb=60m)", yh2, tx2),
        (f"Alg 3 (σ=[{p_alg3['sigma_low']},{p_alg3['sigma_high']}], W=[5,60]m)", yh3, tx3),
        (f"Alg 4 (ε={eps}{unid}, Thb=60m, φ={p_alg4['damping_phi']})", yh4, tx4),
    ]

    results = []
    for label, yh, tx in runs:
        m = eval_metrics(y_true, yh, tx, label)
        results.append({
            "Coorte": coorte,
            "Dispositivo": f"{device_id} ({nome_disp})",
            "Sensor": sensor,
            "Unidade": unid,
            **m,
        })
    return results


def analisar_ar_vs_solo():
    """
    Avalia o nó 86817 (TCC MESSIAS) nas 4 grandezas (temperatura, temperatura_solo, umidade, umidade_solo)
    no limiar nominal (0.5°C / 2.0%) e também num limiar de alta precisão edáfica (0.2°C / 1.0%)
    onde as rampas monotônicas lentas do solo destacam a extrapolação linear do Alg 4.
    """
    device_id = 86817
    nome_disp = "TCC MESSIAS"
    sensores_cfg = {
        "temperatura": PARAMS_OTIMOS["temperatura"],
        "temperatura_solo": PARAMS_SOLO["temperatura_solo"],
        "umidade": PARAMS_OTIMOS["umidade"],
        "umidade_solo": PARAMS_SOLO["umidade_solo"],
    }

    rows_ar_solo = []
    series_dict = {}

    for sensor, cfg in sensores_cfg.items():
        df_s = load_series(CSV_PATH, device_id, sensor)
        series_dict[sensor] = df_s
        rows_ar_solo.extend(avaliar_serie_completa(df_s, "Agricola_Solo", device_id, nome_disp, sensor, cfg))

        # Avalia também limiar estrito de alta precisão no solo e no ar (0.2°C e 1.0%) para comparar Alg 2 vs Alg 4
        eps_fino = 0.2 if "temperatura" in sensor else 1.0
        unid = cfg["unidade"]
        y_true = df_s["valor"].values
        yh2_f, tx2_f = sim_alg2(df_s, delta=eps_fino, thb_min=THB_MIN)
        yh4_f, tx4_f = sim_alg4(df_s, eps=eps_fino, thb_min=THB_MIN, **cfg["alg4"])
        for lbl, yh, tx in [
            (f"Alg 2 Alta Precisão (δ={eps_fino}{unid}, Thb=60m)", yh2_f, tx2_f),
            (f"Alg 4 Alta Precisão (ε={eps_fino}{unid}, Thb=60m)", yh4_f, tx4_f),
        ]:
            m = eval_metrics(y_true, yh, tx, lbl)
            rows_ar_solo.append({
                "Coorte": "Agricola_Solo",
                "Dispositivo": f"{device_id} ({nome_disp})",
                "Sensor": sensor,
                "Unidade": unid,
                **m,
            })

    df_ar_solo = pd.DataFrame(rows_ar_solo)
    df_ar_solo.to_csv(OUT_DIR / "tabela_coorte2_ar_vs_solo_86817.csv", index=False)

    # Plot de 7 dias (ex: 01/08/2026 a 08/08/2026) contrastando reconstrução Ar vs Solo (Alg 2 e Alg 4)
    z_start, z_end = "2026-08-01T00:00:00", "2026-08-08T00:00:00"
    fig, axes = plt.subplots(2, 2, figsize=(14, 8.5), sharex=True, dpi=150)

    paineis = [
        (axes[0, 0], "temperatura", "Temperatura do Ar (°C) — Alta Volatilidade Diurna", PARAMS_OTIMOS["temperatura"]),
        (axes[0, 1], "temperatura_solo", "Temperatura do Solo (°C) — Alta Inércia Térmica Edáfica", PARAMS_SOLO["temperatura_solo"]),
        (axes[1, 0], "umidade", "Umidade Relativa do Ar (%) — Transientes Rápidos", PARAMS_OTIMOS["umidade"]),
        (axes[1, 1], "umidade_solo", "Umidade do Solo (%) — Estabilidade Hídrica", PARAMS_SOLO["umidade_solo"]),
    ]

    for ax, sensor, titulo, cfg in paineis:
        df_z = slice_window(series_dict[sensor], z_start, z_end)
        ts = df_z["timestamp"]
        yt = df_z["valor"].values
        eps = cfg["eps"]
        unid = cfg["unidade"]

        yh2, tx2 = sim_alg2(df_z, delta=eps, thb_min=THB_MIN)
        yh4, tx4 = sim_alg4(df_z, eps=eps, thb_min=THB_MIN, **cfg["alg4"])
        tr2 = (1.0 - np.sum(tx2) / len(yt)) * 100.0
        tr4 = (1.0 - np.sum(tx4) / len(yt)) * 100.0
        rmse2 = float(np.sqrt(np.mean((yt - yh2) ** 2)))
        rmse4 = float(np.sqrt(np.mean((yt - yh4) ** 2)))

        ax.plot(ts, yt, color="#2c3e50", alpha=0.45, linewidth=1.4, label="Série Base (5 min)")
        ax.step(ts, yh2, where="post", color="#1f77b4", linewidth=1.4, label=f"Alg 2 (TR={tr2:.1f}%, RMSE={rmse2:.3f}{unid})")
        ax.plot(ts, yh4, color="#2ca02c", linestyle="--", linewidth=1.5, label=f"Alg 4 (TR={tr4:.1f}%, RMSE={rmse4:.3f}{unid})")
        ax.scatter(ts[tx2], yt[tx2], color="#1f77b4", s=14, alpha=0.8, zorder=4, label=f"Envios Alg 2 (N={int(np.sum(tx2))})")
        ax.set_title(titulo, fontsize=10.5, fontweight="bold")
        ax.set_ylabel(f"Valor ({unid})")
        ax.grid(True, linestyle="--", alpha=0.35)
        ax.legend(loc="best", fontsize=8.2, frameon=True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))

    axes[1, 0].set_xlabel("Data (01/08/2026 a 08/08/2026)")
    axes[1, 1].set_xlabel("Data (01/08/2026 a 08/08/2026)")
    fig.suptitle(
        "Coorte 2 (TCC MESSIAS - Nó 86817): Contraste de Compressão e Reconstrução entre Atmosfera (Ar) e Solo",
        fontsize=12.5,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(OUT_DIR / "coorte2_reconstrucao_ar_vs_solo_86817.png")
    plt.close(fig)

    # Gráfico de barras: Comparação TR% Ar vs Solo (Limiar Padrão vs Limiar de Alta Precisão)
    fig2, (ax_tr, ax_rmse) = plt.subplots(1, 2, figsize=(12.5, 5.2), dpi=150)
    labels_cat = ["Temp. Ar\n(0.5°C)", "Temp. Solo\n(0.5°C)", "Temp. Solo\n(0.2°C Fino)", "Umid. Ar\n(2.0%)", "Umid. Solo\n(2.0%)"]

    def get_metric(sens, alg_prefix, col):
        sub = df_ar_solo[(df_ar_solo["Sensor"] == sens) & (df_ar_solo["Algoritmo"].str.startswith(alg_prefix))]
        return float(sub[col].iloc[0])

    tr_alg2 = [
        get_metric("temperatura", "Alg 2 (δ=0.5", "TR_pct"),
        get_metric("temperatura_solo", "Alg 2 (δ=0.5", "TR_pct"),
        get_metric("temperatura_solo", "Alg 2 Alta Precisão (δ=0.2", "TR_pct"),
        get_metric("umidade", "Alg 2 (δ=2.0", "TR_pct"),
        get_metric("umidade_solo", "Alg 2 (δ=2.0", "TR_pct"),
    ]
    tr_alg4 = [
        get_metric("temperatura", "Alg 4 (ε=0.5", "TR_pct"),
        get_metric("temperatura_solo", "Alg 4 (ε=0.5", "TR_pct"),
        get_metric("temperatura_solo", "Alg 4 Alta Precisão (ε=0.2", "TR_pct"),
        get_metric("umidade", "Alg 4 (ε=2.0", "TR_pct"),
        get_metric("umidade_solo", "Alg 4 (ε=2.0", "TR_pct"),
    ]

    x = np.arange(len(labels_cat))
    width = 0.35
    b1 = ax_tr.bar(x - width / 2, tr_alg2, width, label="Alg 2: Limiar Estático Híbrido", color="#1f77b4")
    b2 = ax_tr.bar(x + width / 2, tr_alg4, width, label="Alg 4: Predição Dupla EWMA", color="#2ca02c")
    ax_tr.axhline(91.65, color="#d62728", linestyle="--", linewidth=1.2, label="Teto Assintótico (Heartbeat Thb=60m: ~91.7%)")
    ax_tr.set_ylabel("Taxa de Redução de Transmissões — TR (%)")
    ax_tr.set_title("Economia de Rádio (TR%): Variáveis Rápidas do Ar vs. Inércia do Solo", fontweight="bold")
    ax_tr.set_xticks(x)
    ax_tr.set_xticklabels(labels_cat)
    ax_tr.set_ylim(50, 100)
    ax_tr.grid(True, axis="y", linestyle="--", alpha=0.35)
    ax_tr.legend(loc="lower right", fontsize=8.5)

    for bars in [b1, b2]:
        for bar in bars:
            h = bar.get_height()
            ax_tr.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                           textcoords="offset points", ha="center", va="bottom", fontsize=8)

    rmse_alg2 = [
        get_metric("temperatura", "Alg 2 (δ=0.5", "RMSE"),
        get_metric("temperatura_solo", "Alg 2 (δ=0.5", "RMSE"),
        get_metric("temperatura_solo", "Alg 2 Alta Precisão (δ=0.2", "RMSE"),
        get_metric("umidade", "Alg 2 (δ=2.0", "RMSE"),
        get_metric("umidade_solo", "Alg 2 (δ=2.0", "RMSE"),
    ]
    rmse_alg4 = [
        get_metric("temperatura", "Alg 4 (ε=0.5", "RMSE"),
        get_metric("temperatura_solo", "Alg 4 (ε=0.5", "RMSE"),
        get_metric("temperatura_solo", "Alg 4 Alta Precisão (ε=0.2", "RMSE"),
        get_metric("umidade", "Alg 4 (ε=2.0", "RMSE"),
        get_metric("umidade_solo", "Alg 4 (ε=2.0", "RMSE"),
    ]

    b3 = ax_rmse.bar(x - width / 2, rmse_alg2, width, label="Alg 2: Limiar Estático Híbrido", color="#1f77b4")
    b4 = ax_rmse.bar(x + width / 2, rmse_alg4, width, label="Alg 4: Predição Dupla EWMA", color="#2ca02c")
    ax_rmse.set_ylabel("Erro de Reconstrução — RMSE (°C ou %)")
    ax_rmse.set_title("Fidelidade de Reconstrução (RMSE) no Servidor", fontweight="bold")
    ax_rmse.set_xticks(x)
    ax_rmse.set_xticklabels(labels_cat)
    ax_rmse.grid(True, axis="y", linestyle="--", alpha=0.35)
    ax_rmse.legend(loc="upper left", fontsize=8.5)

    for bars in [b3, b4]:
        for bar in bars:
            h = bar.get_height()
            ax_rmse.annotate(f"{h:.3f}", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                             textcoords="offset points", ha="center", va="bottom", fontsize=8)

    fig2.tight_layout()
    fig2.savefig(OUT_DIR / "coorte2_barras_ar_vs_solo_86817.png")
    plt.close(fig2)

    return df_ar_solo


def analisar_todos_coortes():
    """
    Aplica os algoritmos nos nós representativos das 4 Coortes ao longo de toda a série histórica (200 dias)
    para consolidar o comportamento em cada regime operacional.
    """
    alvos = [
        ("Externo_Cluster", 86811, "1006EXT-TEMPHUM-03"),
        ("Externo_Cluster", 86809, "1006EXT-TEMPHUM-01"),
        ("Agricola_Solo", 86817, "TCC MESSIAS"),
        ("Indoor_Baseline", 1, "TEMP2"),
        ("Indoor_Baseline", 86782, "TEMP4"),
        ("Cluster_Server", 86794, "1006CLUSTER-TEMPHUM-01"),
        ("Cluster_Server", 86795, "1006CLUSTER-TEMPHUM-02"),
    ]

    all_rows = []
    for coorte, dev_id, nome in alvos:
        for sensor in ["temperatura", "umidade"]:
            df_s = load_series(CSV_PATH, dev_id, sensor)
            if len(df_s) == 0:
                continue
            cfg = PARAMS_OTIMOS[sensor]
            all_rows.extend(avaliar_serie_completa(df_s, coorte, dev_id, nome, sensor, cfg))

    df_all = pd.DataFrame(all_rows)
    df_all.to_csv(OUT_DIR / "tabela_consolidada_todos_coortes_200dias.csv", index=False)

    # Filtra Alg 2 e Alg 4 para plotar comparação direta entre os Coortes (Temperatura e Umidade)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), dpi=150)
    nós_ref = [
        ("86811 (1006EXT-TEMPHUM-03)", "Coorte 1:\nExterno (86811)"),
        ("86817 (TCC MESSIAS)", "Coorte 2:\nAgrícola Ar (86817)"),
        ("1 (TEMP2)", "Coorte 3:\nIndoor Lab (1)"),
        ("86782 (TEMP4)", "Coorte 3:\nIndoor Lab (86782)"),
        ("86795 (1006CLUSTER-TEMPHUM-02)", "Coorte 4:\nServer (86795)"),
    ]

    for ax, sensor, unid in [(axes[0], "temperatura", "°C"), (axes[1], "umidade", "%")]:
        sub_s = df_all[df_all["Sensor"] == sensor]
        tr_w15, tr_a2, tr_a4 = [], [], []
        labels_x = []
        for disp_key, lbl_x in nós_ref:
            s_d = sub_s[sub_s["Dispositivo"] == disp_key]
            tr_w15.append(float(s_d[s_d["Algoritmo"] == "Alg 1 (W=15m)"]["TR_pct"].iloc[0]))
            tr_a2.append(float(s_d[s_d["Algoritmo"].str.startswith("Alg 2")]["TR_pct"].iloc[0]))
            tr_a4.append(float(s_d[s_d["Algoritmo"].str.startswith("Alg 4")]["TR_pct"].iloc[0]))
            labels_x.append(lbl_x)

        x = np.arange(len(labels_x))
        w = 0.26
        ax.bar(x - w, tr_w15, w, label="Alg 1 (Janela Fixa W=15m)", color="#7f7f7f")
        b2 = ax.bar(x, tr_a2, w, label="Alg 2 (Limiar Estático Híbrido)", color="#1f77b4")
        b4 = ax.bar(x + w, tr_a4, w, label="Alg 4 (Predição Dupla EWMA)", color="#2ca02c")
        ax.axhline(91.65, color="#d62728", linestyle="--", linewidth=1.2, label="Limite Assintótico (Thb=60m: 91.65%)")
        ax.set_xticks(x)
        ax.set_xticklabels(labels_x, fontsize=8.8)
        ax.set_ylim(55, 98)
        ax.set_ylabel("Taxa de Redução de Transmissões — TR (%)")
        ax.set_title(f"Desempenho por Coorte Experimental — {sensor.capitalize()} ({unid})", fontweight="bold")
        ax.grid(True, axis="y", linestyle="--", alpha=0.35)
        ax.legend(loc="lower right", fontsize=8.2)

        for bars in [b2, b4]:
            for bar in bars:
                h = bar.get_height()
                ax.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 2),
                            textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

    fig.suptitle("Comparação Multi-Coorte nos 200 Dias (Parâmetros Congelados da Fase 1)", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "comparacao_multi_coorte_tr_200dias.png")
    plt.close(fig)

    return df_all


def main():
    print("1. Processando Coorte 2 (Agricola_Solo - Ar vs. Solo no TCC MESSIAS 86817)...")
    df_ar_solo = analisar_ar_vs_solo()
    print("\n=== RESULTADOS COORTE 2: AR VS. SOLO (NÓ 86817 - TCC MESSIAS) ===")
    cols_show = ["Sensor", "Algoritmo", "Amostras", "Pacotes", "TR_pct", "MAE", "RMSE", "ErroMax"]
    print(df_ar_solo[cols_show].to_string(index=False))

    print("\n2. Processando comparação consolidada entre todos os Coortes (1, 2, 3 e 4)...")
    df_all = analisar_todos_coortes()
    sub_resumo = df_all[df_all["Algoritmo"].str.startswith(("Alg 2", "Alg 4"))]
    print("\n=== SÍNTESE MULTI-COORTE (ALG 2 E ALG 4 NOS 200 DIAS) ===")
    print(sub_resumo[["Coorte", "Dispositivo", "Sensor", "Algoritmo", "Pacotes", "TR_pct", "MAE", "RMSE", "ErroMax"]].to_string(index=False))
    print(f"\nArquivos salvos em: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
