"""Fase XIII - Pruebas de accesibilidad (ACC-033 teclado, ACC-034 contraste, ACC-035 nombres accesibles).

Estandar adoptado por el laboratorio: WCAG 2.1 nivel AA (contraste 4.5:1 en texto normal, 3:1 en texto grande y
componentes de interfaz; todo controlable por teclado con foco visible; controles con nombre accesible).
Herramientas: Selenium + axe-core 4.10.2 (motor de las extensiones de accesibilidad; incluido en acc/axe.min.js)
y una recorrida real de la tecla Tab.

    python acc/accesibilidad.py                                  (Chrome, paginas del estudiante)
    python acc/accesibilidad.py --navegador edge --paginas /auth/login,/courses/,/enrollments/my
    python acc/accesibilidad.py --paginas-extra /grades/my       (otras rutas)

Requisitos: servidor del SGA iniciado y la cuenta de prueba (carga0595 por defecto; preparar_datos_carga.py --usuarios 600).
Esta automatizacion cubre lo que se puede medir por programa. NO sustituye la revision con lector de pantalla (NVDA)
ni la revision de contraste en estados hover/foco/deshabilitado: ver LEEME_FASE_XIII.txt.
Solo contra el entorno de pruebas local.
"""
import argparse, csv, json, platform, sys, time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:5000")
ap.add_argument("--navegador", choices=["chrome", "edge", "firefox"], default="chrome")
ap.add_argument("--paginas", default="/auth/login,/courses/,/enrollments/my")
ap.add_argument("--paginas-extra", default="")
ap.add_argument("--usuario", default="carga0595@sga.test")
ap.add_argument("--clave", default="Carga123!")
ap.add_argument("--axe", default=str(Path(__file__).with_name("axe.min.js")))
ap.add_argument("--salida", default="acc/resultados")
ap.add_argument("--max-tab", type=int, default=80)
ap.add_argument("--headless", action="store_true"); ap.add_argument("--no-sandbox", action="store_true")
a = ap.parse_args()

OUT = Path(a.salida); OUT.mkdir(parents=True, exist_ok=True); (OUT / "capturas").mkdir(exist_ok=True)
AXE = Path(a.axe).read_text(encoding="utf-8")
SO = f"{platform.system()} {platform.release()}"
paginas = [p for p in (a.paginas + "," + a.paginas_extra).split(",") if p.strip()]

JS_AXE = """var done = arguments[arguments.length - 1];
axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}}).then(function(r) {
  function nodo(n) { var d = {}; (n.any.concat(n.all, n.none)).forEach(function(c){ if (c.data && c.data.contrastRatio) d = c.data; });
    return {sel: n.target.join(' '), html: (n.html || '').slice(0, 140), resumen: (n.failureSummary || '').split('\\n').slice(1, 2).join(' ').trim(),
            ratio: d.contrastRatio || null, esperado: d.expectedContrastRatio || null, fg: d.fgColor || null, bg: d.bgColor || null}; }
  done(JSON.stringify({
    violaciones: r.violations.map(function(v){ return {id: v.id, impacto: v.impact, ayuda: v.help, wcag: v.tags.filter(function(t){return /^wcag\\d/.test(t) || /^wcag2/.test(t);}).join(','), nodos: v.nodes.map(nodo)}; }),
    aprobadas: r.passes.length, revisar: r.incomplete.map(function(v){ return {id: v.id, n: v.nodes.length}; })}));
}).catch(function(e) { done(JSON.stringify({error: String(e)})); });"""

JS_MARCAR = """var q = 'a[href],button,input:not([type=hidden]),select,textarea,[tabindex]:not([tabindex="-1"]),summary';
var els = Array.from(document.querySelectorAll(q)).filter(function(e){ var r = e.getBoundingClientRect(); var cs = getComputedStyle(e);
  return !e.disabled && r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; });
els.forEach(function(e, i){ e.setAttribute('data-acc-i', i); });
return els.map(function(e, i){ return {i: i, tag: e.tagName.toLowerCase(), t: (e.getAttribute('aria-label') || e.innerText || e.value || e.name || e.id || '').trim().slice(0, 40)}; });"""

JS_ACTIVO = """var e = document.activeElement; if (!e || e === document.body || e === document.documentElement) return null;
var cs = getComputedStyle(e); var r = e.getBoundingClientRect();
var visible_foco = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== 'none');
return {i: e.getAttribute('data-acc-i'), tag: e.tagName.toLowerCase(), t: (e.getAttribute('aria-label') || e.innerText || e.value || e.name || e.id || '').trim().slice(0, 40),
        foco: !!visible_foco, enpantalla: r.bottom > 0 && r.top < window.innerHeight};"""

# --- clasificacion de reglas de axe por caso
ACC035 = ("label", "button-name", "link-name", "input-button-name", "select-name", "form-field-multiple-labels", "document-title",
          "html-has-lang", "html-lang-valid", "image-alt", "input-image-alt", "label-title-only", "autocomplete-valid", "frame-title",
          "aria-", "role-", "th-has-data-cells", "td-headers-attr", "scope-attr", "empty-heading", "heading-order", "page-has-heading-one")
ACC033 = ("tabindex", "focus-order-semantics", "scrollable-region-focusable", "bypass", "accesskeys", "nested-interactive", "skip-link", "frame-focusable-content")


def caso_de(regla):
    if regla == "color-contrast": return "ACC-034"
    if regla.startswith(ACC035): return "ACC-035"
    if regla.startswith(ACC033): return "ACC-033"
    return "OTRAS"


def crear():
    if a.navegador == "chrome":
        o = webdriver.ChromeOptions()
        if a.headless: o.add_argument("--headless=new")
        if a.no_sandbox: o.add_argument("--no-sandbox")
        return webdriver.Chrome(options=o)
    if a.navegador == "edge":
        o = webdriver.EdgeOptions()
        if a.headless: o.add_argument("--headless=new")
        if a.no_sandbox: o.add_argument("--no-sandbox")
        return webdriver.Edge(options=o)
    o = webdriver.FirefoxOptions()
    if a.headless: o.add_argument("-headless")
    return webdriver.Firefox(options=o)


filas = []     # caso, pagina, verificacion, resultado, impacto, detalle, elementos


def reg(caso, pagina, ver, ok, impacto="", detalle="", elementos=""):
    filas.append([caso, pagina, ver, "CUMPLE" if ok else "NO CUMPLE", impacto, detalle, elementos])
    print(f"   [{'OK ' if ok else 'XX '}] {caso} {ver}" + ("" if ok else f" ({impacto}) {detalle}"[:170]), flush=True)


def auditar_axe(d, pagina):
    d.execute_script(AXE)
    d.set_script_timeout(90)
    r = json.loads(d.execute_async_script(JS_AXE))
    if "error" in r:
        reg("OTRAS", pagina, "axe-core ejecutado", False, "", r["error"]); return
    (OUT / f"axe_{pagina.strip('/').replace('/', '_') or 'inicio'}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    por_caso = {"ACC-033": [], "ACC-034": [], "ACC-035": [], "OTRAS": []}
    for v in r["violaciones"]:
        por_caso[caso_de(v["id"])].append(v)
    for caso, ver in (("ACC-034", "Contraste de color (WCAG 1.4.3)"), ("ACC-035", "Nombres, etiquetas y estructura accesibles (WCAG 1.3.1 / 4.1.2 / 2.4.2 / 3.1.1)")):
        vs = por_caso[caso]
        if not vs:
            reg(caso, pagina, ver, True)
        for v in vs:
            if caso == "ACC-034":
                det = "; ".join(f"{n['fg']} sobre {n['bg']} = {n['ratio']}:1 (minimo {n['esperado']}:1)" for n in v["nodos"][:3])
            else:
                det = f"{v['ayuda']} ({v['id']})"
            reg(caso, pagina, f"{ver} - {v['id']}", False, v["impacto"], det + f" | {len(v['nodos'])} elemento(s)",
                " || ".join(n["sel"] for n in v["nodos"][:4]))
    for v in por_caso["ACC-033"] + por_caso["OTRAS"]:
        reg("ACC-033" if v in por_caso["ACC-033"] else "OTRAS", pagina, f"axe: {v['id']}", False, v["impacto"], f"{v['ayuda']} | {len(v['nodos'])} elemento(s)",
            " || ".join(n["sel"] for n in v["nodos"][:4]))
    if r["revisar"]:
        filas.append(["ACC-034", pagina, "Elementos que axe no pudo evaluar (revisar a mano)", "REVISAR", "", ", ".join(f"{x['id']}({x['n']})" for x in r["revisar"]), ""])
    return r


def recorrer_teclado(d, pagina):
    """Tab real sobre la pagina: orden, alcance, foco visible y trampas."""
    d.get(a.base + pagina); time.sleep(0.6)
    esperados = d.execute_script(JS_MARCAR)
    # No hacer clic en la pagina: Chrome tomaria el clic como punto de partida de Tab y saltaria lo anterior.
    d.execute_script("document.activeElement && document.activeElement.blur(); window.scrollTo(0,0);")
    alcanzados, orden, sin_foco, consec, trampa = [], [], [], 0, False
    previo = None
    for _ in range(min(a.max_tab, len(esperados) + 6)):
        ActionChains(d).send_keys(Keys.TAB).perform()
        e = d.execute_script(JS_ACTIVO)
        if e is None:
            if orden: break          # el foco salio de la pagina: el ciclo termino
            continue
        if e["i"] is not None and e["i"] in alcanzados:
            break                    # ya paso por este: ciclo completo
        consec = consec + 1 if previo == e["i"] else 0
        previo = e["i"]
        if consec >= 2: trampa = True; break
        if e["i"] is not None: alcanzados.append(e["i"])
        orden.append(f"{e['tag']}:{e['t'] or '(sin texto)'}")
        if not e["foco"]: sin_foco.append(f"{e['tag']}:{e['t'] or '(sin texto)'}")
    faltan = [f"{x['tag']}:{x['t'] or '(sin texto)'}" for x in esperados if str(x["i"]) not in alcanzados]
    reg("ACC-033", pagina, "Todos los controles se alcanzan con Tab", not faltan, "serious", f"{len(alcanzados)} de {len(esperados)} alcanzados; faltan: {', '.join(faltan[:6])}", " || ".join(faltan[:6]))
    reg("ACC-033", pagina, "Sin trampas de teclado (WCAG 2.1.2)", not trampa, "critical", "el foco se queda atascado en un control")
    reg("ACC-033", pagina, "Foco visible en cada control (WCAG 2.4.7)", not sin_foco, "serious", f"{len(sin_foco)} control(es) sin indicador de foco: {', '.join(sin_foco[:5])}", " || ".join(sin_foco[:6]))
    print(f"      orden de tabulacion: {' > '.join(orden[:12])}{' ...' if len(orden) > 12 else ''}")
    return orden


def login_por_teclado(d):
    d.get(a.base + "/auth/login"); time.sleep(0.6)
    d.delete_all_cookies(); d.get(a.base + "/auth/login")
    d.execute_script("document.activeElement && document.activeElement.blur()")
    campo_email = None
    for _ in range(8):
        ActionChains(d).send_keys(Keys.TAB).perform()
        t = d.execute_script("var e=document.activeElement; return e ? (e.name||e.type||e.tagName) : ''")
        if t in ("email",) or d.execute_script("var e=document.activeElement; return e && (e.name==='email'||e.type==='email')"):
            campo_email = True; break
    if not campo_email:
        reg("ACC-033", "/auth/login", "Iniciar sesion usando solo el teclado (Tab, texto, Enter)", False, "critical", "no se llego al campo de correo con Tab"); return False
    ActionChains(d).send_keys(a.usuario).send_keys(Keys.TAB).send_keys(a.clave).send_keys(Keys.ENTER).perform()
    ok = False
    t0 = time.time()
    while time.time() - t0 < 8 and not ok:
        ok = "salir" in d.page_source.lower() and "/auth/login" not in d.current_url
        time.sleep(0.3)
    reg("ACC-033", "/auth/login", "Iniciar sesion usando solo el teclado (Tab, texto, Enter)", ok, "critical", "con Enter no se inicio la sesion")
    return ok


d = None
try:
    d = crear()
except Exception as e:
    sys.exit(f"No se pudo abrir {a.navegador}: {str(e).splitlines()[0][:200]}")
try:
    version = d.capabilities.get("browserVersion", "?")
    print(f"\n######## {a.navegador} {version} | {SO} ########", flush=True)
    d.set_window_size(1366, 768)
    # 1) paginas publicas: login
    for pag in [p for p in paginas if p.startswith("/auth")]:
        print(f"\n== {pag} ==", flush=True)
        d.get(a.base + pag); time.sleep(0.6)
        d.save_screenshot(str(OUT / "capturas" / f"{pag.strip('/').replace('/', '_')}.png"))
        auditar_axe(d, pag); recorrer_teclado(d, pag)
    # 2) sesion iniciada solo con teclado
    print("\n== Inicio de sesion solo con teclado ==", flush=True)
    if login_por_teclado(d):
        for pag in [p for p in paginas if not p.startswith("/auth")]:
            print(f"\n== {pag} ==", flush=True)
            d.get(a.base + pag); time.sleep(0.6)
            d.save_screenshot(str(OUT / "capturas" / f"{pag.strip('/').replace('/', '_')}.png"))
            auditar_axe(d, pag); recorrer_teclado(d, pag)
    else:
        print("   No se pudo continuar sin sesion; se omiten las paginas protegidas.")
finally:
    if d: d.quit()

with open(OUT / "acc_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["caso", "pagina", "verificacion", "resultado", "impacto", "detalle", "elementos", "navegador", "version", "so"])
    for f in filas: w.writerow(f + [a.navegador, version, SO])

print("\n" + "=" * 100 + "\nRESULTADO ACC-033 / ACC-034 / ACC-035 (WCAG 2.1 AA)\n" + "=" * 100)
print(f"{'Caso':<9}{'Pagina':<22}{'Incumplimientos':>16}{'Cumple':>8}")
casos = {}
for f in filas:
    k = (f[0], f[1]); casos.setdefault(k, [0, 0])
    if f[3] == "NO CUMPLE": casos[k][0] += 1
    elif f[3] == "CUMPLE": casos[k][1] += 1
for (caso, pag), (n, ok) in sorted(casos.items()): print(f"{caso:<9}{pag:<22}{n:>16}{ok:>8}")
graves = [f for f in filas if f[3] == "NO CUMPLE"]
orden_imp = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3, "": 4, None: 4}
if graves:
    print("\nBARRERAS ENCONTRADAS (mas graves primero):")
    for f in sorted(graves, key=lambda x: orden_imp.get(x[4], 4))[:25]:
        print(f"  - [{f[4] or '-'}] {f[0]} {f[1]}: {f[2]} -> {f[5][:140]}")
print(f"\nEvidencia: {OUT / 'acc_resultado.csv'}, un JSON de axe por pagina y capturas en {OUT / 'capturas'}")
