import os
import time
import math
from pathlib import Path
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
if ENV_FILE.exists():
    for _line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if _line.strip() and not _line.strip().startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

BASE_URL = os.getenv("KOALA_BASE_URL", "http://andromeda.lasdpc.icmc.usp.br:60106")
USERNAME = os.getenv("KOALA_USERNAME", "")
PASSWORD = os.getenv("KOALA_PASSWORD", "")

OUTPUT_DIR = str(ROOT_DIR / "dataset_koala_e2")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Período Ouro: 01/03/2026 a 16/09/2026 (200 dias, cortando antes do apagão de fim de setembro/outubro)
START_DATE = datetime(2026, 3, 1, 0, 0, 0)
END_DATE   = datetime(2026, 9, 16, 23, 59, 59)
TIME_BUCKET = "5 minutes"
T_NOMINAL_MIN = 5.0

SENSORES_INFO = {
    1:  {"nome": "temperatura",      "unidade": "C",       "min": -10.0, "max": 65.0},
    2:  {"nome": "umidade",          "unidade": "%",       "min": 0.0,   "max": 100.0},
    10: {"nome": "luminosidade",     "unidade": "lux_adc", "min": 0.0,   "max": 5000.0},
    13: {"nome": "umidade_solo",     "unidade": "%",       "min": 0.0,   "max": 100.0},
    14: {"nome": "temperatura_solo", "unidade": "C",       "min": -5.0,  "max": 60.0},
    15: {"nome": "fluxo",            "unidade": "L_min",   "min": 0.0,   "max": 100.0},
}

ALVOS = [
    # Coorte 1: Externo Cluster (Talhão Virtual + 86812 com falha em maio)
    {"id": 86809, "nome": "1006EXT-TEMPHUM-01", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86811, "nome": "1006EXT-TEMPHUM-03", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86812, "nome": "1006EXT-TEMPHUM-04", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86813, "nome": "1006EXT-TEMPHUM-05", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86814, "nome": "1008EXT-TEMPHUM-01", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86784, "nome": "1008EXT-TEMPHUM-03", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86785, "nome": "1008EXT-TEMPHUM-04", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 86783, "nome": "1008EXT-TEMPHUM-05", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    {"id": 46,    "nome": "1008EXT-TEMPHUM-06", "id_env": 4, "ambiente": "Externo", "coorte": "Externo_Cluster", "sensores": [1, 2]},
    
    # Coorte 2: Agrícola Solo (Ativo a partir de 28/05 e 01/07)
    {"id": 86817, "nome": "TCC MESSIAS",        "id_env": 4, "ambiente": "Externo", "coorte": "Agricola_Solo",   "sensores": [1, 2, 13, 14, 15]},
    
    # Coorte 3: Indoor Baseline (Regime Estável + Luminosidade)
    {"id": 1,     "nome": "TEMP2",              "id_env": 1, "ambiente": "1006",    "coorte": "Indoor_Baseline", "sensores": [1, 2, 10]},
    {"id": 86782, "nome": "TEMP4",              "id_env": 1, "ambiente": "1006",    "coorte": "Indoor_Baseline", "sensores": [1, 2, 10]},
    
    # Coorte 4: Cluster Server (Ativo a partir de 01/07, inclui anomalia térmica)
    {"id": 86794, "nome": "1006CLUSTER-TEMPHUM-01", "id_env": 3, "ambiente": "Cluster 1006", "coorte": "Cluster_Server", "sensores": [1, 2]},
    {"id": 86795, "nome": "1006CLUSTER-TEMPHUM-02", "id_env": 3, "ambiente": "Cluster 1006", "coorte": "Cluster_Server", "sensores": [1, 2]},
]

def autenticar():
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}

def gerar_janelas_com_overlap(dt_ini, dt_fim, dias_passo=10, horas_overlap=12):
    """Gera janelas com sobreposição de 12h para evitar perda de borda por conversão UTC/BRT na API."""
    janelas = []
    atual = dt_ini
    while atual < dt_fim:
        prox = min(atual + timedelta(days=dias_passo), dt_fim)
        janelas.append((
            atual.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            prox.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        ))
        if prox >= dt_fim:
            break
        atual = prox - timedelta(hours=horas_overlap)
    return janelas

def parse_float_seguro(val):
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None

def requisitar_bloco(headers, payload, max_tentativas=3):
    for tentativa in range(1, max_tentativas + 1):
        try:
            r = requests.post(f"{BASE_URL}/datastream/filter", headers=headers, json=payload, timeout=25)
            if r.status_code == 200 and isinstance(r.json(), list):
                return r.json(), headers
            elif r.status_code == 401:
                headers = autenticar()
        except Exception as e:
            print(f"    [Aviso] Tentativa {tentativa}/{max_tentativas} falhou ({e}). Retentando...")
            time.sleep(1.5 * tentativa)
    return [], headers

def main():
    print("=== EXTRAÇÃO DEFINITIVA KOALA (01/03/2026 A 16/09/2026 COM OVERLAP DE FUSO) ===")
    headers = autenticar()
    janelas = gerar_janelas_com_overlap(START_DATE, END_DATE, dias_passo=10, horas_overlap=12)
    print(f"[OK] Total de {len(janelas)} janelas de 10 dias (overlap de 12h) | Bucket: {TIME_BUCKET}\n")

    # 1. Salvar Dicionário de Dispositivos
    df_meta = pd.DataFrame(ALVOS)
    df_meta["sensores"] = df_meta["sensores"].apply(lambda lista: ",".join(map(str, lista)))
    caminho_meta = os.path.join(OUTPUT_DIR, "koala_dicionario_dispositivos.csv")
    df_meta.to_csv(caminho_meta, index=False, encoding="utf-8")

    registros_limpos = []
    relatorio_qos = []

    for dev in ALVOS:
        id_dev = dev["id"]
        nome_dev = dev["nome"]
        id_env = dev["id_env"]
        ambiente = dev["ambiente"]
        coorte = dev["coorte"]

        for id_sensor in dev["sensores"]:
            s_info = SENSORES_INFO[id_sensor]
            nome_sensor = s_info["nome"]
            unidade = s_info["unidade"]
            lim_min, lim_max = s_info["min"], s_info["max"]

            print(f"-> Extraindo Dev {id_dev:5d} ({nome_dev:22s}) | Sensor {id_sensor:2d} ({nome_sensor:16s})...", end=" ", flush=True)
            blocos_brutos = []

            for dt_ini, dt_fim in janelas:
                payload = {
                    "startDate": dt_ini,
                    "endDate": dt_fim,
                    "idDeviceType": id_sensor,
                    "idEnviroment": id_env,
                    "idDevice": id_dev,
                    "timeBucket": TIME_BUCKET
                }
                dados_janela, headers = requisitar_bloco(headers, payload)
                blocos_brutos.extend([x for x in dados_janela if isinstance(x, dict)])
                time.sleep(0.04)

            # Desduplicar blocos brutos pelo timestamp antes de auditar NaNs (por causa do overlap de 12h)
            vistos_ts = set()
            blocos_unicos = []
            for b in blocos_brutos:
                ts_raw = b.get("time_interval") or b.get("time_intervall")
                if ts_raw and ts_raw not in vistos_ts:
                    vistos_ts.add(ts_raw)
                    blocos_unicos.append(b)

            total_retornado = len(blocos_unicos)
            qtd_nans = 0
            qtd_outliers = 0
            timestamps_validos = []

            for b in blocos_unicos:
                ts_raw = b.get("time_interval") or b.get("time_intervall")
                v_avg = parse_float_seguro(b.get("avg_value"))
                v_min = parse_float_seguro(b.get("min_value"))
                v_max = parse_float_seguro(b.get("max_value"))

                if v_avg is None:
                    qtd_nans += 1
                    continue

                if not (lim_min <= v_avg <= lim_max):
                    qtd_outliers += 1
                    continue

                timestamps_validos.append(ts_raw)
                registros_limpos.append({
                    "timestamp": ts_raw,
                    "id_dispositivo": id_dev,
                    "nome_dispositivo": nome_dev,
                    "ambiente": ambiente,
                    "coorte": coorte,
                    "id_sensor": id_sensor,
                    "sensor": nome_sensor,
                    "valor": round(v_avg, 4),
                    "valor_min": round(v_min, 4) if v_min is not None else round(v_avg, 4),
                    "valor_max": round(v_max, 4) if v_max is not None else round(v_avg, 4),
                    "unidade": unidade
                })

            qtd_validos = len(timestamps_validos)
            if qtd_validos > 1:
                s_dt = pd.to_datetime(pd.Series(timestamps_validos)).sort_values().drop_duplicates()
                qtd_unicos = len(s_dt)
                span_min = (s_dt.iloc[-1] - s_dt.iloc[0]).total_seconds() / 60.0
                n_esperado = int(span_min / T_NOMINAL_MIN) + 1 if span_min > 0 else qtd_unicos
                pdr_bruto = min(100.0, (qtd_unicos / n_esperado) * 100.0)

                deltas_min = s_dt.diff().dropna().dt.total_seconds() / 60.0
                gaps = deltas_min[deltas_min > (3.0 * T_NOMINAL_MIN)]
                estaveis = deltas_min[deltas_min <= (3.0 * T_NOMINAL_MIN)]

                # Descontando apagões globais (> 12h = 720 min) para estimar PDR intrínseco da rede/nó
                apagoes_servidor_min = gaps[gaps >= 720.0].sum()
                span_ativo_min = max(span_min - apagoes_servidor_min, T_NOMINAL_MIN)
                n_esperado_ativo = int(span_ativo_min / T_NOMINAL_MIN) + 1
                pdr_ativo = min(100.0, (qtd_unicos / n_esperado_ativo) * 100.0)

                jitter_medio = float(estaveis.mean()) if len(estaveis) > 0 else np.nan
                jitter_std = float(estaveis.std()) if len(estaveis) > 0 else np.nan
                qtd_gaps = int(len(gaps))
                mttr_min = float(gaps.mean()) if qtd_gaps > 0 else 0.0
                maior_gap_min = float(gaps.max()) if qtd_gaps > 0 else 0.0
                dt_primeiro, dt_ultimo = str(s_dt.iloc[0]), str(s_dt.iloc[-1])
            else:
                qtd_unicos, n_esperado, pdr_bruto, pdr_ativo = qtd_validos, 0, 0.0, 0.0
                jitter_medio, jitter_std, qtd_gaps, mttr_min, maior_gap_min = 0.0, 0.0, 0, 0.0, 0.0
                dt_primeiro, dt_ultimo = "", ""

            relatorio_qos.append({
                "id_dispositivo": id_dev,
                "nome_dispositivo": nome_dev,
                "ambiente": ambiente,
                "coorte": coorte,
                "id_sensor": id_sensor,
                "sensor": nome_sensor,
                "inicio_serie": dt_primeiro,
                "fim_serie": dt_ultimo,
                "blocos_retornados_api": total_retornado,
                "blocos_nan_hardware": qtd_nans,
                "blocos_outlier_fisico": qtd_outliers,
                "amostras_validas_unicas": qtd_unicos,
                "amostras_esperadas_5min": n_esperado,
                "pdr_empirico_global_pct": round(pdr_bruto, 2),
                "pdr_sem_apagao_servidor_pct": round(pdr_ativo, 2),
                "intervalo_medio_min": round(jitter_medio, 3),
                "jitter_std_min": round(jitter_std, 3),
                "qtd_lacunas_maior_15min": qtd_gaps,
                "mttr_medio_lacunas_min": round(mttr_min, 2),
                "maior_lacuna_min": round(maior_gap_min, 2)
            })
            print(f"OK! Válidos: {qtd_unicos:5d} | PDR Global: {pdr_bruto:5.1f}% (Ativo: {pdr_ativo:5.1f}%) | Gaps: {qtd_gaps}")

    # 2. Salvar Auditoria de QoS Empírico
    df_qos = pd.DataFrame(relatorio_qos)
    caminho_qos = os.path.join(OUTPUT_DIR, "koala_auditoria_qos_bruto.csv")
    df_qos.to_csv(caminho_qos, index=False, encoding="utf-8")
    print(f"\n[OK] Relatório de QoS Empírico salvo em: {caminho_qos}")

    # 3. Salvar Dataset Mestre Formato Longo
    df_long = pd.DataFrame(registros_limpos)
    df_long = df_long.drop_duplicates(subset=["timestamp", "id_dispositivo", "id_sensor"])
    df_long = df_long.sort_values(by=["timestamp", "id_dispositivo", "id_sensor"]).reset_index(drop=True)
    caminho_long = os.path.join(OUTPUT_DIR, "koala_dataset_mestre_5min.csv")
    df_long.to_csv(caminho_long, index=False, encoding="utf-8")
    print(f"[OK] Dataset Mestre salvo em: {caminho_long} ({len(df_long)} linhas)")

    # 4. Salvar Dataset Pivotado (Wide) para Cluster Externo
    df_ext = df_long[df_long["coorte"] == "Externo_Cluster"].copy()
    if not df_ext.empty:
        df_wide = df_ext.pivot_table(
            index=["timestamp", "sensor", "unidade"],
            columns="nome_dispositivo",
            values="valor",
            aggfunc="first"
        ).reset_index()
        df_wide = df_wide.sort_values(by=["sensor", "timestamp"]).reset_index(drop=True)
        caminho_wide = os.path.join(OUTPUT_DIR, "koala_cluster_externo_wide_5min.csv")
        df_wide.to_csv(caminho_wide, index=False, encoding="utf-8")
        print(f"[OK] Dataset Cluster Externo (Wide) salvo em: {caminho_wide} ({len(df_wide)} linhas)")

    print("\n=== EXTRAÇÃO FINALIZADA COM SUCESSO! ===")

if __name__ == "__main__":
    main()