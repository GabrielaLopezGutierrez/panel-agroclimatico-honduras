"""Calendario dekadal.

ASIS publica por dekads, no por mes: D1 son los días 1 a 10, D2 los días 11 a 20
y D3 del 21 al fin de mes. Un dekad se identifica con el código `YYYY-MM-Dn`, que
es la clave temporal de todo el panel.
"""
from __future__ import annotations

import pandas as pd

MONTH_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
            7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def dekad_code(y: int, m: int, d: int) -> str:
    return f"{y:04d}-{m:02d}-D{d}"


def dekad_index(code: str) -> int:
    """Entero monótono: permite aritmética de ventanas sin manejar meses."""
    y, m, d = int(code[:4]), int(code[5:7]), int(code[-1])
    return y * 36 + (m - 1) * 3 + (d - 1)


def dekad_from_index(i: int) -> str:
    y, rest = divmod(i, 36)
    return dekad_code(y, rest // 3 + 1, rest % 3 + 1)


def dekad_range(y0, m0, d0, y1, m1, d1) -> list[str]:
    a = dekad_index(dekad_code(y0, m0, d0))
    b = dekad_index(dekad_code(y1, m1, d1))
    return [dekad_from_index(i) for i in range(a, b + 1)]


def dekad_between(start: str, end: str) -> list[str]:
    """Todos los dekads de start a end, inclusive, por código."""
    return [dekad_from_index(i)
            for i in range(dekad_index(start), dekad_index(end) + 1)]


def dekad_window(code: str, n: int) -> list[str]:
    """Los n dekads que terminan en code, inclusive (ventanas móviles)."""
    end = dekad_index(code)
    return [dekad_from_index(i) for i in range(end - n + 1, end + 1)]


def dekad_date(code: str) -> pd.Timestamp:
    """Fecha de inicio del dekad: día 1, 11 o 21."""
    y, m, d = int(code[:4]), int(code[5:7]), int(code[-1])
    return pd.Timestamp(year=y, month=m, day=(1, 11, 21)[d - 1])


def dekad_of_date(ts) -> str:
    """Dekad que contiene una fecha. Lo usa el selector de fechas de la app,
    que trabaja en días porque es lo que entiende un analista."""
    ts = pd.Timestamp(ts)
    d = 1 if ts.day <= 10 else (2 if ts.day <= 20 else 3)
    return dekad_code(ts.year, ts.month, d)


def dekad_of_year(code: str) -> int:
    """Posición del dekad dentro del año, de 1 a 36. Es el eje con el que se
    compara un año contra su propia climatología."""
    m, d = int(code[5:7]), int(code[-1])
    return (m - 1) * 3 + d


def dekad_label(code: str) -> str:
    y, m, d = int(code[:4]), int(code[5:7]), int(code[-1])
    return f"{d}a dek {MONTH_ES[m]} {y}"


MONTH_ES_FULL = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
                 6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
                 10: "octubre", 11: "noviembre", 12: "diciembre"}
ORDINAL_ES = {1: "1er", 2: "2do", 3: "3er"}


def dekad_label_long(code: str) -> str:
    """Forma larga, para el encabezado: "3er dekadal agosto 2026".

    La corta (`dekad_label`) sigue en ejes, leyendas y cifras, donde el nombre
    completo del mes no cabe sin apretar el resto.
    """
    y, m, d = int(code[:4]), int(code[5:7]), int(code[-1])
    return f"{ORDINAL_ES[d]} dekadal {MONTH_ES_FULL[m]} {y}"


def dekad_year(code: str) -> int:
    return int(code[:4])
