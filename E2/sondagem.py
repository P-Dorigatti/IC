import os
from pathlib import Path
import requests
import pandas as pd
from datetime import datetime
import time

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

TARGET_ENVIRONMENTS = {1, 2, 3, 4, 6}

def autenticar():
    url = f"{BASE_URL}/auth/login"
    resp = requests.post(url, json={"username": USERNAME, "password": PASSWORD}, timeout=15)
    resp.raise_for_status()
    token = resp.json().get("token")
    print("[OK] Autenticado com sucesso!")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def get_json(headers, endpoint):
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

def extrair_timestamp(item):
    """Lida com o typo 'time_intervall' visto no vídeo ou variações."""
    return (
        item.get("time_intervall") 
        or item.get("time_interval") 
        or item.get("timestamp") 
        or item.get("date")
    )

def main():
    headers = autenticar()
    
    # 1. Busca Devices e DeviceTypeMappings separados (como visto no Swagger)
    devices = get_json(headers, "/device")
    print(f"[OK] Total de dispositivos retornados em /device: {len(devices)}")
    if devices:
        print(f"     Exemplo de chaves em /device: {list(devices[0].keys())}")

    try:
        mappings = get_json(headers, "/deviceTypeMapping")
        print(f"[OK] Total de mapeamentos em /deviceTypeMapping: {len(mappings)}")
        if mappings:
            print(f"     Exemplo de item em /deviceTypeMapping: {mappings[0]}")
    except Exception as e:
        print(f"[Aviso] Não foi possível ler /deviceTypeMapping: {e}")
        mappings = []

    # Constrói dicionário: id_device -> lista de id_device_type
    mapa_dev_sensores = {}
    for m in mappings:
        # Tenta capturar diferentes formatos de chave que a API pode usar
        d_id = m.get("id_device") or m.get("idDevice") or (m.get("device") or {}).get("id")
        t_id = m.get("id_device_type") or m.get("idDeviceType") or (m.get("device_type") or {}).get("id")
        if d_id and t_id:
            mapa_dev_sensores.setdefault(int(d_id), set()).add(int(t_id))

    # 2. DESCOBERTA DE PERÍODO ATIVO POR AMBIENTE (2024, 2025 e 2026)
    # Fazemos um teste rápido sem idDevice (média do ambiente) para ver onde estão os dados no banco!
    print("\n=== ETAPA 1: DESCOBRINDO EM QUAIS ANOS/MESES HÁ DADOS NOS AMBIENTES ===")
    janelas_teste = [
        ("2024_S2", "2024-07-01T00:00:00.000Z", "2024-12-31T23:59:59.000Z"),
        ("2025_S1", "2025-01-01T00:00:00.000Z", "2025-06-30T23:59:59.000Z"),
        ("2025_S2", "2025-07-01T00:00:00.000Z", "2025-12-31T23:59:59.000Z"),
        ("2026_S1", "2026-01-01T00:00:00.000Z", "2026-06-30T23:59:59.000Z"),
        ("2026_S2", "2026-07-01T00:00:00.000Z", "2026-10-28T23:59:59.000Z"),
    ]

    primeiro_exemplo_impresso = False
    janelas_ativas_por_amb = {}

    for id_env in sorted(TARGET_ENVIRONMENTS):
        for nome_jan, dt_ini, dt_fim in janelas_teste:
            payload = {
                "startDate": dt_ini,
                "endDate": dt_fim,
                "idDeviceType": 1, # Temperatura como referência
                "idEnviroment": id_env,
                "timeBucket": "2 hours"
            }
            try:
                r = requests.post(f"{BASE_URL}/datastream/filter", headers=headers, json=payload, timeout=20)
                if r.status_code == 200:
                    dados = r.json()
                    validos = [x for x in dados if isinstance(x, dict) and x.get("avg_value") is not None]
                    if validos:
                        if not primeiro_exemplo_impresso:
                            print(f"\n[DEBUG] Exemplo real de resposta do /datastream/filter:\n{validos[0]}\n")
                            primeiro_exemplo_impresso = True
                        datas = [extrair_timestamp(x) for x in validos if extrair_timestamp(x)]
                        print(f"  [!] Ambiente {id_env} | Janela {nome_jan}: {len(validos)} blocos (de {min(datas)[:10]} a {max(datas)[:10]})")
                        janelas_ativas_por_amb.setdefault(id_env, []).append((dt_ini, dt_fim))
            except Exception as e:
                print(f"  [Erro] Amb {id_env} na janela {nome_jan}: {e}")

    # 3. SONDAGEM POR DISPOSITIVO INDIVIDUAL
    print("\n=== ETAPA 2: SONDANDO DISPOSITIVOS INDIVIDUAIS ===")
    devs_filtrados = [d for d in devices if d.get("id_enviroment") in TARGET_ENVIRONMENTS]
    relatorio = []

    for d in devs_filtrados:
        id_dev = int(d.get("id"))
        name_dev = d.get("name")
        id_env = int(d.get("id_enviroment"))
        available = d.get("available")

        # Pega sensores mapeados ou testa [1 (Temp), 2 (Hum)] por padrão
        sensores = sorted(mapa_dev_sensores.get(id_dev, {1, 2}))
        
        # Usa as janelas onde o ambiente teve dados (ou testa 2024_S2 e 2026_S2 se vazio)
        janelas_busca = janelas_ativas_por_amb.get(id_env, [
            ("2024-07-01T00:00:00.000Z", "2024-12-31T23:59:59.000Z"),
            ("2026-07-01T00:00:00.000Z", "2026-10-28T23:59:59.000Z")
        ])

        for id_type in sensores:
            pontos_totais = []
            for dt_ini, dt_fim in janelas_busca:
                payload = {
                    "startDate": dt_ini,
                    "endDate": dt_fim,
                    "idDeviceType": id_type,
                    "idEnviroment": id_env,
                    "idDevice": id_dev,
                    "timeBucket": "2 hours"
                }
                try:
                    r = requests.post(f"{BASE_URL}/datastream/filter", headers=headers, json=payload, timeout=20)
                    if r.status_code == 200 and isinstance(r.json(), list):
                        validos = [x for x in r.json() if isinstance(x, dict) and x.get("avg_value") is not None]
                        pontos_totais.extend(validos)
                except Exception as e:
                    pass
                time.sleep(0.1)

            if pontos_totais:
                valores = [float(p["avg_value"]) for p in pontos_totais]
                datas = [extrair_timestamp(p) for p in pontos_totais if extrair_timestamp(p)]
                dt_min = min(datas) if datas else "N/A"
                dt_max = max(datas) if datas else "N/A"
                print(f"  [ATIVO] Amb {id_env} | Dev {id_dev:5d} ({name_dev:22s}) | Sensor {id_type:2d} -> {len(pontos_totais):4d} blocos ({dt_min[:10]} a {dt_max[:10]})")
                relatorio.append({
                    "id_enviroment": id_env,
                    "id_device": id_dev,
                    "device_name": name_dev,
                    "available_now": available,
                    "id_device_type": id_type,
                    "blocos_2h_com_dados": len(pontos_totais),
                    "primeira_leitura": dt_min,
                    "ultima_leitura": dt_max,
                    "media_geral": round(sum(valores)/len(valores), 2),
                    "min_geral": round(min(valores), 2),
                    "max_geral": round(max(valores), 2)
                })
            else:
                relatorio.append({
                    "id_enviroment": id_env,
                    "id_device": id_dev,
                    "device_name": name_dev,
                    "available_now": available,
                    "id_device_type": id_type,
                    "blocos_2h_com_dados": 0,
                    "primeira_leitura": None,
                    "ultima_leitura": None,
                    "media_geral": None,
                    "min_geral": None,
                    "max_geral": None
                })

    df_rel = pd.DataFrame(relatorio)
    if not df_rel.empty:
        df_rel = df_rel.sort_values(by=["blocos_2h_com_dados", "id_enviroment"], ascending=[False, True])
        df_rel.to_csv("relatorio_sensores_uteis.csv", index=False)
        
        print("\n=== TOP SENSORES COM DADOS ÚTEIS ===")
        uteis = df_rel[df_rel["blocos_2h_com_dados"] > 0]
        if not uteis.empty:
            print(uteis.to_string(index=False))
        else:
            print("Nenhum dispositivo individual retornou dados com idDevice preenchido. Verifique a saída da Etapa 1 acima!")
    else:
        print("A lista de dispositivos veio vazia.")

if __name__ == "__main__":
    main()