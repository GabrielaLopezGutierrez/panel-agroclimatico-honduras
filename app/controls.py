"""Controles de la app y acceso al panel con caché.

Tres controles y nada más: nivel, indicador y ventana. `START_YEAR`, el país y
el bbox viven en `asis/config.py` porque se cambian una vez al año, no por
corrida.

El nivel no es solo un filtro: decide qué vistas tienen sentido y con qué
geometría se dibuja el mapa. Esa decisión vive en `panel.LEVEL_GEO` y aquí se
consulta, para que la app no la repita en cada vista.

El panel se cachea por proceso, que es lo correcto: no contiene información de
ningún usuario. El estado de la consulta vive en `st.session_state`, porque ese
sí es de cada quien.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from asis import config as cfg, panel
from asis.calendar import (dekad_index, dekad_label, dekad_of_year,
                           dekad_window)

LEVELS = {"municipio": "Municipio", "departamento": "Departamento",
          "pais": "País"}

DEFAULT_RANGE = 54      # 18 meses: la ventana con la que se trabaja a diario
# Un mapa animado con un cuadro por dekad deja de ser legible mucho antes de
# volverse pesado. Pasado este limite el mapa muestra el extremo de la ventana
# en vez de la secuencia.
MAX_FRAMES = 24

SERIES_HELP = {
    cfg.ASI_COMBINED:
        "Para cada municipio y cada dekad toma el **mayor** de los dos valores "
        "del ASI, el de la primera y el de la postrera. No promedia ni mezcla: "
        "es uno de los dos valores reales, y la app dice de cuál temporada "
        "viene. Las dos temporadas se solapan en septiembre y octubre, y fuera "
        "de su ventana el índice queda congelado; tomar el más alto evita "
        "reportar calma cuando una de las dos sí tiene estrés.",
    "asi_gs1": "Solo la temporada primera, se siembra entre mayo y junio y se "
               "cosecha entre agosto y septiembre. Fuera de esa ventana el "
               "valor está congelado.",
    "asi_gs2": "Solo la temporada postrera, se siembra en septiembre y se "
               "cosecha entre diciembre y enero.",
    "vci": "Condición de la vegetación frente a su propia historia reciente. "
           "Cubre todo el territorio y todo el año, también fuera del área de "
           "cultivo. El umbral de alerta de FAO es 0,35.",
}


@dataclass
class Query:
    level: str
    series_id: str
    start: str
    end: str
    departments: list[str]

    @property
    def single(self) -> bool:
        return self.start == self.end

    @property
    def family(self) -> str:
        return panel.family_of(self.series_id)

    @property
    def label(self) -> str:
        return panel.label_of(self.series_id)

    @property
    def unit(self) -> str:
        return panel.unit_of(self.series_id)

    @property
    def mapped(self) -> bool:
        """Si el nivel se dibuja en un mapa. El país es un solo valor: un mapa
        de una sola clase no dice nada que el número no diga mejor."""
        return self.level in panel.LEVEL_GEO

    @property
    def code_col(self) -> str:
        return panel.LEVEL_GEO.get(self.level, {}).get("code", "adm2_code")

    @property
    def name_col(self) -> str:
        return panel.LEVEL_GEO.get(self.level, {}).get("name", "adm2_name")

    @property
    def unit_name(self) -> str:
        return LEVELS[self.level].lower()

    @property
    def window_label(self) -> str:
        if self.single:
            return dekad_label(self.start)
        return f"{dekad_label(self.start)} a {dekad_label(self.end)}"

    def slug(self) -> str:
        base = f"{self.series_id}_{self.level}_{self.start}"
        return base if self.single else f"{base}_{self.end}"


# --- Acceso cacheado ---------------------------------------------------------
# Todo lo cacheado se indexa por la versión del panel: la actualización
# automática commitea datos nuevos mientras el proceso sigue vivo, y un panel
# nuevo debe invalidar las entradas viejas en vez de servir cifras de la semana
# pasada.
def data_version() -> str:
    try:
        return str(panel.MANIFEST.stat().st_mtime_ns)
    except OSError:
        return "0"


@st.cache_data(show_spinner=False)
def _manifest(version: str) -> dict:
    return panel.manifest()


@st.cache_data(show_spinner=False)
def _geojson(version: str, level: str) -> dict:
    return panel.geojson(level)


@st.cache_data(show_spinner=False)
def _dekads(version: str, series_id: str) -> list[str]:
    return panel.dekads(series_id)


@st.cache_data(show_spinner="Leyendo el panel...")
def _load(version: str, series_id: str, start: str, end: str) -> pd.DataFrame:
    return panel.load(series_id, start, end)


@st.cache_data(show_spinner=False)
def _national(version: str, name: str) -> pd.DataFrame:
    return panel.national(name)


@st.cache_data(show_spinner=False)
def _series_options(version: str) -> dict[str, str]:
    return panel.available_series()


@st.cache_data(show_spinner=False)
def _municipios(version: str) -> pd.DataFrame:
    return panel.municipios()


def manifest() -> dict:
    return _manifest(data_version())


def geojson(level: str = "municipio") -> dict:
    return _geojson(data_version(), level)


def dekads(series_id: str) -> list[str]:
    return _dekads(data_version(), series_id)


def load(series_id: str, start: str, end: str) -> pd.DataFrame:
    return _load(data_version(), series_id, start, end)


def national(name: str) -> pd.DataFrame:
    return _national(data_version(), name)


def series_options() -> dict[str, str]:
    return _series_options(data_version())


def municipios() -> pd.DataFrame:
    return _municipios(data_version())


def _clamp(code: str, available: list[str]) -> str:
    """Lleva un código al dekad disponible más cercano hacia atrás."""
    if code in available:
        return code
    earlier = [d for d in available if dekad_index(d) <= dekad_index(code)]
    return earlier[-1] if earlier else available[0]


# --- Panel de control --------------------------------------------------------
def sidebar(options: dict[str, str]) -> Query:
    st.sidebar.header("Consulta")

    level = st.sidebar.radio(
        "Nivel", list(LEVELS), format_func=lambda k: LEVELS[k], key="nivel",
        help="El nivel cambia el mapa y las vistas disponibles. Departamento y "
             "país se derivan del panel municipal ponderando por píxeles "
             "válidos del ráster.")

    series_id = st.sidebar.selectbox(
        "Indicador", list(options), format_func=lambda k: options[k],
        key="serie", help=SERIES_HELP.get(st.session_state.get("serie", "")))
    if SERIES_HELP.get(series_id):
        st.sidebar.caption(SERIES_HELP[series_id])

    available = dekads(series_id)
    if not available:
        st.sidebar.error("La serie seleccionada no tiene datos en disco.")
        st.stop()

    st.sidebar.divider()
    mode = st.sidebar.radio(
        "Ventana", ["Un dekad", "Rango"], key="modo", horizontal=True,
        help="Solo se ofrecen dekads que FAO publicó: no se puede pedir uno "
             "que no exista.")

    if mode == "Un dekad":
        default = _clamp(st.session_state.get("dekad", available[-1]), available)
        start = end = st.sidebar.selectbox(
            "Dekad", available, index=available.index(default),
            format_func=dekad_label, key="dekad")
    else:
        # Por omisión, los últimos 18 meses y no la historia completa: veintiún
        # años de dekads hacen ilegible cualquier vista y pesan de más en el
        # navegador. Quien quiera todo el periodo lo pide moviendo "Desde".
        inicio = _clamp(dekad_window(available[-1], DEFAULT_RANGE)[0], available)
        d_from = _clamp(st.session_state.get("desde", inicio), available)
        d_to = _clamp(st.session_state.get("hasta", available[-1]), available)
        start = st.sidebar.selectbox(
            "Desde", available, index=available.index(d_from),
            format_func=dekad_label, key="desde")
        later = [d for d in available if dekad_index(d) >= dekad_index(start)]
        end = st.sidebar.selectbox(
            "Hasta", later,
            index=later.index(d_to) if d_to in later else len(later) - 1,
            format_func=dekad_label, key="hasta")

    departments: list[str] = []
    if level == "municipio":
        st.sidebar.divider()
        all_dept = sorted(municipios()["adm1_name"].unique())
        departments = st.sidebar.multiselect(
            "Filtrar departamentos", all_dept, default=[], key="departamentos",
            help="Vacío significa todo el país.")

    return Query(level=level, series_id=series_id, start=start, end=end,
                 departments=departments)


# --- Estado de la temporada --------------------------------------------------
def seasons_of(series_id: str) -> list[str]:
    """Temporadas que gobiernan el aviso de fuera de temporada."""
    if series_id == cfg.ASI_COMBINED:
        return [s.season for s in cfg.SERIES.values() if s.season]
    season = cfg.SERIES[series_id].season
    return [season] if season else []


def season_status(query: Query) -> dict:
    """Cuántos dekads de la ventana caen fuera de la ventana de cultivo.

    Se responde con la ventana declarada en config y no con la ausencia de dato,
    porque el ráster del ASI trae valores los 36 dekads del año: fuera de
    temporada el índice está congelado, que no es lo mismo que ausente.

    El indicador combinado se evalúa contra las dos temporadas a la vez: está
    fuera de temporada solo cuando ninguna está activa, que en Honduras ocurre
    entre febrero y abril.
    """
    seasons = seasons_of(query.series_id)
    if not seasons:
        return {"seasonal": False, "outside": 0, "total": 0}
    if query.series_id == cfg.ASI_COMBINED:
        name = "primera ni la postrera"
        window = " / ".join(f"{s}: {season_window_label(s)}" for s in seasons)
    else:
        name = cfg.SEASONS[seasons[0]].split(" (")[0].lower()
        window = season_window_label(seasons[0])
    codes = [d for d in dekads(query.series_id)
             if query.start <= d <= query.end]
    outside = [d for d in codes
               if not any(cfg.in_season(s, dekad_of_year(d)) for s in seasons)]
    return {"seasonal": True, "season_name": name, "outside": len(outside),
            "total": len(codes), "outside_codes": outside, "window": window}


def season_window_label(season: str) -> str:
    from asis.calendar import MONTH_ES
    start, end = cfg.SEASON_WINDOW[season]

    def name(k):
        return f"{MONTH_ES[(k - 1) // 3 + 1]} D{(k - 1) % 3 + 1}"

    return f"{name(start)} a {name(end)}"
