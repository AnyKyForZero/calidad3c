"""Fase X - Pruebas de capacidad (CAP-026, CAP-027, CAP-028).

  CAP-026  capacidad de usuarios concurrentes   -> niveles progresivos con JMeter (plan_SGA.jmx)
  CAP-027  matriculas simultaneas con cupo      -> solicitudes que arrancan al mismo instante + verificacion en la BD
  CAP-028  crecimiento de datos                 -> la BD crece por niveles y se repite la misma carga fija
  limpiar  borra los datos de prueba creados por CAP-027 y CAP-028

Ejecutar desde la RAIZ de la copia de rendimiento, con el servidor waitress ya iniciado en otra terminal:
  python carga/capacidad.py cap026 --jmeter "C:\\...\\bin\\jmeter.bat" --niveles 50,100,150,200,250
  python carga/capacidad.py cap027
  python carga/capacidad.py cap028 --jmeter "C:\\...\\bin\\jmeter.bat"
  python carga/capacidad.py limpiar

CRITERIOS (se fijan ANTES de ejecutar; ajustables por parametro):
  Por OPERACION (no global):  errores <= 1 %,  p95 <= 2000 ms (cursos, matricula, mis matriculas),  p95 login <= 3000 ms
  CPU media del servidor < 85 %
  CAP-027: nunca mas matriculas que cupos, sin duplicados, enrolled_count = matriculas reales, sin errores HTTP 5xx,
           y cuando la demanda supera el cupo se llenan exactamente los cupos.
Solo contra el entorno de pruebas local.
"""
import argparse, csv, math, random, sqlite3, subprocess, sys, threading, time
from pathlib import Path

RES = Path("carga/resultados")


# ------------------------------------------------------------------ utilidades comunes
def conectar(a):
    ruta = a.db
    if not ruta:
        sys.path.insert(0, str(Path.cwd()))
        from app.config import Config
        ruta = Config.DATABASE
    con = sqlite3.connect(ruta, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    return con


def exigir_columnas(con, tabla, dadas):
    """Avisa si la tabla tiene columnas obligatorias que el script no rellena (esquema distinto al esperado)."""
    info = con.execute(f"PRAGMA table_info({tabla})").fetchall()
    falta = [r[1] for r in info if r[3] and r[4] is None and not r[5] and r[1] not in dadas]
    if falta:
        sys.exit(f"La tabla {tabla} exige columnas que este script no rellena: {falta}. Avise para ajustar el script.")
    return [r[1] for r in info]


def pct(v, p):
    v = sorted(v)
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)] if v else 0


def analizar(jtl, rec):
    filas = list(csv.DictReader(open(jtl, encoding="utf-8")))
    if not filas:
        sys.exit(f"{jtl} no tiene muestras: el servidor no respondio o JMeter fallo.")
    ini = min(int(f["timeStamp"]) for f in filas); fin = max(int(f["timeStamp"]) + int(f["elapsed"]) for f in filas)
    t = [int(f["elapsed"]) for f in filas]
    err = sum(f["success"].lower() != "true" for f in filas)
    m = {"n": len(filas), "media": round(sum(t) / len(t)), "p95": pct(t, 95), "p99": pct(t, 99),
         "err": round(100 * err / len(filas), 2), "rps": round(len(filas) / ((fin - ini) / 1000 or 1), 1), "ops": {}, "cpu": 0.0}
    for lab in sorted({f["label"] for f in filas}):
        s = [f for f in filas if f["label"] == lab]; tt = [int(f["elapsed"]) for f in s]
        m["ops"][lab] = {"n": len(s), "media": round(sum(tt) / len(tt)), "p95": pct(tt, 95), "p99": pct(tt, 99),
                         "err": round(100 * sum(f["success"].lower() != "true" for f in s) / len(s), 2)}
    if Path(rec).exists():
        r = list(csv.DictReader(open(rec, encoding="utf-8")))
        if r:
            m["cpu"] = round(sum(float(x["cpu_proceso_pct"]) for x in r) / len(r), 1)
    return m


def medir(a, caso, usuarios, duracion):
    RES.mkdir(parents=True, exist_ok=True)
    jtl = RES / f"{caso}.jtl"; rec = RES / f"{caso}_recursos.csv"; rampa = max(2, int(duracion * 0.4))
    mon = subprocess.Popen([sys.executable, "carga/monitor_recursos.py", "--puerto", str(a.puerto), "--salida", str(rec),
                            "--duracion", str(duracion + 10), "--intervalo", "2"], stdout=subprocess.DEVNULL)
    print(f"\n=== {caso}: {usuarios} usuarios, {duracion}s (rampa {rampa}s) ===", flush=True)
    if a.motor == "jmeter":
        if not a.jmeter:
            mon.kill(); sys.exit("Indique --jmeter con la ruta de jmeter.bat")
        rep = RES / f"{caso}_reporte"
        if rep.exists():
            import shutil; shutil.rmtree(rep)
        jtl.unlink(missing_ok=True)
        subprocess.run([a.jmeter, "-n", "-t", "carga/plan_SGA.jmx", f"-Jusuarios={usuarios}", f"-Jrampa={rampa}", f"-Jduracion={duracion}",
                        f"-Jpuerto={a.puerto}", "-Jjmeter.save.saveservice.subresults=false", "-l", str(jtl), "-e", "-o", str(rep)])
    else:
        subprocess.run([sys.executable, "carga/escenario_carga.py", "--usuarios", str(usuarios), "--rampa", str(rampa), "--duracion", str(duracion),
                        "--puerto", str(a.puerto), "--pensar", "0.5", "--salida", str(jtl)])
    mon.wait()
    return analizar(jtl, rec)


def evaluar(m, a):
    fallos = []
    for op, s in m["ops"].items():
        lim = a.p95_login if op.strip().startswith("01") else a.p95_op
        if s["p95"] > lim: fallos.append(f"{op}: p95 {s['p95']} ms > {lim} ms")
        if s["err"] > a.err: fallos.append(f"{op}: errores {s['err']} % > {a.err} %")
    if m["cpu"] >= a.cpu: fallos.append(f"CPU media {m['cpu']} % >= {a.cpu} %")
    return fallos


def imprimir_ops(m):
    print(f"   {'operacion':<24}{'n':>7}{'media':>8}{'p95':>8}{'p99':>8}{'error%':>8}")
    for op, s in m["ops"].items():
        print(f"   {op:<24}{s['n']:>7}{s['media']:>8}{s['p95']:>8}{s['p99']:>8}{s['err']:>8}")


def guardar_ops(ruta, filas):
    nuevo = not Path(ruta).exists()
    with open(ruta, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        if nuevo: w.writerow(["caso", "variable", "operacion", "n", "media_ms", "p95_ms", "p99_ms", "error_pct", "cumple"])
        w.writerows(filas)


# ------------------------------------------------------------------ CAP-026
def cap026(a):
    niveles = [int(x) for x in a.niveles.split(",")]
    RES.mkdir(parents=True, exist_ok=True)
    salida = RES / "cap026_operaciones.csv"; salida.unlink(missing_ok=True)
    tabla, capacidad, primer_fallo = [], None, None
    for i, u in enumerate(niveles, 1):
        m = medir(a, f"CAP-026-N{i}-{u}", u, a.duracion)
        fallos = evaluar(m, a)
        ok = not fallos
        tabla.append((u, m["media"], m["p95"], m["err"], m["rps"], m["cpu"], "CUMPLE" if ok else "NO CUMPLE", "; ".join(fallos)))
        print(f"-> {u} usuarios: {'CUMPLE' if ok else 'NO CUMPLE'}  (errores {m['err']} %, CPU {m['cpu']} %)")
        imprimir_ops(m)
        for f in fallos: print("   x", f)
        guardar_ops(salida, [[f"CAP-026-N{i}", u, op, s["n"], s["media"], s["p95"], s["p99"], s["err"],
                              "SI" if not any(x.startswith(op) for x in fallos) else "NO"] for op, s in m["ops"].items()])
        if ok:
            capacidad = u
        else:
            primer_fallo = u
            print(f"CRITERIO NO CUMPLIDO en {u} usuarios: se detiene el incremento."); break
        time.sleep(a.descanso)
    confirmada = None
    if capacidad:
        print(f"\nConfirmacion: se repite el nivel de {capacidad} usuarios para comprobar que no fue casualidad ...")
        time.sleep(a.descanso)
        m = medir(a, f"CAP-026-CONFIRMA-{capacidad}", capacidad, a.duracion)
        fallos = evaluar(m, a); confirmada = not fallos
        imprimir_ops(m)
        for f in fallos: print("   x", f)
        guardar_ops(salida, [[f"CAP-026-CONF", capacidad, op, s["n"], s["media"], s["p95"], s["p99"], s["err"],
                              "SI" if not any(x.startswith(op) for x in fallos) else "NO"] for op, s in m["ops"].items()])
    print("\n" + "=" * 96 + "\nRESULTADO CAP-026 - CAPACIDAD DE USUARIOS CONCURRENTES\n" + "=" * 96)
    print(f"{'Usuarios':>9}{'Media ms':>10}{'p95 ms':>9}{'Error %':>9}{'Req/s':>8}{'CPU %':>7}  Resultado")
    for t in tabla: print(f"{t[0]:>9}{t[1]:>10.0f}{t[2]:>9.0f}{t[3]:>9.2f}{t[4]:>8.1f}{t[5]:>7.1f}  {t[6]}")
    if capacidad:
        print(f"\nCapacidad maxima observada que cumple los criterios: {capacidad} usuarios concurrentes"
              + ("" if confirmada else "  (NO se confirmo en la repeticion: tomar con reserva)"))
    else:
        print("\nNingun nivel cumplio los criterios: probar con niveles menores (p. ej. --niveles 10,25,50).")
    print(f"Primer nivel que no cumple: {primer_fallo if primer_fallo else 'no se alcanzo en los niveles ejecutados'}")
    with open(RES / "cap026_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";"); w.writerow(["usuarios", "media_ms", "p95_ms", "error_pct", "req_s", "cpu_pct", "resultado", "incumplimientos"])
        w.writerows(tabla)
        w.writerow(["capacidad", capacidad or "", "", "", "", "", "CONFIRMADA" if confirmada else ("NO CONFIRMADA" if capacidad else "NINGUNA"), ""])


# ------------------------------------------------------------------ CAP-027
def cap027(a):
    import requests
    from concurrent.futures import ThreadPoolExecutor
    con = conectar(a)
    exigir_columnas(con, "courses", {"code", "name", "description", "teacher_id", "schedule", "max_quota", "status"})
    teacher = con.execute("SELECT teacher_id FROM courses ORDER BY id LIMIT 1").fetchone()[0]
    correos = [r[0] for r in con.execute("SELECT email FROM users WHERE email LIKE 'carga%@sga.test' ORDER BY email")]
    if len(correos) < a.solicitantes:
        sys.exit(f"Hay {len(correos)} estudiantes de carga y se piden {a.solicitantes}. Ejecute preparar_datos_carga.py --usuarios {a.solicitantes}")
    correos = correos[:a.solicitantes]
    base = f"http://127.0.0.1:{a.puerto}"
    marca = time.strftime("%H%M%S")

    def login(email):
        s = requests.Session(); s.trust_env = False   # no usar proxies del sistema para localhost
        s.headers['Connection'] = 'close'   # sin keep-alive: 150 sesiones abiertas agotarian el limite de conexiones de waitress
        r = s.post(f"{base}/auth/login", data={"email": email, "password": "Carga123!"}, timeout=60)
        return s if "salir" in r.text.lower() else None

    print(f"Iniciando sesion de {len(correos)} estudiantes (fuera de la medicion) ...", flush=True)
    with ThreadPoolExecutor(8) as ex:
        sesiones = list(ex.map(login, correos))
    if any(s is None for s in sesiones):
        sys.exit(f"{sum(s is None for s in sesiones)} inicios de sesion fallaron. Revise el servidor y las cuentas de carga.")

    def crear_curso(codigo, cupo):
        con.execute("INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES(?,?,?,?,?,?,'active')",
                    (codigo, f"Curso prueba capacidad {codigo}", "Curso de prueba CAP-027", teacher, "Lun 8-10", cupo))
        con.commit()
        return con.execute("SELECT id FROM courses WHERE code=?", (codigo,)).fetchone()[0]

    def disparar(lista, cid):
        n = len(lista); barrera = threading.Barrier(n); out = [None] * n

        def w(i):
            try:
                barrera.wait(60)
                r = lista[i].post(f"{base}/enrollments/enroll/{cid}", timeout=120)
                txt = r.text.lower()
                out[i] = (r.status_code, "matricula registrada" in txt)
            except Exception:
                out[i] = (0, False)
        hilos = [threading.Thread(target=w, args=(i,)) for i in range(n)]
        t0 = time.perf_counter()
        for h in hilos: h.start()
        for h in hilos: h.join()
        return out, time.perf_counter() - t0

    def verificar(cid):
        c = sqlite3.connect(con.execute("PRAGMA database_list").fetchone()[2], timeout=60)
        real = c.execute("SELECT COUNT(*) FROM enrollments WHERE course_id=?", (cid,)).fetchone()[0]
        cupo, cont = c.execute("SELECT max_quota,enrolled_count FROM courses WHERE id=?", (cid,)).fetchone()
        dup = c.execute("SELECT COUNT(*) FROM (SELECT student_id FROM enrollments WHERE course_id=? GROUP BY student_id HAVING COUNT(*)>1)", (cid,)).fetchone()[0]
        c.close()
        return real, cupo, cont, dup

    escenarios = []
    for r in range(1, a.rondas + 1):
        for cupo in [int(x) for x in a.cupos.split(",")]:
            escenarios.append((f"CAP027-{marca}-R{r}-C{cupo}", cupo, "distintos"))
    escenarios.append((f"CAP027-{marca}-DOBLECLIC", 100, "repetido"))

    filas, todo_ok = [], True
    print(f"\n{'Escenario':<28}{'Cupo':>5}{'Pide':>6}{'Reales':>8}{'Exito*':>8}{'Sobrecupo':>10}{'Dup':>5}{'Cont':>6}{'HTTP5xx':>8}  Resultado")
    for codigo, cupo, tipo in escenarios:
        cid = crear_curso(codigo, cupo)
        if tipo == "distintos":
            lista = list(sesiones); demanda = len(lista); distintos = len(lista)
        else:   # cada estudiante envia 3 solicitudes simultaneas (doble clic / reintento)
            sub = sesiones[:40]; lista = []
            for s in sub:
                for _ in range(3):
                    s2 = requests.Session(); s2.trust_env = False; s2.headers['Connection'] = 'close'; s2.cookies.update(s.cookies); lista.append(s2)
            demanda = len(lista); distintos = len(sub)
        out, seg = disparar(lista, cid)
        real, cupo_bd, cont, dup = verificar(cid)
        exito = sum(1 for st, ok in out if ok); err5 = sum(1 for st, ok in out if st == 0 or st >= 500)
        sobre = max(0, real - cupo_bd)
        esperado = min(cupo_bd, distintos)
        fallos = []
        if sobre: fallos.append(f"SOBRECUPO de {sobre}")
        if dup: fallos.append(f"{dup} matricula(s) duplicada(s)")
        if cont != real: fallos.append(f"enrolled_count={cont} pero hay {real}")
        if err5: fallos.append(f"{err5} error(es) HTTP/5xx")
        if real < esperado: fallos.append(f"se llenaron {real} de {esperado} cupos esperados")
        if exito != real: fallos.append(f"se informaron {exito} exitos pero hay {real} en la BD")
        ok = not fallos; todo_ok &= ok
        print(f"{codigo:<28}{cupo_bd:>5}{demanda:>6}{real:>8}{exito:>8}{sobre:>10}{dup:>5}{cont:>6}{err5:>8}  {'CUMPLE' if ok else 'NO CUMPLE: ' + '; '.join(fallos)}")
        filas.append([codigo, tipo, cupo_bd, demanda, real, exito, sobre, dup, cont, err5, round(seg, 2), "CUMPLE" if ok else "NO CUMPLE", "; ".join(fallos)])
    print("* Exito = respuestas que dicen 'Matricula registrada'.")
    print("\n" + "=" * 96 + "\nRESULTADO CAP-027 - MATRICULAS SIMULTANEAS\n" + "=" * 96)
    n_ok = sum(f[11] == "CUMPLE" for f in filas)
    print(f"Escenarios que cumplen: {n_ok} de {len(filas)}")
    if todo_ok:
        print("DECISION: se preservan las reglas de cupo e integridad bajo concurrencia.")
    else:
        print("DECISION: HAY INCUMPLIMIENTOS. Si aparece SOBRECUPO o duplicados, es un DEFECTO de concurrencia "
              "(verificar cupo e insertar no son atomicos): registrelo como DEF-15, corrijalo y repita CAP-027 + regresion.")
    RES.mkdir(parents=True, exist_ok=True)
    with open(RES / "cap027_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["escenario", "tipo", "cupo", "solicitudes", "matriculas_reales", "exitos_informados", "sobrecupo", "duplicadas",
                    "enrolled_count", "errores_http", "segundos", "resultado", "detalle"])
        w.writerows(filas)


# ------------------------------------------------------------------ CAP-028
def conteos(con):
    r = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("courses", "enrollments", "grades", "users")}
    r["mb"] = round(Path(con.execute("PRAGMA database_list").fetchone()[2]).stat().st_size / 1e6, 1)
    return r


def crecer(con, n_cursos, k):
    exigir_columnas(con, "courses", {"code", "name", "description", "teacher_id", "schedule", "max_quota", "status"})
    exigir_columnas(con, "enrollments", {"student_id", "course_id"})
    gcols = exigir_columnas(con, "grades", {"enrollment_id", "grade1", "grade2", "grade3", "final_grade"})
    teacher = con.execute("SELECT teacher_id FROM courses ORDER BY id LIMIT 1").fetchone()[0]
    ya_cursos = con.execute("SELECT COUNT(*) FROM courses WHERE code LIKE 'VOL-%'").fetchone()[0]
    con.executemany("INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES(?,?,?,?,?,?,'active')",
                    [(f"VOL-{i:05d}", f"Curso de volumen {i}", "Dato de prueba CAP-028", teacher, "Lun 8-10", 100000) for i in range(ya_cursos + 1, n_cursos + 1)])
    con.commit()
    cursos = [r[0] for r in con.execute("SELECT id FROM courses WHERE code LIKE 'VOL-%' ORDER BY id")]
    alumnos = [r[0] for r in con.execute("SELECT id FROM users WHERE email LIKE 'carga%@sga.test' ORDER BY id")]
    k = min(k, len(cursos))
    for sid in alumnos:
        ya = {r[0] for r in con.execute("SELECT course_id FROM enrollments WHERE student_id=? AND course_id IN (SELECT id FROM courses WHERE code LIKE 'VOL-%')", (sid,))}
        faltan = k - len(ya)
        if faltan > 0:
            nuevos = random.sample([c for c in cursos if c not in ya], faltan)
            con.executemany("INSERT INTO enrollments(student_id,course_id) VALUES(?,?)", [(sid, c) for c in nuevos])
    con.commit()
    sin_nota = [r[0] for r in con.execute("SELECT e.id FROM enrollments e JOIN courses c ON c.id=e.course_id LEFT JOIN grades g ON g.enrollment_id=e.id "
                                          "WHERE c.code LIKE 'VOL-%' AND g.enrollment_id IS NULL")]
    notas = []
    for eid in sin_nota:
        n1, n2, n3 = (round(random.uniform(1.5, 5.0), 1) for _ in range(3))
        notas.append((eid, n1, n2, n3, round((n1 + n2 + n3) / 3, 2)))
    con.executemany("INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,?,?,?,?)", notas)
    con.execute("UPDATE courses SET enrolled_count=(SELECT COUNT(*) FROM enrollments e WHERE e.course_id=courses.id) WHERE code LIKE 'VOL-%'")
    con.commit()


def cap028(a):
    niveles = [(0, 0)] + [tuple(int(y) for y in x.split(":")) for x in a.volumenes.split(",")]
    con = conectar(a)
    RES.mkdir(parents=True, exist_ok=True)
    salida = RES / "cap028_operaciones.csv"; salida.unlink(missing_ok=True)
    resumen, base = [], None
    for i, (nc, k) in enumerate(niveles):
        if i > 0:
            print(f"\nCreciendo la BD: {nc} cursos de volumen y {k} matriculas por estudiante de carga (con su calificacion) ...", flush=True)
            t0 = time.time(); crecer(con, nc, k); print(f"   listo en {time.time() - t0:.0f} s")
        c = conteos(con)
        m = medir(a, f"CAP-028-V{i}", a.usuarios, a.duracion)
        fallos = evaluar(m, a); ok = not fallos
        if base is None: base = m
        print(f"-> Volumen V{i}: {c['courses']} cursos, {c['enrollments']} matriculas, {c['grades']} calificaciones, BD {c['mb']} MB => {'CUMPLE' if ok else 'NO CUMPLE'}")
        imprimir_ops(m)
        for f in fallos: print("   x", f)
        guardar_ops(salida, [[f"CAP-028-V{i}", f"{c['courses']} cursos/{c['enrollments']} matr", op, s["n"], s["media"], s["p95"], s["p99"], s["err"],
                              "SI" if not any(x.startswith(op) for x in fallos) else "NO"] for op, s in m["ops"].items()])
        resumen.append([f"V{i}", c["courses"], c["enrollments"], c["grades"], c["mb"], m["media"], m["p95"], m["err"], m["cpu"],
                        "CUMPLE" if ok else "NO CUMPLE", "; ".join(fallos)])
        time.sleep(a.descanso)
    print("\n" + "=" * 100 + "\nRESULTADO CAP-028 - CRECIMIENTO DE DATOS (carga fija de %d usuarios)\n" % a.usuarios + "=" * 100)
    print(f"{'Nivel':<6}{'Cursos':>8}{'Matric.':>9}{'Calif.':>9}{'BD MB':>7}{'Media':>7}{'p95':>7}{'Err%':>6}{'CPU%':>6}  Resultado")
    for r in resumen: print(f"{r[0]:<6}{r[1]:>8}{r[2]:>9}{r[3]:>9}{r[4]:>7}{r[5]:>7}{r[6]:>7}{r[7]:>6}{r[8]:>6}  {r[9]}")
    print("\nEfecto del volumen por operacion (p95 en ms) respecto al volumen base: ver carga/resultados/cap028_operaciones.csv")
    with open(RES / "cap028_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["nivel", "cursos", "matriculas", "calificaciones", "bd_mb", "media_ms", "p95_ms", "error_pct", "cpu_pct", "resultado", "incumplimientos"])
        w.writerows(resumen)


# ------------------------------------------------------------------ limpiar
def limpiar(a):
    con = conectar(a)
    like = "(code LIKE 'VOL-%' OR code LIKE 'CAP027-%')"
    ids = f"SELECT id FROM courses WHERE {like}"
    g = con.execute(f"DELETE FROM grades WHERE enrollment_id IN (SELECT id FROM enrollments WHERE course_id IN ({ids}))").rowcount
    e = con.execute(f"DELETE FROM enrollments WHERE course_id IN ({ids})").rowcount
    c = con.execute(f"DELETE FROM courses WHERE {like}").rowcount
    con.commit(); con.execute("VACUUM")
    print(f"Eliminados: {c} cursos de prueba, {e} matriculas y {g} calificaciones.")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    com = argparse.ArgumentParser(add_help=False)
    com.add_argument("--puerto", type=int, default=5000); com.add_argument("--db", help="ruta a sga.db (por defecto la de app.config)")
    com.add_argument("--motor", choices=["jmeter", "python"], default="jmeter"); com.add_argument("--jmeter", help="ruta a jmeter.bat")
    com.add_argument("--duracion", type=int, default=180); com.add_argument("--descanso", type=int, default=30)
    com.add_argument("--err", type=float, default=1.0, help="errores maximos por operacion (%%)")
    com.add_argument("--p95-op", type=int, default=2000); com.add_argument("--p95-login", type=int, default=3000)
    com.add_argument("--cpu", type=float, default=85)
    p = sub.add_parser("cap026", parents=[com]); p.add_argument("--niveles", default="50,100,150,200,250"); p.set_defaults(f=cap026)
    p = sub.add_parser("cap027", parents=[com]); p.add_argument("--solicitantes", type=int, default=150)
    p.add_argument("--cupos", default="10,20,50"); p.add_argument("--rondas", type=int, default=5); p.set_defaults(f=cap027)
    p = sub.add_parser("cap028", parents=[com]); p.add_argument("--usuarios", type=int, default=100)
    p.add_argument("--volumenes", default="200:20,1000:100,3000:300", help="cursos:matriculas_por_estudiante (acumulado), separados por coma")
    p.set_defaults(f=cap028, duracion=120)
    p = sub.add_parser("limpiar", parents=[com]); p.set_defaults(f=limpiar)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
