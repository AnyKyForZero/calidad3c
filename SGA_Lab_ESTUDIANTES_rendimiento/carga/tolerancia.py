"""Fase XIV - Pruebas de tolerancia a fallos (FAIL-036, FAIL-037).  SOLO ENTORNO DE LABORATORIO.

  fail036  Interrupcion durante la matricula:
           A) clientes que cortan la conexion (solicitud completa sin leer la respuesta, e incompleta);
           B) caida brusca del servidor (se mata el proceso) en pleno proceso de matricula, reinicio y revision.
  fail037  Solicitudes concurrentes duplicadas de la MISMA matricula (varias por estudiante a la vez) con cupo limitado.
  limpiar  Borra los cursos FAIL-* y sus matriculas.

    python carga/tolerancia.py fail037
    python carga/tolerancia.py fail036
    python carga/tolerancia.py limpiar

Seguridad (definido ANTES de ejecutar):
  - Se trabaja en la copia SGA_Lab_ESTUDIANTES_rendimiento, con datos de prueba (cursos FAIL-*, estudiantes carga0301..).
  - Copia de seguridad automatica de la BD en instance/sga_antes_fase_XIV.db (API de respaldo de SQLite).
  - Restauracion: 'limpiar' borra solo los datos FAIL-*; para volver al estado exacto, detener los servidores y copiar la copia
    de seguridad sobre sga.db.
  - fail036-B levanta SU PROPIO servidor en el puerto --puerto-lab (5100) y mata solo ese proceso; no toca el servidor principal.
  - Nadie mas debe usar la base durante la prueba.
"""
import argparse, csv, shutil, socket, sqlite3, struct, subprocess, sys, threading, time
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("caso", choices=["fail036", "fail037", "limpiar"])
ap.add_argument("--puerto", type=int, default=5000, help="servidor principal (fail037 y fail036-A)")
ap.add_argument("--puerto-lab", type=int, default=5100, help="servidor propio que se mata en fail036-B")
ap.add_argument("--app", default="run:app", help="aplicacion waitress para el servidor propio")
ap.add_argument("--db", help="ruta a sga.db (por defecto la de app.config)")
ap.add_argument("--clave", default="Carga123!")
ap.add_argument("--primer-estudiante", type=int, default=301, help="se usan carga0301, carga0302, ...")
a = ap.parse_args()
RES = Path("carga/resultados"); RES.mkdir(parents=True, exist_ok=True)


def abrir():
    ruta = a.db
    if not ruta:
        sys.path.insert(0, str(Path.cwd()))
        from app.config import Config
        ruta = Config.DATABASE
    con = sqlite3.connect(ruta, timeout=60); con.execute("PRAGMA busy_timeout=60000")
    return con, ruta


def respaldo(con, ruta):
    dst = Path(ruta).with_name("sga_antes_fase_XIV.db")
    if dst.exists():
        print(f"Copia de seguridad ya existente: {dst}"); return
    d = sqlite3.connect(dst); con.backup(d); d.close()
    print(f"Copia de seguridad creada: {dst}")


def crear_curso(con, codigo, cupo):
    teacher = con.execute("SELECT teacher_id FROM courses ORDER BY id LIMIT 1").fetchone()[0]
    con.execute("INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES(?,?,?,?,?,?,'active')",
                (codigo, f"Curso prueba {codigo}", "Curso de prueba FAIL", teacher, "Lun 8-10", cupo))
    con.commit()
    return con.execute("SELECT id FROM courses WHERE code=?", (codigo,)).fetchone()[0]


def correos(n):
    return [f"carga{a.primer_estudiante + i:04d}@sga.test" for i in range(n)]


def login(puerto, email):
    import requests
    s = requests.Session(); s.trust_env = False; s.headers["Connection"] = "close"
    r = s.post(f"http://127.0.0.1:{puerto}/auth/login", data={"email": email, "password": a.clave}, timeout=60)
    return s if "salir" in r.text.lower() else None


def sesiones(puerto, mails):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex: ss = list(ex.map(lambda m: login(puerto, m), mails))
    if any(x is None for x in ss):
        sys.exit(f"{sum(x is None for x in ss)} inicios de sesion fallaron. Falta preparar_datos_carga.py --usuarios 600 o el servidor no responde.")
    return ss


def estado(ruta, cids):
    """Revisa integridad de la BD y de cada curso de prueba."""
    c = sqlite3.connect(ruta, timeout=60)
    ic = c.execute("PRAGMA integrity_check").fetchone()[0]
    out = {"integrity": ic, "cursos": {}}
    for cid in cids:
        real = c.execute("SELECT COUNT(*) FROM enrollments WHERE course_id=?", (cid,)).fetchone()[0]
        cupo, cont = c.execute("SELECT max_quota,enrolled_count FROM courses WHERE id=?", (cid,)).fetchone()
        dup = c.execute("SELECT COUNT(*) FROM (SELECT student_id FROM enrollments WHERE course_id=? GROUP BY student_id HAVING COUNT(*)>1)", (cid,)).fetchone()[0]
        out["cursos"][cid] = (real, cupo, cont, dup)
    out["mat_huerfanas"] = c.execute("SELECT COUNT(*) FROM enrollments e LEFT JOIN courses c ON c.id=e.course_id WHERE c.id IS NULL").fetchone()[0]
    out["notas_huerfanas"] = c.execute("SELECT COUNT(*) FROM grades g LEFT JOIN enrollments e ON e.id=g.enrollment_id WHERE e.id IS NULL").fetchone()[0]
    c.close()
    return out


def juzgar(e, esperado=None):
    """Devuelve lista de incumplimientos (vacia = integro)."""
    f = []
    if e["integrity"] != "ok": f.append(f"integrity_check: {e['integrity']}")
    if e["mat_huerfanas"]: f.append(f"{e['mat_huerfanas']} matriculas huerfanas")
    if e["notas_huerfanas"]: f.append(f"{e['notas_huerfanas']} calificaciones huerfanas")
    for cid, (real, cupo, cont, dup) in e["cursos"].items():
        if real > cupo: f.append(f"curso {cid}: sobrecupo ({real} > {cupo})")
        if cont != real: f.append(f"curso {cid}: enrolled_count={cont} pero hay {real} matriculas")
        if dup: f.append(f"curso {cid}: {dup} matricula(s) duplicada(s)")
        if esperado and cid in esperado and real != esperado[cid]: f.append(f"curso {cid}: se esperaban {esperado[cid]} matriculas y hay {real}")
    return f


filas = []


def reg(caso, prueba, fallos, detalle=""):
    ok = not fallos
    filas.append([caso, prueba, "CUMPLE" if ok else "NO CUMPLE", "; ".join(fallos), detalle])
    print(f"   [{'OK ' if ok else 'XX '}] {caso} {prueba}" + (f" -> {'; '.join(fallos)}" if fallos else "") + (f"  ({detalle})" if detalle else ""), flush=True)


def disparar(lista_sesiones, url_cid, puerto):
    n = len(lista_sesiones); barrera = threading.Barrier(n); out = [None] * n

    def w(i):
        try:
            barrera.wait(60)
            r = lista_sesiones[i].post(f"http://127.0.0.1:{puerto}/enrollments/enroll/{url_cid}", timeout=60)
            out[i] = (r.status_code, "matricula registrada" in r.text.lower(), "ya matriculado" in r.text.lower())
        except Exception:
            out[i] = (0, False, False)
    hs = [threading.Thread(target=w, args=(i,)) for i in range(n)]
    for h in hs: h.start()
    for h in hs: h.join()
    return out


# ------------------------------------------------------------------ FAIL-037
def fail037():
    import requests
    con, ruta = abrir(); respaldo(con, ruta)
    tag = time.strftime("%H%M%S")
    escenarios = [(f"FAIL-037-{tag}-A", 50, 30, 6), (f"FAIL-037-{tag}-B", 10, 30, 4)]   # codigo, cupo, estudiantes, solicitudes duplicadas por estudiante
    base = sesiones(a.puerto, correos(30))
    print(f"\n{'Escenario':<26}{'Cupo':>5}{'Estud.':>7}{'Solic.':>7}{'Reales':>8}{'Dup':>5}{'Cont':>6}{'5xx':>5}  Resultado")
    for codigo, cupo, nest, dups in escenarios:
        cid = crear_curso(con, codigo, cupo)
        lista = []
        for s in base[:nest]:
            for _ in range(dups):
                s2 = requests.Session(); s2.trust_env = False; s2.headers["Connection"] = "close"; s2.cookies.update(s.cookies); lista.append(s2)
        out = disparar(lista, cid, a.puerto)
        e = estado(ruta, [cid]); f = juzgar(e, {cid: min(cupo, nest)})
        err5 = sum(1 for st, _, _ in out if st == 0 or st >= 500)
        if err5: f.append(f"{err5} errores HTTP/5xx")
        real, cupo_bd, cont, dup = e["cursos"][cid]
        print(f"{codigo:<26}{cupo_bd:>5}{nest:>7}{len(lista):>7}{real:>8}{dup:>5}{cont:>6}{err5:>5}  {'CUMPLE' if not f else 'NO CUMPLE: ' + '; '.join(f)}")
        reg("FAIL-037", f"{codigo} (cupo {cupo}, {nest} estudiantes x {dups} solicitudes simultaneas)", f, f"reales={real}, enrolled_count={cont}")
    return


# ------------------------------------------------------------------ FAIL-036
def peticion_cruda(puerto, cookie, cid, completa):
    """Envia una solicitud HTTP a mano y corta la conexion sin leer la respuesta."""
    s = socket.create_connection(("127.0.0.1", puerto), timeout=10)
    req = (f"POST /enrollments/enroll/{cid} HTTP/1.1\r\nHost: 127.0.0.1:{puerto}\r\nCookie: {cookie}\r\n"
           f"Content-Length: 0\r\nConnection: close\r\n")
    s.sendall((req + "\r\n").encode() if completa else req.encode())     # incompleta: falta la linea en blanco final
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("hh" if sys.platform == "win32" else "ii", 1, 0))   # cierre abrupto (RST)
    s.close()


def fail036():
    con, ruta = abrir(); respaldo(con, ruta)
    tag = time.strftime("%H%M%S")
    # ---------- A: el cliente corta la conexion
    print("\n== FAIL-036-A: el cliente corta la conexion durante la matricula ==", flush=True)
    cidA = crear_curso(con, f"FAIL-036-{tag}-A", 100)
    mails = correos(40); ss = sesiones(a.puerto, mails)
    for i, s in enumerate(ss):
        ck = "; ".join(f"{k}={v}" for k, v in s.cookies.items())
        peticion_cruda(a.puerto, ck, cidA, completa=(i < 20))
    time.sleep(4)
    c = sqlite3.connect(ruta); ids = [r[0] for r in c.execute("SELECT id FROM users WHERE email IN (%s)" % ",".join("?" * 40), mails)]
    inc = c.execute("SELECT COUNT(*) FROM enrollments WHERE course_id=? AND student_id IN (SELECT id FROM users WHERE email IN (%s))" % ",".join("?" * 20), [cidA] + mails[20:]).fetchone()[0]
    comp = c.execute("SELECT COUNT(*) FROM enrollments WHERE course_id=? AND student_id IN (SELECT id FROM users WHERE email IN (%s))" % ",".join("?" * 20), [cidA] + mails[:20]).fetchone()[0]
    c.close()
    e = estado(ruta, [cidA]); f = juzgar(e)
    if inc: f.append(f"{inc} matricula(s) creadas por solicitudes INCOMPLETAS (no deberian existir)")
    reg("FAIL-036", "A1. Estado tras cortes de conexion (BD integra y coherente)", f, f"solicitudes completas procesadas: {comp} de 20; incompletas procesadas: {inc} de 20")
    # reintento: todos los estudiantes vuelven a matricularse y deben quedar exactamente una vez
    import requests
    rs = []
    for s in ss:
        r = s.post(f"http://127.0.0.1:{a.puerto}/enrollments/enroll/{cidA}", timeout=60)
        rs.append((r.status_code, "matricula registrada" in r.text.lower() or "ya matriculado" in r.text.lower()))
    e = estado(ruta, [cidA]); f = juzgar(e, {cidA: 40})
    mal = sum(1 for st, ok in rs if st >= 500 or not ok)
    if mal: f.append(f"{mal} reintentos sin respuesta clara ('Matricula registrada' o 'Ya matriculado')")
    reg("FAIL-036", "A2. Reintento tras el corte: cada estudiante queda matriculado una sola vez", f, f"matriculas finales: {e['cursos'][cidA][0]} de 40")

    # ---------- B: se cae el servidor
    print("\n== FAIL-036-B: caida brusca del servidor durante la matricula ==", flush=True)
    cidB = crear_curso(con, f"FAIL-036-{tag}-B", 40)
    log = open(RES / "fail036_servidor_lab.log", "w")

    def arrancar():
        p = subprocess.Popen([sys.executable, "-m", "waitress", f"--listen=127.0.0.1:{a.puerto_lab}", a.app], stdout=log, stderr=log)
        t0 = time.time()
        while time.time() - t0 < 30:
            try:
                socket.create_connection(("127.0.0.1", a.puerto_lab), timeout=1).close(); return p
            except OSError: time.sleep(0.3)
        p.kill(); sys.exit("El servidor de laboratorio no arranco: revise carga/resultados/fail036_servidor_lab.log y --app")
    srv = arrancar()
    mailsB = correos(60)
    ssB = sesiones(a.puerto_lab, mailsB)
    res = []
    hilo = threading.Thread(target=lambda: res.extend(disparar(ssB, cidB, a.puerto_lab))); hilo.start()
    time.sleep(0.25)
    srv.kill(); srv.wait()                     # caida brusca (equivale a cortar la energia al proceso)
    print("   Servidor de laboratorio terminado de forma abrupta durante las matriculas.", flush=True)
    hilo.join()
    recibidas = sum(1 for st, ok, ya in res if st == 200); cortadas = sum(1 for st, ok, ya in res if st == 0)
    e = estado(ruta, [cidB]); f = juzgar(e)         # la BD se revisa SIN servidor: debe recuperarse sola
    reg("FAIL-036", "B1. Estado de la BD justo tras la caida (sin servidor)", f,
        f"{recibidas} respuestas recibidas, {cortadas} conexiones cortadas; matriculas guardadas: {e['cursos'][cidB][0]}")
    srv = arrancar()
    ok_login = login(a.puerto_lab, mailsB[0]) is not None
    reg("FAIL-036", "B2. El servicio vuelve a funcionar tras reiniciar", [] if ok_login else ["no se pudo iniciar sesion tras el reinicio"])
    ssB = sesiones(a.puerto_lab, mailsB)
    out = disparar(ssB, cidB, a.puerto_lab)
    srv.kill(); srv.wait(); log.close()
    e = estado(ruta, [cidB]); f = juzgar(e, {cidB: 40})
    mal = sum(1 for st, ok, ya in out if st >= 500 or st == 0)
    if mal: f.append(f"{mal} reintentos con error")
    reg("FAIL-036", "B3. Reintento tras la recuperacion: cupo y matriculas coherentes", f, f"matriculas finales: {e['cursos'][cidB][0]} (cupo 40, 60 estudiantes)")


def limpiar():
    con, ruta = abrir()
    like = "code LIKE 'FAIL-%'"; ids = f"SELECT id FROM courses WHERE {like}"
    g = con.execute(f"DELETE FROM grades WHERE enrollment_id IN (SELECT id FROM enrollments WHERE course_id IN ({ids}))").rowcount
    e = con.execute(f"DELETE FROM enrollments WHERE course_id IN ({ids})").rowcount
    c = con.execute(f"DELETE FROM courses WHERE {like}").rowcount
    con.commit(); print(f"Eliminados: {c} cursos FAIL-*, {e} matriculas y {g} calificaciones.")


{"fail037": fail037, "fail036": fail036, "limpiar": limpiar}[a.caso]()
if filas:
    with open(RES / f"{a.caso}_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";"); w.writerow(["caso", "prueba", "resultado", "incumplimientos", "detalle"]); w.writerows(filas)
    print("\n" + "=" * 100 + f"\nRESULTADO {a.caso.upper()}\n" + "=" * 100)
    for f in filas: print(f"{f[2]:<11}{f[0]} {f[1]}" + (f"\n           -> {f[3]}" if f[3] else ""))
    print(f"\nCumplen: {sum(f[2] == 'CUMPLE' for f in filas)} de {len(filas)}")
    if any(f[2] != "CUMPLE" for f in filas):
        print("HAY INCUMPLIMIENTOS: si hay sobrecupo, duplicados o conteos distintos, es un DEFECTO de integridad (registrar como DEF-17).")
    print("Al terminar:  python carga/tolerancia.py limpiar")
