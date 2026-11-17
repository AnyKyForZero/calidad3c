"""Fase XVI - Pruebas de mantenibilidad (MAN-041 duplicacion, MAN-042 complejidad).  Analisis ESTATICO: no ejecuta la app.

  man041   Duplicacion: (a) bloques de lineas repetidos entre archivos/funciones, (b) literales repetidos
           (consultas SQL y mensajes), (c) funciones con cuerpo casi identico.
  man042   Complejidad: complejidad ciclomatica (radon), tamano de funcion, anidamiento, indice de
           mantenibilidad por archivo (radon) y legibilidad (lineas largas, varias sentencias por linea).
  todo     Ejecuta ambos y escribe los CSV en carga/resultados.

    pip install radon
    python carga/mantenibilidad.py todo
    python carga/mantenibilidad.py todo --app app --umbral-cc 10 --umbral-lineas 50

Umbrales definidos por el equipo ANTES de analizar (se pueden cambiar con las opciones):
  complejidad ciclomatica por funcion : <=10 aceptable, 11-20 atencion, >20 alta   (rango radon A-B / C / D-F)
  longitud de funcion                 : >50 lineas fisicas = atencion (solo cuenta junto con otro indicador)
  anidamiento maximo                  : >4 niveles = atencion
  indice de mantenibilidad (archivo)  : >=20 aceptable (rango A radon); 10-19 media; <10 baja
  lineas de mas de 120 caracteres, y lineas con 2 o mas sentencias separadas por ';' (legibilidad)
  duplicacion: bloque de >=4 lineas significativas iguales en 2 o mas sitios; literal >=25 caracteres repetido >=3 veces
Regla de la guia: una funcion larga NO es defecto por si sola; se reporta como hallazgo solo si coincide con otro
indicador (complejidad, anidamiento, duplicacion o baja legibilidad) y se documenta su impacto.
"""
import argparse, ast, csv, hashlib, re, sys, tokenize, io
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("caso", choices=["man041", "man042", "todo"])
ap.add_argument("--app", default="app", help="carpeta del codigo fuente (por defecto app)")
ap.add_argument("--umbral-cc", type=int, default=10)
ap.add_argument("--umbral-lineas", type=int, default=50)
ap.add_argument("--umbral-anidamiento", type=int, default=4)
ap.add_argument("--ancho", type=int, default=120)
ap.add_argument("--bloque", type=int, default=4, help="lineas significativas minimas de un bloque duplicado")
a = ap.parse_args()
RES = Path("carga/resultados"); RES.mkdir(parents=True, exist_ok=True)
SELLO = datetime.now().strftime("%Y%m%d_%H%M%S")
RAIZ = Path(a.app)
ARCH = sorted(p for p in RAIZ.rglob("*.py") if "__pycache__" not in p.parts)
if not ARCH:
    sys.exit(f"No se encontraron .py en '{a.app}'. Ejecuta el comando desde la raiz del proyecto.")


def csv_out(nombre, cab, filas):
    f = RES / f"{nombre}_{SELLO}.csv"
    with open(f, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(cab); w.writerows(filas)
    return f


def rel(p): return str(p).replace("\\", "/")


# ---------------------------------------------------------------- utilidades
def lineas_significativas(texto):
    """[(nro, texto normalizado)] sin comentarios, vacias ni decoradores/import."""
    out = []
    for i, l in enumerate(texto.splitlines(), 1):
        s = re.sub(r"\s+#.*$", "", l).strip()
        if not s or s.startswith("#") or s.startswith(("import ", "from ", "@")):
            continue
        out.append((i, re.sub(r"\s+", " ", s)))
    return out


def sentencias(l):
    """Numero aproximado de sentencias en una linea (separadas por ';' fuera de cadenas)."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(l.strip() + "\n").readline))
        return 1 + sum(1 for t in toks if t.type == tokenize.OP and t.string == ";")
    except Exception:
        return 1 + l.count(";")


# ---------------------------------------------------------------- MAN-041
def man041():
    print("\nMAN-041 Duplicacion de codigo")
    hallazgos = []
    # (a) bloques de lineas significativas repetidos
    N = a.bloque
    ventanas = defaultdict(list)
    sig = {}
    for p in ARCH:
        s = lineas_significativas(p.read_text(encoding="utf-8", errors="replace"))
        sig[p] = s
        for i in range(len(s) - N + 1):
            bloque = tuple(x[1] for x in s[i:i + N])
            if sum(len(x) for x in bloque) < 80:   # ignora bloques triviales
                continue
            ventanas[bloque].append((p, s[i][0], s[i + N - 1][0]))
    vistos = set()
    for bloque, sitios in ventanas.items():
        if len(sitios) < 2: continue
        sitios = sorted(set(sitios), key=lambda t: (str(t[0]), t[1]))
        # evita informar ventanas solapadas del mismo bloque
        clave = tuple((str(p), l1 // N) for p, l1, _ in sitios)
        if clave in vistos: continue
        vistos.add(clave)
        hallazgos.append(["bloque", f"{len(sitios)} sitios", "; ".join(f"{rel(p)}:{l1}-{l2}" for p, l1, l2 in sitios), " / ".join(bloque)[:160]])
    # (b) literales repetidos (SQL, mensajes)
    lits = defaultdict(list)
    for p in ARCH:
        try: tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError: continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value.strip()) >= 25:
                lits[re.sub(r"\s+", " ", n.value.strip())].append((p, n.lineno))
    for v, sitios in lits.items():
        if len(sitios) >= 3:
            hallazgos.append(["literal", f"{len(sitios)} veces", "; ".join(f"{rel(p)}:{l}" for p, l in sitios), v[:160]])
        elif len(sitios) == 2 and re.match(r"(?i)(select|update|insert|delete)\b", v):
            hallazgos.append(["literal SQL", "2 veces", "; ".join(f"{rel(p)}:{l}" for p, l in sitios), v[:160]])
    # (c) funciones con cuerpo casi identico (estructura AST sin nombres ni constantes)
    firmas = defaultdict(list)
    for p in ARCH:
        try: tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError: continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(n.body) >= 3:
                cuerpo = ast.dump(ast.Module(body=n.body, type_ignores=[]), annotate_fields=False)
                cuerpo = re.sub(r"Name\('[^']*'", "Name('_'", cuerpo); cuerpo = re.sub(r"Constant\([^)]*\)", "C", cuerpo)
                firmas[hashlib.md5(cuerpo.encode()).hexdigest()].append((p, n.name, n.lineno))
    for sitios in firmas.values():
        if len(sitios) >= 2:
            hallazgos.append(["funcion", f"{len(sitios)} funciones", "; ".join(f"{rel(p)}:{l} {nm}()" for p, nm, l in sitios), "cuerpos con la misma estructura"])
    f = csv_out("man041_duplicacion", ["tipo", "ocurrencias", "ubicaciones", "fragmento"], hallazgos)
    total = sum(len(s) for s in sig.values())
    print(f"   Archivos analizados: {len(ARCH)}   Lineas significativas: {total}")
    if not hallazgos:
        print("   Sin duplicacion que supere los umbrales.")
    for h in hallazgos:
        print(f"   [{h[0]:11}] {h[1]:12} {h[2]}")
        print(f"                 {h[3][:110]}")
    print(f"   Hallazgos: {len(hallazgos)}   CSV: {f}")
    return hallazgos


# ---------------------------------------------------------------- MAN-042
def anidamiento(nodo, nivel=0):
    mx = nivel
    for h in ast.iter_child_nodes(nodo):
        if isinstance(h, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)):
            mx = max(mx, anidamiento(h, nivel + 1))
        else:
            mx = max(mx, anidamiento(h, nivel))
    return mx


def man042():
    print("\nMAN-042 Complejidad de funciones")
    try:
        from radon.complexity import cc_visit, cc_rank
        from radon.metrics import mi_visit, mi_rank
    except ImportError:
        sys.exit("Falta radon. Instalalo con:  pip install radon")
    funcs, archivos = [], []
    for p in ARCH:
        txt = p.read_text(encoding="utf-8", errors="replace")
        ls = txt.splitlines()
        try:
            bloques = cc_visit(txt); mi = mi_visit(txt, multi=True)
        except SyntaxError:
            continue
        tree = ast.parse(txt)
        por_linea = {n.lineno: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for b in bloques:
            if not hasattr(b, "endline") or b.__class__.__name__ == "Class":
                continue
            n = por_linea.get(b.lineno) or por_linea.get(b.lineno + 1)
            largo = b.endline - b.lineno + 1
            seg = ls[b.lineno - 1:b.endline]
            anid = anidamiento(n) if n else 0
            multi = sum(1 for l in seg if sentencias(l) >= 2)
            largas = sum(1 for l in seg if len(l) > a.ancho)
            indic = []
            if b.complexity > a.umbral_cc: indic.append(f"CC {b.complexity} > {a.umbral_cc}")
            if anid > a.umbral_anidamiento: indic.append(f"anidamiento {anid} > {a.umbral_anidamiento}")
            if largo > a.umbral_lineas: indic.append(f"longitud {largo} > {a.umbral_lineas}")
            if multi >= 3: indic.append(f"{multi} lineas con varias sentencias")
            if largas >= 3: indic.append(f"{largas} lineas > {a.ancho} car.")
            # regla de la guia: la longitud sola no basta
            fuertes = [i for i in indic if not i.startswith("longitud")]
            if b.complexity > a.umbral_cc or anid > a.umbral_anidamiento: clasif = "SUPERA UMBRAL"
            elif fuertes: clasif = "ATENCION (legibilidad)"
            elif indic: clasif = "observacion (solo longitud)"
            else: clasif = "aceptable"
            funcs.append([rel(p), b.name, b.lineno, largo, b.complexity, cc_rank(b.complexity), anid, multi, largas, clasif, "; ".join(indic)])
        total = len([l for l in ls if l.strip()])
        coment = len([l for l in ls if l.strip().startswith("#")]) + sum(l.count("  #") for l in ls)
        archivos.append([rel(p), len(ls), round(mi, 1), mi_rank(mi), sum(1 for l in ls if sentencias(l) >= 2),
                         sum(1 for l in ls if len(l) > a.ancho), round(100 * coment / max(total, 1), 1)])
    funcs.sort(key=lambda r: (-r[4], -r[3]))
    f1 = csv_out("man042_funciones", ["archivo", "funcion", "linea", "lineas", "CC", "rango", "anidamiento", "lineas_multi_sentencia", "lineas_largas", "clasificacion", "indicadores"], funcs)
    f2 = csv_out("man042_archivos", ["archivo", "lineas", "indice_mantenibilidad", "rango", "lineas_multi_sentencia", f"lineas_>{a.ancho}", "comentarios_%"], archivos)
    print(f"   Funciones analizadas: {len(funcs)}   Archivos: {len(archivos)}")
    print(f"\n   {'Archivo':28} {'Funcion':20} {'Lin':>4} {'CC':>3} {'Anid':>4} {'Multi':>5} {'Larg':>4}  Clasificacion")
    for r in funcs[:15]:
        print(f"   {r[0][-28:]:28} {r[1][:20]:20} {r[3]:>4} {r[4]:>3} {r[6]:>4} {r[7]:>5} {r[8]:>4}  {r[9]}")
    if len(funcs) > 15: print(f"   ... {len(funcs) - 15} funciones mas en el CSV")
    print(f"\n   {'Archivo':28} {'Lineas':>6} {'MI':>6} {'Rango':>5} {'Multi':>5} {'Largas':>6} {'Coment%':>7}")
    for r in sorted(archivos, key=lambda r: r[2]):
        print(f"   {r[0][-28:]:28} {r[1]:>6} {r[2]:>6} {r[3]:>5} {r[4]:>5} {r[5]:>6} {r[6]:>7}")
    sup = [r for r in funcs if r[9] == "SUPERA UMBRAL"]
    aten = [r for r in funcs if r[9].startswith("ATENCION")]
    obs = [r for r in funcs if r[9].startswith("observacion")]
    cc = [r[4] for r in funcs]
    print(f"\n   CC media {sum(cc) / max(len(cc), 1):.1f}, maxima {max(cc) if cc else 0}.  Superan umbral: {len(sup)}  |  atencion por legibilidad: {len(aten)}  |  solo longitud: {len(obs)}")
    print(f"   CSV: {f1}\n        {f2}")
    return funcs, archivos


if a.caso in ("man041", "todo"): man041()
if a.caso in ("man042", "todo"): man042()
print("\nSiguiente paso: guarda la captura de esta salida y los CSV de carga\\resultados; luego revisa manualmente las funciones marcadas.")
