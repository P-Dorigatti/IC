#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FASE 1 (COMPLEMENTO UMIDADE - NÓ 86811):
1. Grid Search do Algoritmo 4 e Algoritmo 3 na janela de 15 dias (01/04 a 16/04/2026)
2. Curva de Pareto (RMSE % vs TR %) nos 15 dias e nos 200 dias
3. Validação nos 200 dias completos com tratamento estrito de lacunas (Cold Start > 15m)
"""

from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ==============================================================================
# 1. CONFIGURAÇÕES E JANELA DE CALIBRAÇÃO (15 DIAS)
# ==============================================================================
ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT_DIR / "dataset_koala_e2/koala_dataset_mestre_5min.csv"
OUT_DIR = ROOT_DIR / "resultados_e4_fase1_umidade"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_DEVICE = 86811
TARGET_SENSOR = "umidade"  # id_sensor = 2 (%)
DT_NOMINAL_MIN = 5.0
GAP_RESET_MIN = 15.0

# Janela de 15 dias para o Grid Search (mesma época limpa de abril)
TRAIN_START = "2026-04-01T00:00:00"
TRAIN_END = "2026-04-16T00:00:00"

# Parâmetro de referência oficial p/ Umidade (Seção 3.2 do Plano): delta = 2.0%, Thb = 60m
TARGET_EPS_HUM = 2.0
TARGET_THB_MIN = 60.0


# ==============================================================================
# 2. CARREGAMENTO E PREPARAÇÃO COM DETECÇÃO DE LACUNAS
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


# ==============================================================================
# 3. IMPLEMENTAÇÃO DOS 4 ALGORITMOS (COM SATURAÇÃO FÍSICA [0%, 100%] NO ALG 4)
# ==============================================================================
def eval_metrics(y_true: np.ndarray, y_hat: np.ndarray, tx_flags: np.ndarray, label: str = "") -> dict:
    n_total = len(y_true)
    n_tx = int(np.sum(tx_flags))
    tr_pct = (1.0 - (n_tx / n_total)) * 100.0
    abs_err = np.abs(y_true - y_hat)
    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean(abs_err ** 2)))
    max_err = float(np.max(abs_err))
    return {
        "Algoritmo": label,
        "Pacotes": n_tx,
        "TR_pct": tr_pct,
        "MAE": mae,
        "RMSE": rmse,
        "ErroMax": max_err,
    }


def run_alg1(df: pd.DataFrame, window_min: float) -> dict:
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
    return eval_metrics(y_vals, y_hat, tx_flags, f"Alg 1 (W={int(window_min)}m)")


def run_alg2(df: pd.DataFrame, delta: float, thb_min: float) -> dict:
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
    return eval_metrics(y_vals, y_hat, tx_flags, f"Alg 2 (δ={delta}%, Thb={int(thb_min)}m)")


def run_alg3(df: pd.DataFrame, k_win: int, sigma_low: float, sigma_high: float, w_min: float, w_max: float) -> dict:
    y_vals = df["valor"].values
    gaps = df["is_gap_reset"].values
    dt_vals = df["dt_min"].fillna(0.0).values
    n = len(y_vals)
    y_hat = np.zeros(n, dtype=float)
    tx_flags = np.zeros(n, dtype=bool)

    elapsed = 0.0
    y_last = y_vals[0]
    buf = []
    for i in range(n):
        if gaps[i]:
            buf = [y_vals[i]]
            y_last = y_vals[i]
            y_hat[i] = y_last
            tx_flags[i] = True
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

            elapsed += dt_vals[i]
            if elapsed >= w_curr - 1e-6:
                y_last = y_vals[i]
                y_hat[i] = y_last
                tx_flags[i] = True
                elapsed = 0.0
            else:
                y_hat[i] = y_last
    return eval_metrics(y_vals, y_hat, tx_flags, f"Alg 3 (σ=[{sigma_low},{sigma_high}], W=[{int(w_min)},{int(w_max)}]m)")


def run_alg4(
    df: pd.DataFrame,
    eps: float,
    thb_min: float,
    alpha: float,
    beta: float,
    deadband: float,
    damping_phi: float,
    clip_bounds: tuple[float, float] = (0.0, 100.0)
) -> dict:
    """
    Algoritmo 4 com proteção física de saturação (ex: Umidade Relativa não passa de 100%).
    Tanto o nó quanto o servidor aplicam clip(y_pred, 0.0, 100.0).
    """
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

    return eval_metrics(
        y_vals, y_hat, tx_flags,
        f"Alg 4 (ε={eps}%, Thb={int(thb_min)}m, φ={damping_phi})"
    )


# ==============================================================================
# 4. GRID SEARCH PARA O ALGORITMO 4 NA UMIDADE (15 DIAS)
# ==============================================================================
def grid_search_alg4_humidity(df_15d: pd.DataFrame, eps: float = 2.0, thb_min: float = 60.0) -> dict:
    # Referência do Alg 2 no mesmo limiar (delta = 2.0%, Thb = 60m)
    ref_alg2 = run_alg2(df_15d, delta=eps, thb_min=thb_min)

    alphas = [0.2, 0.3, 0.4, 0.5, 0.6]
    betas = [0.05, 0.10, 0.15, 0.25, 0.35]
    deadbands = [0.005, 0.015, 0.030, 0.050, 0.080]  # em % / min
    phis = [0.75, 0.82, 0.88, 0.92, 0.96]

    best_score = float("inf")
    best_cfg = None
    best_res = None

    for a, b, db, phi in product(alphas, betas, deadbands, phis):
        res = run_alg4(df_15d, eps=eps, thb_min=thb_min, alpha=a, beta=b, deadband=db, damping_phi=phi)
        # Função custo J: maximizar TR% e minimizar RMSE simultaneamente
        # Penaliza se TR% ficar abaixo do Alg 2 de mesmo limiar
        tr_penalty = max(0.0, ref_alg2["TR_pct"] - res["TR_pct"]) * 0.15
        score = res["RMSE"] - 0.025 * res["TR_pct"] + tr_penalty

        if score < best_score:
            best_score = score
            best_cfg = {"alpha": a, "beta": b, "deadband": db, "damping_phi": phi}
            best_res = res

    print(f"\n=== REFERÊNCIA ALG 2 NOS 15 DIAS (δ={eps}%, Thb={int(thb_min)}m) ===")
    print(
        f"Desempenho Alg 2: Pacotes={ref_alg2['Pacotes']} | TR={ref_alg2['TR_pct']:.2f}% | "
        f"MAE={ref_alg2['MAE']:.4f}% | RMSE={ref_alg2['RMSE']:.4f}% | ErroMax={ref_alg2['ErroMax']:.3f}%"
    )

    print(f"\n=== MELHOR CONFIGURAÇÃO ENCONTRADA VIA GRID SEARCH PARA ALG 4 (ε={eps}%, Thb={int(thb_min)}m) ===")
    print(
        f"Parâmetros Ótimos: alpha={best_cfg['alpha']}, beta={best_cfg['beta']}, "
        f"deadband={best_cfg['deadband']}%/min, damping_phi={best_cfg['damping_phi']}"
    )
    print(
        f"Desempenho Alg 4 Otimizado: Pacotes={best_res['Pacotes']} | TR={best_res['TR_pct']:.2f}% | "
        f"MAE={best_res['MAE']:.4f}% | RMSE={best_res['RMSE']:.4f}% | ErroMax={best_res['ErroMax']:.3f}%"
    )
    return best_cfg


# ==============================================================================
# 5. EXECUÇÃO PRINCIPAL (15 DIAS -> PARETO -> 200 DIAS COMPLETOS)
# ==============================================================================
def main():
    df_200d = load_series(CSV_PATH, TARGET_DEVICE, TARGET_SENSOR)
    df_15d = slice_window(df_200d, TRAIN_START, TRAIN_END)

    print(f"Série carregada (Nó {TARGET_DEVICE} - {TARGET_SENSOR}):")
    print(f" -> Recorte 15 dias ({TRAIN_START[:10]} a {TRAIN_END[:10]}): {len(df_15d):,} amostras")
    print(f" -> Série completa 200 dias: {len(df_200d):,} amostras")

    # 1. Executa o Grid Search nos 15 dias para encontrar os ótimos da Umidade
    best_alg4_hum = grid_search_alg4_humidity(df_15d, eps=TARGET_EPS_HUM, thb_min=TARGET_THB_MIN)

    # 2. Varredura da Fronteira de Pareto para Umidade (nos 15 dias e nos 200 dias)
    deltas_hum = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]
    windows_min = [10, 15, 20, 30, 45, 60, 90, 120]
    alg3_grids = [
        (0.2, 1.2, 15), (0.4, 2.0, 30), (0.6, 3.5, 60), (1.0, 5.0, 90), (1.5, 7.0, 120)
    ]

    for period_name, df_target in [("15dias", df_15d), ("200dias", df_200d)]:
        p_alg1 = [run_alg1(df_target, w) for w in windows_min]
        p_alg2 = [run_alg2(df_target, d, TARGET_THB_MIN) for d in deltas_hum]
        p_alg3 = [run_alg3(df_target, 6, sl, sh, 5.0, wm) for sl, sh, wm in alg3_grids]
        p_alg4 = [
            run_alg4(df_target, d, TARGET_THB_MIN, **best_alg4_hum)
            for d in deltas_hum
        ]

        plt.figure(figsize=(9, 5.5), dpi=150)
        plt.plot([r["TR_pct"] for r in p_alg1], [r["RMSE"] for r in p_alg1],
                 "o--", label="Alg 1: Janela Fixa (W=10..120m)", color="#7f7f7f")
        plt.plot([r["TR_pct"] for r in p_alg3], [r["RMSE"] for r in p_alg3],
                 "s-.", label="Alg 3: Janela Adaptativa (Variância)", color="#ff7f0e")
        plt.plot([r["TR_pct"] for r in p_alg2], [r["RMSE"] for r in p_alg2],
                 "^-", linewidth=2.2, label="Alg 2: Limiar Estático Híbrido (Thb=60m)", color="#1f77b4")
        plt.plot([r["TR_pct"] for r in p_alg4], [r["RMSE"] for r in p_alg4],
                 "d:", linewidth=2.2, label="Alg 4: Predição Dupla EWMA Otimizado (Thb=60m)", color="#2ca02c")

        plt.xlabel(f"Taxa de Redução de Transmissões - TR (%) [{period_name}]", fontsize=11)
        plt.ylabel("Erro de Reconstrução - RMSE (% Umidade)", fontsize=11)
        plt.title(f"Fronteira de Pareto - Umidade Relativa ({period_name} - Nó 86811)", fontsize=12, fontweight="bold")
        plt.grid(True, linestyle="--", alpha=0.4)
        plt.legend(frameon=True, fontsize=9.5)
        plt.tight_layout()
        plt.savefig(OUT_DIR / f"pareto_umidade_{period_name}_86811.png")
        plt.close()

    # 3. Tabela Consolidada dos 200 Dias Completos para Umidade (Com Parâmetros Congelados)
    summary_200d = [
        run_alg1(df_200d, 15.0),
        run_alg1(df_200d, 30.0),
        run_alg1(df_200d, 60.0),
        run_alg2(df_200d, delta=TARGET_EPS_HUM, thb_min=TARGET_THB_MIN),
        run_alg3(df_200d, k_win=6, sigma_low=0.6, sigma_high=3.5, w_min=5.0, w_max=60.0),
        run_alg4(df_200d, eps=TARGET_EPS_HUM, thb_min=TARGET_THB_MIN, **best_alg4_hum),
    ]
    df_sum = pd.DataFrame(summary_200d)
    df_sum["TR_pct"] = df_sum["TR_pct"].round(2)
    df_sum["MAE"] = df_sum["MAE"].round(4)
    df_sum["RMSE"] = df_sum["RMSE"].round(4)
    df_sum["ErroMax"] = df_sum["ErroMax"].round(3)
    df_sum.to_csv(OUT_DIR / "tabela_fase1_umidade_200dias_86811.csv", index=False)

    print("\n=== RESULTADOS GLOBAIS NOS 200 DIAS (NÓ 86811 - UMIDADE RELATIVA) ===")
    print(df_sum.to_string(index=False))
    print(f"\nArquivos salvos em: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()