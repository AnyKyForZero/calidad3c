"""Calcula los indicadores que pide la guia a partir del .jtl (JMeter o escenario_carga.py).
    python carga/resumir_resultados.py --jtl carga/resultados/LOAD-021.jtl --caso LOAD-021 --usuarios 50 \
        --recursos carga/resultados/LOAD-021_recursos.csv
Muestra: usuarios, duracion, media, p90, p95, tasa de errores, solicitudes/s, CPU y memoria,
y agrega una fila a carga/resultados/resumen_rendimiento.csv. Percentiles: metodo del rango mas cercano (como JMeter).
"""
import argparse, csv, math
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--jtl", required=True); ap.add_argument("--caso", default="LOAD-XXX")
ap.add_argument("--usuarios", type=int, default=0); ap.add_argument("--recursos")
ap.add_argument("--salida", default="carga/resultados/resumen_rendimiento.csv")
a = ap.parse_args()


def pct(v, p):
    v = sorted(v); return v[max(0, math.ceil(p / 100 * len(v)) - 1)] if v else 0


filas = list(csv.DictReader(open(a.jtl, encoding="utf-8")))
if not filas: raise SystemExit("El archivo no tiene muestras.")
t = [int(f["elapsed"]) for f in filas]
errores = sum(f["success"].lower() != "true" for f in filas)
ini = min(int(f["timeStamp"]) for f in filas); fin = max(int(f["timeStamp"]) + int(f["elapsed"]) for f in filas)
dur = (fin - ini) / 1000
usuarios = a.usuarios or max(int(f.get("allThreads", 0) or 0) for f in filas)
res = {"caso": a.caso, "usuarios": usuarios, "duracion_s": round(dur), "muestras": len(filas),
       "media_ms": round(sum(t) / len(t)), "p90_ms": pct(t, 90), "p95_ms": pct(t, 95), "p99_ms": pct(t, 99),
       "error_pct": round(100 * errores / len(filas), 2), "solicitudes_por_s": round(len(filas) / dur, 1)}
if a.recursos and Path(a.recursos).exists():
    r = list(csv.DictReader(open(a.recursos, encoding="utf-8")))
    cpu = [float(x["cpu_proceso_pct"]) for x in r]; mem = [float(x["memoria_proceso_mb"]) for x in r]
    res.update(cpu_media_pct=round(sum(cpu) / len(cpu), 1), cpu_pico_pct=round(max(cpu), 1),
               mem_inicio_mb=mem[0], mem_max_mb=max(mem))
print("\n" + "=" * 70 + f"\nRESUMEN {a.caso}\n" + "=" * 70)
for k, v in res.items(): print(f"{k:<20}{v}")
print("\nPor operacion:\n" + f"{'operacion':<24}{'n':>7}{'media':>8}{'p90':>8}{'p95':>8}{'error%':>8}")
for lab in sorted({f['label'] for f in filas}):
    s = [f for f in filas if f["label"] == lab]; tt = [int(f["elapsed"]) for f in s]
    print(f"{lab:<24}{len(s):>7}{round(sum(tt)/len(tt)):>8}{pct(tt,90):>8}{pct(tt,95):>8}{100*sum(f['success'].lower()!='true' for f in s)/len(s):>8.1f}")
Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
nuevo = not Path(a.salida).exists()
with open(a.salida, "a", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["caso","usuarios","duracion_s","muestras","media_ms","p90_ms","p95_ms","p99_ms","error_pct","solicitudes_por_s","cpu_media_pct","cpu_pico_pct","mem_inicio_mb","mem_max_mb"], delimiter=";", restval="")
    if nuevo: w.writeheader()
    w.writerow(res)
print("\nFila agregada a", a.salida)
