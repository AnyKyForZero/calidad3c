"""SYS-009..012, SEC-038/039, RF03, RF07, RF08 - Sistema, roles y seguridad."""
import pytest


# ---------- SYS-009 Flujo del estudiante ----------
def test_SYS009_flujo_estudiante(client, entrar, fetch, cid):
    entrar("estudiante@sga.local")
    assert "ING101" in client.get("/courses/").get_data(as_text=True)
    r = client.post(f"/enrollments/enroll/{cid('ING101')}", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Matricula registrada" in html and "ING101" in html


# ---------- SYS-010 Permisos por rol ----------
@pytest.mark.parametrize("rol,url,esperado", [
    ("estudiante@sga.local", "/grades/", 302),
    ("estudiante@sga.local", "/reports/", 302),
    ("estudiante@sga.local", "/courses/new", 302),
    ("docente@sga.local", "/courses/new", 302),
    ("docente@sga.local", "/grades/", 200),
    ("docente@sga.local", "/reports/", 200),
    ("admin@sga.local", "/grades/", 200),
    ("admin@sga.local", "/reports/", 200),
    ("admin@sga.local", "/courses/new", 200),
    ("estudiante@sga.local", "/enrollments/my", 200),
])
def test_SYS010_permisos_por_rol(client, entrar, rol, url, esperado):
    entrar(rol)
    assert client.get(url).status_code == esperado


@pytest.mark.parametrize("url", ["/enrollments/my", "/grades/", "/reports/", "/courses/new"])
def test_SYS010_anonimo_redirige_al_login(client, url):
    r = client.get(url)
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


# ---------- SYS-011 Registro y consulta de notas ----------
def test_SYS011_notas_y_promedio_consultados_por_el_estudiante(client, entrar, uid, cid, matricula):
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))
    entrar("docente@sga.local")
    client.post(f"/grades/save/{eid}", data={"grade1": 4.0, "grade2": 3.5, "grade3": 5.0})
    entrar("estudiante@sga.local")
    html = client.get("/enrollments/my").get_data(as_text=True)
    assert "4.0, 3.5, 5.0" in html
    assert "4.1666" in html or "4.17" in html  # promedio de tres notas


# ---------- SYS-012 Cierre de sesion ----------
def test_SYS012_cierre_de_sesion_protege_paginas(client, entrar):
    entrar("estudiante@sga.local")
    assert client.get("/enrollments/my").status_code == 200
    client.get("/auth/logout")
    r = client.get("/enrollments/my")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


# ---------- SEC-038 Aislamiento de informacion academica ----------
def test_SEC038_un_estudiante_no_ve_matriculas_de_otro(client, entrar, uid, cid, matricula):
    matricula(uid("estudiante@sga.local"), cid("CAL201"))
    entrar("laura@sga.local")
    html = client.get("/enrollments/my").get_data(as_text=True)
    assert "CAL201" not in html


# ---------- SEC-039 Funciones administrativas ----------
def test_SEC039_estudiante_no_puede_crear_cursos(client, entrar, fetch):
    entrar("estudiante@sga.local")
    client.post("/courses/new", data=dict(code="HACK1", name="X", description="x",
                teacher_email="docente@sga.local", schedule="Lunes", max_quota=5, status="active"))
    assert fetch("SELECT id FROM courses WHERE code='HACK1'") == []


def test_SEC039_estudiante_no_puede_modificar_notas(client, entrar, fetch, uid, cid, matricula, nota_previa):
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))
    nota_previa(eid)
    entrar("estudiante@sga.local")
    client.post(f"/grades/save/{eid}", data={"grade1": 5, "grade2": 5, "grade3": 5})
    assert fetch("SELECT grade1 FROM grades WHERE enrollment_id=?", (eid,))[0]["grade1"] == 3.0


def test_SEC039_docente_no_califica_cursos_ajenos(client, fetch, run_sql, uid, cid, matricula, nota_previa):
    """Hallazgo a validar con el docente: un docente solo debe calificar sus propios cursos."""
    otro = run_sql("INSERT INTO users(document,first_name,last_name,email,phone,password_hash,role)"
                   " VALUES('2002','Otro','Docente','otro@sga.local','3','x','teacher')")
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))  # curso del docente@sga.local
    nota_previa(eid)
    with client.session_transaction() as s:
        s["user_id"] = otro
    client.post(f"/grades/save/{eid}", data={"grade1": 5, "grade2": 5, "grade3": 5})
    assert fetch("SELECT grade1 FROM grades WHERE enrollment_id=?", (eid,))[0]["grade1"] == 3.0


# ---------- RF03 Gestion de cursos ----------
CURSO = dict(code="NEW101", name="Curso Nuevo", description="d",
             teacher_email="docente@sga.local", schedule="Jueves 10:00", max_quota=15, status="active")


def test_RF03_admin_crea_curso(client, entrar, fetch):
    entrar("admin@sga.local")
    client.post("/courses/new", data=CURSO)
    assert len(fetch("SELECT id FROM courses WHERE code='NEW101'")) == 1


@pytest.mark.parametrize("cupo", [0, -5])
def test_RF03_rechaza_cupo_no_positivo(client, entrar, fetch, cupo):
    entrar("admin@sga.local")
    client.post("/courses/new", data=dict(CURSO, max_quota=cupo))
    assert fetch("SELECT id FROM courses WHERE code='NEW101'") == []


def test_RF03_rechaza_codigo_de_curso_duplicado(client, entrar, fetch):
    entrar("admin@sga.local")
    client.post("/courses/new", data=dict(CURSO, code="ING101"))
    assert len(fetch("SELECT id FROM courses WHERE code='ING101'")) == 1
