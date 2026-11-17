"""RF06 - Calculo de notas y limites (UT-002, UT-003)."""
import pytest


@pytest.fixture
def mat(uid, cid, matricula):
    return matricula(uid("estudiante@sga.local"), cid("ING101"))


def _guardar(client, eid, n1, n2, n3):
    return client.post(f"/grades/save/{eid}", data={"grade1": n1, "grade2": n2, "grade3": n3})


def _nota(fetch, eid):
    return fetch("SELECT grade1,final_grade FROM grades WHERE enrollment_id=?", (eid,))[0]


# ---------- Registro inicial de notas (ruta INSERT) ----------
def test_RF06_primer_registro_de_notas_se_guarda(client, entrar, fetch, mat):
    entrar("docente@sga.local")
    r = _guardar(client, mat, 4.0, 3.5, 5.0)
    assert r.status_code < 500
    assert len(fetch("SELECT id FROM grades WHERE enrollment_id=?", (mat,))) == 1


# ---------- UT-002 Promedio (se prepara fila previa para aislar el calculo) ----------
def test_UT002_promedio_de_tres_notas(client, entrar, fetch, mat, nota_previa):
    nota_previa(mat)
    entrar("docente@sga.local")
    _guardar(client, mat, 4.0, 3.5, 5.0)
    assert _nota(fetch, mat)["final_grade"] == pytest.approx((4.0 + 3.5 + 5.0) / 3, abs=0.01)  # 4.17


def test_UT002_promedio_de_notas_iguales(client, entrar, fetch, mat, nota_previa):
    nota_previa(mat)
    entrar("docente@sga.local")
    _guardar(client, mat, 3.0, 3.0, 3.0)
    assert _nota(fetch, mat)["final_grade"] == pytest.approx(3.0)


# ---------- UT-003 Limites ----------
@pytest.mark.parametrize("nota", [0.0, 2.5, 5.0])
def test_UT003_acepta_notas_dentro_del_rango(client, entrar, fetch, mat, nota_previa, nota):
    nota_previa(mat)
    entrar("docente@sga.local")
    _guardar(client, mat, nota, nota, nota)
    assert _nota(fetch, mat)["grade1"] == pytest.approx(nota)


@pytest.mark.parametrize("nota", [-1, 5.1, 10])
def test_UT003_rechaza_notas_fuera_del_rango(client, entrar, fetch, mat, nota_previa, nota):
    nota_previa(mat)  # nota anterior = 3.0; si la entrada invalida se acepta, cambia
    entrar("docente@sga.local")
    _guardar(client, mat, nota, nota, nota)
    assert _nota(fetch, mat)["grade1"] == pytest.approx(3.0)


def test_UT003_nota_no_numerica_no_genera_error_500(client, entrar, mat):
    entrar("docente@sga.local")
    r = _guardar(client, mat, "abc", 3, 3)
    assert r.status_code < 500


def test_RF06_nota_cero_se_muestra_como_cero(client, entrar, run_sql, mat):
    run_sql("INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,0.0,0.0,0.0,0.0)", (mat,))
    entrar("estudiante@sga.local")
    html = client.get("/enrollments/my").get_data(as_text=True)
    assert "0.0, 0.0, 0.0" in html  # la plantilla muestra '-' cuando la nota es 0.0
