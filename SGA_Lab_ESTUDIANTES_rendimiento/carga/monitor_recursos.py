"""Mide CPU y memoria del proceso del servidor mientras corre la prueba de carga.
    python carga/monitor_recursos.py --salida carga/resultados/LOAD-021_recursos.csv --duracion 300
Busca solo el proceso que escucha en el puerto (por defecto 5000). Si no lo encuentra: --pid <numero>.
Requiere:  python -m pip install psutil
"""
import argparse, csv, time
from datetime import datetime
import psutil

ap = argparse.ArgumentParser()
ap.add_argument("--puerto", type=int, default=5000)
ap.add_argument("--pid", type=int)
ap.add_argument("--duracion", type=int, default=300, help="segundos a medir")
ap.add_argument("--intervalo", type=float, default=2.0)
ap.add_argument("--salida", default="recursos.csv")
a = ap.parse_args()

pid = a.pid
if pid is None:
    for c in psutil.net_connections(kind="tcp"):
        if c.status == psutil.CONN_LISTEN and c.laddr.port == a.puerto and c.pid:
            pid = c.pid; break
if pid is None:
    raise SystemExit(f"No encontre un proceso escuchando en el puerto {a.puerto}. Inicie el servidor o use --pid.")
p = psutil.Process(pid); p.cpu_percent(None); psutil.cpu_percent(None)
print(f"Midiendo PID {pid} ({p.name()}) durante {a.duracion}s ...")
with open(a.salida, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["hora", "cpu_proceso_pct", "cpu_total_pct", "memoria_proceso_mb"])
    fin = time.time() + a.duracion
    while time.time() < fin:
        time.sleep(a.intervalo)
        try:
            w.writerow([datetime.now().strftime("%H:%M:%S"), p.cpu_percent(None) / psutil.cpu_count(),
                        psutil.cpu_percent(None), round(p.memory_info().rss / 1048576, 1)]); fh.flush()
        except psutil.NoSuchProcess:
            print("El proceso del servidor termino."); break
print("Listo:", a.salida, "(cpu_proceso_pct esta normalizado a 0-100 % del total de nucleos)")
