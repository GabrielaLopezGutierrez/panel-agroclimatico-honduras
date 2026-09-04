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

from app import texts
from asis import config as cfg, panel
from asis.calendar import (dekad_index, dekad_label, dekad_of_year,
                           dekad_window)

LEVELS = {"pais": "País", "departamento": "Departamento",
          "municipio": "Municipio"}

# El resumen nacional es un modo de vista, no una serie: muestra las dos
# temporadas del ASI una al lado de la otra, cada una con su propia cifra. No
# existe como serie del panel a propósito. Antes había aquí un indicador
# combinado que tomaba el mayor de las dos temporadas por municipio; se retiró
# porque cada temporada se mide sobre su propia máscara de cultivo, y al
# agregar a país ponderando por píxeles válidos el combinado terminaba por
# debajo de la primera sola: los municipios donde mandaba la postrera perdían
# el 95% de su peso justo por ser los peores. Ver DECISIONES.md.
OVERVIEW = "resumen"
# Las series que componen el resumen, en el orden en que se muestran.
OVERVIEW_SERIES = ["asi_gs1", "asi_gs2", "vci"]

DEFAULT_RANGE = 54      # 18 meses: la ventana con la que se trabaja a diario
# El modo de ventana que conviene por omisión no es el mismo en todos los
# niveles: a nivel país un solo dekad no dice mucho sin su serie de tiempo
# (por eso "Rango" es la que se muestra al abrir); a nivel departamento y
# municipio la vista de uso diario es la foto de un dekad, así que "Un dekad"
# es el que se ve primero. Esto es solo el valor inicial: cada nivel guarda su
# propia elección aparte, así que cambiarlo en un nivel no toca los otros.
DEFAULT_MODE = {"pais": "Rango", "departamento": "Un dekad",
                "municipio": "Un dekad"}
WINDOW_MODES = ["Un dekad", "Rango"]

# Atajos del rango, en dekads. Antes el rango se elegía con dos desplegables de
# 779 opciones cada uno: para ver los últimos doce meses había que buscar un
# código a mano en una lista de veintiún años. Casi siempre se quiere una
# ventana reciente de largo redondo, así que eso se resuelve con un clic y el
# deslizador queda para el caso que no cubre ningún atajo.
CUSTOM_RANGE = "Personalizado"
RANGE_PRESETS = {
    "12 meses": 36,
    "18 meses": 54,
    "3 años": 108,
    "5 años": 180,
    "Todo": None,
    CUSTOM_RANGE: None,
}
# Un mapa animado con un cuadro por dekad deja de ser legible mucho antes de
# volverse pesado. Pasado este limite el mapa muestra el extremo de la ventana
# en vez de la secuencia.
MAX_FRAMES = 24


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
    def overview(self) -> bool:
        """El resumen nacional no es una serie: no tiene familia ni unidad
        propias, y las vistas que lo reciben trabajan serie por serie."""
        return self.series_id == OVERVIEW

    @property
    def family(self) -> str:
        return "ASI" if self.overview else panel.family_of(self.series_id)

    @property
    def label(self) -> str:
        return (texts.OVERVIEW_LABEL if self.overview
                else panel.label_of(self.series_id))

    @property
    def unit(self) -> str:
        return panel.unit_of("asi_gs1" if self.overview else self.series_id)

    @property
    def unit_short(self) -> str:
        return panel.unit_short_of(
            "asi_gs1" if self.overview else self.series_id)

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


@st.cache_data(show_spinner=False)
def _is_preliminary(version: str, series_id: str, dekad_id: str) -> bool:
    return panel.is_preliminary(series_id, dekad_id)


def manifest() -> dict:
    return _manifest(data_version())


def geojson(level: str = "municipio") -> dict:
    return _geojson(data_version(), level)


def dekads(series_id: str) -> list[str]:
    # El eje de tiempo del resumen es el de la primera: es la temporada de
    # ventana más ancha, así que ninguna de las otras series se queda fuera.
    if series_id == OVERVIEW:
        series_id = "asi_gs1"
    return _dekads(data_version(), series_id)


def load(series_id: str, start: str, end: str) -> pd.DataFrame:
    return _load(data_version(), series_id, start, end)


def national(name: str) -> pd.DataFrame:
    return _national(data_version(), name)


def series_options() -> dict[str, str]:
    return _series_options(data_version())


def municipios() -> pd.DataFrame:
    return _municipios(data_version())


def is_preliminary(series_id: str, dekad_id: str) -> bool:
    if series_id == OVERVIEW:
        return any(_is_preliminary(data_version(), s, dekad_id)
                   for s in OVERVIEW_SERIES)
    return _is_preliminary(data_version(), series_id, dekad_id)


def _clamp(code: str, available: list[str]) -> str:
    """Lleva un código al dekad disponible más cercano hacia atrás."""
    if code in available:
        return code
    earlier = [d for d in available if dekad_index(d) <= dekad_index(code)]
    return earlier[-1] if earlier else available[0]


def preset_range(available: list[str], n: int | None) -> tuple[str, str]:
    """Extremos de un atajo: los últimos `n` dekads, o todo si `n` es None."""
    if n is None:
        return available[0], available[-1]
    return _clamp(dekad_window(available[-1], n)[0], available), available[-1]


def range_controls(available: list[str]) -> tuple[str, str]:
    """Selección del rango: un atajo y un deslizador de dos extremos.

    El deslizador reemplaza dos desplegables de 779 opciones. Además de ser
    menos clics, quita el estado imposible que tenían: eran dos controles
    independientes, así que "Hasta" había que recortarlo a mano para que no
    quedara antes de "Desde". Un deslizador de dos extremos no puede cruzarse.
    """
    if not available:
        return "", ""
    por_omision = preset_range(available, DEFAULT_RANGE)

    def _aplicar_atajo():
        n = RANGE_PRESETS[st.session_state["atajo"]]
        if st.session_state["atajo"] == CUSTOM_RANGE:
            return          # personalizado no mueve nada: manda el deslizador
        st.session_state["rango"] = preset_range(available, n)

    def _movio_el_deslizador():
        # Mover el deslizador deja de ser cualquier atajo: decirlo evita que la
        # etiqueta afirme "12 meses" sobre una ventana que ya no lo es.
        st.session_state["atajo"] = CUSTOM_RANGE

    st.session_state.setdefault("atajo", "18 meses")
    st.session_state.setdefault("rango", por_omision)
    st.sidebar.selectbox("Atajo", list(RANGE_PRESETS), key="atajo",
                         on_change=_aplicar_atajo, help=texts.RANGE_HELP)

    # El rango guardado se reajusta a la serie actual: cambiar de indicador
    # puede dejar un extremo en un dekad que esa serie no tiene.
    guardado = st.session_state["rango"]
    st.session_state["rango"] = (_clamp(guardado[0], available),
                                 _clamp(guardado[1], available))
    return st.sidebar.select_slider(
        "Periodo", options=available, key="rango", format_func=dekad_label,
        on_change=_movio_el_deslizador)


def indicator_options(level: str, options: dict[str, str]) -> dict[str, str]:
    """Opciones de indicador mostradas según el nivel.

    Todas las opciones son series reales del panel. A nivel país se antepone
    el resumen, que no es una serie sino la vista que muestra las dos
    temporadas del ASI por separado, cada una con su cifra y su mapa de calor.
    """
    if level != "pais" or not {"asi_gs1", "asi_gs2"} <= set(options):
        return dict(options)
    return {OVERVIEW: texts.OVERVIEW_LABEL, **options}


# --- Panel de control --------------------------------------------------------
def sidebar(options: dict[str, str]) -> Query:
    st.sidebar.header("Consulta")

    level = st.sidebar.radio(
        "Nivel", list(LEVELS), format_func=lambda k: LEVELS[k], key="nivel",
        help=texts.LEVEL_HELP)

    opts = indicator_options(level, options)
    # Cambiar de nivel puede dejar en session_state un indicador que ya no es
    # una opción válida (el resumen general solo existe a nivel país): se
    # corrige antes de crear el selectbox, porque Streamlit no acepta un valor
    # guardado que no está entre las opciones nuevas.
    if st.session_state.get("serie") not in opts:
        st.session_state["serie"] = next(iter(opts))
    series_id = st.sidebar.selectbox(
        "Indicador", list(opts), format_func=lambda k: opts[k], key="serie",
        help=texts.SERIES_HELP.get(st.session_state.get("serie", "")))

    available = dekads(series_id)
    if not available:
        st.sidebar.error("La serie seleccionada no tiene datos en disco.")
        st.stop()

    st.sidebar.divider()
    # Una llave de estado por nivel: así "Rango" a nivel país e "Un dekad" a
    # nivel municipio no se pisan entre sí, y cada uno recuerda lo último que
    # se eligió ahí la próxima vez que se vuelve a ese nivel.
    modo_key = f"modo_{level}"
    mode = st.sidebar.radio(
        "Ventana", WINDOW_MODES, key=modo_key, horizontal=True,
        index=WINDOW_MODES.index(DEFAULT_MODE[level]), help=texts.WINDOW_HELP)

    if mode == "Un dekad":
        default = _clamp(st.session_state.get("dekad", available[-1]), available)
        start = end = st.sidebar.selectbox(
            "Dekad", available, index=available.index(default),
            format_func=dekad_label, key="dekad")
    else:
        start, end = range_controls(available)

    departments: list[str] = []
    if level == "municipio":
        st.sidebar.divider()
        all_dept = sorted(municipios()["adm1_name"].unique())
        departments = st.sidebar.multiselect(
            "Filtrar departamentos", all_dept, default=[], key="departamentos",
            placeholder="Todo el país")

    return Query(level=level, series_id=series_id, start=start, end=end,
                 departments=departments)


# --- Estado de la temporada --------------------------------------------------
def seasons_of(series_id: str) -> list[str]:
    """Temporadas que gobiernan el aviso de fuera de temporada."""
    if series_id == OVERVIEW:
        return [s.season for s in cfg.SERIES.values() if s.season]
    season = cfg.SERIES[series_id].season
    return [season] if season else []


def season_status(query: Query) -> dict:
    """Cuántos dekads de la ventana caen fuera de la ventana de cultivo.

    Se responde con la ventana declarada en config y no con la ausencia de dato,
    porque el ráster del ASI trae valores los 36 dekads del año: fuera de
    temporada el índice está congelado, que no es lo mismo que ausente.

    El resumen nacional se evalúa contra las dos temporadas a la vez: está
    fuera de temporada solo cuando ninguna está activa, que en Honduras ocurre
    entre febrero y abril.
    """
    seasons = seasons_of(query.series_id)
    if not seasons:
        return {"seasonal": False, "outside": 0, "total": 0}
    combinado = query.series_id == OVERVIEW
    if combinado:
        name = ""
        window = " · ".join(f"{cfg.SEASONS[s].split(' (')[0].lower()} "
                            f"{season_window_label(s)}" for s in seasons)
    else:
        name = cfg.SEASONS[seasons[0]].split(" (")[0].lower()
        window = season_window_label(seasons[0])
    codes = [d for d in dekads(query.series_id)
             if query.start <= d <= query.end]
    outside = [d for d in codes
               if not any(cfg.in_season(s, dekad_of_year(d)) for s in seasons)]
    return {"seasonal": True, "season_name": name, "combined": combinado,
            "outside": len(outside), "total": len(codes),
            "outside_codes": outside, "window": window}


def season_window_label(season: str) -> str:
    from asis.calendar import MONTH_ES
    start, end = cfg.SEASON_WINDOW[season]

    def name(k):
        return f"{MONTH_ES[(k - 1) // 3 + 1]} D{(k - 1) % 3 + 1}"

    return f"{name(start)} a {name(end)}"
