"""Fase VII - Pruebas de regresion (REG-017 a REG-020).
Conserva los resultados ANTERIORES y POSTERIORES a las modificaciones y compara prueba por prueba
para detectar efectos secundarios:
    PASA  -> PASA   funcionalidad que se mantiene
    FALLA -> PASA   defecto corregido (lo confirma la Fase VI)
    PASA  -> FALLA  REGRESION (efecto secundario del cambio)
    FALLA -> FALLA  defecto que sigue abierto

Uso (desde la raiz del proyecto, con el entorno virtual activo):
  1) En el proyecto ORIGINAL, antes de corregir:      python regresion.py antes
  2) En la copia CORREGIDA, despues de los cambios:   python regresion.py despues ..\\ruta\\resultados_antes.json
Genera resultados_antes.json / resultados_despues.json y, al final, regresion_resultado.csv
y regresion_detalle.csv (evidencia).
"""
import csv, json, sys
from datetime import datetime
import pytest

# Grupos por caso REG (se asigna cada prueba al primero que coincida)
GRUPOS = [
    ("REG-017", "Regresion de autenticacion", ["test_auth.py", "test_SYS012", "test_SYS010_sin_sesion", "test_RF04_matricula_requiere_autenticacion"]),
    ("REG-018", "Regresion de matriculas",    ["test_enrollments.py", "test_SYS009"]),
    ("REG-019", "Regresion de calificaciones", ["test_grades.py", "test_SYS011"]),
    ("REG-020", "Regresion de permisos",       ["test_SYS010", "test_SEC038", "test_SEC039", "test_system_security.py"]),
    ("ACE",     "Aceptacion del proceso (complementario)", ["test_aceptacion.py"]),
]


class Registro:
    def __init__(self): self.res = {}
    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and not report.passed):
            self.res[report.nodeid.replace("\\", "/")] = "PASA" if report.passed else "FALLA"


def ejecutar():
    reg = Registro()
    pytest.main(["-q", "-p", "no:cacheprovider", "--no-header", "test"], plugins=[reg])
    return reg.res


def grupo(nodeid):
    for cod, nombre, claves in GRUPOS:
        if any(k in nodeid for k in claves):
            return cod, nombre
    return "OTRO", "Otras pruebas"


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("antes", "despues"):
        print(__doc__); return
    fase = sys.argv[1]
    res = ejecutar()
    with open(f"resultados_{fase}.json", "w", encoding="utf-8") as fh:
        json.dump({"fecha": datetime.now().isoformat(timespec="seconds"), "resultados": res}, fh, indent=1, ensure_ascii=False)
    n_ok = sum(v == "PASA" for v in res.values())
    print(f"\nGuardado resultados_{fase}.json  ({n_ok}/{len(res)} pruebas pasan)")
    if fase == "antes":
        print("Ahora aplica las modificaciones en la copia y ejecuta:  python regresion.py despues <ruta a resultados_antes.json>")
        return

    ruta = sys.argv[2] if len(sys.argv) > 2 else "resultados_antes.json"
    antes = json.load(open(ruta, encoding="utf-8"))["resultados"]
    detalle, resumen = [], {}
    for nodeid in sorted(set(antes) | set(res)):
        a, d = antes.get(nodeid, "NUEVA"), res.get(nodeid, "AUSENTE")
        cat = {("PASA", "PASA"): "SE MANTIENE", ("FALLA", "PASA"): "CORREGIDO", ("PASA", "FALLA"): "REGRESION",
               ("FALLA", "FALLA"): "DEFECTO ABIERTO"}.get((a, d), f"{a}->{d}")
        cod, nombre = grupo(nodeid)
        detalle.append([cod, nodeid, a, d, cat])
        r = resumen.setdefault(cod, {"nombre": nombre, "SE MANTIENE": 0, "CORREGIDO": 0, "REGRESION": 0, "DEFECTO ABIERTO": 0, "otros": 0})
        r[cat if cat in r else "otros"] += 1

    print("\n" + "=" * 112 + "\nRESULTADO DE LAS PRUEBAS DE REGRESION (antes vs despues)\n" + "=" * 112)
    print(f"{'REG':<9}{'Se mantiene':>12}{'Corregido':>11}{'REGRESION':>11}{'Abierto':>9}   Decision")
    filas = []
    for cod, nombre, _ in GRUPOS + [("OTRO", "Otras pruebas", [])]:
        if cod not in resumen: continue
        r = resumen[cod]
        dec = "SIN REGRESIONES" if r["REGRESION"] == 0 else f"HAY {r['REGRESION']} REGRESION(ES)"
        print(f"{cod:<9}{r['SE MANTIENE']:>12}{r['CORREGIDO']:>11}{r['REGRESION']:>11}{r['DEFECTO ABIERTO']:>9}   {dec}  - {nombre}")
        filas.append([cod, nombre, r["SE MANTIENE"], r["CORREGIDO"], r["REGRESION"], r["DEFECTO ABIERTO"], dec])
    reg_list = [d for d in detalle if d[4] == "REGRESION"]
    if reg_list:
        print("\nPRUEBAS QUE PASABAN Y AHORA FALLAN:")
        for d in reg_list: print("  -", d[1])
    print("\nDECISION GLOBAL:", "SIN REGRESIONES: las modificaciones no afectaron lo que funcionaba." if not reg_list
          else f"{len(reg_list)} REGRESION(ES) DETECTADA(S): revisar el cambio que las causo.")
    with open("regresion_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";"); w.writerow(["REG", "Grupo", "Se mantiene", "Corregido", "Regresion", "Defecto abierto", "Decision"]); w.writerows(filas)
    with open("regresion_detalle.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";"); w.writerow(["REG", "Prueba", "Antes", "Despues", "Clasificacion"]); w.writerows(detalle)


if __name__ == "__main__":
    main()
