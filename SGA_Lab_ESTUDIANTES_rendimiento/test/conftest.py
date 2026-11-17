"""Fixtures compartidas. Cada prueba usa una BD SQLite temporal y aislada:
no toca instance/sga.db ni el codigo original del SGA."""
import sqlite3
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.config import Config

CLAVE = "Clave123!"
_HASH = generate_password_hash(CLAVE)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATABASE", tmp_path / "sga_test.db")
    app = create_app()
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def fetch(app):
    """fetch(sql, params) -> lista de filas (sqlite3.Row) de la BD de prueba."""
    def _fetch(sql, params=()):
        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, params).fetchall()
        con.close()
        return rows
    return _fetch


@pytest.fixture
def run_sql(app):
    """run_sql(sql, params) -> ejecuta INSERT/UPDATE de preparacion de datos."""
    def _run(sql, params=()):
        con = sqlite3.connect(app.config["DATABASE"])
        cur = con.execute(sql, params)
        con.commit()
        last = cur.lastrowid
        con.close()
        return last
    return _run


@pytest.fixture
def uid(fetch):
    """uid('estudiante@sga.local') -> id del usuario sembrado."""
    return lambda email: fetch("SELECT id FROM users WHERE email=?", (email,))[0]["id"]


@pytest.fixture
def cid(fetch):
    """cid('CAL201') -> id del curso sembrado."""
    return lambda code: fetch("SELECT id FROM courses WHERE code=?", (code,))[0]["id"]


@pytest.fixture
def entrar(client, uid):
    """entrar('docente@sga.local') -> abre sesion sin pasar por el formulario."""
    def _entrar(email):
        with client.session_transaction() as s:
            s["user_id"] = uid(email)
    return _entrar


@pytest.fixture
def nuevo_estudiante(run_sql):
    """nuevo_estudiante(n) -> crea un estudiante de prueba y devuelve su id."""
    def _nuevo(n):
        return run_sql(
            "INSERT INTO users(document,first_name,last_name,email,phone,password_hash,role)"
            " VALUES(?,?,?,?,?,?,'student')",
            (f"9{n:04d}", f"Est{n}", "Prueba", f"est{n}@test.local", "3000000000", _HASH))
    return _nuevo


@pytest.fixture
def matricula(run_sql):
    """matricula(student_id, course_id) -> crea la matricula directamente en BD."""
    return lambda s, c: run_sql("INSERT INTO enrollments(student_id,course_id) VALUES(?,?)", (s, c))


@pytest.fixture
def nota_previa(run_sql):
    """nota_previa(eid) -> deja una fila de notas 3.0/3.0/3.0 ya creada.
    Se usa para aislar el calculo/validacion (ruta UPDATE) del defecto de la ruta INSERT."""
    return lambda eid: run_sql(
        "INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,3.0,3.0,3.0,3.0)", (eid,))
