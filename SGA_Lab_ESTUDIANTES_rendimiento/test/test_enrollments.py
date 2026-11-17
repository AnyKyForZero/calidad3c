"""RF04 / RF05 - Matricula y cupos (UT-004, INT-006..008)."""


# ---------- UT-004 Calculo de cupos: capacidad 30, 17 matriculas ----------
def test_UT004_cupos_disponibles_con_17_matriculas(client, entrar, fetch, cid, nuevo_estudiante, uid):
    c = cid("ING101")  # capacidad 30
    for n in range(1, 18):
        est = nuevo_estudiante(n)
        with client.session_transaction() as s:
            s["user_id"] = est
        client.post(f"/enrollments/enroll/{c}")
    curso = fetch("SELECT max_quota, enrolled_count FROM courses WHERE id=?", (c,))[0]
    matriculas = fetch("SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (c,))[0]["n"]
    assert matriculas == 17
    assert curso["max_quota"] - curso["enrolled_count"] == 13


# ---------- INT-006 Matricula y cupos ----------
def test_INT006_matricula_descuenta_un_cupo(client, entrar, fetch, cid):
    c = cid("CAL201")  # capacidad 7
    entrar("estudiante@sga.local")
    client.post(f"/enrollments/enroll/{c}")
    assert fetch("SELECT enrolled_count FROM courses WHERE id=?", (c,))[0]["enrolled_count"] == 1


def test_INT006_listado_de_cursos_muestra_cupo_actualizado(client, entrar, cid):
    c = cid("CAL201")
    entrar("estudiante@sga.local")
    client.post(f"/enrollments/enroll/{c}")
    assert "1/7" in client.get("/courses/").get_data(as_text=True)


def test_RF05_curso_sin_cupos_bloquea_matricula(client, entrar, fetch, cid, run_sql):
    c = cid("CAL201")
    run_sql("UPDATE courses SET enrolled_count=max_quota WHERE id=?", (c,))
    entrar("estudiante@sga.local")
    client.post(f"/enrollments/enroll/{c}")
    assert fetch("SELECT id FROM enrollments WHERE course_id=?", (c,)) == []


def test_RF05_cupo_se_agota_con_matriculas_reales(client, fetch, cid, run_sql, nuevo_estudiante):
    c = cid("CAL201")
    run_sql("UPDATE courses SET max_quota=2 WHERE id=?", (c,))
    for n in range(1, 4):  # 3 estudiantes para 2 cupos
        est = nuevo_estudiante(n)
        with client.session_transaction() as s:
            s["user_id"] = est
        client.post(f"/enrollments/enroll/{c}")
    assert fetch("SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (c,))[0]["n"] == 2


# ---------- INT-007 Matricula repetida ----------
def test_INT007_no_permite_matricula_duplicada(client, entrar, fetch, cid):
    c = cid("ING101")
    entrar("estudiante@sga.local")
    client.post(f"/enrollments/enroll/{c}")
    client.post(f"/enrollments/enroll/{c}")
    assert fetch("SELECT COUNT(*) n FROM enrollments WHERE course_id=?", (c,))[0]["n"] == 1


# ---------- INT-008 Curso inactivo ----------
def test_INT008_no_permite_matricula_en_curso_inactivo(client, entrar, fetch, cid):
    c = cid("OLD001")
    entrar("estudiante@sga.local")
    client.post(f"/enrollments/enroll/{c}")
    assert fetch("SELECT id FROM enrollments WHERE course_id=?", (c,)) == []


def test_RF04_curso_inexistente_no_genera_matricula(client, entrar, fetch):
    entrar("estudiante@sga.local")
    r = client.post("/enrollments/enroll/9999")
    assert r.status_code in (302, 404)
    assert fetch("SELECT id FROM enrollments") == []


def test_RF04_matricula_requiere_autenticacion(client, fetch, cid):
    r = client.post(f"/enrollments/enroll/{cid('ING101')}")
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]
    assert fetch("SELECT id FROM enrollments") == []
