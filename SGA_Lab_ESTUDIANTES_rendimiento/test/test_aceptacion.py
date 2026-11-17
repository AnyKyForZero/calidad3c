"""Fase V - Prueba de aceptacion: proceso academico completo desde la perspectiva de cada actor.

Escenarios (guia):  1 Administrador prepara el curso   2 Estudiante consulta y se matricula
                    3 Docente revisa matriculas y califica   4 Estudiante consulta sus notas
                    5 Cada actor completa su parte del proceso
Cada criterio de aceptacion (CA) se evalua con evidencia observable (HTML, BD, codigos HTTP).
Ejecutar con:  python -m pytest test/test_aceptacion.py -v -s
"""
import pytest

NOTAS = (4.0, 3.5, 5.0)
PROMEDIO = sum(NOTAS) / 3  # 4.17


class Acta:
    def __init__(self):
        self.filas, self.codigos = [], []

    def verificar(self, escenario, ca, descripcion, condicion, evidencia):
        self.filas.append((escenario, ca, descripcion, "CUMPLE" if condicion else "NO CUMPLE", evidencia))
        return condicion

    def bloquear(self, escenario, ca, descripcion, motivo):
        self.filas.append((escenario, ca, descripcion, "BLOQUEADO", motivo))

    def http(self, r):
        self.codigos.append(r.status_code)
        return r

    def imprimir(self):
        print("\n" + "=" * 100 + "\nACTA DE ACEPTACION - PROCESO ACADEMICO\n" + "=" * 100)
        for esc, ca, desc, res, ev in self.filas:
            print(f"[{res:<10}] E{esc} {ca}: {desc}\n             evidencia: {ev}")
        n = sum(1 for f in self.filas if f[3] == "CUMPLE")
        print("-" * 100 + f"\nCriterios cumplidos: {n}/{len(self.filas)}")
        print("DECISION:", "ACEPTADO" if n == len(self.filas) else "NO ACEPTADO")


def _entrar(app, correo, clave):
    c = app.test_client()
    r = c.post("/auth/login", data={"email": correo, "password": clave})
    assert r.status_code == 302, f"No inicio sesion {correo}"
    return c


def test_ACE_proceso_academico_completo(app, fetch, run_sql):
    acta = Acta()
    admin = _entrar(app, "admin@sga.local", "Admin123!")
    est = _entrar(app, "estudiante@sga.local", "Estudiante123!")
    doc = _entrar(app, "docente@sga.local", "Docente123!")

    # ---------- Escenario 1: Administrador prepara un curso disponible ----------
    acta.http(admin.post("/courses/new", data=dict(
        code="ACE101", name="Aceptacion QA", description="Curso de aceptacion",
        teacher_email="docente@sga.local", schedule="Viernes 08:00-10:00", max_quota=3, status="active")))
    curso = fetch("SELECT * FROM courses WHERE code='ACE101'")
    acta.verificar(1, "CA-01", "El curso queda creado, activo y con cupo 3", len(curso) == 1 and curso[0]["status"] == "active" and curso[0]["max_quota"] == 3, "fila en tabla courses")
    lista = acta.http(admin.get("/courses/")).get_data(as_text=True)
    acta.verificar(1, "CA-01", "El curso aparece en el listado con 0 de 3 cupos ocupados", "ACE101" in lista and "0/3" in lista, "HTML de /courses/")
    cid = curso[0]["id"] if curso else None

    # ---------- Escenario 2: Estudiante consulta e intenta matricularse ----------
    lista = acta.http(est.get("/courses/")).get_data(as_text=True)
    acta.verificar(2, "CA-02", "El estudiante ve el curso disponible", "ACE101" in lista, "HTML de /courses/")
    html = acta.http(est.post(f"/enrollments/enroll/{cid}", follow_redirects=True)).get_data(as_text=True)
    acta.verificar(2, "CA-02", "La matricula se confirma al estudiante", "Matricula registrada" in html, "mensaje en pantalla")
    mis = acta.http(est.get("/enrollments/my")).get_data(as_text=True)
    acta.verificar(2, "CA-02", "El curso aparece en 'Mis matriculas'", "ACE101" in mis, "HTML de /enrollments/my")
    ocupados = fetch("SELECT enrolled_count FROM courses WHERE code='ACE101'")[0]["enrolled_count"]
    acta.verificar(2, "CA-03", "El cupo ocupado aumenta a 1 tras la matricula", ocupados == 1, f"enrolled_count={ocupados}")
    dup = acta.http(est.post(f"/enrollments/enroll/{cid}", follow_redirects=True)).get_data(as_text=True)
    n = fetch("SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (cid,))[0]["n"]
    acta.verificar(2, "CA-04", "No se permite matricular dos veces el mismo curso", n == 1 and "Ya matriculado" in dup, f"matriculas={n}")

    # ---------- Escenario 3: Docente revisa matriculas y registra notas ----------
    notas_html = acta.http(doc.get("/grades/")).get_data(as_text=True)
    acta.verificar(3, "CA-05", "El docente ve la matricula del curso en Calificaciones", "ACE101" in notas_html, "HTML de /grades/")
    eid = fetch("SELECT id FROM enrollments WHERE course_id=?", (cid,))[0]["id"]
    r = acta.http(doc.post(f"/grades/save/{eid}", data=dict(grade1=NOTAS[0], grade2=NOTAS[1], grade3=NOTAS[2])))
    guardada = fetch("SELECT * FROM grades WHERE enrollment_id=?", (eid,))
    ok_guardado = r.status_code < 500 and len(guardada) == 1
    acta.verificar(3, "CA-06", "El docente registra las tres notas sin error y quedan guardadas", ok_guardado, f"HTTP {r.status_code}; filas en grades={len(guardada)}")

    # ---------- Escenario 4: Estudiante consulta sus calificaciones ----------
    if not ok_guardado:
        # Desvio de diagnostico (NO cuenta como aceptacion): crea la fila previa y repite el guardado
        # por la ruta de actualizacion, para poder evaluar el resto del flujo.
        run_sql("INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,0,0,0,0)", (eid,))
        doc.post(f"/grades/save/{eid}", data=dict(grade1=NOTAS[0], grade2=NOTAS[1], grade3=NOTAS[2]))
        acta.bloquear(4, "CA-07", "Consulta directa de notas registradas por el docente", "bloqueado por CA-06; se evalua con desvio de diagnostico")
    mis = acta.http(est.get("/enrollments/my")).get_data(as_text=True)
    acta.verificar(4, "CA-07", "El estudiante ve las tres notas registradas (4.0, 3.5, 5.0)", "4.0, 3.5, 5.0" in mis, "HTML de /enrollments/my")
    fila = fetch("SELECT final_grade FROM grades WHERE enrollment_id=?", (eid,))
    final = fila[0]["final_grade"] if fila else None
    acta.verificar(4, "CA-08", f"La definitiva es el promedio de las tres notas ({PROMEDIO:.2f})", final is not None and abs(final - PROMEDIO) < 0.01, f"definitiva guardada={final}")

    # ---------- Escenario 5: Cada actor completa su parte sin errores y sin invadir otros roles ----------
    acta.verificar(5, "CA-09", "Ninguna operacion del proceso produjo error del sistema (HTTP 5xx)", all(c < 500 for c in acta.codigos), f"codigos HTTP: {sorted(set(acta.codigos))}")
    acta.verificar(5, "CA-10", "El estudiante no accede a funciones de docente ni administrador",
                   est.get("/grades/").status_code == 302 and est.get("/courses/new").status_code == 302, "302 en /grades/ y /courses/new")

    acta.imprimir()
    fallos = [f"{f[1]} {f[2]} ({f[3]})" for f in acta.filas if f[3] != "CUMPLE"]
    assert not fallos, "Criterios no cumplidos: " + " | ".join(fallos)
