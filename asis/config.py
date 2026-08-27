"""Configuración del panel agroclimático: endpoints, malla, semántica de los
indicadores y registro de series.

Todo lo que se cambia una vez al año y no por corrida vive aquí. Cambiar
START_YEAR, ISO3 o HND_BBOX y volver a construir es suficiente para mover el
periodo o el país; no hay años escritos a mano en el resto del paquete.

Este módulo no importa nada pesado a propósito: lo cargan tanto la app (que solo
lee parquet) como el constructor (que necesita rasterio y geopandas).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Rutas -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("ASIS_DATA", ROOT / "data"))
PANEL_DIR = DATA / "municipal"          # versionado: panel municipio x dekad
OFICIAL_DIR = DATA / "oficial"          # versionado: instantánea de los CSV de FAO
GEO_DIR = DATA / "geo"                  # versionado: geometría simplificada
# La cache de rásteres no se versiona: son varios GB y se reconstruyen solos.
CACHE = Path(os.environ.get("ASIS_CACHE", ROOT / "asis_cache"))

# --- Endpoints ---------------------------------------------------------------
IMG_SERVER = "https://asis-esri.fao.org/image/rest/services/{svc}/ImageServer"
WFS_GAUL = "https://data.apps.fao.org/map/gsrv/gsrv1/gaul/wfs"
CSV_DIR = "https://www.fao.org/giews/earthobservation/asis/data/country/{iso3}/"

ISO3, GAUL_COUNTRY = "HND", "Honduras"

# --- Ventana temporal --------------------------------------------------------
# START_YEAR gobierna toda la lectura histórica: climatología, líneas base,
# percentiles y series de lluvia. 2005 no es arbitrario: la serie de lluvia de
# GIEWS tiene un quiebre de homogeneidad alrededor de ese año, de modo que
# mezclarla con lo anterior introduce un salto que no es climático.
START_YEAR = 2005

# --- Malla nativa ASIS -------------------------------------------------------
WKID = 4326
PIX_DEG = 0.00892857143            # 1/112 de grado, malla nativa ASIS (~1 km)
PIX_KM2 = 0.988                    # área media del píxel a la latitud de Honduras
HND_BBOX = (-89.40, 12.90, -83.10, 16.60)
GRID_X0, GRID_Y0, GRID_STEP = -180.004464, 75.0044643, PIX_DEG
NODATA = -9999.0

# --- Semántica de los indicadores -------------------------------------------
# Fuera del rango válido los rásteres traen banderas, NO valores del índice.
# Contarlas como dato es el error más común al hacer estadística zonal.
VALID_RANGE = {"ASI_D": (0, 100), "ASI_A": (0, 100), "DI_D": (0, 100),
               "DI_A": (0, 100), "VHI_D": (0, 1), "VHI_M": (0, 1),
               "VCI_D": (0, 1), "VCI_M": (0, 1), "MVHI_D": (0, 1),
               "MVHI_A": (0, 1)}
# FLAGS no se usa en el cálculo (el enmascarado ocurre en el servidor vía
# renderingRule); queda como referencia de qué significa cada valor fuera de
# rango, y es lo que la app cita cuando un municipio sale en blanco.
FLAGS = {251: "fuera de temporada", 252: "sin dato", 253: "sin estacionalidad",
         254: "sin cultivo/pasto", 255: "nodata"}

# Umbrales de alerta del ASI que se muestran en la app: verde/amarillo/naranja/
# rojo. Son distintos de ASI_THRESHOLDS (30, 40, 55, 70), que son los que ya
# vienen calculados en el panel de datos (columnas pct_gt30/40/55/70) y no se
# tocan aquí; estos cuatro son solo para la clasificación visual, la leyenda y
# el texto de alerta que ve la persona que usa la app.
ASI_ALERT_THRESHOLDS = (10, 25, 40)
ASI_ALERT_DESCRIPTIONS = {
    "<10": "Sin estrés hídrico",
    "10-25": "Estrés leve/moderado",
    "25-40": "Estrés severo",
    ">=40": "Estrés extremo",
}

# Clases y paleta que se usan en todas las figuras. El ASI usa la clasificación
# de alerta de arriba (4 clases); el VCI conserva las 9 clases oficiales de FAO,
# que no cambian con esto.
CLASSES = {
    "ASI": ([0, 10, 25, 40, 100.01],
            ["<10", "10-25", "25-40", ">=40"],
            ["#2fcd00", "#ffd400", "#ff8c00", "#d7263d"]),
    "VCI": ([0, .15, .25, .35, .45, .55, .65, .75, .85, 1.0001],
            ["<0.15", "0.15-0.25", "0.25-0.35", "0.35-0.45", "0.45-0.55",
             "0.55-0.65", "0.65-0.75", "0.75-0.85", ">=0.85"],
            ["#9a0000", "#ff0000", "#ff8900", "#ffcd66", "#ffff00",
             "#66ff00", "#2fcd00", "#009a00", "#217400"]),
}
PALETTE = {fam: dict(zip(v[1], v[2])) for fam, v in CLASSES.items()}

# Umbrales de severidad del ASI que usa GIEWS para alertas.
ASI_THRESHOLDS = (30, 40, 55, 70)
# Umbral FAO por debajo del cual el VCI indica vegetación en mal estado.
VCI_THRESHOLDS = (0.35, 0.25)

SEASONS = {"GS1": "Primera (siembra may-jun, cosecha ago-sep)",
           "GS2": "Postrera (siembra sep, cosecha dic-ene)"}

# Ventana de cultivo de cada temporada, en dekads del año (1 a 36).
#
# Hace falta declararla porque no se puede deducir del dato: el ráster del ASI
# trae valores los 36 dekads del año, pero fuera de la ventana el índice está
# congelado en el valor con que cerró la temporada. Graficarlo ahí sugeriría una
# persistencia del estrés que el índice no afirma, y leerlo como la situación
# actual es el error que la app tiene que impedir.
#
# GS2 envuelve el fin de año: la postrera se siembra en septiembre y se cosecha
# entre diciembre y enero.
SEASON_WINDOW = {"GS1": (13, 30),      # may D1 a oct D3
                 "GS2": (25, 3)}       # sep D1 a ene D3


def in_season(season: str | None, dekad_of_year: int) -> bool:
    """Si el dekad cae dentro de la ventana de cultivo de la temporada.

    Sin temporada (el VCI) siempre es válido: cubre todo el año.
    """
    if not season or season not in SEASON_WINDOW:
        return True
    start, end = SEASON_WINDOW[season]
    if start <= end:
        return start <= dekad_of_year <= end
    return dekad_of_year >= start or dekad_of_year <= end


@dataclass(frozen=True)
class Series:
    """Una serie del panel: de qué servicio sale, cómo se llama su ráster y con
    qué umbrales se resume. El id es también el nombre de la carpeta en
    data/municipal/, de modo que agregar una serie no toca el constructor."""
    id: str
    svc: str
    label: str
    family: str                      # ASI o VCI: gobierna clases y paleta
    unit: str
    unit_short: str = ""
    suffix: str = ""                 # sufijo del nombre del ráster
    season: str | None = None        # GS1, GS2 o None si no es estacional
    seasonal: bool = False           # si solo existe dentro de la ventana de cultivo
    thresholds_gt: tuple = ()
    thresholds_lt: tuple = ()
    note: str = ""

    @property
    def valid_range(self) -> tuple:
        return VALID_RANGE[self.svc]


SERIES: dict[str, Series] = {
    "asi_gs1": Series(
        id="asi_gs1", svc="ASI_D", suffix=".GS1.LC-C", season="GS1",
        family="ASI", seasonal=True, thresholds_gt=ASI_THRESHOLDS,
        label="ASI · temporada primera",
        unit="% del área de cultivo bajo estrés hídrico", unit_short="ASI %",
        note="Índice de estrés agrícola acumulado dentro de la ventana de "
             "cultivo de la primera. Fuera de temporada no existe."),
    "asi_gs2": Series(
        id="asi_gs2", svc="ASI_D", suffix=".GS2.LC-C", season="GS2",
        family="ASI", seasonal=True, thresholds_gt=ASI_THRESHOLDS,
        label="ASI · temporada postrera",
        unit="% del área de cultivo bajo estrés hídrico", unit_short="ASI %",
        note="Mismo índice sobre la ventana de cultivo de la postrera."),
    "vci": Series(
        id="vci", svc="VCI_D", family="VCI", seasonal=False,
        thresholds_lt=VCI_THRESHOLDS,
        label="VCI · condición de la vegetación",
        unit="índice 0-1", unit_short="VCI",
        note="Condición de la vegetación frente a su historia reciente. Cubre "
             "todo el territorio y todo el año, también fuera del área de "
             "cultivo."),
}

# Serie derivada que combina las dos temporadas del ASI. No se guarda en disco:
# se arma al vuelo tomando, para cada municipio y dekad, el mayor de los dos
# valores. Criterio conservador para alerta temprana. Ver aggregate.worst_case().
#
# El id no cambia porque es el nombre de una carpeta y de una columna; la
# etiqueta sí, porque "peor caso" no le dice a nadie qué está viendo.
ASI_COMBINED = "asi_peor_caso"
ASI_COMBINED_LABEL = "ASI · el más alto de las dos temporadas"

# --- Construcción ------------------------------------------------------------
# FAO republica dekads. El constructor falla ruidosamente si un dekad ya
# guardado vuelve con valores distintos por encima de esta tolerancia, en vez de
# sobrescribirlo en silencio. Se revisa a mano.
#
# La tolerancia es una fracción del rango del indicador, no un número absoluto:
# el ASI va de 0 a 100 y el VCI de 0 a 1, así que medio punto es ruido de
# redondeo en el primero y media escala en el segundo. Con 0,005 la tolerancia
# queda en 0,5 pp para el ASI y en 0,005 para el VCI.
TOLERANCE_FRAC = 0.005


def tolerance_for(series: "Series") -> float:
    lo, hi = series.valid_range
    return TOLERANCE_FRAC * (hi - lo)
WORKERS = 6                          # descargas simultaneas de ráster
GEOJSON_TOL = 0.004                  # ~400 m: mantiene la forma, pesa 10x menos

# Portal oficial de FAO GIEWS para Honduras. Toda cita de la fuente en la app,
# en los cuadernos y en el README apunta aquí: quien lee una cifra tiene que
# poder llegar al dato original sin buscarlo.
SOURCE_URL = ("https://www.fao.org/giews/earthobservation/country/index.jsp"
              "?code=HND&type=11#")
SOURCE_NAME = "FAO GIEWS ASIS"

# La nota al pie de cada figura. El enlace va en HTML porque es lo que entiende
# la anotación de Plotly, y el ampersand se escribe escapado para que el atributo
# quede bien formado.
SOURCE_NOTE = (
    f'Fuente: <a href="{SOURCE_URL.replace("&", "&amp;")}" target="_blank">'
    f'{SOURCE_NAME}</a> · rásteres ~1 km agregados a municipio (GAUL 2015) · '
    'elaboración propia')
