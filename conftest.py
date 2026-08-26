"""Hace importable el paquete `asis` desde las pruebas.

Existe por una diferencia sutil: `python -m pytest` agrega el directorio actual
a `sys.path` y `pytest` a secas no. Sin este archivo las pruebas pasaban en la
laptop y fallaban en CI con `ModuleNotFoundError: No module named 'asis'`.

Con un conftest.py en la raíz, pytest agrega esta carpeta al path sea cual sea
la forma de invocarlo, y el proyecto no necesita instalarse para probarlo.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
