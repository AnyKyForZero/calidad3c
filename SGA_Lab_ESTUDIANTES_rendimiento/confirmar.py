"""Fase VI - Pruebas de confirmacion (CON-013 a CON-016).
Repite EXACTAMENTE los casos que fallaron al detectar cada defecto (mismas entradas) y compara
el resultado original con el actual. Un defecto solo se declara CONFIRMADO COMO CORREGIDO si
todos sus casos asociados pasan; que la aplicacion inicie no cuenta como evidencia.

Uso (desde la carpeta del proyecto, con el entorno virtual activo):
    python confirmar.py
Genera confirmacion_resultado.csv (evidencia posterior a la correccion).
"""
import csv, sys
import pytest

# defecto, CON, casos originales, resultado original, fragmentos de nombre de prueba que lo confirman
DEFECTOS = [
    ("DEF-01", "CON-013", "UT-001",          "5 de 7 correos invalidos aceptados", ["test_valid_email_rechaza_correos_invalidos", "test_valid_email_acepta_correos_validos"]),
    ("DEF-07", "CON-013", "INT-005",         "Login falla con correo registrado en mayusculas", ["test_INT005_"]),
    ("DEF-08", "CON-013", "EXT-02",          "Se muestra 'UNIQUE constraint failed'", ["test_RF01_correo_duplicado"]),
    ("DEF-11", "CON-013", "EXT-07",          "Se crean cursos con cupo 0 y -5", ["test_RF03_rechaza_cupo_no_positivo"]),
    ("DEF-12", "CON-013", "EXT-07",          "Se crea curso con codigo duplicado", ["test_RF03_rechaza_codigo_de_curso_duplicado"]),
    ("DEF-02", "CON-014", "UT-002, SYS-011", "Definitiva 6,25 en vez de 4,17", ["test_UT002_", "test_SYS011_promedio"]),
    ("DEF-03", "CON-014", "UT-003",          "Se guardan notas -1, 5,1 y 10", ["test_UT003_acepta", "test_UT003_rechaza"]),
    ("DEF-06", "CON-014", "SYS-011, EXT-04", "Error 500 al guardar notas por primera vez", ["test_RF06_primer_registro", "test_SYS011_flujo_completo"]),
    ("DEF-09", "CON-014", "UT-003",          "Error 500 con nota no numerica", ["test_UT003_nota_no_numerica"]),
    ("DEF-10", "CON-014", "EXT-05",          "La nota 0,0 se muestra como '-'", ["test_RF06_nota_cero"]),
    ("DEF-04", "CON-015", "UT-004, INT-006, EXT-08", "enrolled_count nunca aumenta", ["test_UT004_", "test_INT006_", "test_RF05_cupo_se_agota", "test_SYS009_estado_de_datos_cupo"]),
    ("DEF-05", "CON-015", "INT-008",         "Se matricula en curso inactivo", ["test_INT008_", "test_SYS009_estado_de_datos_curso_inactivo"]),
    ("DEF-13", "CON-016", "SEC-039",         "Docente califica curso ajeno", ["test_SEC039_docente_no_califica"]),
    ("DEF-14", "CON-016", "SYS-012",         "Paginas protegidas sin Cache-Control: no-store", ["test_SYS012_boton_atras"]),
]


class Registro:
    def __init__(self): self.res = {}
    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and not report.passed):
            self.res[report.nodeid] = report.passed


def main():
    reg = Registro()
    pytest.main(["-q", "-p", "no:cacheprovider", "--no-header", "-x" if False else "-q", "test"], plugins=[reg])
    filas = []
    for d, con, casos, original, claves in DEFECTOS:
        ids = [n for n in reg.res if any(k in n for k in claves)]
        ok = sum(reg.res[n] for n in ids)
        confirmado = bool(ids) and ok == len(ids)
        filas.append([con, d, casos, original, "Fallida", f"{ok}/{len(ids)} pruebas pasan",
                      "CONFIRMADO COMO CORREGIDO" if confirmado else "NO CONFIRMADO (sigue abierto)"])
    # Regresion: el resto de la suite no debe empeorar (SEC-040 es una sospecha, no un defecto)
    resto = {n: v for n, v in reg.res.items() if "SEC040" not in n}
    fallan = [n for n, v in resto.items() if not v]
    filas.append(["REGRESION", "-", "Toda la suite", "-", "-", f"{len(resto) - len(fallan)}/{len(resto)} pruebas pasan",
                  "SIN REGRESIONES" if not fallan else f"{len(fallan)} pruebas fallan"])
    print("\n" + "=" * 118 + "\nRESULTADO DE LAS PRUEBAS DE CONFIRMACION\n" + "=" * 118)
    print(f"{'CON':<10}{'Defecto':<8}{'Casos originales':<24}{'Original':<9}{'Actual':<22}Decision")
    for f in filas:
        print(f"{f[0]:<10}{f[1]:<8}{f[2]:<24}{f[4]:<9}{f[5]:<22}{f[6]}")
    with open("confirmacion_resultado.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["CON", "Defecto", "Casos originales", "Resultado original", "Estado original", "Resultado actual", "Decision"])
        w.writerows(filas)


if __name__ == "__main__":
    main()
