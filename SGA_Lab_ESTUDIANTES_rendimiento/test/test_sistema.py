"""Fase IV - Pruebas de sistema (SYS-009 a SYS-012).
Se prueba la aplicacion completa: sesion real por el formulario /auth/login,
rutas, reglas de negocio, plantillas y base de datos, sin llamar funciones internas."""
import pytest

CUENTAS = {
    "admin":      ("admin@sga.local", "Admin123!"),
    "docente":    ("docente@sga.local", "Docente123!"),
    "estudiante": ("estudiante@sga.local", "Estudiante123!"),
}


def iniciar_sesion(client, rol):
    correo, clave = CUENTAS[rol]
    r = client.post("/auth/login", data={"email": correo, "password": clave})
    assert r.status_code == 302, f"No se pudo iniciar sesion como {rol}"
    return r


# =====================================================================
# SYS-009  Flujo del estudiante
# =====================================================================
def test_SYS009_flujo_completo_del_estudiante(client, fetch, cid):
    iniciar_sesion(client, "estudiante")
    cursos = client.get("/courses/").get_data(as_text=True)
    assert "ING101" in cursos and "CAL201" in cursos
    html = client.post(f"/enrollments/enroll/{cid('CAL201')}", follow_redirects=True).get_data(as_text=True)
    assert "Matricula registrada" in html
    assert "CAL201" in client.get("/enrollments/my").get_data(as_text=True)
    assert len(fetch("SELECT id FROM enrollments")) == 1


def test_SYS009_segunda_matricula_en_el_mismo_curso_es_rechazada(client, fetch, cid):
    iniciar_sesion(client, "estudiante")
    client.post(f"/enrollments/enroll/{cid('CAL201')}")
    html = client.post(f"/enrollments/enroll/{cid('CAL201')}", follow_redirects=True).get_data(as_text=True)
    assert "Ya matriculado" in html
    assert len(fetch("SELECT id FROM enrollments")) == 1


def test_SYS009_estado_de_datos_cupo_actualizado(client, fetch, cid):
    iniciar_sesion(client, "estudiante")
    client.post(f"/enrollments/enroll/{cid('CAL201')}")
    assert fetch("SELECT enrolled_count FROM courses WHERE code='CAL201'")[0]["enrolled_count"] == 1


def test_SYS009_estado_de_datos_curso_inactivo_no_admite_matricula(client, fetch, cid):
    iniciar_sesion(client, "estudiante")
    client.post(f"/enrollments/enroll/{cid('OLD001')}")
    assert fetch("SELECT id FROM enrollments") == []


# =====================================================================
# SYS-010  Permisos por rol (sesion real de cada perfil)
# =====================================================================
PERMISOS = [  # (rol, metodo, url, resultado esperado)
    ("estudiante", "GET", "/enrollments/my", 200),
    ("estudiante", "GET", "/grades/", 302),
    ("estudiante", "GET", "/reports/", 302),
    ("estudiante", "GET", "/courses/new", 302),
    ("docente", "GET", "/grades/", 200),
    ("docente", "GET", "/reports/", 200),
    ("docente", "GET", "/courses/new", 302),
    ("admin", "GET", "/grades/", 200),
    ("admin", "GET", "/reports/", 200),
    ("admin", "GET", "/courses/new", 200),
]


@pytest.mark.parametrize("rol,metodo,url,esperado", PERMISOS)
def test_SYS010_permisos_por_rol(client, rol, metodo, url, esperado):
    iniciar_sesion(client, rol)
    assert client.open(url, method=metodo).status_code == esperado


@pytest.mark.parametrize("url", ["/enrollments/my", "/grades/", "/reports/", "/courses/new"])
def test_SYS010_sin_sesion_redirige_al_login(client, url):
    r = client.get(url)
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_SYS010_estudiante_no_ejecuta_operaciones_de_docente_ni_admin(client, fetch, uid, cid, matricula, nota_previa):
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))
    nota_previa(eid)
    iniciar_sesion(client, "estudiante")
    client.post(f"/grades/save/{eid}", data={"grade1": 5, "grade2": 5, "grade3": 5})
    client.post("/courses/new", data=dict(code="X1", name="X", description="x",
                teacher_email="docente@sga.local", schedule="L", max_quota=5, status="active"))
    assert fetch("SELECT grade1 FROM grades WHERE enrollment_id=?", (eid,))[0]["grade1"] == 3.0
    assert fetch("SELECT id FROM courses WHERE code='X1'") == []


# =====================================================================
# SYS-011  Registro y consulta de notas (docente -> estudiante)
# =====================================================================
def _registrar_y_consultar(client, eid):
    iniciar_sesion(client, "docente")
    client.post(f"/grades/save/{eid}", data={"grade1": 4.0, "grade2": 3.5, "grade3": 5.0})
    client.get("/auth/logout")
    iniciar_sesion(client, "estudiante")
    return client.get("/enrollments/my").get_data(as_text=True)


def test_SYS011_flujo_completo_docente_registra_estudiante_consulta(client, uid, cid, matricula, fetch):
    """Flujo real: la matricula no tiene notas previas (primer registro)."""
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))
    html = _registrar_y_consultar(client, eid)
    assert "4.0, 3.5, 5.0" in html


def test_SYS011_consulta_coincide_con_lo_guardado(client, uid, cid, matricula, nota_previa, fetch):
    """Aisla el defecto del primer INSERT: parte de una fila de notas existente."""
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))
    nota_previa(eid)
    html = _registrar_y_consultar(client, eid)
    fila = fetch("SELECT grade1,grade2,grade3,final_grade FROM grades WHERE enrollment_id=?", (eid,))[0]
    assert f"{fila['grade1']}, {fila['grade2']}, {fila['grade3']}" in html   # notas consultadas = guardadas
    assert str(fila["final_grade"]) in html                                 # definitiva consultada = guardada


def test_SYS011_promedio_consultado_es_el_promedio_de_las_tres_notas(client, uid, cid, matricula, nota_previa, fetch):
    eid = matricula(uid("estudiante@sga.local"), cid("ING101"))
    nota_previa(eid)
    _registrar_y_consultar(client, eid)
    final = fetch("SELECT final_grade FROM grades WHERE enrollment_id=?", (eid,))[0]["final_grade"]
    assert final == pytest.approx((4.0 + 3.5 + 5.0) / 3, abs=0.01)


# =====================================================================
# SYS-012  Cierre de sesion y navegacion hacia atras
# =====================================================================
RUTAS_PROTEGIDAS = ["/enrollments/my", "/grades/", "/reports/"]


@pytest.mark.parametrize("rol", ["estudiante", "docente", "admin"])
def test_SYS012_tras_cerrar_sesion_las_paginas_protegidas_exigen_login(client, rol):
    iniciar_sesion(client, rol)
    client.get("/auth/logout")
    for url in RUTAS_PROTEGIDAS:
        r = client.get(url)
        assert r.status_code == 302 and "/auth/login" in r.headers["Location"], url


def test_SYS012_sesion_se_elimina_al_cerrar(client):
    iniciar_sesion(client, "estudiante")
    client.get("/auth/logout")
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_SYS012_boton_atras_no_muestra_paginas_protegidas_desde_cache(client):
    """Al volver con 'Atras' el navegador reutiliza la pagina en cache si el servidor no lo prohibe.
    Las paginas protegidas deben enviar Cache-Control: no-store."""
    iniciar_sesion(client, "estudiante")
    r = client.get("/enrollments/my")
    assert "no-store" in r.headers.get("Cache-Control", "")
