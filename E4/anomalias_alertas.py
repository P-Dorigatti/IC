#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENTREGÁVEL E4 — SCRIPT 3: TRATAMENTO DE ANOMALIAS REAIS (CLUSTER_SERVER) E EVENTOS SINTÉTICOS
1. Anomalias Térmicas Reais na Coorte 4 (Cluster_Server - Nós 86794 e 86795):
   - Surto térmico contínuo real em 29/03/2026 (Nó 86794: salto de 20.4°C para 26.36°C em 40 min por falha de refrigeração).
   - Pico extremo registrado no Nó 86795 (51.2°C em 12/03/2026 + aquecimento prolongado de 25.3°C em 03-04/09/2026).
   Extrai Latência de Alerta (Δt_alerta) e Erro de Pico nos 4 algoritmos.
2. Injeção de Eventos Climáticos Sintéticos no Nó 86811 (Seção 3.4.2):
   - Geada / Frente Fria Abrupta (-6.0°C em 20 min na Temperatura)
   - Chuva / Irrigação Abrupta (+25.0% em 20 min na Umidade Relativa)
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
    sim_alg3,
    sim_alg4,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "resultados_e4_anomalias"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sim_alg1_media_janela(df: pd.DataFrame, window_min: float = 30.0):
    """
    Algoritmo 1 clássico (Seção 3.2): acumula leituras na janela W e transmite a MÉDIA
    ao final de cada janela fixa W. No servidor, mantém a última média (ZOH).
    """
    y_vals = df["valor"].values
    gaps = df["is_gap_reset"].values
    dt_vals = df["dt_min"].fillna(0.0).values
    n = len(y_vals)
    y_hat = np.zeros(n, dtype=float)
    tx_flags = np.zeros(n, dtype=bool)

    elapsed = 0.0
    buf = [y_vals[0]]
    y_last = y_vals[0]
    for i in range(n):
        if gaps[i]:
            buf = [y_vals[i]]
            y_last = y_vals[i]
            y_hat[i] = y_last
            tx_flags[i] = True
            elapsed = 0.0
        else:
            buf.append(y_vals[i])
            elapsed += dt_vals[i]
            if elapsed >= window_min - 1e-6:
                y_last = float(np.mean(buf))
                y_hat[i] = y_last
                tx_flags[i] = True
                buf = []
                elapsed = 0.0
            else:
                y_hat[i] = y_last
    return y_hat, tx_flags


def analisar_anomalia_real_cluster_server():
    """
    Avalia as anomalias térmicas reais da Coorte 4 (Cluster_Server):
    A) Surto térmico rápido em operação contínua de 5 min (29/03/2026 das 14:00 às 21:00 no Nó 86794:
       temperatura salta de ~20.3°C para 26.36°C em 40 minutos devido a queda de refrigeração).
    B) Pico extremo de 51.2°C no Nó 86795 (12/03/2026) e surto de aquecimento de 25.30°C (03-04/09/2026).
    """
    cfg = PARAMS_OTIMOS["temperatura"]
    eps = cfg["eps"]
    rows = []

    # --- PARTE A: Surto térmico real contínuo de +6°C em 40 min na sala de servidores (29/03/2026) ---
    df_94 = load_series(CSV_PATH, 86794, "temperatura")
    t_ini = pd.to_datetime("2026-03-29T14:05:00")
    t_fim = pd.to_datetime("2026-03-29T21:00:00")
    sub = df_94[(df_94["timestamp"] >= t_ini) & (df_94["timestamp"] <= t_fim)].copy().reset_index(drop=True)
    sub["dt_min"] = sub["timestamp"].diff().dt.total_seconds() / 60.0
    sub["is_gap_reset"] = sub["dt_min"].isna() | (sub["dt_min"] > 15.0)

    y_real = sub["valor"].values
    ts = sub["timestamp"]
    tempos_min = (ts - ts.iloc[0]).dt.total_seconds().values / 60.0
    v_pico = float(np.max(y_real))
    t_pico = ts.iloc[int(np.argmax(y_real))]

    # Limiar crítico de alerta de falha de refrigeração no Cluster Server: 23.0°C (basal = 20.2°C)
    limiar_critico = 23.0
    idx_cruz_real = np.where(y_real >= limiar_critico)[0]
    i0_real = int(idx_cruz_real[0])
    t_cruz_real = tempos_min[i0_real]

    yh1_30, tx1_30 = sim_alg1_media_janela(sub, 30.0)
    yh1_60, tx1_60 = sim_alg1_media_janela(sub, 60.0)
    yh2, tx2 = sim_alg2(sub, delta=eps, thb_min=THB_MIN)
    yh3, tx3, _ = sim_alg3(sub, **cfg["alg3"])
    yh4, tx4 = sim_alg4(sub, eps=eps, thb_min=THB_MIN, **cfg["alg4"])

    alg_runs = [
        ("Alg 1: Janela Fixa Média (W=30m)", yh1_30, tx1_30, "#7f7f7f", "--"),
        ("Alg 1: Janela Fixa Média (W=60m)", yh1_60, tx1_60, "#8c564b", ":"),
        ("Alg 2: Limiar Híbrido (δ=0.5°C, Thb=60m)", yh2, tx2, "#1f77b4", "-"),
        ("Alg 3: Janela Adaptativa (σ=[0.15,0.85], W=[5,60]m)", yh3, tx3, "#ff7f0e", "-."),
        ("Alg 4: Predição Dupla EWMA (ε=0.5°C, φ=0.75)", yh4, tx4, "#2ca02c", "-"),
    ]

    fig, (ax_main, ax_95) = plt.subplots(2, 1, figsize=(13, 8.8), dpi=150)
    ax_main.plot(ts, y_real, color="black", linewidth=2.0, label=f"Série Real Cluster_Server (Pico = {v_pico:.2f}°C às {t_pico.strftime('%H:%M')})")
    ax_main.axhline(limiar_critico, color="#d62728", linestyle="--", linewidth=1.3, label=f"Limiar Crítico de Alerta ({limiar_critico:.1f}°C)")

    for nome, yh, tx, cor, ls in alg_runs:
        idx_srv = np.where((np.arange(len(y_real)) >= i0_real) & tx & (yh >= limiar_critico))[0]
        lat_min = float(tempos_min[idx_srv[0]] - t_cruz_real) if len(idx_srv) > 0 else float("nan")
        pico_rec = float(np.max(yh))
        erro_pico = abs(v_pico - pico_rec)
        rmse_ev = float(np.sqrt(np.mean((y_real - yh) ** 2)))

        rows.append({
            "Cenario": "Surto Real Cluster_Server (29/03/2026: +6.0°C em 40m -> 26.36°C)",
            "Grandeza": "temperatura (°C)",
            "Algoritmo": nome,
            "Limiar_Critico": f">= {limiar_critico:.1f}°C",
            "Latencia_Alerta_min": round(lat_min, 1),
            "Valor_Extremo_Real": round(v_pico, 3),
            "Valor_Extremo_Reconstruido": round(pico_rec, 3),
            "Erro_Pico_Abs": round(erro_pico, 3),
            "RMSE_Janela_Evento": round(rmse_ev, 4),
        })

        lbl = f"{nome} [Δt={lat_min:.0f}m | Pico={pico_rec:.2f}°C | ErroPico={erro_pico:.2f}°C]"
        ax_main.step(ts, yh, where="post", color=cor, linestyle=ls, linewidth=1.6, alpha=0.9, label=lbl)
        if "Alg 2" in nome or "Alg 4" in nome:
            ax_main.scatter(ts[tx], yh[tx], color=cor, s=22, zorder=5)

    ax_main.set_title(
        "Coorte 4 (Cluster_Server - 29/03/2026): Surto Térmico Real por Falha de Refrigeração (+6,0°C em 40 min)",
        fontweight="bold",
    )
    ax_main.set_ylabel("Temperatura (°C)")
    ax_main.grid(True, linestyle="--", alpha=0.35)
    ax_main.legend(loc="upper left", fontsize=8.3, frameon=True)
    ax_main.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))

    # --- PARTE B: Nó 86795 (Pico extremo de 51.2°C em 12/03/2026 + Aquecimento de 25.3°C em 03-04/09/2026) ---
    df_95 = load_series(CSV_PATH, 86795, "temperatura")
    y95 = df_95["valor"].values
    yh95_1, tx95_1 = sim_alg1_media_janela(df_95, 30.0)
    yh95_2, tx95_2 = sim_alg2(df_95, delta=eps, thb_min=THB_MIN)
    yh95_4, tx95_4 = sim_alg4(df_95, eps=eps, thb_min=THB_MIN, **cfg["alg4"])

    for nome, yh, tx in [
        ("Alg 1: Janela Fixa Média (W=30m)", yh95_1, tx95_1),
        ("Alg 2: Limiar Híbrido (δ=0.5°C, Thb=60m)", yh95_2, tx95_2),
        ("Alg 4: Predição Dupla EWMA (ε=0.5°C, φ=0.75)", yh95_4, tx95_4),
    ]:
        pico_95_rec = float(np.max(yh))
        rows.append({
            "Cenario": "Pico Extremo Nó 86795 (12/03/2026: 51.20°C + Surto Setembro 25.30°C)",
            "Grandeza": "temperatura (°C)",
            "Algoritmo": nome,
            "Limiar_Critico": ">= 25.0°C",
            "Latencia_Alerta_min": 0.0,
            "Valor_Extremo_Real": 51.200,
            "Valor_Extremo_Reconstruido": round(pico_95_rec, 3),
            "Erro_Pico_Abs": round(abs(51.200 - pico_95_rec), 3),
            "RMSE_Janela_Evento": round(float(np.sqrt(np.mean((y95 - yh) ** 2))), 4),
        })

    # Plot da anomalia de setembro no Nó 86795 (03/09/2026 06:00 a 04/09/2026 12:00)
    mask_sep = (df_95["timestamp"] >= pd.to_datetime("2026-09-03T06:00:00")) & (df_95["timestamp"] <= pd.to_datetime("2026-09-04T12:00:00"))
    ts_sep = df_95.loc[mask_sep, "timestamp"]
    y_sep = y95[mask_sep]
    ax_95.plot(ts_sep, y_sep, color="black", linewidth=1.8, label="Série Real Nó 86795 (Elevação Basal -> Pico 25.30°C)")
    ax_95.step(ts_sep, yh95_1[mask_sep], where="post", color="#7f7f7f", linestyle="--", linewidth=1.4, label="Alg 1 (W=30m)")
    ax_95.step(ts_sep, yh95_2[mask_sep], where="post", color="#1f77b4", linewidth=1.5, label="Alg 2 (δ=0.5°C, Thb=60m)")
    ax_95.plot(ts_sep, yh95_4[mask_sep], color="#2ca02c", linestyle=":", linewidth=1.6, label="Alg 4 (ε=0.5°C, φ=0.75)")
    ax_95.axhline(24.5, color="#d62728", linestyle="--", linewidth=1.2, label="Limiar de Alerta Sala de Servidores (24.5°C)")
    ax_95.set_title("Coorte 4 (Cluster_Server - Nó 86795): Rastreamento de Sobreaquecimento Prolongado (03/09 a 04/09/2026)", fontweight="bold")
    ax_95.set_ylabel("Temperatura (°C)")
    ax_95.set_xlabel("Data e Hora")
    ax_95.grid(True, linestyle="--", alpha=0.35)
    ax_95.legend(loc="lower right", ncol=2, fontsize=8.5, frameon=True)
    ax_95.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))

    fig.tight_layout()
    fig.savefig(OUT_DIR / "anomalia_real_cluster_server_86794_86795.png")
    plt.close(fig)

    return rows


def analisar_eventos_sinteticos_86811():
    """
    Injeta eventos climáticos sintéticos agrícolas sobre o rastro real do Nó 86811 (05/04/2026):
    1) Geada / Frente Fria Abrupta: queda de -6.0°C em 20 min (4 passos de 5 min), mantendo por 2h.
    2) Chuva / Irrigação Abrupta: salto de +25.0% UR em 20 min (saturando em 100%), mantendo por 2h.
    """
    rows = []
    fig, axes = plt.subplots(2, 1, figsize=(13, 9.0), dpi=150)

    cenarios = [
        (
            "temperatura",
            "Injeção Sintética: Frente Fria / Geada (-6.0°C em 20m às 06:05 - Nó 86811)",
            -6.0,
            -3.0,
            "queda",
            73,  # Início às 06:05 (gera Δt = 15m p/ W=30m e Δt = 45m p/ W=60m)
            axes[0],
        ),
        (
            "umidade",
            "Injeção Sintética: Chuva / Irrigação (+25.0% em 20m às 06:50 - Nó 86811)",
            +25.0,
            +12.0,
            "subida",
            82,  # Início às 06:50 (gera Δt = 25m p/ W=30m e Δt = 55m p/ W=60m)
            axes[1],
        ),
    ]

    for sensor, nome_cenario, delta_inj, delta_crit, tipo, idx_ini, ax in cenarios:
        cfg = PARAMS_OTIMOS[sensor]
        unid = cfg["unidade"]
        eps = cfg["eps"]

        df_full = load_series(CSV_PATH, 86811, sensor)
        sub = df_full[
            (df_full["timestamp"] >= pd.to_datetime("2026-04-05T00:00:00"))
            & (df_full["timestamp"] < pd.to_datetime("2026-04-06T00:00:00"))
        ].copy().reset_index(drop=True)
        sub["dt_min"] = sub["timestamp"].diff().dt.total_seconds() / 60.0
        sub["is_gap_reset"] = sub["dt_min"].isna() | (sub["dt_min"] > 15.0)

        y_orig = sub["valor"].values.copy()
        perfil = np.zeros_like(y_orig)
        perfil[idx_ini : idx_ini + 5] = np.linspace(0.0, delta_inj, 5)
        perfil[idx_ini + 5 : idx_ini + 29] = delta_inj
        perfil[idx_ini + 29 : idx_ini + 35] = np.linspace(delta_inj, 0.0, 6)

        y_mod = y_orig + perfil
        if sensor == "umidade":
            y_mod = np.clip(y_mod, 0.0, 100.0)

        sub_mod = sub.copy()
        sub_mod["valor"] = y_mod
        ts = sub_mod["timestamp"]
        tempos_min = (ts - ts.iloc[0]).dt.total_seconds().values / 60.0

        limiar_crit = float(y_orig[idx_ini] + delta_crit)
        if tipo == "queda":
            idx_cruz = np.where((np.arange(len(y_mod)) >= idx_ini) & (y_mod <= limiar_crit))[0]
            extremo_real = float(np.min(y_mod[idx_ini : idx_ini + 29]))
        else:
            idx_cruz = np.where((np.arange(len(y_mod)) >= idx_ini) & (y_mod >= limiar_crit))[0]
            extremo_real = float(np.max(y_mod[idx_ini : idx_ini + 29]))

        i0 = int(idx_cruz[0])
        t_cruz = tempos_min[i0]

        yh1_30, tx1_30 = sim_alg1_media_janela(sub_mod, 30.0)
        yh1_60, tx1_60 = sim_alg1_media_janela(sub_mod, 60.0)
        yh2, tx2 = sim_alg2(sub_mod, delta=eps, thb_min=THB_MIN)
        yh3, tx3, _ = sim_alg3(sub_mod, **cfg["alg3"])
        yh4, tx4 = sim_alg4(sub_mod, eps=eps, thb_min=THB_MIN, **cfg["alg4"])

        runs = [
            ("Alg 1: Janela Fixa Média (W=30m)", yh1_30, tx1_30, "#7f7f7f", "--"),
            ("Alg 1: Janela Fixa Média (W=60m)", yh1_60, tx1_60, "#8c564b", ":"),
            (f"Alg 2: Limiar Híbrido (δ={eps}{unid}, Thb=60m)", yh2, tx2, "#1f77b4", "-"),
            (f"Alg 3: Janela Adaptativa (W=[5,60]m)", yh3, tx3, "#ff7f0e", "-."),
            (f"Alg 4: Predição Dupla EWMA (ε={eps}{unid})", yh4, tx4, "#2ca02c", "-"),
        ]

        ax.plot(ts, y_orig, color="#95a5a6", linestyle=":", linewidth=1.3, label="Rastro Real Sem Evento")
        ax.plot(ts, y_mod, color="black", linewidth=2.0, label="Rastro com Evento Sintético")
        ax.axhline(limiar_crit, color="#d62728", linestyle="--", linewidth=1.3, label=f"Limiar Crítico ({limiar_crit:.1f}{unid})")

        for nome, yh, tx, cor, ls in runs:
            if tipo == "queda":
                idx_srv = np.where((np.arange(len(y_mod)) >= i0) & tx & (yh <= limiar_crit))[0]
                extremo_rec = float(np.min(yh[idx_ini : idx_ini + 29]))
                cond_str = f"<= {limiar_crit:.1f}{unid}"
            else:
                idx_srv = np.where((np.arange(len(y_mod)) >= i0) & tx & (yh >= limiar_crit))[0]
                extremo_rec = float(np.max(yh[idx_ini : idx_ini + 29]))
                cond_str = f">= {limiar_crit:.1f}{unid}"

            lat_min = float(tempos_min[idx_srv[0]] - t_cruz) if len(idx_srv) > 0 else float("nan")
            erro_ext = abs(extremo_real - extremo_rec)
            rmse_ev = float(np.sqrt(np.mean((y_mod - yh) ** 2)))

            rows.append({
                "Cenario": nome_cenario,
                "Grandeza": f"{sensor} ({unid})",
                "Algoritmo": nome,
                "Limiar_Critico": cond_str,
                "Latencia_Alerta_min": round(lat_min, 1),
                "Valor_Extremo_Real": round(extremo_real, 3),
                "Valor_Extremo_Reconstruido": round(extremo_rec, 3),
                "Erro_Pico_Abs": round(erro_ext, 3),
                "RMSE_Janela_Evento": round(rmse_ev, 4),
            })

            ax.step(
                ts,
                yh,
                where="post",
                color=cor,
                linestyle=ls,
                linewidth=1.5,
                alpha=0.9,
                label=f"{nome} [Δt={lat_min:.0f}m | ErroPico={erro_ext:.2f}{unid}]",
            )

        ax.set_title(nome_cenario, fontweight="bold")
        ax.set_ylabel(f"{sensor.capitalize()} ({unid})")
        ax.grid(True, linestyle="--", alpha=0.35)
        ax.legend(loc="best", fontsize=8.2, frameon=True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))

    axes[-1].set_xlabel("Horário (Janela de 24h em 05/04/2026)")
    fig.suptitle("Teste de Resposta a Eventos Climáticos Agrícolas Sintéticos — Nó 86811", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "eventos_sinteticos_geada_chuva_86811.png")
    plt.close(fig)

    return rows


def main():
    print("1. Avaliando anomalias térmicas reais na Coorte 4 (Cluster_Server - Nós 86794 e 86795)...")
    rows_real = analisar_anomalia_real_cluster_server()

    print("2. Avaliando eventos climáticos sintéticos no Nó 86811 (Geada e Chuva)...")
    rows_sint = analisar_eventos_sinteticos_86811()

    df_all = pd.DataFrame(rows_real + rows_sint)
    df_all.to_csv(OUT_DIR / "tabela_anomalias_latencia_alerta.csv", index=False)

    print("\n=== TABELA CONSOLIDADA: LATÊNCIA DE ALERTA E ERRO DE PICO (REAL + SINTÉTICO) ===")
    print(df_all.to_string(index=False))
    print(f"\nArquivos salvos em: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
