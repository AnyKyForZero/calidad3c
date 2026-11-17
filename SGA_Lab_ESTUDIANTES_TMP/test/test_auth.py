"""RF01 / RF02 / RNF02 - Registro, validacion de correo y autenticacion."""
import pytest
from app.auth import valid_email

DATOS = dict(document="9001", first_name="Ana", last_name="Prueba",
             email="ana.prueba@test.com", phone="3001112233", password="Clave123!")


# ---------- UT-001 Validacion de correo (componente) ----------
@pytest.mark.parametrize("email", ["a@b.com", "usuario.nombre@dominio.co", "x_y+z@sub.dominio.edu.co"])
def test_valid_email_acepta_correos_validos(email):
    assert valid_email(email)


@pytest.mark.parametrize("email", ["@", "a@", "@b.com", "a@b", "sin-arroba", "a b@c.com", ""])
def test_valid_email_rechaza_correos_invalidos(email):
    # RF01: correo valido. Varios casos FALLAN -> defecto DEF-01
    assert not valid_email(email)


# ---------- INT-005 Registro y autenticacion (integracion) ----------
def test_INT005_registro_y_login(client, fetch):
    r = client.post("/auth/register", data=DATOS)
    assert r.status_code == 302
    assert len(fetch("SELECT id FROM users WHERE email=?", (DATOS["email"],))) == 1
    r = client.post("/auth/login", data={"email": DATOS["email"], "password": DATOS["password"]})
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert "user_id" in s


def test_INT005_login_con_correo_registrado_en_mayusculas(client):
    # El login normaliza a minusculas; el registro debe guardar el correo igual de normalizado.
    d = dict(DATOS, email="Ana.Prueba@Test.com")
    client.post("/auth/register", data=d)
    client.post("/auth/login", data={"email": d["email"], "password": d["password"]})
    with client.session_transaction() as s:
        assert "user_id" in s


def test_RF01_correo_duplicado_rechazado_con_mensaje_controlado(client, fetch):
    client.post("/auth/register", data=DATOS)
    r = client.post("/auth/register", data=dict(DATOS, document="9002"))
    assert len(fetch("SELECT id FROM users WHERE email=?", (DATOS["email"],))) == 1
    assert b"UNIQUE" not in r.data  # no exponer errores internos de SQLite


def test_RNF02_contrasena_no_se_guarda_en_texto_plano(client, fetch):
    client.post("/auth/register", data=DATOS)
    h = fetch("SELECT password_hash FROM users WHERE email=?", (DATOS["email"],))[0]["password_hash"]
    assert h != DATOS["password"]


# ---------- RF02 Autenticacion y bloqueo ----------
def test_RF02_credenciales_invalidas_no_abren_sesion(client):
    client.post("/auth/login", data={"email": "estudiante@sga.local", "password": "mala"})
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_RF02_bloqueo_tras_cinco_intentos_fallidos(client):
    for _ in range(5):
        client.post("/auth/login", data={"email": "estudiante@sga.local", "password": "mala"})
    r = client.post("/auth/login", data={"email": "estudiante@sga.local", "password": "Estudiante123!"})
    with client.session_transaction() as s:
        assert "user_id" not in s
    assert b"bloqueada" in r.data


def test_RF02_cuatro_fallos_no_bloquean(client):
    for _ in range(4):
        client.post("/auth/login", data={"email": "estudiante@sga.local", "password": "mala"})
    client.post("/auth/login", data={"email": "estudiante@sga.local", "password": "Estudiante123!"})
    with client.session_transaction() as s:
        assert "user_id" in s


# ---------- SEC-040 Politica de contrasenas (supuesto: minimo 8 caracteres) ----------
@pytest.mark.parametrize("clave", ["1", "abc"])
def test_SEC040_rechaza_contrasenas_cortas(client, fetch, clave):
    client.post("/auth/register", data=dict(DATOS, password=clave))
    assert fetch("SELECT id FROM users WHERE email=?", (DATOS["email"],)) == []
