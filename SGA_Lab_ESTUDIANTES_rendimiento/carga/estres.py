"""Fase IX - Prueba de estres (STR-025): carga progresiva con criterios de deteccion y recuperacion.
Sube la carga por niveles (misma logica de plan_SGA.jmx), mide cada nivel y se DETIENE al cumplirse un criterio
de parada. Despues baja a una carga normal para observar la RECUPERACION.

    python carga/estres.py --jmeter "C:\\apache-jmeter-5.6.3\\bin\\jmeter.bat" --niveles 100,200,300,400,500,600
    (validacion sin JMeter:  --motor python --niveles 5,10,15 --duracion 10)

Criterios (ajustables, acordar con el docente ANTES de ejecutar):
  DEGRADACION  error > 2 %  o  p95 > 5000 ms          -> se registra el primer nivel que la cumple
  DETENCION    error >= 10 % o p95 >= 10000 ms o CPU media del servidor >= 95 %  -> se detiene el incremento
  RECUPERACION al volver a --recuperacion usuarios: media <= 800 ms, p95 <= 2000 ms, error <= 1 %
Solo contra el entorno de pruebas local. Nunca contra sistemas productivos.
"""
import argparse, csv, subprocess, sys, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--motor", choices=["jmeter", "python"], default="jmeter")
ap.add_argument("--jmeter", help="ruta a jmeter.bat (motor jmeter)")
ap.add_argument("--niveles", default="100,200,300,400,500,600")
ap.add_argument("--duracion", type=int, default=180, help="segundos por nivel (incluye la rampa)")
ap.add_argument("--recuperacion", type=int, default=50)
ap.add_argument("--puerto", type=int, default=5000)
ap.add_argument("--descanso", type=int, default=30)
ap.add_argument("--degrad-error", type=float, default=2); ap.add_argument("--degrad-p95", type=int, default=5000)
ap.add_argument("--stop-error", type=float, default=10); ap.add_argument("--stop-p95", type=int, default=10000)
ap.add_argument("--stop-cpu", type=float, default=95)
a = ap.parse_args()
niveles = [int(x) for x in a.niveles.split(",")]
res_dir = Path("carga/resultados"); res_dir.mkdir(parents=True, exist_ok=True)
resumen = res_dir / "resumen_estres.csv"
if resumen.exists(): resumen.unlink()
if a.motor == "jmeter" and not a.jmeter: sys.exit("Indique --jmeter con la ruta de jmeter.bat")


def correr(caso, usuarios):
    rampa = max(2, int(a.duracion * 0.4))
    jtl = res_dir / f"{caso}.jtl"; rec = res_dir / f"{caso}_recursos.csv"
    mon = subprocess.Popen([sys.executable, "carga/monitor_recursos.py", "--puerto", str(a.puerto), "--salida", str(rec),
                            "--duracion", str(a.duracion + 10), "--intervalo", "2"], stdout=subprocess.DEVNULL)
    print(f"\n=== {caso}: {usuarios} usuarios virtuales, {a.duracion}s (rampa {rampa}s) ===", flush=True)
    if a.motor == "jmeter":
        rep = res_dir / f"{caso}_reporte"
        if rep.exists():
            import shutil; shutil.rmtree(rep)
        jtl.unlink(missing_ok=True)
        subprocess.run([a.jmeter, "-n", "-t", "carga/plan_SGA.jmx", f"-Jusuarios={usuarios}", f"-Jrampa={rampa}", f"-Jduracion={a.duracion}",
                        f"-Jpuerto={a.puerto}", "-Jjmeter.save.saveservice.subresults=false", "-l", str(jtl), "-e", "-o", str(rep)])
    else:
        subprocess.run([sys.executable, "carga/escenario_carga.py", "--usuarios", str(usuarios), "--rampa", str(rampa), "--duracion", str(a.duracion),
                        "--puerto", str(a.puerto), "--pensar", "0.5", "--salida", str(jtl)])
    mon.wait()
    subprocess.run([sys.executable, "carga/resumir_resultados.py", "--jtl", str(jtl), "--caso", caso, "--usuarios", str(usuarios),
                    "--recursos", str(rec), "--salida", str(resumen)], stdout=subprocess.DEVNULL)
    filas = list(csv.DictReader(open(resumen, encoding="utf-8-sig"), delimiter=";"))
    f = filas[-1]
    return {k: float(f[k]) if f[k] not in ("", None) and k != "caso" else f[k] for k in f}


tabla, degrad, parada = [], None, None
for i, u in enumerate(niveles, 1):
    m = correr(f"STR-025-N{i}-{u}", u)
    cpu = m.get("cpu_media_pct") or 0
    estado = "ESTABLE"
    if m["error_pct"] > a.degrad_error or m["p95_ms"] > a.degrad_p95:
        estado = "DEGRADACION"; degrad = degrad or u
    if m["error_pct"] >= a.stop_error or m["p95_ms"] >= a.stop_p95 or cpu >= a.stop_cpu:
        estado = "DETENCION"; parada = u
    tabla.append((u, m["media_ms"], m["p95_ms"], m["error_pct"], m["solicitudes_por_s"], cpu, estado))
    print(f"-> {u} usuarios: media {m['media_ms']:.0f} ms, p95 {m['p95_ms']:.0f} ms, errores {m['error_pct']}%, CPU {cpu}% => {estado}", flush=True)
    if parada:
        print(f"CRITERIO DE DETENCION CUMPLIDO en {u} usuarios: se detiene el incremento."); break
    time.sleep(a.descanso)

print(f"\nDescanso de {a.descanso}s y prueba de recuperacion con {a.recuperacion} usuarios ...")
time.sleep(a.descanso)
r = correr("STR-025-RECUPERACION", a.recuperacion)
recupera = r["media_ms"] <= 800 and r["p95_ms"] <= 2000 and r["error_pct"] <= 1

print("\n" + "=" * 86 + "\nRESULTADO STR-025 - PRUEBA DE ESTRES\n" + "=" * 86)
print(f"{'Usuarios':>9}{'Media ms':>10}{'p95 ms':>9}{'Error %':>9}{'Req/s':>8}{'CPU %':>7}  Estado")
for t in tabla: print(f"{t[0]:>9}{t[1]:>10.0f}{t[2]:>9.0f}{t[3]:>9.2f}{t[4]:>8.1f}{t[5]:>7.1f}  {t[6]}")
print(f"\nPrimer nivel con degradacion : {degrad if degrad else 'no se alcanzo en los niveles ejecutados'}")
print(f"Nivel de detencion           : {parada if parada else 'no se alcanzo (se ejecutaron todos los niveles)'}")
print(f"Recuperacion a {a.recuperacion} usuarios   : media {r['media_ms']:.0f} ms, p95 {r['p95_ms']:.0f} ms, error {r['error_pct']}%  => "
      + ("RECUPERA" if recupera else "NO RECUPERA (revisar reinicio del servicio)"))
with open(res_dir / "estres_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";"); w.writerow(["usuarios", "media_ms", "p95_ms", "error_pct", "req_s", "cpu_pct", "estado"]); w.writerows(tabla)
    w.writerow(["recuperacion", r["media_ms"], r["p95_ms"], r["error_pct"], r["solicitudes_por_s"], r.get("cpu_media_pct", ""), "RECUPERA" if recupera else "NO RECUPERA"])
