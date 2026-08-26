"""Adapta los cuadernos para que importen el paquete `asis`.

Los cuadernos traían la infraestructura duplicada y ya divergida: la misma
`zonal_stats` en dos versiones, con identificadores en inglés en la corta y en
español en la larga. Este script reemplaza ese andamiaje por un import y ajusta
los sitios de llamada a la API del paquete.

Se conserva la convención de la versión corta —identificadores en inglés, texto
de figuras en español— porque es la que los propios cuadernos declaran.

Uso:
    python scripts/convertir_cuadernos.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = ROOT / "notebooks"

# --- La celda que reemplaza al andamiaje --------------------------------------
IMPORT_CELL = '''# CELDA 1 · Infraestructura: se importa del paquete
#
# El cálculo vive una sola vez, en `asis/`. Este cuaderno lo importa, de modo
# que una corrección en la estadística zonal se hace en un solo lugar y no en
# dos.
import sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "asis").exists() else Path.cwd().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from asis import client, panel
from asis.config import (ASI_THRESHOLDS, CACHE, CLASSES, FLAGS, GRID_STEP,
                         HND_BBOX, NODATA, PALETTE, PIX_DEG, PIX_KM2, SEASONS,
                         SEASON_WINDOW, SERIES, SOURCE_NOTE, SOURCE_URL,
                         START_YEAR,
                         VALID_RANGE, WKID, in_season)
from asis.calendar import (MONTH_ES, dekad_between, dekad_code, dekad_date,
                           dekad_label, dekad_of_year, dekad_range,
                           dekad_window)
from asis.client import (SNAP, catalog_parsed, clip_period, export_tif,
                         export_tifs, last_dekad, load_csv, raster_name)
from asis.zonal import (SHAPE, TRANSFORM, export_geometry, grid,
                        municipal_series, read_tif, zonal_stats)
from asis.aggregate import (classify, climatology, department_weights,
                            national_from_csv, severity_area, to_country,
                            to_department, worst_case)
from asis.viz import (SCALE_ASI, SCALE_VCI, class_map, climatology_fig,
                      climatology_matrix, continuous_map, dashboard_fig,
                      heatmap_panel, rainfall_fig, ranking_fig, raster_detail,
                      series_fig, severity_area_fig, style_fig)

pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 170)

# La malla de zonas se arma una vez y la reutilizan todos los dekads: es lo que
# hace viable recorrer veinte años de rásteres.
G = grid()
MUNI, DEPT, NZ, ZONES = G.muni, G.dept, G.nz, G.zones

# Geometría simplificada para las coropletas (~400 m: mantiene la forma y pesa
# unas diez veces menos que la original).
GEOJSON, MUNI_REF = export_geometry()

print("infraestructura lista ·", pd.Timestamp.today().date(),
      "· periodo desde", START_YEAR, "·", NZ, "municipios ·",
      len(DEPT), "departamentos")
print("último dekad publicado · ASI_D GS1 LC-C:",
      last_dekad("ASI_D", season="GS1", landcover="C"),
      "· VCI_D:", last_dekad("VCI_D"))
'''

INFRA_MARKDOWN = '''---

# 0. Infraestructura

Una celda: se importa el paquete `asis`, que trae el cliente de los servicios de
FAO, las geometrías GAUL con la estadística zonal y la capa de visualización. El
cálculo vive una sola vez ahí y no duplicado en cada cuaderno: una corrección en
la estadística zonal se hace en un solo lugar.

El periodo histórico arranca en 2005 y está gobernado por `START_YEAR`: la serie
de lluvia de GIEWS tiene un quiebre de homogeneidad alrededor de ese año, así que
encadenarla con los años previos introduce un salto que no es climático.

Para instalar las dependencias: `pip install -r requirements-build.txt`.
'''

# --- Sitios de llamada que cambian de firma ----------------------------------
CALL_REWRITES: list[tuple[str, str]] = []

# Figuras de mapa que ahora reciben la geometría como segundo argumento:
# dibujar un mapa ya no obliga a tener geopandas cargado en el proceso.
MAP_FIGURES = ("class_map", "continuous_map")

# Cómo se identifica cada serie a partir del servicio y el sufijo del ráster.
SERIES_BY_CALL = {("ASI_D", "SUF_GS1"): "asi_gs1",
                  ("ASI_D", "SUF_GS2"): "asi_gs2",
                  ("VCI_D", None): "vci"}


def _split_args(text: str) -> list[str]:
    """Separa argumentos respetando paréntesis, corchetes y comillas.

    Hace falta porque el segundo argumento suele ser otra llamada con comas
    dentro, como `dekad_range(2020, 9, 1, 2021, 1, 3)`, y una expresión regular
    ingenua la corta por la mitad.
    """
    args, depth, buf, quote = [], 0, [], None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        args.append("".join(buf).strip())
    return args


def _find_calls(src: str, name: str):
    """Localiza cada llamada a `name` y devuelve (inicio, fin, argumentos)."""
    token, i = name + "(", 0
    while True:
        j = src.find(token, i)
        if j < 0:
            return
        k, depth = j + len(token), 1
        while k < len(src) and depth:
            if src[k] in "([{":
                depth += 1
            elif src[k] in ")]}":
                depth -= 1
            k += 1
        yield j, k, _split_args(src[j + len(token):k - 1])
        i = k


def insert_geojson(src: str) -> str:
    """Agrega GEOJSON como segundo argumento de las figuras de mapa.

    Se hace con un recorrido que respeta paréntesis, no con una expresión
    regular: el primer argumento suele ser una expresión con comas, como
    `delta.dropna(subset=["saldo"])`.
    """
    for name in MAP_FIGURES:
        pieces, last = [], 0
        for start, end, args in list(_find_calls(src, name)):
            if len(args) < 2 or args[1] == "GEOJSON":
                continue                      # ya convertida
            pieces.append(src[last:start])
            pieces.append(f"{name}({args[0]}, GEOJSON, "
                          + ", ".join(args[1:]) + ")")
            last = end
        if pieces:
            pieces.append(src[last:])
            src = "".join(pieces)
    return src


def rewrite_municipal_series(src: str, name="municipal_series") -> str:
    """`municipal_series("ASI_D", dekads, SUF_GS1, thresholds_gt=...)` pasa a
    recibir la serie declarada en config: los umbrales y la máscara de uso de
    suelo viajan con la serie, que es donde pertenecen."""
    out, i = [], 0
    token = name + "("
    while True:
        j = src.find(token, i)
        if j < 0:
            out.append(src[i:])
            break
        out.append(src[i:j])
        # Localizar el paréntesis de cierre que corresponde.
        k, depth = j + len(token), 1
        while k < len(src) and depth:
            if src[k] in "([{":
                depth += 1
            elif src[k] in ")]}":
                depth -= 1
            k += 1
        inner = src[j + len(token):k - 1]
        args = _split_args(inner)
        svc = args[0].strip().strip("\"'") if args else ""
        suffix = None
        for a in args[1:]:
            if a in ("SUF_GS1", "SUF_GS2"):
                suffix = a
        sid = SERIES_BY_CALL.get((svc, suffix))
        if sid and len(args) >= 2:
            out.append(f'{name}(SERIES["{sid}"], {args[1]})')
        else:
            out.append(src[j:k])              # no se reconoce: se deja igual
        i = k
    return "".join(out)

# Nombres que la versión larga tenía en español y el paquete tiene en inglés.
# Se aplican como palabra completa para no tocar texto de figuras.
SPANISH_TO_ENGLISH = {
    "ANIO_INICIO": "START_YEAR",
    "ASI_UMBRALES": "ASI_THRESHOLDS",
    "ESCALA_ASI": "SCALE_ASI",
    "ESCALA_VCI": "SCALE_VCI",
    "FUENTE": "SOURCE_NOTE",
    "PAIS_GAUL": "GAUL_COUNTRY",
    "DEPTO": "DEPT",
    "a_departamento": "to_department",
    "a_pais": "to_country",
    "clasificar": "classify",
    "dekad_back": "dekad_window",
    "dekad_idx": "dekad_index",
    "dekad_to_date": "dekad_date",
    "fig_estilo": "style_fig",
    "geojson_muni": "muni_geojson",
    "idx_dekad": "dekad_from_index",
    "leer_tif": "read_tif",
    "mapa_clases": "class_map",
    "mapa_continuo": "continuous_map",
    "area_severidad": "severity_area_fig",
    "raster_detalle": "raster_detail",
    "nombre_raster": "raster_name",
    "recortar_periodo": "clip_period",
    "serie_municipal": "municipal_series",
    "ultima_dekada": "last_dekad",
    "construir_zonas": "build_zones",
    "_registrar_ids": "_register_ids",
    "_ckey": "_cache_key",
    "MESES_ES": "MONTH_ES",
    "TEMPORADAS": "SEASONS",
}
# Argumentos por nombre y columnas.
KEYWORD_REWRITES = {
    "umbrales_gt": "thresholds_gt",
    "umbrales_lt": "thresholds_lt",
    "dekadas": "dekads",
    "dekada_ref": "ref_dekad",
    "etiqueta_barra": "bar_label",
    "etiqueta": "label",
    "familia": "family",
    "titulo": "title",
    "subtitulo": "subtitle",
    "valor": "value_col",
    "animacion": "animation",
    "escala": "scale",
    "rango": "value_range",
    "leyenda": "legend",
    "y_fuente": "y_source",
    "fuente": "source",
    "sufijo": "suffix",
    "peso": "weight_col",
    "anio_min": "min_year",
    "lc": "landcover",
    "temporada": "season",
}
# La columna del dekad se llamaba distinto en la versión larga.
COLUMN_REWRITES = {'"dekada"': '"dekad_id"', "'dekada'": "'dekad_id'",
                   '"temporada"': '"season"', "'temporada'": "'season'",
                   '"fecha"': '"date"', "'fecha'": "'date'",
                   '"municipios"': '"n_muni"', "'municipios'": "'n_muni'"}


# Celdas completas que se sustituyen: definían funciones que ahora viven en
# `asis/aggregate.py`. Se reconocen por su encabezado.
NATIONAL_CELL = '''# Series nacionales oficiales de GIEWS, ponderadas por área de cultivo
REF_DEKAD, CASE_YEAR = "2019-09-D2", 2019

# El peso de cada departamento es su área de cultivo en píxeles válidos del
# ráster. Ponderar por número de departamentos le daría a Islas de la Bahía el
# mismo peso que a Olancho.
DEPT_WEIGHT = department_weights(municipal_series(SERIES["asi_gs1"],
                                                 [REF_DEKAD]))

# Serie nacional a partir del CSV departamental de GIEWS: es el dato de FAO, no
# un agregado propio, y es la referencia contra la cual se valida el panel.
_asi_csv = load_csv("asi_dekad_s1")
_asi_csv = _asi_csv[_asi_csv["Land_Type"].astype(str)
                    .str.contains("Crop", case=False, na=False)]
asi_history = national_from_csv(clip_period(_asi_csv), DEPT_WEIGHT)

print(f"serie nacional ASI · {len(asi_history):,} dekads · "
      f"{int(asi_history['Year'].min())}-{int(asi_history['Year'].max())}")
'''

# El bloque de la lluvia dentro de la celda de la figura 2.1.
RAINFALL_BLOCK = '''# Lluvia dekadal nacional y su promedio de largo plazo (LTA), ponderando
# departamentos por área de cultivo. La LTA es la que publica FAO y NO se
# recalcula: es la referencia oficial contra la que compara GIEWS.
rainfall = national_from_csv(clip_period(load_csv("rain_dekad")), DEPT_WEIGHT,
                             lta_col="Data_long_term_Average")
rainfall = rainfall.rename(columns={"value": "obs"})
'''


# La versión larga arma las series nacionales a mano y con sus propios nombres
# de columna (`valor`, `dek_anio`). Se sustituye el cálculo por el del paquete y
# se renombran las columnas de vuelta, para no tener que tocar las veinte celdas
# que las consumen más abajo.
LONG_BLOCKS: list[tuple[str, str]] = [
    (r"_ref = zonal_stats\(.*?asi_hist = nacional_csv\(\"asi_dekad_s1\"\)\n",
     '''# El peso de cada departamento es su área de cultivo en píxeles válidos del
# ráster, no el número de departamentos.
PESO_DEP = department_weights(municipal_series(SERIES["asi_gs1"], [PEAK19]))

# Serie nacional oficial de GIEWS: es el dato de FAO, no un agregado propio.
_asi_csv = load_csv("asi_dekad_s1")
_asi_csv = _asi_csv[_asi_csv["Land_Type"].astype(str)
                    .str.contains("Crop", case=False, na=False)]
asi_hist = national_from_csv(clip_period(_asi_csv), PESO_DEP).rename(
    columns={"value": "valor", "dekad_of_year": "dek_anio"})
'''),
    (r"def nacional_lluvia\(\):.*?lluvia = nacional_lluvia\(\)\n",
     '''# Lluvia dekadal nacional y su promedio de largo plazo, ponderando
# departamentos por área de cultivo. La LTA es la que publica FAO y NO se
# recalcula: es la referencia oficial contra la que compara GIEWS.
lluvia = national_from_csv(clip_period(load_csv("rain_dekad")), PESO_DEP,
                           lta_col="Data_long_term_Average").rename(
    columns={"value": "obs"})
'''),
]


def strip_outputs(nb: dict) -> dict:
    """Los cuadernos se distribuyen sin salidas guardadas, como ellos mismos
    declaran: las figuras son interactivas y no se ven en un visor estático, y
    guardarlas hacía que un cuaderno pesara varios megabytes."""
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        cell.pop("id", None)
    nb.get("metadata", {}).pop("widgets", None)
    return nb


def rewrite_code(src: str, spanish: bool) -> str:
    # Los nombres en español se traducen PRIMERO: el resto de las reglas busca
    # los nombres del paquete, así que si se aplicaran antes no encontrarían
    # nada en la versión larga.
    if spanish:
        for a, b in SPANISH_TO_ENGLISH.items():
            src = re.sub(rf"\b{re.escape(a)}\b", b, src)
        for a, b in KEYWORD_REWRITES.items():
            src = re.sub(rf"\b{re.escape(a)}=", f"{b}=", src)
        for a, b in COLUMN_REWRITES.items():
            src = src.replace(a, b)
    if spanish:
        for pattern, repl in LONG_BLOCKS:
            src = re.sub(pattern, repl, src, flags=re.DOTALL)
    src = rewrite_municipal_series(src)
    src = insert_geojson(src)
    for pattern, repl in CALL_REWRITES:
        src = re.sub(pattern, repl, src)
    # La lluvia nacional se arma con national_from_csv en vez de repetir la
    # ponderación a mano dentro del cuaderno.
    src = re.sub(r"def (country_rainfall|national_rainfall)\(\):.*?"
                 r"rainfall = \1\(\)\n", RAINFALL_BLOCK, src, flags=re.DOTALL)
    return src


def convert(path: Path, spanish: bool) -> dict:
    nb = json.loads(path.read_text(encoding="utf-8"))
    out_cells = []
    replaced_infra = False
    for cell in nb["cells"]:
        src = "".join(cell["source"])
        if cell["cell_type"] == "code":
            # Las cuatro celdas de andamiaje se sustituyen por una sola.
            if re.match(r"#\s*CELDA\s*1\s*[·.]", src):
                cell["source"] = IMPORT_CELL.splitlines(keepends=True)
                out_cells.append(cell)
                replaced_infra = True
                continue
            if re.match(r"#\s*CELDA\s*[234]\s*[·.]", src):
                continue                      # queda dentro del paquete
            if re.match(r"#\s*CELDA\s*5\s*[·.]", src):
                cell["source"] = NATIONAL_CELL.splitlines(keepends=True)
                out_cells.append(cell)
                continue
            cell["source"] = rewrite_code(src, spanish).splitlines(keepends=True)
        else:
            if src.lstrip().startswith("---") and "# 0. Infraestructura" in src:
                cell["source"] = INFRA_MARKDOWN.splitlines(keepends=True)
            elif re.match(r"##\s*[234]\.", src.lstrip()) and \
                    ("Cliente ASIS" in src or "estadística zonal" in src
                     or "Capa de visualización" in src
                     or "capa de visualizacion" in src.lower()):
                continue                      # describía celdas que ya no están
        out_cells.append(cell)
    nb["cells"] = out_cells
    if not replaced_infra:
        print(f"   ! {path.name}: no se encontró la celda de andamiaje")
    return strip_outputs(nb)


def main() -> int:
    targets = [("ASIS_GIEWS_corta.ipynb", False),
               ("ASIS_GIEWS_larga.ipynb", True)]
    for name, spanish in targets:
        p = NOTEBOOKS / name
        if not p.exists():
            print(f"   - {name}: no está")
            continue
        before = p.stat().st_size
        nb = convert(p, spanish)
        p.write_text(json.dumps(nb, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        n_code = sum(1 for c in nb["cells"] if c["cell_type"] == "code")
        print(f"   {name}: {before // 1024} KB -> "
              f"{p.stat().st_size // 1024} KB · {len(nb['cells'])} celdas "
              f"({n_code} de código)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
