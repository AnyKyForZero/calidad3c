"""Prepara los datos de la prueba de carga: crea N estudiantes virtuales y escribe usuarios.csv.
Ejecutar DENTRO de la copia del proyecto que se usara para la carga (nunca en el original):
    python preparar_datos_carga.py --usuarios 300
Cuentas: carga0001@sga.test ... carga0300@sga.test   Contrasena: Carga123!
"""
import argparse, csv, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from werkzeug.security import generate_password_hash
from app import create_app
from app.config import Config

ap = argparse.ArgumentParser()
ap.add_argument("--usuarios", type=int, default=300)
ap.add_argument("--salida", default="carga/usuarios.csv")
ap.add_argument("--cupo", type=int, default=1000, help="cupo minimo de los cursos activos en la copia de carga (evita que los cupos se agoten)")
a = ap.parse_args()

create_app()                                   # crea instance/sga.db y los datos base si no existen
h = generate_password_hash("Carga123!")        # un solo hash para todos: acelera la preparacion
con = sqlite3.connect(Config.DATABASE)
for i in range(1, a.usuarios + 1):
    con.execute("INSERT OR IGNORE INTO users(document,first_name,last_name,email,phone,password_hash,role)"
                " VALUES(?,?,?,?,?,?,'student')",
                (f"8{i:05d}", f"Carga{i:04d}", "Virtual", f"carga{i:04d}@sga.test", "3000000000", h))
con.execute("UPDATE courses SET max_quota=MAX(max_quota,?) WHERE status='active'", (a.cupo,))  # solo datos de prueba, en la copia
con.commit()
n = con.execute("SELECT COUNT(*) FROM users WHERE email LIKE 'carga%@sga.test'").fetchone()[0]
con.close()
Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
with open(a.salida, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["email", "password"])
    for i in range(1, a.usuarios + 1): w.writerow([f"carga{i:04d}@sga.test", "Carga123!"])
print(f"Estudiantes de carga en la BD: {n}. Cupo minimo de cursos activos: {a.cupo}. Archivo: {a.salida}")
