# Instalacion y puesta en marcha del SGA (borrador generado por portabilidad.py)

Verificado en: Windows-11-10.0.26200-SP0, Python 3.14.4.

## Requisitos
- Python 3.14.4 (version con la que se verifico) y pip.
- Windows (PowerShell) o Linux/Mac. No se necesita instalar una base de datos: usa SQLite.

## Pasos
1. Copiar la carpeta del proyecto (sin la carpeta `.venv`: un entorno virtual NO se puede copiar a otra ruta, `pip.exe` guarda la ruta original).
2. Abrir una terminal en la raiz del proyecto y crear el entorno virtual: `python -m venv .venv`
3. Activarlo: `.venv\Scripts\Activate.ps1` (Windows) o `source .venv/bin/activate` (Linux/Mac)
4. Instalar dependencias: `python -m pip install -r requirements.txt`
5. Iniciar el servidor: `python -m waitress --port=5000 run:app`
6. Abrir `http://127.0.0.1:5000/` en el navegador (no usar 0.0.0.0).

## Notas
- La base de datos se crea sola en `instance/sga.db` la primera vez que se inicia la aplicacion.
- El puerto se cambia con `--port`.
