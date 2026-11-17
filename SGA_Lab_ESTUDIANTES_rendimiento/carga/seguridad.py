"""Fase XV - Pruebas de seguridad (SEC-038, SEC-039, SEC-040).  SOLO ENTORNO DE LABORATORIO.

  sec038   Aislamiento de informacion academica entre dos estudiantes autorizados.
  sec039   Acceso a funciones administrativas desde perfiles sin permiso (estudiante, docente, sin sesion).
  sec040   Politica de contrasenas en el registro (longitudes y complejidades) + hash + bloqueo + mensajes.
  todo     Ejecuta sec038, sec039 y sec040 en ese orden.
  limpiar  Borra todas las cuentas y cursos de prueba SEC.

    python carga/seguridad.py todo          (con el servidor encendido en el puerto 5000)
    python carga/seguridad.py limpiar

Reglas (definidas ANTES de ejecutar):
  - Solo se usa la copia de laboratorio, con cuentas y cursos creados por este script (identificadores no sensibles:
    sec.est01, sec.est02, sec.doc01, sec.doc02, sec.adm01, sec.blq01, secpw01...). Nunca datos reales.
  - Solo se usan mecanismos normales de la aplicacion (navegar, enviar formularios). No se explota nada, no se
    escanea, no se ataca a terceros y no se sale de http://127.0.0.1.
  - Las contrasenas NO se imprimen ni se guardan en los resultados: de cada prueba solo se registra su perfil
    (longitud y tipos de caracteres) con un identificador P01, P02...
  - Copia de seguridad previa: instance/sga_antes_fase_XV.db. 'limpiar' deja la BD sin datos SEC.
"""
import argparse, csv, re, sqlite3, sys, time
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("caso", choices=["sec038", "sec039", "sec040", "todo", "limpiar"])
ap.add_argument("--puerto", type=int, default=5000)
ap.add_argument("--db", help="ruta a sga.db (por defecto la de app.config)")
ap.add_argument("--min-longitud", type=int, default=8, help="longitud minima de la politica (por defecto 8)")
ap.add_argument("--max-longitud", type=int, default=64, help="longitud maxima de la politica (por defecto 64)")
a = ap.parse_args()
CLAVE = "Lab#Segura2026"          # clave de las cuentas de prueba (solo laboratorio; no se muestra)
URL = f"http://127.0.0.1:{a.puerto}"
RES = Path("carga/resultados"); RES.mkdir(parents=True, exist_ok=True)
DOM = "sga.test"


def abrir():
    ruta = a.db
    if not ruta:
        sys.path.insert(0, str(Path.cwd()))
        from app.config import Config
        ruta = Config.DATABASE
    con = sqlite3.connect(ruta, timeout=60); con.execute("PRAGMA busy_timeout=60000"); con.row_factory = sqlite3.Row
    return con, ruta


def respaldo(con, ruta):
    dst = Path(ruta).with_name("sga_antes_fase_XV.db")
    if dst.exists():
        print(f"Copia de seguridad ya existente: {dst}"); return
    d = sqlite3.connect(dst); con.backup(d); d.close()
    print(f"Copia de seguridad creada: {dst}")


def sesion():
    import requests
    s = requests.Session(); s.trust_env = False; s.headers["Connection"] = "close"
    return s


def entrar(email, clave=CLAVE):
    s = sesion()
    r = s.post(f"{URL}/auth/login", data={"email": email, "password": clave}, timeout=30)
    return s if "salir" in r.text.lower() else None


filas = []


def reg(caso, prueba, actor, esperado, obtenido, ok):
    filas.append([caso, prueba, actor, esperado, obtenido, "CUMPLE" if ok else "NO CUMPLE"])
    print(f"   [{'OK ' if ok else 'XX '}] {caso} {prueba} [{actor}] esperado: {esperado} | obtenido: {obtenido}", flush=True)


# ------------------------------------------------------------------ datos de prueba
def preparar(con):
    from werkzeug.security import generate_password_hash
    h = generate_password_hash(CLAVE)
    cuentas = [("est01", "student"), ("est02", "student"), ("doc01", "teacher"), ("doc02", "teacher"), ("adm01", "admin"), ("blq01", "student")]
    for i, (n, rol) in enumerate(cuentas, 1):
        con.execute("DELETE FROM users WHERE email=?", (f"sec.{n}@{DOM}",))
        con.execute("INSERT INTO users(document,first_name,last_name,email,phone,password_hash,role) VALUES(?,?,?,?,?,?,?)",
                    (f"SECD{i:02d}", "Sec", n.upper(), f"sec.{n}@{DOM}", "3000000000", h, rol))
    uid = lambda n: con.execute("SELECT id FROM users WHERE email=?", (f"sec.{n}@{DOM}",)).fetchone()[0]
    for code in ("SEC-A", "SEC-B"):
        con.execute("DELETE FROM courses WHERE code=?", (code,))
    con.execute("INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES('SEC-A','Curso SEC A','prueba',?,'Lun 8-10',30,'active')", (uid("doc01"),))
    con.execute("INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES('SEC-B','Curso SEC B','prueba',?,'Mar 8-10',30,'active')", (uid("doc02"),))
    cid = lambda c: con.execute("SELECT id FROM courses WHERE code=?", (c,)).fetchone()[0]
    eids = {}
    for est, c in (("est01", "SEC-A"), ("est02", "SEC-B")):
        con.execute("INSERT INTO enrollments(student_id,course_id) VALUES(?,?)", (uid(est), cid(c)))
        con.execute("UPDATE courses SET enrolled_count=enrolled_count+1 WHERE id=?", (cid(c),))
        eids[est] = con.execute("SELECT id FROM enrollments WHERE student_id=? AND course_id=?", (uid(est), cid(c))).fetchone()[0]
        con.execute("INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,3.0,3.0,3.0,3.0)", (eids[est],))
    con.commit()
    return eids


def nota(con, eid):
    r = con.execute("SELECT grade1,grade2,grade3,final_grade FROM grades WHERE enrollment_id=?", (eid,)).fetchone()
    return tuple(r) if r else None


def existe_curso(con, code):
    return con.execute("SELECT 1 FROM courses WHERE code=?", (code,)).fetchone() is not None


FORM_CURSO = dict(name="Curso prueba", description="x", teacher_email=f"sec.doc01@{DOM}", schedule="Lun", max_quota=5, status="active")


# ------------------------------------------------------------------ SEC-038
def sec038(con, eids):
    print("\nSEC-038 Aislamiento de informacion academica (cuentas: sec.est01, sec.est02)")
    for yo, otro, mi_c, su_c in (("est01", "est02", "SEC-A", "SEC-B"), ("est02", "est01", "SEC-B", "SEC-A")):
        s = entrar(f"sec.{yo}@{DOM}")
        if not s: reg("SEC-038", "inicio de sesion", yo, "acceso", "no inicio sesion", False); continue
        t = s.get(f"{URL}/enrollments/my", timeout=30).text
        reg("SEC-038", "Mis matriculas muestra solo lo propio", yo, f"{mi_c} si, {su_c} no", f"{mi_c}={'si' if mi_c in t else 'no'}, {su_c}={'si' if su_c in t else 'no'}", mi_c in t and su_c not in t)
        t = s.get(f"{URL}/grades/", timeout=30).text
        fuga = (su_c in t) or (otro.upper() in t.upper()) or ("/grades/save/" in t)
        reg("SEC-038", "Pantalla de calificaciones (docente/admin) no expone datos ajenos", yo, "sin datos del otro estudiante", "datos expuestos" if fuga else "sin datos", not fuga)
        antes = nota(con, eids[otro])
        s.post(f"{URL}/grades/save/{eids[otro]}", data={"grade1": 5, "grade2": 5, "grade3": 5}, timeout=30)
        reg("SEC-038", "No puede modificar notas del otro estudiante", yo, "nota sin cambios", "sin cambios" if nota(con, eids[otro]) == antes else "NOTA MODIFICADA", nota(con, eids[otro]) == antes)
    s = sesion()
    t = s.get(f"{URL}/enrollments/my", timeout=30).text
    reg("SEC-038", "Sin sesion no ve matriculas", "anonimo", "sin datos SEC", "datos expuestos" if "SEC-" in t else "sin datos", "SEC-" not in t)


# ------------------------------------------------------------------ SEC-039
def sec039(con, eids):
    print("\nSEC-039 Acceso a funciones administrativas (cuentas: sec.est01, sec.doc01, sec.doc02, sec.adm01)")
    # control positivo: la funcion existe y funciona con el perfil autorizado
    adm = entrar(f"sec.adm01@{DOM}")
    if adm:
        adm.post(f"{URL}/courses/new", data=dict(FORM_CURSO, code="SEC-OK1"), timeout=30)
        reg("SEC-039", "CONTROL: admin si crea cursos", "admin", "curso creado", "creado" if existe_curso(con, "SEC-OK1") else "no creado", existe_curso(con, "SEC-OK1"))
    doc1 = entrar(f"sec.doc01@{DOM}")
    if doc1:
        doc1.post(f"{URL}/grades/save/{eids['est01']}", data={"grade1": 4, "grade2": 4, "grade3": 4}, timeout=30)
        n = nota(con, eids["est01"])
        reg("SEC-039", "CONTROL: docente si califica su propio curso", "docente01", "nota 4.0", f"{n[3] if n else None}", bool(n) and abs(n[3] - 4.0) < 1e-9)
    est = entrar(f"sec.est01@{DOM}")
    if est:
        r = est.get(f"{URL}/courses/new", timeout=30)
        reg("SEC-039", "Estudiante abre el formulario de crear cursos", "estudiante", "formulario no disponible", "formulario visible" if "teacher_email" in r.text else "no visible", "teacher_email" not in r.text)
        est.post(f"{URL}/courses/new", data=dict(FORM_CURSO, code="SEC-X1"), timeout=30)
        reg("SEC-039", "Estudiante intenta crear un curso", "estudiante", "curso no creado", "CREADO" if existe_curso(con, "SEC-X1") else "no creado", not existe_curso(con, "SEC-X1"))
        antes = nota(con, eids["est01"])
        est.post(f"{URL}/grades/save/{eids['est01']}", data={"grade1": 5, "grade2": 5, "grade3": 5}, timeout=30)
        reg("SEC-039", "Estudiante intenta cambiar su propia nota", "estudiante", "nota sin cambios", "sin cambios" if nota(con, eids["est01"]) == antes else "NOTA MODIFICADA", nota(con, eids["est01"]) == antes)
        t = est.get(f"{URL}/grades/", timeout=30).text
        reg("SEC-039", "Estudiante abre la pantalla de calificaciones", "estudiante", "sin formulario de notas", "formulario visible" if "/grades/save/" in t else "no visible", "/grades/save/" not in t)
    if doc1:
        doc1.post(f"{URL}/courses/new", data=dict(FORM_CURSO, code="SEC-X2"), timeout=30)
        reg("SEC-039", "Docente intenta crear un curso (solo admin)", "docente01", "curso no creado", "CREADO" if existe_curso(con, "SEC-X2") else "no creado", not existe_curso(con, "SEC-X2"))
        t = doc1.get(f"{URL}/grades/", timeout=30).text
        reg("SEC-039", "Docente solo ve los cursos que dicta", "docente01", "SEC-A si, SEC-B no", f"SEC-A={'si' if 'SEC-A' in t else 'no'}, SEC-B={'si' if 'SEC-B' in t else 'no'}", "SEC-A" in t and "SEC-B" not in t)
    doc2 = entrar(f"sec.doc02@{DOM}")
    if doc2:
        antes = nota(con, eids["est01"])
        doc2.post(f"{URL}/grades/save/{eids['est01']}", data={"grade1": 5, "grade2": 5, "grade3": 5}, timeout=30)
        reg("SEC-039", "Docente califica un curso de OTRO docente", "docente02", "nota sin cambios", "sin cambios" if nota(con, eids["est01"]) == antes else "NOTA MODIFICADA", nota(con, eids["est01"]) == antes)
    an = sesion(); antes = nota(con, eids["est01"])
    an.post(f"{URL}/courses/new", data=dict(FORM_CURSO, code="SEC-X3"), timeout=30)
    an.post(f"{URL}/grades/save/{eids['est01']}", data={"grade1": 1, "grade2": 1, "grade3": 1}, timeout=30)
    reg("SEC-039", "Sin sesion intenta crear curso y cambiar notas", "anonimo", "nada cambia", "CAMBIOS" if existe_curso(con, "SEC-X3") or nota(con, eids["est01"]) != antes else "nada cambia", not existe_curso(con, "SEC-X3") and nota(con, eids["est01"]) == antes)
    # el formulario publico de registro no debe permitir elegir rol
    s = sesion()
    s.post(f"{URL}/auth/register", data=dict(document="SECD90", first_name="Sec", last_name="ROL", email=f"sec.rol01@{DOM}", phone="3", password=CLAVE, role="admin"), timeout=30)
    r = con.execute("SELECT role FROM users WHERE email=?", (f"sec.rol01@{DOM}",)).fetchone()
    reg("SEC-039", "Registro publico con campo 'role=admin' manipulado", "anonimo", "rol student", f"rol {r['role']}" if r else "no se creo", bool(r) and r["role"] == "student")


# ------------------------------------------------------------------ SEC-040
def perfil(p):
    t = []
    if re.search(r"[a-z]", p): t.append("minusc")
    if re.search(r"[A-Z]", p): t.append("mayusc")
    if re.search(r"\d", p): t.append("digito")
    if re.search(r"[^A-Za-z0-9\s]", p): t.append("simbolo")
    return f"{len(p)} caracteres: " + (", ".join(t) if t else "sin letras ni numeros")


def cumple_politica(p):
    return (a.min_longitud <= len(p) <= a.max_longitud and re.search(r"[a-z]", p) and re.search(r"[A-Z]", p)
            and re.search(r"\d", p) and re.search(r"[^A-Za-z0-9\s]", p) and p == p.strip())


def sec040(con, eids):
    print(f"\nSEC-040 Politica de contrasenas (politica: {a.min_longitud}-{a.max_longitud} caracteres, con mayuscula, minuscula, digito y simbolo)")
    L = a.min_longitud
    casos = [
        "1" * (L - 1), "1" * L, "a" * L, "A" * L, "abcdefg1"[:L].ljust(L, "x"), "Abcdefg1"[:L].ljust(L, "x"),
        "Ab1!", "", " " * L,
        "Abcdef1!".ljust(L, "x"), "Lab#Segura2026x", "Ab1!" + "x" * (a.max_longitud - 4), "Ab1!" + "x" * (a.max_longitud + 40),
    ]
    for i, p in enumerate(casos, 1):
        email = f"secpw{i:02d}@{DOM}"; con.execute("DELETE FROM users WHERE email=?", (email,)); con.commit()
        s = sesion()
        try:
            r = s.post(f"{URL}/auth/register", data=dict(document=f"SECP{i:02d}", first_name="Sec", last_name=f"PW{i:02d}", email=email, phone="3000000000", password=p), timeout=30)
            cod = r.status_code
        except Exception:
            cod = 0
        creado = con.execute("SELECT password_hash FROM users WHERE email=?", (email,)).fetchone()
        debe = bool(cumple_politica(p))
        if cod >= 500 or cod == 0:
            reg("SEC-040", f"P{i:02d} {perfil(p)}", "anonimo", "aceptar" if debe else "rechazar", f"ERROR del servidor ({cod})", False)
        else:
            reg("SEC-040", f"P{i:02d} {perfil(p)}", "anonimo", "aceptar" if debe else "rechazar", "aceptada" if creado else "rechazada", bool(creado) == debe)
        if creado and i == 10:
            h = creado["password_hash"]
            reg("SEC-040", "Contrasena almacenada como hash (no en claro)", "secpw10", "hash con sal", h.split("$")[0].split(":")[0] if ":" in h else "texto plano", ":" in h and h != p)
    # mensajes iguales para usuario inexistente y contrasena incorrecta (no revelar si la cuenta existe)
    s1, s2 = sesion(), sesion()
    m1 = s1.post(f"{URL}/auth/login", data={"email": f"sec.noexiste@{DOM}", "password": "x"}, timeout=30).text
    m2 = s2.post(f"{URL}/auth/login", data={"email": f"sec.est01@{DOM}", "password": "x"}, timeout=30).text
    msg = lambda t: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
    reg("SEC-040", "Mismo mensaje con usuario inexistente y clave incorrecta", "anonimo", "mensajes iguales", "iguales" if msg(m1) == msg(m2) else "DISTINTOS", msg(m1) == msg(m2))
    # bloqueo tras intentos fallidos
    for _ in range(5):
        sesion().post(f"{URL}/auth/login", data={"email": f"sec.blq01@{DOM}", "password": "incorrecta"}, timeout=30)
    ok = entrar(f"sec.blq01@{DOM}") is not None
    reg("SEC-040", "Bloqueo de la cuenta tras 5 intentos fallidos", "sec.blq01", "login correcto rechazado", "ACCEDIO" if ok else "bloqueada", not ok)


# ------------------------------------------------------------------ limpiar
def limpiar(con):
    con.execute("DELETE FROM grades WHERE enrollment_id IN (SELECT e.id FROM enrollments e JOIN users u ON u.id=e.student_id WHERE u.email LIKE ?)", (f"sec.%@{DOM}",))
    con.execute("DELETE FROM enrollments WHERE student_id IN (SELECT id FROM users WHERE email LIKE ? OR email LIKE ?)", (f"sec.%@{DOM}", f"secpw%@{DOM}"))
    con.execute("DELETE FROM enrollments WHERE course_id IN (SELECT id FROM courses WHERE code LIKE 'SEC-%')")
    con.execute("DELETE FROM courses WHERE code LIKE 'SEC-%'")
    n = con.execute("DELETE FROM users WHERE email LIKE ? OR email LIKE ?", (f"sec.%@{DOM}", f"secpw%@{DOM}")).rowcount
    con.commit()
    print(f"Datos SEC eliminados ({n} cuentas de prueba).")


def main():
    con, ruta = abrir()
    if a.caso == "limpiar":
        limpiar(con); return
    respaldo(con, ruta)
    import requests
    try:
        requests.Session().get(URL + "/", timeout=5)
    except Exception:
        sys.exit(f"No hay servidor en {URL}. Enciendelo antes (waitress-serve --port={a.puerto} run:app).")
    limpiar(con); eids = preparar(con)
    print(f"Cuentas de prueba creadas: sec.est01, sec.est02, sec.doc01, sec.doc02, sec.adm01, sec.blq01 (@{DOM}). Contrasenas no se muestran.")
    if a.caso in ("sec038", "todo"): sec038(con, eids)
    if a.caso in ("sec039", "todo"): sec039(con, eids)
    if a.caso in ("sec040", "todo"): sec040(con, eids)
    f = RES / f"seguridad_{a.caso}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(f, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["caso", "prueba", "cuenta", "esperado", "obtenido", "resultado"]); w.writerows(filas)
    print("\n" + "=" * 100)
    for c in ("SEC-038", "SEC-039", "SEC-040"):
        x = [r for r in filas if r[0] == c]
        if x:
            bad = [r for r in x if r[5] != "CUMPLE"]
            print(f"{c}: {len(x) - len(bad)}/{len(x)} CUMPLE" + ("" if not bad else "  -> NO CUMPLE: " + " | ".join(r[1] for r in bad)))
    print(f"Resultados: {f}\nCuando termines: python carga/seguridad.py limpiar")


main()
