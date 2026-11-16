#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entregável E3 — Gráficos Exploratórios, Médias Móveis e Identificação de Lacunas
Projeto IC FAPESP: RSSF na Agricultura de Precisão (Testbed Koala)
Pesquisador: Pedro Dorigatti Aureo Ferreira | Orientador: Prof. Dr. Julio Cezar Estrella
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Configuração visual padrão publicação científica (IEEE / Elsevier style)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--"
})

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "dataset_koala_e2"
OUT_DIR = ROOT_DIR / "figuras_e3"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def extrair_serie_grade_5min(df: pd.DataFrame, id_disp: int, nome_sensor: str) -> pd.DataFrame:
    """
    Filtra um par (id_dispositivo, sensor) e reindexa em uma grade estrita de 5 minutos.
    Qualquer bloco ausente vira NaN explícito (evita que o matplotlib trace retas falsas sobre lacunas).
    """
    sub = df[(df["id_dispositivo"] == id_disp) & (df["sensor"] == nome_sensor)].copy()
    sub = sub.sort_values("timestamp").drop_duplicates(subset=["timestamp"])

    # Calcula deltas reais antes de reindexar para mapear lacunas (> 15 min)
    sub["dt_min"] = sub["timestamp"].diff().dt.total_seconds() / 60.0
    lacunas = sub[sub["dt_min"] > 15.0][["timestamp", "dt_min"]].copy()
    lacunas["inicio_lacuna"] = lacunas["timestamp"] - pd.to_timedelta(lacunas["dt_min"], unit="m")
    lacunas["fim_lacuna"] = lacunas["timestamp"]

    # Cria grade contínua de 5 min do início ao fim da série
    grade_completa = pd.date_range(
        start=sub["timestamp"].min(),
        end=sub["timestamp"].max(),
        freq="5min"
    )
    sub_indexed = sub.set_index("timestamp").reindex(grade_completa)
    sub_indexed.index.name = "timestamp"

    # Médias móveis centradas/causais respeitando falhas (min_periods evita sumir bordas)
    # 1h = 12 blocos de 5 min | 6h = 72 blocos | 24h = 288 blocos
    sub_indexed["mma_1h"] = sub_indexed["valor"].rolling(window=12, min_periods=6).mean()
    sub_indexed["mma_6h"] = sub_indexed["valor"].rolling(window=72, min_periods=24).mean()
    sub_indexed["mma_24h"] = sub_indexed["valor"].rolling(window=288, min_periods=96).mean()

    return sub_indexed, lacunas


def sombrear_lacunas(ax, lacunas: pd.DataFrame, limiar_min: float = 60.0, label_unica: bool = True):
    """Destaca visualmente no gráfico os intervalos onde houve perda de dados > limiar_min."""
    grandes = lacunas[lacunas["dt_min"] >= limiar_min]
    for idx, (_, row) in enumerate(grandes.iterrows()):
        lbl = f"Lacuna / Inatividade (>{int(limiar_min)} min)" if (idx == 0 and label_unica) else None
        ax.axvspan(row["inicio_lacuna"], row["fim_lacuna"], color="#e74c3c", alpha=0.22, label=lbl)


def plot_fig1_panorama_lacunas(df: pd.DataFrame):
    """
    FIGURA 1: Série Temporal Completa (200 dias), Média Móvel de 24h e Identificação Visual de Lacunas.
    Compara um nó externo (86811) com um nó indoor (1 - TEMP4) para evidenciar os apagões simultâneos do servidor.
    """
    s_ext, lac_ext = extrair_serie_grade_5min(df, id_disp=86811, nome_sensor="temperatura")
    s_ind, lac_ind = extrair_serie_grade_5min(df, id_disp=86782, nome_sensor="temperatura")

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

    # Painel A: Nó Externo
    ax = axes[0]
    ax.plot(s_ext.index, s_ext["valor"], color="#95a5a6", alpha=0.45, linewidth=0.5, label="Série Bruta (5 min)")
    ax.plot(s_ext.index, s_ext["mma_24h"], color="#d35400", linewidth=1.8, label="Média Móvel 24h (Tendência Sazonal)")
    sombrear_lacunas(ax, lac_ext, limiar_min=60.0, label_unica=True)
    ax.set_title("A) Coorte Externo_Cluster — Nó 1006EXT-TEMPHUM-03 (ID 86811) | Ciclo Diurno e Sazonalidade")
    ax.set_ylabel("Temperatura (°C)")
    ax.legend(loc="upper right", frameon=True)

    # Painel B: Nó Indoor
    ax = axes[1]
    ax.plot(s_ind.index, s_ind["valor"], color="#7f8c8d", alpha=0.45, linewidth=0.5, label="Série Bruta (5 min)")
    ax.plot(s_ind.index, s_ind["mma_24h"], color="#2980b9", linewidth=1.8, label="Média Móvel 24h (Regime Climatizado)")
    sombrear_lacunas(ax, lac_ind, limiar_min=60.0, label_unica=True)
    ax.set_title("B) Coorte Indoor_Baseline — Nó TEMP4 (ID 86782 - Lab 1006) | Estabilidade Térmica e Apagões Sincronizados")
    ax.set_ylabel("Temperatura (°C)")
    ax.set_xlabel("Data (Março a Setembro de 2026)")
    ax.legend(loc="upper right", frameon=True)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    fig.tight_layout()
    caminho = OUT_DIR / "E3_fig1_panorama_200dias_e_lacunas.png"
    fig.savefig(caminho, dpi=300)
    plt.close(fig)
    print(f"[OK] Figura 1 salva em: {caminho}")


def plot_fig2_zoom_media_movel_envelope(df: pd.DataFrame):
    """
    FIGURA 2: Zoom de 10 dias mostrando Série Bruta (5 min), Envelope Intra-bloco [min, max],
    Média Móvel de 1h (filtro de ruído local) e Média Móvel de 6h, além de uma lacuna real de ~16h.
    """
    s_ext, lac_ext = extrair_serie_grade_5min(df, id_disp=86811, nome_sensor="temperatura")
    s_hum, lac_hum = extrair_serie_grade_5min(df, id_disp=86811, nome_sensor="umidade")

    # Recorte de 01/04/2026 a 11/04/2026
    ini, fim = "2026-04-01", "2026-04-11"
    z_temp = s_ext.loc[ini:fim]
    z_hum = s_hum.loc[ini:fim]
    lac_z = lac_ext[(lac_ext["fim_lacuna"] >= ini) & (lac_ext["inicio_lacuna"] <= fim)]

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

    # Temperatura
    ax = axes[0]
    ax.fill_between(
        z_temp.index, z_temp["valor_min"], z_temp["valor_max"],
        color="#f39c12", alpha=0.25, label="Envelope Intra-bloco [Min, Max] (5 min)"
    )
    ax.plot(z_temp.index, z_temp["valor"], color="#7f8c8d", alpha=0.6, linewidth=0.8, label="Amostra Média (5 min)")
    ax.plot(z_temp.index, z_temp["mma_1h"], color="#c0392b", linewidth=1.6, label="Média Móvel 1h (12 amostras)")
    ax.plot(z_temp.index, z_temp["mma_6h"], color="#2c3e50", linewidth=1.5, linestyle="--", label="Média Móvel 6h (72 amostras)")
    sombrear_lacunas(ax, lac_z, limiar_min=15.0, label_unica=True)
    ax.set_title("A) Dinâmica de Curto Prazo, Volatilidade Intra-bloco e Médias Móveis — Temperatura (Nó 86811)")
    ax.set_ylabel("Temperatura (°C)")
    ax.legend(loc="upper right", ncol=2, frameon=True)

    # Umidade
    ax = axes[1]
    ax.fill_between(
        z_hum.index, z_hum["valor_min"], z_hum["valor_max"],
        color="#3498db", alpha=0.25, label="Envelope Intra-bloco [Min, Max] (5 min)"
    )
    ax.plot(z_hum.index, z_hum["valor"], color="#7f8c8d", alpha=0.6, linewidth=0.8, label="Amostra Média (5 min)")
    ax.plot(z_hum.index, z_hum["mma_1h"], color="#2980b9", linewidth=1.6, label="Média Móvel 1h (12 amostras)")
    sombrear_lacunas(ax, lac_z, limiar_min=15.0, label_unica=True)
    ax.set_title("B) Dinâmica de Curto Prazo e Médias Móveis — Umidade Relativa do Ar (Nó 86811)")
    ax.set_ylabel("Umidade Relativa (%)")
    ax.set_xlabel("Data (Recorte de 10 dias: 01/04/2026 a 11/04/2026)")
    ax.legend(loc="lower right", ncol=2, frameon=True)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    fig.autofmt_xdate(rotation=25)
    fig.tight_layout()
    caminho = OUT_DIR / "E3_fig2_zoom_10dias_medias_moveis_e_lacuna.png"
    fig.savefig(caminho, dpi=300)
    plt.close(fig)
    print(f"[OK] Figura 2 salva em: {caminho}")


def plot_fig3_contraste_agricola_solo_vs_ar(df: pd.DataFrame):
    """
    FIGURA 3: Estação Agrícola TCC MESSIAS (ID 86817).
    Contrasta a volatilidade atmosférica (Ar) com a inércia térmica e hídrica (Solo),
    justificando visualmente por que algoritmos orientados a eventos comprimem mais no solo.
    """
    s_tar, lac_tar = extrair_serie_grade_5min(df, id_disp=86817, nome_sensor="temperatura")
    s_tsolo, _ = extrair_serie_grade_5min(df, id_disp=86817, nome_sensor="temperatura_solo")
    s_uar, _ = extrair_serie_grade_5min(df, id_disp=86817, nome_sensor="umidade")
    s_usolo, _ = extrair_serie_grade_5min(df, id_disp=86817, nome_sensor="umidade_solo")

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

    # Painel A: Temperatura do Ar vs Solo
    ax = axes[0]
    ax.plot(s_tar.index, s_tar["valor"], color="#e67e22", alpha=0.45, linewidth=0.7, label="Temp. do Ar — Bruta (5 min)")
    ax.plot(s_tar.index, s_tar["mma_6h"], color="#d35400", linewidth=1.6, label="Temp. do Ar — Média Móvel 6h")
    ax.plot(s_tsolo.index, s_tsolo["valor"], color="#27ae60", alpha=0.5, linewidth=0.8, label="Temp. do Solo — Bruta (5 min)")
    ax.plot(s_tsolo.index, s_tsolo["mma_6h"], color="#1e8449", linewidth=1.8, label="Temp. do Solo — Média Móvel 6h (Alta Inércia)")
    sombrear_lacunas(ax, lac_tar, limiar_min=60.0, label_unica=True)
    ax.set_title("A) Coorte Agricola_Solo (Nó 86817 - TCC MESSIAS) | Atenuação e Defasagem Térmica: Ar vs. Solo")
    ax.set_ylabel("Temperatura (°C)")
    ax.legend(loc="upper right", ncol=2, frameon=True)

    # Painel B: Umidade do Ar vs Solo
    ax = axes[1]
    ax.plot(s_uar.index, s_uar["mma_1h"], color="#3498db", alpha=0.75, linewidth=1.1, label="Umidade Relativa do Ar (Média Móvel 1h)")
    ax.plot(s_usolo.index, s_usolo["mma_1h"], color="#8e44ad", linewidth=1.8, label="Umidade Capacitiva do Solo (Média Móvel 1h)")
    sombrear_lacunas(ax, lac_tar, limiar_min=60.0, label_unica=True)
    ax.set_title("B) Coorte Agricola_Solo (Nó 86817 - TCC MESSIAS) | Oscilação Diária do Ar vs. Curvas de Secagem/Recarga do Solo")
    ax.set_ylabel("Umidade (%)")
    ax.set_xlabel("Data (Julho a Setembro de 2026)")
    ax.legend(loc="lower left", ncol=2, frameon=True)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%Y"))
    fig.tight_layout()
    caminho = OUT_DIR / "E3_fig3_agricola_solo_vs_ar.png"
    fig.savefig(caminho, dpi=300)
    plt.close(fig)
    print(f"[OK] Figura 3 salva em: {caminho}")


def plot_fig4_dispersao_espacial_cluster_wide(incluir_no_falho: bool = False):
    """
    FIGURA 4: Análise do Transecto Espacial (Externo_Cluster) usando o arquivo wide.
    Por padrão (incluir_no_falho=False), utiliza os 8 nós íntegros nos 200 dias (coorte homogênea).
    """
    wide_path = DATA_DIR / "koala_cluster_externo_wide_5min.csv"
    df_w = pd.read_csv(wide_path, parse_dates=["timestamp"])
    df_temp = df_w[df_w["sensor"] == "temperatura"].sort_values("timestamp").set_index("timestamp")

    # Reindexa em grade de 5 min
    grade = pd.date_range(df_temp.index.min(), df_temp.index.max(), freq="5min")
    df_temp = df_temp.reindex(grade)

    # Filtra os 8 nós operacionais contínuos (exclui 1006EXT-TEMPHUM-04 que morreu em 15/05/2026)
    NO_FALHO = "1006EXT-TEMPHUM-04"
    colunas_nos = [
        c for c in df_temp.columns 
        if "EXT-TEMPHUM" in c and (incluir_no_falho or c != NO_FALHO)
    ]
    n_nos = len(colunas_nos)

    # Calcula Mediana Espacial M_t e Desvio Máximo Delta_max a cada 5 min
    mediana_espacial = df_temp[colunas_nos].median(axis=1)
    desvio_max = df_temp[colunas_nos].sub(mediana_espacial, axis=0).abs().max(axis=1)

    # Recorte de 7 dias em Abril para mostrar divergência local (condensadoras)
    ini, fim = "2026-04-10", "2026-04-17"
    sub_nos = df_temp.loc[ini:fim, colunas_nos]
    sub_med = mediana_espacial.loc[ini:fim]
    sub_dev = desvio_max.loc[ini:fim]

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)

    ax = axes[0]
    for col in colunas_nos:
        ax.plot(sub_nos.index, sub_nos[col], alpha=0.45, linewidth=0.9, label=col)
    ax.plot(sub_med.index, sub_med, color="black", linewidth=2.0, label=f"Mediana Espacial ($M_t$ - {n_nos} Nós)")
    ax.set_title(f"A) Coorte Externo_Cluster ({n_nos} Nós Homogêneos) | Correlação Espacial e Perturbações Térmicas")
    ax.set_ylabel("Temperatura (°C)")
    ax.legend(loc="upper right", ncol=3, fontsize=8, frameon=True)

    ax = axes[1]
    ax.plot(sub_dev.index, sub_dev, color="#c0392b", alpha=0.6, linewidth=0.9, label="Desvio Espacial Máximo Instantâneo ($\\Delta_{\\max}$)")
    ax.plot(sub_dev.index, sub_dev.rolling(12, min_periods=3).mean(), color="#922b21", linewidth=1.8, label="Média Móvel 1h de $\\Delta_{\\max}$")
    ax.axhline(2.0, color="#2c3e50", linestyle="--", linewidth=1.2, label="Limiar Espacial $\\tau_{\\text{espacial}} = 2,0^\\circ$C")
    ax.set_title("B) Divergência Espacial no Talhão Virtual ($\\Delta_{\\max} = \\max_i |v_i - M_t|$) para Decisão do Cluster Head")
    ax.set_ylabel("$\\Delta_{\\max}$ (°C)")
    ax.set_xlabel("Data (10/04/2026 a 17/04/2026)")
    ax.legend(loc="upper right", frameon=True)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))
    fig.autofmt_xdate(rotation=25)
    fig.tight_layout()
    caminho = OUT_DIR / f"E3_fig4_divergencia_espacial_cluster_head_{n_nos}nos.png"
    fig.savefig(caminho, dpi=300)
    plt.close(fig)
    print(f"[OK] Figura 4 ({n_nos} nós) salva em: {caminho}")

def main():
    csv_mestre = DATA_DIR / "koala_dataset_mestre_5min.csv"
    print(f"Carregando dataset mestre: {csv_mestre} ...")
    df = pd.read_csv(csv_mestre, parse_dates=["timestamp"])
    print(f"Total de registros carregados: {len(df):,}")

    plot_fig1_panorama_lacunas(df)
    plot_fig2_zoom_media_movel_envelope(df)
    plot_fig3_contraste_agricola_solo_vs_ar(df)
    plot_fig4_dispersao_espacial_cluster_wide(incluir_no_falho=False)
    print("\nConcluído! Todas as 5 figuras do Entregável E3 foram geradas na pasta 'figuras_e3/'.")


if __name__ == "__main__":
    main()