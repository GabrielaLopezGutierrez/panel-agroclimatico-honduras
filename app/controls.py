"""Controles de la app y acceso al panel con caché.

Tres controles y nada más: nivel, indicador y ventana. `START_YEAR`, el país y
el bbox viven en `asis/config.py` porque se cambian una vez al año, no por
corrida.

El panel se cachea por proceso, que es lo correcto: no contiene información de
ningún usuario. El estado de la consulta vive en `st.session_state`, porque ese
sí es de cada quien.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from asis import config as cfg, panel
from asis.calendar import dekad_index, dekad_label, dekad_of_year, dekad_window

LEVELS = {"municipio": "Municipio", "departamento": "Departamento",
          "pais": "País"}


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
    def season(self) -> str | None:
        if self.series_id == cfg.ASI_COMBINED:
            return None
        return cfg.SERIES[self.series_id].season

    @property
    def label(self) -> str:
        return panel.label_of(self.series_id)

    @property
    def window_label(self) -> str:
        if self.single:
            return dekad_label(self.start)
        return f"{dekad_label(self.start)} a {dekad_label(self.end)}"

    def slug(self) -> str:
        base = f"{self.series_id}_{self.level}_{self.start}"
        return base if self.single else f"{base}_{self.end}"


# --- Acceso cacheado ---------------------------------------------------------
# La caché es por proceso y eso es lo correcto para el panel, que no contiene
# información de ningún usuario. Pero el panel se reconstruye por debajo: la
# actualización automática commitea datos nuevos mientras el proceso sigue vivo.
# Por eso todo lo cacheado se indexa por la versión del panel, y un panel nuevo
# invalida las entradas viejas en vez de servir cifras de la semana pasada.
def data_version() -> str:
    try:
        return str(panel.MANIFEST.stat().st_mtime_ns)
    except OSError:
        return "0"


@st.cache_data(show_spinner=False)
def _manifest(version: str) -> dict:
    return panel.manifest()


@st.cache_data(show_spinner=False)
def _geojson(version: str) -> dict:
    return panel.geojson()


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


def geojson() -> dict:
    return _geojson(data_version())


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


# --- Atajos de ventana -------------------------------------------------------
def presets(available: list[str]) -> dict[str, tuple[str, str]]:
    """Ventanas de uso frecuente. Se recortan a lo que existe en el panel: un
    atajo no debe ofrecer un dekad que FAO no publicó."""
    last = available[-1]
    out: dict[str, tuple[str, str]] = {
        "Último dekad": (last, last),
        "Últimos 18 meses": (max(dekad_window(last, 54)[0], available[0]), last),
    }
    for name, (a, b) in (("Sequía de 2019", ("2019-05-D1", "2019-10-D3")),
                         ("Eta e Iota 2020", ("2020-10-D1", "2021-02-D3"))):
        lo = max(a, available[0])
        hi = min(b, last)
        if dekad_index(lo) <= dekad_index(hi):
            out[name] = (lo, hi)
    return out


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
        "Nivel", list(LEVELS), format_func=lambda k: LEVELS[k],
        key="nivel", horizontal=False,
        help="Departamento y país se derivan del panel municipal ponderando "
             "por píxeles válidos.")

    series_id = st.sidebar.selectbox(
        "Indicador", list(options), format_func=lambda k: options[k],
        key="serie")

    available = dekads(series_id)
    if not available:
        st.sidebar.error("La serie seleccionada no tiene datos en disco.")
        st.stop()

    st.sidebar.divider()
    quick = presets(available)
    st.sidebar.caption("Atajos")
    cols = st.sidebar.columns(2)
    for i, (name, (a, b)) in enumerate(quick.items()):
        if cols[i % 2].button(name, use_container_width=True,
                              key=f"atajo_{i}"):
            st.session_state["modo"] = "Un dekad" if a == b else "Rango"
            st.session_state["desde"] = a
            st.session_state["hasta"] = b
            st.session_state["dekad"] = b

    mode = st.sidebar.radio("Ventana", ["Un dekad", "Rango"], key="modo",
                            horizontal=True)

    if mode == "Un dekad":
        default = st.session_state.get("dekad", available[-1])
        idx = available.index(_clamp(default, available))
        start = end = st.sidebar.selectbox(
            "Dekad", available, index=idx, format_func=dekad_label,
            key="dekad")
    else:
        d_from = _clamp(st.session_state.get("desde", available[0]), available)
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
def season_status(query: Query) -> dict:
    """Cuántos dekads de la ventana caen fuera de la ventana de cultivo.

    Se responde con la ventana declarada en config y no con la ausencia de dato,
    porque el ráster del ASI trae valores los 36 dekads del año: fuera de
    temporada el índice está congelado, que no es lo mismo que ausente.

    El peor caso combinado se evalúa contra las dos temporadas a la vez: está
    fuera de temporada solo cuando ninguna de las dos está activa, que en
    Honduras ocurre entre febrero y abril.
    """
    if query.series_id == cfg.ASI_COMBINED:
        seasons = [s.season for s in cfg.SERIES.values() if s.season]
        name = "primera ni la postrera"
        window = " / ".join(f"{s}: {season_window_label(s)}" for s in seasons)
    elif query.season:
        seasons = [query.season]
        name = cfg.SEASONS.get(query.season, query.season).split(" (")[0].lower()
        window = season_window_label(query.season)
    else:
        return {"seasonal": False, "outside": 0, "total": 0}

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
