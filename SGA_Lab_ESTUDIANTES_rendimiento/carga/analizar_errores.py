"""Diagnostico de una prueba de estres: ¿que errores hubo y cuando empezaron?
    python carga\\analizar_errores.py --jtl res_estres.jtl [--ventana 30]
Muestra: 1) errores por operacion/codigo/mensaje, 2) evolucion por ventana de tiempo (usuarios activos,
solicitudes/s, solicitudes EXITOSAS/s, errores %, media, p95) y 3) la primera ventana que cumple los
criterios de degradacion (error > 2 % o p95 > 5000 ms) y de detencion (error >= 10 % o p95 >= 10000 ms).
Sirve con el .jtl de JMeter (CSV) y con el generado por escenario_carga.py.
"""
import argparse, csv, math, re
from collections import Counter

ap = argparse.ArgumentParser()
ap.add_argument("--jtl", required=True); ap.add_argument("--ventana", type=int, default=30)
ap.add_argument("--incluir-sub", action="store_true", help="contar tambien las sub-muestras de redireccion (etiquetas ...-0, ...-1)")
a = ap.parse_args()


def pct(v, p):
    v = sorted(v); return v[max(0, math.ceil(p / 100 * len(v)) - 1)] if v else 0


filas = list(csv.DictReader(open(a.jtl, encoding="utf-8", errors="replace")))
if not a.incluir_sub:  # las sub-muestras (label-0, label-1) duplican la peticion y diluyen la tasa de error
    n0 = len(filas); filas = [f for f in filas if not re.search(r"-\d+$", f["label"])]
    print(f"(Se excluyen {n0 - len(filas)} sub-muestras de redireccion; use --incluir-sub para contarlas)")
if not filas: raise SystemExit("El archivo no tiene muestras.")
ok = lambda f: f["success"].lower() == "true"
t0 = min(int(f["timeStamp"]) for f in filas)
print(f"Muestras: {len(filas)}   Errores: {sum(not ok(f) for f in filas)} ({100*sum(not ok(f) for f in filas)/len(filas):.1f} %)\n")

print("1) ERRORES POR TIPO (operacion | codigo | mensaje)")
c = Counter((f["label"], f.get("responseCode", ""), (f.get("responseMessage") or f.get("failureMessage") or "")[:70]) for f in filas if not ok(f))
for (lab, cod, msg), n in c.most_common(8): print(f"  {n:>7}  {lab:<22} {cod:<28} {msg}")
print("\n   Errores por operacion:")
for lab in sorted({f["label"] for f in filas}):
    s = [f for f in filas if f["label"] == lab]
    print(f"   {lab:<24}{len(s):>8} muestras  {100*sum(not ok(f) for f in s)/len(s):>6.1f} % error")

print(f"\n2) EVOLUCION CADA {a.ventana} s")
print(f"{'min:seg':>8}{'usuarios':>9}{'req/s':>8}{'exitosas/s':>11}{'error %':>9}{'media':>7}{'p95':>7}  estado")
primera_deg = primera_stop = None
vent = {}
for f in filas: vent.setdefault((int(f["timeStamp"]) - t0) // (a.ventana * 1000), []).append(f)
for k in sorted(vent):
    s = vent[k]; e = [int(x["elapsed"]) for x in s]; err = 100 * sum(not ok(x) for x in s) / len(s)
    us = max(int(x.get("allThreads") or 0) for x in s); p95 = pct(e, 95)
    est = "ESTABLE"
    if err > 2 or p95 > 5000: est = "DEGRADACION"; primera_deg = primera_deg or (k, us)
    if err >= 10 or p95 >= 10000: est = "DETENCION"; primera_stop = primera_stop or (k, us)
    seg = k * a.ventana
    print(f"{seg//60:>4}:{seg%60:02d}{us:>9}{len(s)/a.ventana:>8.1f}{sum(ok(x) for x in s)/a.ventana:>11.1f}{err:>9.1f}{sum(e)/len(e):>7.0f}{p95:>7}  {est}")
fmt = lambda x: "no se alcanzo" if not x else f"minuto {x[0]*a.ventana//60}:{x[0]*a.ventana%60:02d} con {x[1]} usuarios activos"
print(f"\n3) Primera ventana con DEGRADACION: {fmt(primera_deg)}\n   Primera ventana con DETENCION  : {fmt(primera_stop)}")
