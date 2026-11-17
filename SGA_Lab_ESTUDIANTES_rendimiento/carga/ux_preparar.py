"""Fase XII - Preparacion de las pruebas de experiencia de usuario (UX-031 y UX-032).

Crea cuentas de estudiante para los participantes (ux01@sga.test ...), les asigna matriculas con calificaciones
(para UX-032) y deja sin matricular el curso objetivo de UX-031. Imprime la hoja del facilitador.
Ejecutar DENTRO de la copia de rendimiento, con la correccion DEF-15 aplicada:
    python carga/ux_preparar.py --participantes 5
    python carga/ux_preparar.py --limpiar          (al terminar las sesiones)
La clave de prueba se entrega a cada participante de forma verbal; NO se escribe en los registros de observacion.
"""
import argparse, random, sqlite3, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--participantes", type=int, default=5)
ap.add_argument("--clave", default="Ux2026!")
ap.add_argument("--db", help="ruta a sga.db (por defecto la de app.config)")
ap.add_argument("--limpiar", action="store_true")
a = ap.parse_args()

ruta = a.db
if not ruta:
    sys.path.insert(0, str(Path.cwd()))
    from app.config import Config
    ruta = Config.DATABASE
con = sqlite3.connect(ruta, timeout=60)

if a.limpiar:
    ids = "SELECT id FROM users WHERE email LIKE 'ux%@sga.test'"
    g = con.execute(f"DELETE FROM grades WHERE enrollment_id IN (SELECT id FROM enrollments WHERE student_id IN ({ids}))").rowcount
    e = con.execute(f"DELETE FROM enrollments WHERE student_id IN ({ids})").rowcount
    u = con.execute("DELETE FROM users WHERE email LIKE 'ux%@sga.test'").rowcount
    con.execute("UPDATE courses SET enrolled_count=(SELECT COUNT(*) FROM enrollments e WHERE e.course_id=courses.id)")
    con.commit(); print(f"Eliminados: {u} cuentas UX, {e} matriculas y {g} calificaciones."); sys.exit()

from werkzeug.security import generate_password_hash
h = generate_password_hash(a.clave)
cursos = con.execute("SELECT id,code,name FROM courses WHERE status='active' AND enrolled_count<max_quota "
                     "AND code NOT LIKE 'VOL-%' AND code NOT LIKE 'CAP027-%' ORDER BY id").fetchall()
if len(cursos) < 3:
    sys.exit("Se necesitan al menos 3 cursos activos con cupo. Cree cursos como administrador y repita.")
objetivo = cursos[-1]                     # curso que NO se matricula: es la tarea de UX-031
con_notas = cursos[:2]                    # cursos con calificaciones: es la tarea de UX-032
random.seed(2026)
print(f"UX-031 - curso objetivo: {objetivo[1]} - {objetivo[2]}   (los participantes NO estan matriculados en el)\n")
print(f"{'Participante':<14}{'Cuenta':<18}{'Curso con notas':<34}{'Notas':<22}Promedio final esperado")
for i in range(1, a.participantes + 1):
    email = f"ux{i:02d}@sga.test"
    con.execute("INSERT OR IGNORE INTO users(document,first_name,last_name,email,phone,password_hash,role) VALUES(?,?,?,?,?,?,'student')",
                (f"9{i:05d}", f"Participante{i}", "UX", email, "3000000000", h))
    sid = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    curso = con_notas[i % 2]
    if not con.execute("SELECT 1 FROM enrollments WHERE student_id=? AND course_id=?", (sid, curso[0])).fetchone():
        con.execute("INSERT INTO enrollments(student_id,course_id) VALUES(?,?)", (sid, curso[0]))
        eid = con.execute("SELECT id FROM enrollments WHERE student_id=? AND course_id=?", (sid, curso[0])).fetchone()[0]
        n1, n2, n3 = (round(random.uniform(2.0, 4.8), 1) for _ in range(3))
        con.execute("INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,?,?,?,?)",
                    (eid, n1, n2, n3, round((n1 + n2 + n3) / 3, 2)))
    g = con.execute("SELECT g.grade1,g.grade2,g.grade3,g.final_grade FROM grades g JOIN enrollments e ON e.id=g.enrollment_id "
                    "WHERE e.student_id=? AND e.course_id=?", (sid, curso[0])).fetchone()
    print(f"P{i:<13}{email:<18}{curso[1] + ' ' + curso[2][:22]:<34}{str(g[:3]):<22}{g[3]}")
con.execute("UPDATE courses SET enrolled_count=(SELECT COUNT(*) FROM enrollments e WHERE e.course_id=courses.id)")
con.commit()
print(f"\nClave de prueba (entregarla verbalmente, no anotarla): {a.clave}")
