"""Fase XI - Pruebas de compatibilidad (COM-029 navegadores, COM-030 tamanos de pantalla).

Ejecuta con Selenium el flujo principal del estudiante en cada navegador y en cada resolucion, y registra
navegador, version, sistema operativo, resolucion real, resultado de cada paso, diferencias y una captura.

    pip install selenium
    python compat/compatibilidad.py                       (Chrome, Edge y Firefox instalados; escritorio, tableta y movil)
    python compat/compatibilidad.py --navegadores chrome,edge --viewports escritorio,movil
    python compat/compatibilidad.py --base http://127.0.0.1:5000 --usuario-base 590

Requisitos: el servidor del SGA iniciado y usuarios de prueba carga0590.. (preparar_datos_carga.py --usuarios 600).
Selenium 4 descarga solo el driver de cada navegador (necesita internet la primera vez).
Un navegador no instalado se registra como NO DISPONIBLE, no como fallo de la aplicacion.

Escritorio = ventana real. Tableta y movil: en Chrome/Edge se emula la pantalla con el protocolo del navegador
(herramienta autorizada: equivale al modo dispositivo de las DevTools); en Firefox se redimensiona la ventana
y se registra la resolucion que realmente se obtuvo (Firefox no baja de cierto ancho minimo).
Solo contra el entorno de pruebas local.
"""
import argparse, csv, platform, sys, time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

VIEWPORTS = {"escritorio": (1366, 768), "tableta": (768, 1024), "movil": (390, 844)}

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:5000")
ap.add_argument("--navegadores", default="chrome,edge,firefox")
ap.add_argument("--viewports", default="escritorio,tableta,movil")
ap.add_argument("--usuario-base", type=int, default=590, help="se usan carga{N}, carga{N+1}... uno por navegador")
ap.add_argument("--clave", default="Carga123!")
ap.add_argument("--salida", default="compat/resultados")
ap.add_argument("--headless", action="store_true", help="sin ventana visible (solo para validar el script; para la evidencia use ventana real)")
ap.add_argument("--no-sandbox", action="store_true", help="solo contenedores/Linux como root")
a = ap.parse_args()

OUT = Path(a.salida); OUT.mkdir(parents=True, exist_ok=True)
(OUT / "capturas").mkdir(exist_ok=True)
REF = {"w": 0}
SO = f"{platform.system()} {platform.release()} ({platform.version()[:40]})"
filas = []


def crear(nombre):
    if nombre == "chrome":
        o = webdriver.ChromeOptions()
        if a.headless: o.add_argument("--headless=new")
        if a.no_sandbox: o.add_argument("--no-sandbox")
        return webdriver.Chrome(options=o)
    if nombre == "edge":
        o = webdriver.EdgeOptions()
        if a.headless: o.add_argument("--headless=new")
        if a.no_sandbox: o.add_argument("--no-sandbox")
        return webdriver.Edge(options=o)
    o = webdriver.FirefoxOptions()
    if a.headless: o.add_argument("-headless")
    return webdriver.Firefox(options=o)


def poner_viewport(d, nombre, vp):
    w, h = VIEWPORTS[vp]
    chromium = nombre in ("chrome", "edge")
    if chromium:
        try: d.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
        except Exception: pass
    if vp == "escritorio" or not chromium:
        d.set_window_size(w, h)
        dw = w - d.execute_script("return window.innerWidth"); dh = h - d.execute_script("return window.innerHeight")
        d.set_window_size(w + dw, h + dh)     # ajusta bordes de la ventana para obtener el viewport pedido
    else:
        d.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 2, "mobile": True})
    time.sleep(0.5)
    iw, ih = d.execute_script("return window.innerWidth"), d.execute_script("return window.innerHeight")
    REF["w"] = w if (chromium and vp != "escritorio") else iw     # ancho de pantalla contra el que se mide el contenido
    return iw, ih


def esperar(d, cond, seg=8):
    t = time.time()
    while time.time() - t < seg:
        try:
            if cond(): return True
        except WebDriverException: pass
        time.sleep(0.2)
    return False


def en_pantalla(d, el):
    """Visible y dentro del ancho del viewport."""
    if not el.is_displayed(): return False, "no visible"
    r = el.rect; iw = REF["w"] or d.execute_script("return window.innerWidth")
    if r["x"] < -1 or r["x"] + r["width"] > iw + 1: return False, f"fuera del ancho de pantalla (x={r['x']:.0f}, ancho={r['width']:.0f}, pantalla={iw})"
    return True, ""


def sin_scroll_h(d):
    sw, iw = d.execute_script("return [document.documentElement.scrollWidth, window.innerWidth]")
    iw = REF["w"] or iw
    return sw <= iw + 1, f"contenido {sw}px > pantalla {iw}px"


def flujo(d, nombre, version, vp, res, usuario):
    cod = "COM-029" if vp == "escritorio" else "COM-030"
    n = [0]

    def reg(prueba, ok, detalle="", captura=True):
        n[0] += 1; cap = ""
        if captura:
            cap = f"capturas/{nombre}_{vp}_{n[0]:02d}.png"
            try: d.save_screenshot(str(OUT / cap))
            except Exception: cap = ""
        filas.append([cod, nombre, version, SO, vp, res, prueba, "CUMPLE" if ok else "NO CUMPLE", detalle if not ok else "", cap])
        print(f"   [{'OK ' if ok else 'XX '}] {prueba}" + ("" if ok else f"  -> {detalle}"), flush=True)

    d.delete_all_cookies()
    # 1. Pagina de inicio de sesion
    d.get(a.base + "/auth/login")
    em = d.find_elements(By.CSS_SELECTOR, "input[name=email], input[type=email]")
    pw = d.find_elements(By.CSS_SELECTOR, "input[name=password], input[type=password]")
    if not em or not pw:
        faltan = ", ".join(x for x, l in (("campo correo", em), ("campo clave", pw)) if not l)
        reg("Login: formulario visible y utilizable", False,
            f"no se encontro: {faltan}. URL actual: {d.current_url} | titulo: '{d.title}' (si no es la pagina de login, revise --base y que el servidor este activo)")
        return
    em, pw = em[0], pw[0]
    bt = pw.find_elements(By.XPATH, "./ancestor::form//button | ./ancestor::form//input[@type='submit']")
    if not bt:
        reg("Login: formulario visible y utilizable", False, "el formulario no tiene boton de envio (button o input submit)"); return
    bt = bt[0]
    malos = [x for x, e in (("correo", em), ("clave", pw), ("boton", bt)) if not en_pantalla(d, e)[0]]
    reg("Login: formulario visible y utilizable", not malos, "no visibles/alcanzables: " + ", ".join(malos))
    ok, det = sin_scroll_h(d); reg("Login: sin desplazamiento horizontal", ok, det, captura=False)
    meta = d.execute_script("return !!document.querySelector('meta[name=viewport]')")
    reg("Meta viewport presente (adaptacion a movil)", bool(meta), "falta <meta name=\"viewport\">: los moviles muestran la pagina como escritorio reducido", captura=False)
    # 2. Iniciar sesion
    try:
        em.send_keys(usuario); pw.send_keys(a.clave); bt.click()
        ok = esperar(d, lambda: "salir" in d.page_source.lower() and "/auth/login" not in d.current_url)
        reg("Iniciar sesion con credenciales validas", ok, f"no aparece 'Salir' (URL: {d.current_url})")
        if not ok: return
    except WebDriverException as e:
        reg("Iniciar sesion con credenciales validas", False, str(e).splitlines()[0][:150]); return
    # 3. Consultar cursos
    d.get(a.base + "/courses/")
    ok = esperar(d, lambda: "codigo" in d.page_source.lower() or "código" in d.page_source.lower())
    filas_t = len(d.find_elements(By.CSS_SELECTOR, "table tbody tr, table tr"))
    reg("Consultar cursos: lista visible", ok and filas_t > 1, f"filas encontradas: {filas_t}")
    ok, det = sin_scroll_h(d); reg("Cursos: sin desplazamiento horizontal", ok, det, captura=False)
    # 4. Matricularse
    forms = d.find_elements(By.CSS_SELECTOR, "form[action*='/enrollments/enroll/']")
    if not forms:
        reg("Matricularse: boton disponible", False, "no hay formularios de matricula en la lista de cursos")
    else:
        f = forms[0]
        try:
            b = f.find_element(By.CSS_SELECTOR, "button, input[type=submit]")
            d.execute_script("arguments[0].scrollIntoView({block:'center'})", b)
            vis, det = en_pantalla(d, b)
            b.click()
            esperar(d, lambda: any(k in d.page_source.lower() for k in ("matricula registrada", "ya matriculado", "sin cupos", "no esta disponible")))
            src = d.page_source.lower()
            msg = "Matricula registrada" if "matricula registrada" in src else ("Ya matriculado" if "ya matriculado" in src else ("Sin cupos" if "sin cupos" in src else ("Curso no disponible" if "no esta disponible" in src else "")))
            reg(f"Matricularse: boton accesible y respuesta del sistema ('{msg}')", vis and bool(msg), det if not vis else "sin mensaje de respuesta")
        except WebDriverException as e:
            reg("Matricularse: boton accesible y respuesta del sistema", False, "no se pudo pulsar: " + str(e).splitlines()[0][:150])
    # 5. Mis matriculas
    d.get(a.base + "/enrollments/my")
    ok = esperar(d, lambda: "mis matriculas" in d.page_source.lower() or "mis matrículas" in d.page_source.lower())
    reg("Mis matriculas: pagina visible", ok, "no aparece el titulo")
    ok, det = sin_scroll_h(d); reg("Mis matriculas: sin desplazamiento horizontal", ok, det, captura=False)
    # 6. Cerrar sesion
    try:
        els = d.find_elements(By.XPATH, "//a[contains(normalize-space(.),'Salir')] | //button[contains(normalize-space(.),'Salir')] | //input[@value='Salir']")
        if not els:
            reg("Cerrar sesion: opcion 'Salir' accesible y cierra la sesion", False, "no existe la opcion 'Salir'")
        else:
            vis, det = en_pantalla(d, els[0])
            if vis:
                els[0].click(); time.sleep(1)
                d.get(a.base + "/enrollments/my")          # pagina protegida: sin sesion debe pedir login
                ok = esperar(d, lambda: bool(d.find_elements(By.CSS_SELECTOR, "input[name=password], input[type=password]")))
                reg("Cerrar sesion: opcion 'Salir' accesible y cierra la sesion", ok, "tras pulsar Salir la pagina protegida sigue accesible")
            else:
                reg("Cerrar sesion: opcion 'Salir' accesible y cierra la sesion", False, det)
    except WebDriverException as e:
        reg("Cerrar sesion: opcion 'Salir' accesible y cierra la sesion", False, str(e).splitlines()[0][:150])


VIEWPORT_IDX = {v: i for i, v in enumerate(VIEWPORTS)}
nav = [x.strip() for x in a.navegadores.split(",") if x.strip()]
vps = [x.strip() for x in a.viewports.split(",") if x.strip()]
for i, nombre in enumerate(nav):
    print(f"\n######## {nombre.upper()} ########", flush=True)
    try:
        d = crear(nombre)
    except Exception as e:
        det = str(e).splitlines()[0][:160]
        print(f"   NO DISPONIBLE: {det}")
        filas.append(["COM-029", nombre, "", SO, "", "", "Navegador disponible", "NO DISPONIBLE", det, ""]); continue
    try:
        version = d.capabilities.get("browserVersion", "?")
        for vp in vps:
            iw, ih = poner_viewport(d, nombre, vp)
            print(f"\n== {nombre} {version} | {vp} {iw}x{ih} ==", flush=True)
            flujo(d, nombre, version, vp, f"{iw}x{ih}", f"carga{a.usuario_base + i:04d}@sga.test")
    finally:
        d.quit()

# ---------- resultados
with open(OUT / "compat_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["caso", "navegador", "version", "sistema_operativo", "viewport", "resolucion", "prueba", "resultado", "diferencia_observada", "captura"])
    w.writerows(filas)

print("\n" + "=" * 100 + "\nRESULTADO COM-029 / COM-030 (pasos que cumplen / total por navegador y resolucion)\n" + "=" * 100)
print(f"{'Navegador':<10}{'Version':<16}{'Viewport':<12}{'Resolucion':<12}{'Cumple':>7}{'Total':>7}  Estado")
grupos = {}
for f in filas:
    grupos.setdefault((f[1], f[2], f[4], f[5]), []).append(f[7])
for (nombre, ver, vp, res), r in grupos.items():
    ok = sum(x == "CUMPLE" for x in r)
    est = "NO DISPONIBLE" if r == ["NO DISPONIBLE"] else ("CUMPLE" if ok == len(r) else "CON DIFERENCIAS")
    print(f"{nombre:<10}{ver:<16}{vp:<12}{res:<12}{ok:>7}{len(r):>7}  {est}")
dif = [f for f in filas if f[7] == "NO CUMPLE"]
if dif:
    print("\nDIFERENCIAS OBSERVADAS:")
    for f in dif: print(f"  - {f[1]} {f[4]} {f[5]}: {f[6]} -> {f[8]}")
print(f"\nEvidencia: {OUT / 'compat_resultado.csv'} y capturas en {OUT / 'capturas'}")
