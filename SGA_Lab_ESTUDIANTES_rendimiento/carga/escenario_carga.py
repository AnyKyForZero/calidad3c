"""Generador de carga alternativo en Python (misma logica que plan_SGA.jmx).
Sirve para validar el escenario con pocos usuarios y como contraste si JMeter no esta disponible.
Escribe un CSV con el mismo formato que JMeter (timeStamp,elapsed,label,responseCode,success,threadName,allThreads),
que tambien entiende resumir_resultados.py.
    python carga/escenario_carga.py --usuarios 50 --rampa 30 --duracion 300 --salida carga/resultados/LOAD-021.jtl
Requiere:  python -m pip install requests
"""
import argparse, csv, random, threading, time
import requests

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--puerto", type=int, default=5000)
ap.add_argument("--usuarios", type=int, default=50); ap.add_argument("--rampa", type=int, default=30)
ap.add_argument("--duracion", type=int, default=300); ap.add_argument("--pensar", type=float, default=1.0)
ap.add_argument("--csv", default="carga/usuarios.csv"); ap.add_argument("--salida", default="carga/resultados/carga.jtl")
a = ap.parse_args()

base = f"http://{a.host}:{a.puerto}"
cuentas = list(csv.DictReader(open(a.csv, encoding="utf-8")))
filas, cerrojo, activos = [], threading.Lock(), [0]
fin_global = time.time() + a.duracion


def medir(s, nombre, metodo, ruta, esperado, hilo):
    t0 = time.time()
    try:
        r = s.request(metodo, base + ruta, timeout=30, allow_redirects=True)
        ok = r.status_code == 200 and esperado in r.text; codigo = r.status_code
    except requests.RequestException:
        ok, codigo = False, "ERR"
    with cerrojo:
        filas.append([int(t0 * 1000), int((time.time() - t0) * 1000), nombre, codigo, "true" if ok else "false", hilo, activos[0]])
    return ok


def usuario(i):
    hilo = f"Estudiantes {i + 1}"; s = requests.Session(); c = cuentas[i % len(cuentas)]
    with cerrojo: activos[0] += 1
    t0 = time.time()
    try:
        r = s.post(base + "/auth/login", data={"email": c["email"], "password": c["password"]}, timeout=30)
        ok = r.status_code == 200 and "Salir" in r.text
    except requests.RequestException:
        ok, r = False, None
    with cerrojo:
        filas.append([int(t0 * 1000), int((time.time() - t0) * 1000), "01 Login", r.status_code if r is not None else "ERR", "true" if ok else "false", hilo, activos[0]])
    while time.time() < fin_global:
        for nombre, metodo, ruta, esp in (("02 Consultar cursos", "GET", "/courses/", "Codigo"),
                                           ("03 Matricular", "POST", f"/enrollments/enroll/{random.randint(1, 3)}", "Mis matriculas"),
                                           ("04 Mis matriculas", "GET", "/enrollments/my", "Mis matriculas")):
            if time.time() >= fin_global: break
            medir(s, nombre, metodo, ruta, esp, hilo); time.sleep(a.pensar)
    with cerrojo: activos[0] -= 1


hilos = []
for i in range(a.usuarios):
    t = threading.Thread(target=usuario, args=(i,), daemon=True); t.start(); hilos.append(t)
    time.sleep(a.rampa / a.usuarios)
for t in hilos: t.join()
with open(a.salida, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["timeStamp", "elapsed", "label", "responseCode", "success", "threadName", "allThreads"]); w.writerows(filas)
print(f"{len(filas)} muestras guardadas en {a.salida}")
