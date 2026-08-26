"""Panel agroclimático de Honduras — app de Streamlit.

Lee el panel ya construido de `data/` y no toca la red. Punto de entrada del
despliegue: `streamlit run streamlit_app.py`.

Es un tablero: la pantalla la ocupan los datos y los controles. Todo lo
explicativo vive en la pestaña "Cómo leer". Fuera de ahí solo aparecen los
avisos que dependen de la selección, que no son contexto general sino una
advertencia sobre la cifra que se está mirando.

El nivel gobierna la navegación y va de lo general a lo particular: país,
departamento, municipio.

Transparencia: cada figura trae la descarga de **sus** datos, los que están
dibujados en ella. Una sola descarga por nivel no alcanzaba, porque las figuras
muestran cortes distintos —otra ventana, otro nivel de agregación, otra fuente— y
ninguna descarga podía corresponder a todas.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app import texts
from app.controls import (LEVELS, MAX_FRAMES, Query, dekads, geojson, load,
                          manifest, national, season_status, sidebar,
                          series_options)
from asis import config as cfg, panel, viz
from asis.aggregate import at_level, severity_area, to_country
from asis.calendar import dekad_label, dekad_window

st.set_page_config(page_title=texts.TITLE, page_icon="🌾", layout="wide")

TABS = {
    "pais": ["Panorama nacional", "Datos", texts.HELP_TAB],
    "departamento": ["Mapa", "Series", "Datos", texts.HELP_TAB],
    "municipio": ["Mapa", "Ranking", "Datos", texts.HELP_TAB],
}
COUNTRY_WINDOW = 54           # 18 meses: mínimo para que una serie sea serie
PLURAL = {"municipio": "Municipios", "departamento": "Departamentos"}


# --- Ventana efectiva --------------------------------------------------------
def effective(query: Query) -> tuple[Query, bool]:
    """Ventana con la que se trabaja de verdad.

    A nivel país un solo dekad no da una serie, así que se amplía a 18 meses.
    Se amplía **la consulta entera** y no solo el gráfico: cuando solo se
    ampliaba el gráfico, la pestaña de datos mostraba una observación mientras
    la figura mostraba cincuenta y cuatro, y las dos decían ser lo mismo.
    """
    if query.level != "pais" or not query.single:
        return query, False
    available = dekads(query.series_id)
    inicio = max(dekad_window(query.end, COUNTRY_WINDOW)[0], available[0])
    if inicio == query.start:
        return query, False
    return Query(level=query.level, series_id=query.series_id, start=inicio,
                 end=query.end, departments=query.departments), True


# --- Encabezado --------------------------------------------------------------
def header(mf: dict):
    ultimo = max((s.get("ultimo") or "" for s in mf.get("series", {}).values()),
                 default="")
    st.title(texts.TITLE)
    st.caption(f"FAO GIEWS ASIS · panel al "
               f"{dekad_label(ultimo) if ultimo else 'sin datos'}")


def notices(query: Query, ampliada: bool):
    if ampliada:
        st.caption(f"Ventana ampliada a 18 meses ({query.window_label}): a "
                   f"nivel país un solo dekad no forma una serie.")
    status = season_status(query)
    if not status["seasonal"] or not status["outside"]:
        return
    completo = status["outside"] == status["total"]
    if status["combined"]:
        plantilla = (texts.OUT_OF_SEASON_COMBINED if completo
                     else texts.PARTIAL_SEASON_COMBINED)
    else:
        plantilla = texts.OUT_OF_SEASON if completo else texts.PARTIAL_SEASON
    st.warning(plantilla.format(
        n=status["outside"], total=status["total"],
        temporada=status["season_name"], ventana=status["window"],
        dekad=query.window_label))


def summary(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Cifras de encabezado del último dekad de la ventana.

    El promedio sale del agregado ponderado por píxeles válidos y no del
    promedio de las medias municipales: sin ponderar, un municipio diminuto
    pesaría igual que uno con diez veces más área de cultivo, y son más de tres
    puntos de diferencia.
    """
    with_data = cut.dropna(subset=["mean"])
    if with_data.empty:
        return
    nacional = to_country(muni)
    nacional = nacional[nacional["dekad_id"] == query.end]
    at_last = with_data[with_data["dekad_id"] == query.end]
    c1, c2, c3 = st.columns(3)
    if len(nacional):
        etiqueta = ("Promedio del área filtrada" if query.departments
                    else "Promedio nacional")
        c1.metric(f"{etiqueta} · {dekad_label(query.end)}",
                  f"{nacional['mean'].iloc[0]:.2f}",
                  help=f"{query.unit}. Ponderado por píxeles válidos.")
    if query.level == "pais":
        aportan = int(at_last["n_muni"].iloc[0]) if len(at_last) else 0
        c2.metric("Municipios que aportan", f"{aportan:,}")
    else:
        c2.metric(f"{PLURAL[query.level]} con dato", f"{len(at_last):,}")
    c3.metric("Dekads en la ventana", f"{with_data['dekad_id'].nunique():,}")


# --- Preparación del corte ---------------------------------------------------
def slice_for(query: Query) -> tuple[pd.DataFrame, pd.DataFrame]:
    muni = load(query.series_id, query.start, query.end)
    if len(muni) and query.departments:
        muni = muni[muni["adm1_name"].isin(query.departments)]
    if muni.empty:
        return muni, muni
    return muni, at_level(muni, query.level)


DISPLAY_NAMES = {
    "adm2_code": "código municipio", "adm2_name": "municipio",
    "adm1_code": "código departamento", "adm1_name": "departamento",
    "dekad_id": "dekad", "date": "fecha", "series": "serie",
    "season": "temporada", "n_px": "píxeles válidos", "km2": "km2",
    "mean": "media", "median": "mediana", "n_muni": "municipios",
}


def for_display(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df.columns if c != "series"]
    out = df[cols].rename(columns=DISPLAY_NAMES)
    if "fecha" in out:
        out["fecha"] = pd.to_datetime(out["fecha"]).dt.date
    return out


def figure(fig, data: pd.DataFrame, slug: str, key: str):
    """Dibuja una figura y ofrece exactamente los datos que muestra.

    El botón va en una columna angosta a la derecha: es una salida, no una
    acción principal, y no debe competir con la figura.
    """
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, width="stretch")
    shown = for_display(data)
    _, right = st.columns([3, 1])
    right.download_button(
        f"{texts.FIG_DOWNLOAD} ({len(shown):,})",
        shown.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"asis_{slug}.csv", mime="text/csv", key=key,
        width="stretch")


# --- Vistas: detalle territorial ---------------------------------------------
def view_map(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Coropleta del nivel seleccionado, con su propia geometría.

    Con una ventana corta el mapa se anima, un cuadro por dekad. Con una larga
    no: una animación de cientos de cuadros no se puede leer y obliga al
    navegador a cargar la geometría una vez por dekad. En ese caso se pinta el
    peor valor de la ventana.
    """
    data = muni if query.level == "municipio" else cut
    if data.empty:
        st.info(texts.NO_DATA)
        return
    n_dekads = data["dekad_id"].nunique()
    resumen = not query.single and n_dekads > MAX_FRAMES
    peor = "mayor" if query.family == "ASI" else "menor"
    extra = {c: ":.0f" for c in ("pct_gt40", "pct_lt0.35")
             if c in data.columns}

    if resumen:
        agg = "max" if query.family == "ASI" else "min"
        claves = [query.code_col, query.name_col]
        if query.name_col != "adm1_name" and "adm1_name" in data:
            claves.append("adm1_name")
        data = (data.groupby(claves, as_index=False, observed=True)
                .agg(**{"mean": ("mean", agg), "km2": ("km2", "max")}))
        titulo = f"{query.label} · {peor} valor de la ventana"
        subtitulo = f"{query.window_label} · {n_dekads} dekads"
        extra = {}
    else:
        titulo = f"{query.label} · {query.window_label}"
        subtitulo = ""

    fig = viz.class_map(
        data, geojson(query.level), query.family, titulo, subtitulo,
        animation=None if (query.single or resumen) else "dekad_id",
        hover_extra=extra, code_col=query.code_col, name_col=query.name_col)
    figure(fig, data, f"mapa_{query.slug()}", "dl_mapa")


def view_municipal_ranking(query: Query, muni: pd.DataFrame):
    """Los municipios en el extremo, seguidos en el tiempo.

    Con un rango es una matriz municipio por dekad, ordenada por el peor valor
    alcanzado en la ventana y no por el del último dekad, que dejaría fuera a
    quien tuvo el pico a mitad del periodo.
    """
    if muni.empty:
        st.info(texts.NO_DATA)
        return
    peor = "mayor" if query.family == "ASI" else "menor"
    top = st.slider("Municipios en el ranking", 10, 100, 50, 10,
                    key="top_ranking")
    agg = "max" if query.family == "ASI" else "min"

    if query.single:
        base = muni[muni["dekad_id"] == query.end]
        elegidos = (base.nlargest(top, "mean") if query.family == "ASI"
                    else base.nsmallest(top, "mean"))
        fig = viz.ranking_fig(
            base, "mean", f"Los {top} municipios con {peor} valor",
            dekad_label(query.end), family=query.family, top=top,
            label=query.unit_short, height=max(420, 17 * top))
    else:
        orden = muni.groupby("adm2_code", observed=True)["mean"].agg(agg)
        codigos = (orden.nlargest(top).index if query.family == "ASI"
                   else orden.nsmallest(top).index)
        elegidos = muni[muni["adm2_code"].isin(codigos)]
        fig = viz.heatmap_panel(
            muni, "mean", f"Los {top} municipios con {peor} valor",
            f"{query.window_label} · orden por el {peor} valor del periodo",
            family=query.family, top=top, ref_dekad=None,
            label=query.unit_short, height=max(480, 16 * top))
    figure(fig, elegidos, f"ranking_{query.slug()}", "dl_ranking")

    if not query.single:
        area = viz.severity_area_fig(
            muni, query.family, "Superficie por clase de severidad",
            "km2 en cada clase, dekad por dekad")
        figure(area, severity_area(muni, query.family).reset_index(),
               f"superficie_{query.slug()}", "dl_area")


def view_department_series(query: Query, cut: pd.DataFrame):
    """Una línea por departamento, o el ranking si la ventana es un dekad."""
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    if query.single:
        d = cut[cut["dekad_id"] == query.end]
        etiquetado = d.copy()
        etiquetado["adm2_name"] = etiquetado["adm1_name"]   # ranking_fig lo usa
        fig = viz.ranking_fig(
            etiquetado, "mean", f"{query.label} por departamento",
            dekad_label(query.end), family=query.family, top=18,
            label=query.unit_short, height=520)
        figure(fig, d, f"departamentos_{query.slug()}", "dl_dept")
        return

    d = cut.dropna(subset=["mean"]).sort_values("dekad_id")
    fig = px.line(d, x="date", y="mean", color="adm1_name",
                  labels={"mean": query.unit_short, "date": "",
                          "adm1_name": ""}, height=560)
    fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}"
                                    "<extra>%{fullData.name}</extra>")
    # Leyenda vertical a la derecha: dieciocho departamentos en una fila
    # horizontal no se leen.
    viz.style_fig(fig, f"{query.label} por departamento", query.window_label,
                  y_source=-0.13, legend="v")
    figure(fig, d, f"departamentos_{query.slug()}", "dl_dept")


# --- Vista: panorama nacional ------------------------------------------------
def view_country(query: Query, cut: pd.DataFrame):
    """Del encuadre histórico al detalle de la ventana.

    Primero la climatología, que sitúa el año dentro de veintiún años; después
    los tres indicadores sobre el mismo eje temporal; al final la lluvia contra
    su promedio de largo plazo.
    """
    asi_nat = national("serie_nacional_asi")
    rain = national("serie_nacional_lluvia")

    if not asi_nat.empty:
        fig = viz.climatology_matrix(
            asi_nat, "Climatología del estrés agrícola",
            "ASI nacional oficial de FAO por dekad de la temporada primera · "
            "cada franja roja horizontal es una sequía agrícola")
        figure(fig, asi_nat[asi_nat["dekad_of_year"].between(13, 30)]
               [["Year", "dekad_id", "dekad_of_year", "value"]],
               "climatologia_asi_nacional", "dl_clima")

    asi_id = query.series_id if query.family == "ASI" else cfg.ASI_COMBINED
    asi = to_country(load(asi_id, query.start, query.end))
    vci = (to_country(load("vci", query.start, query.end))
           if "vci" in panel.stored_series() else pd.DataFrame())
    ventana = pd.DataFrame()
    if len(rain):
        ventana = rain[(rain["dekad_id"] >= query.start)
                       & (rain["dekad_id"] <= query.end)]
    tablero = viz.dashboard_fig(
        asi, vci, ventana, "Estrés, vegetación y lluvia", query.window_label)
    figure(tablero, _merge_dashboard(asi, vci, ventana),
           f"tablero_nacional_{query.slug()}", "dl_tablero")

    if len(ventana):
        fig = viz.rainfall_fig(
            ventana, "Lluvia observada y su promedio histórico",
            "Ponderada por área de cultivo · el promedio de largo plazo es el "
            "que publica FAO y no se recalcula")
        figure(fig, ventana, f"lluvia_nacional_{query.slug()}", "dl_lluvia")


def _merge_dashboard(asi, vci, rain) -> pd.DataFrame:
    """Los tres indicadores del tablero en una tabla, para la descarga."""
    out = pd.DataFrame()
    if len(asi):
        out = asi[["dekad_id", "date", "mean"]].rename(columns={"mean": "asi"})
    if len(vci):
        v = vci[["dekad_id", "mean"]].rename(columns={"mean": "vci"})
        out = v if out.empty else out.merge(v, on="dekad_id", how="outer")
    if len(rain):
        cols = [c for c in ("dekad_id", "obs", "lta", "anom_pct")
                if c in rain.columns]
        out = (rain[cols] if out.empty
               else out.merge(rain[cols], on="dekad_id", how="outer"))
    return out.sort_values("dekad_id") if len(out) else out


# --- Vista: datos ------------------------------------------------------------
def view_data(query: Query, cut: pd.DataFrame):
    """El corte completo del nivel, más la definición de cada columna."""
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    shown = for_display(cut)
    st.download_button(
        f"Descargar el corte completo · {len(shown):,} filas",
        shown.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"asis_{query.slug()}.csv", mime="text/csv",
        help=texts.DOWNLOAD_HELP, type="primary", key="dl_completo")
    st.dataframe(shown, width="stretch", hide_index=True, height=420)

    definiciones = pd.DataFrame(
        [{"columna": c, "definición": texts.describe_column(c)}
         for c in shown.columns])
    with st.expander("Definición de cada columna"):
        st.dataframe(definiciones, width="stretch", hide_index=True,
                     height=min(430, 45 + 35 * len(definiciones)))


def view_help(mf: dict):
    """Todo lo explicativo, en un solo lugar y solo cuando se busca."""
    for titulo, fichas in (("Cómo leer los indicadores", texts.READING),
                           ("Limitaciones", texts.LIMITS)):
        st.subheader(titulo)
        left, right = st.columns(2)
        for i, (nombre, cuerpo) in enumerate(fichas):
            with (left if i % 2 == 0 else right):
                with st.container(border=True):
                    st.markdown(f"**{nombre}**")
                    st.caption(cuerpo)

    st.subheader("Procedencia y validación")
    ultimo = max((s.get("ultimo") or "" for s in mf.get("series", {}).values()),
                 default="")
    st.caption(texts.SOURCE_TEMPLATE.format(
        construido=(mf.get("actualizado") or "")[:10],
        ultimo=dekad_label(ultimo) if ultimo else "sin datos"))
    v = mf.get("validacion") or {}
    if v.get("r") is not None:
        st.caption(texts.VALIDATION_TEMPLATE.format(
            r=v["r"], r2=v["r2"], mae=v["mae_pp"], sesgo=v["sesgo_pp"],
            pares=v["pares"]))
    src = panel.sources()
    vintages = ", ".join(f"{k} ({d.get('descargado')})"
                         for k, d in sorted(src.items())
                         if d.get("descargado"))
    if vintages:
        st.caption(f"Instantáneas de los CSV oficiales de GIEWS: {vintages}.")
    st.caption(texts.AI_NOTE)


# --- Página ------------------------------------------------------------------
def render(name: str, query: Query, muni: pd.DataFrame, cut: pd.DataFrame,
           mf: dict):
    if name == "Mapa":
        view_map(query, muni, cut)
    elif name == "Ranking":
        view_municipal_ranking(query, muni)
    elif name == "Series":
        view_department_series(query, cut)
    elif name == "Panorama nacional":
        view_country(query, cut)
    elif name == "Datos":
        view_data(query, cut)
    elif name == texts.HELP_TAB:
        view_help(mf)


def main():
    try:
        mf = manifest()
        options = series_options()
    except panel.PanelVacio:
        st.title(texts.TITLE)
        st.error(texts.EMPTY_PANEL)
        return
    if not options:
        st.title(texts.TITLE)
        st.error(texts.EMPTY_PANEL)
        return

    query, ampliada = effective(sidebar(options))
    header(mf)
    notices(query, ampliada)
    muni, cut = slice_for(query)

    if muni.empty:
        st.info(texts.NO_DATA)
        return

    summary(query, muni, cut)
    names = TABS[query.level]
    for tab, name in zip(st.tabs(names), names):
        with tab:
            render(name, query, muni, cut, mf)


if __name__ == "__main__":
    main()
