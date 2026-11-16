import os
from pathlib import Path
import requests
import pandas as pd
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

def autenticar():
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}

def main():
    headers = autenticar()
    devices = requests.get(f"{BASE_URL}/device", headers=headers, timeout=15).json()
    mappings = requests.get(f"{BASE_URL}/deviceTypeMapping", headers=headers, timeout=15).json()

    # Agora usando as chaves exatas que você descobriu: 'device_id' e 'type_id'!
    mapa_sensores = {}
    for m in mappings:
        d_id = m.get("device_id")
        t_id = m.get("type_id") 
        if d_id and t_id:
            mapa_sensores.setdefault(int(d_id), set()).add(int(t_id))

    # Janelas mensais leves em 2026 para não dar timeout
    janelas_2026 = [
        ("2026-03-01T00:00:00.000Z", "2026-04-30T23:59:59.000Z"),
        ("2026-07-01T00:00:00.000Z", "2026-08-31T23:59:59.000Z"),
        ("2026-09-01T00:00:00.000Z", "2026-10-28T23:59:59.000Z"),
    ]

    print("=== TESTANDO LABS 1006 (Amb 1), 1008 (Amb 2) E SENSORES EXTRAS EM 2026 ===")
    alvos = [d for d in devices if d.get("id_enviroment") in {1, 2} or d.get("id") == 86817]

    for d in alvos:
        id_dev = int(d["id"])
        name_dev = d["name"]
        id_env = int(d["id_enviroment"])
        sensores = sorted(mapa_sensores.get(id_dev, {1, 2}))

        for id_type in sensores:
            blocos = []
            for dt_ini, dt_fim in janelas_2026:
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
                        blocos.extend(validos)
                except Exception as e:
                    print(f"  [Timeout/Erro] Dev {id_dev} Sensor {id_type} ({dt_ini[:7]}): {e}")
                time.sleep(0.1)

            if blocos:
                datas = [x.get("time_interval") or x.get("time_intervall") for x in blocos]
                valores = [float(x["avg_value"]) for x in blocos]
                print(f"  [ATIVO 2026] Amb {id_env} | Dev {id_dev:5d} ({name_dev:24s}) | Sensor {id_type:2d} -> {len(blocos):4d} blocos ({min(datas)[:10]} a {max(datas)[:10]}) | Média: {sum(valores)/len(valores):.2f}")

if __name__ == "__main__":
    main()