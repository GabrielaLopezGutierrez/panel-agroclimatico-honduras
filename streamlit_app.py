"""Panel agroclimático de Honduras — app de Streamlit.

Lee el panel ya construido de `data/` y no toca la red. Punto de entrada del
despliegue: `streamlit run streamlit_app.py`.

El nivel gobierna la navegación. Cada nivel ofrece solo las vistas que tienen
sentido en él y todas traen contenido: no hay pestañas que terminen en un
mensaje pidiendo cambiar el nivel o la ventana, que es lo que hacía parecer
ordenada una navegación que no servía para navegar.
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
from asis.calendar import dekad_index, dekad_label, dekad_window, dekad_year

st.set_page_config(page_title=texts.TITLE, page_icon="🌾", layout="wide")

# Vistas de cada nivel, en el orden en que se muestran.
TABS = {
    "municipio": ["Mapa", "Ranking municipal", "Contexto nacional", "Datos"],
    "departamento": ["Mapa", "Series por departamento", "Contexto nacional",
                     "Datos"],
    "pais": ["Serie nacional", "Contexto nacional", "Datos"],
}
DASHBOARD_WINDOW = 54          # 18 meses, la ventana que usa el cuaderno
# El plural no se arma agregando una "s": "Paiss" no es una palabra.
PLURAL = {"municipio": "Municipios", "departamento": "Departamentos",
          "pais": "Series"}


# --- Encabezado --------------------------------------------------------------
def header(mf: dict, query: Query):
    st.title(texts.TITLE)
    st.caption(texts.SUBTITLE)

    ultimo = max((s.get("ultimo") or "" for s in mf.get("series", {}).values()),
                 default="")
    v = mf.get("validacion") or {}
    with st.expander(f"Procedencia y validación · panel al "
                     f"{dekad_label(ultimo) if ultimo else 'sin datos'}"):
        st.caption(texts.SOURCE_TEMPLATE.format(
            construido=(mf.get("actualizado") or "")[:10],
            ultimo=dekad_label(ultimo) if ultimo else "sin datos"))
        if v.get("r") is not None:
            st.caption(texts.VALIDATION_TEMPLATE.format(
                r=v["r"], r2=v["r2"], mae=v["mae_pp"], sesgo=v["sesgo_pp"],
                pares=v["pares"]))
        st.caption(texts.WEIGHTING)
        src = panel.sources()
        vintages = ", ".join(f"{k} ({d.get('descargado')})"
                             for k, d in sorted(src.items())
                             if d.get("descargado"))
        if vintages:
            st.caption(f"Instantáneas de los CSV oficiales de GIEWS: "
                       f"{vintages}.")
    st.caption(texts.HOW_TO_READ_SHORT)


def season_notice(query: Query):
    """Aviso explícito de fuera de temporada. Nunca un mapa vacío que se lea
    como ausencia de estrés."""
    status = season_status(query)
    if not status["seasonal"] or not status["outside"]:
        return
    if status["outside"] == status["total"]:
        st.warning(texts.OUT_OF_SEASON.format(
            serie=query.label, temporada=status["season_name"],
            ventana=status["window"], dekad=query.window_label))
    else:
        st.warning(texts.PARTIAL_SEASON.format(
            n=status["outside"], total=status["total"],
            temporada=status["season_name"]))


def season_origin(query: Query, muni: pd.DataFrame):
    """De qué temporada sale cada valor del indicador combinado.

    Responde en pantalla la pregunta que el nombre del indicador no contesta:
    qué se está seleccionando cuando se toma el más alto de las dos temporadas.
    """
    if query.series_id != cfg.ASI_COMBINED or "season" not in muni:
        return
    d = muni[muni["dekad_id"] == query.end].dropna(subset=["mean"])
    if d.empty:
        return
    counts = d["season"].value_counts()
    partes = [f"**{cfg.SEASONS.get(k, k).split(' (')[0].lower()}** en "
              f"{n} municipios" for k, n in counts.items()]
    st.caption(f"En {dekad_label(query.end)} el valor más alto viene de la "
               + " y de la ".join(partes) + ".")


def summary(query: Query, muni: pd.DataFrame, cut: pd.DataFrame):
    """Cifras de encabezado del último dekad de la ventana.

    El promedio se toma siempre del agregado ponderado por píxeles válidos, no
    del promedio de las medias municipales: promediar municipios sin ponderar le
    daría a uno diminuto el mismo peso que a uno con diez veces más área de
    cultivo, y son más de tres puntos de diferencia.
    """
    with_data = cut.dropna(subset=["mean"])
    if with_data.empty:
        return
    last = to_country(muni)
    last = last[last["dekad_id"] == query.end]
    scope = "del área seleccionada" if query.departments else "nacional"
    c1, c2, c3 = st.columns(3)
    if len(last):
        c1.metric(f"Promedio {scope} · {dekad_label(query.end)}",
                  f"{last['mean'].iloc[0]:.2f}",
                  help=f"{query.unit}. Ponderado por píxeles válidos.")
    at_last = with_data[with_data["dekad_id"] == query.end]
    if query.level == "pais":
        # Contar "países con dato" no informa nada. Lo que importa es cuántos
        # municipios sostienen la cifra nacional de ese dekad.
        aportan = int(at_last["n_muni"].iloc[0]) if len(at_last) else 0
        c2.metric("Municipios que aportan", f"{aportan:,}",
                  help="Municipios con dato válido que entran en el promedio "
                       "ponderado de ese dekad.")
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
    no: una animación de cientos de cuadros no se puede leer y además obliga al
    navegador a cargar la geometría una vez por dekad. En ese caso se muestra el
    peor valor que cada unidad alcanzó en la ventana, que es la pregunta que uno
    le hace a un periodo largo.
    """
    data = muni if query.level == "municipio" else cut
    if data.empty:
        st.info(texts.NO_DATA)
        return
    extra = {c: ":.0f" for c in ("pct_gt40", "pct_lt0.35", "p90")
             if c in data.columns}
    n_dekads = data["dekad_id"].nunique()
    resumen = not query.single and n_dekads > MAX_FRAMES

    if resumen:
        peor = "max" if query.family == "ASI" else "min"
        claves = [query.code_col, query.name_col]
        if query.name_col != "adm1_name" and "adm1_name" in data:
            claves.append("adm1_name")
        data = (data.groupby(claves, as_index=False, observed=True)
                .agg(**{"mean": ("mean", peor), "km2": ("km2", "max")}))
        titulo = (f"{query.label} · {'mayor' if peor == 'max' else 'menor'} "
                  f"valor de la ventana")
        subtitulo = (f"{query.window_label}, {n_dekads} dekads. Cada "
                     f"{query.unit_name} se pinta con el "
                     f"{'mayor' if peor == 'max' else 'menor'} valor que "
                     f"alcanzó en ese periodo, no con el del último dekad.")
        extra = {}
    else:
        titulo = f"{query.label} · {query.window_label}"
        subtitulo = texts.MAP_SUBTITLE.format(unidad=query.unit_name)

    fig = viz.class_map(
        data, geojson(query.level), query.family, titulo, subtitulo,
        animation=None if (query.single or resumen) else "dekad_id",
        hover_extra=extra, code_col=query.code_col, name_col=query.name_col)
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, width="stretch")
    if resumen:
        st.caption(f"Para ver la secuencia dekad por dekad, acorte la ventana a "
                   f"{MAX_FRAMES} dekads o menos, o elija un dekad único.")
    elif not query.single:
        st.caption("Cada cuadro de la animación es un dekad. El control de "
                   "abajo recorre la ventana seleccionada.")
    if query.level == "departamento":
        st.caption(texts.DEPARTMENT_MAP)


def view_municipal_ranking(query: Query, muni: pd.DataFrame):
    """Los municipios en el extremo, seguidos en el tiempo.

    Con un rango es una matriz municipio por dekad: muestra a la vez el cuándo y
    el dónde, y ordena por el peor valor que cada municipio alcanzó en la
    ventana, no por el del último dekad, que dejaría fuera a quien tuvo el pico
    a mitad del periodo. Con un solo dekad la matriz sería una columna, así que
    la vista es un ranking ordenado.
    """
    if muni.empty:
        st.info(texts.NO_DATA)
        return
    top = st.slider("Municipios en el ranking", 10, 100, 50, 10,
                    key="top_ranking")
    peor = "mayor" if query.family == "ASI" else "menor"
    if query.single:
        fig = viz.ranking_fig(
            muni[muni["dekad_id"] == query.end], "mean",
            f"Los {top} municipios con {peor} {query.label}",
            f"{dekad_label(query.end)}.", family=query.family, top=top,
            label=query.unit, height=max(420, 18 * top))
    else:
        fig = viz.heatmap_panel(
            muni, "mean", f"Los {top} municipios con {peor} valor de la ventana",
            f"{query.window_label}. Cada fila es un municipio y cada columna un "
            f"dekad; el orden va del {peor} valor alcanzado en el periodo.",
            family=query.family, top=top, ref_dekad=None,
            label=query.unit, height=max(480, 15 * top))
    if fig is None:
        st.info(texts.NO_DATA)
        return
    st.plotly_chart(fig, width="stretch")

    if not query.single:
        area = viz.severity_area_fig(
            muni, query.family, "Superficie por clase de severidad",
            "km2 en cada clase, dekad por dekad. Responde cuánta superficie y "
            "no solo cuán intenso, que es la pregunta de quien reparte "
            "recursos.")
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
            f"{dekad_label(query.end)}. Ponderado por píxeles válidos.",
            family=query.family, top=18, label=query.unit, height=520)
        if fig:
            st.plotly_chart(fig, width="stretch")
        st.caption("Con un rango de fechas esta vista pasa a ser una serie de "
                   "tiempo por departamento.")
        return

    d = cut.dropna(subset=["mean"]).sort_values("dekad_id")
    fig = px.line(d, x="date", y="mean", color="adm1_name",
                  labels={"mean": query.unit, "date": "", "adm1_name": ""},
                  height=540)
    fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>%{y:.2f}<extra>"
                                    "%{fullData.name}</extra>")
    viz.style_fig(fig, f"{query.label} por departamento",
                  f"{query.window_label}. Cada línea es un departamento, "
                  "ponderado por píxeles válidos del ráster.", y_source=-0.16)
    st.plotly_chart(fig, width="stretch")
    st.caption("Haga clic en un departamento de la leyenda para aislarlo, o "
               "doble clic para ver solo ese.")


def _dashboard_window(query: Query) -> tuple[str, str]:
    """Ventana del tablero nacional.

    Con un solo dekad seleccionado no hay serie que dibujar, así que se muestran
    los 18 meses que terminan en ese dekad. Es la ventana del cuaderno y se dice
    en el subtítulo, para que nadie lea el gráfico como si fuera el dekad.
    """
    if not query.single:
        return query.start, query.end
    available = dekads(query.series_id)
    inicio = dekad_window(query.end, DASHBOARD_WINDOW)[0]
    return max(inicio, available[0]), query.end


def view_country(query: Query, cut: pd.DataFrame):
    """Serie nacional: primero la línea del indicador, después los tres
    indicadores sobre el mismo eje temporal."""
    start, end = _dashboard_window(query)
    ampliada = (start, end) != (query.start, query.end)
    serie = to_country(load(query.series_id, start, end))
    if serie.empty:
        st.info(texts.NO_DATA)
        return
    nota = (f"Ventana ampliada a los últimos 18 meses hasta "
            f"{dekad_label(end)}: una serie necesita más de un dekad."
            if ampliada else f"{query.window_label}.")
    fig = viz.series_fig(
        serie, "mean", f"{query.label} · nacional", nota,
        label=query.unit, family=query.family,
        threshold=0.35 if query.family == "VCI" else None,
        threshold_label="umbral FAO 0,35" if query.family == "VCI" else "")
    if fig:
        st.plotly_chart(fig, width="stretch")

    st.divider()
    asi_id = query.series_id if query.family == "ASI" else cfg.ASI_COMBINED
    asi = to_country(load(asi_id, start, end))
    vci = to_country(load("vci", start, end)) if "vci" in panel.stored_series() \
        else pd.DataFrame()
    rain = national("serie_nacional_lluvia")
    if len(rain):
        rain = rain[(rain["dekad_id"] >= start) & (rain["dekad_id"] <= end)]
    tablero = viz.dashboard_fig(
        asi, vci, rain, "Estrés, vegetación y lluvia en el mismo eje",
        "Tres indicadores independientes: déficit hídrico acumulado en el "
        "cultivo (ASI), estado de la vegetación (VCI) y lluvia observada frente "
        "a su normal. Leerlos juntos evita confundir un exceso de agua con una "
        "sequía.")
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
            asi_nat, pctl, n_base, years,
            f"{year} frente a la norma histórica",
            f"ASI nacional de la temporada primera, mayo a octubre. La franja "
            f"azul es el rango habitual (p10-p90) de los {n_base} años previos "
            f"a {year}. Serie oficial de GIEWS ponderada por área de cultivo.")
        if fig:
            st.plotly_chart(fig, width="stretch")

        matrix = viz.climatology_matrix(
            asi_nat, "Climatología del estrés agrícola",
            "ASI nacional por dekad de la temporada primera. Cada franja roja "
            "horizontal es una sequía agrícola.")
        if matrix:
            st.plotly_chart(matrix, width="stretch")

    if not rain.empty:
        start, end = _dashboard_window(query)
        window = rain[(rain["dekad_id"] >= start) & (rain["dekad_id"] <= end)]
        if len(window) < 3:
            window = rain.tail(DASHBOARD_WINDOW)
        fig = viz.rainfall_fig(
            window, "Lluvia observada frente a su promedio histórico",
            "Lluvia dekadal nacional ponderada por área de cultivo. El promedio "
            "de largo plazo es el que publica FAO y no se recalcula.")
        if fig:
            st.plotly_chart(fig, width="stretch")


def view_data(query: Query, cut: pd.DataFrame):
    if cut.empty:
        st.info(texts.NO_DATA)
        return
    shown = for_display(cut)
    st.caption(f"{len(shown):,} filas · {query.unit_name} · {query.label} · "
               f"{query.window_label}")
    st.dataframe(shown, width="stretch", hide_index=True, height=460)
    csv = shown.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Descargar CSV del corte en pantalla", csv,
        file_name=f"asis_{query.slug()}.csv", mime="text/csv",
        help=texts.DOWNLOAD_HELP, type="primary")
    if query.level != "municipio":
        st.caption("Los percentiles (p10, mediana, p90) existen solo a nivel "
                   "municipal: el p90 de un departamento no es el promedio de "
                   "los p90 de sus municipios, así que no se publica.")


def limits_panel():
    st.divider()
    st.subheader("Limitaciones")
    st.caption("Lo que este panel no dice. Conviene leerlo antes de citar "
               "cualquier cifra fuera de la app.")
    left, right = st.columns(2)
    for i, (title, body) in enumerate(texts.LIMITS):
        with (left if i % 2 == 0 else right):
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(body)
    st.caption(texts.AI_NOTE)


# --- Página ------------------------------------------------------------------
def render(query: Query, muni: pd.DataFrame, cut: pd.DataFrame, name: str):
    if name == "Mapa":
        view_map(query, muni, cut)
    elif name == "Ranking municipal":
        view_municipal_ranking(query, muni)
    elif name == "Series por departamento":
        view_department_series(query, cut)
    elif name == "Serie nacional":
        view_country(query, cut)
    elif name == "Contexto nacional":
        view_context(query)
    elif name == "Datos":
        view_data(query, cut)


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
    header(mf, query)
    season_notice(query)
    muni, cut = slice_for(query)

    if muni.empty:
        st.info(texts.NO_DATA)
        limits_panel()
        return

    summary(query, muni, cut)
    season_origin(query, muni)

    names = TABS[query.level]
    for tab, name in zip(st.tabs(names), names):
        with tab:
            render(query, muni, cut, name)

    limits_panel()


if __name__ == "__main__":
    main()
