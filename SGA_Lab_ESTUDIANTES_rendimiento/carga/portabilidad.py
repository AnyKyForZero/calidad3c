"""Fase XVII - Pruebas de portabilidad (POR-043, POR-044; apoyo para POR-045).  SOLO ENTORNO DE LABORATORIO.

  por043   Instala una COPIA del proyecto en otra ubicacion, con un entorno virtual NUEVO, siguiendo lo documentado
           (requirements.txt) y la pone en marcha en otro puerto. Hace una prueba de humo (inicio, cursos, registro, login).
  por044   Revisa rutas y configuracion: busca rutas absolutas en el codigo, comprueba que la BD y las carpetas quedan
           DENTRO de la copia aunque se ejecute desde otro directorio y que no se toca la BD original.
  todo     por043 + por044 (por044 usa la copia creada por por043).
  limpiar  Borra la copia de prueba.

    python carga/portabilidad.py todo
    python carga/portabilidad.py limpiar

Reglas: el proyecto original NO se modifica (se copia). La copia vive en una carpeta hermana 'SGA Portabilidad POR043'
(con espacio a proposito, como ocurre en rutas reales de Windows). No se usan datos reales; la cuenta de humo es por.test01@sga.test.
Registra tambien: entorno original, entorno destino, cambios de configuracion necesarios y pasos que hubo que agregar.
"""
import argparse, csv, json, os, platform, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("caso", choices=["por043", "por044", "todo", "limpiar"])
ap.add_argument("--proyecto", default=".", help="raiz del proyecto original (por defecto la carpeta actual)")
ap.add_argument("--destino", help="carpeta de la copia (por defecto <padre>/SGA Portabilidad POR043)")
ap.add_argument("--puerto", type=int, default=5200)
ap.add_argument("--requisitos", default="requirements.txt")
a = ap.parse_args()

ORIG = Path(a.proyecto).resolve()
DEST = Path(a.destino).resolve() if a.destino else ORIG.parent / "SGA Portabilidad POR043"
MARCA = DEST / ".por043"
RES = ORIG / "carga" / "resultados"; RES.mkdir(parents=True, exist_ok=True)
SELLO = datetime.now().strftime("%Y%m%d_%H%M%S")
WIN = os.name == "nt"
filas, cambios, entorno = [], [], {}


def reg(caso, paso, ok, detalle="", seg=None):
    filas.append([caso, paso, "CUMPLE" if ok else "NO CUMPLE", detalle, "" if seg is None else f"{seg:.1f}"])
    print(f"   [{'OK ' if ok else 'XX '}] {caso} {paso}" + (f" -> {detalle}" if detalle else "") + (f"  ({seg:.1f} s)" if seg is not None else ""), flush=True)


def cambio(texto):
    cambios.append(texto); print(f"   [!!] CAMBIO NECESARIO NO DOCUMENTADO: {texto}", flush=True)


def correr(cmd, cwd, timeout=600, env=None):
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr).strip(), time.time() - t
    except subprocess.TimeoutExpired:
        return 124, "tiempo agotado", time.time() - t


def py_venv():
    return DEST / ".venv" / ("Scripts" if WIN else "bin") / ("python.exe" if WIN else "python")


def info_entorno(etiqueta, py=None):
    py = py or sys.executable
    c, out, _ = correr([str(py), "-c", "import sys,platform;print(platform.platform());print(sys.version.split()[0]);print(sys.prefix)"], ORIG, 60)
    l = out.splitlines() if c == 0 else ["?", "?", "?"]
    c2, fr, _ = correr([str(py), "-m", "pip", "list", "--format=freeze"], ORIG, 120)
    entorno[etiqueta] = {"sistema": l[0], "python": l[1], "prefijo": l[2], "paquetes": fr.splitlines() if c2 == 0 else []}
    print(f"   Entorno {etiqueta}: {l[0]} | Python {l[1]} | {len(entorno[etiqueta]['paquetes'])} paquetes")


def copiar():
    if DEST.exists():
        if not MARCA.exists():
            sys.exit(f"La carpeta {DEST} ya existe y no es una copia de prueba. Usa --destino con otra ruta.")
        shutil.rmtree(DEST)
    ign = shutil.ignore_patterns(".venv", "venv", "__pycache__", "*.pyc", ".git", ".pytest_cache", "resultados", "*.db", "*.db-journal", "*.jtl", "*.log")
    shutil.copytree(ORIG, DEST, ignore=ign)
    MARCA.write_text("copia de prueba de portabilidad (Fase XVII). Se puede borrar.", encoding="utf-8")
    (DEST / "instance").mkdir(exist_ok=True)


def espera(puerto, s=40):
    import requests
    t = time.time()
    while time.time() - t < s:
        try:
            requests.Session().get(f"http://127.0.0.1:{puerto}/", timeout=2); return True
        except Exception:
            time.sleep(0.5)
    return False


def por043():
    print(f"\nPOR-043 Instalacion en otro entorno\n   Origen : {ORIG}\n   Destino: {DEST}")
    info_entorno("original")
    db_orig = None
    c, out, _ = correr([sys.executable, "-c", "from app.config import Config;print(Config.DATABASE)"], ORIG, 60)
    if c == 0 and out.strip():
        p = Path(out.splitlines()[-1].strip()); db_orig = (p, p.stat().st_size, p.stat().st_mtime) if p.exists() else (p, None, None)
    t = time.time(); copiar()
    reg("POR-043", "Copia limpia del proyecto (sin .venv, bases de datos ni resultados)", True, f"{sum(1 for _ in DEST.rglob('*') if _.is_file())} archivos", time.time() - t)
    docs = [n for n in ("README.md", "README.txt", "INSTALACION.md", "LEEME.txt", "LEEME.md") if (DEST / n).exists()]
    reg("POR-043", "Hay documentacion de instalacion en la raiz", bool(docs), ", ".join(docs) or "no hay README/INSTALACION/LEEME en la raiz del proyecto")
    req = DEST / a.requisitos
    reg("POR-043", f"Existe {a.requisitos} con las dependencias", req.exists(), "" if req.exists() else "sin archivo de requisitos: no se puede reproducir el entorno")
    t = time.time(); c, out, _ = correr([sys.executable, "-m", "venv", str(DEST / ".venv")], DEST, 300)
    reg("POR-043", "Crear entorno virtual nuevo en el destino", c == 0, out[-200:] if c else "", time.time() - t)
    if c: return
    vpy = py_venv()
    if req.exists():
        t = time.time(); c, out, _ = correr([str(vpy), "-m", "pip", "install", "-r", str(req)], DEST, 900)
        reg("POR-043", "Instalar dependencias con pip install -r requirements.txt", c == 0, out.splitlines()[-1][:200] if c else "", time.time() - t)
    else:
        t = time.time(); c, out, _ = correr([str(vpy), "-m", "pip", "install", "flask", "waitress", "requests"], DEST, 900)
        cambio("No hay requirements.txt: hubo que deducir e instalar a mano flask, waitress y requests")
        reg("POR-043", "Instalar dependencias deduciendolas del codigo", c == 0, "", time.time() - t)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")}
    env["PYTHONIOENCODING"] = "utf-8"
    chk = lambda m: correr([str(vpy), "-c", f"import {m}"], DEST, 60, env)[0] == 0
    faltan = [m for m in ("flask", "waitress") if not chk(m)]
    if faltan:
        cambio(f"Faltaban en las dependencias documentadas: {', '.join(faltan)} (se instalaron a mano)")
        correr([str(vpy), "-m", "pip", "install", *faltan], DEST, 600, env)
    reg("POR-043", "Dependencias suficientes para ejecutar (flask y waitress)", not faltan, "faltaban: " + ", ".join(faltan) if faltan else "")
    log = open(RES / f"portabilidad_servidor_{SELLO}.log", "w", encoding="utf-8")
    srv = subprocess.Popen([str(vpy), "-m", "waitress", f"--port={a.puerto}", "run:app"], cwd=str(DEST), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        t = time.time(); arriba = espera(a.puerto)
        reg("POR-043", f"Poner en marcha: waitress --port={a.puerto} run:app (desde la copia)", arriba, "" if arriba else "el servidor no respondio; ver el log", time.time() - t)
        if arriba:
            import requests
            s = requests.Session(); s.trust_env = False; s.headers["Connection"] = "close"; U = f"http://127.0.0.1:{a.puerto}"
            for ruta, txt in (("/", "pagina de inicio"), ("/courses/", "listado de cursos"), ("/auth/login", "formulario de ingreso")):
                r = s.get(U + ruta, timeout=20); reg("POR-043", f"Prueba de humo: {txt}", r.status_code == 200, f"HTTP {r.status_code}")
            clave = "Lab#Segura2026"
            s.post(U + "/auth/register", data=dict(document="POR0001", first_name="Por", last_name="Test", email="por.test01@sga.test", phone="3000000000", password=clave), timeout=20)
            r = s.post(U + "/auth/login", data={"email": "por.test01@sga.test", "password": clave}, timeout=20)
            reg("POR-043", "Prueba de humo: registrar una cuenta e iniciar sesion", "salir" in r.text.lower(), "cuenta por.test01 (sin mostrar clave)")
            r = s.get(U + "/enrollments/my", timeout=20); reg("POR-043", "Prueba de humo: Mis matriculas (sesion iniciada)", r.status_code == 200, f"HTTP {r.status_code}")
    finally:
        srv.terminate()
        try: srv.wait(10)
        except Exception: srv.kill()
        log.close()
    dbn = DEST / "instance" / "sga.db"
    reg("POR-043", "La base de datos se creo dentro de la copia (instance/sga.db)", dbn.exists(), str(dbn) if dbn.exists() else "no se encontro instance/sga.db en la copia")
    if db_orig and db_orig[1] is not None:
        p, sz, mt = db_orig; igual = p.exists() and p.stat().st_size == sz and p.stat().st_mtime == mt
        reg("POR-043", "La base de datos del proyecto ORIGINAL no fue tocada", igual, str(p))
    info_entorno("destino", vpy)
    escribir_borrador(vpy)


def escribir_borrador(vpy):
    """Genera, a partir de lo que SI funciono, un borrador de instrucciones y (si falta) un requirements sugerido."""
    pv = entorno.get("destino", {}).get("python", "?")
    if not (DEST / a.requisitos).exists():
        pk = [p for p in entorno.get("destino", {}).get("paquetes", []) if p.split("==")[0].lower() not in ("pip", "setuptools", "wheel")]
        (RES / "requirements_sugerido.txt").write_text("\n".join(pk) + "\n", encoding="utf-8")
        print(f"   Se genero {RES / 'requirements_sugerido.txt'} (copialo a la raiz como requirements.txt)")
    md = f"""# Instalacion y puesta en marcha del SGA (borrador generado por portabilidad.py)

Verificado en: {entorno.get('destino', {}).get('sistema', '?')}, Python {pv}.

## Requisitos
- Python {pv} (version con la que se verifico) y pip.
- Windows (PowerShell) o Linux/Mac. No se necesita instalar una base de datos: usa SQLite.

## Pasos
1. Copiar la carpeta del proyecto (sin la carpeta `.venv`: un entorno virtual NO se puede copiar a otra ruta, `pip.exe` guarda la ruta original).
2. Abrir una terminal en la raiz del proyecto y crear el entorno virtual: `python -m venv .venv`
3. Activarlo: `.venv\\Scripts\\Activate.ps1` (Windows) o `source .venv/bin/activate` (Linux/Mac)
4. Instalar dependencias: `python -m pip install -r requirements.txt`
5. Iniciar el servidor: `python -m waitress --port=5000 run:app`
6. Abrir `http://127.0.0.1:5000/` en el navegador (no usar 0.0.0.0).

## Notas
- La base de datos se crea sola en `instance/sga.db` la primera vez que se inicia la aplicacion.
- El puerto se cambia con `--port`.
"""
    (RES / "INSTALACION_borrador.md").write_text(md, encoding="utf-8")
    print(f"   Se genero {RES / 'INSTALACION_borrador.md'} (borrador para la documentacion; revisalo antes de usarlo)")


def escanear():
    ext = {".py", ".html", ".js", ".css", ".cfg", ".ini", ".json", ".txt", ".md", ".ps1", ".bat", ".toml", ".yml", ".yaml", ".env"}
    pat = {"ruta absoluta de Windows": re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:(?:\\\\|\\|/)(?!/)"),
           "ruta absoluta de Linux/Mac": re.compile(r"(?<![\w.:/])/(?:home|Users|tmp|var|opt|etc|mnt)/\w")}
    out, info = [], []
    for p in DEST.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in ext: continue
        partes = set(p.relative_to(DEST).parts)
        if partes & {".venv", "__pycache__", "instance", "resultados"}: continue
        aplic = (p.relative_to(DEST).parts[0] in ("app", "run.py", "config.py", "wsgi.py")) or len(p.relative_to(DEST).parts) == 1
        herr = p.relative_to(DEST).parts[0] in ("carga", "compat", "acc", "test", "tests", "p")
        try: txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception: continue
        for i, l in enumerate(txt.splitlines(), 1):
            for n, rx in pat.items():
                if rx.search(l):
                    (info if herr and not aplic else out).append((str(p.relative_to(DEST)).replace("\\", "/"), i, n, l.strip()[:90]))
            if re.search(r"SECRET_KEY\s*=\s*['\"]", l) and not herr:
                info.append((str(p.relative_to(DEST)).replace("\\", "/"), i, "clave secreta fija en el codigo (configurar por variable de entorno)", l.strip()[:60]))
    return out, info


def por044():
    print(f"\nPOR-044 Rutas y configuracion\n   Copia analizada: {DEST}")
    if not MARCA.exists(): sys.exit("Primero ejecuta por043 (crea la copia).")
    vpy = py_venv()
    out, info = escanear()
    reg("POR-044", "El codigo de la aplicacion no contiene rutas absolutas", not out, "; ".join(f"{f}:{l} {n}" for f, l, n, _ in out[:5]))
    for f, l, n, t in out[:8]: print(f"        {f}:{l} [{n}] {t}")
    if info: print(f"   Informativo (no cuenta como incumplimiento): {len(info)} coincidencias"); [print(f"        {f}:{l} [{n}]") for f, l, n, _ in info[:6]]
    cfg = next((p for p in (DEST / "app" / "config.py", DEST / "config.py") if p.exists()), None)
    txt = cfg.read_text(encoding="utf-8", errors="replace") if cfg else ""
    usa_env = bool(re.search(r"environ|getenv", txt))
    reg("POR-044", "La configuracion permite cambiar valores por variable de entorno (SECRET_KEY, BD)", usa_env, "" if usa_env else "la configuracion esta fija en el codigo; no hay variables de entorno")
    otro = Path(tempfile.mkdtemp(prefix="por044_cwd_"))
    code = ("import sys;sys.path.insert(0,r'%s');from app.config import Config;from app import create_app;a=create_app();"
            "print(Config.DATABASE);print(a.instance_path)" % DEST)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")}
    c, o, _ = correr([str(vpy), "-c", code], otro, 120, env)
    if c != 0:
        reg("POR-044", "Ejecutar desde otro directorio de trabajo", False, o.splitlines()[-1][:200] if o else "error")
    else:
        ls = o.splitlines(); dbp, inst = Path(ls[-2]), Path(ls[-1])
        dentro = lambda p: str(p.resolve()).lower().startswith(str(DEST.resolve()).lower())
        reg("POR-044", "Ejecutando desde otro directorio, la BD queda dentro de la copia", dbp.is_absolute() and dentro(dbp), str(dbp))
        reg("POR-044", "Ejecutando desde otro directorio, la carpeta instance queda dentro de la copia", dentro(inst), str(inst))
        sueltos = [p.name for p in otro.iterdir()]
        reg("POR-044", "No se crean archivos sueltos en el directorio desde el que se ejecuta", not sueltos, ", ".join(sueltos))
    shutil.rmtree(otro, ignore_errors=True)
    est = [p for p in (DEST / "app" / "static", DEST / "app" / "templates") if p.exists()]
    reg("POR-044", "Plantillas y recursos estaticos viajan con la copia", len(est) >= 1, ", ".join(p.name for p in est))
    reg("POR-044", "Codificacion y rutas con espacios (la copia esta en una carpeta con espacio)", " " in str(DEST), str(DEST.name))


def limpiar():
    if DEST.exists() and MARCA.exists():
        shutil.rmtree(DEST, ignore_errors=True); print(f"Copia eliminada: {DEST}")
    else:
        print("No hay copia de prueba que borrar (o la carpeta no fue creada por este script).")


def cerrar():
    f = RES / f"portabilidad_{a.caso}_{SELLO}.csv"
    with open(f, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["caso", "paso", "resultado", "detalle", "segundos"]); w.writerows(filas)
    j = RES / f"portabilidad_entornos_{SELLO}.json"
    j.write_text(json.dumps({"entornos": entorno, "cambios_no_documentados": cambios}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 92)
    for c in ("POR-043", "POR-044"):
        x = [r for r in filas if r[0] == c]
        if x:
            bad = [r for r in x if r[2] != "CUMPLE"]
            print(f"{c}: {len(x) - len(bad)}/{len(x)} CUMPLE" + ("" if not bad else "  -> NO CUMPLE: " + " | ".join(r[1] for r in bad)))
    if entorno:
        for k, v in entorno.items(): print(f"Entorno {k}: {v['sistema']} | Python {v['python']}")
    if cambios:
        print("Cambios/pasos NO documentados que fueron necesarios:"); [print("  - " + c) for c in cambios]
    print(f"Resultados: {f}\nEntornos  : {j}\nCuando termines: python carga/portabilidad.py limpiar")


if a.caso == "limpiar": limpiar()
else:
    if a.caso in ("por043", "todo"): por043()
    if a.caso in ("por044", "todo"): por044()
    cerrar()
