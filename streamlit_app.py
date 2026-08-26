"""Panel agroclimático de Honduras — app de Streamlit.

Lee el panel ya construido de `data/` y no toca la red. Punto de entrada del
despliegue: `streamlit run streamlit_app.py`.

Es un tablero: la pantalla la ocupan los datos y los controles. Todo lo
explicativo vive en la pestaña "Cómo leer" y no repartido por cada vista. Lo
único que aparece fuera de ahí son los avisos que dependen de la selección, que
no son contexto general sino una advertencia sobre la cifra que se está mirando.

El nivel gobierna la navegación y va de lo general a lo particular: país,
departamento, municipio. Cada nivel ofrece solo las vistas que tienen sentido en
él y todas traen contenido.
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
from asis.aggregate import at_level, climatology, to_country
from asis.calendar import dekad_label, dekad_window, dekad_year

st.set_page_config(page_title=texts.TITLE, page_icon="🌾", layout="wide")

TABS = {
    "pais": ["Serie nacional", "Contexto", "Datos", texts.HELP_TAB],
    "departamento": ["Mapa", "Series", "Datos", texts.HELP_TAB],
    "municipio": ["Mapa", "Ranking", "Datos", texts.HELP_TAB],
}
DASHBOARD_WINDOW = 54          # 18 meses, la ventana que usa el cuaderno
# El plural no se arma agregando una "s": "Paiss" no es una palabra.
PLURAL = {"municipio": "Municipios", "departamento": "Departamentos"}


# --- Encabezado --------------------------------------------------------------
def header(mf: dict):
    """Título y una sola línea de contexto. El resto está en «Cómo leer»."""
    ultimo = max((s.get("ultimo") or "" for s in mf.get("series", {}).values()),
                 default="")
    st.title(texts.TITLE)
    st.caption(f"FAO GIEWS ASIS · panel al "
               f"{dekad_label(ultimo) if ultimo else 'sin datos'}")


def season_notice(query: Query):
    """Aviso de fuera de temporada. Nunca un mapa vacío que se lea como
    ausencia de estrés."""
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

    El promedio se toma siempre del agregado ponderado por píxeles válidos, no
    del promedio de las medias municipales: promediar sin ponderar le daría a un
    municipio diminuto el mismo peso que a uno con diez veces más área de
    cultivo, y son más de tres puntos de diferencia.
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
    """Devuelve (panel municipal filtrado, corte al nivel pedido)."""
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


# --- Vistas ------------------------------------------------------------------
def view_map(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Coropleta del nivel seleccionado, con su propia geometría.

    Con una ventana corta el mapa se anima, un cuadro por dekad. Con una larga
    no: una animación de cientos de cuadros no se puede leer y obliga al
    navegador a cargar la geometría una vez por dekad. En ese caso se pinta el
    peor valor de la ventana, que es la pregunta que uno le hace a un periodo
    largo.
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
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, width="stretch")


def view_municipal_ranking(query: Query, muni: pd.DataFrame):
    """Los municipios en el extremo, seguidos en el tiempo.

    Con un rango es una matriz municipio por dekad, ordenada por el peor valor
    alcanzado en la ventana y no por el del último dekad, que dejaría fuera a
    quien tuvo el pico a mitad del periodo. Con un solo dekad la matriz sería
    una columna, así que la vista es un ranking ordenado.
    """
    if muni.empty:
        st.info(texts.NO_DATA)
        return
    peor = "mayor" if query.family == "ASI" else "menor"
    top = st.slider("Municipios en el ranking", 10, 100, 50, 10,
                    key="top_ranking")
    if query.single:
        fig = viz.ranking_fig(
            muni[muni["dekad_id"] == query.end], "mean",
            f"Los {top} municipios con {peor} valor",
            dekad_label(query.end), family=query.family, top=top,
            label=query.unit_short, height=max(420, 17 * top))
    else:
        fig = viz.heatmap_panel(
            muni, "mean", f"Los {top} municipios con {peor} valor",
            f"{query.window_label} · orden por el {peor} valor del periodo",
            family=query.family, top=top, ref_dekad=None,
            label=query.unit_short, height=max(480, 16 * top))
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, width="stretch")

    if not query.single:
        area = viz.severity_area_fig(
            muni, query.family, "Superficie por clase de severidad",
            "km2 en cada clase, dekad por dekad")
        if area:
            st.plotly_chart(area, width="stretch")


def view_department_series(query: Query, cut: pd.DataFrame):
    """Una línea por departamento, o el ranking si la ventana es un dekad."""
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    if query.single:
        d = cut[cut["dekad_id"] == query.end].copy()
        d["adm2_name"] = d["adm1_name"]        # ranking_fig etiqueta con este
        fig = viz.ranking_fig(
            d, "mean", f"{query.label} por departamento",
            dekad_label(query.end), family=query.family, top=18,
            label=query.unit_short, height=520)
        if fig:
            st.plotly_chart(fig, width="stretch")
        return

    d = cut.dropna(subset=["mean"]).sort_values("dekad_id")
    fig = px.line(d, x="date", y="mean", color="adm1_name",
                  labels={"mean": query.unit_short, "date": "",
                          "adm1_name": ""},
                  height=560)
    fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}"
                                    "<extra>%{fullData.name}</extra>")
    # Leyenda vertical a la derecha: dieciocho departamentos en una fila
    # horizontal no se leen.
    viz.style_fig(fig, f"{query.label} por departamento", query.window_label,
                  y_source=-0.13, legend="v")
    st.plotly_chart(fig, width="stretch")


def _dashboard_window(query: Query) -> tuple[str, str]:
    """Ventana del tablero nacional.

    Con un solo dekad no hay serie que dibujar, así que se muestran los 18 meses
    que terminan en ese dekad y se dice en el subtítulo, para que nadie lea el
    gráfico como si fuera el dekad.
    """
    if not query.single:
        return query.start, query.end
    available = dekads(query.series_id)
    inicio = dekad_window(query.end, DASHBOARD_WINDOW)[0]
    return max(inicio, available[0]), query.end


def view_country(query: Query):
    """Serie nacional del indicador y los tres indicadores en el mismo eje."""
    start, end = _dashboard_window(query)
    ampliada = (start, end) != (query.start, query.end)
    serie = to_country(load(query.series_id, start, end))
    if serie.empty:
        st.info(texts.NO_DATA)
        return
    sub = (f"Últimos 18 meses hasta {dekad_label(end)}" if ampliada
           else query.window_label)
    fig = viz.series_fig(
        serie, "mean", f"{query.label} · nacional", sub,
        label=query.unit_short, family=query.family,
        threshold=0.35 if query.family == "VCI" else None,
        threshold_label="umbral FAO 0,35" if query.family == "VCI" else "")
    if fig:
        st.plotly_chart(fig, width="stretch")

    asi_id = query.series_id if query.family == "ASI" else cfg.ASI_COMBINED
    asi = to_country(load(asi_id, start, end))
    vci = (to_country(load("vci", start, end))
           if "vci" in panel.stored_series() else pd.DataFrame())
    rain = national("serie_nacional_lluvia")
    if len(rain):
        rain = rain[(rain["dekad_id"] >= start) & (rain["dekad_id"] <= end)]
    tablero = viz.dashboard_fig(
        asi, vci, rain, "Estrés, vegetación y lluvia", sub)
    if tablero:
        st.plotly_chart(tablero, width="stretch")


def view_context(query: Query):
    """Contexto nacional oficial de FAO: climatología y lluvia.

    Es el dato que publica GIEWS, no un agregado propio, y es la referencia
    contra la cual se valida el panel.
    """
    asi_nat = national("serie_nacional_asi")
    rain = national("serie_nacional_lluvia")
    if asi_nat.empty and rain.empty:
        st.info("Las series nacionales oficiales no están construidas en este "
                "despliegue.")
        return

    if not asi_nat.empty:
        year = dekad_year(query.end)
        pctl, n_base = climatology(asi_nat, year_max=year)
        years = [y for y in (year, 2019, 2020) if y in set(asi_nat["Year"])]
        fig = viz.climatology_fig(
            asi_nat, pctl, n_base, years, f"{year} frente a la norma histórica",
            f"ASI nacional de la primera, mayo a octubre · franja p10-p90 de "
            f"{n_base} años previos")
        if fig:
            st.plotly_chart(fig, width="stretch")

        matrix = viz.climatology_matrix(
            asi_nat, "Climatología del estrés agrícola",
            "ASI nacional por dekad de la primera · cada franja roja es una "
            "sequía agrícola")
        if matrix:
            st.plotly_chart(matrix, width="stretch")

    if not rain.empty:
        start, end = _dashboard_window(query)
        window = rain[(rain["dekad_id"] >= start) & (rain["dekad_id"] <= end)]
        if len(window) < 3:
            window = rain.tail(DASHBOARD_WINDOW)
        fig = viz.rainfall_fig(
            window, "Lluvia observada y su promedio histórico",
            "Ponderada por área de cultivo · la LTA es la que publica FAO")
        if fig:
            st.plotly_chart(fig, width="stretch")


def view_data(query: Query, cut: pd.DataFrame):
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    shown = for_display(cut)
    csv = shown.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        f"Descargar CSV · {len(shown):,} filas", csv,
        file_name=f"asis_{query.slug()}.csv", mime="text/csv",
        help=texts.DOWNLOAD_HELP, type="primary")
    st.dataframe(shown, width="stretch", hide_index=True, height=520)


def view_help(mf: dict):
    """Todo lo explicativo, en un solo lugar y solo cuando se busca."""
    st.subheader("Cómo leer los indicadores")
    left, right = st.columns(2)
    for i, (title, body) in enumerate(texts.READING):
        with (left if i % 2 == 0 else right):
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(body)

    st.subheader("Limitaciones")
    left, right = st.columns(2)
    for i, (title, body) in enumerate(texts.LIMITS):
        with (left if i % 2 == 0 else right):
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(body)

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
    elif name == "Serie nacional":
        view_country(query)
    elif name == "Contexto":
        view_context(query)
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

    query = sidebar(options)
    header(mf)
    season_notice(query)
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
