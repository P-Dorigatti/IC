#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENTREGÁVEL E4 — SCRIPT 1: VALIDAÇÃO DA RECONSTRUÇÃO DA SÉRIE BASE (NÓ 86811)
Compara a série original (Ground Truth de 5 min) com a série reconstruída no servidor
pelos 4 algoritmos usando os hiperparâmetros ótimos congelados (Temperatura e Umidade).
Gera gráficos detalhados de reconstrução + erro instantâneo |y(t) - y_hat(t)| e CSV resumo.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ==============================================================================
# 1. CONFIGURAÇÕES E HIPERPARÂMETROS ÓTIMOS CONGELADOS
# ==============================================================================
ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT_DIR / "dataset_koala_e2/koala_dataset_mestre_5min.csv"
OUT_DIR = ROOT_DIR / "resultados_e4_reconstrucao"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DEVICE = 86811
DT_NOMINAL_MIN = 5.0
GAP_RESET_MIN = 15.0
THB_MIN = 60.0

# Janela de 15 dias de referência e janela de zoom de 72h (3 dias) para inspeção visual nítida
WINDOW_15D_START = "2026-04-01T00:00:00"
WINDOW_15D_END = "2026-04-16T00:00:00"
ZOOM_START = "2026-04-04T00:00:00"
ZOOM_END = "2026-04-07T00:00:00"

PARAMS_OTIMOS = {
    "temperatura": {
        "unidade": "°C",
        "eps": 0.5,
        "alg3": {"k_win": 6, "sigma_low": 0.15, "sigma_high": 0.85, "w_min": 5.0, "w_max": 60.0},
        "alg4": {
            "alpha": 0.4,
            "beta": 0.15,
            "deadband": 0.005,
            "damping_phi": 0.75,
            "clip_bounds": (-10.0, 60.0),
        },
    },
    "umidade": {
        "unidade": "%",
        "eps": 2.0,
        "alg3": {"k_win": 6, "sigma_low": 0.6, "sigma_high": 3.5, "w_min": 5.0, "w_max": 60.0},
        "alg4": {
            "alpha": 0.6,
            "beta": 0.10,
            "deadband": 0.030,
            "damping_phi": 0.82,
            "clip_bounds": (0.0, 100.0),
        },
    },
}


# ==============================================================================
# 2. CARREGAMENTO E IMPLEMENTAÇÃO DOS ALGORITMOS (RETORNANDO SÉRIES RECONSTRUÍDAS)
# ==============================================================================
def load_series(csv_path: Path, device_id: int, sensor_name: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    sub = df[(df["id_dispositivo"] == device_id) & (df["sensor"] == sensor_name)].copy()
    sub["timestamp"] = pd.to_datetime(sub["timestamp"])
    sub = sub.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    sub["dt_min"] = sub["timestamp"].diff().dt.total_seconds() / 60.0
    sub["is_gap_reset"] = sub["dt_min"].isna() | (sub["dt_min"] > GAP_RESET_MIN)
    return sub


def slice_window(df: pd.DataFrame, t_start: str, t_end: str) -> pd.DataFrame:
    sub = df[(df["timestamp"] >= pd.to_datetime(t_start)) & (df["timestamp"] < pd.to_datetime(t_end))].copy()
    sub = sub.reset_index(drop=True)
    sub["dt_min"] = sub["timestamp"].diff().dt.total_seconds() / 60.0
    sub["is_gap_reset"] = sub["dt_min"].isna() | (sub["dt_min"] > GAP_RESET_MIN)
    return sub


def eval_metrics(y_true: np.ndarray, y_hat: np.ndarray, tx_flags: np.ndarray, label: str = "") -> dict:
    n_total = len(y_true)
    n_tx = int(np.sum(tx_flags))
    tr_pct = (1.0 - (n_tx / n_total)) * 100.0
    abs_err = np.abs(y_true - y_hat)
    return {
        "Algoritmo": label,
        "Amostras": n_total,
        "Pacotes": n_tx,
        "TR_pct": round(tr_pct, 2),
        "MAE": round(float(np.mean(abs_err)), 4),
        "RMSE": round(float(np.sqrt(np.mean(abs_err ** 2))), 4),
        "ErroMax": round(float(np.max(abs_err)), 3),
        "P95_Erro": round(float(np.percentile(abs_err, 95)), 4),
    }


def sim_alg1(df: pd.DataFrame, window_min: float = 30.0):
    y_vals = df["valor"].values
    gaps = df["is_gap_reset"].values
    dt_vals = df["dt_min"].fillna(0.0).values
    n = len(y_vals)
    y_hat = np.zeros(n, dtype=float)
    tx_flags = np.zeros(n, dtype=bool)

    elapsed = 0.0
    y_last = y_vals[0]
    for i in range(n):
        if gaps[i]:
            y_last = y_vals[i]
            y_hat[i] = y_last
            tx_flags[i] = True
            elapsed = 0.0
        else:
            elapsed += dt_vals[i]
            if elapsed >= window_min - 1e-6:
                y_last = y_vals[i]
                y_hat[i] = y_last
                tx_flags[i] = True
                elapsed = 0.0
            else:
                y_hat[i] = y_last
    return y_hat, tx_flags


def sim_alg2(df: pd.DataFrame, delta: float, thb_min: float = 60.0):
    y_vals = df["valor"].values
    gaps = df["is_gap_reset"].values
    dt_vals = df["dt_min"].fillna(0.0).values
    n = len(y_vals)
    y_hat = np.zeros(n, dtype=float)
    tx_flags = np.zeros(n, dtype=bool)

    elapsed = 0.0
    y_last = y_vals[0]
    for i in range(n):
        if gaps[i]:
            y_last = y_vals[i]
            y_hat[i] = y_last
            tx_flags[i] = True
            elapsed = 0.0
        else:
            elapsed += dt_vals[i]
            if (abs(y_vals[i] - y_last) >= delta) or (elapsed >= thb_min - 1e-6):
                y_last = y_vals[i]
                y_hat[i] = y_last
                tx_flags[i] = True
                elapsed = 0.0
            else:
                y_hat[i] = y_last
    return y_hat, tx_flags


def sim_alg3(df: pd.DataFrame, k_win: int, sigma_low: float, sigma_high: float, w_min: float, w_max: float):
    y_vals = df["valor"].values
    gaps = df["is_gap_reset"].values
    dt_vals = df["dt_min"].fillna(0.0).values
    n = len(y_vals)
    y_hat = np.zeros(n, dtype=float)
    tx_flags = np.zeros(n, dtype=bool)
    w_series = np.zeros(n, dtype=float)

    elapsed = 0.0
    y_last = y_vals[0]
    buf = []
    for i in range(n):
        if gaps[i]:
            buf = [y_vals[i]]
            y_last = y_vals[i]
            y_hat[i] = y_last
            tx_flags[i] = True
            w_series[i] = w_max
            elapsed = 0.0
        else:
            buf.append(y_vals[i])
            if len(buf) > k_win:
                buf.pop(0)
            sigma_k = float(np.std(buf, ddof=0)) if len(buf) > 1 else 0.0
            if sigma_k <= sigma_low:
                w_curr = w_max
            elif sigma_k >= sigma_high:
                w_curr = w_min
            else:
                ratio = (sigma_k - sigma_low) / (sigma_high - sigma_low)
                w_curr = w_max - ratio * (w_max - w_min)

            w_series[i] = w_curr
            elapsed += dt_vals[i]
            if elapsed >= w_curr - 1e-6:
                y_last = y_vals[i]
                y_hat[i] = y_last
                tx_flags[i] = True
                elapsed = 0.0
            else:
                y_hat[i] = y_last
    return y_hat, tx_flags, w_series


def sim_alg4(
    df: pd.DataFrame,
    eps: float,
    thb_min: float,
    alpha: float,
    beta: float,
    deadband: float,
    damping_phi: float,
    clip_bounds: tuple[float, float],
):
    y_vals = df["valor"].values
    gaps = df["is_gap_reset"].values
    dt_vals = df["dt_min"].fillna(0.0).values
    n = len(y_vals)
    y_hat = np.zeros(n, dtype=float)
    tx_flags = np.zeros(n, dtype=bool)

    low_b, high_b = clip_bounds
    level_local = y_vals[0]
    trend_local = 0.0
    y_sent = y_vals[0]
    m_sent = 0.0
    elapsed = 0.0
    steps_since_tx = 0

    for i in range(n):
        if gaps[i]:
            level_local = y_vals[i]
            trend_local = 0.0
            y_sent = y_vals[i]
            m_sent = 0.0
            y_hat[i] = y_sent
            tx_flags[i] = True
            elapsed = 0.0
            steps_since_tx = 0
        else:
            dt = dt_vals[i]
            elapsed += dt
            steps_since_tx += 1

            prev_level = level_local
            pred_local = np.clip(prev_level + (damping_phi * trend_local) * dt, low_b, high_b)
            level_local = alpha * y_vals[i] + (1.0 - alpha) * pred_local
            instant_slope = (level_local - prev_level) / max(dt, 1e-6)
            trend_local = beta * instant_slope + (1.0 - beta) * (damping_phi * trend_local)

            if abs(1.0 - damping_phi) > 1e-6:
                damped_steps = damping_phi * (1.0 - (damping_phi ** steps_since_tx)) / (1.0 - damping_phi)
            else:
                damped_steps = float(steps_since_tx)

            y_pred_srv = float(np.clip(y_sent + m_sent * (damped_steps * DT_NOMINAL_MIN), low_b, high_b))

            if (abs(y_vals[i] - y_pred_srv) >= eps) or (elapsed >= thb_min - 1e-6):
                y_sent = y_vals[i]
                m_sent = 0.0 if abs(trend_local) < deadband else trend_local
                y_hat[i] = y_sent
                tx_flags[i] = True
                elapsed = 0.0
                steps_since_tx = 0
            else:
                y_hat[i] = y_pred_srv

    return y_hat, tx_flags


# ==============================================================================
# 3. PLOTAGEM DE RECONSTRUÇÃO (4 ALGORITMOS + ERRO DE RECONSTRUÇÃO)
# ==============================================================================
def plot_reconstrucao_zoom(df_15d: pd.DataFrame, sensor: str, cfg: dict):
    unid = cfg["unidade"]
    eps = cfg["eps"]
    p_alg3 = cfg["alg3"]
    p_alg4 = cfg["alg4"]

    y_true = df_15d["valor"].values
    yh1, tx1 = sim_alg1(df_15d, window_min=30.0)
    yh2, tx2 = sim_alg2(df_15d, delta=eps, thb_min=THB_MIN)
    yh3, tx3, _ = sim_alg3(df_15d, **p_alg3)
    yh4, tx4 = sim_alg4(df_15d, eps=eps, thb_min=THB_MIN, **p_alg4)

    mask_z = (df_15d["timestamp"] >= pd.to_datetime(ZOOM_START)) & (df_15d["timestamp"] < pd.to_datetime(ZOOM_END))
    ts_z = df_15d.loc[mask_z, "timestamp"]
    yt_z = y_true[mask_z]

    # Painel 1: Reconstrução dos 4 algoritmos na janela de 72h
    fig, axes = plt.subplots(4, 1, figsize=(13, 10.5), sharex=True, dpi=150)
    alg_list = [
        (f"Alg 1: Janela Fixa (W=30m)", yh1[mask_z], tx1[mask_z], "#7f7f7f", True),
        (f"Alg 2: Limiar Estático Híbrido (δ={eps}{unid}, Thb=60m)", yh2[mask_z], tx2[mask_z], "#1f77b4", True),
        (
            f"Alg 3: Janela Adaptativa (σ=[{p_alg3['sigma_low']},{p_alg3['sigma_high']}]{unid}, W=[5,60]m)",
            yh3[mask_z],
            tx3[mask_z],
            "#ff7f0e",
            True,
        ),
        (
            f"Alg 4: Predição Dupla EWMA Otimizado (ε={eps}{unid}, Thb=60m, φ={p_alg4['damping_phi']})",
            yh4[mask_z],
            tx4[mask_z],
            "#2ca02c",
            False,
        ),
    ]

    for ax, (titulo, yh_z, tx_z, cor, is_step) in zip(axes, alg_list):
        n_env = int(np.sum(tx_z))
        tr_z = (1.0 - n_env / len(yt_z)) * 100.0
        rmse_z = float(np.sqrt(np.mean((yt_z - yh_z) ** 2)))
        emax_z = float(np.max(np.abs(yt_z - yh_z)))

        ax.plot(ts_z, yt_z, color="#2c3e50", alpha=0.45, linewidth=1.4, label="Série Base Real (5 min)")
        if is_step:
            ax.step(ts_z, yh_z, where="post", color=cor, linewidth=1.6, label="Reconstrução no Servidor (ZOH)")
        else:
            ax.plot(ts_z, yh_z, color=cor, linewidth=1.6, label="Reconstrução no Servidor (Extrapolação EWMA)")
        ax.scatter(
            ts_z[tx_z],
            yt_z[tx_z],
            color=cor,
            s=18,
            zorder=5,
            label=f"Pacotes Transmitidos (N={n_env}/{len(yt_z)} | TR={tr_z:.1f}%)",
        )
        ax.set_title(f"{titulo}  —  [RMSE={rmse_z:.3f}{unid} | ErroMáx={emax_z:.3f}{unid}]", fontsize=10.5, fontweight="bold")
        ax.set_ylabel(f"{sensor.capitalize()} ({unid})")
        ax.grid(True, linestyle="--", alpha=0.35)
        ax.legend(loc="upper right", ncol=3, fontsize=8.5, frameon=True)

    axes[-1].set_xlabel("Data e Hora (Zoom de 72h: 04/04/2026 a 07/04/2026)")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))
    fig.suptitle(
        f"Validação da Reconstrução da Série Temporal — {sensor.capitalize()} (Nó {TARGET_DEVICE})",
        fontsize=12.5,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"reconstrucao_72h_{sensor}_86811.png")
    plt.close(fig)

    # Painel 2: Comparação direta do Erro Instantâneo |y(t) - y_hat(t)| (Alg 1 vs Alg 2 vs Alg 4)
    fig2, (ax_top, ax_err) = plt.subplots(2, 1, figsize=(12.5, 6.5), sharex=True, dpi=150)
    ax_top.plot(ts_z, yt_z, color="black", linewidth=1.6, label="Série Base Real (5 min)")
    ax_top.step(ts_z, yh1[mask_z], where="post", color="#7f7f7f", linestyle="--", alpha=0.8, label="Alg 1 (W=30m)")
    ax_top.step(ts_z, yh2[mask_z], where="post", color="#1f77b4", linewidth=1.4, label=f"Alg 2 (δ={eps}{unid})")
    ax_top.plot(ts_z, yh4[mask_z], color="#2ca02c", linestyle=":", linewidth=1.7, label=f"Alg 4 (ε={eps}{unid})")
    ax_top.set_ylabel(f"{sensor.capitalize()} ({unid})")
    ax_top.set_title(f"Sobreposição da Série Base vs. Reconstruções — {sensor.capitalize()} (Nó {TARGET_DEVICE})", fontweight="bold")
    ax_top.grid(True, linestyle="--", alpha=0.35)
    ax_top.legend(loc="upper right", ncol=4, fontsize=9)

    ax_err.plot(ts_z, np.abs(yt_z - yh1[mask_z]), color="#7f7f7f", alpha=0.75, linewidth=1.2, label="Erro |y - ŷ| Alg 1 (W=30m) — Viola Limiar")
    ax_err.plot(ts_z, np.abs(yt_z - yh2[mask_z]), color="#1f77b4", alpha=0.85, linewidth=1.2, label=f"Erro |y - ŷ| Alg 2 (δ={eps}{unid})")
    ax_err.plot(ts_z, np.abs(yt_z - yh4[mask_z]), color="#2ca02c", alpha=0.85, linewidth=1.2, label=f"Erro |y - ŷ| Alg 4 (ε={eps}{unid})")
    ax_err.axhline(eps, color="#d62728", linestyle="--", linewidth=1.5, label=f"Teto Garantido de Erro (δ = ε = {eps}{unid})")
    ax_err.set_ylabel(f"Erro Absoluto ({unid})")
    ax_err.set_xlabel("Data e Hora (Zoom de 72h: 04/04/2026 a 07/04/2026)")
    ax_err.set_title("Garantia Determinística de Limite de Erro (Alg 2 e Alg 4) vs. Erro Descontrolado em Transientes (Alg 1)", fontweight="bold")
    ax_err.grid(True, linestyle="--", alpha=0.35)
    ax_err.legend(loc="upper right", ncol=2, fontsize=8.8)
    ax_err.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))

    fig2.tight_layout()
    fig2.savefig(OUT_DIR / f"erro_instantaneo_72h_{sensor}_86811.png")
    plt.close(fig2)

    return [
        {"Grandeza": sensor, **eval_metrics(y_true, yh1, tx1, "Alg 1 (W=30m)")},
        {"Grandeza": sensor, **eval_metrics(y_true, yh2, tx2, f"Alg 2 (δ={eps}{unid}, Thb=60m)")},
        {"Grandeza": sensor, **eval_metrics(y_true, yh3, tx3, f"Alg 3 (σ=[{p_alg3['sigma_low']},{p_alg3['sigma_high']}], W=[5,60]m)")},
        {"Grandeza": sensor, **eval_metrics(y_true, yh4, tx4, f"Alg 4 (ε={eps}{unid}, Thb=60m, φ={p_alg4['damping_phi']})")},
    ]


def main():
    rows_all = []
    for sensor, cfg in PARAMS_OTIMOS.items():
        df_full = load_series(CSV_PATH, TARGET_DEVICE, sensor)
        df_15d = slice_window(df_full, WINDOW_15D_START, WINDOW_15D_END)
        rows = plot_reconstrucao_zoom(df_15d, sensor, cfg)
        rows_all.extend(rows)

    df_res = pd.DataFrame(rows_all)
    df_res.to_csv(OUT_DIR / "tabela_validacao_reconstrucao_15d_86811.csv", index=False)
    print("\n=== VALIDAÇÃO DE RECONSTRUÇÃO (JANELA 15 DIAS E ZOOM 72H - NÓ 86811) ===")
    print(df_res.to_string(index=False))
    print(f"\nGráficos e tabela salvos em: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
